# firmware download methods
import subprocess, re, urllib3, certifi, time, requests, os, stat, datetime
from multiprocessing import Process, Queue
from datetime import date
from helpers import *

LOGGING = Logging.getInstance()

# http(s) pool
http = urllib3.PoolManager(ca_certs=certifi.where(), retries=10) # http(s) pool

def getFirmwares(): 
	# https://api.ipsw.me/v2.1/firmwares.json
	r = requests.get(url='https://api.ipsw.me/v2.1/firmwares.json')
	data = r.json()
	return data['devices']

def getFirmwareURL(buildid, model):
	allFirmwares = getFirmwares()
	modelFirmwaresArray = allFirmwares[model]['firmwares']
	foundURL = ''
	for availableFirmware in modelFirmwaresArray:
		if buildid in availableFirmware['buildid']:
			foundURL = availableFirmware['url']
	return foundURL

def findBuildNumberByiOSVersion(model, iosVersion):
	allFirmwares = getFirmwares()
	modelFirmwaresArray = allFirmwares[model]['firmwares']
	found = ''
	for availableFirmware in modelFirmwaresArray:
		if iosVersion in availableFirmware['version']:
			found = availableFirmware['buildid']
	return found

def findModelByBoardConfig(boardConfig):
	allFirmwares = getFirmwares()
	allDeviceKeys = allFirmwares.keys()
	found = ''
	for deviceKey in allDeviceKeys:
		if boardConfig in allFirmwares[deviceKey]['BoardConfig']:
			found = deviceKey
	return found

def findiOSVersionByBuildNumber(model, buildnumber):
	allFirmwares = getFirmwares()
	modelFirmwaresArray = allFirmwares[model]['firmwares']
	found = ''
	for availableFirmware in modelFirmwaresArray:
		if buildnumber in availableFirmware['buildid']:
			found = availableFirmware['version']
	return found

# check, download and cache our firmwares.json
def checkFirmwaresFileCache(): 
	LOGGING.DEBUG("checking .firmware cache")
	allFirmwares = getFirmwares()
	FIRMWARES_CACHE_FILENAME = '.firmwares'
	if os.path.exists(FIRMWARES_CACHE_FILENAME):
		cacheLastUpdateTime = os.stat(FIRMWARES_CACHE_FILENAME).st_mtime
		last_time = round((time.time() - cacheLastUpdateTime), 2) # hours
		LOGGING.DEBUG(".firmwares is "+str(last_time // 60)+" minutes old.");
		if (last_time // 3600) <= 6: # update every 6 hours 
			LOGGING.PRINT(".firmwares updated "+str(last_time // 3600)+" hours ago, skipping...")
			return;
		with open(FIRMWARES_CACHE_FILENAME, 'r') as firmwaresCacheFile:
			firmwaresCacheJSON = json.load(firmwaresCacheFile)
			if allFirmwares == firmwaresCacheJSON: # no changes have been made to the firmwares json data
				pass
			else:
				with open(FIRMWARES_CACHE_FILENAME, 'w') as f:
					json.dump(firmwaresCacheJSON, f)
	else:
		with open(FIRMWARES_CACHE_FILENAME, 'w') as f:
			json.dump(allFirmwares, f)
	return allFirmwares

# --- pzb --- 
# pzb - partialZipBrowser method
def partialzipDownloadFromURL(dlurl, dlpath, outputpath):
	start_time = time.time()
	LOGGING.PRINT("starting download for \'"+dlpath+"\' to "+str(outputpath))
	pzbcmd = ['pzb', '-g', dlpath, dlurl]
	p = subprocess.Popen(pzbcmd, stdout=subprocess.PIPE, cwd=outputpath)
	p.wait()
	LOGGING.PRINT(dlpath+" finished in "+str(round(time.time() - start_time, 2))+" seconds")

# pzb - partialZipBrowser list and find firmware files files
def partialzipListFromURL(dlurl, listPath):
	pzbcmd = ['pzb', '--list='+listPath, dlurl]
	p = subprocess.Popen(pzbcmd, stdout=subprocess.PIPE)
	stdbuff = ""
	for line in p.stdout:
		stdbuff += line.decode('utf-8').strip()+'\n'
	p.wait()
	resultsArray = []
	splitBuff = stdbuff.split("\n")
	for buffLine in splitBuff:
		splitLine = buffLine.split(" ")
		for lineSub in splitLine:
			# filter for im4p images, ignoring sep, aop, and plist files
			if (".im4p" in lineSub) and (".plist" not in lineSub) and ("AOP" not in lineSub) and ("sep" not in lineSub):
				resultsArray.append(lineSub)
	return resultsArray

# find all firmware images in an ipsw uring pzb
def findAllFirmwareImages(firmwareURL):
	LOGGING.PRINT("looking for images in 'Firmware/' (this may take a minute)")
	foundFirmwareImages = partialzipListFromURL(firmwareURL, "Firmware/")
	allImagePaths = []
	for foundImage in foundFirmwareImages:
		allImagePaths.append("Firmware/"+foundImage)
	return allImagePaths