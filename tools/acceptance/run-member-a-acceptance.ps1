#Requires -Version 5.1
<#
run-member-a-acceptance.ps1 - single Windows acceptance entrypoint for the
Member A release candidate (ESP32-S3 predictive cold-chain AIoT).

PHASE_A_OFFLINE .. PHASE_F_TEC_ACTUATION, with every hardware-touching phase
behind an explicit operator switch. Verdict and gate vocabulary is reused from
A-IHA-01-campaign/firmware/tools/iha01/iha01_runner.py:
EXECUTABLE / BLOCKED_NEEDS_OPERATOR / BLOCKED_DEPENDENCY, and per-phase
PASS / FAIL / NOT_RUN-with-reason / BLOCKED_NEEDS_OPERATOR.

Default invocation runs PHASE_A only: no port is opened, no build is invoked,
nothing is flashed, no branch is energised.

  powershell -NoProfile -ExecutionPolicy Bypass -File tools\acceptance\run-member-a-acceptance.ps1
  ... -Plan                      # print the gate decision table, execute nothing
  ... -Phases A,C
  ... -Phases A,B -AllowSerialProbe -Port COM4 -Seconds 30
  ... -Phases A,C,D -AllowFlash -ConfirmFlashPhrase <literal>
  ... -Phases A,B,E -AllowEnergize -Port COM4 -AllowSerialProbe (5 ack switches)

Exit codes: 0 every requested phase PASS; 1 any phase FAIL; 2 no failure but
one or more phases NOT_RUN / BLOCKED_NEEDS_OPERATOR / BLOCKED_DEPENDENCY;
3 the script could not start (repo layout, no Python interpreter).
#>
[CmdletBinding()]
param(
    [ValidateSet('A', 'B', 'C', 'D', 'E', 'F')]
    [string[]] $Phases = @('A'),

    [switch] $AllPhases,
    [switch] $Plan,

    [string] $RepoRoot,
    [string] $OutDir,
    [string] $PythonExe,

    # PHASE_B_IDENTITY (read-only port work is still hardware work)
    [switch] $AllowSerialProbe,
    [string] $Port,
    [ValidateRange(1, 600)] [int] $Seconds = 30,
    [ValidateRange(1200, 921600)] [int] $Baud = 115200,

    # PHASE_C_BUILD
    # ESP-IDF/mbedtls fails past ~250 object-path characters, so the build must
    # run in a pre-staged short path. The coordinator owns _rcbuild; this script
    # never creates it, it only accepts a -BuildDir that already exists.
    [string] $BuildDir = 'C:\Users\dlbac\Downloads\coldguard-repo\_rcbuild',
    [string] $IdfProfile = 'C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1',
    # PHASE_C is DRY-RUN unless -RunBuild is passed: the entrypoint prints the
    # exact idf.py recipe instead of starting a competing build.
    [switch] $RunBuild,
    [switch] $ArtifactsOnly,
    [string] $ExpectedFirmwareSha256,

    # PHASE_D_FLASH
    [switch] $AllowFlash,
    [string] $ConfirmFlashPhrase,
    [switch] $ExecuteFlash,

    # PHASE_E_SAFETY_OFF
    [switch] $AllowEnergize,
    [switch] $AckSlot3Removed,
    [switch] $AckPsu12VPresent,
    [switch] $AckTecBranchOpen,
    [switch] $AckOperatorAtBox,
    [switch] $AckNoSoftwarePowerActions,

    # PHASE_F_TEC_ACTUATION
    [switch] $AllowTecActuation,
    [switch] $OperatorSupervised,
    [string] $AckSlot3Status,
    [string] $ConfirmTecPhrase,

    # Predecessor wave drivers are subsumed by the W06 superset driver; running
    # them again costs ~4 min, so they are opt-in.
    [switch] $IncludeLegacyWaveDrivers
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# ---------------------------------------------------------------------------
# Constants: verdicts, gate decisions and the literals an operator must type.
# ---------------------------------------------------------------------------
$V_PASS = 'PASS'
$V_FAIL = 'FAIL'
$V_NOT_RUN = 'NOT_RUN'
$V_BLOCKED = 'BLOCKED_NEEDS_OPERATOR'
$D_EXECUTABLE = 'EXECUTABLE'
$D_BLOCKED_OPERATOR = 'BLOCKED_NEEDS_OPERATOR'
$D_BLOCKED_DEPENDENCY = 'BLOCKED_DEPENDENCY'

$LITERAL_FLASH = 'I-CONFIRM-ARTIFACT-HASHES-AND-SLOT3-STATUS'
$LITERAL_TEC = 'OPERATOR-PRESENT-TEC-ACTUATION'

# The actuator vocabulary the firmware accepts, from firmware/main/cg_tec_command.h.
# Nothing in this script ever writes any of it to a port.
$FORBIDDEN_TOKENS = @('ARM', 'STAGE', 'START', 'STOP', 'ESTOP', 'CLEAR', 'SUPERVISE', 'RUN', 'PHASE')

# States that mean the TEC branch is not commanding current, from the H8S frames
# observed in _probe-id/baseline.log (state=OFF, pwm_applied_permille=0).
$ALLOWED_IDLE_STATES = @('OFF', 'IDLE')

$SafetyRules = @(
    'Default invocation performs ZERO hardware actions and ZERO flashing.',
    'PHASE_B opens the port with dtr=False and rts=False and calls read() only: zero bytes written, asserted from the capture summary, not from a comment.',
    'No actuator command (ARM / STAGE / START / STOP / ESTOP / CLEAR / SUPERVISE / RUN / PHASE) is ever sent by this script.',
    'PHASE_D is dry-run by default; a write-flash needs -AllowFlash, the exact typed confirmation phrase and the separate -ExecuteFlash.',
    'This script never reinserts a fuse and never toggles a power supply: those are physical operator actions.',
    'A FAIL in any phase aborts the run; there is no retry anywhere and specifically no retry after an unexpected COM loss.',
    'Exit code 0 only when every requested phase PASSED; NOT_RUN and BLOCKED are reported separately from FAIL.',
    'PHASE_F can never report PASS: the script has no capability to energise or actuate, it only writes the operator action sheet.'
)

$PhaseSpec = [ordered]@{
    'A' = @{
        Name      = 'PHASE_A_OFFLINE'
        Risk      = 'OFFLINE'
        Required  = @()
        Summary   = 'Existing host-side validators and unit checks: no serial, no device, no build toolchain.'
    }
    'B' = @{
        Name      = 'PHASE_B_IDENTITY'
        Risk      = 'READ_ONLY_PORT'
        Required  = @('AllowSerialProbe')
        Summary   = 'COM ports + VID:PID inventory and an optional zero-write boot capture.'
    }
    'C' = @{
        Name      = 'PHASE_C_BUILD'
        Risk      = 'OFFLINE'
        Required  = @()
        Summary   = 'ESP-IDF v6.1 build in a pre-staged short path, then artifact hashes.'
    }
    'D' = @{
        Name      = 'PHASE_D_FLASH'
        Risk      = 'FLASH_WRITE'
        Required  = @('AllowFlash')
        Summary   = 'Flash plan plus backup/recovery path; dry-run unless -ExecuteFlash.'
    }
    'E' = @{
        Name      = 'PHASE_E_SAFETY_OFF'
        Risk      = 'POWERED_ISOLATED'
        Required  = @('AllowEnergize', 'AllowSerialProbe', 'AckSlot3Removed', 'AckPsu12VPresent', 'AckTecBranchOpen', 'AckOperatorAtBox', 'AckNoSoftwarePowerActions')
        Summary   = '12 V present with fuse slot 3 (15 A, IBT-2 B+) physically REMOVED; read-only observation only.'
    }
    'F' = @{
        Name      = 'PHASE_F_TEC_ACTUATION'
        Risk      = 'POWERED_ACTUATION'
        Required  = @('AllowTecActuation', 'OperatorSupervised', 'AckSlot3Status')
        Summary   = 'Operator action sheet. The script never actuates; unreachable unattended.'
    }
}

$PhaseEPreconditions = @(
    'Fuse slot 3 (15 A, IBT-2 B+) is physically REMOVED, so no current path to the TEC exists.',
    'The 12 V supply is present and powering the logic rail (that is the point of this phase).',
    'The TEC branch conductors at the IBT-2 B+ side are open/insulated and touched by nobody.',
    'The operator is physically at the box for the whole session and knows where the supply switch is.',
    'No software action in this run reinserts a fuse or toggles a supply; PHY-FUSE-001 (docs/01 s16.4) forbids a powered TEC test that bypasses the branch fuse.',
    'A read-only capture is the only port operation; opening the port can reset the board, which cannot energise anything.'
)

$script:Transcript = New-Object System.Collections.ArrayList
$script:PhasesToRun = @('A')
$script:PythonPrefix = @()
$script:PythonRuntime = [ordered]@{ exe = ''; prefix = @() }
$script:BuildOutputDir = ''
$script:FlashArgs = @()
$script:Run = [ordered]@{
    schema          = 'coldguard.member-a-acceptance.v1'
    generated_utc   = ''
    repo_root       = ''
    out_dir         = ''
    python          = ''
    python_exe      = ''
    pyserial        = $null
    requested       = @()
    overall         = ''
    exit_code       = -1
    exit_meaning    = ''
    abort_reason    = ''
    safety_rules    = $SafetyRules
    phases          = [ordered]@{}
}

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
function Write-Log {
    param([string]$Message)
    $line = '{0}  {1}' -f (Get-Date).ToString('HH:mm:ss'), $Message
    Write-Host $line
    [void]$script:Transcript.Add($line)
}

function Write-Section {
    param([string]$Title)
    Write-Log ''
    Write-Log ('==== {0} ====' -f $Title)
}

function Get-RepoRelative {
    param([string]$Relative)
    return (Join-Path $script:Run['repo_root'] $Relative)
}

function Initialize-Phase {
    param([string]$Key)
    $spec = $PhaseSpec[$Key]
    $script:Run['phases'][$Key] = [ordered]@{
        key            = $Key
        name           = $spec.Name
        risk           = $spec.Risk
        summary        = $spec.Summary
        requested      = $false
        gate_decision  = ''
        gates_required = @($spec.Required)
        gates_missing  = @()
        verdict        = $V_NOT_RUN
        reason         = 'phase not started'
        started_utc    = ''
        finished_utc   = ''
        checks         = @()
        artifacts      = @()
        operator_actions = @()
        notes          = @()
    }
}

function Set-PhaseOutcome {
    param([string]$Key, [string]$Verdict, [string]$Reason)
    $phase = $script:Run['phases'][$Key]
    $phase['verdict'] = $Verdict
    $phase['reason'] = $Reason
    $phase['finished_utc'] = [datetime]::UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
    Write-Log ('{0} verdict={1} reason={2}' -f $PhaseSpec[$Key].Name, $Verdict, $Reason)
}

function Test-GateSupplied {
    param([string]$Name)
    $value = (Get-Variable -Name $Name -ValueOnly)
    if ($value -is [switch]) { return $value.IsPresent }
    if ($value -is [string]) { return (-not [string]::IsNullOrWhiteSpace($value)) }
    return [bool]$value
}

function Get-MissingGates {
    param([string]$Key)
    $missing = @()
    foreach ($gate in $PhaseSpec[$Key].Required) {
        if (-not (Test-GateSupplied $gate)) { $missing += $gate }
    }
    return $missing
}

function Test-InteractiveConsole {
    try { return ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) }
    catch { return $false }
}

