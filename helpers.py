# misc helper methods
import json, os
from colored import fg, bg, attr

class Logging(object):
	__instance = None
	VERBOSE_LOGGING_ENABLED = False
	# init
	def __init__(self):
		if Logging.__instance != None:
			raise Exception("This class is a singleton!")
		else:
			Logging.__instance = self
	# static access method
	@staticmethod
	def getInstance():
		if Logging.__instance == None:
			Logging()
		return Logging.__instance 

	# get VERBOSE_LOGGING_ENABLED
	def isVerbose(self):
		self.DEBUG("VERBOSE_LOGGING_ENABLED => "+str(self.VERBOSE_LOGGING_ENABLED))
		return self.VERBOSE_LOGGING_ENABLED

	# set VERBOSE_LOGGING_ENABLED
	def setVerbose(self, shouldVerboseLog):
		self.VERBOSE_LOGGING_ENABLED = shouldVerboseLog

	# verbose debug printing
	def DEBUG(self, str):
		if self.VERBOSE_LOGGING_ENABLED:
			print("[GM_DEBUG] "+str)

	# standard printing
	def PRINT(self, str, appendGrandmasterTag=True, endStr='\n', outputColor='aquamarine_3'):
		if appendGrandmasterTag is False:
			print("%s%s%s%s" % (fg(outputColor), bg('black'), str, attr('reset')), end=endStr)
		else:
			print("%s%s[GM]%s %s%s%s%s" % (fg("purple_1b"), bg('black'), attr('reset'), fg(outputColor), bg('black'), str, attr('reset')), end=endStr)

# who reinvents wheels? https://gist.github.com/garrettdreyfus/8153571
def confirmationPrompt(question):
	while "input invalid":
		reply = str(input(question+' (y/n): ')).lower().strip()
		if reply[:1] == 'y':
			return True
		if reply[:1] == 'n':
			return False

# load and return a JSON object from its filepath 
def loadJSON(filePath):
	with open(filePath, 'r') as json_file:
		jsonObj = json.load(json_file)
		if jsonObj is not None:
			return jsonObj
		else: 
			return None

# write an object as JSON to a filepath
def writeJSON(obj, filepath):
	with open(filepath, 'w') as outfile:
		json.dump(obj, outfile, indent=4, sort_keys=True)

