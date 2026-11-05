<#
.SYNOPSIS
    Render the CG-HW-001 cooling-branch power topology as a block diagram.

.DESCRIPTION
    The picture is generated from the node and edge lists below; every link
    carries the evidence class the repository actually holds for it
    (PHOTO_VERIFIED / OPERATOR_CONFIRMED / INFERRED / UNVERIFIED). Unverified
    links are drawn dashed and labelled instead of being omitted, so the diagram
    cannot read as more confirmed than the dossier is.

    Sources: evidence/A/W01/bom-audit.csv, evidence/A/W01/photos/,
    evidence/A/as-built-pinmap-2026-10-27.md, evidence/A/W04/g0-electrical-verification.md,
    evidence/A/W04/fuse-commissioning-note.md, firmware/main/coldguard_config.h.

    Edit the lists below and re-run; do not edit the PNG.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File `
      evidence\A\W04\tools\render_power_topology.ps1 -Png evidence\A\W04\power-topology-v1.png
#>
param(
    [string]$Png = "evidence/A/W04/power-topology-v1.png",
    [int]$Width = 1500,
    [int]$Height = 1010
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

if (-not [System.IO.Path]::IsPathRooted($Png)) { $Png = Join-Path (Get-Location) $Png }
$Png = [System.IO.Path]::GetFullPath($Png)
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Png) | Out-Null

# --- nodes: id, box, title, detail lines, evidence class -------------------
$nodes = @(
    @{ id='AC';    x=40;   y=70;  w=200; h=86;  title='AC mains';                  lines=@('wall inlet, operator switched');                 ev='PHOTO_VERIFIED' }
    @{ id='PSU';   x=300;  y=70;  w=250; h=86;  title='PSU 12 V / 400 W / 33.3 A'; lines=@('label photographed','11.95 V idle measured');      ev='PHOTO_VERIFIED' }
    @{ id='FUSE3'; x=610;  y=70;  w=250; h=86;  title='Fuse box slot 3';           lines=@('15 A installed (operator)','no readable marking'); ev='OPERATOR_CONFIRMED' }
    @{ id='IBT';   x=920;  y=70;  w=250; h=86;  title='IBT-2  BTS7960B';           lines=@('module photographed','B+ / B- / M+ / M-');         ev='PHOTO_VERIFIED' }
    @{ id='TEC';   x=1230; y=70;  w=230; h=86;  title='TEC1-12715';                lines=@('marking photographed','cold face inside box');      ev='OPERATOR_CONFIRMED' }
    @{ id='XL';    x=40;   y=250; w=250; h=86;  title='XL4015 5 V logic rail';     lines=@('chip marking unreadable','fed from slot 1 = 5 A');  ev='OPERATOR_CONFIRMED' }
    @{ id='SHUNT'; x=920;  y=250; w=250; h=86;  title='PZEM-017 shunt';            lines=@('50 A / 75 mV, in the return','position user-reported'); ev='OPERATOR_CONFIRMED' }
    @{ id='FAN';   x=1230; y=250; w=230; h=86;  title='V1 fan 12 V 0.20 A';        lines=@('label photographed','own branch, slot 4 = 1 A');   ev='OPERATOR_CONFIRMED' }
    @{ id='ESP';   x=40;   y=430; w=330; h=160; title='ESP32-S3R2 (MAKDRIVERONE)'; lines=@('RPWM GPIO5, R_EN GPIO6, L_EN GPIO10','LPWM tied to GND at the module','RS-485 TX GPIO36 / RX GPIO37','1-Wire GPIO33, BME280 GPIO21/34','door MC-38 GPIO35'); ev='PHOTO_VERIFIED' }
    @{ id='RS485'; x=470;  y=430; w=290; h=120; title='TTL485-V2.0 auto-direction'; lines=@('5 V module, no DE/RE pin','canonical part was MAX3485','deviation CR-A-W01-01 still open'); ev='PHOTO_VERIFIED' }
    @{ id='PZEMM'; x=830;  y=430; w=290; h=120; title='PZEM-017 meter';            lines=@('slave 1, 9600 8N1','read-only, no write path in firmware'); ev='PHOTO_VERIFIED' }
    @{ id='BUS';   x=470;  y=620; w=650; h=104; title='1-Wire bus GPIO33 - 4 DS18B20'; lines=@('T1 287088CA inside-box air (operator)','T3 28CBE9CA inside-box air (operator)','SPARE 283BE5C9 inside-box air (operator)','T2 28AEBF22 on the hot block (operator + device t2_role=HOT_SIDE)'); ev='OPERATOR_CONFIRMED' }
)

# --- edges: from, to, explicit exit/entry sides, waypoints, label, label pos -
# Sides are explicit because auto-routing produced diagonals that crossed boxes.
$edges = @(
    @{ a='AC';    b='PSU';   from='right'; to='left';   via=@();                                   label='mains in';       lx=243; ly=96;  ev='PHOTO_VERIFIED' }
    @{ a='PSU';   b='FUSE3'; from='right'; to='left';   via=@();                                   label='+12 V';          lx=553; ly=96;  ev='OPERATOR_CONFIRMED' }
    @{ a='FUSE3'; b='IBT';   from='right'; to='left';   via=@();                                   label='B+ open'; lx=868; ly=96; ev='UNVERIFIED' }
    @{ a='IBT';   b='TEC';   from='right'; to='left';   via=@();                                   label='M+ / M-';        lx=1173; ly=96; ev='OPERATOR_CONFIRMED' }
    @{ a='IBT';   b='SHUNT'; from='bottom'; to='top';   via=@();                                   label='B- return';      lx=1050; ly=196; ev='OPERATOR_CONFIRMED' }
    @{ a='SHUNT'; b='PSU';   from='left';  to='bottom'; via=@('880,205', '425,205');                   label='to PSU- through the shunt - no parallel logic-GND bridge (INFERRED, G0 item)'; lx=440; ly=186; ev='INFERRED' }
    @{ a='PSU';   b='XL';    from='bottom'; to='top';   via=@('425,220', '165,220');                   label='12 V in';        lx=170; ly=205; ev='OPERATOR_CONFIRMED' }
    @{ a='XL';    b='ESP';   from='bottom'; to='top';   via=@();                                   label='5 V to board';   lx=170; ly=398; ev='OPERATOR_CONFIRMED' }
    @{ a='XL';    b='PZEMM'; from='bottom'; to='top';   via=@('240,375', '975,375');                   label='5 V logic supply to PZEM + transceiver'; lx=250; ly=356; ev='OPERATOR_CONFIRMED' }
    @{ a='PSU';   b='FAN';   from='bottom'; to='top';   via=@('500,166', '1345,166');                  label='12 V fan branch, slot 4 = 1 A'; lx=560; ly=148; ev='OPERATOR_CONFIRMED' }
    @{ a='ESP';   b='RS485'; from='right'; to='left';   via=@();                                   label='GPIO36/37'; lx=380; ly=492; ev='PHOTO_VERIFIED' }
    @{ a='RS485'; b='PZEMM'; from='right'; to='left';   via=@();                                   label='RS-485'; lx=772; ly=470; ev='PHOTO_VERIFIED' }
    @{ a='PZEMM'; b='SHUNT'; from='top';   to='bottom'; via=@();                                   label='internal shunt'; lx=985; ly=400; ev='OPERATOR_CONFIRMED' }
    @{ a='ESP';   b='IBT';   from='top';   to='left';   via=@('205,400', '860,400', '860,113');          label='logic inputs RPWM/R_EN/L_EN (GPIO5/6/10)'; lx=402; ly=382; ev='PHOTO_VERIFIED' }
    @{ a='ESP';   b='BUS';   from='bottom'; to='left';  via=@();                                   label='1-Wire + 4.7k'; lx=300; ly=600; ev='PHOTO_VERIFIED' }
)

$bmp = New-Object System.Drawing.Bitmap $Width, $Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.Clear([System.Drawing.Color]::White)

$penBox    = New-Object System.Drawing.Pen([System.Drawing.Color]::Black, 2)
$penSolid  = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(255, 35, 70, 120), 2.5)
$penDash   = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(255, 175, 60, 40), 2.5)
$penDash.DashStyle = [System.Drawing.Drawing2D.DashStyle]::Dash
$brushFill = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 246, 249, 252))
$brushText = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::Black)
$brushSub  = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 70, 70, 70))
$fontTitle = New-Object System.Drawing.Font('Segoe UI', 16, [System.Drawing.FontStyle]::Bold)
$fontBox   = New-Object System.Drawing.Font('Segoe UI', 10, [System.Drawing.FontStyle]::Bold)
$fontLine  = New-Object System.Drawing.Font('Segoe UI', 8)
$fontEdge  = New-Object System.Drawing.Font('Segoe UI', 8)

function ById([string]$id) { return ($nodes | Where-Object { $_.id -eq $id }) }
function Side($n, [string]$side) {
    $cx = $n.x + $n.w / 2; $cy = $n.y + $n.h / 2
    switch ($side) {
        'left'   { return @{ x = $n.x;          y = $cy } }
        'right'  { return @{ x = $n.x + $n.w;   y = $cy } }
        'top'    { return @{ x = $cx;           y = $n.y } }
        'bottom' { return @{ x = $cx;           y = $n.y + $n.h } }
        default  { throw "bad side '$side'" }
    }
}

# 1. edges first, so boxes sit on top of the lines
foreach ($edge in $edges) {
    $from = ById $edge.a
    $to = ById $edge.b
    $pen = $penSolid
    if ($edge.ev -eq 'UNVERIFIED') { $pen = $penDash }
    $points = @()
    $points += (Side $from $edge.from)
    foreach ($w in $edge.via) {
        $xy = $w.Split(',')
        $points += @{ x = [double]$xy[0]; y = [double]$xy[1] }
    }
    $points += (Side $to $edge.to)
    if ($env:TOPO_DEBUG) {
        $desc = ($points | ForEach-Object { "(" + $_.x + "," + $_.y + ")" }) -join " "
        Write-Output ("EDGE " + $edge.a + "->" + $edge.b + " from=" + $edge.from + " to=" + $edge.to + " " + $desc)
    }
    for ($i = 0; $i -lt ($points.Count - 1); $i++) {
        $g.DrawLine($pen, [single]$points[$i].x, [single]$points[$i].y, [single]$points[$i + 1].x, [single]$points[$i + 1].y)
    }
}

# 2. boxes and their text
foreach ($n in $nodes) {
    $g.FillRectangle($brushFill, [single]$n.x, [single]$n.y, [single]$n.w, [single]$n.h)
    $g.DrawRectangle($penBox, [single]$n.x, [single]$n.y, [single]$n.w, [single]$n.h)
    $g.DrawString($n.title, $fontBox, $brushText, [single]($n.x + 8), [single]($n.y + 6))
    $y = $n.y + 26
    foreach ($line in $n.lines) {
        $g.DrawString($line, $fontLine, $brushSub, [single]($n.x + 8), [single]$y)
        $y += 13
    }
    $badge = "[$($n.ev)]"
    $size = $g.MeasureString($badge, $fontLine)
    $g.DrawString($badge, $fontLine, $brushSub, [single]($n.x + $n.w - $size.Width - 6), [single]($n.y + $n.h - 15))
}

# 3. edge labels last, each on a white plate at its declared position
foreach ($edge in $edges) {
    $size = $g.MeasureString($edge.label, $fontEdge)
    $g.FillRectangle([System.Drawing.Brushes]::White, [single]($edge.lx - 2), [single]($edge.ly - 2), [single]($size.Width + 4), [single]($size.Height + 2))
    $color = $brushSub
    if ($edge.ev -eq 'UNVERIFIED') { $color = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 175, 60, 40)) }
    $g.DrawString($edge.label + ' [' + $edge.ev + ']', $fontEdge, $color, [single]$edge.lx, [single]$edge.ly)
}

$legendY = $Height - 110
$g.DrawLine($penSolid, 40, $legendY, 120, $legendY)
$g.DrawString('solid: a repository record exists for this link - read its badge (PHOTO_VERIFIED, OPERATOR_CONFIRMED or INFERRED)', $fontLine, $brushText, 128, ($legendY - 8))
$g.DrawLine($penDash, 40, ($legendY + 22), 120, ($legendY + 22))
$g.DrawString('open G0 item: PSU+ to IBT-2 B+ continuity with slot 3 empty (g0-electrical-verification.md D.8)', $fontLine, $brushSub, 128, ($legendY + 14))
$g.DrawString('Generated by evidence/A/W04/tools/render_power_topology.ps1 from the node and edge lists in that file.', $fontLine, $brushSub, 40, ($legendY + 48))

$bmp.Save($Png, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Output ("PNG written: {0} ({1} bytes)" -f $Png, (Get-Item $Png).Length)
