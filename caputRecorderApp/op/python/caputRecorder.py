# This should be executed as "python caputRecorder.py", so it doesn't make a
# .pyc file, because this directory might be in a read-only file system

import sys
import threading
import thread
import epics
import time
import copy
import Queue
import keyword
import string
import shutil
import os

# trial support for global variables
def _getGlobals(prefix, debug=False):
	g = {}
	numGlobals = epics.caget(prefix+"caputRecorderNumGlobals")
	g["filepath"] = epics.caget(prefix+"caputRecorderGbl_filepath", as_string=True)
	g["filename"] = epics.caget(prefix+"caputRecorderGbl_filename", as_string=True)
	for i in range(1, numGlobals+1):
		name = epics.caget(prefix+"caputRecorderGbl_%d.DESC" % i, as_string=True)
		if len(name)>0:
			g[name] = epics.caget(prefix+"caputRecorderGbl_%d" % i, as_string=True)
	return g

HAVE_FILE_SELECTOR = False
defaultPath = ""
defaultFile = ""
try:
	import wx
	HAVE_FILE_SELECTOR = True
except:
	pass

#import macros
macros = None

macroFileName = "macros.py"

# convert commas to spaces
commaToSpaceTable = string.maketrans(",", " ")
# legal characters for function names
legalChars = string.letters + string.digits + "_"

wake = threading.Event()
debug = 0
connected = True

prefix = "xxx:"
menuFields=["ZRST","ONST","TWST","THST","FRST","FVST","SXST","SVST","EIST","NIST","TEST","ELST","TVST","TTST","FTST","FFST"]

# commands
doStartMacro = 0
doStopMacro = 0
doReloadMacros = 0
doexecuteMacro = 0
doSelectMacro = 0
doAbortMacro = 0
doEditMacros = 0
executingMacro = 0
exitProgram = 0
doSelectFile = 0

# if execute while recording
executeLevel = 0
postponeStop = 0

from inspect import getmembers, isfunction, getargspec
maxArgs = 20

maxMacroMenus = 6

# all macro functions
_macroFunctionNames = []
_macroFunctions = []
# all macro functions whose names don't begin with "_"
macroFunctionNames = []
macroFunctions = []

# for sending messages to writer()
MSG_COMMAND = 0
MSG_COMMENT = 1
MSG_DELAY = 2
MSG_DO = 3


allowedUsers = []
allowedHosts = []
forbiddenUsers = []
forbiddenHosts = []

commandMonitorList = []

timeOfLastPut = None
recordTiming = 0
waitCompletion = 1
ifMacroExists = "Fail"
recordingActive = False

########################################################################
def deleteFunction(fileName, functionName):
	deletedLines = []
	retainedLines = []
	macroFile = open(fileName,"r")
	lines = macroFile.readlines()
	deleting = 0
	for line in lines:
		if deleting:
			if line.find("def")==0:
				deleting = 0
		else:
			if line.find("def " + functionName)==0:
				deleting = 1
		
		if deleting:
			deletedLines.append(line)
		else:
			retainedLines.append(line)
	
	macroFile.close()

	macroFile = open(fileName,"w")
	macroFile.writelines(retainedLines)
	macroFile.close()
	return deletedLines

########################################################################
def prefixesMonFunc(pvname, value, char_value, **kwd):
	makeCommandMonitorList(char_value)

def makeCommandMonitorList(prefixStrings):
	global prefix, commandMonitorList
	pstring = prefixStrings.translate(commaToSpaceTable)
	userPrefixes = pstring.split(" ")
	if debug: print "userPrefixes=", userPrefixes
	if userPrefixes and userPrefixes[0]:
		commandMonitorList = []
		for p in userPrefixes:
			if p: commandMonitorList.append(p+"caputRecorderCommand")
	if debug: print "makeCommandMonitorList: commandMonitorList=", commandMonitorList

########################################################################
## Respond to monitors from command and comment PVs
## All we're going to do is send (pvname,value) information to the message queue

def calcAllowed(char_value):
	global debug
	allowed = []
	forbidden = []
	if char_value != "":
		items = char_value.split(" ")
		for item in items:
			if item[0] == '-':
				forbidden.append(item[1:])
			else:
				allowed.append(item)
	return (allowed, forbidden)

def usersMonFunc(pvname, value, char_value, **kwd):
	global debug, allowedUsers, forbiddenUsers
	if debug: print "usersMonFunc: char_value='%s'" % char_value
	(allowedUsers, forbiddenUsers) = calcAllowed(char_value)
	if (debug):
		print "allowedUsers='%s', forbiddenUsers='%s'\n" % (allowedUsers, forbiddenUsers)

