# 验证预览区文字可否拖选复制：置前 → 从文本起点按下左键拖动到行尾 → Ctrl+C → 输出剪贴板。
# 用法: powershell -NoProfile -File tools/select_copy_test.ps1
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

Add-Type @"
using System; using System.Runtime.InteropServices;
public class SelW {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint x, uint y, uint d, UIntPtr e);
  public struct RECT { public int Left, Top, Right, Bottom; }
}
"@

$proc = Get-Process | Where-Object { $_.MainWindowTitle -like "*MD*" } | Select-Object -First 1
if (-not $proc) { Write-Output "NO_WINDOW"; exit 1 }
$h = $proc.MainWindowHandle
[SelW]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 700

$r = New-Object SelW+RECT
[SelW]::GetWindowRect($h, [ref]$r) | Out-Null

# 预览正文首段大约在窗口 y=+330 一带；从 x=+90 拖到 x=+690
$x1 = $r.Left + 90
$y  = $r.Top + 330
$x2 = $r.Left + 690

[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point($x1, $y)
Start-Sleep -Milliseconds 250
[SelW]::mouse_event(2, 0, 0, 0, [UIntPtr]::Zero)   # LEFTDOWN
Start-Sleep -Milliseconds 150
for ($i = 1; $i -le 12; $i++) {
  $step = [int]($x1 + ($x2 - $x1) * $i / 12)
  [System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point($step, $y)
  Start-Sleep -Milliseconds 55
}
[SelW]::mouse_event(4, 0, 0, 0, [UIntPtr]::Zero)   # LEFTUP
Start-Sleep -Milliseconds 350

[System.Windows.Forms.SendKeys]::SendWait("^c")
Start-Sleep -Milliseconds 500
$clip = [System.Windows.Forms.Clipboard]::GetText()
Write-Output ("CLIP=[" + $clip + "]")
