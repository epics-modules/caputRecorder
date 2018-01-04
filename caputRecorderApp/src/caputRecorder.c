#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <asLib.h>
#include <asTrapWrite.h>
#include <dbAccess.h>
#include <cvtFast.h>
#include <recSup.h>
#include <errlog.h>
#include <epicsMessageQueue.h>
#include <epicsStdio.h>
#include <epicsThread.h>
#include <epicsVersion.h>

/* EPICS base version test.*/
#ifndef EPICS_VERSION_INT
#define VERSION_INT(V,R,M,P) ( ((V)<<24) | ((R)<<16) | ((M)<<8) | (P))
#define EPICS_VERSION_INT VERSION_INT(EPICS_VERSION, EPICS_REVISION, EPICS_MODIFICATION, EPICS_PATCH_LEVEL)
#endif
#define LT_EPICSBASE(V,R,M,P) (EPICS_VERSION_INT < VERSION_INT((V),(R),(M),(P)))
#define GE_EPICSBASE(V,R,M,P) (EPICS_VERSION_INT >= VERSION_INT((V),(R),(M),(P)))

#if GE_EPICSBASE(3,15,0,0)

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
 * API there yet (see dbChannel.h...).
 */

#endif
#include <iocsh.h>
#include <epicsExport.h>


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

#define MIN(a,b) (a)>(b)?(b):(a);

volatile int caputRecorderDebug=0;
epicsExportAddress(int,caputRecorderDebug);

/*************************************************************
 * myConvert
 */
#define oldDBR_STRING      0
#define oldDBR_INT         1
#define oldDBR_SHORT       1
#define oldDBR_FLOAT       2
#define oldDBR_ENUM        3
#define oldDBR_CHAR        4
#define oldDBR_LONG        5
#define oldDBR_DOUBLE      6

static void getEnumString(dbAddr *paddr, char *destString, unsigned short us) {
	struct rset *prset = 0;
	struct dbr_enumStrs	enumStrs;
	int status;

	cvtUshortToString(us, destString);
	if (paddr) {
		prset = dbGetRset(paddr);
		if (prset && prset->get_enum_strs) {
			status = (*prset->get_enum_strs)(paddr,&enumStrs);
			if (!status) {
				if (us < enumStrs.no_str) {
					strcpy(destString, enumStrs.strs[us]);
				}
			}
		}
	}
}

static void getMenuString(dbAddr *paddr, char *destString, unsigned short us) {
    dbFldDes *pdbFldDes = 0;
    dbMenu *pdbMenu = 0;
    char **papChoiceValue = 0;
	unsigned int nChoice = 0;

	cvtUshortToString(us, destString);
	if (paddr) {
		pdbFldDes = paddr->pfldDes;
		if (pdbFldDes) {
			pdbMenu = (dbMenu *)pdbFldDes->ftPvt;
			if (pdbMenu) {
				nChoice = pdbMenu->nChoice;
				papChoiceValue = pdbMenu->papChoiceValue;
			}
		}
	}
	if (nChoice > 0) {
		if (caputRecorderDebug) errlogPrintf("getMenuString: nChoice = %d\n", nChoice);
		if (us < nChoice) {
			strcpy(destString, papChoiceValue[us]);
		}
	}
}