def hostsMonFunc(pvname, value, char_value, **kwd):
	global debug, allowedHosts, forbiddenHosts
	if debug: print "hostsMonFunc: char_value='%s'" % char_value
	(allowedHosts, forbiddenHosts) = calcAllowed(char_value)
	if (debug):
		print "allowedHosts='%s', forbiddenHosts='%s'\n" % (allowedHosts, forbiddenHosts)

########################################################################
## Respond to monitors from command, comment, and delay PVs
## All we're going to do is send (pvname,value) information to the message queue

def commandMonFunc(pvname, value, char_value, **kwd):
	global debug, macroFile, prefix, msgQueue, recordingActive
	if debug: print "commandMonFunc: char_value='%s'" % char_value
	if recordingActive:
		msgQueue.put((MSG_COMMAND, char_value))
	else:
		if debug: print "commandMonFunc: char_value='%s' while recordingActive==False" % char_value

def commentMonFunc(pvname, value, char_value, **kwd):
	global debug, macroFile, msgQueue
	msgQueue.put((MSG_COMMENT, char_value))

def delayMonFunc(pvname, value, char_value, **kwd):
	global debug, macroFile, msgQueue
	if value>0:
		msgQueue.put((MSG_DELAY, char_value))

## execute selected macro
def executeMacroMonFunc(pvname, value, char_value, **kwd):
	global debug, macroFile, msgQueue
	if debug: print "executeMacroMonFunc: char_value=%s" % char_value
	msgQueue.put((MSG_DO, char_value))

def hostMatch(thisHost, hostList):
	if len(hostList) == 0:
		return False
	for host in hostList:
		if host.startswith(thisHost):
			return True
		if thisHost.startswith(host):
			return True
	return False

############################################################################
## writer thread
# read from the message queue, and write to the macros.py file, which startMacro()
# opened for us as the file handle "MacroFile"

def userHostAllowed(user, host):
	global allowedHosts, forbiddenHosts, allowedUsers, forbiddenUsers

	if debug:
		print "userHostAllowed: user=%s, host=%s" % (user, host)
		print "userHostAllowed: allowedHosts=%s" % allowedHosts
		print "userHostAllowed: allowedUsers=%s" % allowedUsers

	if allowedHosts and not hostMatch(host, allowedHosts):
		return False
	if forbiddenHosts and hostMatch(host, forbiddenHosts):
		return False

	if allowedUsers and user not in allowedUsers:
		return False
	if forbiddenUsers and user in forbiddenUsers:
		return False
	return True

def asString(argValue):
	""" if arg type is string, make sure argValue contains quotes """

	if argValue[0] == "'":
		if argValue[-1] == "'":
			return(argValue)
		elif argValue[-1] == '"':
			argValue = argValue[0:-1] + "'"
			return(argValue)
		else:
			return(argValue + "'")

	elif argValue[0] == '"':
		if argValue[-1] == '"':
			return(argValue)
		elif argValue[-1] == "'":
			argValue = argValue[0:-1] + '"'
			return(argValue)
		else:
			return(argValue + '"')

	else:
		argValue = "'" + argValue
		if argValue[-1] == "'":
			return(argValue)
		elif argValue[-1] == '"':
			argValue = argValue[0:-1] + "'"
			return(argValue)
		else:
			return(argValue + "'")

