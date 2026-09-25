//  **************** FILE : CNC90.NED (lingua : nederlands) ******************
 3"J@/@N"
25"BEVESTIG@ (%s) ?@"
25"@%s @bezig.."
10"HELP"
10"FOUT"
15"@<Alt+H=@HELP@>@"
50"bestand@ %s @niet gevonden"
50"bestand@ %s @bestaat"
50"fout in toegang tot bestand@ %s@"
50"floppy@ %c: @vol"
50"fout in periferie"
50"fout in printer"
50"floppy schrijf beveiligt"
50"floppy niet klaar in station@ %c:@"
50"fout in disk"
50"interne fout"
50"niet genoeg geheugen"
50"toegang geweigert"
50"Niet behandelt"                                //msg 18
50"Nogmaals proberen@ (%s) ?@"                    //msg 19
50"Bevestig stoppen@ (%s) ?@"                     //msg 20
50"Kan bestand niet openen @ %s@"                 //msg 21
50"Programma@ %s @niet in directory"              //msg 22
50"Programma@ %s @in directory"                   //msg 23
50"Fout  : taal bestand niet korrekt"             //msg 24
70"Fout  : kan VGA video mode niet instellen"     //msg 25
70"Error : kan letterfont niet in  stellen"       //msg 26
70"Error : environ@ %s @niet in orde"             //msg 27
70"Error : environ@ %s @not gevonden"             //msg 28
70"Error : bestand@ %s @niet in orde"             //msg 29
70"Error : bestand@ %s @niet gevonden"            //msg 30
03"R@/@L"                                         //msg 31 caratteri destro/sinistro nazionale
08"Naam"                                          //msg 32
03"Num"                                           //msg 33
03"Typ"                                           //msg 34
03"Inp"                                           //msg 35
03"Out"                                           //msg 36
20"Programma"                                     //msg 37
20"List"                                          //msg 38
20"Bar-Code"                                      //msg 39
40"Bruikbare toetsen : @<PGUP> <PGDW> <ESC>@"     //msg 40
40"Bestanden Directory"                           //msg 41
40"Fouten lijst"                                  //msg 42
08"Escl"                                          //msg 43
40"fout : Directory vol"                          //msg 44
00"@!065@"                                 <---- *****
01""                                      //msg 65 libero !!??
80"@CNC90 %s - T.P.A. SpA   Sesto S. G."  //msg 66 INTESTAZIONE ESEGUIBILI
14"@00000000000000@"                      //msg 67 Maschera psw su menu di plancia
01""                                      //msg 68 libero !!??
01""                                      //msg 69 libero !!??
//
00"@!070@"                 <---- ***** OFFSETS SUGLI ESEGUIBILI
04"@100@"                  //offset PLANCIA.EXE
04"@500@"                  //offset EDIPART.EXE   (msg generali)
04"@600@"                  //offset EDIGRAF.EXE
04"@1000@"                 //offset COMPILA.EXE
04"@1000@"                 //offset EDIPART.EXE
04"@1000@"                 //offset EDIPAR.EXE
04"@1000@"                 //offset EDILIST.EXE
04"@1000@"                 //offset COPIA.EXE
04"@1000@"                 //offset ESTERNO.EXE
04"@1000@"                 //offset VENTOSE.EXE
04"@1000@"                 //offset IMPORT.EXE
04"@1000@"                 //offset MSGEDIATT
04"@1030@"                 //offset MSGEDITEC0
04"@1200@"                 //offset MSGEDITEC1öMSGEDITEC10
04"@1230@"                 //offset MSGEDITEC11
04"@1270@"                 //offset MSGEDITEC12
04"@1300@"                 //offset MSGEDITEC13
04"@1000@"                 //offset MSGPRINTDIR
04"@1000@"                 //offset per prossimo eseguibile
04"@1000@"                 //offset per prossimo eseguibile
04"@1000@"                 //offset per prossimo eseguibile
04"@1000@"                 //offset per prossimo eseguibile
04"@1000@"                 //offset per prossimo eseguibile
04"@1000@"                 //offset per prossimo eseguibile
04"@1000@"                 //offset per prossimo eseguibile
04"@1000@"                 //offset per prossimo eseguibile
04"@1000@"                 //offset per prossimo eseguibile
04"@1000@"                 //offset per prossimo eseguibile
04"@1000@"                 //offset per prossimo eseguibile
04"@1000@"                 //offset per prossimo eseguibile
//
 0"@!100@"
