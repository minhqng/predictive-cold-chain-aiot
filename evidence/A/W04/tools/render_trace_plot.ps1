<#
.SYNOPSIS
    Render a W04 evidence line plot straight from a derived trace CSV.

.DESCRIPTION
    Windows-only (System.Drawing). The CSV stays the machine-readable artifact;
    this figure is the human-readable one, and every number drawn on it is
    recomputed from the CSV rather than typed in. Series that a session did not
    record simply produce no points - nothing is filled in.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File `
      evidence\A\W04\tools\render_trace_plot.ps1 `
      -Csv evidence\A\W04\h6\first-tec-trace.csv `
      -Png evidence\A\W04\h6\first-tec-plot.png `
      -XColumn host_uptime_s `
      -Series '1:current_a:Firebrick:current (A);1:power_w:SteelBlue:power (W);2:duty_permille:SeaGreen:duty_permille' `
      -Title 'W04 first TEC response' -Note 'thermal channels absent'
#>
param(
    [Parameter(Mandatory = $true)][string]$Csv,
    [Parameter(Mandatory = $true)][string]$Png,
    [string]$Title = "W04 trace",
    [string]$XColumn = "host_uptime_s",
    [double]$XDivisor = 1,
    # `powershell -File` cannot bind a repeated array parameter, so series and
    # event columns arrive as one ';' separated string.
    [string]$Series = '',
    [string]$EventColumns = '',
    [string]$Note = "",
    [int]$Width = 1180,
    [int]$Height = 780
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$seriesList = @($Series -split ';' | Where-Object { $_.Trim() })
$eventList = @($EventColumns -split ';' | Where-Object { $_.Trim() })

if (-not [System.IO.Path]::IsPathRooted($Csv)) { $Csv = Join-Path (Get-Location) $Csv }
if (-not [System.IO.Path]::IsPathRooted($Png)) { $Png = Join-Path (Get-Location) $Png }
$Csv = [System.IO.Path]::GetFullPath($Csv)
$Png = [System.IO.Path]::GetFullPath($Png)
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Png) | Out-Null

$rows = Import-Csv -Path $Csv
if (-not $rows) { throw "no rows in $Csv" }

# Each series spec is panel:column:color:label
$parsed = foreach ($spec in $seriesList) {
    $parts = $spec.Split(':', 4)
    if ($parts.Count -lt 4) { throw "bad -Series '$spec', expected panel:column:color:label" }
    [pscustomobject]@{ Panel = [int]$parts[0]; Column = $parts[1]; Color = $parts[2]; Label = $parts[3] }
}
if (-not $parsed) { throw 'at least one -Series is required' }
$panelNumbers = $parsed | Select-Object -ExpandProperty Panel -Unique | Sort-Object

function Value([object]$row, [string]$column) {
    $raw = $row.$column
    if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
    $out = 0.0
    if ([double]::TryParse($raw, [ref]$out)) { return $out }
    return $null
}

$bmp = New-Object System.Drawing.Bitmap $Width, $Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.Clear([System.Drawing.Color]::White)

$penAxis  = New-Object System.Drawing.Pen([System.Drawing.Color]::Black, 2)
$penGrid  = New-Object System.Drawing.Pen([System.Drawing.Color]::Gainsboro, 1)
$penEvent = New-Object System.Drawing.Pen([System.Drawing.Color]::Gray, 1)
$penEvent.DashStyle = [System.Drawing.Drawing2D.DashStyle]::Dash
$brushText = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::Black)
$brushSub  = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 80, 80, 80))
$fontTitle = New-Object System.Drawing.Font('Segoe UI', 15, [System.Drawing.FontStyle]::Bold)
$fontText  = New-Object System.Drawing.Font('Segoe UI', 9)
$fontSmall = New-Object System.Drawing.Font('Segoe UI', 8)

$xMax = 0.0
foreach ($row in $rows) {
    $v = Value $row $XColumn
    if ($null -ne $v -and ($v / $XDivisor) -gt $xMax) { $xMax = $v / $XDivisor }
}
if ($xMax -le 0) { $xMax = 1 }

$left = 96; $right = $Width - 70; $topMargin = 124
$noteRows = 0
if ($Note) { $noteRows = [math]::Ceiling($Note.Length / 150) }
$plotBottom = $Height - 56 - (18 * $noteRows)
$gap = 46
$panelHeight = [int](($plotBottom - $topMargin - $gap * ($panelNumbers.Count - 1)) / $panelNumbers.Count)

$rects = @{}
for ($i = 0; $i -lt $panelNumbers.Count; $i++) {
    $pTop = $topMargin + $i * ($panelHeight + $gap)
    $rects[[int]$panelNumbers[$i]] = @($pTop, ($pTop + $panelHeight))
}

function Map-X([double]$x) { $left + ($x / $xMax) * ($right - $left) }

