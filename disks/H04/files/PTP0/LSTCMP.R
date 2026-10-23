 PROG.: FRESA.0    T.P.A.: GPL1000 COMPILER       11/13/01      page 1

ADDRESS     OBJECT      LINE    SOURCE LINE


				*** FUNCTION ***

                          1   ;>>>>>>>>>>>>>>>>> FUNZIONI DI FRESATA - LINEARE
                          2   
  #83                     3   FUN      131,FLinAF1                   ;Fresata l
           00             +
           19             +
           1910           +    BYTE
           1D10           +    BYTE
           2110           +    BYTE
           4410           +    ASSI
           4510           +    DIREZ
           4620           +    RATEIC
           4820           +    RESOL
           4A40           +    QF1
           4E40           +    QF2
           5240           +    QF3
           5640           +    DIAG
                          4   
  0000     2800F4FF       5 &          OUT       &BYTE+FITTIZ1       ;
  0004     2800F5FF       6 &          OUT       &BYTE+FITTIZ2       ;
  0008     2800FBFF       7 &          OUT       &BYTE+FITTIZ3       ;
  000C     2E08F21A00     8            SNZ       CAMBUT,SEG          ;Con cambi
  0011     1747FF00       9            FCALL     71                  ;Funz. tes
  0015     2E04E02A00    10            SNZ       FLGESCLU,ESCI       ;
  001A     2D08F52000    11   SEG:     SKZ       FINCONT             ;Se=0 NO C
  001F     5E            12            ECNT                          ;
  0020     2D20F42700    13            SKZ       FCONTOR             ;Se=1 Cont
  0025     5D01          14            ICNT      1                   ;
  0027     152B00        15            CALL      XYFLIN              ;
  002A     18            16   ESCI:    FRET                          ;
                         17   
                         18   ;*****************  SUBROUTINE (F131) PER LA FACC
                         19   
  002B     5A00000000    20 & XYFLIN:  LINEAR    &LINEA
           0000000000
           0000000000
           0000000000
           000000
  0042     16            21            RET
                         22   
                         23   
                         24   ; ***** NOTE: FUNZIONE (F131) FUNZIONE DI FRESATA
                         25   
                         26   ;ELENCO PARAMETRI:
                         27   
                         28   ;01  --> BYTE FITTIZIO1
                         29   ;02  -->   "     "    2
                         30   ;03  -->   "     "    3 ESCLUSIONI
                         31   ;Parametri passati alla  --> LINEAR XYFLIN
                         32   ;04  --> MASCHERA ASSI
                         33   ;05  --> DIREZIONE ASSE

 PROG.: FRESA.0    T.P.A.: GPL1000 COMPILER       11/13/01      page 2

ADDRESS     OBJECT      LINE    SOURCE LINE

                         34   ;06  --> RATEIC
                         35   ;07  --> PASSO RESOL
                         36   ;08  --> QUOTA ASSE 1
                         37   ;09  --> QUOTA ASSE 2
                         38   ;10  --> QUOTA ASSE 3
                         39   ;11  --> DIAGONALE
                         40   
                         41   
  #84                    42   FUN      132,FLinAF2                   ;Fresata l
           00             +
           19             +
           1910           +    BYTE
           1D10           +    BYTE
           2110           +    BYTE
           4410           +    ASSI
           4510           +    DIREZ
           4620           +    RATEIC
           4820           +    RESOL
           4A40           +    QF1
           4E40           +    QF2
           5240           +    QF3
           5640           +    DIAG
                         43   
  0000     2800F4FF      44 &          OUT       &BYTE+FITTIZ1       ;
  0004     2800F5FF      45 &          OUT       &BYTE+FITTIZ2       ;
  0008     2800FBFF      46 &          OUT       &BYTE+FITTIZ3       ;
  000C     2E08F21A00    47            SNZ       CAMBUT,SEG          ;Con cambi
  0011     1747FF00      48            FCALL     71                  ;Funz. tes
  0015     2E04E02A00    49            SNZ       FLGESCLU,ESCI       ;
  001A     2D08F52000    50   SEG:     SKZ       FINCONT             ;Se=0 NO C
  001F     5E            51            ECNT                          ;
  0020     2D20F42700    52            SKZ       FCONTOR             ;Se=1 Cont
  0025     5D01          53            ICNT      1                   ;
  0027     152B00        54            CALL      XYFLIN              ;
  002A     18            55   ESCI:    FRET                          ;
                         56   
                         57   ;*****************  SUBROUTINE (F132) PER LA FACC
                         58   
  002B     5A00000000    59 & XYFLIN:  LINEAR    &LINEA
           0000000000
           0000000000
           0000000000
           000000
  0042     16            60            RET
                         61   
                         62   
                         63   
                         64   
                         65   
                         66   ; ***** NOTE: FUNZIONE (F132) FUNZIONE DI FRESATA
                         67   
                         68   ;ELENCO PARAMETRI:
                         69   

 PROG.: FRESA.0    T.P.A.: GPL1000 COMPILER       11/13/01      page 3