80"AUTOMATIC"
 6"auto"
 6"start"
 6"stop"
 6"set-p"
 6"hand"
 6"eind"
 6"l_list"
 6"s_list"
 6"diagn"
 5"menu"
33"Programma Bewerken"
33"Programma Kompileren"
33"Technische Parameters"
33"Gereedschap Parameters"
33"Gereedschap Uitrusting"
33"Lijsten bewerken"
33"Bestanden Beheer"
33"Systeem Diversen"
33"CAD Starten"
33"Verbinding in Lan"
33"Start extern programma"
33"Verander station voor coord.assen"
33"Shell naar DOS"
33"Verlaat Systeem CNC90"
33"Generale Parameters"
33"Parameters Groep @1@"
33"Parameters Groep @2@"
33"Parameters Groep @3@"
33"Parameters Groep @4@"
33"Parameters Groep @5@"
33"Parameters Groep @6@"
33"Parameters Groep @7@"
33"Parameters Groep @8@"
33"Parameters Groep @9@"
33"Parameters Groep @10@"
33"Korrektie Parameters"
33"Instellingen"
33"Klant Parameters"
33"Uitrusting @%d@"
33"-"
33"-"
33"-"
33"-"
33"-"
33"-"
33"-"
33"-"
33"-"
80"-"
63"-"
40"Programma @%s.%d@ te lang"
40"Programma @%s.%d@ niet gecompileeerd"
60"Functie @%d@ van station @%d@ gekopieerd"
60"Verzend functie @%03d@ naar station @%2d@"
60"Verzend parameters naar station @%2d@"
60"Verzend programma @%s@ naar station @%d@"
60"Module : @%d@"
60"Bestand van functie @%s.%d@ niet gecompileeerd"
60"Korrektie param. verzenden naar station @%d@"
60"Te veel coordinaten voor beschikbaar geheugen"
60"Buiten coord. bereik @%d@ tab. @%d@ axis @%c@"
60"Station @%d@ van module @%d@ niet geconfigureerd"
60"Taak"
60"Station nummmer verschilt van configuratie"
60"Station : @%d@"
64"@|50|@Druk op functie toets voor geselecteerde bewerking :"
64"@F1@           Roep Automatische bewerking aan"
64"@F4@           Roep Set Point aan"
64"@F5@           Roep Handbediening aan"
64"@F7@           Roep lijst van directory"
64"@F8@           Bewaar huidige lijst in list directory"
64"@F9@           Roep Diagnose aan"
64"@F10@          Terug naar Menu"
64"@F11@          Bewerk DV2"
64""
64"   AUTOMATIC"
64"@ESC@          Wis een plaats"
64"@TAB@          Verschuif cursor een plaats rechts"
64"@SHIFT+TAB@    Verschuif cursor een plaats links"
64"@RETURN@       Spring naar volgend veld om te bewerken"
64"@CTRL+Y@       Verwijder regel"
64"@CTRL+U@       Maak de laatste regel verwijdering ongedaan"
64"@CTRL+RETURN@  Voeg een regel in"
64"@CTRL+HOME@    Ga direkt naar eerste regel"
64"@CTRL+END@     Ga direkt naar de laatste regel"
64"@CTRL+D@       Verwijder huidige lijst"
64"@CTRL+N@       Geef het aantal herhalingen"
64"@CTRL+S@       Zoek een woord in de lijst"
64"@PGUP@         Pagina terug"
64"@PGDW@         Pagina verder"
64"@\x18@            Vorige regel"
64"@\x19@            Volgende regel"
64"@F2@           Uitvoeren van lijst"
64"@F3@           Zet de lijst in stop status"
64"@F6@           Stop lijst in bewerking en exit"
64"@F7@           Roep lijst van directory"
64"@F8@           Bewaar huidige lijst in list directory"
64"@F10@          Uitvoeren van bewerkingen uit directory"
64""
64"   SET POINT & DIAGNOSE"
64"@F2@           Voer procedure uit"
64"@F3@           Zet programma in stop status"
64"@F6@           Einde programma bewerking"
64""
64"   MENU & HELP"
64"@ESC@          Exit van MENU of van HELP scherm"
64"@PGUP@         Pagina terug"
64"@PGDW@         Pagina verder"
64"@\x18@            Vorige line"
64"@\x19@            Volgende regel"
64"@ENTER@        Selecteer gemarkeerd deel"
64""
64"@ALT+M@        Enter Monitor"
64"@ALT+R@        Herhaal parameters, programma's en functie verzending"
64"@CTRL+R@       Maak het scherm schoon."
08"-"
80"Type @EXIT@ + @<ENTER>@ om terug te gaan naar CNC90."
40"Druk op @%s@ om verder te gaan"
50" Fout in Initialisatie ."
30" Nog eens proberen @%s@ ?"
65"Uitrusting niet overeenkomstig met paneel @%s@"
65"Kan niet AUTOMATISCH STARTEN, SET POINT NIET UITGEVOERD !"
65"Kan Bestand @%s@ niet openen"
65"Paneel @%s@ NIET aanwezig in directory"
65"Geef het nummer van de UITRUSTING in de machine"
65"Verkeer numeriek veld in paneel @%s@"
65"Functie bestaat niet : Paneel %s, Func. %d, Stat. %d"
65"Programma te lang voor het geheugen"
65"Bewerking niet mogenlijk in paneel @%s@"
65"Fout in gecompileerd bestand van paneel @%s@"
 5"dir"
 6"f_rate"
