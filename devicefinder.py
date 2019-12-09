# class assisting in finding / indentifying a device
import urllib3, certifi, json
import usb.core, sys
http = urllib3.PoolManager(cert_reqs='CERT_REQUIRED', ca_certs=certifi.where()) # http(s) pool

class DeviceFinder():
	DEVICE_ARRAY = None
	"""DeviceFinder - methods to help identify a device by Apples, many, device identifiers. Now with USB!"""
	def __init__(self):
		super(DeviceFinder, self).__init__()
	
	def initDeviceArray(self):
		if self.DEVICE_ARRAY is None:
			with open(".firmwares") as firmwaresFile:
				self.DEVICE_ARRAY = []
				firmaresFileData = json.load(firmwaresFile)
				for device in firmaresFileData.keys():
					deviceFirmwareData = firmaresFileData[device]
					del deviceFirmwareData['firmwares']
					deviceFirmwareData['identifier'] = device
					self.DEVICE_ARRAY.append(deviceFirmwareData)
		return self.DEVICE_ARRAY

	def boardConfigForModel(self, modelNumber):
		deviceArray = self.initDeviceArray()
		for deviceDictionary in deviceArray:
			if modelNumber in deviceDictionary['identifier']:
				return deviceDictionary['BoardConfig']
		return ''

	def modelForBoardConfig(self, boardConfig):
		deviceArray = self.initDeviceArray()
		for deviceDictionary in deviceArray:
			if boardConfig in deviceDictionary['BoardConfig']:
				return deviceDictionary['identifier']
		return ''

	def deviceConfigForUSBSerial(self, usbSerialString):
		deviceConfigDictionary = {}
		serialStringSplit = usbSerialString.split(" ")
		for serialStringItem in serialStringSplit:
			serialStringKey = serialStringItem.split(":")[0]
			serialStringValue = serialStringItem.split(":")[1]
			if "SRTG" in serialStringKey:
				serialStringValue = serialStringValue.strip("[").strip("]")
			deviceConfigDictionary[serialStringKey] = serialStringValue
		return deviceConfigDictionary

	def deviceConfigForIdentifier(self, deviceIdentifier): # ex param. iPhone9,3
		deviceArray = self.initDeviceArray()
		for deviceDictionary in deviceArray:
			if deviceIdentifier in deviceDictionary["identifier"]:
				return deviceDictionary
		return None

	def checkIfImageBoardConfigMatchesDevice(self, targetDevice, imageName):
		deviceConfigFromImageName = imageName.split(".")[1]
		targetDeviceConfig = self.deviceConfigForIdentifier(targetDevice)
		if deviceConfigFromImageName in targetDeviceConfig["BoardConfig"]:
			return True
		if deviceConfigFromImageName in targetDeviceConfig["identifier"].split(",")[0].lower():
			return True
		return False

	def printExtraInfoForDeviceConfig(self, deviceConfig):
		deviceArray = self.initDeviceArray()
		for deviceDictionary in deviceArray:
			if (("0x"+deviceConfig["CPID"]) == hex(deviceDictionary["cpid"])):
				if int(deviceConfig["BDID"], 16) == deviceDictionary["bdid"]:
					deviceDescriptionString = "\nPlatform: "
					if len(deviceDictionary["platform"]) > 0:
						deviceDescriptionString += deviceDictionary["platform"]
					else:
						deviceDescriptionString += 'Unknown'
					deviceDescriptionString += '| Identifier: '
					if len(deviceDictionary["identifier"]) > 0:
						deviceDescriptionString += deviceDictionary["identifier"]
					else:
						deviceDescriptionString += 'Unknown'
					deviceDescriptionString += '| BoardConfig: '
					if len(deviceDictionary["BoardConfig"]) > 0:
						deviceDescriptionString += ('Board Config: '+deviceDictionary["BoardConfig"])
					else:
						deviceDescriptionString += 'Unknown'
					print(deviceDescriptionString)

	# search for dfu or recovery mode devices connected to USB
	def findAllUSBDevices(self):
		foundSerial = None
		dev_recovery_mode = usb.core.find(idProduct=0x1281)
		if dev_recovery_mode is not None:
			serialString = usb.util.get_string(dev_recovery_mode, dev_recovery_mode.iSerialNumber)
			foundSerial = serialString
			#self.printExtraInfoForDeviceConfig(self.deviceConfigForUSBSerial(serialString))
		dev_dfu_mode = usb.core.find(idProduct=0x1227)
		if dev_dfu_mode is not None:
			serialString = usb.util.get_string(dev_dfu_mode, dev_dfu_mode.iSerialNumber)
			foundSerial = serialString
			#self.printExtraInfoForDeviceConfig(self.deviceConfigForUSBSerial(serialString))
		return foundSerial
