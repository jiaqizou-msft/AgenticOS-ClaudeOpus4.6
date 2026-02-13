# Launch AgenticOS demo as a fully detached process
# Usage: .\launch_demo.ps1 -Demo 1
#        .\launch_demo.ps1 -Demo all
param(
    [string]$Demo = "1"
)

$Root = Split-Path -Parent $PSScriptRoot
if (-not $Root) { $Root = $PSScriptRoot }
if (-not $Root) { $Root = "C:\Users\jiaqizou\Downloads\AgenticOS" }

$Python = "python"
$Script = Join-Path $Root "scripts\run_demo_detached.py"
$LogFile = Join-Path $Root "recordings\demo_log.txt"

# Ensure recordings dir exists
$RecDir = Join-Path $Root "recordings"
if (-not (Test-Path $RecDir)) { New-Item -ItemType Directory -Path $RecDir | Out-Null }

# Clear old log
if (Test-Path $LogFile) { Remove-Item $LogFile -Force }

Write-Host "Launching demo $Demo as detached process..."
Write-Host "Log file: $LogFile"
Write-Host ""

# Launch fully detached
$proc = Start-Process -FilePath $Python `
    -ArgumentList "$Script --demo $Demo" `
    -WorkingDirectory $Root `
    -WindowStyle Normal `
    -PassThru

Write-Host "Process started: PID $($proc.Id)"
Write-Host "Monitoring log file..."
Write-Host ""

# Wait a bit then tail the log
Start-Sleep -Seconds 5

# Monitor log file
$lastPos = 0
$timeout = 600  # 10 min max
$start = Get-Date

while (-not $proc.HasExited) {
    if (Test-Path $LogFile) {
        $content = Get-Content $LogFile -Raw -ErrorAction SilentlyContinue
        if ($content -and $content.Length -gt $lastPos) {
            $newContent = $content.Substring($lastPos)
            Write-Host $newContent -NoNewline
            $lastPos = $content.Length
        }
    }
    
    $elapsed = ((Get-Date) - $start).TotalSeconds
    if ($elapsed -gt $timeout) {
        Write-Host "`nTimeout reached ($timeout s). Killing process."
        Stop-Process -Id $proc.Id -Force
        break
    }
    
    Start-Sleep -Seconds 2
}

# Final output
if (Test-Path $LogFile) {
    $content = Get-Content $LogFile -Raw -ErrorAction SilentlyContinue
    if ($content -and $content.Length -gt $lastPos) {
        Write-Host $content.Substring($lastPos)
    }
}

Write-Host ""
Write-Host "Process exited with code: $($proc.ExitCode)"
