 PROG.: SETP.0    T.P.A.: COMPILATORE GPL1000    05/16/92     pagina 1

INDIRIZZO  OGGETTO     LINEA   LINEA SORGENTE


				*** PROGRAMMA ***

                          1   ;***************** SET POINT BUSELLATO **********
                          2   
                          3    PROG
  0000     4D07           4            LIMITOFF  XYZ                 ;Disattiva
  0002     2A04EB         5            RES       FLGSBLO
  0005     2A08DE         6            RES       STOPPRG             ;Flag di s
  0008     17A3FF00       7            FCALL     163                 ;Reset por
  000C     17A9FF00       8            FCALL     169                 ;Disattiva
  0010     1754FF00       9            FCALL     84                  ;Funz. ges
  0014     1758FF00      10            FCALL     88                  ;Funz. di 
  0018     1739FF00      11            FCALL     57                  ;Funz. set
  001C     1E009B00FF    12            APROG     1Y
           FFFFFFFFFF
  0026     1E00A900FF    13            APROG     2X
           FFFFFFFFFF
  0030     2D08F33F00    14            SKZ       ABILW
  0035     1E00B700FF    15            APROG     3W
           FFFFFFFFFF
  003F     2D10F34E00    16            SKZ       ABILV
  0044     1E00C500FF    17            APROG     3V
           FFFFFFFFFF
  004E     23009B00FF    18            WPROG     1Y
           FFFFFFFFFF
  0058     2300A900FF    19            WPROG     2X
           FFFFFFFFFF
  0062     2300B700FF    20            WPROG     3W
           FFFFFFFFFF
  006C     2300C500FF    21            WPROG     3V
           FFFFFFFFFF
  0076     4C07          22            LIMITON   XYZ
  0078     0720233226    23            VIDEO     #2&6                ;Setpoint 
           3620202020
           2020202020
           2020202020
           2020202020
           2020202020
           20202020
  009A     02            24            END
                         25   
                         26   ;SOTTOPROGRAMMA PER ESECUZIONE CONTEMPORANEA SETP
                         27   
                         28   PROG     1Y
  009B     173AFF00      29            FCALL     58                  ;Funz. set
  009F     1F00FFFFFF    30            EPROG
           FFFFFFFFFF
                         31   
                         32   PROG     2X
  00A9     173BFF00      33            FCALL     59                  ;Funz. set
  00AD     1F00FFFFFF    34            EPROG
           FFFFFFFFFF

 PROG.: SETP.0    T.P.A.: COMPILATORE GPL1000    05/16/92     pagina 2

INDIRIZZO  OGGETTO     LINEA   LINEA SORGENTE

                         35   
                         36   PROG     3W
  00B7     173CFF00      37            FCALL     60                  ;Funz. set
  00BB     1F00FFFFFF    38            EPROG
           FFFFFFFFFF
                         39   
                         40   PROG     3V
  00C5     173EFF00      41            FCALL     62                  ;Funz. set
  00C9     1F00FFFFFF    42            EPROG
           FFFFFFFFFF

Numero di byte occupati: 211

Numero di errori rilevati: 0

