' Nesting tool launcher (Windows Script Host): the desktop shortcut runs this file.
' It runs start.bat in this folder with no visible window, which updates the tool from GitHub,
' starts it and opens the page; the tool stops by itself when the page is closed. If the tool
' already runs, it only opens the page. If start.bat fails, a message box says why and shows
' the end of the log (%USERPROFILE%\nesting-project\start.log). Nothing else: no downloads,
' no changes outside that project folder.
Option Explicit

Const TITLE = "Nesting tool"
Const URL = "http://127.0.0.1:8800/"
Const TAIL_LINES = 12

Dim shell, fso, repo, bat, project, logFile, code, msg
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

repo = fso.GetParentFolderName(WScript.ScriptFullName)
bat = repo & "\start.bat"
If Not fso.FileExists(bat) Then
    MsgBox "start.bat was not found next to this launcher:" & vbCrLf & bat, vbExclamation, TITLE
    WScript.Quit 1
End If

' Already running: only open the page. This must not run start.bat: its "> start.log" would
' truncate (or fail on) the log that the running copy still writes to.
If ToolRuns(URL & "api/ping") Then
    shell.Run URL
    WScript.Quit 0
End If

project = shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\nesting-project"
logFile = project & "\start.log"
If Not MakeFolder(project) Then
    MsgBox "Cannot create the project folder:" & vbCrLf & project, vbExclamation, TITLE
    WScript.Quit 1
End If

' Quiet mode for start.bat; an environment variable survives its re-call after an update.
shell.Environment("Process")("NESTING_QUIET") = "1"
' cmd /c strips the first and the last quote of: ""<repo>\start.bat" > "<log>" 2>&1"
' Window style 0 = hidden; True = wait until start.bat ends (that is: until the tool stops).
code = shell.Run("cmd /c """"" & bat & """ > """ & logFile & """ 2>&1""", 0, True)
If code = 0 Then WScript.Quit 0

Select Case code
    Case 2
        msg = "Python 3 was not found. Install it from python.org (tick Add python.exe to PATH)."
    Case 3
        msg = "This Python is too old: 3.11 or newer is needed."
    Case 4
        msg = "Port 8800 is in use by another program, or an old window of the tool is still open: close it."
    Case 5
        msg = "The tool did not start or stopped with an error."
    Case Else
        msg = "The tool could not be started (code " & code & ")."
End Select
MsgBox msg & vbCrLf & vbCrLf & LogTail(logFile, TAIL_LINES) & vbCrLf & "Log: " & logFile, _
    vbExclamation, TITLE
WScript.Quit code


' True when the nesting tool answers on the port: GET /api/ping gives {"app": "nesting", ...}.
' Any error (nothing listens, timeout, no HTTP object) means False: start.bat then checks again
' itself and reports "something else holds the port".
Function ToolRuns(pingUrl)
    Dim http, status, body, found
    ToolRuns = False
    On Error Resume Next
    Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
    If Err.Number <> 0 Then
        Err.Clear
        Set http = CreateObject("MSXML2.ServerXMLHTTP")
    End If
    If Err.Number <> 0 Then Exit Function
    ' resolve, connect, send, receive (milliseconds)
    http.setTimeouts 2000, 2000, 2000, 3000
    http.open "GET", pingUrl, False
    http.send
    If Err.Number <> 0 Then Exit Function
    status = http.status
    If Err.Number <> 0 Then Exit Function
    If status <> 200 Then Exit Function
    body = Replace(Replace(Replace(http.responseText, " ", ""), vbTab, ""), vbLf, "")
    found = InStr(body, """app"":""nesting""")
    ' Checked apart: under On Error Resume Next an error inside an If condition runs the Then part.
    If Err.Number <> 0 Then Exit Function
    ToolRuns = (found > 0)
End Function

' Create the folder (one level: %USERPROFILE% exists). False when it cannot be made.
Function MakeFolder(path)
    If Not fso.FolderExists(path) Then
        On Error Resume Next
        fso.CreateFolder path
        Err.Clear
        On Error GoTo 0
    End If
    MakeFolder = fso.FolderExists(path)
End Function

' The last lines of the log, each cut to 90 characters, at most 700 characters in all (a message
' box shows only about 1024 characters, and the "Log:" line must stay visible). "" when the log
' cannot be read.
Function LogTail(path, count)
    Dim f, text, lines, first, last, i, line, tail
    LogTail = ""
    On Error Resume Next
    Set f = fso.OpenTextFile(path, 1, False)
    If Err.Number <> 0 Then Exit Function
    text = f.ReadAll
    f.Close
    If Err.Number <> 0 Then Exit Function
    lines = Split(Replace(text, vbCr, ""), vbLf)
    last = UBound(lines)
    Do While last >= 0
        If Trim(lines(last)) <> "" Then Exit Do
        last = last - 1
    Loop
    first = last - count + 1
    If first < 0 Then first = 0
    tail = ""
    For i = first To last
        line = lines(i)
        If Len(line) > 90 Then line = Left(line, 87) & "..."
        tail = tail & line & vbCrLf
    Next
    If Len(tail) > 700 Then tail = "..." & Right(tail, 697)
    If Err.Number <> 0 Then Exit Function
    LogTail = tail
End Function
