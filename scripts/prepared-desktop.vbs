Option Explicit
Dim shell, files, base, executable, launcher, command
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
base = files.GetParentFolderName(WScript.ScriptFullName)
executable = shell.ExpandEnvironmentStrings("%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe")
launcher = files.BuildPath(base, "prepared-desktop-launcher.ps1")
command = """" & executable & """ -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & launcher & """"
If WScript.Arguments.Count = 1 Then
    If InStr(WScript.Arguments(0), """") > 0 Then WScript.Quit 2
    command = command & " -NoBrowser -SmokeTestOutput """ & files.GetAbsolutePathName(WScript.Arguments(0)) & """"
End If
shell.Run command, 0, False
