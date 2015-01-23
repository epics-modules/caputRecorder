#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <asTrapWrite.h>
#include <dbAccess.h>
#include <epicsExport.h>
#include <errlog.h>
#include <epicsMessageQueue.h>
#include <epicsThread.h>
#include <epicsVersion.h>
#define GE_EPICSBASE(v,r,l) ((EPICS_VERSION >= (v)) && (EPICS_REVISION >= (r)) && (EPICS_MODIFICATION >= (l)))

#if GE_EPICSBASE(3,15,0)

#include <dbChannel.h>

/* Andrew Johnson's tech-talk message:
 *In 3.15 the void * asTrapWriteMessage.serverSpecific pointer that gets
 * passed to the listeners is no longer a dbAddr*, it's now a dbChannel* so
 * to get the PV name all RSRV asTrapWriteListeners must call
 *     dbChannelName((dbChannel *) msg.serverSpecific)
 * instead, which returns a const char* holding the channel's full PV name.
 * 
 * I just updated the 3.15.1 AppDevGuide to correct this in the Access
 * Security chapter, although we haven't actually documented the dbChannel
 * API there yet (see dbChannel.h and post questions here until that gets
 * written, sorry).
 */

#endif


static epicsMessageQueueId caputRecorderMsgQueue=0;
static int shutdown = FALSE;

static DBADDR dbaddr_cmd;
static DBADDR *paddr_cmd = &dbaddr_cmd;
static int valid_command_buffer=0;
static epicsThreadId threadId=0;
#define BUFFER_SIZE 100
#define COMMAND_SIZE 300
#define MAX_MESSAGES 200
typedef struct {
	int nchar;
	char command[COMMAND_SIZE];
} MSG;
#define MSG_SIZE sizeof(MSG)

volatile int caputRecorderDebug=0;
epicsExportAddress(int,caputRecorderDebug);

void myAsListener(asTrapWriteMessage *pmessage, int after) {
#if GE_EPICSBASE(3,15,0)
	dbChannel *pchannel;
	dbAddr addr;
#endif
	DBADDR *paddr;
	char pvname[BUFFER_SIZE], value[COMMAND_SIZE], save[COMMAND_SIZE];
	MSG msg;
	unsigned int numChar;
	long n=1, one=1, options=0;
	short field_size;
	dbfType field_type;
	int i, j;

	if (caputRecorderDebug) errlogPrintf("myListener: after=%d\n", after);
	if (after==0) return;

	if (caputRecorderDebug) errlogPrintf("myListener: %s@%s\n", pmessage->userid, pmessage->hostid);

#if GE_EPICSBASE(3,15,0)
	if (caputRecorderDebug) errlogPrintf("myListener: GE_EPICSBASE(3,15,0)\n");
	pchannel = pmessage->serverSpecific;
	addr = pchannel->addr;
	paddr = &addr;
	n = pchannel->final_no_elements;
	field_type = pchannel->final_type;
	/* field_type = pchannel->final_dbr_type; */
	field_size = pchannel->final_field_size;
	if (caputRecorderDebug) errlogPrintf("myListener:final_type=%d, final_dbr_type=%d\n", pchannel->final_type, pchannel->final_dbr_type);
	if (caputRecorderDebug) errlogPrintf("myListener:n=%d, field_size=%d\n", n, field_size);
	strncpy(pvname, dbChannelName(pchannel), BUFFER_SIZE-1);
	numChar = strlen(pvname);
#else
	if (caputRecorderDebug) errlogPrintf("myListener: LT_EPICSBASE(3,15,0)\n");
	paddr = pmessage->serverSpecific;
	n = paddr->no_elements;
	field_type = paddr->field_type;
	field_size = paddr->field_size;
	numChar = dbNameOfPV(paddr, pvname, BUFFER_SIZE);
#endif
	if (caputRecorderDebug) errlogPrintf("myListener: field_type=%d, no_elements='%ld'\n", field_type, n);

	if (caputRecorderDebug) errlogPrintf("n==%ld, field_size==%d\n", n, field_size);

	if ((n>1) && (field_size==1)) {
		/* long string */
		if (caputRecorderDebug) errlogPrintf("myListener: (n>1) && (field_size==1)\n");
		dbGetField(paddr, field_type, value, &options, &n, NULL);
	} else if (n>1) {
		/* we don't do arrays, unless they're actually long strings */
		if (caputRecorderDebug) errlogPrintf("myListener: n>1\n");
		dbGetField(paddr, DBF_STRING, value, &options, &one, NULL);
		strcpy(save, value);
		sprintf(value, "array(%s,...)", save);
	} else {
		if (caputRecorderDebug) errlogPrintf("myListener: n<=1\n");
		dbGetField(paddr, DBF_STRING, value, &options, &n, NULL);
	}
	value[COMMAND_SIZE-1] = '\0';
	if (caputRecorderDebug) errlogPrintf("myListener: pvname='%s' => '%s'\n", pvname, value);
	
	/* if " in value, replace with \" */
	strcpy(save, value);
	for (i=0, j=0; i<COMMAND_SIZE; ) {
		if (save[j] == '"') value[i++] = '\\';
		value[i++] = save[j++];
	}
	n = snprintf(msg.command, COMMAND_SIZE-1, "%s,%s,%s@%s", pvname, value, pmessage->userid, pmessage->hostid);
	msg.command[n] = '\0';
	msg.nchar = n+1;
	if (caputRecorderDebug) errlogPrintf("myListener: msg.command='%s', msg.nchar=%d\n\n", msg.command, msg.nchar);

	/* if (valid_command_buffer) dbPutField(paddr_cmd, DBF_CHAR, msg.command, n+1); */
	if (!caputRecorderMsgQueue) {
		errlogPrintf("myAsListener: no message queue\n");
		return;
	}
	if (caputRecorderDebug) errlogPrintf("myListener: &msg=%p\n", &msg);

	if (epicsMessageQueueTrySend(caputRecorderMsgQueue, (void *)&msg, MSG_SIZE)) {
		errlogPrintf("myAsListener: message queue overflow\n");
	}

}