ADDRESS     OBJECT      LINE    SOURCE LINE

                         70   ;01  --> BYTE FITTIZIO1
                         71   ;02  -->   "     "    2
                         72   ;03  -->   "     "    3 ESCLUSIONI
                         73   ;Parametri passati alla  --> LINEAR XYFLIN
                         74   ;04  --> MASCHERA ASSI
                         75   ;05  --> DIREZIONE ASSE
                         76   ;06  --> RATEIC
                         77   ;07  --> PASSO RESOL
                         78   ;08  --> QUOTA ASSE 1
                         79   ;09  --> QUOTA ASSE 2
                         80   ;10  --> QUOTA ASSE 3
                         81   ;11  --> DIAGONALE
                         82   
                         83   
  #85                    84   FUN      133,FLinAF3                  ;Fresata li
           00             +
           19             +
           1910           +    BYTE
           1D10           +    BYTE
           2110           +    BYTE
           4410           +    ASSI
           4510           +    DIREZ
           4620           +    RATEIC
           4820           +    RESOL
           4A40           +    QF1
           4E40           +    QF2
           5240           +    QF3
           5640           +    DIAG
                         85   
  0000     2800F4FF      86 &          OUT       &BYTE+FITTIZ1       ;
  0004     2800F5FF      87 &          OUT       &BYTE+FITTIZ2       ;
  0008     2800FBFF      88 &          OUT       &BYTE+FITTIZ3       ;
  000C     2E08F21A00    89            SNZ       CAMBUT,SEG          ;Con cambi
  0011     1747FF00      90            FCALL     71                  ;Funz. tes
  0015     2E04E02A00    91            SNZ       FLGESCLU,ESCI       ;
  001A     2D08F52000    92   SEG:     SKZ       FINCONT             ;Se=0 NO C
  001F     5E            93            ECNT                          ;
  0020     2D20F42700    94            SKZ       FCONTOR             ;Se=1 Cont
  0025     5D01          95            ICNT      1                   ;
  0027     152B00        96            CALL      XYFLIN              ;
  002A     18            97   ESCI:    FRET                          ;
                         98   
                         99   
                        100   ;*****************  SUBROUTINE (F133) PER LA FACC
                        101   
  002B     5A00000000   102 & XYFLIN:  LINEAR    &LINEA
           0000000000
           0000000000
           0000000000
           000000
  0042     16           103            RET
                        104   
                        105   

 PROG.: FRESA.0    T.P.A.: GPL1000 COMPILER       11/13/01      page 4