function Resolve-TypedPhrase {
    param([string]$Supplied, [string]$PromptText, [ref]$Note)
    if (-not [string]::IsNullOrWhiteSpace($Supplied)) { return $Supplied.Trim() }
    if (-not (Test-InteractiveConsole)) {
        $Note.Value = 'no interactive console: the operator must supply the confirmation phrase as a parameter'
        return ''
    }
    Write-Log $PromptText
    $typed = Read-Host
    return $typed.Trim()
}

function Format-Arguments {
    param([string[]]$Arguments)
    $quoted = New-Object System.Collections.ArrayList
    foreach ($item in $Arguments) {
        if ($item -match '\s' -and $item -notmatch '"') {
            [void]$quoted.Add('"' + $item + '"')
        }
        else {
            [void]$quoted.Add($item)
        }
    }
    return [string[]]$quoted.ToArray()
}

function Get-PlainLines {
    # ROOT-CAUSE GUARD for the phase A JSON bloat.
    # Get-Content returns System.String objects decorated with the provider
    # NoteProperties PSPath / PSParentPath / PSChildName / PSDrive / PSProvider.
    # ConvertTo-Json then walks PSDrive -> Provider -> ImplementingType (a live
    # System.Type) -> Assembly.DefinedTypes / ExportedTypes, i.e. the whole
    # System.Management.Automation type table, once per line. That turned a
    # 1,089-byte stdout log into a 90,635,714-byte phase-A-offline.json and hung
    # the 16:56 run. [System.IO.File]::ReadAllLines returns undecorated strings.
    param([string]$Path, [int]$MaxLines = 0, [int]$MaxLineChars = 400)
    if ([string]::IsNullOrWhiteSpace($Path)) { return @() }
    if (-not (Test-Path -LiteralPath $Path)) { return @() }
    $all = @([System.IO.File]::ReadAllLines($Path))
    $clean = @()
    foreach ($item in $all) {
        $s = $item -as [string]
        if ($null -eq $s) { $s = '' }
        if ($MaxLineChars -gt 0 -and $s.Length -gt $MaxLineChars) { $s = $s.Substring(0, $MaxLineChars) + '...[TRUNCATED]' }
        $clean += $s
    }
    if ($MaxLines -gt 0 -and $clean.Count -gt $MaxLines) { $clean = @($clean | Select-Object -Last $MaxLines) }
    return @($clean)
}

function ConvertTo-JsonBounded {
    # Serialise, but never let a regression turn the run directory into a
    # multi-megabyte artifact or hang the runner: bounded depth, bounded size.
    param($InputObject, [int]$Depth = 8, [int]$MaxChars = 4000000, [string]$FallbackDocument)
    try {
        $json = ConvertTo-Json $InputObject -Depth $Depth
        $text = $json -as [string]
        if ($null -eq $text) { $text = '' }
        if ($text.Length -gt $MaxChars) {
            Write-Log ('JSON serialised to ' + $text.Length + ' chars, over the ' + $MaxChars + ' char budget: writing the hard-trimmed minimal document instead (BLOCKED_SOFTWARE on the verbose artifact)')
            return ($FallbackDocument -as [string])
        }
        return $text
    }
    catch {
        Write-Log ('ConvertTo-Json failed: ' + $_.Exception.Message + ' - writing the hard-trimmed minimal document')
        return ($FallbackDocument -as [string])
    }
}

function Invoke-LoggedCommand {
    param(
        [Parameter(Mandatory)][string]$Label,
        [Parameter(Mandatory)][string]$FilePath,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory
    )
    $base = ($Label -replace '[^A-Za-z0-9_.-]', '_')
    $stdoutPath = Join-Path $script:Run['out_dir'] ($base + '.out.txt')
    $stderrPath = Join-Path $script:Run['out_dir'] ($base + '.err.txt')
    if (-not [string]::IsNullOrWhiteSpace($WorkingDirectory)) {
        if (-not (Test-Path -LiteralPath $WorkingDirectory)) {
            throw "Invoke-LoggedCommand: working directory missing: $WorkingDirectory"
        }
        $proc = Start-Process -FilePath $FilePath -ArgumentList (Format-Arguments $Arguments) `
            -WorkingDirectory $WorkingDirectory -NoNewWindow -PassThru -Wait `
            -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    }
    else {
        $proc = Start-Process -FilePath $FilePath -ArgumentList (Format-Arguments $Arguments) `
            -NoNewWindow -PassThru -Wait `
            -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    }
    $code = if ($null -ne $proc.ExitCode) { $proc.ExitCode } else { -1 }
    $lines = @(Get-PlainLines -Path $stdoutPath)
    $lines += @(Get-PlainLines -Path $stderrPath)
    return [ordered]@{
        label     = $Label
        command   = ((@($FilePath) + @($Arguments)) -join ' ')
        exit_code = $code
        stdout_log = $stdoutPath
        stderr_log = $stderrPath
        lines     = @($lines)
        tail      = @($lines | Select-Object -Last 25)
    }
}

function Get-ChildCheckLines {
    param([string[]]$Lines)
    $rows = @()
    foreach ($line in $Lines) {
        if ($line -match '^\[(PASS|FAIL|NOT_RUN|NEED_USER_ACTION|BLOCKED[_A-Z]*)\]\s*(.*)$') {
            $rows += [ordered]@{ marker = $Matches[1]; text = $Matches[2].Trim() }
        }
    }
    return @($rows)
}

function Get-NotRunLines {
    param([string[]]$Lines)
    $surfaced = @()
    foreach ($line in $Lines) {
        if ($line -match 'NOT_RUN|NEED_USER_ACTION|not certified|remain open') {
            $surfaced += $line.Trim()
        }
    }
    return @($surfaced)
}

function Invoke-ProbeProcess {
    param([string]$FilePath, [string[]]$Arguments)
    $outFile = Join-Path $env:TEMP 'cg_acceptance_probe_out.txt'
    try {
        $proc = Start-Process -FilePath $FilePath -ArgumentList (Format-Arguments $Arguments) `
            -NoNewWindow -PassThru -Wait -RedirectStandardOutput $outFile `
            -RedirectStandardError ($outFile + '.err')
        $code = if ($null -ne $proc.ExitCode) { $proc.ExitCode } else { 1 }
        $text = ''
        if (Test-Path -LiteralPath $outFile) { $text = ((Get-Content -LiteralPath $outFile -Raw -ErrorAction SilentlyContinue) -as [string]).Trim() }
        return [ordered]@{ exit_code = $code; output = $text }
    }
    catch {
        return [ordered]@{ exit_code = 1; output = '' }
    }
}

function Resolve-PythonRuntime {
    # The launcher prefix matters: py.exe needs -3, python.exe does not, so every
    # later call site must reuse the same resolved exe + prefix pair.
    param([switch]$PreferIdf)
    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($PythonExe)) {
        if (Test-Path -LiteralPath $PythonExe) { $candidates += [pscustomobject]@{ exe = $PythonExe; prefix = @() } }
        else { throw "-PythonExe not found: $PythonExe" }
    }
    else {
        $idfPython = 'C:\Espressif\tools\python\v6.1\venv\Scripts\python.exe'
        if ($PreferIdf.IsPresent -and (Test-Path -LiteralPath $idfPython)) {
            $candidates += [pscustomobject]@{ exe = $idfPython; prefix = @() }
        }
        $pyLauncher = Join-Path $env:SystemRoot 'py.exe'
        if (Test-Path -LiteralPath $pyLauncher) { $candidates += [pscustomobject]@{ exe = $pyLauncher; prefix = @('-3') } }
        $found = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($null -ne $found) { $candidates += [pscustomobject]@{ exe = $found.Source; prefix = @() } }
    }
    foreach ($candidate in $candidates) {
        $probe = Invoke-ProbeProcess -FilePath $candidate.exe -Arguments (@($candidate.prefix) + @('-c', 'import sys'))
        if ($probe.exit_code -eq 0) { return [ordered]@{ exe = $candidate.exe; prefix = @($candidate.prefix) } }
    }
    throw 'no usable Python interpreter found; pass -PythonExe'
}

function Invoke-PythonCommand {
    param([string]$Label, [string[]]$Arguments, [string]$WorkingDirectory)
    return Invoke-LoggedCommand -Label $Label -FilePath $script:PythonRuntime['exe'] `
        -Arguments (@($script:PythonRuntime['prefix']) + @($Arguments)) -WorkingDirectory $WorkingDirectory
}

function Get-EsptoolRunner {
    # esptool lives in the IDF venv, not necessarily in the interpreter that runs
    # the host validators, so PHASE_D resolves its own runner instead of assuming.
    $idfPython = 'C:\Espressif\tools\python\v6.1\venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $idfPython) {
        return [ordered]@{ exe = $idfPython; prefix = @(); source = 'idf venv' }
    }
    return [ordered]@{ exe = $script:PythonRuntime['exe']; prefix = @($script:PythonRuntime['prefix']); source = 'acceptance interpreter' }
}

function Test-PySerialAvailable {
    param([string]$Label)
    $probe = Invoke-ProbeProcess -FilePath $script:PythonRuntime['exe'] `
        -Arguments (@($script:PythonRuntime['prefix']) + @('-c', 'import serial;print(serial.__version__)'))
    if ($probe.exit_code -eq 0) {
        return [ordered]@{ available = $true; version = $probe.output }
    }
    return [ordered]@{ available = $false; version = ''; reason = "pyserial is not importable by $Label" }
}