65"Geef de naam van de bestemmings lijst"
65"Lijst @%s@ bestaat al, bewaren afgebroken !"
65"Kan de lijst @%s@ niet bewaren , afgebroken !"
14"*111Menu"
65"Geef het wachtwoord om door te gaan "
65"Bevestig exit naar DOS @(%s)@ ?"
65"Fout nummer in param. in functie n. @%s@"
65"Wachtwoord fout , kan niet verder gaan."
50"Vacuum configuratie fout of niet aanwezig"
65"Lijst niet gevonden, kan niet AUTOMATISCH starten!"                     26
65"CAD vacuum configutie van bestand @%s@ niet gevonden"                   27
65"Te veel druk geselecteeerd op half-veld in programma @%s@"              28
65"Druk in programma @%s@ buiten limieten"                                 29
65"CAD gereserveerde code nummer fout of onvoldoende"                      30
65"Programma @%s@ niet compileerd , uitvoering afgebroken"                 31
65"Geef bewerkings code met BARCODE"                                       32
65"Programma niet gevonden lijst @%s@"                                     33
65"Programma @%s@ niet uitvoerbaar in gespecificeerd veld"                 34
65"Geef veld om te vinden"                                                 35
65"Fout in lijst bestand @%s@"                                             36
60"HELP Systeem Fout N.@%d@"                                               37
60"@<%d/%m/%y> <%H:%M:%S>@"                                                38
60"@%s <%-*s> <%-*s %-*s>\x0A@"                                            39
60"@<%d/%m/%y> <%H:%M:%S>@"                                                40
60"@%s\x0A<%s>\x0A@"                                                       41
60"@%s <%s>\x0A@"                                                          42
06"@DIAGN1@"                                                               43
06"@DIAGN2@"                                                               44
06"@DIAGN3@"                                                               45
06"@DIAGN4@"                                                               46
06"@DIAGN5@"                                                               47
06"@DIAGN6@"                                                               48
06"@DIAGN7@"                                                               49
06"@DIAGN8@"                                                               50
06"@DIAGN@"                                                                51
06"exit"                                                                   52
65"Programma uitrusting @%d@, Machine uitrusting @%d@."                    53
//
 0"@!500@"