ADDRESS     OBJECT      LINE    SOURCE LINE

                        106   
                        107   ; ***** NOTE: FUNZIONE (F133) FUNZIONE DI FRESATA
                        108   
                        109   ;ELENCO PARAMETRI:
                        110   
                        111   ;01  --> BYTE FITTIZIO1
                        112   ;02  -->   "     "    2
                        113   ;03  -->   "     "    3 ESCLUSIONI
                        114   ;Parametri passati alla  --> LINEAR XYFLIN
                        115   ;04  --> MASCHERA ASSI
                        116   ;05  --> DIREZIONE ASSE
                        117   ;06  --> RATEIC
                        118   ;07  --> PASSO RESOL
                        119   ;08  --> QUOTA ASSE 1
                        120   ;09  --> QUOTA ASSE 2
                        121   ;10  --> QUOTA ASSE 3
                        122   ;11  --> DIAGONALE
                        123   
                        124   
                        125   
                        126   
                        127   
  #86                   128   FUN      134,FLinAF4                   ;Fresata l
           00             +
           19             +
           1910           +    BYTE
           1D10           +    BYTE
           2110           +    BYTE
           4410           +    ASSI
           4510           +    DIREZ
           4620           +    RATEIC
           4820           +    RESOL
           4A40           +    QF1
           4E40           +    QF2
           5240           +    QF3
           5640           +    DIAG
                        129   
  0000     2800F4FF     130 &          OUT       &BYTE+FITTIZ1       ;
  0004     2800F5FF     131 &          OUT       &BYTE+FITTIZ2       ;
  0008     2800FBFF     132 &          OUT       &BYTE+FITTIZ3       ;
  000C     2E08F21A00   133            SNZ       CAMBUT,SEG          ;Con cambi
  0011     1747FF00     134            FCALL     71                  ;Funz. tes
  0015     2E04E02A00   135            SNZ       FLGESCLU,ESCI       ;
  001A     2D08F52000   136   SEG:     SKZ       FINCONT             ;Se=0 NO C
  001F     5E           137            ECNT                          ;
  0020     2D20F42700   138            SKZ       FCONTOR             ;Se=1 Cont
  0025     5D01         139            ICNT      1                   ;
  0027     152B00       140            CALL      XYFLIN              ;
  002A     18           141   ESCI:    FRET                          ;
                        142   
                        143   
                        144   
                        145   ;*****************  SUBROUTINE (F134) PER LA FACC

 PROG.: FRESA.0    T.P.A.: GPL1000 COMPILER       11/13/01      page 5

ADDRESS     OBJECT      LINE    SOURCE LINE

                        146   
  002B     5A00000000   147 & XYFLIN:  LINEAR    &LINEA
           0000000000
           0000000000
           0000000000
           000000
  0042     16           148            RET
                        149   
                        150   
                        151   ; ***** NOTE: FUNZIONE (F134) FUNZIONE DI FRESATA
                        152   
                        153   ;ELENCO PARAMETRI:
                        154   
                        155   ;01  --> BYTE FITTIZIO1
                        156   ;02  -->   "     "    2
                        157   ;03  -->   "     "    3 ESCLUSIONI
                        158   ;Parametri passati alla  --> LINEAR XYFLIN
                        159   ;04  --> MASCHERA ASSI
                        160   ;05  --> DIREZIONE ASSE
                        161   ;06  --> RATEIC
                        162   ;07  --> PASSO RESOL
                        163   ;08  --> QUOTA ASSE 1
                        164   ;09  --> QUOTA ASSE 2
                        165   ;10  --> QUOTA ASSE 3
                        166   ;11  --> DIAGONALE
                        167   
                        168   
  #87                   169   FUN      135,FLinAF5                   ;Fresata l
           00             +
           19             +
           1910           +    BYTE
           1D10           +    BYTE
           2110           +    BYTE
           4410           +    ASSI
           4510           +    DIREZ
           4620           +    RATEIC
           4820           +    RESOL
           4A40           +    QF1
           4E40           +    QF2
           5240           +    QF3
           5640           +    DIAG
                        170   
  0000     2800F4FF     171 &          OUT       &BYTE+FITTIZ1       ;
  0004     2800F5FF     172 &          OUT       &BYTE+FITTIZ2       ;
  0008     2800FBFF     173 &          OUT       &BYTE+FITTIZ3       ;
  000C     2E08F21A00   174            SNZ       CAMBUT,SEG          ;Con cambi
  0011     1747FF00     175            FCALL     71                  ;Funz. tes
  0015     2E04E02A00   176            SNZ       FLGESCLU,ESCI       ;
  001A     2D08F52000   177   SEG:     SKZ       FINCONT             ;Se=0 NO C
  001F     5E           178            ECNT                          ;
  0020     2D20F42700   179            SKZ       FCONTOR             ;Se=1 Cont
  0025     5D01         180            ICNT      1                   ;
  0027     152B00       181            CALL      XYFLIN              ;

 PROG.: FRESA.0    T.P.A.: GPL1000 COMPILER       11/13/01      page 6

