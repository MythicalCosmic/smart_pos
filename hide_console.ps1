Add-Type @'
using System;
using System.Runtime.InteropServices;

public class WinConsole {
    [DllImport("kernel32.dll")]
    public static extern IntPtr GetConsoleWindow();

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
'@

# 6 = minimize, 0 = hide completely
[WinConsole]::ShowWindow([WinConsole]::GetConsoleWindow(), 0)
