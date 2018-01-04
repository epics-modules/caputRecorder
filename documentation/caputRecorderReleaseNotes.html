<html>

<head>
<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">
<title>caputRecorderReleaseNotes</title>
</head>

<body bgcolor="#FFFFFF">

<h1 align="center">caputRecorder Release Notes</h1>

<h2 align="center">Release 1-8</h2>
<ul>
<li>EPICS-version test was defective.
</ul>


<h2 align="center">Release 1-7</h2>
<ul>

<li>Added op/ui/autoconvert directory

<li>Added callable iocsh boot script
</ul>

<h2 align="center">Release 1-6</h2>
<ul>

<li>Defend against user rapidly clicking the "(re)start recorder" button. 
Previously, this could result in multiple copies of caputRecorder running simultaneously.

<li>Previously caputRecorder could end up with '$$' at the end of a PV name, by
helpfully appending '$' to a name that already ended with '$'. Now, it makes
sure there is at most one '$'.

</ul>


<h2 align="center">Release 1-5-1</h2>
<ul>

<li>Increased the number of arguments from 10 to 20.

<li>Added caputRecorderExecute.adl, which displays all 20
arguments, and doesn't display recording PVs.

</ul>


<h2 align="center">Release 1-5</h2>
<ul>
<li>Fixed host match.  Previously only the first component of the host name was
stored, so a match to the full name failed. 
<li>Added global variables, including filepath and filename, which are
supported by a file requester, if wxPython is available.
</ul>

<h2 align="center">Release 1-4-3</h2>
<ul>
<li>defend against very long strings in caputRecorder.c.
<li>defend against malformed caput-notification strings in caputRecorder.py
<li>Added powerpoint presentation
<li>delete reference to dbChannel.final_dbr_type.  Doesn't exist in 3.15.2
<li>don't use dbNameOfPV from base; it's not public to windows dynamic build
<li>If macro argument is of type string, make user's value (from EPICS PV) a string
<li>try/except around camonitor calls
<li>If program is restarted while executing a macro, old copy now kills macro execution
<li>If ExecuteLoops>1 while a macro is executed while recording, write a loop

</ul>


<h2 align="center">Release 1-4-2</h2>
<ul>

<li>If ExecuteLoops>1 while a macro is executed while recording, write a loop
into macros.py.
<li>try/except around wake.wait() in start(), because it sometimes errors on
abort.
<li>If erasing a macro leaves an mbbo record with a value greater than the
number_of_items-1, set the value to zero.

<li>In R1-4-1, the default time to wait for a callback was -1 seconds, but this
doesn't mean "forever" to pyepics.  Changed to 1000000.

</ul>

<h2 align="center">Release 1-4-1</h2>
<ul>

<li>Previously, the first recording after caputRecorder.py was restarted could
record a monitor that actually resulted from the ca-connection process, not from
any user action.  Now caputRecorder defends against monitors that aren't the
results of user action. 

<li>Previously, the default wait-for-completion time was 300 seconds; now it's
-1 (wait forever).

<li>In PyEpics 3.2.4, string writes to DBF_UCHAR fields (such as PROC) caused an
error.  Now we write to those fields with a number.

</ul>


<h2 align="center">Release 1-4</h2>
<ul>

<li>Use asTrapWriteWithData, if it's available, instead of getting values with
dbGetField.  For EPICS 3.14.12.4 and earlier, and for 3.15.1 and earlier, this
requires a patch to base.

<li>If using asTrapWriteWithData, convert numbers to strings for ENUM and MENU
fields.

<li>Permit executing a previously recorded macro while recording a new macro.

<li>Increased the number of arguments to 10, and the number of menus to six.

<li>Specifying a macro with a put_callback from a client had a problem:
caputRecorderMacro did not post its value unless it was different from its old
value, so python didn't get a monitor, so python didn't clear the busy record,
so the operation never completed.  Fixed.

<li>Clear menus and arguments in the database, rather than requiring
caputRecorder.py to write to all those fields.

<li>Added caputRecorderStartTime.  If caputRecorderStartTime changes, but isn't
empty, caputRecorder assumes a new copy of the program has started, and exits.
Removed code trying to achieve this result from
<code>example_start_put_recorder</code>

<li>Added caputRecorderHeartbeat, to show the status of the program.

<li>Added connection management: if caputRecorderHeartbeat disconnects,
caputRecorder disables all EPICS stuff until 10 seconds after
caputRecorderHeartbeat reconnects, to avoid misconstruing initial monitors from
a rebooted IOC as commands to execute.  If caputRecorderHeartbeat remains
disconnected for 10 seconds, caputRecorder exits.

<li>When menus have been rewritten, caputRecorder sets caputRecorderNeedRefresh,
so user knows to press the "Refresh Menus" button.  Added code to detect when
the display has been closed and reopened (e.g., as the result of "Refresh
Menus"), and clear caputRecorderNeedRefresh.

<li>caputRecorder.py exits when it detects a new version of itself talking to
the same control database.

<li>If macro exists in macro file, allow Fail/Append/Replace.  Added option to
try to reproduce timing of caputs.  Made wait for completion an option.  Reload
macros on ca reconnect.

<li>Allow for more than one copy of caputRecorder per ioc.


</ul>

<h2 align="center">Release 1-3-1</h2>
<ul>

<li>Use environment variables START_PUTRECORDER and MACROS_PY, instead of having
required locations.

</ul>

<h2 align="center">Release 1-3</h2>

<ul>
<li>Use epicsSnprintf, instead of snprintf, for older vxWorks versions.

<li>Enable user to insert delay commands, and to specify the put_callback wait
time.
</ul>

<h2 align="center">Release 1-2</h2>
<ul>

<li>Changed format of the value the IOC writes to caputRecorderCommand, from
"pvname,value" to "pvname,value,user@host".  Note that an R1-2 ioc won't work
with an R1-1 client, but an R1-1 ioc will work with an R1-2 client.

<li>Added PVs caputRecorderUsers and caputRecorderHosts

<li>caputRecorder.py now filters commands to honor caputRecorderUsers and
caputRecorderHosts

<li>caputRecorder.py now defends against macro names that contain embedded
spaces or are python keywords.

</ul>

<h2 align="center">Release 1-1</h2>

<ul>

<li>caputRecorder.c: fixes for EPICS 3.15 asTrapWrite, fix for string values
longer than 100 bytes

</ul>

<h2 align="center">Release 1-0</h2>

<ul>

<li>first release

</ul>



<address>
    Suggestions and Comments to: <br>
    <a href="mailto:mooney@aps.anl.gov">Tim Mooney </a>:
    (mooney@aps.anl.gov) <br>
</address>
</body>
</html>
