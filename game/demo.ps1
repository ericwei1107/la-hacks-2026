param(
    [string]$Player = "demo",
    [int]$Difficulty = 3,
    [switch]$NoSpark,
    [switch]$NoApp,
    [switch]$NoDemo
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root
$DataDir = Join-Path $Root "data"
$AppDir = Join-Path $Root "app"
$AnalyticsDir = "C:\Users\sahil\kumite-analytics"
$Spark = "sahilmehta@spark-c686"
$SparkIncoming = "${Spark}:~/kumite-llm/incoming"
$HealthSeconds = 60
$Rows = New-Object System.Collections.ArrayList

foreach ($scope in "Machine", "User") {
    $saved = [Environment]::GetEnvironmentVariables($scope)
    foreach ($name in $saved.Keys) {
        if (-not (Test-Path -LiteralPath "Env:$name")) { Set-Item -LiteralPath "Env:$name" -Value $saved[$name] }
    }
}

if ($Player -notmatch '^[A-Za-z0-9_-]+$') { throw "Player must be letters, digits, _ or -" }
if ($Difficulty -lt 1 -or $Difficulty -gt 5) { throw "Difficulty must be 1..5" }

function Add-Row([string]$Title, [string]$Window, [string]$Health) {
    [void]$Rows.Add([pscustomobject]@{ Window = $Title; Status = $Window; Health = $Health })
    Write-Host ("{0,-20} {1,-16} {2}" -f $Title, $Window, $Health)
}

function Open-Window([string]$Title, [string]$Dir, [string]$Body) {
    $script = "`$Host.UI.RawUI.WindowTitle='$Title'; Set-Location -LiteralPath '$Dir'; $Body"
    if ($script.Contains('"')) { throw "window script for $Title contains a double quote" }
    Start-Process powershell -WorkingDirectory $Dir -ArgumentList "-NoExit -Command `"$script`"" -PassThru
}

function Test-Http([string]$Url) {
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return $r.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-Udp([int]$Port) {
    return $null -ne (Get-NetUDPEndpoint -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Test-Tcp([int]$Port) {
    return $null -ne (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Test-Window([string]$Title) {
    $pattern = "*WindowTitle='$Title'*"
    return $null -ne (Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -like $pattern -and $_.ProcessId -ne $PID } | Select-Object -First 1)
}

function Wait-Until([scriptblock]$Check, $Proc) {
    $watch = [Diagnostics.Stopwatch]::StartNew()
    while ($watch.Elapsed.TotalSeconds -lt $HealthSeconds) {
        if (& $Check) { return ("ok after {0:N1} s" -f $watch.Elapsed.TotalSeconds) }
        if ($Proc -and $Proc.HasExited) { return "FAILED: window closed" }
        Start-Sleep -Milliseconds 500
    }
    return "FAILED: no answer in $HealthSeconds s"
}

Write-Host "Kumite demo launcher (repo $Root)"
Write-Host ""

$title = "Kumite padserver"
if (Test-Udp 8768) {
    Add-Row $title "already running" "udp 8768 bound"
} else {
    $p = Open-Window $title $Root "python -m game.padserver"
    Add-Row $title "started" ("udp 8768 " + (Wait-Until { Test-Udp 8768 } $p))
}

$title = "Kumite replay"
$url = "http://127.0.0.1:8766/health"
if (Test-Http $url) {
    Add-Row $title "already running" "$url ok"
} else {
    $p = Open-Window $title $Root "`$env:KUMITE_COACH_MODE='auto'; python -m uvicorn replay.main:app --host 127.0.0.1 --port 8766"
    Add-Row $title "started" ("$url " + (Wait-Until { Test-Http $url } $p))
}

$title = "Kumite analytics"
$url = "http://127.0.0.1:8767/health"
if (Test-Http $url) {
    Add-Row $title "already running" "$url ok"
} elseif (-not (Test-Path -LiteralPath (Join-Path $AnalyticsDir "analytics\demo_host.py"))) {
    Write-Warning "$AnalyticsDir\analytics\demo_host.py not found; continuing without analytics"
    Add-Row $title "MISSING" "no worktree at $AnalyticsDir"
} else {
    $p = Open-Window $title $AnalyticsDir "Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue; python -m analytics.demo_host serve --data-dir '$DataDir' --host 127.0.0.1 --port 8767 --file-only"
    Add-Row $title "started" ("$url " + (Wait-Until { Test-Http $url } $p))
}

$sparkReachable = $false
if (-not $NoSpark) {
    $probe = Start-Process ssh -ArgumentList "-n -o BatchMode=yes -o ConnectTimeout=6 $Spark true" -WindowStyle Hidden -PassThru
    $null = $probe.Handle
    if ($probe.WaitForExit(10000)) {
        $sparkReachable = $probe.ExitCode -eq 0
    } else {
        Stop-Process -Id $probe.Id -Force -ErrorAction SilentlyContinue
    }
    if (-not $sparkReachable) { Write-Warning "$Spark did not answer ssh within 10 s; the spark windows will retry on their own output" }
}

$title = "Kumite laya watch"
$watchCmd = "python -m game.finetune watch"
if (-not $NoSpark) { $watchCmd += " --spark $SparkIncoming" }
if (Test-Window $title) {
    Add-Row $title "already running" "window open"
} else {
    $p = Open-Window $title $Root $watchCmd
    Start-Sleep -Seconds 2
    if ($p.HasExited) { Add-Row $title "FAILED" "window closed" } else { Add-Row $title "started" "no health URL" }
}

$title = "Kumite spark llm"
if ($NoSpark) {
    Add-Row $title "skipped" "-NoSpark"
} elseif (Test-Window $title) {
    Add-Row $title "already running" "window open"
} else {
    $p = Open-Window $title $Root "ssh -t $Spark 'cd kumite-llm && .venv/bin/python serve_llm.py'"
    $health = if ($sparkReachable) { "ssh reachable, no health URL" } else { "ssh NOT reachable" }
    Add-Row $title "started" $health
}

$title = "Kumite app"
if ($NoApp) {
    Add-Row $title "skipped" "-NoApp"
} elseif (Test-Window $title) {
    Add-Row $title "already running" "window open"
} else {
    $pkg = Get-Content -LiteralPath (Join-Path $AppDir "package.json") -Raw | ConvertFrom-Json
    $exe = Get-ChildItem -LiteralPath $AppDir -Directory | Where-Object { $_.Name -ne "node_modules" } |
        ForEach-Object { Get-ChildItem -LiteralPath $_.FullName -Recurse -Filter *.exe -File -ErrorAction SilentlyContinue } |
        Select-Object -First 1
    $envs = "`$env:KUMITE_BRAIN_URL='http://127.0.0.1:8765'; `$env:KUMITE_REPLAY_URL='http://127.0.0.1:8766'; `$env:KUMITE_ANALYTICS_URL='http://127.0.0.1:8767'"
    if ($exe) {
        $p = Open-Window $title $AppDir "$envs; & '$($exe.FullName)'"
        Add-Row $title "started" "built exe $($exe.Name)"
    } elseif ($pkg.scripts.dev) {
        $install = if (Test-Path -LiteralPath (Join-Path $AppDir "node_modules")) { "" } else { "npm.cmd ci; " }
        $p = Open-Window $title $AppDir "$envs; ${install}npm.cmd run dev"
        $note = if ($install) { "npm ci then npm run dev" } else { "npm run dev" }
        Add-Row $title "started" "$note (no health URL)"
    } else {
        Add-Row $title "FAILED" "no built exe and no dev script in app/package.json"
    }
}

$title = "Kumite bot"
$botCmd = "python -m game.bot --player $Player --bot kazuya --difficulty $Difficulty --mode versus --loop --laya"
if (-not $NoDemo) { $botCmd += " --demo" }
if (Test-Window $title) {
    Add-Row $title "already running" "window open; close it or run demo-stop.ps1 for a new bot"
} else {
    if (Test-Tcp 8765) { Write-Warning "tcp 8765 is already in use; the bot's brain API will not bind until it is freed" }
    $p = Open-Window $title $Root "Write-Host 'Start Tekken Versus, Devil Jin vs Kazuya on the 2P pad. Press Enter when the round 1 intro is on screen.'; [void](Read-Host); $botCmd"
    Add-Row $title "started" "waiting for Enter; brain :8765 comes up with the bot"
}

$failed = @($Rows | Where-Object { $_.Status -in @("FAILED", "MISSING") -or $_.Health -like "*FAILED*" -or $_.Health -like "*NOT*" })

Write-Host ""
Write-Host "==================== Kumite demo ===================="
$Rows | Format-Table -AutoSize | Out-String -Width 200 | Write-Host
Write-Host "Bot: $botCmd"
Write-Host ""
Write-Host "1. Padserver window: type start, start (only if Tekken has not seen the 2P pad yet)."
Write-Host "2. Tekken: Versus, Devil Jin (you, 1P) vs Kazuya (2P pad). At the round 1 intro press Enter in 'Kumite bot'."
Write-Host ""
Write-Host "Change difficulty between matches:"
Write-Host "  Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/config -ContentType 'application/json' -Body '{`"difficulty`": 5}'"
Write-Host "Eric's source check (during a round, from his worktree):"
Write-Host "  cd $AnalyticsDir; python -m analytics.demo_host check --data-dir $DataDir --session-id latest --wait-for-round-seconds 300"
Write-Host "Stop everything (Tekken is left alone):"
Write-Host "  .\game\demo-stop.ps1"
if ($failed.Count -gt 0) {
    Write-Host ""
    Write-Warning ("needs attention: " + (($failed | ForEach-Object { $_.Window }) -join ", "))
}
Write-Host "====================================================="