static void caputRecorderTask() {
	int msg_size;
	MSG msg;
	MSG *pmsg = &msg;
	while (!shutdown) {
		msg_size = epicsMessageQueueReceiveWithTimeout(caputRecorderMsgQueue, (void *)pmsg, MSG_SIZE, 5.0);
		if (msg_size > 0 && pmsg && valid_command_buffer) {
			if (caputRecorderDebug) errlogPrintf("caputRecorderTask: pmsg=%p\n", pmsg);
			if (caputRecorderDebug) errlogPrintf("caputRecorderTask: pmsg->command='%s'\n\n", pmsg->command);
			dbPutField(paddr_cmd, DBF_CHAR, pmsg->command, pmsg->nchar);
		}
	}
}

void registerCaputRecorderTrapListener(char *PVname) {
	asTrapWriteId id;
	long status;

	if (caputRecorderDebug) printf("registerCaputRecorderTrapListener: entry\n");
	if ((status = dbNameToAddr(PVname, paddr_cmd)) != 0) {
		printf("registerCaputRecorderTrapListener: dbNameToAddr can't find PV '%s'\n", PVname);
		valid_command_buffer = 0;
		return;
	}
	valid_command_buffer = 1;

	id = asTrapWriteRegisterListener(myAsListener);
	if (!caputRecorderMsgQueue) {
		caputRecorderMsgQueue = epicsMessageQueueCreate(MAX_MESSAGES, MSG_SIZE);
	}

	if (!threadId) {
		threadId = epicsThreadCreate("caputRecorder", epicsThreadPriorityLow,
			epicsThreadGetStackSize(epicsThreadStackSmall),
			caputRecorderTask, NULL);
	}
}

/*-------------------------------------------------------------------------------*/
/*** ioc-shell command registration ***/
#include <epicsExport.h>
#include <iocsh.h>

#define IOCSH_ARG		static const iocshArg
#define IOCSH_ARG_ARRAY	static const iocshArg * const
#define IOCSH_FUNCDEF	static const iocshFuncDef

/* int registerCaputRecorderTrapListener(char *filename); */
IOCSH_ARG       registerCaputRecorderTrapListener_Arg0    = {"PVname",iocshArgString};
IOCSH_ARG_ARRAY registerCaputRecorderTrapListener_Args[1] = {&registerCaputRecorderTrapListener_Arg0};
IOCSH_FUNCDEF   registerCaputRecorderTrapListener_FuncDef = {"registerCaputRecorderTrapListener",1,registerCaputRecorderTrapListener_Args};
static void     registerCaputRecorderTrapListener_CallFunc(const iocshArgBuf *args) {registerCaputRecorderTrapListener(args[0].sval);}

void caputRecorderRegister(void)
{
    iocshRegister(&registerCaputRecorderTrapListener_FuncDef, registerCaputRecorderTrapListener_CallFunc);
}

epicsExportRegistrar(caputRecorderRegister);

