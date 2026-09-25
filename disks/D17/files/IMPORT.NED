//  **************** FILE : IMPORT.ENG (lingua : inglese) *************
00"@!1@"
65"Confirm interruption (Y/N) " 				     //(1)	messaggio 1
20"import"							     //(2)	messaggio 2
20"delete"							     //(3)	messaggio 3
20"import + comp."						     //(4)	messaggio 4
20"command"							     //(5)	messaggio 5
3"Y/N"								     //(6)	messaggio 6

//ERRORI che si possono verificare sui primi sei record di IMPORT.CMD

00"@!20@"
45"(20) !! Impossible open IMPORT.CMD"                               //+0(20)   errore 1
45"(21) !! ERROR syntax error to record nø"                          //+1(21)   errore 2
60"(22) !! ERROR driver not specified to record nø"                  //+2(22)   errore 3
70"(23) !! ERROR start directory non found"                          //+3(23)   errore 4
75"(24) !! ERROR errors file directory not found"                    //+4(24)   errore 5
55"(25) !! line or/and columne wrong"                                //+5(25)   errore 6
70"(26) !! background or/and forground color not valid"              //+6(26)   errore 7
65"(27) !! ERROR value not valid to record nø "                      //+7(27)   errore 8
60"(28) !! ERROR IMPORT.CMD file not valid"                          //+8(28)   errore 9
70"(29) !!IMPOSSIBLE change video mode setting"                      //+9(29)   errore 10


//ERRORI che si possono verificare dal 7ø record in poi

00"@!50@"
50" (50)  ERROR  sintax error                  !!!   "		     //+0(50)	errore 1
50" (51)  ERROR  value not numerical                 "		     //+1(51)	errore 2
50" (52)  ERROR  on lenght of record                 "		     //+2(52)	errore 3
50" (53)  ERROR  on command field                    "		     //+3(53)	errore 4
50" (54)  ERROR  execution failed                    "		     //+4(54)	errore 5
50" (55)  NAVETTA.CMD not found  o non modificabile  "		     //+5(55)	errore 6
50" (56)  ERROR  on communication file open          "		     //+6(56)	errore 7
50" (57)  IMPORT.CMD non presente o non modificabile "		     //+7(57)	errore 8
50" (58)  ERROR  programme name not assigned         "		     //+8(58)	errore 9
50" (59)  ERROR  mother programma not founde         "		     //+9(59)	errore 10
50" (60)  ERROR  on format of IMPORT.CMD file        "		     //+10(60)	errore 11
50" (61)  ERROR  record number not sequential        "		     //+11(61)	errore 12
50" (62)  ERROR  too many records number (> 200)     "		     //+12(62)	errore 13
