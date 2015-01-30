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
import macros

# convert commas to spaces
commaToSpaceTable = string.maketrans(",", " ")
# legal characters for function names
legalChars = string.letters + string.digits + "_"

wake = threading.Event()
debug = 0

prefix = "xxx:"
menuFields=["ZRST","ONST","TWST","THST","FRST","FVST","SXST","SVST","EIST","NIST","TEST","ELST","TVST","TTST","FTST","FFST"]

# commands
doStartMacro = 0
doStopMacro = 0
doReloadMacros = 0
doexecuteMacro = 0
doSelectMacro = 0
doAbortMacro = 0
executingMacro = 0

from inspect import getmembers, isfunction, getargspec
maxArgs = 5

maxMacroMenus = 2

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

allowedUsers = []
allowedHosts = []
forbiddenUsers = []
forbiddenHosts = []

commandMonitorList = []

def prefixesMonFunc(pvname, value, char_value, **kwd):
	makeCommandMonitorList(char_value)

def makeCommandMonitorList(prefixStrings):
	global prefix, commandMonitorList
	pstring = prefixStrings.translate(commaToSpaceTable)
	userPrefixes = pstring.split(" ")
	if debug: print "userPrefixes=", userPrefixes
	if userPrefixes:
		commandMonitorList = []
		for p in userPrefixes:
			commandMonitorList.append(p+"caputRecorderCommand")
	if debug: print "commandMonitorList=", commandMonitorList

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
	global debug, macroFile, prefix, msgQueue
	if debug: print "commandMonFunc: char_value='%s'" % char_value
	msgQueue.put((MSG_COMMAND, char_value))

def commentMonFunc(pvname, value, char_value, **kwd):
	global debug, macroFile, msgQueue
	msgQueue.put((MSG_COMMENT, char_value))

def delayMonFunc(pvname, value, char_value, **kwd):
	global debug, macroFile, msgQueue
	if value>0:
		msgQueue.put((MSG_DELAY, char_value))

############################################################################
## writer thread
# read from the message queue, and write to the macros.py file, which startMacro()
# opened for us as the file handle "MacroFile"

def userHostAllowed(user, host):
	global allowedHosts, forbiddenHosts, allowedUsers, forbiddenUsers

	if debug: print "userHostAllowed: user=%s, host=%s" % (user, host)

	if allowedHosts and host not in allowedHosts:
		return False
	if forbiddenHosts and host in forbiddenHosts:
		return False
	if allowedUsers and user not in allowedUsers:
		return False
	if forbiddenUsers and user in forbiddenUsers:
		return False
	return True

def writer():
	global debug, macroFile, prefix, msgQueue

	while(1):
		(msg, char_value) = msgQueue.get()
		if debug: print "writer: type=%d, char_value='%s'" % (msg, char_value)
		if msg == MSG_COMMAND:
			if char_value.find(prefix+"caputRecorder") == -1:
				(pvname,value,user_host) = char_value.split(',')
				# check user and host
				allowed = True
				if user_host:
					(user, host) = user_host.split("@")
					host = host.split(".")[0]
					if debug: print "writer: user=%s, host=%s" % (user, host)
					allowed = userHostAllowed(user, host)
				if allowed:
					putWaitSeconds = epics.caget(prefix+"caputRecorderWaitCBSec", use_monitor=True)
					macroFile.write("\tepics.caput(\"%s\",\"%s\", wait=True, timeout=%.1f)\n" % (pvname,value,putWaitSeconds))
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

########################################################################
## Respond to monitors from StopStart PV

def stopStartMonFunc(pvname, value, char_value, **kwd):
	global debug, doStartMacro, doStopMacro

	#print("stopStartMonFunc: value = ", value, "char_value = ", char_value)
	if value:
		doStartMacro = 1
	else:
		doStopMacro = 1
	wake.set()