function Get-JsonFieldValues {
    param($Summary, [string]$Key)
    if ($null -eq $Summary) { return @() }
    if ($null -eq $Summary.field_values) { return @() }
    $prop = $Summary.field_values.PSObject.Properties[$Key]
    if ($null -eq $prop -or $null -eq $prop.Value) { return @() }
    return @($prop.Value)
}

function Test-AllZero {
    param([string[]]$Values)
    $Values = @($Values)
    if ($Values.Count -lt 1) { return $false }
    foreach ($value in $Values) {
        if ($value -ne '0') { return $false }
    }
    return $true
}

function Write-OperatorSheet {
    param([string]$Key, [string[]]$Lines)
    $path = Join-Path $script:Run['out_dir'] ('{0}-{1}-operator-sheet.md' -f $Key, $PhaseSpec[$Key].Name)
    Set-Content -LiteralPath $path -Value ($Lines -join "`r`n") -Encoding ASCII
    return $path
}

# ---------------------------------------------------------------------------
# PHASE_A_OFFLINE
# ---------------------------------------------------------------------------
function Find-OfflineEntrypoints {
    $tools = Join-Path (Get-RepoRelative 'firmware') 'tools'
    $evidence = Get-RepoRelative 'evidence\A'
    $required = @(
        [ordered]@{ id = 'w06_superset'; role = 'required'; label = 'RC superset driver (unit suite + W02..W06 static checks + W02..W06 dossier validators + contract artifacts)'; path = (Join-Path $tools 'run_all_checks_w06.py'); cwd = (Get-RepoRelative '') },
        [ordered]@{ id = 'w01_validator'; role = 'required'; label = 'W01 hardware-audit dossier validator (not covered by the W06 driver)'; path = (Join-Path $evidence 'W01\validate_w01.py'); cwd = (Join-Path $evidence 'W01') }
    )
    $optional = @(
        [ordered]@{ id = 'w02_driver'; role = 'optional'; label = 'legacy W02 wave driver'; path = (Join-Path $tools 'run_all_checks.py'); cwd = (Get-RepoRelative '') },
        [ordered]@{ id = 'w03_driver'; role = 'optional'; label = 'legacy W03 wave driver'; path = (Join-Path $tools 'run_all_checks_w03.py'); cwd = (Get-RepoRelative '') },
        [ordered]@{ id = 'w04_driver'; role = 'optional'; label = 'legacy W04 wave driver'; path = (Join-Path $tools 'run_all_checks_w04.py'); cwd = (Get-RepoRelative '') },
        [ordered]@{ id = 'w05_driver'; role = 'optional'; label = 'legacy W05 wave driver'; path = (Join-Path $tools 'run_all_checks_w05.py'); cwd = (Get-RepoRelative '') }
    )
    $all = @()
    foreach ($entry in ($required + $optional)) {
        $copy = [ordered]@{}
        foreach ($k in $entry.Keys) { $copy[$k] = $entry[$k] }
        $copy['exists'] = (Test-Path -LiteralPath $entry['path'])
        $all += [pscustomobject]$copy
    }
    return @($all)
}