def writer():
	global debug, macroFile, prefix, msgQueue, doexecuteMacro, executeLevel, postponeStop
	global doStartMacro, doStopMacro, connected, recordTiming, timeOfLastPut, waitCompletion, recordingActive
	global macroFunctionNames, macroFunctions
	
	epics.ca.use_initial_context()

	while(1):
		(msg, char_value) = msgQueue.get()
		if debug: print "writer: type=%d, char_value='%s'" % (msg, char_value)
		if executeLevel and (msg != MSG_DO):
			continue
		if not connected:
			continue
		if msg == MSG_COMMAND:
			now = time.time()
			if timeOfLastPut:
				if debug: print "writer: recordTiming = %d" % recordTiming
				dt = now - timeOfLastPut
				if recordTiming and dt>0:
					macroFile.write("\ttime.sleep(%.3f)\n" % dt)
			timeOfLastPut = now

			try:
				(pvname,value,user_host) = char_value.split(',')
				recordablePV = 1
			except:
				try:
					(pvname,value) = char_value.split(',')
					print "caputRecorder: could not extract pvname,value,user@host"
					macroFile.write("\t# unrecorded write to %s\n" % pvname)
					macroFile.flush()
				except:
					print "caputRecorder: could not extract pvname"
					macroFile.write("\t# unrecorded write to unknown PV\n")
					macroFile.flush()
				recordablePV = 0

			# Ignore caputs to caputRecorder PVs
			if char_value.find(prefix+"caputRecorder") >= 0:
				recordablePV = 0

			if recordablePV:
				# check user and host
				allowed = True
				if user_host:
					(user, host) = user_host.split("@")
					if debug: print "writer: user=%s, host=%s" % (user, host)
					allowed = userHostAllowed(user, host)
				if allowed:
					# If DBF_UCHAR (TPRO, DISP, PROC, UDF, syn.AQR, mbbiDirect.Bn), write int value to avoid bug in PyEpics 3.4.2
					# None but PROC are at all likely
					dbf_uchar_fields = (".PROC", ".TPRO", ".DISP", ".UDF")
					if waitCompletion:
						putWaitSeconds = epics.caget(prefix+"caputRecorderWaitCBSec", use_monitor=True)
						if pvname.endswith(dbf_uchar_fields):
							macroFile.write("\tepics.caput(\"%s\",%d, wait=True, timeout=%.1f)\n" % (pvname,int(value),putWaitSeconds))
						else:
							macroFile.write("\tepics.caput(\"%s\",\"%s\", wait=True, timeout=%.1f)\n" % (pvname,value,putWaitSeconds))
					else:
						if pvname.endswith(dbf_uchar_fields):
							macroFile.write("\tepics.caput(\"%s\",%d)\n" % (pvname,int(value)))
						else:
							macroFile.write("\tepics.caput(\"%s\",\"%s\")\n" % (pvname,value))
					macroFile.flush()
			msgQueue.task_done()
		elif msg == MSG_COMMENT:
			macroFile.write("\t# %s\n" % char_value)
			macroFile.flush()
		elif msg == MSG_DELAY:
			delayTime = epics.caget(prefix+"caputRecorderDelaySec")
			macroFile.write("\ttime.sleep(%.3f)\n" % delayTime)
			macroFile.flush()
			epics.caput(prefix+"caputRecorderAddDelayCmd", 0)
		elif msg == MSG_DO:
			if debug: print "writer:MSG_DO, char_value='%s'" % char_value
			try:
				busy = epics.caget(prefix+"caputRecorderMacroRecording")
			except:
				return
			if char_value == "Do":
				if (busy):
					# We're recording a macro.  While recording, commands to execute a macro
					# become calls to that macro's python function

					# if ExecuteLoops > 1, write a loop
					loops = epics.caget(prefix+"caputRecorderExecuteLoops")
					loops = max(1, loops)
					if loops>1:
						indent = "\t\t"
						cmd = "\tfor i in range(%s):\n" % loops
						macroFile.write(cmd)
					else:
						indent = "\t"

					# add call to selected function to macro file
					funcName = epics.caget(prefix+"caputRecorderMacro")
					
					# get argument types from default_vals
					try:
						func = macroFunctions[macroFunctionNames.index(funcName)]
						(args, vdummy, kdummy, default_vals) = getargspec(func)
					except:
						func = None
						default_vals = None

					cmd = indent + funcName+"("
					for j in range(1,maxArgs+1):
						k = j-1
						argName = epics.caget(prefix+("caputRecorderArg%dName" % j))
						argValue = epics.caget(prefix+("caputRecorderArg%dValue" % j))
						if argName:
							if j>1:
								cmd = cmd + ","

							# if arg type is string, make sure argValue contains quotes
							if default_vals and k < len(default_vals) and type(default_vals[k]) == type(""):
								argValue = asString(argValue)

							cmd = cmd + argName + "=" + argValue
						else:
							break
					cmd = cmd + ")\n"
					macroFile.write(cmd)
					macroFile.flush()
					# execute macro, but stop recording while it executes
					executeLevel += 1
					if executeLevel:
						epics.caput(prefix+"caputRecorderUserMessage", "recording suppressed during execution")
					doexecuteMacro = 1
					wake.set()
				else:
					# wake up start() thread, and tell it to execute
					doexecuteMacro = 1
					wake.set()
			else:
				if executeLevel > 0:
					executeLevel -= 1
					if executeLevel==0:
						epics.caput(prefix+"caputRecorderUserMessage", "")
						if postponeStop:
							if debug: print "writer: executing postponed Stop"
							doStopMacro = 1
							postponeStop = 0
							wake.set()


########################################################################
## Respond to monitors from StopStart PV