ADDRESS     OBJECT      LINE    SOURCE LINE

  002A     18           182   ESCI:    FRET                          ;
                        183   
                        184   
                        185   ;*****************  SUBROUTINE (F135) PER LA FACC
                        186   
  002B     5A00000000   187 & XYFLIN:  LINEAR    &LINEA
           0000000000
           0000000000
           0000000000
           000000
  0042     16           188            RET
                        189   
                        190   
                        191   ; ***** NOTE: FUNZIONE (F135) FUNZIONE DI FRESATA
                        192   
                        193   ;ELENCO PARAMETRI:
                        194   
                        195   ;01  --> BYTE FITTIZIO1
                        196   ;02  -->   "     "    2
                        197   ;03  -->   "     "    3 ESCLUSIONI
                        198   ;Parametri passati alla  --> LINEAR XYFLIN
                        199   ;04  --> MASCHERA ASSI
                        200   ;05  --> DIREZIONE ASSE
                        201   ;06  --> RATEIC
                        202   ;07  --> PASSO RESOL
                        203   ;08  --> QUOTA ASSE 1
                        204   ;09  --> QUOTA ASSE 2
                        205   ;10  --> QUOTA ASSE 3
                        206   ;11  --> DIAGONALE
                        207   
                        208   
                        209   ;>>>>>>>> FUNZIONI DI FRESATA -  ELICOIDALE
                        210   
  #88                   211   FUN      136,FElicF1                   ;Fresata E
           00             +
           2B             +
           2510           +    BYTE
           2910           +    BYTE
           2D10           +    BYTE
           5010           +    ASSI
           5110           +    ASSIH
           5210           +    DIREZ
           5320           +    RATEIC
           5520           +    RESOL
           5740           +    QF3
           5B40           +    ARCO
           5F40           +    DIAG
           6340           +    QC1
           6740           +    QC2
           6B40           +    QF1
           6F40           +    QF2
           7340           +    RAGGIO
           7710           +    GIRI

 PROG.: FRESA.0    T.P.A.: GPL1000 COMPILER       11/13/01      page 7