function Invoke-PhaseA {
    $Key = 'A'
    Initialize-Phase $Key
    $script:Run['phases'][$Key]['requested'] = $true
    $script:Run['phases'][$Key]['gate_decision'] = $D_EXECUTABLE
    $script:Run['phases'][$Key]['started_utc'] = [datetime]::UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
    Write-Section 'PHASE_A_OFFLINE'

    $entries = Find-OfflineEntrypoints
    $script:Run['phases'][$Key]['notes'] += (@($entries | ForEach-Object { '{0} role={1} exists={2} path={3}' -f $_.id, $_.role, $_.exists, $_.path }))

    $rows = @()
    $failed = 0
    foreach ($entry in $entries) {
        if ($entry.role -eq 'optional' -and -not $IncludeLegacyWaveDrivers.IsPresent) {
            Write-Log ('skip (optional, -IncludeLegacyWaveDrivers not passed): {0}' -f $entry.label)
            $rows += [ordered]@{ id = $entry.id; label = $entry.label; path = $entry.path; verdict = $V_NOT_RUN; exit_code = $null; reason = 'optional entrypoint; -IncludeLegacyWaveDrivers not passed'; checks = @(); output_tail = @() }
            continue
        }
        if (-not $entry.exists) {
            $reason = 'entrypoint path does not exist in this tree'
            if ($entry.role -eq 'required') {
                $failed++
                $verdict = $V_FAIL
            }
            else {
                $verdict = $V_NOT_RUN
            }
            Write-Log ('[{0}] {1}: {2}' -f $verdict, $entry.label, $reason)
            $rows += [ordered]@{ id = $entry.id; label = $entry.label; path = $entry.path; verdict = $verdict; exit_code = $null; reason = $reason; checks = @(); output_tail = @() }
            continue
        }
        Write-Log ('run: {0}' -f $entry.label)
        $result = Invoke-PythonCommand -Label ('phaseA_' + $entry.id) `
            -Arguments @($entry.path) -WorkingDirectory $entry.cwd
        $verdict = if ($result.exit_code -eq 0) { $V_PASS } else { $V_FAIL }
        if ($verdict -eq $V_FAIL) { $failed++ }
        $rows += [ordered]@{
            id            = $entry.id
            role          = $entry.role
            label         = $entry.label
            path          = $entry.path
            cwd           = $entry.cwd
            command       = $result.command
            exit_code     = $result.exit_code
            verdict       = $verdict
            reason        = ''
            checks        = @(Get-ChildCheckLines $result.lines)
            surfaced_not_run = @(Get-NotRunLines $result.lines)
            output_tail   = @($result.tail)
            stdout_log    = $result.stdout_log
        }
        Write-Log ('  exit={0} verdict={1} parsed_checks={2}' -f $result.exit_code, $verdict, @($result.lines | Where-Object { $_ -match '^\[(PASS|FAIL)\]' }).Count)
    }

    $script:Run['phases'][$Key]['checks'] = $rows
    $totalPassed = @($rows | Where-Object { $_.verdict -eq $V_PASS }).Count
    $summaryText = ('PHASE_A: {0} passed, {1} failed, {2} not_run' -f $totalPassed, $failed, @($rows | Where-Object { $_.verdict -eq $V_NOT_RUN }).Count)
    Write-Log $summaryText
    $machinePath = Join-Path $script:Run['out_dir'] 'phase-A-offline.json'
    $payload = [ordered]@{ phase = 'PHASE_A_OFFLINE'; summary = $summaryText; failed = $failed; checks = $rows }
    Write-Log 'serialising phase A json'
    $fallback = (ConvertTo-Json ([ordered]@{
        phase    = 'PHASE_A_OFFLINE'
        summary  = $summaryText
        failed   = $failed
        verbose  = 'BLOCKED_SOFTWARE'
        reason   = 'per-check verbose document exceeded the JSON size budget; minimal document retained, full stdout/err logs are the raw evidence'
        ids      = @($rows | ForEach-Object { $_['id'] })
        verdicts = @($rows | ForEach-Object { $_['verdict'] })
    }) -Depth 3)
    $json = ConvertTo-JsonBounded $payload -Depth 6 -MaxChars 2000000 -FallbackDocument $fallback
    Write-Log ('phase A json length=' + ($json -as [string]).Length)
    Set-Content -LiteralPath $machinePath -Value $json -Encoding ASCII
    Write-Log ('phase A json written to ' + $machinePath)
    $script:Run['phases'][$Key]['artifacts'] += $machinePath
    if ($failed -gt 0) {
        Set-PhaseOutcome $Key $V_FAIL "$failed required offline check(s) failed - see $machinePath"
    }
    else {
        Set-PhaseOutcome $Key $V_PASS "all discovered offline entrypoints passed"
    }
}

# ---------------------------------------------------------------------------
# PHASE_B_IDENTITY
# ---------------------------------------------------------------------------
function Get-SerialPortInventory {
    $names = @()
    try { $names = @([System.IO.Ports.SerialPort]::GetPortNames()) } catch { $names = @() }
    $rows = @()
    try {
        $devices = @(Get-CimInstance -ClassName Win32_PnPEntity -ErrorAction Stop | Where-Object { $_.Name -match '\(COM\d+\)' })
        foreach ($device in $devices) {
            $com = ''
            if ($device.Name -match '\((COM\d+)\)') { $com = $Matches[1] }
            $vid = ''
            $pid = ''
            if ($device.PNPDeviceID -match 'VID_([0-9A-Fa-f]{4})') { $vid = $Matches[1] }
            if ($device.PNPDeviceID -match 'PID_([0-9A-Fa-f]{4})') { $pid = $Matches[1] }
            $rows += [ordered]@{
                com_port      = $com
                name          = $device.Name
                vid           = $vid
                pid           = $pid
                vid_pid       = ('{0}:{1}' -f $vid, $pid)
                status        = $device.Status
                pnp_device_id = $device.PNPDeviceID
            }
        }
    }
    catch {
        $rows += [ordered]@{ com_port = ''; name = 'PnP enumeration failed'; vid = ''; pid = ''; vid_pid = ''; status = $_.Exception.Message; pnp_device_id = '' }
    }
    return [ordered]@{ port_names = @($names | Sort-Object); devices = @($rows) }
}

function Get-CaptureToolPath { return Join-Path $PSScriptRoot 'read_only_capture.py' }

function Invoke-ReadOnlyCapture {
    param([string]$PhaseKey, [string]$Label)
    $out = Join-Path $script:Run['out_dir'] ('{0}-{1}-capture.log' -f $PhaseKey, $Label)
    $jsonOut = Join-Path $script:Run['out_dir'] ('{0}-{1}-capture.json' -f $PhaseKey, $Label)
    $result = Invoke-PythonCommand -Label ('phase' + $PhaseKey + '_capture_' + $Label) `
        -Arguments @((Get-CaptureToolPath), '--port', $Port, '--baud', "$Baud", '--seconds', "$Seconds", '--out', $out, '--json-out', $jsonOut) `
        -WorkingDirectory $PSScriptRoot
    $summary = $null
    if (Test-Path -LiteralPath $jsonOut) {
        $summary = ([System.IO.File]::ReadAllText($jsonOut) | ConvertFrom-Json)
    }
    return [ordered]@{ result = $result; log = $out; summary = $summary; summary_path = $jsonOut }
}

function Invoke-PhaseB {
    $Key = 'B'
    Initialize-Phase $Key
    $phase = $script:Run['phases'][$Key]
    $phase['requested'] = $true
    Write-Section 'PHASE_B_IDENTITY'

    $missing = @(Get-MissingGates $Key)
    $phase['gates_missing'] = $missing
    if ($missing.Count -gt 0) {
        $phase['gate_decision'] = $D_BLOCKED_OPERATOR
        Set-PhaseOutcome $Key $V_BLOCKED ('gate not passed: -' + ($missing -join ' -'))
        $phase['operator_actions'] += @('Pass -AllowSerialProbe to permit read-only port identification.', 'Nothing in this phase flashes or actuates.')
        return
    }
    if ([string]::IsNullOrWhiteSpace($Port)) {
        # No port supplied: the capture degrades to NOT_RUN. No port object is
        # created at any point on this path, so no byte can be written anywhere.
        $phase['gate_decision'] = $D_BLOCKED_OPERATOR
        $phase['notes'] += 'port not supplied: PnP enumeration only, no port object was created and no byte was written'
        $inventory = Get-SerialPortInventory
        $phase['checks'] += [ordered]@{ id = 'enumerate'; label = 'COM port + VID:PID inventory (PnP only, no port opened)'; verdict = $V_PASS; exit_code = 0; devices = $inventory.devices; port_names = $inventory.port_names }
        $phase['checks'] += [ordered]@{ id = 'capture'; label = 'read-only boot capture'; verdict = $V_NOT_RUN; exit_code = $null; reason = '-Port was not supplied, so no port was opened; nothing was written to any device' }
        Set-PhaseOutcome $Key $V_NOT_RUN '-Port not supplied: identity capture NOT_RUN (PnP enumeration above ran without opening a port)'
        $phase['operator_actions'] += @('Re-run with -Port COMx to capture boot text read-only.')
        return
    }
    $phase['gate_decision'] = $D_EXECUTABLE
    $inventory = Get-SerialPortInventory
    $phase['checks'] += [ordered]@{ id = 'enumerate'; label = 'COM port + VID:PID inventory (PnP only, no port opened)'; verdict = $V_PASS; exit_code = 0; devices = $inventory.devices; port_names = $inventory.port_names }
    Write-Log ('enumerated ports: {0}' -f (@($inventory.port_names) -join ', '))
    foreach ($device in $inventory.devices) {
        Write-Log ('  {0} vid:pid={1} status={2}' -f $device.name, $device.vid_pid, $device.status)
    }

    if (-not $script:Run['pyserial'].available) {
        $phase['checks'] += [ordered]@{ id = 'capture'; label = "read-only boot capture on $Port"; verdict = $V_NOT_RUN; exit_code = $null; reason = 'pyserial not importable by the selected interpreter' }
        Set-PhaseOutcome $Key $V_NOT_RUN 'pyserial absent: capture degraded to NOT_RUN (enumeration above still ran)'
        $phase['operator_actions'] += @('Install pyserial for the interpreter, or pass -PythonExe pointing at one that has it.')
        return
    }

    Write-Log ('read-only capture on {0} @ {1} for {2}s (no byte is ever written)' -f $Port, $Baud, $Seconds)
    $capture = Invoke-ReadOnlyCapture -PhaseKey $Key -Label 'boot_identity'
    $result = $capture.result
    $summary = $capture.summary
    $zeroWrite = ($null -ne $summary -and [int]$summary.bytes_written -eq 0 -and [string]$summary.writes_to_port -eq 'NONE')
    $row = [ordered]@{
        id             = 'capture'
        label          = "read-only boot capture on $Port"
        command        = $result.command
        exit_code      = $result.exit_code
        log            = $capture.log
        summary_path   = $capture.summary_path
        bytes_written  = $(if ($null -ne $summary) { [int]$summary.bytes_written } else { $null })
        lines          = $(if ($null -ne $summary) { [int]$summary.lines } else { $null })
        telemetry_frames = $(if ($null -ne $summary) { [int]$summary.telemetry_frames } else { $null })
        identity       = [ordered]@{
            fw       = @(Get-JsonFieldValues $summary 'fw')
            hw       = @(Get-JsonFieldValues $summary 'hw')
            device   = @(Get-JsonFieldValues $summary 'device')
            firmware = @(Get-JsonFieldValues $summary 'firmware')
            boot_id  = @(Get-JsonFieldValues $summary 'boot_id')
            pin_map  = @(Get-JsonFieldValues $summary 'pin_map')
        }
        verdict        = $V_FAIL
        reason         = ''
    }
    switch ($result.exit_code) {
        0 { $row['verdict'] = $V_PASS; $row['reason'] = 'lines captured with zero bytes written' }
        1 { $row['verdict'] = $V_FAIL; $row['reason'] = 'port opened but the device emitted nothing (ZERO_LINES)' }
        2 { $row['verdict'] = $V_NOT_RUN; $row['reason'] = 'pyserial missing inside the capture tool' }
        3 { $row['verdict'] = $V_FAIL; $row['reason'] = 'PORT_ERROR: unexpected COM loss - the run aborts and nothing is retried' }
        default { $row['verdict'] = $V_FAIL; $row['reason'] = "capture tool exit $($result.exit_code)" }
    }
    if ($row['verdict'] -eq $V_PASS -and -not $zeroWrite) {
        $row['verdict'] = $V_FAIL
        $row['reason'] = 'capture summary does not prove zero writes to the port'
    }
    $phase['checks'] += $row
    $phase['artifacts'] += @($capture.log, $capture.summary_path)
    Write-Log ('  {0}: {1}' -f $row['verdict'], $row['reason'])

    if ($row['verdict'] -eq $V_PASS) {
        Set-PhaseOutcome $Key $V_PASS "enumerated and captured $Port read-only, bytes_written=0"
    }
    elseif ($row['verdict'] -eq $V_NOT_RUN) {
        Set-PhaseOutcome $Key $V_NOT_RUN $row['reason']
    }
    else {
        Set-PhaseOutcome $Key $V_FAIL $row['reason']
    }
}

# ---------------------------------------------------------------------------
# PHASE_C_BUILD
# ---------------------------------------------------------------------------
function Get-BuildOutputDir {
    param([string]$Project)
    foreach ($candidate in @((Join-Path $Project 'build'), (Join-Path $Project 'firmware\build'))) {
        if (Test-Path -LiteralPath (Join-Path $candidate 'coldguard_firmware.bin')) { return $candidate }
    }
    foreach ($candidate in @((Join-Path $Project 'build'), (Join-Path $Project 'firmware\build'))) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return ''
}

function Get-ArtifactHashes {
    param([string]$BuildOutput)
    $rel = @('bootloader\bootloader.bin', 'partition_table\partition-table.bin', 'coldguard_firmware.bin', 'coldguard_firmware.elf')
    $rows = @()
    foreach ($item in $rel) {
        $path = Join-Path $BuildOutput $item
        if (Test-Path -LiteralPath $path) {
            $hash = Get-FileHash -LiteralPath $path -Algorithm SHA256
            $size = (Get-Item -LiteralPath $path).Length
            $rows += [ordered]@{ artifact = $item; path = $path; sha256 = $hash.Hash.ToLowerInvariant(); size_bytes = $size }
        }
        else {
            $rows += [ordered]@{ artifact = $item; path = $path; sha256 = ''; size_bytes = $null; missing = $true }
        }
    }
    return @($rows)
}

function Invoke-PhaseC {
    $Key = 'C'
    Initialize-Phase $Key
    $phase = $script:Run['phases'][$Key]
    $phase['requested'] = $true
    Write-Section 'PHASE_C_BUILD'

    $profileMissing = -not (Test-Path -LiteralPath $IdfProfile)
    $projectMissing = -not (Test-Path -LiteralPath (Join-Path $BuildDir 'CMakeLists.txt'))
    if ($profileMissing -or $projectMissing) {
        $phase['gate_decision'] = $D_BLOCKED_DEPENDENCY
        $why = @()
        if ($profileMissing) { $why += "IDF PowerShell profile not found: $IdfProfile" }
        if ($projectMissing) { $why += "no CMakeLists.txt in -BuildDir $BuildDir (the short-path copy is staged by the coordinator, this script never creates it)" }
        Set-PhaseOutcome $Key $V_BLOCKED ($why -join '; ')
        $phase['notes'] += 'ESP-IDF and mbedtls fail on object paths longer than about 250 characters, so the firmware must be staged to a short path before it is built here.'
        return
    }
    if ($BuildDir.Length + 40 -gt 250) {
        Write-Log 'WARNING: -BuildDir is long; ESP-IDF object paths may exceed 250 characters and fail in mbedtls.'
        $phase['notes'] += 'BuildDir path depth is a known ESP-IDF/mbedtls failure mode: ' + $BuildDir
    }

    $buildRow = [ordered]@{ id = 'build'; label = 'ESP-IDF v6.1 build of the production firmware'; verdict = $V_PASS; exit_code = $null; reason = ''; command = ''; output_log = ''; mode = '' }
    $idfRecipe = ". '$IdfProfile'; Set-Location '$BuildDir'; idf.py set-target esp32s3; " +
        "if (`$LASTEXITCODE -ne 0) { Write-Output 'SETTARGET_FAILED'; exit 1 }; idf.py build; " +
        "if (`$LASTEXITCODE -ne 0) { Write-Output 'IDF_BUILD_FAILED'; exit 1 }; Write-Output 'IDF_BUILD_OK'"
    $psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $fullCommand = "& '{0}' -NoProfile -ExecutionPolicy Bypass -Command `"{1}`"" -f $psExe, ($idfRecipe -replace '"', '`"')

    if (-not $RunBuild.IsPresent) {
        # DRY-RUN is the default: the coordinator owns _rcbuild and may have a
        # build in flight, so this entrypoint prints the recipe instead of racing it.
        $buildRow['mode'] = 'DRY_RUN'
        $phase['gate_decision'] = 'DRY_RUN_DEFAULT'
        $buildRow['verdict'] = $V_NOT_RUN
        $buildRow['command'] = $fullCommand
        $buildRow['reason'] = 'PHASE_C is DRY-RUN by default; pass -RunBuild to actually invoke idf.py'
        Write-Log 'PHASE_C DRY-RUN: idf.py was NOT invoked and nothing was built.'
        Write-Log ('  exact command that -RunBuild would execute:')
        Write-Log ('    ' + $fullCommand)
        Write-Log ('  short-path staging requirement: ESP-IDF/mbedtls object paths exceed the ~250-character limit inside deep worktrees, so the source must be staged to a short path first. -BuildDir must already be that staged copy; this script never creates it.')
        $budget = if ($BuildDir.Length + 40 -gt 250) { 'EXCEEDS' } else { 'within' }
        Write-Log ('  -BuildDir = {0} ({1} chars; worst-case object path -BuildDir+~40 = {2} chars, {3} the 250-char ESP-IDF/mbedtls limit)' -f $BuildDir, $BuildDir.Length, ($BuildDir.Length + 40), $budget)
        $phase['notes'] += 'PHASE_C dry-run: command printed only. Pass -RunBuild to execute it.'
        $phase['operator_actions'] += @('Run -Phases A,C -RunBuild once the coordinator reports _rcbuild free, or hash a finished build with -Phases A,C -ArtifactsOnly -BuildDir <staged short path>.')
    }
    elseif ($ArtifactsOnly.IsPresent) {
        $buildRow['mode'] = 'ARTIFACTS_ONLY'
        $buildRow['verdict'] = $V_NOT_RUN
        $buildRow['reason'] = '-ArtifactsOnly passed: the build was not invoked, only existing artifacts were hashed'
        Write-Log 'skipping idf.py build (-ArtifactsOnly): hashing existing artifacts only'
    }
    else {
        # Markers and exit propagation, because powershell.exe -Command returns 0
        # even when idf.py failed. The recipe is the one that works on this box.
        $buildRow['mode'] = 'RUN_BUILD'
        $cmd = $idfRecipe
        $buildRow['command'] = $fullCommand
        Write-Log ('building in {0} (this is long; log streams to the run directory)' -f $BuildDir)
        $buildLog = Join-Path $script:Run['out_dir'] 'phaseC_idf_build.out.txt'
        $buildErr = Join-Path $script:Run['out_dir'] 'phaseC_idf_build.err.txt'
        $psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $proc = Start-Process -FilePath $psExe `
            -ArgumentList (Format-Arguments @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $cmd)) `
            -NoNewWindow -PassThru -Wait -RedirectStandardOutput $buildLog -RedirectStandardError $buildErr
        $code = if ($null -ne $proc.ExitCode) { $proc.ExitCode } else { -1 }
        $buildRow['exit_code'] = $code
        $buildRow['output_log'] = $buildLog
        $phase['artifacts'] += @($buildLog, $buildErr)
        $tail = @()
        if (Test-Path -LiteralPath $buildLog) { $tail = @(Get-PlainLines -Path $buildLog -MaxLines 30) }
        $buildRow['output_tail'] = $tail
        $completed = $false
        $markerOk = $false
        if (Test-Path -LiteralPath $buildLog) {
            $completed = [bool](Select-String -LiteralPath $buildLog -Pattern 'Project build complete' -Quiet -ErrorAction SilentlyContinue)
            $markerOk = [bool](Select-String -LiteralPath $buildLog -Pattern 'IDF_BUILD_OK' -Quiet -ErrorAction SilentlyContinue)
        }
        if ($code -eq 0 -and $completed -and $markerOk) {
            $buildRow['reason'] = 'idf.py build reported Project build complete and the IDF_BUILD_OK marker'
            $buildRow['verdict'] = $V_PASS
        }
        elseif ($code -eq 0) {
            $buildRow['verdict'] = $V_FAIL
            $buildRow['reason'] = 'idf.py exited 0 but the log lacks the build-complete markers'
        }
        else {
            $buildRow['verdict'] = $V_FAIL
            $buildRow['reason'] = "idf.py build exit $code (see $buildLog)"
        }
    }
    if ([string]::IsNullOrWhiteSpace($phase['gate_decision'])) { $phase['gate_decision'] = $D_EXECUTABLE }
    $phase['checks'] += $buildRow

    $buildOutput = Get-BuildOutputDir -Project $BuildDir
    if ([string]::IsNullOrWhiteSpace($buildOutput) -or -not (Test-Path -LiteralPath (Join-Path $buildOutput 'coldguard_firmware.bin'))) {
        if ($buildRow['verdict'] -eq $V_FAIL) { Set-PhaseOutcome $Key $V_FAIL $buildRow['reason']; return }
        # A dry-run has no reason to require an artifact: the absence is expected,
        # not a failure. Only a real -RunBuild that produced nothing is a FAIL.
        if ($buildRow['mode'] -ne 'RUN_BUILD') {
            $hashRow = [ordered]@{ id = 'hashes'; label = 'artifact hashes'; verdict = $V_NOT_RUN; reason = "no coldguard_firmware.bin under $BuildDir (looked in build\ and firmware\build\); expected in $($buildRow['mode']) mode" }
            $phase['checks'] += $hashRow
            Set-PhaseOutcome $Key $V_NOT_RUN "build NOT_RUN in $($buildRow['mode']) mode and no artifact to hash: pass -RunBuild to produce one"
            $phase['operator_actions'] += @('A pre-staged -BuildDir containing a completed build is required before hashes can be recorded.')
            return
        }
        Set-PhaseOutcome $Key $V_FAIL "no coldguard_firmware.bin under $BuildDir (looked in build\ and firmware\build\)"
        return
    }
    $hashes = Get-ArtifactHashes -BuildOutput $buildOutput
    $hashPath = Join-Path $script:Run['out_dir'] 'phaseC-artifact-hashes.json'
    Set-Content -LiteralPath $hashPath -Value (ConvertTo-Json ([ordered]@{ build_output_dir = $buildOutput; artifacts = $hashes; build_invoked = (-not $ArtifactsOnly.IsPresent) }) -Depth 8) -Encoding ASCII
    $phase['artifacts'] += $hashPath
    $fw = @($hashes | Where-Object { $_.artifact -eq 'coldguard_firmware.bin' })[0]
    foreach ($item in $hashes) {
        Write-Log ('  {0} size={1} sha256={2}' -f $item.artifact, $item.size_bytes, $item.sha256)
    }
    $hashRow = [ordered]@{ id = 'hashes'; label = 'artifact hashes'; verdict = $V_PASS; sha256_firmware = $fw.sha256; size_firmware = $fw.size_bytes; path = $hashPath }
    if (-not [string]::IsNullOrWhiteSpace($ExpectedFirmwareSha256)) {
        if ($fw.sha256 -eq $ExpectedFirmwareSha256.Trim().ToLowerInvariant()) {
            $hashRow['reason'] = 'matches -ExpectedFirmwareSha256'
        }
        else {
            $hashRow['verdict'] = $V_FAIL
            $hashRow['reason'] = "firmware hash $($fw.sha256) does not match -ExpectedFirmwareSha256"
        }
    }
    else {
        $hashRow['reason'] = 'no -ExpectedFirmwareSha256 supplied: hash recorded, not compared'
    }
    $phase['checks'] += $hashRow

    $flashArgsPath = Join-Path $buildOutput 'flash_args'
    if (Test-Path -LiteralPath $flashArgsPath) {
        $script:FlashArgs = @(Get-PlainLines -Path $flashArgsPath -MaxLineChars 200 | Where-Object { $_ -match '\S' })
        $phase['notes'] += ('flash_args offsets: ' + ($script:FlashArgs -join ' | '))
    }
    $script:BuildOutputDir = $buildOutput

    if ($buildRow['verdict'] -eq $V_FAIL -or $hashRow['verdict'] -eq $V_FAIL) {
        $reasons = @()
        foreach ($row in @($buildRow, $hashRow)) { if ($row['verdict'] -eq $V_FAIL) { $reasons += ('{0}: {1}' -f $row['id'], $row['reason']) } }
        Set-PhaseOutcome $Key $V_FAIL ($reasons -join '; ')
        return
    }
    if ($buildRow['verdict'] -eq $V_NOT_RUN) {
        Set-PhaseOutcome $Key $V_NOT_RUN ('build NOT_RUN in ' + $buildRow['mode'] + ' mode; hashes recorded for the pre-existing artifacts only')
        return
    }
    Set-PhaseOutcome $Key $V_PASS "idf.py build complete; firmware sha256 $($fw.sha256)"
}