def stopStartMonFunc(pvname, value, char_value, **kwd):
	global debug, doStartMacro, doStopMacro, executingMacro, executeLevel, postponeStop
	global connected

	if debug: print("stopStartMonFunc: value = ", value, "char_value = ", char_value)
	if not connected:
		return

	if executeLevel > 0:
		# ignore or postpone action on switch until executeLevel==0
		if value:
			epics.caput(prefix+"caputRecorderMacroStopStart", 0)
			epics.caput(prefix+"caputRecorderUserMessage", "Can't start recording while executing")
		else:
			postponeStop = 1
	elif executingMacro:
		if value:
			epics.caput(prefix+"caputRecorderMacroStopStart", 0)
			epics.caput(prefix+"caputRecorderUserMessage", "Can't start recording while executing")
	else:
		if value:
			doStartMacro = 1
		else:
			doStopMacro = 1
		wake.set()

def startMacro():
	global debug, macroFile, prefix, macroFunctionNames
	global commandMonitorList, connected, timeOfLastPut, ifMacroExists
	global macroFileName, recordingActive

	if debug: print("startMacro: entry\n")
	if not connected:
		return

	busy = epics.caget(prefix+"caputRecorderMacroRecording")
	if (busy):
		epics.caput(prefix+"caputRecorderUserMessage", "a macro is already being recorded")
		return
	tryMacroName = epics.caget(prefix+"caputRecorderMacroName")
	
	# check macroName for problems
	if (tryMacroName==""):
		epics.caput(prefix+"caputRecorderUserMessage", "*** macro name is empty")
		epics.caput(prefix+"caputRecorderMacroStopStart", 0)
		return
	# function name must start with a letter
	macroName = ""
	if tryMacroName[0] not in string.letters:
		macroName = "a"
	# function name must consist of letters, digits, and underscores
	for c in tryMacroName:
		if c in legalChars:
			macroName += c
		else:
			macroName += "_"
	# function name must be 25 characters or less (mbboRecord string length)
	if len(macroName) > 25: macroName = macroName[:25]
	if (macroName in keyword.kwlist):
		epics.caput(prefix+"caputRecorderUserMessage", "*** macro name is a python keyword")
		epics.caput(prefix+"caputRecorderMacroStopStart", 0)
		return
	# See of function name is already defined
	appending = False
	if debug: print "startMacro: ifMacroExists=", ifMacroExists
	if macroName in macroFunctionNames:
		if debug: print"ifMacroExists=%s" % ifMacroExists
		if ifMacroExists=="Fail":
			epics.caput(prefix+"caputRecorderUserMessage", "*** macro name is already in use")
			epics.caput(prefix+"caputRecorderMacroStopStart", 0)
			return
		if ifMacroExists=="Replace":
			timeString = time.strftime("_%y%m%d-%H%M%S")
			shutil.copy(macroFileName,macroFileName+timeString)
		dl = deleteFunction(macroFileName, macroName)
		if ifMacroExists=="Append":
			macroFile = open(macroFileName,"a")
			macroFile.writelines(dl)
			macroFile.close()
			appending = True
			epics.caput(prefix+"caputRecorderUserMessage", "appending to existing macro")
		else:
			# replace
			
			epics.caput(prefix+"caputRecorderUserMessage", "replacing existing macro")

	epics.caput(prefix+"caputRecorderMacroRecording", 1)
	epics.caput(prefix+"caputRecorderUserMessage", "Recording")
	macroFile = open(macroFileName,"a")
	if appending == False:
		macroFile.write("def %s():\n" % macroName)
	else:
		macroFile.write("\t# appended to existing macro...\n")

	# It's not legal to have a python function with no commands in it.
	# Defend against user stopping recording without doing any caputs
	# by writing dummy command to set the record date.
	now = time.strftime("%c")
	macroFile.write("\trecordDate = \"%s\"\n" % now)
	macroFile.flush()
	timeOfLastPut = None
	epics.camonitor(prefix+"caputRecorderComment",callback=commentMonFunc)
	epics.camonitor(prefix+"caputRecorderAddDelayCmd",callback=delayMonFunc)

	# If this is the first time we're connecting to a commandMonitorList pv,
	# we might get an initial value callback.  We want to ignore that, because the
	# user didn't do it.  So, monitor and unmonitor all the commandMonitorList pvs,
	# to flush out any initial value callbacks, then monitor the pvs and set
	# recordingActive==True.
	for pv in commandMonitorList:
		try:
			epics.camonitor(pv,callback=commandMonFunc)
		except:
			pass

	for pv in commandMonitorList:
		try:
			epics.camonitor_clear(pv)
		except:
			pass

	for pv in commandMonitorList:
		try:
			epics.camonitor(pv,callback=commandMonFunc)
		except:
			print "Can't monitor '%s'" % pv
	recordingActive = True

