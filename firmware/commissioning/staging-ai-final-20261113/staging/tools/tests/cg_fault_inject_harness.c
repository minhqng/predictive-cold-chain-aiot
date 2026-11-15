/*
 * Host harness for the test-only fault-injection module. It compiles the real,
 * unchanged cg_fault_inject.c twice: once with CG_FAULT_INJECTION=1 (enabled
 * scenarios) and once with it 0 (production-disabled). No ESP-IDF headers, no
 * hardware. This proves the selection, single-ROM isolation, console grammar,
 * reboot-clear and the production-inert behaviour without a board.
 */
#include <stdio.h>
#include <string.h>

#include "cg_fault_inject.h"
#include "coldguard_config.h"

static int failures;

#define CHECK(cond)                                                        \
    do {                                                                   \
        if (!(cond)) {                                                     \
            printf("FAIL line %4d: %s\n", __LINE__, #cond);                \
            failures++;                                                    \
        }                                                                  \
    } while (0)

int main(void)
{
#if CG_FAULT_INJECTION
    CHECK(cg_fault_inject_enabled());

    /* baseline: nothing injected */
    cg_fault_inject_reset();
    CHECK(!cg_fault_inject_ds_active(0));
    CHECK(!cg_fault_inject_ds_active(1));
    CHECK(!cg_fault_inject_ds_active(2));
    CHECK(!cg_fault_inject_ds_active(3));
    CHECK(!cg_fault_inject_pzem_down());

    /* exactly one ROM: T2 down, others stay up */
    CHECK(cg_fault_inject_console_line("FAULT DS T2 ON"));
    CHECK(cg_fault_inject_ds_active(1));
    CHECK(!cg_fault_inject_ds_active(0));
    CHECK(!cg_fault_inject_ds_active(2));
    CHECK(!cg_fault_inject_ds_active(3));
    CHECK(!cg_fault_inject_pzem_down());

    /* reselecting moves the single fault, never two at once */
    CHECK(cg_fault_inject_console_line("FAULT DS T3 ON"));
    CHECK(!cg_fault_inject_ds_active(1));
    CHECK(cg_fault_inject_ds_active(2));

    /* PZEM down is independent of the DS selection */
    CHECK(cg_fault_inject_console_line("FAULT PZEM ON"));
    CHECK(cg_fault_inject_pzem_down());
    CHECK(cg_fault_inject_ds_active(2));

    /* explicit clear (and the model of a reboot) removes both */
    CHECK(cg_fault_inject_console_line("FAULT CLEAR"));
    CHECK(!cg_fault_inject_pzem_down());
    CHECK(!cg_fault_inject_ds_active(2));

    /* OFF toggles a single selection back to none */
    CHECK(cg_fault_inject_console_line("FAULT DS T1 ON"));
    CHECK(cg_fault_inject_ds_active(0));
    CHECK(cg_fault_inject_console_line("FAULT DS T1 OFF"));
    CHECK(!cg_fault_inject_ds_active(0));

    /* unknown role is consumed with no state change (no accidental remap) */
    CHECK(cg_fault_inject_console_line("FAULT DS T9 ON"));
    CHECK(!cg_fault_inject_ds_active(0));
    CHECK(!cg_fault_inject_ds_active(1));
    CHECK(!cg_fault_inject_ds_active(2));
    CHECK(!cg_fault_inject_ds_active(3));

    /* malformed commands are consumed, no change */
    CHECK(cg_fault_inject_console_line("FAULT DS"));
    CHECK(cg_fault_inject_console_line("FAULT PZEM MAYBE"));
    CHECK(!cg_fault_inject_pzem_down());

    /* trailing tokens are rejected with no state change */
    CHECK(cg_fault_inject_console_line("FAULT DS T2 ON junk"));
    CHECK(!cg_fault_inject_ds_active(1));
    CHECK(cg_fault_inject_console_line("FAULT PZEM ON junk"));
    CHECK(!cg_fault_inject_pzem_down());

    /* OFF clears only the matching role, never a different active one */
    CHECK(cg_fault_inject_console_line("FAULT DS T2 ON"));
    CHECK(cg_fault_inject_ds_role() == 1);
    CHECK(cg_fault_inject_console_line("FAULT DS T3 OFF"));
    CHECK(cg_fault_inject_ds_active(1));          /* still T2, not cleared */
    CHECK(cg_fault_inject_console_line("FAULT DS T2 OFF"));
    CHECK(!cg_fault_inject_ds_active(1));
    CHECK(cg_fault_inject_ds_role() == -1);

    /* non-FAULT lines are left for the normal command parser */
    CHECK(!cg_fault_inject_console_line("START 5"));
    CHECK(!cg_fault_inject_console_line(""));
    CHECK(!cg_fault_inject_console_line("FAULTY DS T1 ON"));

    printf("FAULT_INJECT ENABLED HARNESS: %s\n", failures ? "FAIL" : "ALL PASS");
#else
    /* Production build: the injection path must be entirely inert. */
    CHECK(!cg_fault_inject_enabled());
    CHECK(!cg_fault_inject_ds_active(0));
    CHECK(!cg_fault_inject_pzem_down());
    /* a FAULT console command cannot activate injection in production */
    CHECK(!cg_fault_inject_console_line("FAULT DS T2 ON"));
    CHECK(!cg_fault_inject_ds_active(1));
    CHECK(!cg_fault_inject_console_line("FAULT PZEM ON"));
    CHECK(!cg_fault_inject_pzem_down());
    CHECK(cg_fault_inject_ds_role() == -1);
    printf("FAULT_INJECT DISABLED HARNESS: %s\n", failures ? "FAIL" : "ALL PASS");
#endif
    return failures ? 1 : 0;
}
