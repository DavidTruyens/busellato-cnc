# Nesting tool on Windows

How to run the nesting tool on a Windows PC and put the programs on a diskette for the
Busellato's control.

**Nothing in this file has been tested on Windows yet.** The `.bat` files and the diskette copy
were written and checked on a Mac. If a step does not do what this says, stop and send a photo or
the text of the window.

## Once: install

1. **Python 3** from <https://www.python.org/downloads/> (3.11 or newer). In the first screen
   of the installer, tick **"Add python.exe to PATH"**, then Install Now.
2. **Git for Windows** from <https://git-scm.com/download/win>. The default answers are fine.
3. **Get the repo.** It is private: your GitHub account needs access to
   `DavidTruyens/busellato-cnc` (ask David). Open "Git Bash" or a Command Prompt and type:

   ```
   cd %USERPROFILE%
   git clone https://github.com/DavidTruyens/busellato-cnc.git
   ```

   (in Git Bash use `cd ~`). Git opens a window to sign in to GitHub: sign in in the browser.
   The repo is now in your user folder, `busellato-cnc`. Git remembers the sign-in.

## Once: make the icon

**This step is not tested on Windows.** This gives you an icon on the desktop that starts the tool without a
black window.

1. Open the `busellato-cnc` folder and double-click **`make-shortcut.vbs`**.
2. Your antivirus may ask about a script. It only makes one shortcut on the desktop.
3. A message says "Shortcut made on the desktop: Nesting tool".

Do this again if you move the `busellato-cnc` folder: the icon still points to the old place.

VBScript, which runs `.vbs` files, is an optional Windows feature that Microsoft plans to remove
in a future version of Windows. When it is gone, the icon stops working: use **`start.bat`**
(see "Troubleshooting: the old way" below), which still works.

## Every time: start the tool

**This step is not tested on Windows.** Double-click the **Nesting tool** icon on the desktop. There is no
black window. It

- updates the tool from GitHub (if there is no internet, or you changed files, it skips the
  update and starts the version on the PC; a failed update never stops the start),
- opens the page `http://127.0.0.1:8800/` in your browser.

If the tool is already running, a second click on the icon only opens the page.

**It stops by itself.** When you close the page (the browser tab or window), the tool stops
about 20 seconds later. Reloading the page does not stop it. It never stops while it is busy
(Generate, save, upload). If the browser was closed without a note (for example it crashed), it
stops 3 minutes after the last contact; if no page was ever opened, after 10 minutes.

When it has stopped and you still have the page open, the page says "The tool has stopped.
Start it again with the icon, then reload this page."

**If it cannot start**, a message box says why and shows the end of the log. The whole log is
in `%USERPROFILE%\nesting-project\start.log`; send a photo or the text of it if you ask for
help. That log is written only when the tool is started with the icon: the old way below
(`start.bat`) shows everything in its window and writes no log.

Your work is in `%USERPROFILE%\nesting-project` (the shapes, the settings, and `out\` with
every generated job). The first start puts the 12 sample plates in it.

## Generate

In the page: add shapes (DXF), set quantities and settings, check the preview, then
**Generate programs**. Every Generate makes a new folder
`%USERPROFILE%\nesting-project\out\<date-time>\` with the programs, `RUNSHEET.html` (print it)
and a `DISKETTE` folder: exactly what goes on the diskette.

In the settings there is a **Pockets** section: the pocket tool, depth and feeds, and one row for
each kind of pocket the shapes have (shown in its own colour in the drawings), where you can
change them or switch a pocket kind off. These numbers are guesses until they are measured.

## Write the diskette

1. Put a 1.44 MB diskette in the USB floppy drive. Format it in Explorer: right-click the
   drive (usually `A:`), Format, file system **FAT**, capacity 1.44 MB. This erases it.
2. Double-click **`copy-to-diskette.bat`**. It takes the newest job, asks for the drive letter
   (type `A`), shows what is on the diskette and asks you to type `YES` before it erases it,
   writes the files and reads each one back to check it. It refuses anything that is not a
   diskette (a USB stick or a hard disk).
3. When it says `OK`, eject the diskette in Explorer (right-click the drive, Eject) and wait
   until the drive light is off before you take it out.

## At the machine

1. CNC90 file management: **Programma Kopie** from the diskette to the hard disk. The
   diskette holds the programs in the machine's own import format (`SORG\INDICE.PRG` plus
   `SORG\SRG\...`), so they should appear in the program list.
2. Only if they do **not** appear in the compiler list: leave CNC90, at the DOS prompt type
   `A:LOAD` (copies each program to its folder, never overwrites), then in file management
   register each program, open it in the editor and save it once.
3. Compile. Check every program in the simulator.
4. For each blank, the order is: drill program (`B..D`), screw the blank and the shapes down,
   pocket program (`B..P`, only when the shapes have pockets), then the cut program (`B..C`).
5. First run **in the air** (no blank on the table, you watching, hand on the emergency
   stop), then on **scrap**, then on real parts. Follow the printed run sheet. The pocket
   programs have not been run on the machine yet, so be especially careful with the first one.

## Update

Nothing to do: the icon (and `start.bat`) updates the tool every time it starts, when there is
internet.

## Troubleshooting: the old way

**This step is not tested on Windows.** If the icon does not work (or you have not made it), double-click
**`start.bat`** in the `busellato-cnc` folder. It does the same, but with a black window that
shows what it is doing, and it keeps running until you close that window. Closing the window
stops the tool. If the window says the tool may already be running, it only opens the page.
It writes no `start.log`: read the messages in the window.
