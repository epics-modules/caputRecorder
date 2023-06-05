---
layout: default
title: Release Notes
nav_order: 3
---



caputRecorder Release Notes
===========================

Release 1-7-5
-------------

*   Fix to stop redefinition of evSubscrip
*   Convert documentation to github pages


Release 1-7-4
-------------

*   Fix to build under epics base 7.0.5


Release 1-7-3
-------------

*   Converted adl files to bob and edl.
*   IOC shell files now installed into top-level iocsh folder rather than residing there.

Release 1-7-2
-------------

*   Req files now installed to top level db folder.

Release 1-7-1
-------------

*   EPICS-version test was defective.

Release 1-7
-----------

*   Added op/ui/autoconvert directory
*   Added callable iocsh boot script

Release 1-6
-----------

*   Defend against user rapidly clicking the "(re)start recorder" button. Previously, this could result in multiple copies of caputRecorder running simultaneously.
*   Previously caputRecorder could end up with '$$' at the end of a PV name, by helpfully appending '$' to a name that already ended with '$'. Now, it makes sure there is at most one '$'.

Release 1-5-1
-------------

*   Increased the number of arguments from 10 to 20.
*   Added caputRecorderExecute.adl, which displays all 20 arguments, and doesn't display recording PVs.

Release 1-5
-----------

*   Fixed host match. Previously only the first component of the host name was stored, so a match to the full name failed.
*   Added global variables, including filepath and filename, which are supported by a file requester, if wxPython is available.

Release 1-4-3
-------------

*   defend against very long strings in caputRecorder.c.
*   defend against malformed caput-notification strings in caputRecorder.py
*   Added powerpoint presentation
*   delete reference to dbChannel.final\_dbr\_type. Doesn't exist in 3.15.2
*   don't use dbNameOfPV from base; it's not public to windows dynamic build
*   If macro argument is of type string, make user's value (from EPICS PV) a string
*   try/except around camonitor calls
*   If program is restarted while executing a macro, old copy now kills macro execution
*   If ExecuteLoops>1 while a macro is executed while recording, write a loop

Release 1-4-2
-------------

*   If ExecuteLoops>1 while a macro is executed while recording, write a loop into macros.py.
*   try/except around wake.wait() in start(), because it sometimes errors on abort.
*   If erasing a macro leaves an mbbo record with a value greater than the number\_of\_items-1, set the value to zero.
*   In R1-4-1, the default time to wait for a callback was -1 seconds, but this doesn't mean "forever" to pyepics. Changed to 1000000.

Release 1-4-1
-------------

*   Previously, the first recording after caputRecorder.py was restarted could record a monitor that actually resulted from the ca-connection process, not from any user action. Now caputRecorder defends against monitors that aren't the results of user action.
*   Previously, the default wait-for-completion time was 300 seconds; now it's -1 (wait forever).
*   In PyEpics 3.2.4, string writes to DBF\_UCHAR fields (such as PROC) caused an error. Now we write to those fields with a number.

Release 1-4
-----------

*   Use asTrapWriteWithData, if it's available, instead of getting values with dbGetField. For EPICS 3.14.12.4 and earlier, and for 3.15.1 and earlier, this requires a patch to base.
*   If using asTrapWriteWithData, convert numbers to strings for ENUM and MENU fields.
*   Permit executing a previously recorded macro while recording a new macro.
*   Increased the number of arguments to 10, and the number of menus to six.
*   Specifying a macro with a put\_callback from a client had a problem: caputRecorderMacro did not post its value unless it was different from its old value, so python didn't get a monitor, so python didn't clear the busy record, so the operation never completed. Fixed.
*   Clear menus and arguments in the database, rather than requiring caputRecorder.py to write to all those fields.
*   Added caputRecorderStartTime. If caputRecorderStartTime changes, but isn't empty, caputRecorder assumes a new copy of the program has started, and exits. Removed code trying to achieve this result from `example_start_put_recorder`
*   Added caputRecorderHeartbeat, to show the status of the program.
*   Added connection management: if caputRecorderHeartbeat disconnects, caputRecorder disables all EPICS stuff until 10 seconds after caputRecorderHeartbeat reconnects, to avoid misconstruing initial monitors from a rebooted IOC as commands to execute. If caputRecorderHeartbeat remains disconnected for 10 seconds, caputRecorder exits.
*   When menus have been rewritten, caputRecorder sets caputRecorderNeedRefresh, so user knows to press the "Refresh Menus" button. Added code to detect when the display has been closed and reopened (e.g., as the result of "Refresh Menus"), and clear caputRecorderNeedRefresh.
*   caputRecorder.py exits when it detects a new version of itself talking to the same control database.
*   If macro exists in macro file, allow Fail/Append/Replace. Added option to try to reproduce timing of caputs. Made wait for completion an option. Reload macros on ca reconnect.
*   Allow for more than one copy of caputRecorder per ioc.

Release 1-3-1
-------------

*   Use environment variables START\_PUTRECORDER and MACROS\_PY, instead of having required locations.

Release 1-3
-----------

*   Use epicsSnprintf, instead of snprintf, for older vxWorks versions.
*   Enable user to insert delay commands, and to specify the put\_callback wait time.

Release 1-2
-----------

*   Changed format of the value the IOC writes to caputRecorderCommand, from "pvname,value" to "pvname,value,user@host". Note that an R1-2 ioc won't work with an R1-1 client, but an R1-1 ioc will work with an R1-2 client.
*   Added PVs caputRecorderUsers and caputRecorderHosts
*   caputRecorder.py now filters commands to honor caputRecorderUsers and caputRecorderHosts
*   caputRecorder.py now defends against macro names that contain embedded spaces or are python keywords.

Release 1-1
-----------

*   caputRecorder.c: fixes for EPICS 3.15 asTrapWrite, fix for string values longer than 100 bytes

Release 1-0
-----------

*   first release

Suggestions and Comments to:  
[Tim Mooney](mailto:mooney@aps.anl.gov) : (mooney@aps.anl.gov)
