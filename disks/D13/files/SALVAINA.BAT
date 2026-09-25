@ECHO OFF
:RIPROVA
CLS
ECHO.
ECHO.
ECHO      ษออออออออออออออออออออออออออออออป ษออออออออออออออออออออออออออออออป
ECHO      บ AGGIORNA I FILES DI DATI     บ บ COPY CUSTOM FILES ON CUSTOM  บ
ECHO      บ UTENTE SU DISCO UTENTE IN A: บ บ DISKETTE.                    บ
ECHO      บ                              บ บ                              บ
ECHO      บ INSERIRE IL DISCO CUSTOM IN Aบ บ INSERT CUSTOM DISKETTE IN A: บ
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
COPY C:\PTP1000\ENVIRON.TPA   A:\PTP1000\*.* /V >NUL
REPLACE C:\PTP1000\*.*   A:\PTP1000 >NUL
COPY C:\PTPSYS\*.*    A:\PTPSYS\*.*  /V >NUL
COPY C:\PTP0\*.*      A:\PTP0\*.*    /V >NUL
COPY C:\CNC90\LINGUE\*.*    A:\CNC90\LINGUE\*.*    /V >NUL
COPY C:\CNC90\MOD1\USER\*.* A:\CNC90\MOD1\USER\*.* /V >NUL
REPLACE C:\CNC90\*.* A:\CNC90 >NUL
CLS
ECHO.
ECHO   Procedura terminata correttamente.