static int myConvert(dbAddr *paddr, char *destString, int dbrType, dbfType field_type, void *data, int no_elements, int maxSize) {
	char *pchar =  (char *)data;
	short *pshort = (short *)data;
	unsigned short *pushort = (unsigned short *)data;
	epicsInt32 *pint32 = (epicsInt32 *)data;
	float *pfloat = (float *)data;
	double *pdouble = (double *)data;
	int i;

	if (caputRecorderDebug) errlogPrintf("myConvert: dbrType=%d, field_type=%d\n", dbrType, field_type);
	switch (dbrType) {
	case(oldDBR_STRING):
		/* ignore no_elements */
		strncpy(destString,(char *)data, maxSize);
		break;

	case(oldDBR_SHORT):
		/* ignore no_elements */
		switch (field_type) {
		case DBF_ENUM:
			getEnumString(paddr, destString, (unsigned short)*pshort);
			break;
		case DBF_MENU:
			getMenuString(paddr, destString, (unsigned short)*pshort);
			break;
		default:
			cvtShortToString(*pshort, destString);
			break;
		}
		break;

	case(oldDBR_ENUM):
		/* ignore no_elements */
		switch (field_type) {
		case DBF_ENUM:
			getEnumString(paddr, destString, *pushort);
			break;
		case DBF_MENU:
			getMenuString(paddr, destString, *pushort);
			break;
		default:
			cvtUshortToString(*pushort, destString);
			break;
		}
		break;

	case(oldDBR_CHAR):
		if (no_elements > maxSize-2) no_elements = maxSize-2;
		for (i=0; i<no_elements; i++) destString[i] = pchar[i];
		if (i<maxSize-1) destString[i] = '\0';
		break;

	case(oldDBR_LONG):
		/* ignore no_elements */
		switch (field_type) {
		case DBF_ENUM:
			getEnumString(paddr, destString, (unsigned short)*pint32);
			break;
		case DBF_MENU:
			getMenuString(paddr, destString, (unsigned short)*pint32);
			break;
		default:
			cvtLongToString(*pint32, destString);
			break;
		}
		break;

	case(oldDBR_FLOAT):
		/* ignore no_elements */
		switch (field_type) {
		case DBF_CHAR:
		case DBF_UCHAR:
		case DBF_SHORT:
		case DBF_USHORT:
		case DBF_LONG:
		case DBF_ULONG:
			cvtLongToString((epicsInt32)*pfloat, destString);
			break;
		case DBF_ENUM:
			getEnumString(paddr, destString, (unsigned short)*pfloat);
			break;
		case DBF_MENU:
			getMenuString(paddr, destString, (unsigned short)*pfloat);
			break;
		default:
			cvtFloatToString(*pfloat, destString, 7);
			break;
		}
		break;

	case(oldDBR_DOUBLE):
		/* ignore no_elements */
		switch (field_type) {
		case DBF_CHAR:
		case DBF_UCHAR:
		case DBF_SHORT:
		case DBF_USHORT:
		case DBF_LONG:
		case DBF_ULONG:
			cvtLongToString((epicsInt32)*pdouble, destString);
			break;
		case DBF_ENUM:
			getEnumString(paddr, destString, (unsigned short)*pdouble);
			break;
		case DBF_MENU:
			getMenuString(paddr, destString, (unsigned short)*pdouble);
			break;
		default:
			cvtDoubleToString(*pdouble, destString, 11);
			break;
		}
		break;
	default:
		break;
	}

	*(destString+maxSize-1) = 0;
	return(0);
}

static void myGetValueString(dbAddr *paddr, long n, char *value, int valueSize) {
	dbfType field_type = paddr->field_type;
	short field_size = paddr->field_size;
	long one=1, options=0;
	char save[COMMAND_SIZE];
	
	if ((n>1) && (field_size==1)) {
		/* long string */
		if (caputRecorderDebug) errlogPrintf("myGetValueString: (n>1) && (field_size==1)\n");
		dbGetField(paddr, field_type, value, &options, &n, NULL);
	} else if (n>1) {
		/* we don't do arrays, unless they're actually long strings */
		if (caputRecorderDebug) errlogPrintf("myGetValueString: n>1\n");
		dbGetField(paddr, DBF_STRING, value, &options, &one, NULL);
		strncpy(save, value, COMMAND_SIZE-1);
		epicsSnprintf(value, valueSize-1, "array(%s,...)", save);
	} else {
		if (caputRecorderDebug) errlogPrintf("myGetValueString: n<=1\n");
		dbGetField(paddr, DBF_STRING, value, &options, &n, NULL);
	}
	value[valueSize-1] = '\0';
}

static unsigned my_dbNameOfPV(const dbAddr *paddr, char *pBuf, unsigned bufLen) {
    dbFldDes * pfldDes = paddr->pfldDes;
    char * pBufTmp = pBuf;

    if (bufLen==0) return(0);

	strncpy(pBufTmp, paddr->precord->name, bufLen-1);
	strncat(pBufTmp, ".", (bufLen-1)-(pBufTmp-pBuf));
	strncat(pBufTmp, pfldDes->name, (bufLen-1)-(pBufTmp-pBuf));
    return(pBufTmp - pBuf);
}

