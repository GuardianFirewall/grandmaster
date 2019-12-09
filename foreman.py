# Foreman related methods
import requests, os
from helpers import *
from version import *

LOGGING = Logging.getInstance()

class Foreman():
	"""Foreman - python helper to submit gm.config files to the Foreman server"""
	def __init__(self):
		super(Foreman, self).__init__()
		# set the foreman host
		if os.environ.get('FOREMAN_HOST') is not None:
			self.FOREMAN_HOST = os.environ.get('FOREMAN_HOST')
		else:
			self.FOREMAN_HOST = "foreman-public.sudosecuritygroup.com"
		# set the foreman port
		if os.environ.get('FOREMAN_PORT') is not None:
			self.FOREMAN_PORT = os.environ.get('FOREMAN_PORT')
		else:
			self.FOREMAN_PORT = 443
		# set the foreman api token
		if os.environ.get('FOREMAN_TOKEN') is not None:
			self.FOREMAN_TOKEN = os.environ.get('FOREMAN_TOKEN')
		else:
			self.FOREMAN_TOKEN = ""

	def submitKeybags(self, configData):
		# check for missing firmware keys
		availableImages = list(configData["kbags"].keys())
		for imageName in availableImages:
			if len(configData["kbags"][imageName]) <= 0:
				LOGGING.PRINT("Key for "+imageName+" is missing, removing it from the submission")
				del configData["kbags"][imageName]
		headers = {
			'User-Agent': 'grandmaster/'+GM_VERSION_STRING,
			'x-api-key':self.FOREMAN_TOKEN
		}
		r = requests.post("https://"+self.FOREMAN_HOST+":"+str(self.FOREMAN_PORT)+"/api/submit/keybags", json=configData, headers=headers)
		jsonResponse = r.json()
		if jsonResponse['result'] is False:
			LOGGING.PRINT("Foreman rejected the config. "+str(jsonResponse['error']), True, '\n', 'light_red')
			return False
		LOGGING.PRINT("Foreman accepted the config", True, '\n', 'green')
		return True

	def submit(self, configData):
		try:
			del configData["kbags"]
		except KeyError:
			LOGGING.PRINT("keybags are already stripped, skipping...")
		# check for missing firmware keys
		availableImages = list(configData["images"].keys())
		for imageName in availableImages:
			if len(configData["images"][imageName]) <= 0:
				LOGGING.PRINT("Key for "+imageName+" is missing, removing it from the submission")
				del configData["images"][imageName]
		headers = {
			'User-Agent': 'grandmaster/'+GM_VERSION_STRING,
			'x-api-key':self.FOREMAN_TOKEN
		}
		r = requests.post("https://"+self.FOREMAN_HOST+":"+str(self.FOREMAN_PORT)+"/api/submit/keys", json=configData, headers=headers)
		jsonResponse = r.json()
		if jsonResponse['result'] is False:
			LOGGING.PRINT("Foreman rejected the config. "+str(jsonResponse['error']), True, '\n', 'light_red')
			return False
		LOGGING.PRINT("Foreman accepted the config", True, '\n', 'green')
		return True
	