def endMacro():
	global debug, macroFile, prefix, doReloadMacros
	global commandMonitorList, connected, recordingActive

	if debug: print("endMacro: entry\n")
	recordingActive = False
	if not connected:
		return

	try:
		recording = epics.caget(prefix+"caputRecorderMacroRecording")
	except:
		return

	if (not recording):
		return

	epics.camonitor_clear(prefix+"caputRecorderComment")
	epics.camonitor_clear(prefix+"caputRecorderAddDelayCmd")
	for pv in commandMonitorList:
		epics.camonitor_clear(pv)

	epics.caput(prefix+"caputRecorderMacroRecording", 0)
	epics.caput(prefix+"caputRecorderUserMessage", "Done")
	if (not macroFile or not isinstance(macroFile, file)):
		print("no macro is being recorded\n")
		return
	macroFile.write("\n")
	macroFile.close()
	macroFile=None
	doReloadMacros = 1
	wake.set()


########################################################################
## Respond to monitors from ReloadMacros PV
## read macros from file, and write names to EPICS PVs

def reloadMacrosMonFunc(pvname, value, char_value, **kwd):
	global debug, doReloadMacros, connected

	if not connected:
		return

	if value:
		doReloadMacros = 1
	wake.set()

def reloadMacros():
	global macros
	global debug, prefix, macroFunctionNames, macroFunctions, menuFields
	global _macroFunctionNames, _macroFunctions, connected

	if debug: print "reloadMacros:entry"
	if not connected:
		if debug: print "reloadMacros:not connected"
		return

	success = 0
	functions = []
	_macroFunctionNames = []
	_macroFunctions = []
	macroFunctionNames = []
	macroFunctions = []

	if debug: print "reloadMacros: dir(macros)=", dir(macros)
	try:
		reload(macros)
		success = 1
	except:
		epics.caput(prefix+"caputRecorderUserMessage", "Macro file contains error(s)")
	if debug: print "reloadMacros: dir(macros)=", dir(macros)

	# erase menu strings
	epics.caput(prefix+"caputRecorderClearMacros", 1, wait=True, timeout=5)

	if success:
		functions = [o for o in getmembers(macros) if isfunction(o[1])]
		if debug: print "reloadMacros:functions=", functions
		(_macroFunctionNames, _macroFunctions) = zip(*functions)
		# don't add functions whose names begin with '_' to function menu
		macroFunctionNames = list(copy.deepcopy(_macroFunctionNames))
		macroFunctions = list(copy.deepcopy(_macroFunctions))
		i = 0
		while i < len(macroFunctionNames):
			if macroFunctionNames[i][0] == '_':
				del macroFunctionNames[i]
				del macroFunctions[i]
			else:
				i += 1
		if debug: print "reloadMacros:macroFunctionNames=", macroFunctionNames
		i = 0
		numItems = [0]*maxMacroMenus
		itemNames = [""]*16*maxMacroMenus
		for (name, func, field) in zip(macroFunctionNames, macroFunctions, menuFields*maxMacroMenus):
			menu = i/len(menuFields) + 1
			epics.caput(prefix + ("caputRecorderMacros%d." % menu) + field, name)
			i += 1
			numItems[menu] += 1
		
		for i in range(maxMacroMenus):
			itemNum = epics.caget(prefix + ("caputRecorderMacros%d" % (i+1)))
			if itemNum > numItems[i]:
				epics.caput(prefix + ("caputRecorderMacros%d" % menu), 0)
		

	selectMacro()
	epics.caput(prefix+"caputRecorderUserMessage", "Macro (re)load succeeded")
	epics.caput(prefix+"caputRecorderNeedRefresh", 1)
	epics.caput(prefix+"caputRecorderReloadMacros", 0)


########################################################################
## Respond to monitors from Macros<n> PVs
## write args for selected macro to EPICS PVs

def selectMacroMonFunc(pvname, value, char_value, **kwd):
	global debug, doSelectMacro, connected

	if not connected:
		return

	doSelectMacro = 1
	wake.set()

def selectMacro():
	global debug, prefix, macroFunctionNames, macroFunctions, maxArgs, menuFields
	global connected

	if not connected:
		return

	# find which function is selected
	funcName = epics.caget(prefix+"caputRecorderMacro")
	try:
		func = macroFunctions[macroFunctionNames.index(funcName)]
	except:
		func = None

	if debug: print macroFunctionNames
	if debug: print "func=", func
	# erase arg names and values
	epics.caput(prefix + "caputRecorderClearArgs", "1")

	# write arg names and values
	if (func):
		(args, v, k, vals) = getargspec(func)
		if vals:
			args_with_vals = args[-len(vals):]
		if len(args) > 0:
			nums = range(1, maxArgs+1)
			for (argname, j) in zip(args, nums):
				epics.caput(prefix+("caputRecorderArg%dName" % j), argname)
				if vals and argname in args_with_vals:
					argvalue = vals[args_with_vals.index(argname)]
					epics.caput(prefix+("caputRecorderArg%dValue" % j), repr(argvalue))

	# clear the busy record that was set to begin this operation
	epics.caput(prefix+"caputRecorderMacrosBusy", 0)