# ---------------------------------------------------------------------------
# PHASE_D_FLASH
# ---------------------------------------------------------------------------
function Invoke-PhaseD {
    $Key = 'D'
    Initialize-Phase $Key
    $phase = $script:Run['phases'][$Key]
    $phase['requested'] = $true
    Write-Section 'PHASE_D_FLASH'

    $missing = @(Get-MissingGates $Key)
    $phase['gates_missing'] = $missing
    if ($missing.Count -gt 0) {
        $phase['gate_decision'] = $D_BLOCKED_OPERATOR
        $phase['operator_actions'] += @("Pass -AllowFlash and type the exact confirmation phrase: $LITERAL_FLASH")
        Set-PhaseOutcome $Key $V_BLOCKED ('gates not passed: -' + ($missing -join ' -'))
        return
    }

    $note = ''
    $phrase = Resolve-TypedPhrase -Supplied $ConfirmFlashPhrase `
        -PromptText ("Type {0} to confirm you checked the artifact hashes and the slot 3 status:" -f $LITERAL_FLASH) `
        -Note ([ref]$note)
    if (-not [string]::IsNullOrWhiteSpace($note)) { $phase['notes'] += $note }
    if ($phrase -ne $LITERAL_FLASH) {
        $phase['gate_decision'] = $D_BLOCKED_OPERATOR
        Set-PhaseOutcome $Key $V_BLOCKED "typed confirmation phrase did not match the required literal"
        $phase['operator_actions'] += @("Re-run with -ConfirmFlashPhrase `"$LITERAL_FLASH`"")
        return
    }
    $phase['gate_decision'] = $D_EXECUTABLE

    $buildOutput = ''
    if (-not [string]::IsNullOrWhiteSpace($script:BuildOutputDir)) { $buildOutput = $script:BuildOutputDir }
    else { $buildOutput = Get-BuildOutputDir -Project $BuildDir }
    $fwPath = Join-Path $buildOutput 'coldguard_firmware.bin'
    if ([string]::IsNullOrWhiteSpace($buildOutput) -or -not (Test-Path -LiteralPath $fwPath)) {
        $phase['gate_decision'] = $D_BLOCKED_DEPENDENCY
        Set-PhaseOutcome $Key $V_BLOCKED "no built artifact at ${fwPath}: run PHASE_C first (-Phases A,C,D)"
        return
    }

    $fw = Get-FileHash -LiteralPath $fwPath -Algorithm SHA256
    $fwSize = (Get-Item -LiteralPath $fwPath).Length
    $backupPath = Join-Path $script:Run['out_dir'] 'recovered-app-before-flash.bin'
    $appOffset = '0x10000'
    $appReadLen = '0x40000'
    $runner = Get-EsptoolRunner
    $portText = if ([string]::IsNullOrWhiteSpace($Port)) { 'COMx' } else { $Port }

    # Built once and reused verbatim, so the sheet the operator reads is the
    # same string the script would execute.
    $backupCmd = @('-m', 'esptool', '--chip', 'esp32s3', '-p', $portText, '-b', '460800', '--before', 'default-reset', '--after', 'no-reset', 'read-flash', $appOffset, $appReadLen, $backupPath)
    $flashCmd = @('-m', 'esptool', '--chip', 'esp32s3', '-p', $portText, '-b', '460800', '--before', 'default-reset', '--after', 'hard-reset', 'write-flash', '@flash_args')
    $verifyCmd = @('-m', 'esptool', '--chip', 'esp32s3', '-p', $portText, '-b', '460800', 'verify', '--flash-mode', 'dio', '--flash-size', '2MB', '--flash-freq', '80m', $appOffset, $fwPath)
    $rollbackCmd = @('-m', 'esptool', '--chip', 'esp32s3', '-p', $portText, '-b', '460800', 'write-flash', $appOffset, $backupPath)
    $show = { param($a) ("& '{0}' {1}" -f $runner.exe, ((@($runner.prefix) + @($a)) -join ' ')) }

    $lines = @(
        '# PHASE_D_FLASH - operator action sheet',
        '',
        "firmware artifact : $fwPath",
        "sha256            : $($fw.Hash.ToLowerInvariant())",
        "size              : $fwSize bytes",
        "flash offsets     : " + (($script:FlashArgs | ForEach-Object { $_ }) -join ' | '),
        '',
        '## Recovery path, run FIRST (flash backup of what is installed now)',
        ('  ' + (& $show $backupCmd)),
        "  working directory : $buildOutput",
        '  the app partition starts at 0x10000 (single-app table at 0x8000; evidence/A/W04/h6/02-identity-backup.md)',
        '',
        '## Flash command (the only thing that writes the device)',
        ('  ' + (& $show $flashCmd)),
        '  run it with the working directory above so esptool resolves @flash_args',
        '',
        '## Verify after flash',
        ('  ' + (& $show $verifyCmd)),
        '',
        '## Rollback',
        ('  ' + (& $show $rollbackCmd)),
        '',
        '## Hard rules for this phase',
        '- A flash fails the run on the first error: no retry, and no retry after an unexpected COM loss.',
        '- The backup read must succeed before anything is written.',
        '- Fuse slot 3 status must be known and recorded before the box is powered again.',
        '- This script never reinserts a fuse and never toggles a power supply.'
    )
    $sheet = Write-OperatorSheet $Key $lines
    $phase['operator_actions'] = $lines
    $planRow = [ordered]@{
        id              = 'plan'
        label           = 'flash plan + recovery path produced (dry-run)'
        verdict         = $V_PASS
        sheet           = $sheet
        firmware_sha256 = $fw.Hash.ToLowerInvariant()
        firmware_size   = $fwSize
        backup_read_cmd = (& $show $backupCmd)
        flash_cmd       = (& $show $flashCmd)
        verify_cmd      = (& $show $verifyCmd)
        rollback_cmd    = (& $show $rollbackCmd)
    }
    $phase['checks'] += $planRow
    $phase['artifacts'] += $sheet
    Write-Log 'dry-run: command and recovery path produced, nothing written to any device'

    if (-not $ExecuteFlash.IsPresent) {
        Set-PhaseOutcome $Key $V_BLOCKED 'dry-run only by design: -ExecuteFlash was not passed, so no esptool command ran'
        return
    }
    if ([string]::IsNullOrWhiteSpace($Port)) {
        Set-PhaseOutcome $Key $V_BLOCKED '-ExecuteFlash needs -Port COMx; nothing ran'
        return
    }

    Write-Log 'EXECUTE FLASH: step 1 is the backup read; a failure here aborts before any write'
    $backup = Invoke-LoggedCommand -Label 'phaseD_backup_read' -FilePath $runner.exe `
        -Arguments (@($runner.prefix) + $backupCmd) -WorkingDirectory $PSScriptRoot
    $backupRow = [ordered]@{ id = 'backup'; label = 'read current app bin'; command = $backup.command; exit_code = $backup.exit_code; path = $backupPath }
    if ($backup.exit_code -ne 0 -or -not (Test-Path -LiteralPath $backupPath)) {
        $backupRow['verdict'] = $V_FAIL
        $backupRow['reason'] = 'backup read failed: aborting, no write-flash attempted'
        $phase['checks'] += $backupRow
        Set-PhaseOutcome $Key $V_FAIL 'backup read failed before flashing - abort, no retry'
        return
    }
    $backupRow['verdict'] = $V_PASS
    $backupRow['reason'] = 'app bin recovered before any write'
    $phase['checks'] += $backupRow
    $phase['artifacts'] += $backupPath

    $flash = Invoke-LoggedCommand -Label 'phaseD_write_flash' -FilePath $runner.exe `
        -Arguments (@($runner.prefix) + $flashCmd) -WorkingDirectory $buildOutput
    $flashRow = [ordered]@{ id = 'flash'; label = 'esptool write-flash from flash_args'; command = $flash.command; exit_code = $flash.exit_code; output_tail = $flash.tail }
    $joined = ($flash.tail -join "`n")
    if ($flash.exit_code -eq 0 -and $joined -match 'Hash of data verified') {
        $flashRow['verdict'] = $V_PASS
        $flashRow['reason'] = 'write complete and hash verified'
        Set-PhaseOutcome $Key $V_PASS ('flashed and verified; backup kept at ' + $backupPath)
    }
    else {
        $flashRow['verdict'] = $V_FAIL
        $flashRow['reason'] = "esptool exit $($flash.exit_code) or no hash verification line - abort, no retry, restore with the rollback command"
        Set-PhaseOutcome $Key $V_FAIL $flashRow['reason']
    }
    $phase['checks'] += $flashRow
    $phase['artifacts'] += @($backup.stdout_log, $flash.stdout_log)
}

# ---------------------------------------------------------------------------
# PHASE_E_SAFETY_OFF
# ---------------------------------------------------------------------------
function Invoke-PhaseE {
    $Key = 'E'
    Initialize-Phase $Key
    $phase = $script:Run['phases'][$Key]
    $phase['requested'] = $true
    Write-Section 'PHASE_E_SAFETY_OFF'

    $missing = @(Get-MissingGates $Key)
    $phase['gates_missing'] = $missing
    Write-Log 'preconditions (each needs its own acknowledgement switch):'
    for ($i = 0; $i -lt $PhaseEPreconditions.Count; $i++) {
        Write-Log ('  P{0}. {1}' -f ($i + 1), $PhaseEPreconditions[$i])
    }
    if ($missing.Count -gt 0) {
        $phase['gate_decision'] = $D_BLOCKED_OPERATOR
        $phase['operator_actions'] += @('-AllowEnergize -AckSlot3Removed -AckPsu12VPresent -AckTecBranchOpen -AckOperatorAtBox -AckNoSoftwarePowerActions')
        Set-PhaseOutcome $Key $V_BLOCKED ('missing acknowledgement(s): -' + ($missing -join ' -'))
        return
    }
    if ([string]::IsNullOrWhiteSpace($Port) -or -not $script:Run['pyserial'].available) {
        $phase['gate_decision'] = $D_BLOCKED_DEPENDENCY
        $why = if ([string]::IsNullOrWhiteSpace($Port)) { '-Port COMx is required to observe anything' } else { 'pyserial is not importable by the selected interpreter' }
        Set-PhaseOutcome $Key $V_BLOCKED $why
        return
    }
    if (-not $AllowSerialProbe.IsPresent) {
        $phase['gate_decision'] = $D_BLOCKED_OPERATOR
        Set-PhaseOutcome $Key $V_BLOCKED 'PHASE_E observes through the port, so it also needs -AllowSerialProbe'
        return
    }
    $phase['gate_decision'] = $D_EXECUTABLE
    $capture = Invoke-ReadOnlyCapture -PhaseKey $Key -Label 'safety_off_12v'
    $summary = $capture.summary
    $result = $capture.result
    $phase['artifacts'] += @($capture.log, $capture.summary_path)

    $states = @(Get-JsonFieldValues $summary 'state')
    $applied = @(Get-JsonFieldValues $summary 'pwm_applied_permille')
    $requested = @(Get-JsonFieldValues $summary 'pwm_req_permille')
    $ren = @(Get-JsonFieldValues $summary 'ren_command')
    $len = @(Get-JsonFieldValues $summary 'len_command')

    $row = [ordered]@{
        id               = 'safety_off_observation'
        label            = '12 V present, TEC branch isolated: duty must stay at zero'
        exit_code        = $result.exit_code
        telemetry_frames = $(if ($null -ne $summary) { [int]$summary.telemetry_frames } else { $null })
        bytes_written    = $(if ($null -ne $summary) { [int]$summary.bytes_written } else { $null })
        observed_state   = $states
        observed_pwm_applied = $applied
        observed_pwm_req = $requested
        observed_ren_command = $ren
        observed_len_command = $len
        observed_current_a = @(Get-JsonFieldValues $summary 'current_a')
        observed_voltage_v = @(Get-JsonFieldValues $summary 'voltage_v')
        verdict          = $V_FAIL
        reason           = ''
    }

    if ($result.exit_code -eq 3) {
        $row['verdict'] = $V_FAIL
        $row['reason'] = 'PORT_ERROR during the energised observation: unexpected COM loss, abort with no retry'
    }
    elseif ($result.exit_code -eq 2) {
        $row['verdict'] = $V_NOT_RUN
        $row['reason'] = 'pyserial missing inside the capture tool'
    }
    elseif ($result.exit_code -eq 1) {
        $row['verdict'] = $V_FAIL
        $row['reason'] = 'no lines while 12 V was present: the box is not reporting, do not proceed to any actuation'
    }
    else {
        $coolingApplied = @(Get-JsonFieldValues $summary 'cooling_applied')
        $badStates = @($states | Where-Object { $ALLOWED_IDLE_STATES -notcontains $_ })
        $dutyOk = (Test-AllZero $applied)
        $renOk = (Test-AllZero $ren)
        $lenOk = (Test-AllZero $len)
        $zeroWrite = ([int]$row['bytes_written'] -eq 0)
        if ($badStates.Count -gt 0) {
            $row['reason'] = 'non-idle state observed with the TEC branch supposed to be isolated: ' + ($badStates -join ',')
        }
        elseif ($coolingApplied.Count -gt 0 -and @($coolingApplied | Where-Object { $_ -ne 'OFF' }).Count -eq 0) {
            # Schema-3 evidence: the firmware reports its real applied state and
            # every frame says cooling_applied=OFF with zero bytes written.
            $row['verdict'] = $V_PASS
            $row['reason'] = ('{0} telemetry frames with state={1}, cooling_applied=OFF (schema-3 applied state), bytes_written=0' -f $row['telemetry_frames'], ($states -join '/'))
        }
        elseif (-not $dutyOk) { $row['reason'] = 'pwm_applied_permille not zero: ' + ($applied -join ',') }
        elseif (-not $renOk) { $row['reason'] = 'ren_command not zero: ' + ($ren -join ',') }
        elseif (-not $lenOk) { $row['reason'] = 'len_command not zero: ' + ($len -join ',') }
        elseif (-not $zeroWrite) { $row['reason'] = 'capture did not prove zero bytes written' }
        elseif ([int]$row['telemetry_frames'] -lt 1) { $row['reason'] = 'no telemetry frame parsed, so duty-zero is unproven' }
        else {
            # Legacy-only evidence path: everything checked is zero, but neither
            # the legacy pwm keys nor schema-3 cooling_applied were present, so
            # the applied state is UNPROVEN - never PASS from empty arrays.
            $row['verdict'] = $V_NOT_RUN
            $row['reason'] = 'UNPROVEN: no schema-3 cooling_applied and no legacy pwm_applied_permille observations in this capture'
        }
    }
    $phase['checks'] += $row
    $phase['operator_actions'] += @('Physically confirm slot 3 empty before and after this phase; the script cannot and will not look at the fuse box.')
    if ($row['verdict'] -eq $V_PASS) { Set-PhaseOutcome $Key $V_PASS $row['reason'] }
    elseif ($row['verdict'] -eq $V_NOT_RUN) { Set-PhaseOutcome $Key $V_NOT_RUN $row['reason'] }
    else { Set-PhaseOutcome $Key $V_FAIL $row['reason'] }
}

# ---------------------------------------------------------------------------
# PHASE_F_TEC_ACTUATION
# ---------------------------------------------------------------------------
function Invoke-PhaseF {
    $Key = 'F'
    Initialize-Phase $Key
    $phase = $script:Run['phases'][$Key]
    $phase['requested'] = $true
    Write-Section 'PHASE_F_TEC_ACTUATION'

    $missing = @(Get-MissingGates $Key)
    $phase['gates_missing'] = $missing
    if ($missing.Count -gt 0) {
        $phase['gate_decision'] = $D_BLOCKED_OPERATOR
        Set-PhaseOutcome $Key $V_BLOCKED ('missing gate(s): -' + ($missing -join ' -'))
        $phase['operator_actions'] += @(
            "-AllowTecActuation -OperatorSupervised -AckSlot3Status `"<what you see in slot 3>`" -ConfirmTecPhrase `"$LITERAL_TEC`"",
            'Without an interactive console the confirmation phrase must be passed as a parameter: an unattended run is never treated as supervision.'
        )
        return
    }

    $status = $AckSlot3Status.Trim()
    if ($status -match 'unknown|tbd|n/?a|not[_ -]?checked|placeholder') {
        $phase['gate_decision'] = $D_BLOCKED_OPERATOR
        Set-PhaseOutcome $Key $V_BLOCKED "slot 3 status was not actually acknowledged (said '$status'): a TEC run with the fuse out reads CURRENT_ZERO_WHILE_COOLING"
        return
    }
    $removed = ($status -match 'removed|empty|out|absent|pull')
    if ($removed) {
        $phase['gate_decision'] = $D_BLOCKED_OPERATOR
        Set-PhaseOutcome $Key $V_BLOCKED "slot 3 acknowledged as '$status': the script does not reinsert fuses, so no cooling run is possible"
        $phase['operator_actions'] += @('The operator selects and installs the branch fuse himself (A-W04-03 is not frozen), then re-acknowledges the status.')
        return
    }

    $phrase = $ConfirmTecPhrase
    if ([string]::IsNullOrWhiteSpace($phrase)) {
        $note = ''
        $phrase = (Resolve-TypedPhrase -Supplied $phrase -PromptText ("Type {0} to confirm you are physically present at the box, or press Enter to decline:" -f $LITERAL_TEC) -Note ([ref]$note))
        if (-not [string]::IsNullOrWhiteSpace($note)) { $phase['notes'] += $note }
    }
    if ($phrase.Trim() -ne $LITERAL_TEC) {
        $phase['gate_decision'] = $D_BLOCKED_OPERATOR
        Set-PhaseOutcome $Key $V_BLOCKED 'operator supervision was not confirmed with the exact phrase'
        return
    }

    $slot3Check = [ordered]@{ id = 'slot3'; label = 'slot 3 status acknowledged by the operator'; verdict = $V_PASS; acknowledged_state = $status; fuse_handling = 'physical operator action only; this script never reinserts a fuse' }
    $phase['checks'] += $slot3Check

    $lines = @(
        '# PHASE_F_TEC_ACTUATION - operator action sheet',
        '',
        "slot 3 as acknowledged by the operator : $status",
        'risk class                            : POWERED_ACTUATION',
        'this script sends nothing             : the console commands below are typed by the operator, on his own authorization',
        '',
        '## Prerequisites in order',
        '1. PHASE_C artifact hash recorded and PHASE_D flashed, and the installed image byte-verified (esptool read-flash 0x10000 compared to the built coldguard_firmware.bin).',
        '2. PHASE_E passed with fuse slot 3 out: state OFF and duty zero.',
        '3. Branch fuse selected, installed and photographed by the operator; PHY-FUSE-001 (docs/01 s16.4) forbids a powered TEC test that bypasses the branch fuse.',
        '4. Boot token read from the boot line (the ARM token is printed at boot; it is never guessed).',
        '',
        '## Operator console sequence (typed by the operator, one boot, one run)',
        '  SUPERVISE <token>',
        '  STAGE',
        "  ARM <8-hex boot token>",
        '  START <seconds>',
        '  read REPORT before the port closes',
        '  STOP on any abort',
        '',
        '## Abort conditions',
        '- stop on smoke, smell, unexpected heat, fan failure, PSU instability, IBT-2 protection cycling or hot-side runaway',
        '- current stays zero while cooling is commanded: stop immediately, do not wait out the stage',
        '- T2 reaching the provisional 55 C stop threshold, or any latched fault',
        '- on any fault preserve the latch and the logs, do NOT CLEAR and do NOT retry: a new run needs a new explicit authorization',
        '',
        '## Why this phase cannot PASS here',
        'The acceptance entrypoint has no capability to energise or actuate, so it produces this sheet and stops. That is structural, not a behavioural promise.',
        'Evidence for A-W04-06 / H6 direction and magnitude is produced by the operator session and must be recorded by the W06 dossier validator.'
    )
    $sheet = Write-OperatorSheet $Key $lines
    $phase['operator_actions'] = $lines
    $phase['artifacts'] += $sheet
    $phase['checks'] += [ordered]@{ id = 'sheet'; label = 'operator action sheet written'; verdict = $V_PASS; path = $sheet; forbidden_tokens_never_sent = $FORBIDDEN_TOKENS }

    Set-PhaseOutcome $Key $V_BLOCKED 'all gates passed, sheet written; the script sends no actuator command so only the operator session can complete this phase'
}

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
function Get-PlanRows {
    $rows = @()
    foreach ($key in $PhaseSpec.Keys) {
        $missing = @(Get-MissingGates $key)
        $decision = $D_BLOCKED_OPERATOR
        if ($missing.Count -eq 0) { $decision = $D_EXECUTABLE }
        if ($key -eq 'C' -or $key -eq 'D') {
            if (-not (Test-Path -LiteralPath $IdfProfile) -or -not (Test-Path -LiteralPath (Join-Path $BuildDir 'CMakeLists.txt'))) { $decision = $D_BLOCKED_DEPENDENCY }
        }
        $rows += [ordered]@{
            phase     = $PhaseSpec[$key].Name
            risk      = $PhaseSpec[$key].Risk
            requested = ($PhasesToRun -contains $key)
            decision  = $decision
            missing   = @($missing)
        }
    }
    return @($rows)
}

function Invoke-AcceptancePlan {
    Write-Section 'PLAN (no phase executed)'
    $rows = Get-PlanRows
    foreach ($row in $rows) {
        Write-Log ('{0,-26} risk={1,-18} requested={2,-5} decision={3,-24} blocked_by={4}' -f `
            $row.phase, $row.risk, $row.requested, $row.decision, (@($row.missing) -join ','))
    }
    foreach ($key in @('A', 'B', 'C', 'D', 'E', 'F')) {
        if ($script:PhasesToRun -notcontains $key) { continue }
        $planRow = @($rows | Where-Object { $_.phase -eq $PhaseSpec[$key].Name })[0]
        $script:Run['phases'][$key]['gate_decision'] = $planRow.decision
        $script:Run['phases'][$key]['gates_missing'] = @($planRow.missing)
        $script:Run['phases'][$key]['reason'] = 'plan only; nothing executed'
    }
    Write-Log 'PLAN writes nothing and opens nothing; exit 0.'
}

function Complete-Run {
    param([int]$ExitCode, [string]$Meaning)
    $script:Run['exit_code'] = $ExitCode
    $script:Run['exit_meaning'] = $Meaning
    $orderedPhases = @()
    foreach ($key in $script:Run['phases'].Keys) { $orderedPhases += $script:Run['phases'][$key] }
    $script:Run['phases'] = $orderedPhases

    $jsonPath = Join-Path $script:Run['out_dir'] 'member-a-acceptance.json'
    $verdictTable = @()
    foreach ($p in $script:Run['phases']) {
        $verdictTable += [ordered]@{ phase = $p['name']; risk = $p['risk']; requested = $p['requested']; decision = $p['gate_decision']; verdict = $p['verdict']; reason = $p['reason'] }
    }
    $summaryFallback = (ConvertTo-Json ([ordered]@{
        schema = 'coldguard.member-a-acceptance.v1'; generated_utc = $script:Run['generated_utc']
        overall = $script:Run['overall']; exit_code = $ExitCode; exit_meaning = $Meaning
        verbose = 'BLOCKED_SOFTWARE'; reason = 'full document exceeded the JSON size budget'
        verdicts = $verdictTable
    }) -Depth 3)
    Set-Content -LiteralPath $jsonPath -Value (ConvertTo-JsonBounded $script:Run -Depth 8 -MaxChars 3000000 -FallbackDocument $summaryFallback) -Encoding ASCII
    $script:Run['summary_json'] = [ordered]@{ verdicts = $verdictTable; overall = $script:Run['overall']; exit_code = $ExitCode }

    $summaryLines = @()
    $summaryLines += '# Member A release candidate acceptance - ' + $script:Run['generated_utc']
    $summaryLines += ''
    $summaryLines += 'repo: ' + $script:Run['repo_root']
    $summaryLines += 'python: ' + $script:Run['python'] + '   pyserial: ' + $(if ($script:Run['pyserial'].available) { $script:Run['pyserial'].version } else { 'NOT INSTALLED' })
    $summaryLines += 'requested phases: ' + ($script:Run['requested'] -join ',')
    $summaryLines += ''
    $summaryLines += '| Phase | Risk | Decision | Verdict | Reason |'
    $summaryLines += '|---|---|---|---|---|'
    foreach ($phase in $script:Run['phases']) {
        $summaryLines += ('| {0} | {1} | {2} | {3} | {4} |' -f $phase['name'], $phase['risk'], $phase['gate_decision'], $phase['verdict'], $phase['reason'])
    }
    $summaryLines += ''
    $summaryLines += '## Safety rules encoded in this entrypoint'
    foreach ($rule in $SafetyRules) { $summaryLines += ('- ' + $rule) }
    $summaryLines += ''
    foreach ($phase in $script:Run['phases']) {
        if (@($phase['operator_actions']).Count -eq 0) { continue }
        $summaryLines += ('## ' + $phase['name'] + ' operator actions')
        foreach ($action in $phase['operator_actions']) { $summaryLines += ('- ' + $action) }
        $summaryLines += ''
    }
    $summaryLines += ('exit code: {0} - {1}' -f $ExitCode, $Meaning)
    $summaryLines += ('machine-readable result: ' + $jsonPath)
    $mdPath = Join-Path $script:Run['out_dir'] 'member-a-acceptance.md'
    Set-Content -LiteralPath $mdPath -Value ($summaryLines -join "`r`n") -Encoding ASCII
    Set-Content -LiteralPath (Join-Path $script:Run['out_dir'] 'console-transcript.txt') -Value ($script:Transcript -join "`r`n") -Encoding ASCII
    Write-Log ''
    Write-Log ('SUMMARY md   = {0}' -f $mdPath)
    Write-Log ('SUMMARY json = {0}' -f $jsonPath)
    Write-Log ''
    foreach ($phase in $script:Run['phases']) {
        Write-Log ('FINAL {0} verdict={1} decision={2}' -f $phase['name'], $phase['verdict'], $phase['gate_decision'])
        Write-Log ('      reason={0}' -f $phase['reason'])
    }
    Write-Log ('OVERALL: ' + $script:Run['overall'] + ' exit=' + $ExitCode + ' (' + $Meaning + ')')
    return $ExitCode
}

function Main {
    if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
        $RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    }
    if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot 'firmware\tools'))) {
        Write-Host "RepoRoot $RepoRoot has no firmware\tools: this script must run from a Member A worktree."
        return 3
    }
    $script:Run['repo_root'] = (Get-Item -LiteralPath $RepoRoot).FullName
    $script:Run['generated_utc'] = [datetime]::UtcNow.ToString("yyyyMMdd'T'HHmmss'Z'")
    if ([string]::IsNullOrWhiteSpace($OutDir)) { $OutDir = Join-Path $PSScriptRoot 'output' }
    $script:Run['out_dir'] = Join-Path $OutDir $script:Run['generated_utc']
    New-Item -ItemType Directory -Force -Path $script:Run['out_dir'] | Out-Null
    Write-Log ('run directory: {0}' -f $script:Run['out_dir'])

    $script:PythonRuntime = Resolve-PythonRuntime
    $script:Run['python'] = ('{0} {1}' -f $script:PythonRuntime['exe'], (@($script:PythonRuntime['prefix']) -join ' ')).Trim()
    $script:Run['python_exe'] = $script:PythonRuntime['exe']
    $script:Run['pyserial'] = Test-PySerialAvailable -Label $script:Run['python']
    Write-Log ('python={0} pyserial_available={1} version={2}' -f $script:Run['python'], $script:Run['pyserial'].available, $script:Run['pyserial'].version)

    $script:PhasesToRun = @('A', 'B', 'C', 'D', 'E', 'F')
    if ($AllPhases.IsPresent) { $script:PhasesToRun = @('A', 'B', 'C', 'D', 'E', 'F') }
    else {
        if ($Phases.Count -gt 0) { $script:PhasesToRun = @($Phases | Sort-Object -Unique) }
    }
    $script:Run['requested'] = @($script:PhasesToRun)

    if ($Plan.IsPresent) {
        foreach ($key in $script:PhasesToRun) { Initialize-Phase $key }
        Invoke-AcceptancePlan
        $script:Run['overall'] = 'PLAN ONLY (no phase executed)'
        return (Complete-Run 0 'plan only; nothing executed')
    }

    $abort = ''
    $runners = @{
        'A' = { Invoke-PhaseA }
        'B' = { Invoke-PhaseB }
        'C' = { Invoke-PhaseC }
        'D' = { Invoke-PhaseD }
        'E' = { Invoke-PhaseE }
        'F' = { Invoke-PhaseF }
    }
    foreach ($key in @('A', 'B', 'C', 'D', 'E', 'F')) {
        if ($script:PhasesToRun -notcontains $key) {
            # Every phase is accounted for in the verdict table, even the ones
            # this invocation did not ask for, so a default run still shows B..F
            # with the exact reason and the gates that would unblock them.
            Initialize-Phase $key
            $p = $script:Run['phases'][$key]
            $missing = @(Get-MissingGates $key)
            if ($missing.Count -gt 0) {
                $p['gate_decision'] = $D_BLOCKED_OPERATOR
                $p['gates_missing'] = $missing
                Set-PhaseOutcome $key $V_BLOCKED ('not requested on this run and gated: needs -Phases to include ' + $key + ' plus -' + ($missing -join ' -'))
            }
            else {
                $p['gate_decision'] = 'NOT_REQUESTED'
                Set-PhaseOutcome $key $V_NOT_RUN ('not requested on this run: add ' + $key + ' to -Phases to execute it (no hardware action was taken for it)')
            }
            continue
        }
        if ($abort -ne '') {
            Initialize-Phase $key
            $script:Run['phases'][$key]['gate_decision'] = 'ABORTED_BEFORE_RUN'
            Set-PhaseOutcome $key $V_NOT_RUN ('aborted before this phase: ' + $abort)
            continue
        }
        try {
            & $runners[$key]
        }
        catch {
            Set-PhaseOutcome $key $V_FAIL ('unhandled script error: ' + $_.Exception.Message)
        }
        if ($script:Run['phases'][$key]['verdict'] -eq $V_FAIL) {
            $abort = ('{0} FAILED' -f $PhaseSpec[$key].Name)
            $script:Run['abort_reason'] = $abort
            Write-Log ("ABORT: $abort - later phases are recorded NOT_RUN, nothing is retried")
        }
    }

    $phases = @($script:Run['phases'].Values)
    $verdicts = @($phases | ForEach-Object { $_['verdict'] })
    $failed = @($verdicts | Where-Object { $_ -eq $V_FAIL }).Count
    $blocked = @($verdicts | Where-Object { $_ -eq $V_BLOCKED -or $_ -eq $V_NOT_RUN }).Count
    $passed = @($verdicts | Where-Object { $_ -eq $V_PASS }).Count

    $exit = 0
    $meaning = 'every requested phase PASSED'
    $overall = $V_PASS
    if ($failed -gt 0) {
        $overall = $V_FAIL
        $exit = 1
        $meaning = "$failed phase(s) FAILED"
    }
    elseif ($blocked -gt 0) {
        $overall = 'INCOMPLETE'
        $exit = 2
        $meaning = "$blocked phase(s) NOT_RUN or BLOCKED_NEEDS_OPERATOR / BLOCKED_DEPENDENCY; no failure"
    }
    $script:Run['overall'] = ('{0} (passed={1} blocked_or_not_run={2} failed={3})' -f $overall, $passed, $blocked, $failed)
    return (Complete-Run $exit $meaning)
}

$result = Main
if ($result -is [array]) { $result = $result[-1] }
if ($null -eq $result) { $result = 3 }
exit ([int]$result)
