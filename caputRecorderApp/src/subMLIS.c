#ifdef vxWorks
#include <vxWorks.h>
#endif

#include <stdio.h>
#include <stdlib.h>

#include <dbAccess.h>
#include <recGbl.h>
#include <recSup.h>
#include <dbEvent.h>
#include <subRecord.h>
#include <registryFunction.h>
#include <epicsExport.h>

int	debugSubMLIS = 0;
epicsExportAddress(int, debugSubMLIS);

#define NUM_EVENT_SUBSCRIPTIONS 5
typedef struct evSubscrip {
    ELLNODE                 node;
    struct dbAddr           *paddr;
} evSub;

long	initSubMLIS(struct subRecord *psub)
{
	if ((psub->dpvt = calloc(NUM_EVENT_SUBSCRIPTIONS, sizeof(evSub *))) == NULL) {
		printf("subMLIS:%s: couldn't allocate memory ", psub->name);
		return(-1);
	}
	if (debugSubMLIS)
		printf("%s: Init completed\n", psub->name);
	return(0);
}


long SubMLIS(struct subRecord *psub)
{
	evSub *pevent, **pSavedEvent;
	int i, changed=0;

    pevent = (evSub *)ellFirst(&psub->mlis);
	pSavedEvent = (evSub **)psub->dpvt;
	for (i=0; i<NUM_EVENT_SUBSCRIPTIONS; i++) {
		if (pevent != pSavedEvent[i]) {
			changed = 1;
		}
		pSavedEvent[i] = pevent;
		if (debugSubMLIS)
			printf("pSavedEvent[%d]=%p; pevent=%p\n", i, pSavedEvent[i], pevent);
		if (pevent) {
	    	pevent = (evSub *)ellNext(&pevent->node);
		}
	}
	if (changed) psub->val = psub->val+1;
	return(0);
}

static registryFunctionRef SubMLISRef[] = {
	{"initSubMLIS", (REGISTRYFUNCTION)initSubMLIS},
	{"SubMLIS", (REGISTRYFUNCTION)SubMLIS}
};

static void SubMLISRegister(void) {
	registryFunctionRefAdd(SubMLISRef, NELEMENTS(SubMLISRef));
}

epicsExportRegistrar(SubMLISRegister);
