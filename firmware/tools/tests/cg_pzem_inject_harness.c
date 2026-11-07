/*
 * Host harness for the test-only PZEM transport-disabled status. Compiles the
 * real cg_pzem.c with CG_FAULT_INJECTION on and off: the INJECT_DISABLED status
 * must exist and name correctly only in the gated test build, and the normal
 * statuses must be unaffected in production.
 */
#include <stdio.h>
#include <string.h>

#include "cg_pzem.h"

int main(void)
{
#if defined(CG_FAULT_INJECTION) && CG_FAULT_INJECTION
    if (strcmp(cg_pzem_status_name(CG_PZEM_INJECT_DISABLED), "INJECT_DISABLED") != 0) {
        printf("FAIL INJECT_DISABLED name\n");
        return 1;
    }
    printf("PZEM_INJECT GATED_ON OK\n");
#else
    if (strcmp(cg_pzem_status_name(CG_PZEM_TIMEOUT), "TIMEOUT") != 0) {
        printf("FAIL TIMEOUT name\n");
        return 1;
    }
    printf("PZEM_INJECT GATED_OFF OK\n");
#endif
    return 0;
}