ADDRESS     OBJECT      LINE    SOURCE LINE

                        212   
  0000     2800F4FF     213 &          OUT       &BYTE+FITTIZ1       ;
  0004     2800F5FF     214 &          OUT       &BYTE+FITTIZ2       ;
  0008     2800FBFF     215 &          OUT       &BYTE+FITTIZ3       ;
  000C     1747FF00     216            FCALL     71                  ;Funz. tes
  0010     2E08F21A00   217            SNZ       CAMBUT,SEG          ;Con cambi
  0015     2E04E02A00   218            SNZ       FLGESCLU,ESCI       ;
  001A     2D08F52000   219   SEG:     SKZ       FINCONT             ;Se=0 NO C
  001F     5E           220            ECNT                          ;
  0020     2D20F42700   221            SKZ       FCONTOR             ;Se=1 Cont
  0025     5D01         222            ICNT      1                   ;
  0027     152B00       223            CALL      XYFELIC             ;
  002A     18           224   ESCI:    FRET                          ;
                        225   
                        226   ;*****************  SUBROUTINE (F136) PER LA FACC
                        227   
  002B     5C00000000   228 & XYFELIC: HELIC     &ELICA
           0000000000
           0000000000
           0000000000
           0000000000
           0000000000
           0000000000
           0000000000
           00
  0054     16           229            RET
                        230   
                        231   
                        232   ; **** NOTE: FUNZIONE (F136 FUNZIONE DI FRESATA E
                        233   
                        234   ;ELENCO PARAMETRI:
                        235   
                        236   ;01  --> BYTE FITTIZIO1
                        237   ;02  -->   "     "    2
                        238   ;03  -->   "     "    3 ESCLUSIONI
                        239   ;Parametri passati alla  --> ELICOIDALE XYFELIC
                        240   ;04  --> MASCHERA ASSI CIRCOLARI
                        241   ;05 -->  MASCHERA ASSE LINEARE
                        242   ;06 -->  SENSO DI ROTAZIONE
                        243   ;07  --> RATEIC
                        244   ;08  --> PASSO RESOL
                        245   ;09  --> QUOTA ASSE 3
                        246   ;10  --> ARCO
                        247   ;11  --> DIAGONALE
                        248   ;12  --> QUOTA CENTRO ASSE 1
                        249   ;13  --> QUOTA CENTRO ASSE 2
                        250   ;14  --> QUOTA FINALE ASSE 1
                        251   ;15  --> QUOTA FINALE ASSE 2
                        252   ;16  --> RAGGIO
                        253   ;17  --> NUMERO GIRI
                        254   
                        255   
  #89                   256   FUN      137,FElicF2                   ;Fresata E

 PROG.: FRESA.0    T.P.A.: GPL1000 COMPILER       11/13/01      page 8

ADDRESS     OBJECT      LINE    SOURCE LINE

           00             +
           2B             +
           2510           +    BYTE
           2910           +    BYTE
           2D10           +    BYTE
           5010           +    ASSI
           5110           +    ASSIH
           5210           +    DIREZ
           5320           +    RATEIC
           5520           +    RESOL
           5740           +    QF3
           5B40           +    ARCO
           5F40           +    DIAG
           6340           +    QC1
           6740           +    QC2
           6B40           +    QF1
           6F40           +    QF2
           7340           +    RAGGIO
           7710           +    GIRI
                        257   
  0000     2800F4FF     258 &          OUT       &BYTE+FITTIZ1       ;
  0004     2800F5FF     259 &          OUT       &BYTE+FITTIZ2       ;
  0008     2800FBFF     260 &          OUT       &BYTE+FITTIZ3       ;
  000C     2E08F21A00   261            SNZ       CAMBUT,SEG          ;Con cambi
  0011     1747FF00     262            FCALL     71                  ;Funz. tes
  0015     2E04E02A00   263            SNZ       FLGESCLU,ESCI       ;
  001A     2D08F52000   264   SEG:     SKZ       FINCONT             ;Se=0 NO C
  001F     5E           265            ECNT                          ;
  0020     2D20F42700   266            SKZ       FCONTOR             ;Se=1 Cont
  0025     5D01         267            ICNT      1                   ;
  0027     152B00       268            CALL      XYFELIC             ;
  002A     18           269   ESCI:    FRET                          ;
                        270   
                        271   
                        272   ;*****************  SUBROUTINE (F137) PER LA FACC
                        273   
  002B     5C00000000   274 & XYFELIC: HELIC     &ELICA
           0000000000
           0000000000
           0000000000
           0000000000
           0000000000
           0000000000
           0000000000
           00
  0054     16           275            RET
                        276   
                        277   
                        278   ; **** NOTE: FUNZIONE (F137 FUNZIONE DI FRESATA E
                        279   
                        280   ;ELENCO PARAMETRI:
                        281   
                        282   ;01  --> BYTE FITTIZIO1
                        283   ;02  -->   "     "    2

 PROG.: FRESA.0    T.P.A.: GPL1000 COMPILER       11/13/01      page 9

ADDRESS     OBJECT      LINE    SOURCE LINE

                        284   ;03  -->   "     "    3 ESCLUSIONI
                        285   ;Parametri passati alla  --> ELICOIDALE XYFELIC
                        286   ;04  --> MASCHERA ASSI CIRCOLARI
                        287   ;05 -->  MASCHERA ASSE LINEARE
                        288   ;06 -->  SENSO DI ROTAZIONE
                        289   ;07  --> RATEIC
                        290   ;08  --> PASSO RESOL
                        291   ;09  --> QUOTA ASSE 3
                        292   ;10  --> ARCO
                        293   ;11  --> DIAGONALE
                        294   ;12  --> QUOTA CENTRO ASSE 1
                        295   ;13  --> QUOTA CENTRO ASSE 2
                        296   ;14  --> QUOTA FINALE ASSE 1
                        297   ;15  --> QUOTA FINALE ASSE 2
                        298   ;16  --> RAGGIO
                        299   ;17  --> NUMERO GIRI
                        300   
                        301   
  #8A                   302   FUN      138,FElicF3                   ;Fresata E
           00             +
           2B             +
           2510           +    BYTE
           2910           +    BYTE
           2D10           +    BYTE
           5010           +    ASSI
           5110           +    ASSIH
           5210           +    DIREZ
           5320           +    RATEIC
           5520           +    RESOL
           5740           +    QF3
           5B40           +    ARCO
           5F40           +    DIAG
           6340           +    QC1
           6740           +    QC2
           6B40           +    QF1
           6F40           +    QF2
           7340           +    RAGGIO
           7710           +    GIRI
                        303   
  0000     2800F4FF     304 &          OUT       &BYTE+FITTIZ1       ;
  0004     2800F5FF     305 &          OUT       &BYTE+FITTIZ2       ;
  0008     2800FBFF     306 &          OUT       &BYTE+FITTIZ3       ;
  000C     2E08F21A00   307            SNZ       CAMBUT,SEG          ;Con cambi
  0011     1747FF00     308            FCALL     71                  ;Funz. tes
  0015     2E04E02A00   309            SNZ       FLGESCLU,ESCI       ;
  001A     2D08F52000   310   SEG:     SKZ       FINCONT             ;Se=0 NO C
  001F     5E           311            ECNT                          ;
  0020     2D20F42700   312            SKZ       FCONTOR             ;Se=1 Cont
  0025     5D01         313            ICNT      1                   ;
  0027     152B00       314            CALL      XYFELIC             ;
  002A     18           315   ESCI:    FRET                          ;
                        316   
                        317   

 PROG.: FRESA.0    T.P.A.: GPL1000 COMPILER       11/13/01      page 10

ADDRESS     OBJECT      LINE    SOURCE LINE

                        318   ;*****************  SUBROUTINE (F138) PER LA FACC
                        319   
  002B     5C00000000   320 & XYFELIC: HELIC     &ELICA
           0000000000
           0000000000
           0000000000
           0000000000
           0000000000
           0000000000
           0000000000
           00
  0054     16           321            RET
                        322   
                        323   
                        324   
                        325   ;**** NOTE: FUNZIONE (F138 FUNZIONE DI FRESATA EL
                        326   
                        327   ;ELENCO PARAMETRI:
                        328   
                        329   ;01  --> BYTE FITTIZIO1
                        330   ;02  -->   "     "    2
                        331   ;03  -->   "     "    3 ESCLUSIONI
                        332   ;Parametri passati alla  --> ELICOIDALE XYFELIC
                        333   ;04  --> MASCHERA ASSI CIRCOLARI
                        334   ;05 -->  MASCHERA ASSE LINEARE
                        335   ;06 -->  SENSO DI ROTAZIONE
                        336   ;07  --> RATEIC
                        337   ;08  --> PASSO RESOL
                        338   ;09  --> QUOTA ASSE 3
                        339   ;01  --> ARCO
                        340   ;11  --> DIAGONALE
                        341   ;12  --> QUOTA CENTRO ASSE 1
                        342   ;13  --> QUOTA CENTRO ASSE 2
                        343   ;14  --> QUOTA FINALE ASSE 1
                        344   ;15  --> QUOTA FINALE ASSE 2
                        345   ;16  --> RAGGIO
                        346   ;17  --> NUMERO GIRI
                        347   
                        348   
                        349   
  #8B                   350   FUN      139,FElicF4                   ;Fresata E
           00             +
           2B             +
           2510           +    BYTE
           2910           +    BYTE
           2D10           +    BYTE
           5010           +    ASSI
           5110           +    ASSIH
           5210           +    DIREZ
           5320           +    RATEIC
           5520           +    RESOL
           5740           +    QF3
           5B40           +    ARCO

 PROG.: FRESA.0    T.P.A.: GPL1000 COMPILER       11/13/01      page 11

ADDRESS     OBJECT      LINE    SOURCE LINE

           5F40           +    DIAG
           6340           +    QC1
           6740           +    QC2
           6B40           +    QF1
           6F40           +    QF2
           7340           +    RAGGIO
           7710           +    GIRI
                        351   
  0000     2800F4FF     352 &          OUT       &BYTE+FITTIZ1       ;
  0004     2800F5FF     353 &          OUT       &BYTE+FITTIZ2       ;
  0008     2800FBFF     354 &          OUT       &BYTE+FITTIZ3       ;
  000C     2E08F21A00   355            SNZ       CAMBUT,SEG          ;Con cambi
  0011     1747FF00     356            FCALL     71                  ;Funz. tes
  0015     2E04E02A00   357            SNZ       FLGESCLU,ESCI       ;
  001A     2D08F52000   358   SEG:     SKZ       FINCONT             ;Se=0 NO C
  001F     5E           359            ECNT                          ;
  0020     2D20F42700   360            SKZ       FCONTOR             ;Se=1 Cont
  0025     5D01         361            ICNT      1                   ;
  0027     152B00       362            CALL      XYFELIC             ;
  002A     18           363   ESCI:    FRET                          ;
                        364   
                        365   
                        366   ;*****************  SUBROUTINE (F139) PER LA FACC
                        367   
  002B     5C00000000   368 & XYFELIC: HELIC     &ELICA
           0000000000
           0000000000
           0000000000
           0000000000
           0000000000
           0000000000
           0000000000
           00
  0054     16           369            RET
                        370   
                        371   
                        372   
                        373   ;**** NOTE: FUNZIONE (F139 FUNZIONE DI FRESATA EL
                        374   
                        375   ;ELENCO PARAMETRI:
                        376   
                        377   ;01  --> BYTE FITTIZIO1
                        378   ;02  -->   "     "    2
                        379   ;03  -->   "     "    3 ESCLUSIONI
                        380   ;Parametri passati alla  --> ELICOIDALE XYFELIC
                        381   ;04  --> MASCHERA ASSI CIRCOLARI
                        382   ;05 -->  MASCHERA ASSE LINEARE
                        383   ;06 -->  SENSO DI ROTAZIONE
                        384   ;07  --> RATEIC
                        385   ;08  --> PASSO RESOL
                        386   ;09  --> QUOTA ASSE 3
                        387   ;10  --> ARCO
                        388   ;11  --> DIAGONALE

 PROG.: FRESA.0    T.P.A.: GPL1000 COMPILER       11/13/01      page 12

ADDRESS     OBJECT      LINE    SOURCE LINE

                        389   ;12  --> QUOTA CENTRO ASSE 1
                        390   ;13  --> QUOTA CENTRO ASSE 2
                        391   ;14  --> QUOTA FINALE ASSE 1
                        392   ;15  --> QUOTA FINALE ASSE 2
                        393   ;16  --> RAGGIO
                        394   ;17  --> NUMERO GIRI
                        395   
                        396   
  #8C                   397   FUN      140,FElicF5                   ;Fresata E
           00             +
           2B             +
           2510           +    BYTE
           2910           +    BYTE
           2D10           +    BYTE
           5010           +    ASSI
           5110           +    ASSIH
           5210           +    DIREZ
           5320           +    RATEIC
           5520           +    RESOL
           5740           +    QF3
           5B40           +    ARCO
           5F40           +    DIAG
           6340           +    QC1
           6740           +    QC2
           6B40           +    QF1
           6F40           +    QF2
           7340           +    RAGGIO
           7710           +    GIRI
                        398   
  0000     2800F4FF     399 &          OUT       &BYTE+FITTIZ1       ;
  0004     2800F5FF     400 &          OUT       &BYTE+FITTIZ2       ;
  0008     2800FBFF     401 &          OUT       &BYTE+FITTIZ3       ;
  000C     2E08F21A00   402            SNZ       CAMBUT,SEG          ;Con cambi
  0011     1747FF00     403            FCALL     71                  ;Funz. tes
  0015     2E04E02A00   404            SNZ       FLGESCLU,ESCI       ;
  001A     2D08F52000   405   SEG:     SKZ       FINCONT             ;Se=0 NO C
  001F     5E           406            ECNT                          ;
  0020     2D20F42700   407            SKZ       FCONTOR             ;Se=1 Cont
  0025     5D01         408            ICNT      1                   ;
  0027     152B00       409            CALL      XYFELIC             ;
  002A     18           410   ESCI:    FRET                          ;
                        411   
                        412   
                        413   ;*****************  SUBROUTINE (F140) PER LA FACC
                        414   
  002B     5C00000000   415 & XYFELIC: HELIC     &ELICA
           0000000000
           0000000000
           0000000000
           0000000000
           0000000000
           0000000000
           0000000000

 PROG.: FRESA.0    T.P.A.: GPL1000 COMPILER       11/13/01      page 13

ADDRESS     OBJECT      LINE    SOURCE LINE

           00
  0054     16           416            RET
                        417   
                        418   
                        419   ;**** NOTE: FUNZIONE (F140 FUNZIONE DI FRESATA EL
                        420   
                        421   ;ELENCO PARAMETRI:
                        422   
                        423   ;01  --> BYTE FITTIZIO1
                        424   ;02  -->   "     "    2
                        425   ;03  -->   "     "    3 ESCLUSIONI
                        426   ;Parametri passati alla  --> ELICOIDALE XYFELIC
                        427   ;04  --> MASCHERA ASSI CIRCOLARI
                        428   ;05 -->  MASCHERA ASSE LINEARE
                        429   ;06 -->  SENSO DI ROTAZIONE
                        430   ;07  --> RATEIC
                        431   ;08  --> PASSO RESOL
                        432   ;09  --> QUOTA ASSE 3
                        433   ;10  --> ARCO
                        434   ;11  --> DIAGONALE
                        435   ;12  --> QUOTA CENTRO ASSE 1
                        436   ;13  --> QUOTA CENTRO ASSE 2
                        437   ;14  --> QUOTA FINALE ASSE 1
                        438   ;15  --> QUOTA FINALE ASSE 2
                        439   ;16  --> RAGGIO
                        440   ;17  --> NUMERO GIRI
                        441   
                        442   
                        443   
                        444   ;>>>>>>>>>>>>>>> FUNZIONI DI FRESATA -  CIRCOLARE
                        445   
  #91                   446   FUN      145,FCircF5                   ;Fresata C
           00             +
           22             +
           1F10           +    BYTE
           2310           +    BYTE
           2710           +    BYTE
           4A10           +    ASSI
           4B10           +    SENSO
           4C20           +    RATEIC
           4E20           +    RESOL
           5040           +    ARCO
           5440           +    QC1
           5840           +    QC2
           5C40           +    QF1
           6040           +    QF2
           6440           +    RAGGIO
           6810           +    GIRI
                        447   
  0000     2800F4FF     448 &          OUT       &BYTE+FITTIZ1       ;
  0004     2800F5FF     449 &          OUT       &BYTE+FITTIZ2       ;
  0008     2800FBFF     450 &          OUT       &BYTE+FITTIZ3       ;
  000C     2E08F21A00   451            SNZ       CAMBUT,SEG          ;Con cambi

 PROG.: FRESA.0    T.P.A.: GPL1000 COMPILER       11/13/01      page 14

ADDRESS     OBJECT      LINE    SOURCE LINE

  0011     1747FF00     452            FCALL     71                  ;Funz. tes
  0015     2E04E02A00   453            SNZ       FLGESCLU,ESCI       ;
  001A     2D08F52000   454   SEG:     SKZ       FINCONT             ;Se=0 NO C
  001F     5E           455            ECNT                          ;
  0020     2D20F42700   456            SKZ       FCONTOR             ;Se=1 Cont
  0025     5D01         457            ICNT      1                   ;
  0027     152B00       458            CALL      XYCIRCLE            ;
  002A     18           459   ESCI:    FRET                          ;
                        460   
                        461   
                        462   ;*****************  SUBROUTINE (F145) PER LA FACC
                        463   
  002B     5B00000000   464 & XYCIRCLE:CIRCLE    &CIRCO
           0000000000
           0000000000
           0000000000
           0000000000
           0000000000
           0000
  004B     16           465            RET
                        466   
                        467   
                        468   ; **** NOTE: FUNZIONE (F145 FUNZIONE DI FRESATA C
                        469   
                        470   ;ELENCO PARAMETRI:
                        471   
                        472   ;01  --> BYTE FITTIZIO1
                        473   ;02  -->   "     "    2
                        474   ;03  -->   "     "    3 ESCLUSIONI
                        475   ;Parametri passati alla  --> CIRCOLARE XYCIRCLE
                        476   ;04  --> MASCHERA ASSI
                        477   ;05  --> SENSO ROTAZIONE
                        478   ;06  --> RATEIC
                        479   ;07  --> PASSO RESOL
                        480   ;08  --> ARCO
                        481   ;09  --> QUOTA CENTRO ASSE 1
                        482   ;10  --> QUOTA CENTRO ASSE 2
                        483   ;11  --> QUOTA FINALE ASSE 1
                        484   ;12  --> QUOTA FINALE ASSE 2
                        485   ;13  --> RAGGIO
                        486   ;14  --> NUMERO GIRI

Number of bytes used: 1166

No. of errors detected: 0

