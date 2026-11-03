# Member A release candidate acceptance - 20261103T114812Z

repo: C:\Users\dlbac\Downloads\coldguard-repo\A-W06-command-ack
python: C:\WINDOWS\py.exe -3   pyserial: 3.5
requested phases: A

| Phase | Risk | Decision | Verdict | Reason |
|---|---|---|---|---|
| PHASE_A_OFFLINE | OFFLINE | EXECUTABLE | PASS | all discovered offline entrypoints passed |
| PHASE_B_IDENTITY | READ_ONLY_PORT | BLOCKED_NEEDS_OPERATOR | BLOCKED_NEEDS_OPERATOR | not requested on this run and gated: needs -Phases to include B plus -AllowSerialProbe |
| PHASE_C_BUILD | OFFLINE | NOT_REQUESTED | NOT_RUN | not requested on this run: add C to -Phases to execute it (no hardware action was taken for it) |
| PHASE_D_FLASH | FLASH_WRITE | BLOCKED_NEEDS_OPERATOR | BLOCKED_NEEDS_OPERATOR | not requested on this run and gated: needs -Phases to include D plus -AllowFlash |
| PHASE_E_SAFETY_OFF | POWERED_ISOLATED | BLOCKED_NEEDS_OPERATOR | BLOCKED_NEEDS_OPERATOR | not requested on this run and gated: needs -Phases to include E plus -AllowEnergize -AllowSerialProbe -AckSlot3Removed -AckPsu12VPresent -AckTecBranchOpen -AckOperatorAtBox -AckNoSoftwarePowerActions |
| PHASE_F_TEC_ACTUATION | POWERED_ACTUATION | BLOCKED_NEEDS_OPERATOR | BLOCKED_NEEDS_OPERATOR | not requested on this run and gated: needs -Phases to include F plus -AllowTecActuation -OperatorSupervised -AckSlot3Status |

## Safety rules encoded in this entrypoint
- Default invocation performs ZERO hardware actions and ZERO flashing.
- PHASE_B opens the port with dtr=False and rts=False and calls read() only: zero bytes written, asserted from the capture summary, not from a comment.
- No actuator command (ARM / STAGE / START / STOP / ESTOP / CLEAR / SUPERVISE / RUN / PHASE) is ever sent by this script.
- PHASE_D is dry-run by default; a write-flash needs -AllowFlash, the exact typed confirmation phrase and the separate -ExecuteFlash.
- This script never reinserts a fuse and never toggles a power supply: those are physical operator actions.
- A FAIL in any phase aborts the run; there is no retry anywhere and specifically no retry after an unexpected COM loss.
- Exit code 0 only when every requested phase PASSED; NOT_RUN and BLOCKED are reported separately from FAIL.
- PHASE_F can never report PASS: the script has no capability to energise or actuate, it only writes the operator action sheet.

exit code: 2 - 5 phase(s) NOT_RUN or BLOCKED_NEEDS_OPERATOR / BLOCKED_DEPENDENCY; no failure
machine-readable result: C:\Users\dlbac\Downloads\coldguard-repo\A-W06-command-ack\tools\acceptance\output\20261103T114812Z\member-a-acceptance.json