static void myAsDataListener(asTrapWriteMessage *pmessage, int after) {
#if GE_EPICSBASE(3,15,0,0)
	dbChannel *pchannel;
	dbAddr addr;
#endif
	DBADDR *paddr;
	char pvname[BUFFER_SIZE], value[COMMAND_SIZE], save[COMMAND_SIZE];
	MSG msg;
	unsigned int numChar;
	long no_elements=1, n;
	short field_size;
	dbfType field_type;
	int i, j, dbrType;

	if (caputRecorderDebug > 1) errlogPrintf("myAsDataListener: after=%d\n", after);
	if (after==0) return;

	if (caputRecorderDebug > 1) errlogPrintf("myAsDataListener: %s@%s\n", pmessage->userid, pmessage->hostid);

#if GE_EPICSBASE(3,15,0,0)
	/* Haven't tested this with asTrapWriteWithData */
	if (caputRecorderDebug > 1) errlogPrintf("myAsDataListener: GE_EPICSBASE(3,15,0,0)\n");
	pchannel = pmessage->serverSpecific;
	addr = pchannel->addr;
	paddr = &addr;
	no_elements = pchannel->final_no_elements;
	field_type = pchannel->final_type;
	field_size = pchannel->final_field_size;
	if (caputRecorderDebug > 1) errlogPrintf("myAsDataListener:final_type=%d\n", pchannel->final_type);
	if (caputRecorderDebug > 1) errlogPrintf("myAsDataListener:no_elements=%ld, field_size=%d\n", no_elements, field_size);
	strncpy(pvname, dbChannelName(pchannel), BUFFER_SIZE-1);
	numChar = strlen(pvname);
#else
	if (caputRecorderDebug > 1) errlogPrintf("myAsDataListener: LT_EPICSBASE(3,15,0)\n");
	paddr = pmessage->serverSpecific;
	no_elements = paddr->no_elements;
	field_type = paddr->field_type;
	field_size = paddr->field_size;
	/*numChar = dbNameOfPV(paddr, pvname, BUFFER_SIZE);*/
	numChar = my_dbNameOfPV(paddr, pvname, BUFFER_SIZE);
#endif

	if (strstr(pvname, "caputRecorderHeartbeat")) {
		return;
	}
	if (caputRecorderDebug) errlogPrintf("myAsDataListener: pvname='%s', no_elements==%ld, field_size==%d\n", pvname, no_elements, field_size);

	no_elements = MIN(COMMAND_SIZE-1, no_elements);
	dbrType = -1;
#ifdef asTrapWriteWithData
	if (pmessage->data) {
		dbrType = pmessage->dbrType;
		no_elements = pmessage->no_elements;
		no_elements = MIN(COMMAND_SIZE-1, no_elements);
		if (caputRecorderDebug) errlogPrintf("myAsDataListener: pvname='%s'\n", pvname);
		myConvert(paddr, value, dbrType, field_type, pmessage->data, pmessage->no_elements, COMMAND_SIZE-1);
	} else {
		myGetValueString(paddr, no_elements, value, COMMAND_SIZE-1);
	}
#else
	myGetValueString(paddr, no_elements, value, COMMAND_SIZE-1);
#endif

	/* long strings */
	if (caputRecorderDebug) errlogPrintf("myAsDataListener: paddr->field_type=%d, no_elements==%ld\n", paddr->field_type, no_elements);
	if ((paddr->field_type == DBF_CHAR) && (no_elements > MAX_STRING_SIZE)) {
		i = strlen(pvname);
		if (i > 0 && i < PVNAME_STRINGSZ-1 && pvname[i-1] != '$') {
			pvname[i] = '$';
			pvname[i+1] = '\0';
		}
	}
	if (caputRecorderDebug) errlogPrintf("myAsDataListener: field_type=%d, dbrType=%d, no_elements='%ld'\n",
	field_type, dbrType, no_elements);

	if (caputRecorderDebug) errlogPrintf("myAsDataListener: pvname='%s' => '%s'\n", pvname, value);
	
	/* if " in value, replace with \" */
	strcpy(save, value);
	for (i=0, j=0; i<COMMAND_SIZE; ) {
		if (save[j] == '"') value[i++] = '\\';
		value[i++] = save[j++];
	}
	n = epicsSnprintf(msg.command, COMMAND_SIZE-1, "%s,%s,%s@%s", pvname, value, pmessage->userid, pmessage->hostid);
	msg.command[n] = '\0';
	msg.nchar = n+1;
	if (caputRecorderDebug) errlogPrintf("myAsDataListener: msg.command='%s', msg.nchar=%d\n\n", msg.command, msg.nchar);

	/* if (valid_command_buffer) dbPutField(paddr_cmd, DBF_CHAR, msg.command, n+1); */
	if (!caputRecorderMsgQueue) {
		errlogPrintf("myAsDataListener: no message queue\n");
		return;
	}
	if (caputRecorderDebug) errlogPrintf("myAsDataListener: &msg=%p\n", &msg);

	if (epicsMessageQueueTrySend(caputRecorderMsgQueue, (void *)&msg, MSG_SIZE)) {
		errlogPrintf("myAsDataListener: message queue overflow\n");
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

	id = asTrapWriteRegisterListener(myAsDataListener);
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

