' Nesting tool: makes the desktop shortcut "Nesting tool" (run once, by double-click).
' The shortcut runs start-quiet.vbs in this folder with Windows Script Host: the tool starts
' with no visible window and stops by itself when the page is closed. Run it again if this
' folder moves. Nothing else: it only writes the one .lnk file on the desktop.
Option Explicit

Const TITLE = "Nesting tool"

Dim shell, fso, repo, launcher, lnk
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

repo = fso.GetParentFolderName(WScript.ScriptFullName)
launcher = repo & "\start-quiet.vbs"
If Not fso.FileExists(launcher) Then
    MsgBox "start-quiet.vbs was not found next to this file:" & vbCrLf & launcher, vbExclamation, TITLE
    WScript.Quit 1
End If

Set lnk = shell.CreateShortcut(shell.SpecialFolders("Desktop") & "\Nesting tool.lnk")
lnk.TargetPath = shell.ExpandEnvironmentStrings("%WINDIR%") & "\System32\wscript.exe"
lnk.Arguments = """" & launcher & """"
lnk.WorkingDirectory = repo
' Expanded here: the same as "%SystemRoot%\System32\shell32.dll,21" without relying on the
' shortcut expanding it.
lnk.IconLocation = shell.ExpandEnvironmentStrings("%SystemRoot%") & "\System32\shell32.dll,21"
lnk.Description = "Start the nesting tool (it stops by itself when the page is closed)"
lnk.Save

MsgBox "Shortcut made on the desktop: Nesting tool. Run make-shortcut again if this folder moves.", _
    vbInformation, TITLE
