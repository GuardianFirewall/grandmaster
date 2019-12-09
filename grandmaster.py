#!/usr/bin/env python3
# external imports
import os, argparse, subprocess, re, sys, pathlib, time, argcomplete
import urllib3, certifi, requests
from multiprocessing import Process, Queue
from pathlib import Path
from threading import Thread
from os import path

# local imports
from version import *
from helpers import *
from downloads import *
from image4 import *
from devicefinder import DeviceFinder
from foreman import Foreman

PROGRAM_NAME = os.path.basename(__file__)
LOGGING = Logging.getInstance()

# globals
WORKING_BUNDLE_PATH = ''
WORKING_TARGET_DEVICE = ''
WORKING_TARGET_BUILD = ''
WORKING_TARGET_IOSVER = None
LOG_HEADER_WIDTH = 45
KEY_JSON_STORE_PATH = ''
LOADED_CONFIG = None

# argparse methods
# --------------
# argparse type checking
def dir_path(string):
	if os.path.isdir(string):
		return string
	else:
		return None

# argparse
parser = argparse.ArgumentParser(description='grandmaster.py | an automated iOS firmware decryption tool.')
parser.add_argument('--generate', help="Generate a gm.config at a given path. (Use --build and --model to skip manual input.)", action="store", metavar="GM_OUTPUT_PATH")
parser.add_argument('--model', help="Specify a device model for --generate to use.", action="store")
parser.add_argument('--boardconfig', help="Specify a BoardConfig for --generate to use.", action="store")
parser.add_argument('--build', help="Specify a firmware build number for --generate to use.", action="store")
parser.add_argument('--iosver', help="Specify an iOS firmware number for --generate to use.", action="store")
parser.add_argument('--overwrite', help="Automatically overwrite gm.config if it already exists during --generate", action="store_true")
parser.add_argument('--download', help="partialzip all availble firmware images.", type=dir_path, metavar="PATH_TO_GM_CONFIG")
parser.add_argument('--extractkbags', help="Extract firmware KBAGs and store them.", type=dir_path, metavar="PATH_TO_GM_CONFIG")
parser.add_argument('--decryptkbags', help="Decrypt firmware KBAGs using ipwndfu and store the keys.", type=dir_path, metavar="PATH_TO_GM_CONFIG")
parser.add_argument('--decryptimages', help="Run decryption on all images specified in the config.", type=dir_path, metavar="PATH_TO_GM_CONFIG")
parser.add_argument('--automate', help="Downloads, extracts and decrypts KBAGs, then decrypts all images in one run.", type=dir_path, metavar="PATH_TO_GM_CONFIG")
parser.add_argument('--noprompt', help="Don't prompt for any additional actions during --automate", action="store_true")
parser.add_argument('--autosubmit', help="Automatically submit to Foreman after --automate completes.", action="store_true")
parser.add_argument('--scanusb', help="Find all DFU / Recovery Mode devices and print out some information about them", action="store_true")
parser.add_argument('--devkbag', help="Use the development KBAG for decryption.", action="store_true")
parser.add_argument('--foreman', help="Submit a completed gm.config to the Foreman keystore server.", type=dir_path, metavar="PATH_TO_GM_CONFIG")
parser.add_argument('--foremanbags', help="Submit extracted keybags to the Foreman server for decryption.", type=dir_path, metavar="PATH_TO_GM_CONFIG")
parser.add_argument('--version', help=("Print "+PROGRAM_NAME+" version"), action="store_true")
parser.add_argument('-v', '--verbose', help="Enable verbose logging.", action="store_true")
argcomplete.autocomplete(parser)
args = parser.parse_args()