########################################################################
## Execute macro, respond to monitors from AbortMacro PV

## abort executing macro
def abortMacroMonFunc(pvname, value, char_value, **kwd):
	global debug, doAbortMacro, executingMacro, connected

	if not connected:
		return

	if debug: print "abortMacroMonFunc: value=%d\n" % value
	if value:
		doAbortMacro = 1
		if executingMacro:
			thread.interrupt_main()
		wake.set()

def executeMacro():
	global macros
	global debug, prefix, macroFunctionNames, macroFunctions, maxArgs, executingMacro
	global _macroFunctionNames, connected

	if not connected:
		return

	# find which function is selected
	funcName = epics.caget(prefix+"caputRecorderMacro")
	try:
		func = macroFunctions[macroFunctionNames.index(funcName)]
		(args, vdummy, kdummy, default_vals) = getargspec(func)
	except:
		executingMacro = 0
		return

	loops = epics.caget(prefix+"caputRecorderExecuteLoops")
	loops = max(1, loops)
	if loops>1:
		commandString = "for i in range(%s): " % loops
	else:
		commandString = ""
	commandString += "macros.%s(" % funcName
	numArgs = len(getargspec(func)[0])
	for j in range(min(maxArgs, numArgs)):
		if j>0:
			commandString += ","
		commandString += getargspec(func)[0][j]+"="
		argValue = epics.caget(prefix+("caputRecorderArg%dValue" % (j+1)), as_string=True)

		# if arg type is string, make sure argValue contains quotes
		if default_vals and j < len(default_vals) and type(default_vals[j]) == type(""):
			argValue = asString(argValue)

		commandString += argValue
	commandString += ")"
	if debug: print "commandString='%s'" % commandString
	try:
		executingMacro = 1
		exec(commandString)
	except KeyboardInterrupt:
		if debug: print "executeMacro:exception: KeyboardInterrupt"
		if "_abort" in _macroFunctionNames:
			eval("macros._abort(prefix)")
	except:
		if doAbortMacro:
			if debug: print "executeMacro:exception: KeyboardInterrupt"
			if "_abort" in _macroFunctionNames:
				eval("macros._abort(prefix)")
		else:
			print "error executing '%s'\n" % commandString
	executingMacro = 0


############################################################################
def startStringMonFunc(pvname, value, char_value, **kwd):
	global debug, startString, wake, exitProgram, connected, executingMacro
	if not char_value:
		epics.caput(prefix+"caputRecorderStartTime", startString)
	else:
		if startString != char_value:
			# Another instance of the program wrote a new start-time string.
			# We don't ever want two copies of the program that use the same control PVs
			# running simultaneously.
			if executingMacro:
				thread.interrupt_main()
			exitProgram = 1
			wake.set()

def onConnectionChange(pvname=None, conn= None, **kws):
	global debug, connected, doReloadMacros, wake
	if debug: print 'onConnectionChange: PV connection status changed: %s %s\n' % (pvname,  repr(conn))
	if conn:
		# wait for initial monitors to come in before allowing writer() to act on them
		if connected == False:
			#time.sleep(1)
			connected = True
			if debug: print 'onConnectionChange: doReloadMacros=1\n'
			doReloadMacros = 1
			wake.set()
	else:
		connected = False
		

def heartbeat():
	global debug, prefix, wake, exitProgram, startString

	epics.ca.use_initial_context()
	
	maxDisconnectTime = 10
	hb = epics.PV(prefix+"caputRecorderHeartbeat", connection_callback=onConnectionChange)
	disconnectTime = 0
	waitTime = 2
	while True:
		if epics.ca.isConnected(hb.chid):
			disconnectTime = 0
			hb.put(1)
		else:
			disconnectTime += waitTime
			if disconnectTime > maxDisconnectTime:
				if debug: print "caputRecorder: exiting"
				exitProgram = 1
				wake.set()

		# While we're here, make sure we haven't missed any monitors on caputRecorderStartTime
		ts = epics.caget(prefix+"caputRecorderStartTime")
		if ts and startString != ts:
			# Another instance of the program wrote a new start-time string.
			# We don't ever want two copies of the program that use the same control PVs
			# running simultaneously.
			if executingMacro:
				thread.interrupt_main()
			exitProgram = 1
			wake.set()
		
		time.sleep(waitTime)

