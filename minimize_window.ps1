Add-Type @"
    using System;
    using System.Runtime.InteropServices;
    public class Window {
        [DllImport("user32.dll")]
        public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
        [DllImport("kernel32.dll")]
        public static extern IntPtr GetConsoleWindow();
    }
"@

$consolePtr = [Window]::GetConsoleWindow()
# SW_MINIMIZE = 6
[Window]::ShowWindow($consolePtr, 6) | Out-Null