def startMacro():
	global debug, macroFile, prefix, macroFunctionNames
	global commandMonitorList
	if debug: print("startMacro: entry\n")
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
	if macroName in macroFunctionNames:
		epics.caput(prefix+"caputRecorderUserMessage", "*** macro name is already in use")
		epics.caput(prefix+"caputRecorderMacroStopStart", 0)
		return
	if (macroName in keyword.kwlist):
		epics.caput(prefix+"caputRecorderUserMessage", "*** macro name is a python keyword")
		epics.caput(prefix+"caputRecorderMacroStopStart", 0)
		return

	epics.caput(prefix+"caputRecorderMacroRecording", 1)
	epics.caput(prefix+"caputRecorderUserMessage", "Recording")
	macroFile = open("macros.py","a")
	macroFile.write("def %s():\n" % macroName)
	# It's not legal to have a python function with no commands in it.
	# Defend against user stopping recording without doing any caputs
	# by writing dummy command to set the record date.
	now = time.strftime("%c")
	macroFile.write("\trecordDate = \"%s\"\n" % now)
	macroFile.flush()
	epics.camonitor(prefix+"caputRecorderComment",callback=commentMonFunc)
	epics.camonitor(prefix+"caputRecorderAddDelayCmd",callback=delayMonFunc)
	for pv in commandMonitorList:
		epics.camonitor(pv,callback=commandMonFunc)

def endMacro():
	global debug, macroFile, prefix, doReloadMacros
	global commandMonitorList
	#print("endMacro: entry\n")
	busy = epics.caget(prefix+"caputRecorderMacroRecording")
	if (not busy):
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
	global debug, doReloadMacros
	if value:
		doReloadMacros = 1
	wake.set()

def reloadMacros():
	global debug, prefix, macroFunctionNames, macroFunctions, menuFields
	global _macroFunctionNames, _macroFunctions

	success = 0
	functions = []
	_macroFunctionNames = []
	_macroFunctions = []
	macroFunctionNames = []
	macroFunctions = []

	try:
		reload(macros)
		success = 1
	except:
		epics.caput(prefix+"caputRecorderUserMessage", "Macro file contains error(s)")

	# erase menu strings
	for menu in range(maxMacroMenus):
		for field in menuFields:
			if (field=="ZRST"):
				epics.caput(prefix + ("caputRecorderMacros%d." % (menu+1)) + field, " ")
			else:
				epics.caput(prefix + ("caputRecorderMacros%d." % (menu+1)) + field, "")

	if success:
		functions = [o for o in getmembers(macros) if isfunction(o[1])]
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
		i = 0
		for (name, func, field) in zip(macroFunctionNames, macroFunctions, menuFields*maxMacroMenus):
			menu = i/len(menuFields) + 1
			epics.caput(prefix + ("caputRecorderMacros%d." % menu) + field, name)
			i += 1

	selectMacro()
	epics.caput(prefix+"caputRecorderReloadMacros", 0)


########################################################################
## Respond to monitors from Macros<n> PVs
## write args for selected macro to EPICS PVs

def selectMacroMonFunc(pvname, value, char_value, **kwd):
	global debug, doSelectMacro
	doSelectMacro = 1
	wake.set()

def selectMacro():
	global debug, prefix, macroFunctionNames, macroFunctions, maxArgs, menuFields

	# find which function is selected
	funcName = epics.caget(prefix+"caputRecorderMacro")
	try:
		func = macroFunctions[macroFunctionNames.index(funcName)]
	except:
		func = None

	if debug: print macroFunctionNames
	if debug: print "func=", func
	# erase arg names and values
	for j in range(1,maxArgs+1):
		epics.caput(prefix+("caputRecorderArg%dName" % j), "")
		epics.caput(prefix+("caputRecorderArg%dValue" % j), "")

	# write arg names and values
	if (func):
		(args, v, k, vals) = getargspec(func)
		if vals:
			args_with_vals = args[-len(vals):]
		if len(args) > 0:
			numFields = min(maxArgs, len(menuFields))
			nums = range(1, numFields+1)
			for (argname, j) in zip(args, nums):
				epics.caput(prefix+("caputRecorderArg%dName" % j), argname)
				if vals and argname in args_with_vals:
					argvalue = vals[args_with_vals.index(argname)]
					epics.caput(prefix+("caputRecorderArg%dValue" % j), repr(argvalue))

	# clear the busy record that was set to begin this operation
	epics.caput(prefix+"caputRecorderMacrosBusy", 0)