def start():
	global debug, prefix, wake, doStartMacro, doStopMacro, doReloadMacros, doexecuteMacro
	global doSelectMacro, doAbortMacro, executingMacro, msgQueue
	global allowedUsers, forbiddenUsers, allowedHosts, forbiddenHosts
	global commandMonitorList, exitProgram, doEditMacros, macroFileName
	global doSelectFile, defaultPath, defaultFile

	wake.clear()

	# this monitor will kill us if a new copy of the program is executed
	epics.camonitor(prefix+"caputRecorderStartTime",callback=startStringMonFunc)

	# Build lists of the PVs we'll monitor while recording
	userPrefixes = epics.caget(prefix+"caputRecorderPrefixes", as_string=True)
	if userPrefixes:
		makeCommandMonitorList(userPrefixes)

	epics.camonitor(prefix+"caputRecorderMacroStopStart",callback=stopStartMonFunc)
	epics.camonitor(prefix+"caputRecorderReloadMacros",callback=reloadMacrosMonFunc)
	epics.camonitor(prefix+"caputRecorderMacro",callback=selectMacroMonFunc)
	epics.camonitor(prefix+"caputRecorderExecuteMacro",callback=executeMacroMonFunc)
	epics.camonitor(prefix+"caputRecorderAbortMacro",callback=abortMacroMonFunc)
	epics.camonitor(prefix+"caputRecorderUsers",callback=usersMonFunc)
	epics.camonitor(prefix+"caputRecorderHosts",callback=hostsMonFunc)
	epics.camonitor(prefix+"caputRecorderPrefixes",callback=prefixesMonFunc)
	reloadMacros()
	# We probably won't get a monitor from Users or Hosts, so do cagets
	users = epics.caget(prefix+"caputRecorderUsers", as_string=True)
	(allowedUsers, forbiddenUsers) = calcAllowed(users)
	if (debug):
		print "allowedUsers='%s', forbiddenUsers='%s'" % (allowedUsers, forbiddenUsers)
	hosts = epics.caget(prefix+"caputRecorderHosts", as_string=True)
	(allowedHosts, forbiddenHosts) = calcAllowed(hosts)
	if (debug):
		print "allowedHosts='%s', forbiddenHosts='%s'" % (allowedHosts, forbiddenHosts)

	# heartbeat
	heartbeatThread = threading.Thread(target=heartbeat)
	heartbeatThread.daemon = True
	heartbeatThread.start()

	# message and queue
	msgQueue = Queue.Queue(maxsize=100)
	writeThread = threading.Thread(target=writer)
	writeThread.daemon = True
	writeThread.start()

	while (1):
		try:
			wake.wait(1)
		except:
			pass

		if wake.is_set():
			if debug: print "start: wake.is_set()"
			wake.clear()
		if doStartMacro:
			if debug: print "start: doStartMacro=True"
			doStartMacro=0
			startMacro()
		if doStopMacro:
			if debug: print "start: doStopMacro=True"
			doStopMacro = 0
			endMacro()
		if doReloadMacros:
			if debug: print "start: doReloadMacros=True"
			doReloadMacros = 0
			reloadMacros()
		if doSelectMacro:
			if debug: print "start: doSelectMacro=True"
			doSelectMacro = 0
			selectMacro()
		if doexecuteMacro:
			if debug: print "start: doexecuteMacro=True"
			executeMacro()
			doexecuteMacro = 0
			epics.caput(prefix+"caputRecorderExecuteMacro", 0)
		if doAbortMacro:
			doAbortMacro = 0
			epics.caput(prefix+"caputRecorderAbortMacro", 0)
		if doEditMacros:
			doEditMacros = 0
			epics.caput(prefix+"caputRecorderEditMacros", 0)
			editor = os.environ['EDITOR']
			os.system(editor + " " + macroFileName + "&")
		if doSelectFile:
			doSelectFile = 0
			epics.caput(prefix+"caputRecorderSelectFile", 0)
			if HAVE_FILE_SELECTOR:
				app = wx.App()
				path = wx.FileSelector("Choose a file", default_path=defaultPath,
					default_filename=defaultFile, flags=wx.OPEN)
				(defaultPath, defaultFile) = os.path.split(path)
				app.Destroy()
				if debug: print "path='%s', defaultPath='%s', defaultFile='%s'" % (path, defaultPath, defaultFile)
				epics.caput(prefix+"caputRecorderGbl_filepath", defaultPath)
				epics.caput(prefix+"caputRecorderGbl_filename", defaultFile)
		if exitProgram:
			sys.exit()
	stop()