# primary methods
# --------------
# handle downloading
def handleDownloading():
	LOGGING.PRINT("Starting firmware downloads...")
	downloadQueue = Queue()
	downloadThreadPool = []
	try:
		imagesToVerify = []
		if LOADED_CONFIG['build'] is not None and LOADED_CONFIG['device'] is not None:
			firmwareURL = getFirmwareURL(LOADED_CONFIG['build'], LOADED_CONFIG['device'])
			for firmwareImagePath in LOADED_CONFIG['images'].keys():
				if path.exists(str(WORKING_BUNDLE_PATH / os.path.basename(firmwareImagePath))) is not True:
					proc = Process(target=partialzipDownloadFromURL, args=(firmwareURL, firmwareImagePath, WORKING_BUNDLE_PATH))
					downloadThreadPool.append(proc)
					imagesToVerify.append(str(WORKING_BUNDLE_PATH / os.path.basename(firmwareImagePath)))
					proc.start()
				else:
					LOGGING.PRINT("Firmware file exists, skipping redownload.")
		LOGGING.DEBUG("Que'd "+str(len(downloadThreadPool))+" downloads")
		for downloadThread in downloadThreadPool:
			downloadThread.join()
		for verifyImagePath in imagesToVerify:
			imageParser = IM4P_Parser(verifyImagePath)
			imageParser.parse()
			if len(imageParser.type()) == 4:
				LOGGING.PRINT("["+os.path.basename(verifyImagePath)+"] image is OK!")
		LOGGING.PRINT("Done!", True, '\n', 'green')
	except (KeyboardInterrupt, SystemExit):
		LOGGING.PRINT("Received program kill request, ending download threads.")

