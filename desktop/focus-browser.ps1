# Only inspect supported browser processes, never editor/terminal window titles.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class BrowserWindow {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int command);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
}
'@
$title = 'BookSide ' + [char]0x00b7 + ' ' + [char]0x6781 + [char]0x7b80 + [char]0x5b66 + [char]0x4e60
$root = [System.Windows.Automation.AutomationElement]::RootElement
$children = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
foreach ($window in $children) {
    try {
        $process = Get-Process -Id $window.Current.ProcessId -ErrorAction Stop
        if ($process.ProcessName -notin @('msedge', 'chrome', 'firefox', 'brave', 'opera', 'vivaldi')) { continue }
        $handle = [IntPtr]$window.Current.NativeWindowHandle
        $found = $window.Current.Name.StartsWith($title)
        if (-not $found) {
            $condition = [System.Windows.Automation.PropertyCondition]::new(
                [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
                [System.Windows.Automation.ControlType]::TabItem)
            $tabs = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition)
            foreach ($tab in $tabs) {
                if ($tab.Current.Name -eq $title) {
                    $selection = $tab.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
                    $selection.Select()
                    $found = $true
                    break
                }
            }
        }
        if ($found) {
            if ([BrowserWindow]::IsIconic($handle)) { [void][BrowserWindow]::ShowWindow($handle, 9) }
            if ([BrowserWindow]::SetForegroundWindow($handle)) { exit 0 }
            exit 2  # Browser/OS refused focus; use the live-page notification fallback.
        }
    } catch { continue }
}
exit 1
