# image4 related methods
import re, os, hexdump, sys, asn1, binascii
from distutils.spawn import find_executable
from asn1 import *
#from asn1 import *
from helpers import *

LOGGING = Logging.getInstance()

'''
SEQUENCE (5 elem)
  IA5String IM4P
  IA5String ibot
  IA5String iBoot-5540.0.129
  OCTET STRING (466816 byte) ENCRYPTED DATA
  OCTET STRING (1 elem) KEYBAGS
    SEQUENCE (2 elem)
      SEQUENCE (3 elem)
        INTEGER 1
        OCTET STRING (16 byte) 493D1322792F9688C135567EE1C30E38
        OCTET STRING (32 byte) 8EF162B030D229A986F8FDED4B0A45D2CB1971400FB93CF6B884BF223B11944D
      SEQUENCE (3 elem)
        INTEGER 2
        OCTET STRING (16 byte) 91C59490E49912A7E20113A8F6501744
        OCTET STRING (32 byte) 6C10B36B64A333FE042459F48B2143F67B63034EEAC776649F82B662814DE63D
'''
class IM4P_Parser():
	# IM4P asn1 structure 
	_MAGIC = ''
	_TYPE = ''
	_IMAGE_VERSION = ''
	_KBAGS = {}

	# working vars
	IMAGE_FILE_PATH = ''

	def __init__(self, imageFilePath):
		super(IM4P_Parser, self).__init__()
		self._KBAGS = {}
		self.IMAGE_FILE_PATH = imageFilePath

	def value_to_string(self, value):
		if isinstance(value, bytes):
			return '0x' + str(binascii.hexlify(value).upper())
		elif isinstance(value, str):
			return value
		else:
			return repr(value)

	# Eh, tricky, buggy
	def find_keybags(self, input_stream):
		CURRENT_KEYBAG_TYPE = None
		while not input_stream.eof(): # loop until end of file
			tag = input_stream.peek() # peek into asn1 tag
			if tag.typ == asn1.Types.Primitive: # if type is Primitive
				tag, value = input_stream.read()
				valstr = self.value_to_string(value)
				if tag.nr == asn1.Numbers.Integer:
					if value == 1: # check INTEGER, 1 = prod or 2 = dev
						CURRENT_KEYBAG_TYPE = "production"
					elif value == 2:
						CURRENT_KEYBAG_TYPE = "development"
					# initialize key if it doesn't already exist in the dict
					if CURRENT_KEYBAG_TYPE not in self._KBAGS.keys():
						self._KBAGS[CURRENT_KEYBAG_TYPE] = ""
					# iv
					tag, value = input_stream.read() # read one
					valstr = self.value_to_string(value).replace('0xb','').replace('\'','') # value to str and cleanup
					if len(valstr) == 32: # iv len
						self._KBAGS[CURRENT_KEYBAG_TYPE] += valstr # append to keybag
					# key
					tag, value = input_stream.read() # read one
					valstr = self.value_to_string(value).replace('0xb','').replace('\'','') # value to str and cleanup
					if len(valstr) == 64: # key len
						self._KBAGS[CURRENT_KEYBAG_TYPE] += valstr # append to keybag
					#print(self._KBAGS[CURRENT_KEYBAG_TYPE])
				else: # any other prim. type other than Integer			
					if len(valstr) < 0x420: # filter out the image payload 
						if tag.nr == asn1.Numbers.OctetString and len(valstr) == 0xed:
							keybagDecoder = asn1.Decoder()
							keybagDecoder.start(value)
							self.find_keybags(keybagDecoder)
						else:
							if ('IM4P' in valstr):
								self._MAGIC = valstr 
							elif (valstr in ['ibss', 'ibec', 'ibot', 'dtre', 'illb', 'logo', 'rlgo', 'rdsk']):
								self._TYPE = valstr
			elif tag.typ == asn1.Types.Constructed: # if type if Constructed
				input_stream.enter()
				self.find_keybags(input_stream)
				input_stream.leave()
		return self._KBAGS

	def keybags(self):
		return self._KBAGS

	def magic(self):
		return self._MAGIC

	def type(self):
		return self._TYPE

	def parse(self):
		if len(self.IMAGE_FILE_PATH) <= 0:
			return None
		decoder = asn1.Decoder()
		with open(self.IMAGE_FILE_PATH, 'rb') as imageFile:
			decoder.start(imageFile.read())
			self.find_keybags(decoder)

# ----------------------------------------------------------
# check for img4 in the user's PATH
def checkIfimg4libBinaryExists():
	return find_executable("img4") is not None

# loose validation for decrypted image files
def validateImageDecryption(imagePath):
	try:
		with open(imagePath, 'rb') as f:
			fileBuffer = f.read()
			# try to find 'Entering recovery mode, starting command prompt' in the binary
			if re.search(b'\x45\x6e\x74\x65\x72\x69\x6e\x67\x20\x72\x65\x63\x6f\x76\x65\x72\x79\x20\x6d\x6f\x64\x65\x2c\x20\x73\x74\x61\x72\x74\x69\x6e\x67\x20\x63\x6f\x6d\x6d\x61\x6e\x64\x20\x70\x72\x6f\x6d\x70\x74', fileBuffer):
				return True
			elif re.search(b'\x69\x42\x6f\x6f\x74\x49\x6d', fileBuffer): # 'iBootIm'
				return True
			elif re.search(b'\x75\x6E\x69\x71\x75\x65\x2D\x63\x68\x69\x70\x2D\x69\x64', fileBuffer): # 'unique-chip-id' in devicetrees
				return True
			elif re.search(b'\x4C\x4C\x42\x20\x66\x6F\x72', fileBuffer): # 'LLB for'
				return True
			elif re.search(b'\x69\x42\x53\x53\x20\x66\x6F\x72', fileBuffer): # 'iBSS for'
				return True
			elif re.search(b'\x69\x42\x45\x43\x20\x66\x6F\x72', fileBuffer): # 'iBEC for'
				return True
			elif re.search(b'\x69\x42\x6F\x6F\x74\x53\x74\x61\x67\x65\x31\x20\x66\x6F\x72', fileBuffer): # 'iBootStage1 for'
				return True
			elif re.search(b'\x69\x42\x6F\x6F\x74\x53\x74\x61\x67\x65\x32\x20\x66\x6F\x72', fileBuffer): # 'iBootStage2 for'
				return True
			else: 
				return False
	except OSError as e:
		LOGGING.PRINT("couldn't open file for validateImageDecryption()")
	
# dump iBoot header from decrypted file
def dumpiBootHeader(decryptedFilePath):
	try:
		with open(str(decryptedFilePath), 'rb') as decryptedFile:
			decryptedFile.seek(0x200)
			decryptedFileData = decryptedFile.read(0x90)
			hexdump.hexdump(decryptedFileData)
	except OSError as e:
		LOGGING.PRINT("couldn't open file for hexump!")