# process an img4/im4p file given its path an its ivkey
def decryptImage(imagePath, imageIVKey):
	DECRYPTION_OUTPUT_PATH = str(imagePath)+'.decrypted'
	LOGGING.PRINT("decrypting "+str(imagePath)+' to '+str(DECRYPTION_OUTPUT_PATH), True, '\n', 'sky_blue_2')
	img4cmd = ['img4', '-i', str(imagePath), '-o', str(DECRYPTION_OUTPUT_PATH), imageIVKey] # img4 -i imagePath -o DECRYPTION_OUTPUT_PATH imageIVKey
	decryptBuff = ''
	p = subprocess.Popen(img4cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	for line in p.stdout:
		decryptBuff += line.decode('utf-8').strip()
	p.wait()
	# check the img4 output for "invalid key"
	if "invalid ivkey" in decryptBuff:
		LOGGING.DEBUG(decryptBuff)
		return False		
	LOGGING.DEBUG("["+os.path.basename(DECRYPTION_OUTPUT_PATH)+"] validating decryption result")
	# branch out for some loose validation on the decryption output
	if validateImageDecryption(DECRYPTION_OUTPUT_PATH):
		# dump the iboot "header" if we're running in verbose mode
		if LOGGING.isVerbose():
			dumpiBootHeader(DECRYPTION_OUTPUT_PATH)
		LOGGING.PRINT("["+os.path.basename(DECRYPTION_OUTPUT_PATH)+"] image appears to be OK.", False, '\n', 'green')
		return True
	else:
		LOGGING.PRINT("["+os.path.basename(DECRYPTION_OUTPUT_PATH)+"] decryption may have failed, double check the result in a hexeditor.", False, '\n', 'light_red')
		return False

# loads the JSON file at the path 
def beginProcessingImages():
	firmwareImageDictionary = LOADED_CONFIG['images']
	LOGGING.DEBUG("Initializing keys for bundle")
	for firmwareImage in firmwareImageDictionary.keys():
		LOGGING.DEBUG(("Firmware File => "+firmwareImage).ljust(60)+(" | ")+("IVKey => "+firmwareImageDictionary[firmwareImage]))
	# make an array of decryption threads to run
	processingThreads = []
	for firmwareImage in firmwareImageDictionary.keys():
		firmwarePath = WORKING_BUNDLE_PATH / os.path.basename(firmwareImage)
		processingThreads.append(Thread(target=decryptImage, args=(firmwarePath, firmwareImageDictionary[firmwareImage])))
	# spawn the threads
	for newThread in processingThreads:
		newThread.start()
		newThread.join()
	LOGGING.PRINT("Done!", True, '\n', 'green')

# get the kbag for an image
def getKBAGForImage(imagePath):
	img4cmd = ['img4', '-i', imagePath, '-b'] # img4 -i imagePath -b 
	stdbuff = ""
	p = subprocess.Popen(img4cmd, stdout=subprocess.PIPE)
	for line in p.stdout:
		stdbuff += line.decode('utf-8').strip()+'\n'
	p.wait()
	kbags = stdbuff.splitlines() # split out each kbag by newline
	kbagArray = []
	if len(kbags) > 0:
		kbagArray.append(kbags[0]) # append kbag #1
		kbagArray.append(kbags[1]) # append kbag #2
	return kbagArray

# handle retrieving the kbags
def handleKBAGExtraction():
	global LOADED_CONFIG
	LOGGING.PRINT("Extracting keybags...")
	firmwareImageDictionary = LOADED_CONFIG['images']
	for firmwareImage in firmwareImageDictionary.keys():
		imageBaseName = os.path.basename(firmwareImage)
		LOGGING.PRINT("Retrieving keybags for image "+imageBaseName)
		# grab the KBAGs for out firmware path
		kbag_result = getKBAGForImage(WORKING_BUNDLE_PATH / imageBaseName)
		# check if we actually got kbags extracted 
		if len(kbag_result) > 0:
			# append our kbag to our LOADED_CONFIG's firmware image KBAGs array
			LOADED_CONFIG['kbags'][firmwareImage] = kbag_result
		elif "[e] cannot get keybag" in kbag_result:
			LOGGING.PRINT("Keybag extraction failed, however, this image may not require decryption.")
		else: # error out if there is none 
			LOGGING.PRINT("Keybag extraction failed. maybe you forgot to --download?")
	LOGGING.DEBUG("Writing kbags to config file...")
	# rewrite our newly mutated LOADED_CONFIG to its filepath
	writeJSON(LOADED_CONFIG, KEY_JSON_STORE_PATH)
	LOGGING.PRINT("Done!", True, '\n', 'green')

# get pwndfu mode 
def handlePwnDFU():
	LOGGING.PRINT('pwning target device')
	ipwnBuff = ''
	ipwndfucmd = ['python', 'ipwndfu', "-p"]
	p = subprocess.Popen(ipwndfucmd, stdout=subprocess.PIPE, cwd='ipwndfu/')
	for line in p.stdout:
		ipwnBuff += line.decode('utf-8').strip()+'\n'
	p.wait()
	if "No Apple device in DFU Mode" in ipwnBuff or p.returncode is not 0:
		return False;
	LOGGING.DEBUG('ipwndfu exited => '+str(p.returncode))	
	return True

# dfu mode spin
def waitForDFUAndPWN():
	foundDFUDevice = False
	deviceFinderObj = DeviceFinder()
	LOGGING.PRINT("Waiting for DFU device to appear", True, "")
	waitCounter = 0
	USBserialStr = None
	while foundDFUDevice is False:
		if waitCounter > 60:
			LOGGING.PRINT("Timed out finding a DFU mode device. Try again.")
			exit(-1) # exit early
		LOGGING.PRINT(".", False, '', 'aquamarine_3')
		sys.stdout.flush()
		USBserialStr = deviceFinderObj.findAllUSBDevices()
		if USBserialStr is not None:
			foundDFUDevice = True
		time.sleep(2) # sleep for 2 seconds before searching again
		waitCounter += 1
	sys.stdout.write('\n')
	LOGGING.PRINT("Found device!", True, '\n', 'green')
	LOGGING.PRINT(USBserialStr)
	if ("PWND:[checkm8]" in USBserialStr):
		LOGGING.PRINT("Device is already pwned!", True, '\n', 'green')
	else:
		if handlePwnDFU() is False:
			LOGGING.PRINT('iPhone failed to enter pwned dfu mode! Please try again...', True, '\n', 'light_red')
			time.sleep(2)
			LOGGING.PRINT("--------------------", True, '\n', 'green')
			waitForDFUAndPWN() # loop back if pwning failed
		else:
			LOGGING.PRINT("pwned!")

# handle decrypting the kbags (via ipwndfu)
def handleKBAGDecryption():
	LOGGING.PRINT("running keybag decryption...")
	# branch out to handle waiting for a DFU device and then pwning it
	waitForDFUAndPWN()
	# get a copy of our firmware images to process
	firmwareImageDictionary = LOADED_CONFIG['images']
	# get a copy of our firmware images KBAGs to process
	firmwareKBAGDictionary = LOADED_CONFIG['kbags']
	# enumerate through our available KBAGs
	kbagImageCounter = 0
	firmwareImageList = list(firmwareKBAGDictionary)
	while kbagImageCounter < len(firmwareImageList):
		firmwareImageName = firmwareImageList[kbagImageCounter]
		imageBaseName = os.path.basename(firmwareImageName)
		LOGGING.PRINT("Decrypting KBAG for "+imageBaseName)
		kbagCount = 0
		# set the target KBAG for decryption
		if args.devkbag:
			LOGGING.PRINT("Using development keybag")
			firmwareKBAG = firmwareKBAGDictionary[firmwareImageName][1]
		else:
			LOGGING.PRINT("Using production keybag")
			firmwareKBAG = firmwareKBAGDictionary[firmwareImageName][0]
		# skip KBAG decryption if our firmware dictionary already has a IVKey populated 
		if len(firmwareImageDictionary[firmwareImageName]) > 0:
			LOGGING.PRINT("We already have a ivkey for this image, skipping...")
			kbagImageCounter += 1
			continue
		kbagCount += 1
		ipwndfucmd_decrypt = ['python', 'ipwndfu', "--decrypt-gid", firmwareKBAG]
		ipwnBuff = ''
		gotKBAG = None
		try:
			p = subprocess.Popen(ipwndfucmd_decrypt, stdout=subprocess.PIPE, cwd='ipwndfu/')
			for line in p.stdout:
				ipwnBuff += line.decode('utf-8').strip()+'\n'
			p.wait()
			# check if we errored out at all
			hexSearch = re.compile(r'(^([A-Fa-f0-9]{2}){32,96}$)')
			if ("ERROR" in ipwnBuff) or ("No Apple Device" in ipwnBuff) or (re.search(hexSearch, ipwnBuff) is False):
				LOGGING.PRINT("Device error'd out during keybag decryption, trying again.", True, '\n', 'light_red')
				# branch out to handle waiting for a DFU device and then pwning it
				waitForDFUAndPWN()
				kbagImageCounter -= 1
				continue
			# if not we're good to go
			gotKBAG = ipwnBuff.split('\n')[1]
		except Exception as e:
			LOGGING.PRINT('CAUGHT EXCEPTION while running ipwndfu', True, '\n', 'light_red')
			LOGGING.PRINT(str(e))
			kbagImageCounter -= 1
			# branch out to handle waiting for a DFU device and then pwning it
			waitForDFUAndPWN()
		if gotKBAG:
			firmwareImageDictionary[firmwareImageName] = gotKBAG
			LOGGING.PRINT("["+os.path.basename(WORKING_BUNDLE_PATH / imageBaseName)+"] "+gotKBAG)
			LOADED_CONFIG['images'] = firmwareImageDictionary
			writeJSON(LOADED_CONFIG, WORKING_BUNDLE_PATH / 'gm.config')
		kbagImageCounter += 1					
	LOGGING.PRINT("Done!", True, '\n', 'green')		

# generate a grandmaster config
def generateConfig():
	global WORKING_TARGET_BUILD
	global WORKING_TARGET_IOSVER
	# check if a gm.config exists
	if os.path.exists(WORKING_BUNDLE_PATH / 'gm.config') and (args.overwrite is None or args.overwrite is False):
		if confirmationPrompt("gm.config already exists here, should we overwite?") is False:
			LOGGING.PRINT("Goodbye!")
			exit(0)
		else:
			LOGGING.PRINT("Overwiting existing gm.config")
	# make a new config dictionary
	newConfigData = {}
	# append the two values we already have and put placeholders if else
	newConfigData['images'] = {}
	newConfigData['kbags'] = {}
	newConfigData['device'] = WORKING_TARGET_DEVICE
	# only one of the following statements should be used here
	if WORKING_TARGET_BUILD is None:
		WORKING_TARGET_BUILD = findBuildNumberByiOSVersion(WORKING_TARGET_DEVICE, WORKING_TARGET_IOSVER)
	if WORKING_TARGET_IOSVER is None:
		WORKING_TARGET_IOSVER = findiOSVersionByBuildNumber(WORKING_TARGET_DEVICE, WORKING_TARGET_BUILD)
	newConfigData['build'] = WORKING_TARGET_BUILD
	newConfigData['iosver'] = WORKING_TARGET_IOSVER
	boardConfigNumber = DeviceFinder().modelForBoardConfig(WORKING_TARGET_DEVICE)
	LOGGING.PRINT("Retrieving available firmware images...")
	# grab the firmware url
	firmwareURL = getFirmwareURL(newConfigData['build'], newConfigData['device'])
	if len(firmwareURL) > 0:
		newConfigData['download'] = firmwareURL
		allFoundImages = findAllFirmwareImages(firmwareURL)
		for foundImage in allFoundImages:
			key = foundImage
			try:
				if newConfigData['images'][key] is None:
					pass
			except KeyError as e:
				if DeviceFinder().checkIfImageBoardConfigMatchesDevice(WORKING_TARGET_DEVICE, foundImage) is False:
					continue
				LOGGING.PRINT("image => "+foundImage)
				newConfigData['images'][key] = ""
	else:
		LOGGING.PRINT("Couldn't find a firmware URL for this build")
	LOGGING.DEBUG("Writing config to "+str(WORKING_BUNDLE_PATH / 'gm.config'))
	writeJSON(newConfigData, WORKING_BUNDLE_PATH / 'gm.config')
	LOGGING.PRINT("Done!", True, '\n', 'green')
	LOGGING.PRINT("Wrote config file to "+str(WORKING_BUNDLE_PATH / 'gm.config'))
	LOGGING.PRINT("\nExample grandmaster usage from here;", False)
	LOGGING.PRINT("\t./%s --automate %s" % (PROGRAM_NAME, str(WORKING_BUNDLE_PATH)), False)
	LOGGING.PRINT("\t./%s --download %s" % (PROGRAM_NAME, str(WORKING_BUNDLE_PATH)), False)

# check if our working directory exists
def checkIfDirectoryExists(directoryPath, shouldMkdir=False):
	if not os.path.exists(directoryPath):
		if shouldMkdir:
			LOGGING.PRINT("Creating path @ "+str(directoryPath))
			pathlib.Path(directoryPath).mkdir(parents=True, exist_ok=True)
			return checkIfDirectoryExists(directoryPath, False)
		else:
			return False
	else:
		return True

# check WORKING_BUNDLE_PATH is valid or exit
def checkWorkingBundlePath():
	if checkIfDirectoryExists(WORKING_BUNDLE_PATH) is False:
		print("Directory doesn't exist!")
		exit(-1)  # exit early

# load the config file into our LOADED_CONFIG global
def loadConfig():
	global LOADED_CONFIG
	global KEY_JSON_STORE_PATH
	checkWorkingBundlePath()
	LOGGING.DEBUG("Loading config from "+str(WORKING_BUNDLE_PATH))
	# this should be where our gm.config is 
	KEY_JSON_STORE_PATH = WORKING_BUNDLE_PATH / 'gm.config'
	if not os.path.exists(KEY_JSON_STORE_PATH):
		LOGGING.DEBUG("'"+KEY_JSON_STORE_PATH+"' does not exist! bailing out...", True, '\n', 'light_red')
		exit(-1) # exit early
	# load the config
	LOADED_CONFIG = loadJSON(KEY_JSON_STORE_PATH)
	if LOADED_CONFIG is None:
		LOGGING.DEBUG("Config failed to load! bailing out...")
		exit(-1) # exit early

# print out version
def print_version():
	print('%s%sGrandmaster%s %s%sv%s%s (%s)' % (fg('green'), bg('black'), attr('reset'), fg('aquamarine_3'), bg('black'), GM_VERSION_STRING, attr('reset'), GM_VERSION_TAG));

# da main
def main():
	global WORKING_BUNDLE_PATH
	global WORKING_TARGET_DEVICE
	global WORKING_TARGET_BUILD
	global WORKING_TARGET_IOSVER
	global VERBOSE_LOGGING_ENABLED
	# just print out our version and exit, else print it anyways
	if args.version:
		print_version();
		exit(0)
	else:
		print_version();
	# enable verbose logging
	if args.verbose:
		LOGGING.setVerbose(True)
		LOGGING.DEBUG("Verbose logging enabled")
	# check if 'img4' exists in our users PATH
	if checkIfimg4libBinaryExists() is not True:
		LOGGING.PRINT("Fatal Error!\nimg4 was not found on your machine's PATH.\nPlease compile and install it from xerub's img4lib.", True, '\n', 'light_red')
		exit(-1)  # exit early
	# check the .firmwares cache
	checkFirmwaresFileCache()
	# argument logic
	if args.generate: # do generate
		WORKING_BUNDLE_PATH = Path(args.generate)
		if args.boardconfig:
			WORKING_TARGET_DEVICE = findModelByBoardConfig(args.boardconfig)
			LOGGING.DEBUG("WORKING_TARGET_DEVICE => "+WORKING_TARGET_DEVICE)
		else:
			WORKING_TARGET_DEVICE = args.model
		if WORKING_TARGET_DEVICE is None: # check our arg
			LOGGING.PRINT("Please specify --model", True, '\n', 'light_red')
			exit(-1) # exit early
		WORKING_TARGET_BUILD = args.build
		WORKING_TARGET_IOSVER = args.iosver
		if WORKING_TARGET_BUILD is None and WORKING_TARGET_IOSVER is None: # check our arg
			LOGGING.PRINT("Please specify --build or --iosver", True, '\n', 'light_red')
			exit(-1) # exit early
		if checkIfDirectoryExists(WORKING_BUNDLE_PATH, True):
			generateConfig() # branch out to generateConfig
		else:
			LOGGING.PRINT("Directory doesn't exist and couldn't be created! mkdir this path and verify your permissions.", True, '\n', 'light_red')
			exit(-1) # exit early
	elif args.decryptimages: # run decryption
		WORKING_BUNDLE_PATH = Path(args.decryptimages)
		loadConfig() # load our config
		beginProcessingImages()
	elif args.download: # run download
		WORKING_BUNDLE_PATH = Path(args.download)
		loadConfig() # load our config
		handleDownloading()
	elif args.extractkbags: # grab kbags
		WORKING_BUNDLE_PATH = Path(args.extractkbags)
		loadConfig() # load our config
		handleKBAGExtraction()
	elif args.decryptkbags: # decrypt kbags
		WORKING_BUNDLE_PATH = Path(args.decryptkbags)
		loadConfig() # load our config
		handleKBAGDecryption()
	elif args.automate: # do "automate"
		WORKING_BUNDLE_PATH = Path(args.automate)
		loadConfig() # load our config
		automate_start_time = time.time()
		handleDownloading()
		handleKBAGExtraction()
		handleKBAGDecryption()
		beginProcessingImages()
		automate_end_time = time.time()
		LOGGING.PRINT("Automate finished in "+str(automate_end_time-automate_start_time)+" seconds")
		if args.autosubmit:
			loadConfig() # reload the config before submitting
			Foreman().submit(LOADED_CONFIG)
		elif args.noprompt is False:
			shouldWeForeman = confirmationPrompt("Would you like to try and submit to Foreman?")
			if shouldWeForeman:
				loadConfig() # reload the config before submitting
				Foreman().submit(LOADED_CONFIG)
	elif args.scanusb: # scan for usb dfu / recovery mode devices
		foundDevice = DeviceFinder().findAllUSBDevices()
		if foundDevice is not None:
			LOGGING.PRINT("Found USB device!\n"+foundDevice)
		else:
			LOGGING.PRINT("Did not find any DFU or recovery mode device.", True, '\n', 'light_red')
	elif args.foreman: # submit our gm.config to the Foreman server
		WORKING_BUNDLE_PATH = Path(args.foreman)
		loadConfig()
		Foreman().submit(LOADED_CONFIG)
	elif args.foremanbags: # submit our gm.config to the Foreman server for keybag decryption
		WORKING_BUNDLE_PATH = Path(args.foremanbags)
		loadConfig()
		Foreman().submitKeybags(LOADED_CONFIG)
	else:
		parser.print_help()
	LOGGING.PRINT("\nGoodbye!", False, '\n', 'green')	
	exit(0)

if __name__== "__main__":
	try:
		main()
	except KeyboardInterrupt:
		LOGGING.PRINT("\nGoodbye!", False, '\n', 'green')
		exit(0)