75"PARAMETRIE"
64"@|16|ESC@               Exits zonder de laatste wijzigingen te bewaren"
64"@END@               Exits met bewaren van laatste wijzigingen"
64"@PGUP@              Ga pagina terug"
64"@PGDW@              Ga pagina verder"
64"@\x18@                 Ga regel terug"
64"@\x19@                 Ga regel verder"
64"@ENTER@             Ga naar volgend invoer veld"
64"@F1@                Herhaal laatste invoeging"
64"@F2@                Tel 32 op in invoerveld"
64"@F3@                Trek 32 af in invoerveld"
64"COLORS :          0=zwart,       1=Blauw,       2=Groen"
64"                  3=Azuur,       4=Rood,        5=Magenta"
64"                  6=Geel,        7=Wit,         8=Grijs"
64"                  9=Fel blauw,   10=Fel Groen,  11=Fel Azuur"
64"                  12=Fel Rood,   13=Fel Magenta"
64"                  14=Fel Geel,   15=Fel Wit"
65"Data niet gevonden in bestand (@%s@) !"
65"Data fout in bestand (@%s@) !"
65"Lees fout in bestand (@%s@) !""
65"Schrijf fout in bestand (@%s@) !"
65"Onbekend meet stelsel"
65"Fout in Help boodschappen"
65"Fout in parameter boodschappen"
15"Pag @%d@/@%d@"
25"-"
50"Bevestig stoppen ?"
//
00"@!600@"                     <-- ***** EDIGRAF.EXE      (Luisa)
30"BEWERKEN"                   //0    -545
20"NAAM"                       //+1    -546
20"Commentaar"                 //+2    -547
20"Metr./inch @ (M/I)@"        //+3    -548
20"Lengte @ L@"                //+4    -549
20"Breedte@ H@"                //+5    -550
20"Dikte  @ S@"                //+6    -551
20"Uitrusting (0-49)@"         //+7    -552
20"Vacuum codering"            //+8    -553
08"Datum"                      //+9    -554
04"Zijde"       //piece sides  //+10   -555
06"Werkvlak"                   //+11   -556
20""           //free          //+12   -557
10"N.o prg"                    //+18   -563
10"Pagina "                    //+19   -564
60"@|16|TAB@       Wissel selectie tussen NAAM en pagina" //+15 max 25  //HELP SU DIRETTORIO
60"@PG UP@     Ga pagina terug"                           //+16
60"@PG DN@     Ga pagina verder"                          //+17
60"@HOME@      Ga naar eerste pagina"                     //+18
60"@END@       Ga naar laatste pagina"                    //+19
60"@0ö9;AöZ@   Vind programma's met gekozen naam"         //+20
60"@\x18@         Ga regel terug op scherm"               //+21
60"@\x19@         Ga regel verder op scherm"              //+22
60"@\x1A \x1B@       Verschuif pagina horizontaal"        //+23
60"@ALT+E@     Zoek pad naam"
60"@ENTER@     Bevestig"                                  //+24
60"@ESC@       Stop"                                      //+25
60""                                                      //+26
60"     Op meerdere selecties :"                          //+27
60"@SPATIE@     Selectie op regel met ''"                //+28
60"@SPATIE@     De-selectie op regel met ''"             //+29
// selecties op rechter zone (norm. 8)
08"PROGRAM."                        //+23  -568
08"INVOEG."                        //+24  -569
08"INVOEG."                        //+25  -570
08"WIJZIG"                          //+26  -571
08"VERWIJD."                        //+27  -572
08"REGEL"                           //+28  -573
08"MATEN"                           //+29  -574
08"FREES R."                        //+30  -575
08"ZIJDE"                           //+39  (2ø pagina)
08"VACUUM"                          //+40
08"ESCL"                            //+41
08"@?@"                             //+42
08"@?@"               samenvoegen   //+43
08"@?@"               zoom          //+44
08"@?@"               zoom off      //+45
08"@?@"                             //+46
// menu van selectie FILES ( 10)
20"@0 @OPENEN@/@NIEUW"             //+31   -576
20"@1 @BEWAAR"                     //+32   -577
20"@2 @BEWAAR ALS"                 //+32   -577
20"@3 @VERWIJDER"                  //+33   -578
20"@4 @KOPIEER"                    //+34   -579
20"@5 @NW. NAAM"                   //+35   -580
20"@6 @PRINT"                      //+36   -581
20"@7 @DIRECTORY"                  //+37   -582
20"@8 @UITVOERING"                 //+38   -583
20"@9 @KOMPILEER"                  //+39   -584
20"@A @TERUG"                      //+40   -585
20"@B @MODULE WIJZIGEN"            //+57
20"@A @MENU 3"                     //+58
20""                               //+59
20""                               //+41   -586
//MENU` 3
33"Programma bewerken"             //+62
33"Module Change"                  //+63
33"Programma kompileren"           //+64
33"Technische Parameters"          //+65
33"Gereedschap Parameters"         //+66
33"Uitrusting"                     //+67
33"Lijsten bewerken"               //+68
33"Bestanden beheer"               //+69
33"CAD starten"                    //+70
33"Extern Programma"               //+71
33""                               //+72
// menu on working selection
10"WERKVLAK"                     //+43   -588
20"SNEL@  x,y,z H@"              //+44   -589
20"SNEL@ x,y,z,w,v H@"           //+45   -590
20"BOREN"                        //+46   -591
20"ZAAG x"                       //+47   -592
20"ZAAG y"                       //+48   -593
20"FREZEN"                       //+49   -594
20"SPECIAAL"                     //+50   -595
20"INVOEGEN"                     //+51   -596
20"SUBPROGRAMMA'S"               //+52   -597
20"BOREN SPECIAAL"               //+53   -598
20"@?@"                          //+54   -599
20"@?@"                          //+55   -600
20"@?@"                          //+55   -600
20"@?@"                          //+55   -600
20"@?@"                          //+55   -600
//              menu of holes
20"BOREN@ (x,y,z)@"              //+56   -601
20"BOREN@ (x,y; u,a)@"           //+57   -602
20"RIJEN BORING x"               //+58   -603
20"RIJEN BORING y"               //+59   -604
20"HERHAAL x"                    //+60   -605
20"HERHAAL y"                    //+61   -606
20"HERHAAL xy"                   //+62   -607
20"HERHAAL xy (u,a)"             //+63   -608
20"BOREN IN CIRKEL"              //+64   -609
20"@?@"                          //+55   -600
20"@?@"                          //+55   -600
20"@?@"                          //+55   -600
//              menu of milling  
20"PLAATSEN@ (x,y,z)@"           //+65   -610
20"PLAATSEN@ (x,y; u,a)@"        //+66   -611
20"@L1 (x,y,z)@"                 //+67   -612
20"@L2 (x,y; u,a)@"              //+68   -613
20"@L3 (u,a)@"                   //+69   -614
20"@L4 (tg; u)@"                 //+70   -615
20"@C1 (x1,x2; c; rot)@"         //+71   -616
20"@C2 (x,y; u; rot)@"           //+72   -617
20"@C3 (c; a; rot)@"             //+73   -618
20"@C4 (tg; x,y; rot)@"          //+74   -619
20"HELICOIDAL C1"                //+75   -620
20"HELICOIDAL C2"                //+76   -621
20"HELICOIDAL C3"                //+77   -622
20"OVAAL"                        //+78   -623
20"LIJN VERBINDING"              //+79   -624
20"RADIUS VERBINDING"            //+80   -625
20"@C5 (xi,yi; x,y)@"            //+81   -626
20"@?@"                          //+82   -627
//              menu of specials
20"VERTRAGING"                   //+83   -628
20"KOMMENTAAR"                   //+84   -629
20"METEN @L@"                    //+85   -630
20"METEN @H@"                    //+86   -631
20"METEN @S@"                    //+87   -632
20"OFFSET"                       //+88   -633
20"ZAAG Aø"                      //+89   -634
20"@?@"                          //+55   -600
20"@?@"                          //+55   -600
20"@?@"                          //+55   -600
20"@?@"                          //+55   -600
20"@?@"                          //+55   -600
//              menu of insertion
20"PLATE"                        //+90   -635
20"BUSH"                         //+91   -636
20"HINGE"                        //+92   -637
20"PLANE SUPPORT"                //+93   -638
20"GENERIC @1@"                  //+94   -639
20"GENERIC @2@"                  //+95   -640
20"PINS"                         //+96   -641
20"@?@"                          //+97   -642
20"@?@"                          //+55   -600
20"@?@"                          //+55   -600
//              menu of special holes
20"HOLE WITH DUMP"               //+98   -643
20"TAPPING"                      //+99   -644
20"@?@"                          //+100  -645
20"@?@"                          //+101  -646
20"@?@"                          //+55   -600
//
20"@?@"    disponibile per nuovo //+146
20"@?@"           sottomenu      //+147
20"@?@"                          //+148
20"@?@"                          //+149
20"@?@"                          //+150
20"@?@"                          //+151
// MESSAGGI GENERALI
25"@F11=DV1@"                      //+152
20"Start"      //msg su modulo     //+153
20"Nieuw"        //msg su modulo   //+154
30"Print met SUB@ (%s) ?@"         //+155
25"Aankomst"                       //+156
25"Nieuwe naam"                    //+157
20"@Rf@ niet gevonden"             //+158
30"Tekst invalide"                 //+159
30"Veld@ %s @fout"                 //+160
30""                               //+161
30""                               //+162
30""                               //+163
30""                               //+164
30""                               //+165
30""                               //+166
30""                               //+167
30""                               //+168
30""                               //+169
30""                               //+170
30""                               //+171
//HELP SU OPEN/NEW
20"@ESC@   Afbreken"                               //+172
20"@ENTER@ Bevestigen"                             //+173
20"@\x18 \x19@   Selectie"                         //+174
20"@PG UP@ Pagina verder"                          //+175
20"@PG DN@ Pagina terrug"                          //+176
20""                                               //+177
//HELP SU MENU <-
50"@|17|HOME@      Selecteer eerste veld"    max 25         //+178
50"@END@       Selecteer laatste  veld"                     //+179
50"@\x18 \x19@       Verplaats vertikale selectie"          //+180
50"@\x1A \x1B@       Verplaats horizontale selectien"       //+181
50"@PG UP/DN@  Ga naar volgende/vorige pagina"              //+182
50"@ENTER@     Bevestig selectie"                           //+183
50"@TAB@       Ga naar menu rechts"                         //+184
50"     Beschikbare functies :"                             //+185
50"PROGRAM.   Selectie in Hoofd Menu"                       //+186
50"INVOEG.   Invoegen regel omhoog  "                     //+187
50"INSERT D   Invoegen regel omlaag  "                     //+188
50"WIJZIG     Wijzig een regel"                             //+189
50"VERWIJDER  Verwijder een of meer regels"                 //+190
50"REGEL      Ga naar regel met nummer"                     //+191
50"MATEN      Geef de div. paneel maten ed."                //+192
50"FREES R.   Grafische voorstelling gecorrig. frees pad"   //+193
50"ZIJDE      Verander de bewerkings zijde"                 //+194
50""                                                       //+195
50""                                                       //+196
50""                                                       //+197
50""                                                       //+198
50""                                                       //+199
50""                                                       //+200
50""                                                       //+201
50""                                                       //+202
//HELP SU MENU ->
50"@|21|@     Functie toetsen in programma bewerken:"  max 30  //+203
50""                                                     //+204
50"@HOME@      Selecteer de eerste regel"              //+205
50"@END@       Selecteer de laatste regel"               //+206
50"@\x18@         Selecteer vorige regel"            //+207
50"@\x19@         Selecteer volgende regel"          //+208
50"@\x1A \x1B@       Selecteer de tweede pagina"     //+209
50"@PG UP@     Selecteer vorige pagina"              //+210
50"@PG DN@     Selecteer volgende pagina"            //+211
50"@Alt+G@     Grafisch scherm"                      //+212
50"@Alt+S@     Sub scherm met subprogramma"          //+213
50"@Alt+L@     ISO- scherm"                          //+214
50"@Alt+D@     Scherm met numerieke parameters"      //+215
50"@Alt+T@     Grafisch scherm met groep"            //+216
50"@Ctrl \x1A@    Verschuif op XYZ veld"             //+217
50"@Ctrl \x1B@    Verschuif op XYZ veld"             //+218
50"@ENTER@     Bevestig en ga naar volgende regel"   //+219
50"@Ctrl+Y@    Verwijder de actuele regel"           //+220
50""                                                 //+221
50"@TAB@       Ga naar het linker menu"              //+222
50"@0 \xF6 F@     Richting selecteren op linker menu"  //+223
50""                                                 //+224
//HELP SU INSERT/MODIFICA
50"@|24|TAB@        Ga naar volgend veld"  max 25    //+225
50"@SHIFT-TAB@  Ga naar vorig veld"                  //+226
50"@\x19@          Ga regel terug"                   //+227
50"@\x18@          Ga naar volgende regel"           //+228
50"@HOME@       Ga naar het eerste veld"             //+229
50"@END@        Ga naar het laatste veld"            //+230
50"@SPACE@      Bewerken met begeleiding @(\x01)@"   //+231
50"@ENTER@      Bevestig"                            //+232
50"@ESC@        Reset de operatie"                   //+233
50"@Alt+G@              Open/Dicht Grafisch scherm"        //+234
50"@Alt+T@      Parameters voor@ T @veld"                  //+235
50"@Alt+D@      Venster met numerieke parameters"          //+236
50""                                                       //+237
50"     On SUBPROGRAM : "                                  //+238
50"@Alt+P@     Subprogramma selectie in directory"         //+239
50"@Alt+S@     Venster met subprogramma"                   //+240
50""                                                       //+241
50"     On MODIFY : "                                      //+242
50"@PG UP@      Ga een regel terug"                        //+243
50"@PG DN@      Ga een regel verder"                       //+244
50""                                                       //+245
50"     Een fout bij OPENEN : "                            //+246
50"@Ctrl+Y@     Verwijder de actuele regel"                //+247
50"@ESC@        Verlaat alle programma's"                  //+248
50""                                                       //+249
//  ERRORI editor
30"Tekst SRG kompleet"
30"Tekst TAB kompleet"
30"Veld@ %s @verkeerde syntax"
30"Veld@ %s @waarde verkeerd"
30"Groep niet toepasbaar"
30"Gereedschap : verkeerde syntax"
30"Gereedschap niet bruikbaar"
30"Veld@ %s @heeft geen waarde"
30"Stap=0 of gereedschap=1"
30"Aantal gaten =0"
30"Code verkeerd"
30"Interpolatie:@ %s @"
30"Werkvlak niet toepasbaar"
30""
30"Module@ %s @invalide"
30"Frees Radius:@ %s @"
30""                                      //+266 (17)
30""                                      //+267 (18)
30""                                      //+268 (19)
30""                                      //+269 (20)
30""                                      //+270 (21)
30""                                      //+271 (22)
30""                                      //+272 (23)
30""                                      //+273 (24)
30""                                      //+274 (25)
30""                                      //+275 (26)
30""                                      //+276 (27)
30""                                      //+277 (28)
30""                                      //+278 (29)
30""                                      //+279 (30)
30""                                      //+280 (31)
// Messaggi su Alt+t (help su gruppo o utensili
16"CORRECT.@X.@:"
16"CORRECT.@Y.@:"
16"CORRECT.@Z.@:"
16"ENCUMB. MAX @X+@:"
16"ENCUMB. MAX @X-@:"
16"ENCUMB. MAX @Y+@:"
16"ENCUMB. MAX @Y-@:"
16"ENCUMB. MAX @Z+@:"
16"GEREEDSCHAP DIAM.:"
16"GEREEDSCHAP NUM.:"
16"GEREEDSCHAP INTERAXIS:"
16"KOP TYPE :"
16"SNELHEID MIN. :"
16"SNELHEID MAX. :"
16"HOEK KOP:"
16"PARAMETER @17@:"
16"Cor.@ X. @(gr)"
16"Cor.@ Y. @(gr)"
16"Cor.@ Z. @(gr)"
//              disponibili
20""
20""
20""
20""
20""
20""
20""
20""
//              Messaggi di errore su ritorno da prg figlio
60"Error 1 : bestand DIGI.CNF niet gevonden"
60"Error 2 : bron programma niet gevonden"
60"Error 3 : geen toegang BASE.DGT of bestand niet gevonden"
60"Error 4 : geen toegang VINCOLI.VNT of bestand niet gevonden"
60"Error 5 : DGT program te lang"
60"Error 6 : CAD start invalide"
60"Error 7 : geen toegang PARTECx.PAT of bestand niet gevonden"
60"Error 8 : too cross bars on machine plane"
60"Error 9 : "
60"Error 10 : SUCKER start not valid"