$summary = @()
foreach ($panel in $panelNumbers) {
    $top, $bot = $rects[[int]$panel]
    $members = @($parsed | Where-Object { $_.Panel -eq $panel })
    $vMax = 0.0
    foreach ($member in $members) {
        foreach ($row in $rows) {
            $v = Value $row $member.Column
            if ($null -ne $v -and $v -gt $vMax) { $vMax = $v }
        }
    }
    if ($vMax -le 0) { $vMax = 1 }

    for ($k = 0; $k -le 4; $k++) {
        $yv = $bot - ($k / 4) * ($bot - $top)
        $g.DrawLine($penGrid, $left, $yv, $right, $yv)
        $g.DrawString([string]([math]::Round($vMax * $k / 4, 2)), $fontSmall, $brushText, ($left - 62), ($yv - 8))
    }
    for ($k = 0; $k -le 6; $k++) {
        $xv = Map-X ($xMax * $k / 6)
        $g.DrawLine($penGrid, $xv, $top, $xv, $bot)
        if ($panel -eq $panelNumbers[-1]) {
            $g.DrawString([string]([math]::Round($xMax * $k / 6, 1)), $fontSmall, $brushText, ($xv - 14), ($bot + 6))
        }
    }
    $g.DrawLine($penAxis, $left, $top, $left, $bot)
    $g.DrawLine($penAxis, $left, $bot, $right, $bot)
    $g.DrawLine($penAxis, $right, $top, $right, $bot)

    $legendY = $top + 2
    foreach ($member in $members) {
        $color = [System.Drawing.Color]::FromName($member.Color)
        $pen = New-Object System.Drawing.Pen($color, 2.5)
        $prev = $null
        $points = 0
        $peak = 0.0
        $sum = 0.0
        foreach ($row in $rows) {
            $xRaw = Value $row $XColumn
            $y = Value $row $member.Column
            if ($null -eq $xRaw -or $null -eq $y) { continue }
            $x = Map-X ($xRaw / $XDivisor)
            $yp = $bot - ($y / $vMax) * ($bot - $top)
            if ($null -ne $prev) { $g.DrawLine($pen, $prev[0], $prev[1], [single]$x, [single]$yp) }
            $prev = @($x, $yp)
            $points++; if ($y -gt $peak) { $peak = $y }; $sum += $y
        }
        $brush = New-Object System.Drawing.SolidBrush $color
        $g.DrawString($member.Label, $fontText, $brush, ($left + 6), $legendY)
        $legendY += 18
        if ($points -gt 0) {
            $summary += "$($member.Column): $points pts, peak $([math]::Round($peak,3)), mean $([math]::Round(($sum / $points),3))"
        } else {
            $summary += "$($member.Column): no points recorded"
        }
        $pen.Dispose(); $brush.Dispose()
    }
}

foreach ($eventColumn in $eventList) {
    $index = 0
    foreach ($row in $rows) {
        if ([string]::IsNullOrWhiteSpace($row.$eventColumn)) { continue }
        $xRaw = Value $row $XColumn
        if ($null -eq $xRaw) { continue }
        $x = Map-X ($xRaw / $XDivisor)
        $firstTop, $unused = $rects[[int]$panelNumbers[0]]
        $lastTop, $lastBot = $rects[[int]$panelNumbers[-1]]
        $g.DrawLine($penEvent, $x, $firstTop, $x, $lastBot)
        $g.DrawString($row.$eventColumn, $fontSmall, $brushSub, ($x + 3), ($firstTop - 14 - (($index % 4) * 13)))
        $index++
    }
}

$g.DrawString($Title, $fontTitle, $brushText, 24, 16)
# Wrap the summary so a wide figure cannot clip the numbers it is citing.
$subtitle = "source: $(Split-Path -Leaf $Csv)   |   $($rows.Count) rows   |   x = $XColumn   |   " + ($summary -join '  |  ')
$lineY = 44
while ($subtitle.Length -gt 150) {
    $cut = $subtitle.LastIndexOf('|', 150)
    if ($cut -lt 40) { $cut = 150 }
    $g.DrawString($subtitle.Substring(0, $cut), $fontSmall, $brushSub, 26, $lineY)
    $subtitle = $subtitle.Substring($cut).TrimStart('|', ' ')
    $lineY += 15
}
$g.DrawString($subtitle, $fontSmall, $brushSub, 26, $lineY)
if ($Note) {
    $noteY = $plotBottom + 24
    $remaining = $Note
    while ($remaining.Length -gt 150) {
        $cut = $remaining.LastIndexOf(' ', 150)
        if ($cut -lt 60) { $cut = 150 }
        $g.DrawString($remaining.Substring(0, $cut), $fontText, $brushSub, 26, $noteY)
        $remaining = $remaining.Substring($cut).TrimStart()
        $noteY += 17
    }
    $g.DrawString($remaining, $fontText, $brushSub, 26, $noteY)
}

$bmp.Save($Png, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Output ("PNG written: {0} ({1} bytes)" -f $Png, (Get-Item $Png).Length)
