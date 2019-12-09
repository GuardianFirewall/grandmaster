#!/usr/bin/env python3
import os, subprocess, sys, pathlib, time
from multiprocessing import Process, Queue
from pathlib import Path

TARGET_BUILD = []
TARGET_MODEL = ''
TARGET_OUTPUT_PATH = None

def printSeperator(char, size):
	current = 0
	while current <= size:
		print(char, end='')
		current += 1
	print('\n', end='')

def massAutomate():
	AUTOMATE_RETS = []
	buildArrayLen = len(TARGET_BUILD)
	buildCount = 1
	for build in TARGET_BUILD:
		print("-------------------------["+str(buildCount)+'/'+str(buildArrayLen)+"]-------------------------")
		BUILD_OUTPUT_PATH = str(TARGET_OUTPUT_PATH / TARGET_MODEL / build)
		automatecmd = ['python3', 'grandmaster.py', '--automate', BUILD_OUTPUT_PATH, '--noprompt', '--autosubmit'] 
		p = subprocess.Popen(automatecmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		for line in p.stdout:
			print('(automate:'+build+') ~ '+line.decode('utf-8').strip())
		p.wait()
		AUTOMATE_RETS.append(p.returncode)
		buildCount += 1
	for ret in AUTOMATE_RETS:
		if ret != 0:
			return False
	return True

def generateThread(threadq, outputPath, targetIdentifier, buildNumber):
	generatecmd = ['python3', 'grandmaster.py', '--generate', outputPath, '--model', targetIdentifier, '--build', buildNumber, '--overwrite'] 
	p = subprocess.Popen(generatecmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	for line in p.stdout:
		print(line.decode('utf-8').strip())
	p.wait()
	threadq.put(p.returncode)

def massGenerate():
	GEN_THREADS = []
	THREAD_RETS = []
	queue = Queue()
	for build in TARGET_BUILD:
		BUILD_OUTPUT_PATH = str(TARGET_OUTPUT_PATH / TARGET_MODEL / build)
		p = Process(target=generateThread, args=(queue, BUILD_OUTPUT_PATH, TARGET_MODEL, build))
		p.start()
		GEN_THREADS.append(p)
	for thread in GEN_THREADS:
		THREAD_RETS.append(queue.get())
		thread.join()
	allReturnedOkay = True
	for ret in THREAD_RETS:
		if ret != 0:
			allReturnedOkay = False
	return allReturnedOkay
		
def main():
	global TARGET_MODEL
	global TARGET_BUILD
	global TARGET_OUTPUT_PATH
	if sys.argv[1] is None:
		print("missing model identifier")
	if sys.argv[2] is None:
		print("missing builds")
	if sys.argv[3] is None:
		print("missing output path")
	TARGET_MODEL = sys.argv[1]
	TARGET_OUTPUT_PATH = Path(sys.argv[3])
	# break down each build, comma seperated
	builds = sys.argv[2].split(',')
	for build in builds:
		TARGET_BUILD.append(build)
	start_time = time.time()
	if massGenerate():
		print("generated configs!")
		if massAutomate() is False:
			print("something went wrong during automation!")
	else:
		print("something went wrong during generation!")
	print("all OK!")
	print("--- %s seconds ---" % (time.time() - start_time))
	exit(0)

if __name__== "__main__":
	try:
		main()
	except KeyboardInterrupt:
		exit(0)