def stop():
	global debug, prefix

	epics.camonitor_clear(prefix+"caputRecorderMacroStopStart")
	epics.camonitor_clear(prefix+"caputRecorderReloadMacros")
	epics.camonitor_clear(prefix+"caputRecorderMacro")
	epics.camonitor_clear(prefix+"caputRecorderExecuteMacro")
	epics.camonitor_clear(prefix+"caputRecorderAbortMacro")
	epics.camonitor_clear(prefix+"caputRecorderUsers")
	epics.camonitor_clear(prefix+"caputRecorderHosts")
	epics.camonitor_clear(prefix+"caputRecorderPrefixes")
	epics.camonitor_clear(prefix+"caputRecorderAddDelayCmd")
	epics.camonitor_clear(prefix+"caputRecorderComment")

	# clear all busy records, and the bo record caputRecorderEditMacros
	epics.caput(prefix+"caputRecorderMacroStopStart", 0)
	epics.caput(prefix+"caputRecorderMacroRecording", 0)
	epics.caput(prefix+"caputRecorderExecuteMacro", 0)
	epics.caput(prefix+"caputRecorderEditMacros", 0)
	epics.caput(prefix+"caputRecorderAbortMacro", 0)
	epics.caput(prefix+"caputRecorderAddDelayCmd", 0)
	epics.caput(prefix+"caputRecorderSelectFile", 0)


def debugMonFunc(pvname, value, char_value, **kwd):
	global debug
	debug = value

def recordTimingMonFunc(pvname, value, char_value, **kwd):
	global debug, recordTiming
	recordTiming = value

def waitCompletionMonFunc(pvname, value, char_value, **kwd):
	global debug, waitCompletion
	waitCompletion = value

def ifMacroExistsMonFunc(pvname, value, char_value, **kwd):
	global debug, ifMacroExists
	ifMacroExists = char_value
	
def editMacrosMonFunc(pvname, value, char_value, **kwd):
	global debug, wake, macroFileName, doEditMacros
	if debug: print "editMacrosMonFunc: entry"
	if value:
		doEditMacros = value
		wake.set()

def selectFileMonFunc(pvname, value, char_value, **kwd):
	global debug, wake, doSelectFile
	if debug: print "selectFileMonFunc: entry"
	if value:
		doSelectFile = value
		wake.set()

usage = """
usage:   python caputRecorder.py prefix [other_prefixes] [macrofile]
example: python caputRecorder.py 1bmb: 1bma: 1bmc: macros_1bmb.py
"""

def go(argv=[]):
	global debug, prefix, commandMonitorList, startString, recordTiming, waitCompletion, ifMacroExists
	global macroFileName, macros

	if len(argv) > 0:
		prefix = argv[0]
		commandMonitorList = [prefix+"caputRecorderCommand"]
	else:
		print usage
		return

	if len(argv) > 1:
		for arg in argv[1:]:
			if arg.endswith(".py"):
				macroFileName = arg
			else:
				commandMonitorList.append(arg+"caputRecorderCommand")
	if debug: print "initial commandMonitorList", commandMonitorList

	# see if prefix+"caputRecorderCommand" exists
	#default_commandPV = epics.PV(prefix+"caputRecorderCommand", timeout=2)
	
	# imort the macros module
	(macroModuleName, ext) = os.path.splitext(os.path.basename(macroFileName))
	macros = __import__(macroModuleName)
	#print "macroFileName='%s'" % macroFileName
	#print "dir(macros)=", dir(macros)

	debug = epics.caget(prefix+"caputRecorderDebug")
	epics.camonitor(prefix+"caputRecorderDebug",callback=debugMonFunc)

	recordTiming = epics.caget(prefix+"caputRecorderRecordTiming")
	epics.camonitor(prefix+"caputRecorderRecordTiming",callback=recordTimingMonFunc)

	waitCompletion = epics.caget(prefix+"caputRecorderWaitCompletion")
	epics.camonitor(prefix+"caputRecorderWaitCompletion",callback=waitCompletionMonFunc)

	ifMacroExists = epics.caget(prefix+"caputRecorderIfMacroExists", as_string=True)
	epics.camonitor(prefix+"caputRecorderIfMacroExists",callback=ifMacroExistsMonFunc)

	epics.camonitor(prefix+"caputRecorderEditMacros",callback=editMacrosMonFunc)
	if HAVE_FILE_SELECTOR:
		epics.camonitor(prefix+"caputRecorderSelectFile",callback=selectFileMonFunc)

	# This is part of our mechanism to exit when a new version of caputRecorder is launched
	# Defend against user hammering on the "(re)start caputRecorder" button, launching
	# multiple copies of caputRecorder that will have the same time string, by appending
	# a string of random hex digits.
	startString = time.strftime("%c_") + os.urandom(3).encode('hex')
	epics.caput(prefix+"caputRecorderStartTime", startString)
	stop()
	start()
	stop()


if __name__ == "__main__":

	go(sys.argv[1:])

	
