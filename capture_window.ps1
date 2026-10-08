param(
    [Parameter(Mandatory = $true)][string]$ExePath,
    [string]$OutDir = $PSScriptRoot,
    [int]$TimeoutSec = 30,
    [switch]$KeepOpen
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

if (-not ('WinCap.Native' -as [type])) {
Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Runtime.InteropServices;

namespace WinCap {

public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

[StructLayout(LayoutKind.Sequential)]
public struct RECT { public int L, T, R, B; }

public static class Native {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lp);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder sb, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowTextLengthW(IntPtr h);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder sb, int n);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr h, int attr, out RECT r, int cb);
    [DllImport("user32.dll")] public static extern int GetSystemMetrics(int i);
    [DllImport("user32.dll")] public static extern IntPtr GetDC(IntPtr h);
    [DllImport("user32.dll")] public static extern int ReleaseDC(IntPtr h, IntPtr hdc);
    [DllImport("gdi32.dll")] public static extern IntPtr CreateCompatibleDC(IntPtr hdc);
    [DllImport("gdi32.dll")] public static extern IntPtr CreateCompatibleBitmap(IntPtr hdc, int w, int h);
    [DllImport("gdi32.dll")] public static extern IntPtr SelectObject(IntPtr hdc, IntPtr obj);
    [DllImport("gdi32.dll")] public static extern bool DeleteObject(IntPtr obj);
    [DllImport("gdi32.dll")] public static extern bool DeleteDC(IntPtr hdc);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);

    public static string[] WindowsOfPid(uint pid) {
        var list = new System.Collections.Generic.List<string>();
        EnumWindows(delegate(IntPtr h, IntPtr lp) {
            uint wpid;
            GetWindowThreadProcessId(h, out wpid);
            if (wpid == pid) {
                int len = GetWindowTextLengthW(h);
                var sb = new StringBuilder(len + 2);
                GetWindowTextW(h, sb, sb.Capacity);
                var cn = new StringBuilder(256);
                GetClassNameW(h, cn, cn.Capacity);
                bool vis = IsWindowVisible(h);
                RECT r; GetWindowRect(h, out r);
                list.Add(h.ToInt64() + "|" + len + "|" + sb.ToString() + "|" + cn + "|" + vis + "|" + r.L + "," + r.T + "," + r.R + "," + r.B);
            }
            return true;
        }, IntPtr.Zero);
        return list.ToArray();
    }
}

}
"@
}

[WinCap.Native]::SetProcessDPIAware() | Out-Null

$p = Start-Process -FilePath $ExePath -PassThru -WorkingDirectory (Split-Path $ExePath)
Write-Output ("Started pid " + $p.Id)

$target = $null
$deadline = (Get-Date).AddSeconds($TimeoutSec)
while (-not $target -and (Get-Date) -lt $deadline) {
    if ($p.HasExited) { throw ("Process exited early, code " + $p.ExitCode) }
    foreach ($w in [WinCap.Native]::WindowsOfPid([uint32]$p.Id)) {
        $parts = $w -split '\|'
        $obj = [pscustomobject]@{
            Hwnd    = [IntPtr][int64]$parts[0]
            Len     = [int]$parts[1]
            Title   = $parts[2]
            Class   = $parts[3]
            Visible = ($parts[4] -eq 'True')
            Rect    = $parts[5]
        }
        if ($obj.Visible -or $obj.Len -gt 0) {
            Write-Output ("  window: class='" + $obj.Class + "' titleLen=" + $obj.Len + " title='" + $obj.Title + "' visible=" + $obj.Visible + " rect=" + $obj.Rect)
        }
        if (-not $target -and $obj.Visible -and $obj.Len -gt 0) { $target = $obj }
    }
    if ($target) { break }
    Start-Sleep -Milliseconds 400
}
if (-not $target) { throw ("No visible titled window for pid " + $p.Id + " within " + $TimeoutSec + "s") }

$hwnd = $target.Hwnd
[void][WinCap.Native]::SetForegroundWindow($hwnd)
Start-Sleep -Milliseconds 700

$xy = $target.Rect -split ','
$L = [int]$xy[0]; $T = [int]$xy[1]; $R = [int]$xy[2]; $B = [int]$xy[3]
$w = $R - $L
$h = $B - $T
if ($w -le 0 -or $h -le 0) { throw ("Bad window rect: " + $target.Rect) }

# Primary capture: PrintWindow (renders the window itself, even if occluded)
$pwPng = Join-Path $OutDir "exe_window_capture.png"
$captured = $false
$hdcScreen = [WinCap.Native]::GetDC([IntPtr]::Zero)
$hdcMem = [WinCap.Native]::CreateCompatibleDC($hdcScreen)
$hbmp = [WinCap.Native]::CreateCompatibleBitmap($hdcScreen, $w, $h)
[void][WinCap.Native]::SelectObject($hdcMem, $hbmp)
$ok = [WinCap.Native]::PrintWindow($hwnd, $hdcMem, 2)  # PW_RENDERFULLCONTENT
if ($ok) {
    $bmp = [System.Drawing.Image]::FromHbitmap($hbmp)
    $bmp.Save($pwPng, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    $captured = $true
    Write-Output ("Saved window capture (PrintWindow): " + $pwPng)
}
[void][WinCap.Native]::DeleteObject($hbmp)
[void][WinCap.Native]::DeleteDC($hdcMem)
[void][WinCap.Native]::ReleaseDC([IntPtr]::Zero, $hdcScreen)

if (-not $captured) {
    $margin = 16
    $cx = [Math]::Max(0, $L - $margin); $cy = [Math]::Max(0, $T - $margin)
    $cw = $w + 2 * $margin; $ch = $h + 2 * $margin
    $bmp = New-Object System.Drawing.Bitmap($cw, $ch)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($cx, $cy, 0, 0, (New-Object System.Drawing.Size($cw, $ch)))
    $g.Dispose()
    $bmp.Save($pwPng, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    Write-Output ("Saved window capture (CopyFromScreen fallback): " + $pwPng)
}

# Backup: full primary screen
$sw = [WinCap.Native]::GetSystemMetrics(0)
$sh = [WinCap.Native]::GetSystemMetrics(1)
$fsPng = Join-Path $OutDir "exe_screen_capture.png"
$fs = New-Object System.Drawing.Bitmap($sw, $sh)
$g2 = [System.Drawing.Graphics]::FromImage($fs)
$g2.CopyFromScreen(0, 0, 0, 0, (New-Object System.Drawing.Size($sw, $sh)))
$g2.Dispose()
$fs.Save($fsPng, [System.Drawing.Imaging.ImageFormat]::Png)
$fs.Dispose()
Write-Output ("Saved screen capture: " + $fsPng)

if (-not $KeepOpen) {
    Stop-Process -Id $p.Id -ErrorAction SilentlyContinue
    Write-Output ("Stopped pid " + $p.Id)
}