########################################################################
## Respond to monitors from ExecuteMacro, and AbortMacro PVs

## execute selected macro
def executeMacroMonFunc(pvname, value, char_value, **kwd):
	global debug, doexecuteMacro
	if debug: print "executeMacroMonFunc: value=%d" % value
	if value:
		doexecuteMacro = 1
	wake.set()

## abort executing macro
def abortMacroMonFunc(pvname, value, char_value, **kwd):
	global debug, doAbortMacro, executingMacro
	if debug: print "abortMacroMonFunc: value=%d" % value
	if value:
		doAbortMacro = 1
		if executingMacro:
			thread.interrupt_main()
	wake.set()

def executeMacro():
	global debug, prefix, macroFunctionNames, macroFunctions, maxArgs, executingMacro
	global _macroFunctionNames

	# find which function is selected
	funcName = epics.caget(prefix+"caputRecorderMacro")
	try:
		func = macroFunctions[macroFunctionNames.index(funcName)]
	except:
		func = None
		executingMacro = 0
		return

	loops = epics.caget(prefix+"caputRecorderExecuteLoops")
	loops = max(1, loops)
	if loops>1:
		commandString = "for i in range(%s): " % loops
	else:
		commandString = ""
	commandString += "macros.%s(" % funcName
	argname = []
	argvalue = []
	numArgs = len(getargspec(func)[0])
	for j in range(min(maxArgs, numArgs)):
		if j>0:
			commandString += ","
		commandString += getargspec(func)[0][j]+"="
		value = epics.caget(prefix+("caputRecorderArg%dValue" % (j+1)), as_string=True)
		commandString += value
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
		print "error executing '%s'\n" % commandString
	executingMacro = 0


############################################################################
def start():
	global debug, prefix, doStartMacro, doStopMacro, doReloadMacros, doexecuteMacro
	global doSelectMacro, doAbortMacro, executingMacro, msgQueue
	global allowedUsers, forbiddenUsers, allowedHosts, forbiddenHosts
	global commandMonitorList

	wake.clear()

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
		print "allowedUsers='%s', forbiddenUsers='%s'\n" % (allowedUsers, forbiddenUsers)
	hosts = epics.caget(prefix+"caputRecorderHosts", as_string=True)
	(allowedHosts, forbiddenHosts) = calcAllowed(hosts)
	if (debug):
		print "allowedHosts='%s', forbiddenHosts='%s'\n" % (allowedHosts, forbiddenHosts)

	# message and queue
	msgQueue = Queue.Queue(maxsize=100)
	writeThread = threading.Thread(target=writer)
	writeThread.daemon = True
	writeThread.start()

	while (1):
		wake.wait(1)
		if wake.is_set():
			if debug: print "start: wake.is_set()"
			wake.clear()
		if doStartMacro:
			doStartMacro=0
			startMacro()
		if doStopMacro:
			doStopMacro = 0
			endMacro()
		if doReloadMacros:
			doReloadMacros = 0
			reloadMacros()
		if doSelectMacro:
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

def go(argv=["xxx:"]):
	global debug, prefix, commandMonitorList

	usage = """
	  python caputRecorder.py prefix [other_prefixes]
	  python caputRecorder.py 1bma: 1bmb: 1bmc:
	"""
	if len(argv) > 0:
		prefix = argv[0]

	commandMonitorList = [prefix+"caputRecorderCommand"]
	
	if len(argv) > 1:
		if debug: print "argv[1:]", argv[1:]
		for otherprefix in argv[1:]:
			commandMonitorList.append(otherprefix+"caputRecorderCommand")

	if debug: print "initial commandMonitorList", commandMonitorList
	stop()
	start()
	stop()


if __name__ == "__main__":

	go(sys.argv[1:])

	
