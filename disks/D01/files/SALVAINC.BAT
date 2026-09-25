@ECHO OFF
:RIPROVA
CLS
ECHO.
ECHO.
ECHO      ษออออออออออออออออออออออออออออออป ษออออออออออออออออออออออออออออออป
ECHO      บ AGGIORNA I FILES DI DATI     บ บ COPY CUTOM FILES FROM DISK A บ
ECHO      บ UTENTE SU DISCO DI LAVORO C: บ บ INTO HARD DISK C:.           บ
ECHO      บ                              บ บ                              บ
ECHO      บ INSERIRE IL DISCO CUSTOM IN Aบ บ INSERT CUSTOM DISKETTE ON A: บ
ECHO      ศออออออออออออออออออออออออออออออผ ศออออออออออออออออออออออออออออออผ
ECHO.
ECHO.
PAUSE
VERIFY ON
IF NOT EXIST A:\PTP1000\*.* GOTO RIPROVA
IF NOT EXIST A:\CNC90\MOD1\USER\*.* GOTO RIPROVA
CLS
ECHO.
ECHO.
ECHO      ษออออออออออออออออออออออออออออออป ษออออออออออออออออออออออออออออออป
ECHO      บ                              บ บ                              บ
ECHO      บ   ... ATTENDERE PREGO ...    บ บ    ...  PLEASE  WAIT  ...    บ
ECHO      บ                              บ บ                              บ
ECHO      ศออออออออออออออออออออออออออออออผ ศออออออออออออออออออออออออออออออผ
ECHO OFF
COPY A:\PTP1000\*.*   C:\PTP1000\*.* /V >NUL
COPY A:\PTPSYS\*.*    C:\PTPSYS\*.*  /V >NUL
COPY A:\PTP0\*.*      C:\PTP0\*.*    /V >NUL
COPY A:\CNC90\LINGUE\*.*    C:\CNC90\LINGUE\*.* /V >NUL
COPY A:\CNC90\MOD1\USER\*.* C:\CNC90\MOD1\USER\*.* /V >NUL
COPY A:\CNC90\*.*     C:\CNC90\*.* /V >NUL
CLS
ECHO.
ECHO   Procedura terminata correttamente.
