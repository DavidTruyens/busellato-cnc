 PROG.: SETP.0    T.P.A.: GPL1000 COMPILER       10/02/01      page 1

ADDRESS     OBJECT      LINE    SOURCE LINE


				*** PROGRAM ***

                          1   ;***************** SET POINT BUSELLATO **********
                          2   
                          3    PROG
  0000     4D07           4            LIMITOFF  XYZ                 ;Disattiva
  0002     2A04EB         5            RES       FLGSBLO
  0005     2A08DE         6            RES       STOPPRG             ;Flag di s
  0008     17A3FF00       7            FCALL     163                 ;Reset por
  000C     17A9FF00       8            FCALL     169                 ;Disattiva
  0010     1754FF00       9            FCALL     84                  ;Funz. ges
  0014     1739FF00      10            FCALL     57                  ;Funz. set
  0018     1E004F00FF    11            APROG     1Y
           FFFFFFFFFF
  0022     1E005D00FF    12            APROG     2X
           FFFFFFFFFF
  002C     2D10F33500    13            SKZ       ABILV
  0031     173EFF00      14            FCALL     62                  ;Funz. set
  0035     23004F00FF    15            WPROG     1Y
           FFFFFFFFFF
  003F     23005D00FF    16            WPROG     2X
           FFFFFFFFFF
  0049     4C07          17            LIMITON   XYZ
  004B     110632        18            MESSAGE   6,2                 ;Setpoint 
  004E     02            19            END
                         20   
                         21   ;SOTTOPROGRAMMA PER ESECUZIONE CONTEMPORANEA SETP
                         22   
                         23   PROG     1Y
  004F     173AFF00      24            FCALL     58                  ;Funz. set
  0053     1F00FFFFFF    25            EPROG
           FFFFFFFFFF
                         26   
                         27   PROG     2X
  005D     173BFF00      28            FCALL     59                  ;Funz. set
  0061     1F00FFFFFF    29            EPROG
           FFFFFFFFFF
                         30   
                         31   PROG     3W
  006B     173CFF00      32            FCALL     60                  ;Funz. set
  006F     1F00FFFFFF    33            EPROG
           FFFFFFFFFF

Number of bytes used: 121

No. of errors detected: 0

