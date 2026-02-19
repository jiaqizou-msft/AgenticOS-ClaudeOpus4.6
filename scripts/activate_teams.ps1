Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinAPI {
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
}
"@

$proc = Get-Process ms-teams -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if ($proc) {
    [WinAPI]::SetForegroundWindow($proc.MainWindowHandle) | Out-Null
    Write-Host "Activated Teams (PID: $($proc.Id))"
} else {
    Write-Host "Teams not found, starting..."
    Start-Process "msteams:"
    Start-Sleep -Seconds 3
}
