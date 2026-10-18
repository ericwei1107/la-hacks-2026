$ErrorActionPreference = "Continue"
$Protected = @("Polaris-Win64-Shipping", "WindowsTerminal", "explorer", "System", "Idle")
$Ports = 8765..8768
$Stopped = New-Object System.Collections.ArrayList

function Stop-Tree([int]$ProcessId, [string]$Reason) {
    if ($ProcessId -le 4 -or $ProcessId -eq $PID) { return }
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $proc) { return }
    if ($Protected -contains $proc.ProcessName) {
        Write-Host ("skip {0} ({1}): protected" -f $proc.ProcessName, $ProcessId)
        return
    }
    & taskkill.exe /T /F /PID $ProcessId 2>&1 | Out-Null
    [void]$Stopped.Add([pscustomobject]@{ Process = $proc.ProcessName; Id = $ProcessId; Reason = $Reason })
}

$shells = Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='pwsh.exe'" |
    Where-Object { $_.CommandLine -like "*WindowTitle='Kumite *" -and $_.ProcessId -ne $PID }
foreach ($s in $shells) {
    $title = [regex]::Match($s.CommandLine, "WindowTitle='(Kumite [^']*)'").Groups[1].Value
    Stop-Tree $s.ProcessId "window '$title'"
}

Get-Process -Name powershell, pwsh -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowTitle -like "Kumite *" -and $_.Id -ne $PID } |
    ForEach-Object { Stop-Tree $_.Id "window '$($_.MainWindowTitle)'" }

$owners = @()
$owners += Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $Ports -contains $_.LocalPort } |
    ForEach-Object { [pscustomobject]@{ Id = [int]$_.OwningProcess; Port = "tcp $($_.LocalPort)" } }
$owners += Get-NetUDPEndpoint -ErrorAction SilentlyContinue | Where-Object { $Ports -contains $_.LocalPort } |
    ForEach-Object { [pscustomobject]@{ Id = [int]$_.OwningProcess; Port = "udp $($_.LocalPort)" } }
foreach ($o in $owners) { Stop-Tree $o.Id "listening on $($o.Port)" }

if ($Stopped.Count -eq 0) {
    Write-Host "nothing from the Kumite launcher was running"
} else {
    $Stopped | Format-Table -AutoSize | Out-String -Width 200 | Write-Host
}

Start-Sleep -Milliseconds 500
$left = @()
$left += Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $Ports -contains $_.LocalPort } | ForEach-Object { "tcp $($_.LocalPort)" }
$left += Get-NetUDPEndpoint -ErrorAction SilentlyContinue | Where-Object { $Ports -contains $_.LocalPort } | ForEach-Object { "udp $($_.LocalPort)" }
if ($left.Count -gt 0) {
    Write-Warning ("still bound: " + ($left -join ", "))
} else {
    Write-Host "ports 8765-8768 are free; Tekken was not touched"
}
