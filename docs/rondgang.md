# Rondgang door de hele interface

Bijgewerkt op 9 oktober 2026 na ronde zes, op commit `5bd1c57` van de werkbranch plus de herstellingen van die ronde, die nog niet zijn vastgelegd. Zes rondes in een eigen kopie met een echte browser, als de voorbeeldpersonen. Ronde zes liep in twee delen (A en B, onderaan dit document) en herstelde wat klein en duidelijk was. Ronde zeven en acht liepen na wat nog open of niet nagelopen stond; de telling hieronder is na ronde acht opnieuw gemaakt.

## Waar het product staat

Alle negen reizen zijn nu minstens één keer tot het eind gelopen, de vacature tot en met vervuld. Van de 93 bevindingen uit ronde een tot en met vijf zijn er 68 hersteld en door een latere ronde bevestigd. Mail, een passkey, twee tabbladen en het bewijs van een akkoord zijn voor het eerst echt gezien en werken. Wat overblijft is een rij ruwe randen, drie vragen die een besluit vragen (A612, A608, B611), en alles wat twee gekoppelde instanties of een echte login-dienst nodig heeft.

## Hoe ver elke reis kwam (alle rondes samen)

| Reis | Stand |
|---|---|
| 1. Opdracht winnen | Voltooid, met interne goedkeuring door een ander (ook met een passkey), een tekenlink per mail, tekenen als gast en een bewijs dat te controleren is. Niet: een node uit het echte corpus |
| 2. Van gedachten veranderen | Afwijzing, afsluiten zonder opdracht, intern terugsturen met reden en een nieuwe offerte daarna. Niet: de nieuwe offerte na een afwijzing door de opdrachtgever aanbieden |
| Interne opdracht | Voltooid; de open rol staat in de kop met een knop |
| 3. Bemensen | Inzetten boven 100 procent met waarschuwing vooraf, inkorten, verwijderen, de weigering in een afgesloten maand, een promotie midden in een maand. Niet: het bord Inzet volledig met de hand, "Open een vacature voor deze rol" |
| 4. Werven | Voltooid tot en met vervuld, met beoordeling van de tekst in twee rondes, en de variant met een bekende kandidaat. De formulieren voor beoordelen en opmerkingen alleen via de API |
| 5. Uitvoeren en factureren | Voltooid tot en met een naverrekening, en een aangeleverde maand heropenen met reden en opnieuw aanleveren |
| 6. Kosten en tarieven | Kostenpost met facturen, bijlage en dekking over twee opdrachten; een nieuwe tarievenkaart midden in het jaar met voorvertoning en gevolg. Open vraag: A612 |
| 7. De dag van de beheerder | Opdracht, persoon, elk recht, manager worden op andermans opdracht, tekstblokken, Activiteit, "Bekijk als", passkey. Niet: standaardteksten van vacatures, het formulier met voorbeeld, Meldingen, organisaties ophalen |
| 8. Alle anderen | Start, Taken en "Wat is er gebeurd" als twaalf personen; koude links zonder recht; twee tabbladen op één onderdeel; herladen midden in een tekst. Niet: de terugknop na elk formulier, de kant van de opdrachtgever voorbij het aanvraagformulier |
| 9. Smal en licht | Ronde vijf: 28 adressen op 390 breed en in het lichte thema zonder zijwaarts schuiven of fout. In ronde zes alleen het bord Inzet op 390 breed bekeken |

## Telling over alle rondes

117 bevindingen: 77 uit ronde een tot en met drie, 12 uit ronde vier, 4 uit ronde vijf, 24 uit ronde zes (13 in deel A, 11 in deel B). Geteld per nummer, uit de tabellen in dit document.

| Stand | Aantal | Welke |
|---|---|---|
| Hersteld en door een latere ronde bevestigd | 86 | ronde vier: F001, F004, F006, F009, F010, F012, F014, F015, F016, F017, F018, F019, F020, F021, F023, F024, F025, F026, F028, F030, F031, F033, F034, F036, F037, F042, G003, G007, G016; ronde vijf: F027, F032, F035, G001, G004, H004, H005, T205, R401, R405, R406, R407, R408, R409, R412; ronde zes: F003, F011, F029, G002, G005, G006, G010, G011, G013, T202, H002, H006, H007, H008, H009, H011, H012, R402, R403, R404, R410, R501, R503, R504; nagelopen op 9 oktober 2026: G012, G014, G015, F041, F002, F005, F007, F008, F013, F039, F040, T201, T203, T204, T206, T207, H010, R502 |
| Hersteld, deels bevestigd of hier niet te beoordelen | 3 | G009, R411, H003 |
| Als hersteld gemeld, nog door niemand nagelopen | 2 | G008, H001 (beide over middernacht) |
| Vervallen | 1 | F038 |
| Open, niet opnieuw bekeken | 1 | F022 (het corpus is in deze opstelling niet bereikbaar) |
| Ronde zes, hersteld | 18 | A601, A602, A603, A604, A606, A607, A609, A610, A611, B601, B602, B603, B604, B605, B607, B608, B609, B610 |
| Ronde zes, open | 6 | A605, A608, A612, A613, B606, B611; A608, A612 en B611 wachten op een besluit |

## Functiescheiding, op het scherm en op de server

| Handeling | Antwoord van de server | Zin |
|---|---|---|
| De maker en aanvrager keurt zijn eigen offerte goed (direct besluit) | 422 | "Je kunt een offerte waarvoor je zelf goedkeuring vroeg niet zelf goedkeuren. Iemand anders met dit recht beslist." |
| Dezelfde, via de bewijsstap | 422 bij het aanmaken | dezelfde zin |
| "Neem deze stap over" op de goedkeurstap door de maker | 403 | "Deze stap kun je niet overnemen: je hebt het recht niet dat hij vraagt, of hij is van wie erover beslist." |
| De goedkeurtaak aan jezelf geven door de maker | 422 | "Deze stap is van wie erover beslist ..." |
| De maker geeft akkoord als opdrachtgever in dezelfde instantie | 404 | "Niet gevonden" (er is geen ontvangen offerte) |
| De aanvrager van een vacature legt zelf het akkoord of een advies vast | 403 | "Je hebt hier geen toegang toe" |
| De schrijver van een vacaturetekst beoordeelt haar eigen tekst | geweigerd | gezien in deel A |
| Een planner neemt een stap van een ander over | 403 | "Deze stap kun je niet overnemen: ..." |
| De eigenaar heropent een aangeleverde maand | 403 | alleen de beheerder, met een reden |

## Toegang, nagelopen met `just check-access`

78 adressen als zeven lezers op de eigen kopie, 546 pagina's: geen knop die de server zou weigeren, geen bedrag bij wie geen geld mag lezen, geen geweigerd verzoek. Eén pagina liep bij de eerste gang vast op tijd terwijl de tests tegelijk draaiden; opnieuw gelopen zonder bevinding.

| Lezer | Inhoud | Leeg | Geen toegang | Niet gevonden | Actie | Lek | Fout |
|---|---|---|---|---|---|---|---|
| Beheerder | 64 | 7 | 1 | 6 | 0 | 0 | 0 |
| Eigenaar | 23 | 6 | 12 | 37 | 0 | 0 | 0 |
| Planner en manager | 41 | 8 | 20 | 9 | 0 | 0 | 0 |
| Alleen planner | 39 | 8 | 21 | 10 | 0 | 0 | 0 |
| Lezer | 45 | 9 | 17 | 7 | 0 | 0 | 0 |
| Teamlid | 14 | 6 | 13 | 45 | 0 | 0 | 0 |
| Aanvrager | 10 | 9 | 13 | 46 | 0 | 0 | 0 |

De lezer "zonder rechten" bestaat niet in deze kopie en is niet nagelopen.

## De tien dingen die nu het meest tellen

1. **Volgt de begroting van een getekende opdracht een nieuwe tarievenkaart?** Nu wel: na het vaststellen van een kaart meldt Financieel "De begroting is € 14.580 hoger dan de getekende offerte" zonder dat iemand de begroting wijzigde (A612). Dit is een besluit, geen fout.
2. **Mag een maand worden afgesloten terwijl een eerdere nog open is?** De server staat het toe (B611). Ook een besluit.
3. **Mag een kostenpost gedekt worden door een personeelsregel?** De keuzelijst biedt het aan (A608). Ook een besluit.
4. **Een gewijzigd tekstblok bereikt geen concept dat al bestond**, ook niet als niemand dat onderdeel aanraakte (B608). Een eigenaar met een open concept krijgt de oude tekst in de offerte.
5. **Een tekenbevoegde van een opdrachtgever leest intern nieuws over vacatures** (R502), al twee rondes.
6. **Twee mensen op één begrotingsregel: de laatste wint, zonder melding** (B610). Teksten weigeren een verouderde opslag wel.
7. **De vervulde vacature heeft geen slotzin en biedt nog een actie die niets doet** (A606); de tab Tekst met een concept heeft drie gelijke knoppen (A603).
8. **De beoordelaar kiezen uit iedereen in de instantie**, ook de tekenbevoegde van een opdrachtgever (A602).
9. **Zeven herstelmeldingen heeft nog niemand met de hand nagelopen**: de twee rond middernacht (G008, H001), de naverrekening als pdf (G012), het gat tussen tarievenkaarten (G014, G015), de deels open rol (H003) en de lopende vacature in "Nieuwe vacature" (F041).
10. **Open sinds ronde een en niet opnieuw bekeken**: één rollenlijst (F008), de node kiezen (F022), en een handvol ruwe randen.

## Wat niet te testen was, en wat dat openlaat

- **Een echte login-dienst**: opnieuw inloggen bij een besluit is niet gezien; de passkey is alleen met een virtuele sleutel in de browser geprobeerd, niet op een telefoon of een echt apparaat.
- **Twee gekoppelde instanties**: een aanvraag versturen en ontvangen, de ontvangen offerte, akkoord als opdrachtgever, inzage in het budget. Alleen door de twee testbestanden met twee instanties gedekt, en die slagen.
- **Het echte corpus en het echte organisatieregister**: niet aangeroepen.
- **Middernacht**: wat rond de wisseling van de dag speelt is alleen door tests met een klok gedekt.
- **De terugknop na elk formulier, en herladen met een open formulier**: maar op een paar plekken gedaan.
- **Meldingen op het scherm, de standaardteksten van vacatures, het aanvraagformulier met voorbeeld en bronnen**: niet gelopen in ronde zes.

## Ronde vijf: nieuwe bevindingen

| Nr | Ernst | Waar, als wie | Wat er gebeurde | Wat je verwacht | Vermoedelijke plek |
|---|---|---|---|---|---|
| R501 | Verwarrend | reis 4, advies van iemand buiten grip; beheerder, de enige die het mag vastleggen | de kop van de vacature zegt ook tegen de beheerder "Je wacht op het advies ... alleen een beheerder kan het daarna vastleggen", zonder knop; vastleggen kan alleen via de rij op de tab Advies en akkoord | voor de beheerder: "Leg het advies van <naam> vast" met de knop | achterkant: werkstroomkop van de vacature. Opgelost: wie het advies mag vastleggen is aan zet ("Leg het advies van concern control van <naam> vast", met de knop, ook in Taken); de aanvrager leest dat een beheerder het vastlegt |
| R502 | Verwarrend | de ochtend erna, "Wat is er gebeurd"; tekenbevoegde van een opdrachtgever | de feed toont interne gebeurtenissen rond vacatures ("Vacature Productmanager is goedgekeurd door ...", "Vacature Developer is opengesteld ...") aan iemand die alleen tekent namens een opdrachtgever | alleen wat deze persoon aangaat: offertes die zij tekent | achterkant: grip/events/news.py (publiek van vacaturenieuws) |
| R503 | Ruw | functiescheiding, taak overdragen; maker van de offerte | het verzoek om de goedkeurtaak aan zichzelf te geven krijgt 200 terug, terwijl er niets verandert (hij krijgt de taak niet en kan niet beslissen) | een weigering met een zin, zoals bij overnemen | achterkant: api/routes/tasks.py (PATCH). Opgelost: een geweigerde overdracht antwoordt met de weigering en de zin; een onbekend veld of een lege wijziging wordt geweigerd in plaats van genegeerd |
| R504 | Ruw | functiescheiding, bewijsstap; maker van de offerte | de server maakt de bewijsstap voor zijn eigen goedkeuring eerst aan (201) en weigert pas aan het eind ("besluit_fout=geweigerd"); het besluit wordt niet vastgelegd | weigeren bij het aanmaken, met dezelfde zin als het directe besluit | achterkant: api/routes/proof.py (intent voor approve). Opgelost: de bewijsstap wordt geweigerd bij het aanmaken, met de zin van het besluit zelf; ook voor aanvaarden als opdrachtgever en voor een offerte die intussen is gewijzigd of beslist |

## Ronde vijf: controle van eerdere bevindingen

| Nr | Uitkomst op 9 oktober 2026 (fc04762) |
|---|---|
| F027 | bevestigd |
| F032 | bevestigd |
| F035 | bevestigd |
| G001 | bevestigd |
| G004 | bevestigd |
| H004 | bevestigd |
| H005 | bevestigd |
| T205 | bevestigd |
| R401 | bevestigd |
| R405 | bevestigd |
| R406 | bevestigd |
| R407 | bevestigd |
| R408 | bevestigd |
| R409 | bevestigd |
| R412 | bevestigd |
| F003 | nog niet goed: de kop van een lege opdracht toont nog vier keer € 0 en "Geen ruimte" |
| H006 | nog niet goed: in het formulier "Nieuwe inzet" geen waarschuwing gezien bij 100 procent erbij voor iemand die al vol zit; pas na het bewaren staat er "Boven 100%" (gezocht op een paar formuleringen, dus niet helemaal zeker) |
| R403 | nog niet goed: ook als beheerder geen actie gevonden om een afgesloten, aangeleverde maand te heropenen |
| R410 | deels: de teruglink naar Beheer staat er; het voorbeeldkenmerk niet gelezen |
| G002, G005, G006, G008, G009, G010, G011, G012, G013, G014, G015, T202, H001, H002, H003, H007, H008, H009, H010, H011, H012, F041, R402, R404, R411 | niet nagelopen |

---

# Stand na ronde vier (commit cf6997e)

Bijgewerkt op 9 oktober 2026 na ronde vier, op commit `cf6997e` van de werkbranch. Vier rondes door een eigen kopie met een echte browser, als de voorbeeldpersonen; deze ronde vindt en beschrijft en wijzigt geen code.

## Waar het product staat

De hoofdweg van een opdracht werkt van begin tot eind: begroting, offerte als brief, interne goedkeuring door een ander, aanbieden, tekenen met bewijs, uitvoeren, maanden afsluiten, een kwartaal aanleveren, de factuur vastleggen en een naverrekening tot en met haar eigen factuur. De kop van een opdracht en van een vacature zegt in één zin waar het staat, wie aan zet is en wat de knop is; de bedragen kloppen over scherm en pdf heen. Van de bevindingen uit ronde een die deze ronde zijn nagelopen is bijna alles echt hersteld. Wat nu het zwaarst weegt is één fout aan de achterkant: zodra een vacature een bewaard aanvraagformulier heeft, valt de pagina Taken voor iedereen om (R407). Daardoor is de reis van de vacature deze ronde niet verder gekomen dan het advies. Een groot deel van de bevindingen uit ronde twee en drie is deze ronde niet nagelopen; dat staat eerlijk in de telling.

## Hoe ver elke reis kwam in ronde vier

| Reis | Stand |
|---|---|
| 1. Opdracht winnen | Voltooid tot en met "Zet in uitvoering": begroting met drie soorten regels, brief met een eigen tekst, een concept van het taalmodel (10 s) en een herschreven passage (5 s), afzender aangevuld door de beheerder, interne goedkeuring gevraagd en door een ander gegeven met ontvangstbewijs, aangeboden met een tekenlink, getekend als de uitgenodigde, bewijs gecontroleerd. Niet: mail (geen postvanger), een node uit het corpus. Dat de server een eigen goedkeuring weigert is niet sluitend getest (het verzoek strandde op een ontbrekend veld); het scherm biedt de knoppen niet. "Neem deze stap over" niet gevonden |
| 2. Van gedachten veranderen | Deels: afwijzing vastgelegd, de opdracht blijft open en de kop leidt naar een nieuwe offerte; afsluiten zonder opdracht vraagt een reden en weigert zonder. Niet: de nieuwe offerte zelf maken en aanbieden |
| Interne opdracht | Voltooid van begin tot uitvoering, met een eigen kort verloop |
| 3. Bemensen | Niet opnieuw gelopen; het bord Inzet niet met de hand bediend |
| 4. Werven | Gestopt bij advies en akkoord: aanvraag voorbereid, motivatie geschreven en vastgesteld, aangevraagd, drie adviseurs genoemd waarvan één buiten grip. Daarna gaf het verloop van de vacature een serverfout (R407). Niet: de tekst door beoordeling, publiceren, vervullen, de variant met een kandidaat |
| 5. Uitvoeren en factureren | Voltooid, inclusief een naverrekening na de factuur via aanleveren tot haar eigen factuur. Een maand heropenen: geen actie voor gevonden (R403) |
| 6. Kosten en tarieven | Niet gelopen |
| 7. De dag van de beheerder | Deels: afzender en personen, interne goedkeuring aangezet, rechten toegekend, een nieuwe persoon gemaakt. Niet: tarievenkaart, organisatieregister, tekstblokken, standaardteksten, formulier met voorbeeld, passkey, meldingen |
| 8. Alle anderen | Deels: start en Taken als goedkeurder en eigenaar; 32 adressen als zuivere planner (nieuw aangemaakt), lezer, teamlid, aanvrager en persoon zonder rechten; diepe links naar tabs zonder recht. Niet: terugknop, herladen, twee tabbladen op één onderdeel, de kant van de opdrachtgever |
| 9. Smal en licht | Alleen de acht werkstroompagina's in licht en donker voor de waas-toets; niet opnieuw alles op 390 |

## Telling over alle rondes

Rondes een tot en met drie: 77 bevindingen (42 uit ronde een, 16, 7 en 12 uit de rondes daarna). Ronde vier voegt er 12 toe.

| Stand | Aantal | Welke |
|---|---|---|
| Hersteld en deze ronde bevestigd | 29 | F001, F004, F006, F009, F010, F012, F014, F015, F016, F017, F018, F019, F020, F021, F023, F024, F025, F026, F028, F030, F031, F033, F034, F036, F037, F042, G003, G007, G016 |
| Hersteld, deels bevestigd | 4 | F011, F029, F027, F032 |
| Als hersteld gemeld, deze ronde niet nagelopen | 23 | G001, G002, G004, G005, G006, G008, G009, G010, G011, G012, G013, G014, G015, T202, T205, H001, H002, H003, H004, H011, H012, F035, F041 |
| Open, gezien dat het er nog is | 1 | F003 |
| Open of zonder stand, deze ronde niet opnieuw bekeken | 20 | F002, F005, F007, F008, F013, F022, F038, F039, F040, T201, T203, T204, T206, T207, H005, H006, H007, H008, H009, H010 |
| Nieuw in ronde vier | 12 | R407, R401, R402, R403, R406, R412, R404, R405, R408, R409, R410, R411 |

Van wat als hersteld was gemeld en is nagelopen, bleek niets helemaal onjuist; twee zijn half (F011, F029).

## De tien dingen die nu het meest tellen

1. **Taken vallen om voor iedereen zodra een vacature een bewaard aanvraagformulier heeft** (R407). Taken, de taken op de startpagina en de kop van de vacature geven een serverfout. Dit raakt de hele instantie.
2. **De reis van een vacature is daardoor niet tot het eind te lopen.** Beoordelen van de tekst, publiceren en vervullen zijn in geen enkele ronde met de hand gedaan.
3. **Wie zelf goedkeurder is en goedkeuring vraagt, krijgt te horen dat zij moet beoordelen** (R401): kop en lijst zeggen het, de knoppen ontbreken terecht.
4. **Een eigenaar leest "Je wacht op een planner. Jij hoeft nu niets te doen"**, terwijl zij de rol zelf kan invullen (R402).
5. **Knoppen in de kop van een vacature vragen twee keer drukken** of leiden naar een tab zonder knop (R405, R406, R408).
6. **Een maand heropenen na aanlevering kan nergens** (R403); of dat de bedoeling is, staat er niet.
7. **Een teamlid leest de tariefcategorie van zijn begrotingsregel** in de beschrijving van zijn eigen balk op het bord (R412).
8. **De kop van een lege opdracht toont nog vier keer € 0** (F003).
9. **Het factuurverzoek van een kwartaal is nog twee pagina's** (F029), en het onderdeel van de offerte blijft open na bewaren (F011).
10. **Drieëntwintig herstelmeldingen uit ronde twee en drie zijn niet door een tweede paar ogen bekeken**, waaronder het overnemen van een stap met functiescheiding (H004) en de ene klok (G008).

## Waar het oog landt (waas-toets, donker en licht gelijk)

| Pagina, als wie | Eerst | Dan | Dan | Is het enige gevulde accent de volgende stap? |
|---|---|---|---|---|
| Opdracht, eigenaar | de blauwe knop "Sluit april 2026 af" rechtsboven | de titel | de rode regel "Had klaar moeten zijn" | ja |
| Vacature, tab Aanvraag, aanvrager | de titel | de groene vinkjes | de zin in de kop | nee: de knop van de stap is hier een gewone knop (R409) |
| Vacature, tab Tekst, aanvrager | de blauwe knop "Maak aanvraagformulier" | de titel | het label "Vastgesteld" | ja |
| Offerte schrijven, eigenaar | de titel | de kolom gelijke "Schrijf"-knoppen | de gedimde "Maak offerte" | nee: er is geen accent (R411) |
| Afsluiten en factureren, eigenaar | de kaart "April 2026 is voorbij" met haar knop | de titel | de cijfers in de kop | ja |
| Factureren, eigenaar | de titel | de zin "Er staat niets klaar" | de ene rij | er is terecht geen accent |
| Taken, eigenaar | de rode data "Te laat" | de titel | de namen van de taken | geen gevuld accent; drie keer rood |
| Start, eigenaar | de titel | de twee kolommen taken en aandacht | het blok "Wat is er gebeurd" | geen gevuld accent |

In vijf seconden te zeggen waar het staat, wie aan zet is en wat je indrukt: ja op de opdracht, op de tekst-tab en op Afsluiten; op de vacature wel de zin maar niet de knop; op de schrijfpagina wel de zin ("Begin met Inleiding") maar niet de knop.

## Nagerekend in ronde vier

| Keten | Gerekend | Op scherm en pdf |
|---|---|---|
| Begroting, offerte, brief, tekenpagina | 0,8 × 12 × 13.125 = 126.000; 0,5 × 12 × 18.900 = 113.400; vast 6.000 (jaar 2027); samen 245.400 | begroting, kop, offertekaart, brief en tekenpagina: € 245.400; de brief noemt de tarieven van 2027 |
| Maand aanpassen | maart: 12.500 + 6.000 (40 in plaats van 60 procent) + 14.400 = 32.900 | het paneel rekent mee: € 6.000, "De maand komt op € 32.900" |
| Kwartaal naar factuurverzoek | 35.900 + 32.900 + 32.900 = 101.700 | tab € 101.700; pdf met subtotalen 35.900, 32.900, 32.900 en totaal € 101.700 |
| Factuur | 101.700 aangeleverd, 101.600 gefactureerd | "€ 100 minder gefactureerd dan aangeleverd" |
| Naverrekening | schaal 11 naar 13 per 1 februari: 2 × 2.500 = 5.000 | periode "Naverrekening € 5.000"; eigen pdf € 5.000; daarna aangeleverd € 106.700, gefactureerd € 106.600 |

Niet opnieuw gerekend: een promotie midden in een maand (klopte in ronde een) en de dekking van een kostenpost.

## Toegang in ronde vier

Als zuivere planner, teamlid, aanvrager en persoon zonder rechten op 32 adressen: geen bedrag van een ander, in lijsten, kop, geschiedenis of feed. Tarieven tonen hun geen bedragen meer. De lezer ziet bedragen van opdrachten, zoals bedoeld. Eén punt: het teamlid leest op het bord de tariefcategorie van zijn eigen begrotingsregel (R412). Pdf's en panelen zijn niet per persoon nagelopen. Geen actie gevonden die de server daarna weigerde, buiten de serverfout van R407.

## Wat hier niet te testen was

- **Een echte login-dienst.** De kopie draait zonder login; opnieuw inloggen bij tekenen en goedkeuren is dus niet gezien. Onbekend blijft of de terugkeer goed gaat en wat een verlopen sessie doet.
- **Mail en pushmeldingen.** Geen postvanger en geen achtergrondproces gestart. Onbekend of de tekenlink aankomt en leesbaar is.
- **Een echte telefoon, een geïnstalleerde app, een passkey.**
- **Twee gekoppelde instanties.** De kant van de opdrachtgever met een ontvangen offerte is niet gelopen.
- **Het echte corpus.** Context kiezen en de context in een concept van het taalmodel zijn niet gezien.

## Ronde vier: nieuwe bevindingen

| Nr | Ernst | Waar, als wie | Wat er gebeurde | Wat je verwacht | Vermoedelijke plek |
|---|---|---|---|---|---|
| R407 | Kapot | reis 4, na "Maak aanvraagformulier" en het noemen van adviseurs met een account; iedereen; Taken, de startpagina en de kop van elke vacature geopend | de server antwoordt 500 op /api/tasks/mine en op het verloop van de vacature: de pagina Taken zegt "Dit laden is niet gelukt", de kop van de vacature valt weg en de taken op de startpagina ook, voor alle gebruikers van de instantie; oorzaak in het logboek: bij het vergelijken van het bewaarde formulier met de vacature wordt een gegeven lui geladen buiten de databasecontext (MissingGreenlet in services/vacancies/service.py form_values, via request_forms.changed_since, via tasks/cases._request_form_facts) | taken blijven werken; de genoemde personen worden vooraf geladen | backend grip/tasks/cases.py (_request_form_facts), services/vacancies/request_forms.py, service.py form_values. Opgelost: de vacature wordt met haar aanvrager geladen; of het formulier nog klopt wordt beantwoord uit wat bij het maken is bewaard, zonder het bestand te openen; een zaak waarvan de feiten falen laat de taken van de rest werken en wordt alleen aan de beheerder gemeld |
| R401 | Verwarrend | reis 1, interne goedkeuring; eigenaar die zelf het recht goedkeurder heeft en de goedkeuring net vroeg; kop van de opdracht en /goedkeuren bekeken | de kop zegt tegen haar "Beoordeel de offerte ... keur haar goed, of stuur haar terug" met de hoofdknop "Beoordeel de offerte", en de offerte staat in haar lijst "Wacht op mijn goedkeuring"; op de beoordeelpagina ontbreken de knoppen terecht, maar er staat niet waarom | voor de aanvrager: "Wacht op goedkeuring door een ander"; op de pagina: "Je kunt je eigen offerte niet goedkeuren" | backend: zin en zet in de werkstroomkop (wie is aan zet sluit de aanvrager uit), GET quote-approvals/waiting. Opgelost: wie de offerte maakte of de goedkeuring vroeg is niet aan zet, leest dat een ander beslist (of wie het recht toekent als er geen ander is), en de offerte staat niet in haar lijst |
| R402 | Verwarrend | reis 3, opdracht net in uitvoering; eigenaar; kop gelezen | "Je wacht op een planner, die de rol Productmanager invult. Jij hoeft nu niets te doen", zonder knop, terwijl de eigenaar zelf iemand kan inzetten op de tab Bemensing | "Vul de rol Productmanager in" met de knop naar Bemensing; "wacht op een planner" alleen voor wie zelf niet kan plannen | backend: werkstroomkop (wie kan de stap zetten). Opgelost: een rol invullen is ook de zet van wie de opdracht mag bemensen; alleen wie dat niet mag, wacht |
| R403 | Verwarrend | reis 5, maand heropenen na aanlevering; eigenaar; tab Afsluiten en factureren, menu's van periode en maand nagelopen | er is geen actie om een afgesloten, aangeleverde maand te heropenen; het woord komt op de pagina niet voor | een actie bij de maand, of een zin die zegt dat corrigeren via een naverrekening gaat | features/month-close. Hersteld. De actie bestond al, alleen voor de beheerder en als "Heropen" onderaan het paneel van een afgesloten maand. Nu: de knop heet "Heropen de maand", het paneel waarschuwt bij een aangeleverde maand wat heropenen doet, en wie maanden afsluit leest in het paneel dat alleen een beheerder heropent en dat een prijsverschil als naverrekening komt |
| R406 | Verwarrend | reis 4, advies en akkoord; aanvrager; hoofdknop "Noem iemand" in de kop gevolgd | de knop brengt je naar de tab Advies en akkoord; daar heeft de kop geen knop meer en staat er geen actie; noemen kan alleen door op de naam van de rij ("Advies HR") te klikken, wat nergens staat | de knop opent het paneel "HR-adviseur noemen" direct, of de rij draagt de knop | features/vacancies (advies-tab, bestemming van de stap). Opgelost: de knop opent het paneel direct, en de tab draagt zelf een knop om iemand te noemen |
| R412 | Verwarrend | toegang, Inzet-bord; teamlid; eigen balken op het bord gelezen | de beschrijving van zijn eigen balk zegt "declareert in schaal 12 en 13 (categorie C), de regel rekent met schaal 10 en 11 (categorie B)": de tariefcategorie van de begrotingsregel, die een teamlid volgens het toegangsmodel niet ziet | voor wie geen geld ziet alleen "ander tarief dan de regel aanneemt", zonder de categorie van de regel | backend: beschrijving van een inzet met tariefverschil per lezer; features/allocations. Hersteld. De categorie van de regel hoort bij het geld van de opdracht (klasse B) en komt alleen nog mee voor wie dat leest; de eigen categorie blijft van de persoon. Lektest op het bord, de inzetlijst, Bemensing en de persoonspagina |
| R404 | Ruw | reis 4, vacaturelijst; aanvrager; lijst naast de vacature gelezen | de kolom Stand zegt "Jij: vraag de vacature aan" terwijl de kop van die vacature zegt dat de aanvraag nog niet compleet is en eerst de motivatie vraagt | dezelfde zin als de kop | backend: stand in de lijst uit dezelfde bron als de kop. Opgelost: de lijst zegt "maak de aanvraag compleet" zolang er iets ontbreekt |
| R405 | Ruw | reis 4, motivatie schrijven; aanvrager; hoofdknop "Schrijf de motivatie" in de kop | de knop brengt je naar de tab Tekst, waar je dezelfde knop "Schrijf de motivatie" nog een keer moet indrukken; de kop houdt intussen zijn eigen knop met dezelfde naam | de knop in de kop opent het schrijven direct | features/vacancies (bestemming van de stap), TextWork. Opgelost: de knop in de kop opent het schrijven direct (adres met wat te openen) |
| R408 | Ruw | reis 4, advies vastleggen; genoemde adviseur; hoofdknop "Leg het advies vast" in de kop | de knop brengt je naar de tab, waar een tweede knop "Leg advies concern control vast" staat die je ook moet indrukken (zelfde patroon als R405 en R406) | één druk opent het paneel | features/vacancies (bestemming van de stap). Opgelost: een druk opent het paneel |
| R409 | Ruw | reis 4, tab Aanvraag van een vacature; aanvrager; kop zegt "Maak het aanvraagformulier" | op de tab waar die knop staat verdwijnt de hoofdknop uit de kop en is de knop op de tab zelf een gewone knop: de pagina heeft dan geen accent; op de andere tabs heeft de kop de blauwe knop wel | op de tab van de stap is de knop van de stap het accent | features/vacancies (headerHoldsPrimary). Opgelost: op de tab waar de stap gedaan wordt is de knop van de stap het accent |
| R410 | Ruw | reis 7, /beheer/offertes; beheerder; pagina gelezen | "Volgende offerte heet bijvoorbeeld LOKAAL-2026-0001" terwijl er al zes offertes zijn; de pagina heeft als enige beheerpagina geen "Terug naar Beheer" | het echte volgende nummer; de teruglink | features/quotes/QuoteSettingsPage.tsx. Hersteld. De server geeft het kenmerk dat de volgende offerte echt krijgt, zonder een nummer te nemen; de pagina heeft de teruglink |
| R411 | Ruw | reis 1, offerte schrijven; eigenaar; pagina met lege onderdelen | geen enkel accent: "Maak offerte" is gedimd en alle "Schrijf"-knoppen zijn gelijk; de zin zegt "Begin met Inleiding" maar die knop valt niet op | "Schrijf" bij het eerste lege onderdeel als hoofdknop | features/quotes/QuoteDraftPage.tsx. Opgelost: "Schrijf" bij het eerste lege onderdeel is het accent; "Maak offerte" pas als het kan |

## Ronde vier: controle van eerdere bevindingen

| Nr | Uitkomst op 9 oktober 2026 |
|---|---|
| F001 | bevestigd op 9 oktober 2026 |
| F004 | bevestigd op 9 oktober 2026 |
| F006 | bevestigd op 9 oktober 2026 |
| F009 | bevestigd op 9 oktober 2026 |
| F010 | bevestigd op 9 oktober 2026 |
| F012 | bevestigd op 9 oktober 2026 |
| F014 | bevestigd op 9 oktober 2026 |
| F015 | bevestigd op 9 oktober 2026 |
| F016 | bevestigd op 9 oktober 2026 |
| F017 | bevestigd op 9 oktober 2026 |
| F018 | bevestigd op 9 oktober 2026 |
| F019 | bevestigd op 9 oktober 2026 |
| F020 | bevestigd op 9 oktober 2026 |
| F021 | bevestigd op 9 oktober 2026 |
| F023 | bevestigd op 9 oktober 2026 |
| F024 | bevestigd op 9 oktober 2026 |
| F025 | bevestigd op 9 oktober 2026 |
| F026 | bevestigd op 9 oktober 2026 |
| F028 | bevestigd op 9 oktober 2026 |
| F030 | bevestigd op 9 oktober 2026 |
| F031 | bevestigd op 9 oktober 2026 |
| F033 | bevestigd op 9 oktober 2026 |
| F034 | bevestigd op 9 oktober 2026 |
| F036 | bevestigd op 9 oktober 2026 |
| F037 | bevestigd op 9 oktober 2026 |
| F042 | bevestigd op 9 oktober 2026 |
| G003 | bevestigd op 9 oktober 2026 |
| G007 | bevestigd op 9 oktober 2026 |
| G016 | bevestigd op 9 oktober 2026 |
| F011 | deels: de melding "Inleiding is bewaard" staat er; het onderdeel blijft open staan |
| F029 | deels: subtotaal per maand staat er; een kwartaal met drie rollen is nog twee pagina's |
| F027 | deels: geen eindeloos laden meer; wat de pagina de lezer daarna zegt is niet bekeken |
| F032 | deels: geen eindeloos laden meer en geen onjuiste zin gezien; verder niet bekeken |
| F003 | nog niet goed: nog aanwezig: de kop van een nieuwe opdracht toont vier keer € 0 en "Geen ruimte" |
| G001, G002, G004, G005, G006, G008, G009, G010, G011, G012, G013, G014, G015, T202, T205, H001, H002, H003, H004, H011, H012, F035, F041 | als hersteld gemeld, deze ronde niet nagelopen |
| F002, F005, F007, F008, F013, F022, F038, F039, F040, T201, T203, T204, T206, T207, H005, H006, H007, H008, H009, H010 | deze ronde niet opnieuw bekeken |

---

# Eerdere rondes

Stand: commit `53005b7` op de werkbranch, 8 oktober 2026. Gedaan in een eigen kopie (eigen database, eigen servers), met een echte browser die klikt en typt, als de verschillende voorbeeldpersonen. Deze ronde vindt en beschrijft; er is niets aan de code gewijzigd.

## Ronde een: hoe ver elke reis kwam

| Reis | Stand |
|---|---|
| 1. Opdracht winnen | Doorlopen tot en met "in uitvoering": opdracht, begroting (drie soorten regels), offerte als brief met een eigen tekst en twee concepten van het taalmodel, pdf bekeken, aangeboden als document en met een tekenlink, getekend als de uitgenodigde, bewijs gedownload en gecontroleerd. Niet gedaan: interne goedkeuring, mail van de tekenlink, "Herschrijf selectie", een node uit het corpus (alleen het paneel gezien) |
| 2. Van gedachten veranderen | Deels: begroting gewijzigd na akkoord en de signalen gelezen; een beheerder die de nieuwe offerte niet mag maken. Niet gedaan: nieuwe offerte na wijziging, afwijzen als opdrachtgever |
| 3. Bemensen | Iemand ingezet vanaf de tab Bemensing, promotie midden in een maand met de gevolgen vooraf, oorzaak teruggevonden in Financieel en Begroting. Niet gedaan: plannen vanaf het bord, inkorten en beëindigen |
| 4. Werven | Deels: aanvraag voorbereid, motivatie geschreven, standaardtekst genomen, aanvraagformulier gemaakt en bekeken. Niet gedaan: aanvragen, advies en akkoord, beoordelen van de tekst, publiceren, vervullen, de variant met een kandidaat |
| 5. Uitvoeren en factureren | Doorlopen: maand aangepast en afgesloten, kwartaal aangeleverd met factuuradres, factuurverzoek bekeken, factuur vastgelegd, naverrekening door een late promotie |
| 6. Kosten en tarieven | Niet gedaan, alleen bekeken in de rondes langs alle pagina's |
| 7. De dag van de beheerder | Alleen: afzender en standaardteksten overgenomen van het profiel. De rest niet gedaan |
| 8. Alle anderen | Elke pagina geopend als planner, eigenaar, lezer, teamlid, persoon zonder rechten en aanvrager, met diepe links naar tabs die zij niet hebben. Niet gedaan: terugknop, herladen na opslaan, twee tabbladen tegelijk, de kant van de opdrachtgever |
| 9. Smal en licht | Elke pagina op 390 breed en in het lichte thema geopend als beheerder; twaalf smalle en acht lichte pagina's bekeken. Geen pagina schuift zijwaarts |

## Ronde een: telling

42 bevindingen: 8 kapot, 19 verwarrend, 15 ruw.

## Ronde een: de vijftien ergste

- **F009** (kapot), reis 1, vaste begrotingsregel: het jaar staat standaard op 2026 (het huidige jaar); de begroting krijgt "Subtotaal 2026 € 6.000" buiten de looptijd, zonder waarschuwing
- **F014** (kapot), reis 1, offertebrief (pdf): Leveringsvoorwaarden punt 6 zegt "Deze offerte is gebaseerd op de tarieven van 2026"; het jaar volgt het moment van maken, niet de tarieven in de offerte
- **F017** (kapot), reis 1, offerte aanbieden: de offerte is aangeboden "Als document"; de drie manieren staan als tekstregels zonder zichtbare keuze of selectie, dus je ziet niet dat er al een gekozen is
- **F023** (kapot), reis 8, /vacatures/beheer: de pagina blijft op "Bezig met laden" staan; de server antwoordt 403 en het scherm zegt dat niet
- **F026** (kapot), reis 8, /factureren: de pagina zegt "Er staat niets klaar om aan te leveren. Alle perioden die voorbij zijn, zijn afgesloten en gefactureerd", wat niet waar is; hij mag het alleen niet zien
- **F027** (kapot), reis 8, diepe link naar Financieel: jaarkeuze en twee knoppen "Download ... (CSV)" staan er, daaronder eindeloos "Bezig met laden"; de server antwoordt 403
- **F032** (kapot), reis 8, diepe link naar Bemensing: er staat "Je kunt de bemensing bekijken. Wijzigen kan de eigenaar ...", daaronder eindeloos "Bezig met laden"; de tab "Overzicht" is gemarkeerd
- **F033** (kapot), reis 8, /beheer/tarieven: alle tarievenkaarten met de maandtarieven per categorie en de schalen per categorie staan er, ook de conceptkaart voor 2030, voor iemand die volgens het toegangsmodel geen geld ziet; de Beheer-pagina zelf zegt "Beheer is voor beheerders"
- **F004** (verwarrend), reis 1, nieuwe opdracht: het formulier vraagt geen looptijd en Overzicht noemt de ontbrekende looptijd niet; later blijken begrotingsregels de looptijd van de opdracht te volgen
- **F006** (verwarrend), reis 1, begrotingsregel: schaal en rol worden stil vervangen door die van de persoon (C werd B); er staat nergens dat de eerdere keuze is overschreven
- **F008** (verwarrend), reis 1, begrotingsregel, rol kiezen: alleen "Productmanager" wordt aangeboden; "Product owner" en "Software engineer" vinden niets, want de rollenlijst kent ze als "po" en "Developer" en zoekt niet op de andere namen die de standaardteksten wel kennen (Ook: PO, Product owner)
- **F010** (verwarrend), reis 1, offerte schrijven: alle onderdelen staan op "Leeg", ook Leveringsvoorwaarden; niets zegt dat de standaardteksten en de afzender van de organisatie ontbreken en dat een beheerder die eerst moet instellen
- **F011** (verwarrend), reis 1, offerte schrijven: het onderdeel blijft open staan met dezelfde knop "Bewaar"; alleen het kleine woord onder de kop wisselt naar "Zelf geschreven"; er is geen bevestiging en het volgende onderdeel opent niet
- **F013** (verwarrend), reis 1, offerte schrijven: het onderdeel blijft "Niet in deze offerte"; niets zegt of de tekst bewaard is en hoe het onderdeel alsnog meedoet
- **F015** (verwarrend), reis 1, offertebrief (pdf): de brief drukt de kop "Contactpersoon ODI

## Bedragen die over schermen heen zijn nagerekend

| Keten | Gerekend | Op de schermen |
|---|---|---|
| Begroting naar kop | 0,8 fte × 12 × € 13.125 = € 126.000; 0,5 fte × 12 × € 18.900 = € 113.400; vast € 6.000; samen € 245.400 | Begroting, kop van de opdracht: € 245.400 |
| Begroting naar offerte en brief | dezelfde drie regels | Offertekaart € 245.400; brief: regels € 126.000, € 113.400, € 6.000, totaal € 245.400; tekenpagina hetzelfde |
| Promotie midden in een maand | jan en feb 2 × 0,8 × 13.125 = 21.000; maart 0,8 × (13.125 × 14/31 + 15.750 × 17/31) = 11.651,61; apr t/m dec 9 × 0,8 × 15.750 = 113.400; samen € 146.051,61 | Financieel 2027, verwacht totaal van de regel: € 146.052; overschrijding € 20.052 |
| Maand afsluiten | maart gepland 12.500 + 9.000 + 14.400 = 35.900; met 40 in plaats van 60 procent: 32.900; kwartaal 35.900 + 32.900 + 32.900 = 101.700 | Tab: € 101.700; factuurverzoek (pdf): € 101.700 met dezelfde regels |
| Naverrekening | schaal 11 naar 13 per 1 februari: 2 maanden × (15.000 − 12.500) = € 5.000 | Tab en Financieel: € 5.000 |
| Begroting na akkoord | 0,1 fte × 12 × € 18.900 = € 22.680 | Overzicht: "€ 22.680 hoger dan de getekende offerte" |

Alle zes ketens kloppen. Wat niet klopt zijn jaren en standen, niet de sommen: een vaste regel op het verkeerde jaar (F009), het verkeerde tariefjaar in de brief (F014), Financieel dat op het verkeerde jaar opent (F025).

## Toegang

Geen bedrag, schaal of kostprijs van een ander gevonden bij het teamlid, de persoon zonder rechten of de aanvrager, op geen van de 47 adressen, ook niet in de feed en de geschiedenis. Twee dingen wel:

- **Tarieven zijn voor iedereen leesbaar** (F033): alle kaarten met de bedragen per categorie, ook het concept. Dat is geen persoonsgegeven, maar het toegangsmodel zegt dat een teamlid geen geld ziet. Dit vraagt een besluit.
- **Tabs en pagina's die je niet hebt, blijven hangen of beweren iets onjuists** (F023, F026, F027, F032): de server weigert terecht, het scherm zegt het niet.

De voorbeeldplanner is ook manager van opdrachten en leidinggevende, dus wat hij aan bedragen ziet, mag hij zien. Een zuivere planner is niet met de hand nagelopen; daarvoor ontbreekt een voorbeeldpersoon.

![Pagina's zonder recht](rondgang/geen-recht.png)

![Teamlid: Factureren, Team en een diepe link naar Financieel](rondgang/teamlid.png)

![Lezer op Bemensing, tarieven zonder rechten, Aanvragen](rondgang/lezer-en-tarieven.png)

![Twaalf pagina's op 390 breed](rondgang/smal.png)

## Fouten in de browser

Geen enkele scriptfout op een pagina. Alle geweigerde verzoeken waren 403 of 404 voor iemand zonder recht, plus één 502 op de pagina met voorstellen uit Wies (Wies was in deze opstelling niet bereikbaar; de pagina zegt dat). Waar een 403 niet werd uitgelegd, staat dat bij de bevindingen (F023, F027, F032).

## Alle bevindingen, per gebied

### Opdrachten en start

| Nr | Ernst | Waar, als wie | Wat er gebeurde | Wat je verwacht | Vermoedelijke plek |
|---|---|---|---|---|---|
| F009 | Kapot | reis 1, vaste begrotingsregel; eigenaar; vaste regel "Licenties" toegevoegd op een opdracht die van 1 jan t/m 31 dec 2027 loopt, jaar niet aangeraakt | het jaar staat standaard op 2026 (het huidige jaar); de begroting krijgt "Subtotaal 2026 € 6.000" buiten de looptijd, zonder waarschuwing | standaard het eerste jaar van de looptijd, en een jaar buiten de looptijd weigeren of melden | features/assignments/BudgetEditor.tsx en services/assignments (validatie) |
| F027 | Kapot | reis 8, diepe link naar Financieel; teamlid; /opdrachten/<id>/financieel geopend (tab staat niet in zijn tabs) | jaarkeuze en twee knoppen "Download ... (CSV)" staan er, daaronder eindeloos "Bezig met laden"; de server antwoordt 403 | geen acties tonen en zeggen dat dit deel niet voor deze lezer is | features/assignments/tabs/FinanceTab.tsx (403 afhandelen), AssignmentLayout (tab die je niet hebt) |
| F032 | Kapot | reis 8, diepe link naar Bemensing; lezer; /opdrachten/<id>/bemensing geopend (tab staat niet in zijn tabs) | er staat "Je kunt de bemensing bekijken. Wijzigen kan de eigenaar ...", daaronder eindeloos "Bezig met laden"; de tab "Overzicht" is gemarkeerd | zeggen dat dit deel niet voor deze lezer is; geen zin die het tegendeel beweert | features/assignments/AssignmentLayout.tsx (route zonder recht), StaffingTab (403) |
| F004 | Verwarrend | reis 1, nieuwe opdracht; eigenaar; opdracht gemaakt met naam en opdrachtgever | het formulier vraagt geen looptijd en Overzicht noemt de ontbrekende looptijd niet; later blijken begrotingsregels de looptijd van de opdracht te volgen | looptijd in het formulier of als eerste stap benoemd | features/assignments (nieuw formulier, OverviewTab) |
| F006 | Verwarrend | reis 1, begrotingsregel; eigenaar; schaal 12 en 13 gekozen, daarna beoogde persoon gekozen | schaal en rol worden stil vervangen door die van de persoon (C werd B); er staat nergens dat de eerdere keuze is overschreven | een regel "Schaal en rol volgen de beoogde persoon" op het moment van kiezen | features/assignments/BudgetEditor.tsx |
| F021 | Verwarrend | reis 1, Overzicht na akkoord; eigenaar; de opdrachtgever heeft getekend; Overzicht geopend | de stappenbalk is weg en de pagina biedt geen volgende stap; "in uitvoering zetten" zit alleen in het menu met drie puntjes, terwijl er wel een taak "Zet de opdracht in uitvoering" bestaat | de volgende stap als hoofdknop in de kop zolang de opdracht op "Akkoord" staat | features/assignments/tabs/OverviewTab.tsx, standing.ts |
| F022 | Verwarrend | reis 1, context toevoegen; eigenaar; "Voeg een node toe" | het paneel vraagt een kale URI ("te vinden op de pagina van de node in het corpus"); er is geen zoeken of kiezen, en niets zegt of het corpus bereikbaar is (in deze opstelling niet vastgesteld) | zoeken in het corpus, met de URI als uitweg | features/nodes |
| F025 | Verwarrend | reis 3, Financieel; eigenaar; Financieel geopend van een opdracht die helemaal in 2027 ligt | de tab staat op 2026 ("Stand per begrotingsregel, 2026") en toont nullen voor de personeelsregels; alleen de vaste regel met het verkeerde jaar heeft een bedrag | het eerste jaar van de looptijd, of "hele looptijd" als begin | features/assignments/tabs/FinanceTab.tsx |
| F037 | Verwarrend | reis 2, Overzicht potentiële opdracht; beheerder (mag de offerte niet maken); Overzicht geopend van een opdracht waarvan de begroting na de offerte is gewijzigd | de hoofdknop "Maak een nieuwe offerte" staat er ook voor wie dat niet mag, naast de regel "Je kunt deze gegevens bekijken"; de klik eindigt op de tab Offerte zonder enige actie | voor wie niet mag: de zin over wat er speelt en wie het kan doen, zonder knop | features/assignments/tabs/OverviewTab.tsx (standing: actie alleen voor wie mag) |
| F005 | Ruw | reis 1, Overzicht; eigenaar; nieuwe opdracht | "Wijzig gegevens" en het menu zweven rechts boven één feit ("Soort"), los van waar ze bij horen; de lege Context toont een gecentreerde zin boven een links uitgelijnde knop | acties bij hun blok, lege staat links uitgelijnd | features/assignments/tabs/OverviewTab.tsx |
| F007 | Ruw | reis 1, begrotingsregel; eigenaar; formulier geopend op opdracht zonder looptijd | in het formulier zit een tweede formulier met eigen knop "Bewaar de looptijd van de opdracht", en "Afwijkende periode" is kale tekst; de uitleg bij Schaal noemt "Tarieven 2026" terwijl de periode nog onbekend is | looptijd vooraf vragen; een knopvorm; tarief pas noemen als de periode bekend is | features/assignments/BudgetEditor.tsx, PeriodChoice.tsx |
| F040 | Ruw | reis 9, Financieel op 390; beheerder; tab Financieel op smal scherm | een losse knop met drie puntjes staat rechts boven de tekst, zonder naam of context | de acties in één balk met de jaarkeuze | features/assignments/tabs/FinanceTab.tsx |

### Vacatures, team, taken

| Nr | Ernst | Waar, als wie | Wat er gebeurde | Wat je verwacht | Vermoedelijke plek |
|---|---|---|---|---|---|
| F023 | Kapot | reis 8, /vacatures/beheer; planner (geen beheerder); pagina "Vacatureformulier en taalmodel" geopend | de pagina blijft op "Bezig met laden" staan; de server antwoordt 403 en het scherm zegt dat niet | de melding "Beheer is voor beheerders", zoals op de andere beheerpagina's | features/vacancies (setup page, foutafhandeling 403) |
| F034 | Verwarrend | reis 4, vacature aanvragen; aanvrager (eigenaar van de opdracht); type contract ingevuld; "Aanleiding en motivatie" staat op "Nog niet ingevuld" | stap 1 "Aanvraag voorbereiden" is afgerond en de hoofdknop is "Vraag aan", terwijl de motivatie die op het aanvraagformulier hoort nog leeg is | de motivatie hoort bij de voorbereiding; "Vraag aan" pas daarna, of met de waarschuwing erbij | features/vacancies/steps.ts, services/vacancies (voorwaarde voor aanvragen) |
| F036 | Verwarrend | reis 4, aanvraagformulier; aanvrager; motivatie geschreven (stand "In de maak"), daarna "Maak aanvraagformulier" | de tab Aanvraag toont "Aanleiding en motivatie (concept, nog vaststellen): Nog niet ingevuld" en het formulier wordt zonder waarschuwing gemaakt met een leeg vak 2 | zeggen "De motivatie is nog niet vastgesteld en staat niet op het formulier", met de knop om vast te stellen | features/vacancies (Aanvraag-tab, RequestFormSection) |
| F041 | Verwarrend | reis 4, nieuwe vacature; eigenaar; "Nieuwe vacature" terwijl Bemensing van dezelfde opdracht zegt "1 van 4 rollen is nog open: Ontwerper" | de open rol staat niet in de keuzelijst (er bestaat al een conceptvacature voor), en het paneel zegt dat niet; je ziet alleen ingevulde rollen | bij de rol noemen "er loopt al een vacature" met een link | features/vacancies/VacanciesPage.tsx (CreateSheet), GET unfilled-roles |

### Offerte, tekenen, factureren, kosten, tarieven

| Nr | Ernst | Waar, als wie | Wat er gebeurde | Wat je verwacht | Vermoedelijke plek |
|---|---|---|---|---|---|
| F017 | Kapot | reis 1, offerte aanbieden; eigenaar; paneel "Offerte aanbieden" geopend en direct op "Bied aan" geklikt, zonder iets te kiezen | de offerte is aangeboden "Als document"; de drie manieren staan als tekstregels zonder zichtbare keuze of selectie, dus je ziet niet dat er al een gekozen is | keuzerondjes met een zichtbare selectie, geen standaard, en "Bied aan" pas na een keuze | features/quotes/OfferSheet.tsx |
| F026 | Kapot | reis 8, /factureren; teamlid zonder geldrechten; adres geopend (staat niet in zijn menu) | de pagina zegt "Er staat niets klaar om aan te leveren. Alle perioden die voorbij zijn, zijn afgesloten en gefactureerd", wat niet waar is; hij mag het alleen niet zien | "Dit is niet voor jou" met wie het wel ziet | features/billing/BillingPage.tsx (lege lijst door rechten onderscheiden van echt leeg; feit van de server) |
| F033 | Kapot | reis 8, /beheer/tarieven; persoon zonder rechten, teamlid, aanvrager; adres geopend | alle tarievenkaarten met de maandtarieven per categorie en de schalen per categorie staan er, ook de conceptkaart voor 2030, voor iemand die volgens het toegangsmodel geen geld ziet; de Beheer-pagina zelf zegt "Beheer is voor beheerders" | besluiten wie tarieven mag lezen en dat afdwingen op de server; nu leest iedereen ze | backend api/routes/rates.py (leesrecht), features/rates |
| F010 | Verwarrend | reis 1, offerte schrijven; eigenaar; schrijfpagina geopend in een instantie waar de afzender en standaardteksten nog niet zijn ingesteld | alle onderdelen staan op "Leeg", ook Leveringsvoorwaarden; niets zegt dat de standaardteksten en de afzender van de organisatie ontbreken en dat een beheerder die eerst moet instellen | een regel "De afzender en standaardteksten zijn nog niet ingesteld" met wie dat kan doen | features/quotes/QuoteDraftPage.tsx, GET quote-draft (feit toevoegen) |
| F011 | Verwarrend | reis 1, offerte schrijven; eigenaar; tekst van Inleiding getypt en "Bewaar" geklikt | het onderdeel blijft open staan met dezelfde knop "Bewaar"; alleen het kleine woord onder de kop wisselt naar "Zelf geschreven"; er is geen bevestiging en het volgende onderdeel opent niet | na bewaren het onderdeel sluiten met "Bewaard" en het volgende lege onderdeel aanbieden | features/quotes/QuoteDraftPage.tsx |
| F013 | Verwarrend | reis 1, offerte schrijven; eigenaar; bij "Scope" (staat op "Niet in deze offerte") op "Schrijf" geklikt, een concept laten opstellen en "Stel vast" geklikt | het onderdeel blijft "Niet in deze offerte"; niets zegt of de tekst bewaard is en hoe het onderdeel alsnog meedoet | schrijven zet het onderdeel in de offerte, of de knop heet "Neem op in de offerte" | features/quotes/QuoteDraftPage.tsx |
| F015 | Verwarrend | reis 1, offertebrief (pdf); eigenaar; offerte gemaakt zonder contactpersoon en ondertekenaar onder Beheer | de brief drukt de kop "Contactpersoon ODI | DigiGilde" zonder persoon eronder en een ondertekening zonder naam; het maken wordt niet tegengehouden en de schrijfpagina noemt het niet als probleem | quote-sheet (pagina 3) |
| F018 | Verwarrend | reis 1, offertekaart; eigenaar; offerte aangeboden als document | de kaart zegt "Aangeboden", het label in de kop van de opdracht zegt nog "Offerte gemaakt" | één stand, dezelfde woorden | features/assignments (statuslabel in ThingHead) of services: status van de opdracht na aanbieden |
| F028 | Verwarrend | reis 5, maand afsluiten; eigenaar; in "Klopt dit met wat er in maart is gewerkt?" het percentage van één persoon van 60 naar 40 gezet | het bedrag in die rij blijft € 9.000 (het geplande bedrag) tot na het afsluiten; pas daarna blijkt de maand € 32.900 in plaats van € 35.900 | het bedrag en het maandtotaal rekenen mee met het percentage, vóór het afsluiten | features/month-close (maandpaneel; voorvertoning van de server) |
| F030 | Verwarrend | reis 5, factuur vastleggen; eigenaar; factuur van € 101.600 vastgelegd op een levering van € 101.700 | de pagina toont beide bedragen in de kopregel maar meldt het verschil van € 100 nergens als punt om naar te kijken | een regel bij de periode: "€ 100 minder gefactureerd dan aangeleverd" | features/month-close, GET billing (signaal) |
| F031 | Verwarrend | reis 5, naverrekening; eigenaar; na de factuur een promotie met terugwerkende kracht vastgelegd (februari en maart waren afgesloten, aangeleverd en gefactureerd) | de kaart bovenaan zegt "Het eerste kwartaal 2026 is klaar: € 5.000. Alle maanden zijn afgesloten. Maak het factuurverzoek", en de periode springt van "Gefactureerd, factuur F-2026-0412" terug naar "Klaar om aan te leveren"; dat er al gefactureerd is en dat dit een naverrekening is, staat alleen in kleine tekst | "Naverrekening over het eerste kwartaal: € 5.000 aan te leveren", met de eerdere factuur zichtbaar bij de periode | features/month-close (kaart en periodestand), services billing |
| F012 | Ruw | reis 1, offerte schrijven; eigenaar; pagina na het overnemen van het profiel | drie onderdelen staan in de lijst als "Niet in deze offerte" (Scope, Beoogde resultaten, Raakvlakken en samenwerking), tussen de onderdelen die wel meedoen | wat niet meedoet onderaan of achter "Voeg een onderdeel toe" | features/quotes/QuoteDraftPage.tsx |
| F016 | Ruw | reis 1, offerte maken; eigenaar; "Maak offerte" met leeg veld "Geldig tot en met" | de offerte wordt gemaakt zonder geldigheid, zonder vraag of dat de bedoeling is | een voorstel (bijvoorbeeld 30 dagen) of een bevestiging | features/quotes |
| F019 | Ruw | reis 1, offertekaart; eigenaar; aangeboden als document | de regel luidt "Meegegeven, wacht op het getekende exemplaar"; "meegegeven" is geen gewoon woord voor wat er gebeurde | "Als document verstuurd; wacht op het getekende exemplaar" | features/quotes/offers.ts |

### Gedeelde bouwstenen

| Nr | Ernst | Waar, als wie | Wat er gebeurde | Wat je verwacht | Vermoedelijke plek |
|---|---|---|---|---|---|
| F001 | Ruw | reis 1, nieuwe opdracht; eigenaar; leeg verstuurd, daarna naam ingevuld | de melding "Geef de opdracht een naam." blijft staan terwijl de naam er staat, tot opnieuw versturen | melding verdwijnt zodra het veld is ingevuld | features/assignments (formulier nieuwe opdracht) of @/ui/layout FormSheet |
| F002 | Ruw | reis 1, opdrachtenlijst; eigenaar; lijst geopend | de weergaven Potentieel/Lopend/Afgesloten zijn een gevulde blauwe tab direct onder de hoofdknop (bekend, herstel loopt in de werkmap) | streep onder de gekozen weergave | @/ui/layout TabNav |
| F003 | Ruw | reis 1, kop nieuwe opdracht; eigenaar; opdracht net gemaakt | de kop toont vier keer "€ 0" en bij Afwijking "Geen ruimte", terwijl er nog geen begroting is | geen kerncijfers tot er een begroting is, of één regel "Nog geen begroting" | @/ui/layout KeyFigures of features/assignments/AssignmentLayout |
| F024 | Ruw | reis 8, beheerpagina's zonder recht; planner; /beheer, /beheer/offertes, /goedkeuren | drie verschillende vormen voor dezelfde boodschap (twee regels, één regel, andere tekst), gecentreerd onder een links uitgelijnde titel | één onderdeel voor "dit is niet voor jou", links uitgelijnd, met wie het wel kan | @/ui/layout (EmptyNotice of een NoAccess-blok) |
| F038 | Ruw | reis 1, offertekaart getekend; eigenaar; getekende offerte bekeken | de stappenbalk meldt in zijn tekst "Gemaakt, stap 1 van 3" terwijl alle drie de stappen zijn afgerond (de korte vorm voor smal scherm en hulptechnologie) | "Getekend, stap 3 van 3" of geen balk meer na het besluit | @/ui/StepBar (positie als alles klaar is), features/quotes/QuoteCard.tsx |
| F039 | Ruw | reis 3, persoonspagina; beheerder; persoon met een tariefverschil bekeken | in de tijdbalk begint het label met "Ander tarief · 100% Opdracht Alfa 2026"; het signaal staat als tekst vóór de naam van de opdracht in de balk | het signaal als teken naast de balk, de balk zelf alleen percentage en opdracht | @/ui/timeline |
| F042 | Ruw | algemeen, datumkiezer; iedereen; een datumveld geopend | de jaarlijst van de kiezer begint bij 1906 | jaren rond de looptijd | designsysteem (datumveld): min en max meegeven vanuit @/ui |

### Achterkant

| Nr | Ernst | Waar, als wie | Wat er gebeurde | Wat je verwacht | Vermoedelijke plek |
|---|---|---|---|---|---|
| F014 | Kapot | reis 1, offertebrief (pdf); eigenaar; offerte gemaakt voor 2027 met tarieven van 2027 (13.125 en 18.900) | Leveringsvoorwaarden punt 6 zegt "Deze offerte is gebaseerd op de tarieven van 2026"; het jaar volgt het moment van maken, niet de tarieven in de offerte | het jaar of de jaren van de tarieven die in de kostentabel staan | backend: services/quote_drafts.py of quote_sender.py (plaatshouder {jaar}) |
| F008 | Verwarrend | reis 1, begrotingsregel, rol kiezen; eigenaar; "Product" getypt | alleen "Productmanager" wordt aangeboden; "Product owner" en "Software engineer" vinden niets, want de rollenlijst kent ze als "po" en "Developer" en zoekt niet op de andere namen die de standaardteksten wel kennen (Ook: PO, Product owner) | één rollenlijst voor begroting, vacatures en standaardteksten | backend: rolcatalogus (seed of lader), grip/data/vacancy_texts |
| F035 | Verwarrend | reis 4, standaardtekst; aanvrager; "Begin met de standaardtekst" voor een vacature op Opdracht Alfa 2026 | de vacaturetekst krijgt de kop "Dit doe je bij Opdracht Alfa 2026": de interne naam van de opdracht staat als kop in een tekst die naar buiten gaat | een plaatshouder voor het team of product in gewone woorden, niet de naam van de opdracht | backend services/vacancies/library.py (plaatshouders), data/vacancy_texts |
| F020 | Ruw | reis 1, bewijs controleren; ondertekenaar; bewijspakket geüpload | de uitkomst spreekt van "vingerafdruk", elders heet hetzelfde "echtheidskenmerk" | één woord | backend grip/proof/verify.py (zinnen) |
| F029 | Ruw | reis 5, factuurverzoek (pdf); eigenaar; eerste kwartaal met drie rollen aangeleverd | één voetregel ("Aangeleverd op ... Dit is geen factuur. Adres ...") valt alleen op pagina 2; per maand staat geen subtotaal, terwijl het scherm de maandbedragen wel noemt | alles op één pagina voor een kwartaal met een handvol rollen; subtotaal per maand | backend grip/services/billing_document.py |

## Wat goed is en zo moet blijven

- De sommen kloppen overal, ook per dag binnen een maand en bij een naverrekening.
- De oorzaak van een tariefverschil staat in gewone woorden bij de regel ("Gepromoveerd per 15 maart 2027: vanaf dan categorie C, de regel is begroot op B").
- Bemensing biedt alleen de regels van de eigen opdracht en zegt in één zin hoe het staat.
- De promotie toont vooraf wat er verandert.
- Het aanleveren weigert zonder factuuradres en zegt welk veld ontbreekt.
- De offertebrief leest als een brief: briefhoofd, genummerde onderdelen, tabel, voorwaarden, ondertekening, bijlage.
- Het aanvraagformulier ziet eruit als het echte formulier, met de juiste vinkjes.
- Tekenen als uitgenodigde werkt van link tot ontvangstbewijs, en het bewijs controleren geeft een leesbare uitkomst.
- De tekenlink toont een vreemde alleen "Deze offerte staat niet voor je klaar".
- Geen pagina schuift zijwaarts op 390 breed; het lichte thema is leesbaar.
- De schrijfpagina van de offerte zegt hoeveel onderdelen er nog te schrijven zijn en met welk je begint.

## Wat in deze opstelling niet te testen was

- Inloggen via een echte login-dienst: de kopie draait zonder login. Het opnieuw inloggen bij het tekenen is dus niet gezien; het akkoord werd direct vastgelegd.
- Mail en pushmeldingen: er draaide geen postvanger en geen achtergrondproces.
- Het corpus: het paneel om een node te kiezen vroeg om een adres; of zoeken werkt als het corpus bereikbaar is, is niet vastgesteld.
- Een echte telefoon, een geïnstalleerde app en een passkey.
- Twee gekoppelde instanties: de kant van de opdrachtgever met een ontvangen offerte.

Onbekend blijft daarmee: of de tekenstap met een echte login goed terugkeert, of de mail aankomt en leesbaar is, en hoe de pagina's zich houden bij een verlopen sessie.


## Ronde twee

Gedaan na de herstellingen van ronde een, op de werkmap met een eigen database en eigen servers. Doorlopen: reis 2 helemaal (begroting gewijzigd na het aanbieden, nieuwe offerte via de schrijfpagina, de oude vervangen, aangeboden met een tekenlink, afgewezen door de uitgenodigde), reis 6 (kostenpost met een ontvangen en een verwachte factuur en dekking over twee opdrachten met een restant; nieuwe tarievenkaart met verhoging en de voorvertoning van vaststellen) en het bord Inzet als planner (plannen, inkorten, dubbel boeken, beëindigen). Niet gedaan: "Herschrijf selectie" met het lokale taalmodel, interne goedkeuring (vragen, goedkeuren, terugsturen), een bijlage bij een factuur van een kostenpost, en het vaststellen van de nieuwe tarievenkaart zelf.

| Nr | Ernst | Waar, als wie | Wat er gebeurde | Wat je verwacht | Stand |
|---|---|---|---|---|---|
| G001 | Kapot | reis 6, kostenpost; beheerder maakt een kostenpost | de beheerder kreeg een lege lijst begrotingsregels om te laten dekken, en geen manager kon de post zien: niemand kon hem dekken | wie een opdracht beheert ziet een ongedekte kostenpost en laat een eigen regel dekken | Hersteld: toegangsregel, test en `docs/toegang.md` |
| G002 | Verwarrend | reis 2, tab Offerte; eigenaar; begroting gewijzigd na de offerte | de kaart van de oude offerte hield "Bied aan" als hoofdknop, terwijl de kop zei dat er een nieuwe offerte nodig is | de volgende stap van de kaart is de nieuwe offerte | Hersteld |
| G003 | Verwarrend | reis 2, tab Offerte na een afwijzing; eigenaar | de tab opent met "Nieuwe offerte" en "Ga verder met de offerte"; dat de laatste offerte is afgewezen, door wie en waarom, staat niet bovenaan | de afwijzing met de reden bovenaan, daarna de weg naar een nieuwe offerte | Opgelost: de zin in de kop zegt wie afwees, wanneer en waarom, met de stap naar een nieuwe offerte |
| G004 | Ruw | reis 6, kostenpost; afwijking | "€ -1.000" met het woord "Overschrijding" ernaast | het bedrag zonder minteken; het woord zegt de richting | Hersteld |
| G005 | Ruw | reis 6, nieuwe tarievenkaart; beheerder; er staat al een concept voor 2030 | het formulier stelt 1 januari 2031 voor, een tweede concept na het eerste | zeggen dat er al een concept klaarstaat, of dat concept openen | Besloten: het formulier gaat verder na de laatste kaart van elke stand en twee kaarten met dezelfde begindatum worden geweigerd; de tarieven komen nu ook van die laatste kaart (G013) |
| G006 | Ruw | reis 2, schrijfpagina; voorbeeld (pdf) terwijl de afzender geen contactpersoon heeft | het voorbeeld drukt de kop "Contactpersoon" zonder persoon eronder; de pagina noemt het gat wel en het maken wordt geweigerd | in het voorbeeld de lege kop weglaten | Hersteld: een lege waarde neemt haar regel en het kopje erboven mee, en de tekst volgt weer als de waarde er is |
| G007 | Kapot | interne goedkeuring aangezet; beheerder wil een goedkeurder aanwijzen | het recht "Interne goedkeurder van offertes" stond niet in de lijst van rechten en de server weigerde het ("Onbekend recht in grip"); niemand kon goedkeurder worden, dus geen offerte kon nog de deur uit | het recht toekennen zoals elk ander | Hersteld: het recht staat in de lijst op de server en op het scherm, het voorbeeld heeft een goedkeurder, test |
| G008 | Kapot | interne goedkeuring; recht toegekend kort na middernacht | het recht telde niet: toekennen rekent met de lokale dag, het zoeken van een goedkeurder en het besluit met de dag in UTC; het besluit kwam terug met `besluit_fout=geen_recht` en de pagina zei daar niets over | een recht van vandaag telt vandaag | Hersteld, ook algemeen: één klok (`grip.core.clock`, ADR 0046). Elke "vandaag" en elke dag van een opgeslagen moment is de dag in Nederland; de schermen volgen dezelfde regel. Tests om 23:30 en 00:30 op een maandgrens, een jaargrens en rond zomer- en wintertijd. Open: de taaklaag (drie bestanden) vraagt de dag nog aan het proces |
| G009 | Kapot | interne goedkeuring; eigenaar; offerte teruggestuurd | "Teruggestuurd op ." zonder datum, naam of reden, terwijl de goedkeurder een reden schreef | wanneer, door wie en waarom | Hersteld: de zin leest het teruggestuurde verzoek uit de geschiedenis, test |
| G010 | Verwarrend | interne goedkeuring; eigenaar; tab Offerte | de kop zegt "Vraag die aan" ook als er nog niemand kan goedkeuren en ook nadat de offerte is teruggestuurd (dan is de stap "Maak nieuwe offerte"); de kaart toont "Wacht op goedkeuring" voordat er iets gevraagd is en nadat er is teruggestuurd; dezelfde zin staat drie keer (kop, kaart, onder de knop); de kop noemt "een offertegoedkeurder", een woord van het systeem | de kop volgt de stand van de goedkeuring, een zin per plek, "een interne goedkeurder van offertes" | Opgelost: de kop volgt de stand (niemand kan goedkeuren, teruggestuurd), de kaart zegt alleen wat er met de goedkeuring gebeurd is, het recht heet "Interne goedkeurder van offertes". Getest op de server, niet in de browser bekeken |
| G011 | Kapot | reis 5, maand heropend na aanlevering; eigenaar | een heropende en opnieuw afgesloten maand wordt opnieuw in zijn geheel aangeleverd (februari € 29.650), terwijl het eerste factuurverzoek februari nog noemt (€ 32.900); niets zei dat het tweede het eerste vervangt, dus de administratie factureert de maand twee keer | het nieuwe verzoek zegt wat het vervangt | Hersteld: de pagina van het eerste verzoek zegt dat de maand opnieuw is aangeleverd, in welk verzoek, en wat er van het verzoek nog telt; het nieuwe verzoek zegt op het scherm hetzelfde als in het document. "Aangeleverd" telt de maand één keer. De opzoeking heeft een eigen test. Een factuur op het vervangen verzoek blijft genoemd; het verschil is een creditering, en wie de maand opnieuw volledig factureert ziet dat als verschil |
| G012 | Ruw | reis 5, naverrekening als pdf | "Na te verrekenen over 2026-Q1", "Periode 2026-Q1" en de regel "Naverrekening 2026-03: Developer": codes in plaats van woorden; de regel toont 100% en € 15.000 bij een bedrag van € 2.500 zonder te zeggen dat het bedrag het verschil is; het paneel sprak van een factuurverzoek terwijl het document Naverrekening heet | maanden in woorden, een zin over de kolommen, hetzelfde woord in paneel en document | Bevestigd: naverrekening als pdf gemaakt en gelezen, maanden in woorden en de zin over de kolommen staan erin. Daarbij gevonden en hersteld: een tarief dat wijzigt op een vastgestelde kaart liet voor aangeleverde maanden geen naverrekening achter; test |
| G013 | Verwarrend | reis 6, nieuwe tarievenkaart na een concept; beheerder | de kaart voor 2029 nam de tarieven van de laatste vastgestelde kaart (2027) en sloeg het concept voor 2028 over | verder gaan op de laatste kaart, ook als die een concept is | Hersteld: de vorige kaart is de laatste van elke stand, test |
| G014 | Verwarrend | reis 6, "Stel vast" op de kaart voor 2029 terwijl 2028 nog een concept is | de voorvertoning zegt niet dat 2028 dan geen vastgestelde kaart heeft; daarna toont de lijst "Geen tarievenkaart" over 2028 | de voorvertoning noemt het gat vooraf | Bevestigd in de browser: de voorvertoning noemt elke periode zonder vastgestelde kaart, met het concept dat erin ligt |
| G015 | Ruw | reis 6, na het vaststellen | het scherm vroeg de voorvertoning nog een keer op voor een kaart die al vaststond en kreeg een weigering | niet meer vragen | Hersteld: het scherm vroeg de voorvertoning na het vaststellen nog steeds een keer op en kreeg een weigering; in de browser gelopen, nu geen verzoek meer |
| G016 | Ruw | tab Afsluiten en factureren met een naverrekening klaar; eigenaar | de kop van de opdracht noemt als stap het afsluiten van april, de tab noemt de naverrekening | een volgende stap | Opgelost: kop en tab volgen dezelfde volgorde, het oudste eerst; een naverrekening komt na het werk van de perioden en blijft op haar periode staan |

Ronde twee, tweede deel. Doorlopen in een browser: de naverrekening (maand heropend en lager afgesloten, daarna een promotie met terugwerkende kracht, aangeleverd via het paneel, beide pdf's bekeken), een nieuwe tarievenkaart met verhoging en "Stel vast" met de voorvertoning, een bijlage bij een factuur van een kostenpost (werkt, geen bevinding), en interne goedkeuring (aanzetten, vragen, terugsturen met een reden). Niet gedaan: goedkeuren en daarna aanbieden, "Herschrijf selectie" met het lokale taalmodel, en het bord Inzet met de hand.

Bedragen in ronde twee nagerekend: kostenpost 4.000 ontvangen plus 9.000 verwacht is 13.000 tegen 12.000 begroot; dekking 40 procent is 5.200, 35 procent is 4.550, ongedekt 3.250 (25 procent); een derde dekking van 40 procent wordt geweigerd met "115 procent". Maand maart met 40 in plaats van 100 procent: de rij gaat van 12.500 naar 5.000 en de maand van 35.900 naar 28.400, vóór het afsluiten.

### Ronde twee: wat een lezer zonder recht ziet

Gedaan op de werkmap, met een eigen database en eigen servers. Eerst de oorzaak hersteld, daarna alle adressen opnieuw nagelopen als acht soorten lezers, en de reizen gelopen die ronde een niet haalde: de dag van de beheerder (persoon toevoegen, een recht toekennen en intrekken, zichzelf manager maken op een opdracht van een ander, organisaties, een gedeeld onderdeel van de standaardteksten, het formulier met een ingevuld voorbeeld, Activiteit, Meldingen), de terugknop na een paneel en na bewaren, diepe links die koud worden geopend (de bestemming van een taak, een tab zonder recht, een onbekend adres), en de kant van de opdrachtgever als aanvrager tot aan het aanvraagformulier.

**De oorzaak van het eindeloze laden.** Een verzoek dat de server weigerde (403, 404) werd drie keer opnieuw gevraagd met oplopende pauzes. Zeven seconden lang stond er "Bezig met laden", terwijl het antwoord er al was. Een antwoord over de lezer wordt nu niet meer herhaald; alleen een uitblijvend antwoord, een keer. Daarnaast toonde elk scherm een weigering op zijn eigen manier. Er is nu een plek voor geen toegang, niet gevonden en niet bereikbaar; zie `docs/toegang.md`.

**De meting** (`just check-access`): 78 adressen, 8 lezers, 624 pagina's.

| | Voor | Na |
|---|---|---|
| Pagina's zonder bevinding | 225 | 511 |
| Blijft op "Bezig met laden" | 34 | 0 |
| Weigering die de pagina niet uitlegt | 269 | 109 |
| Actie bij een lezer die de server zou weigeren | 3 soorten (zie hieronder) | 0 |
| Bedrag of categorie bij wie geen geld mag zien | 4 (tarieven, F033) | 4 (tarieven, F033) |

De telling "voor" is gedaan met de eerste versie van de meting; die rekende de accountknop in de balk ook als actie. De echte acties waren van drie soorten: "Organisatie toevoegen" en "Nieuwe rol" voor iedereen, en "Maak een nieuwe offerte" voor een lezer. De 109 weigeringen die overblijven zijn een en dezelfde: een opdracht of vacature die de lezer niet mag zien, toont "bestaat niet, of je hebt er geen toegang toe" met een eigen melding in de schil in plaats van de gedeelde stand. De tekst klopt; alleen de vorm is nog niet de gedeelde. De persoon die alleen planner is (in de voorbeeldgegevens bestaat die niet, voor de meting aangemaakt) ziet op geen enkele pagina een bedrag van een ander; alleen de tarievenpagina toont bedragen (F033).

![De herstelde standen: tab zonder recht, pagina zonder recht, niet gevonden, de aanvraag die nog niet compleet is, de looptijd bij een nieuwe opdracht](rondgang/toegang-na.png)

| Nr | Stand | Wat er is gedaan |
|---|---|---|
| F023 | Hersteld | De weigering wordt niet meer herhaald; de pagina zegt "Je hebt hier geen toegang. Beheer is voor beheerders." |
| F027, F032 | Hersteld | Een tab die de lezer niet heeft, toont geen toegang en voor wie het wel is, zonder de acties en zinnen van de tab. Open: de tabbalk markeert dan "Overzicht" (T205) |
| F026 | Hersteld (toegang) | De server zegt of de lezer van enige opdracht de bedragen mag zien; mag dat niet, dan zegt Factureren "Je hebt hier geen toegang" in plaats van "alles is afgesloten" |
| F037 | Weg | De kop van de opdracht komt nu van de server; de meting vindt geen actie meer bij een lezer die niet mag |
| F034, F036 | Hersteld | De server weigert aanvragen en het formulier maken zolang iets ontbreekt of de motivatie niet is vastgesteld, met de lijst erbij. Dezelfde lijst staat in het antwoord van de vacature; het scherm toont haar bij het formulier en houdt stap een open |
| F024 | Hersteld | Een onderdeel voor "dit is niet voor jou", links uitgelijnd, met voor wie het wel is; negen eigen versies vervangen |
| F001 | Hersteld | De melding van een formulier gaat weg zodra de lezer een veld wijzigt, in elk paneel (ook de formulieren van Team) |
| F004 | Hersteld | Een nieuwe opdracht vraagt de looptijd (niet verplicht); Overzicht zegt het als die ontbreekt |
| F041 | Hersteld | "Nieuwe vacature" zegt voor welke rollen al een vacature loopt |
| F042 | Hersteld | Datumvelden bieden tien jaar terug tot vijftien jaar vooruit |
| F035 | Hersteld | De standaardtekst vraagt het team of product in gewone woorden en noemt de interne naam alleen als geheugensteun |
| F025 | Was al hersteld | Financieel opent op het eerste jaar van de looptijd |
| F003, F021 | Open, bij de werkstromen | Kop van de opdracht |
| F005, F040 | Bevestigd op 9 oktober 2026, in de browser | Op Overzicht staan de acties links bij hun blok; op Financieel staan ze op smal scherm in een balk met de jaarkeuze |
| F007 | Bevestigd op 9 oktober 2026, in de code | Geen tweede formulier meer in het begrotingsformulier, de looptijd wordt op het tabblad gevraagd en "Afwijkende periode" is een knop; de uitleg bij Schaal is niet nagekeken |
| F002 | Bevestigd op 9 oktober 2026, in de browser | De weergaven van de opdrachtenlijst hebben een streep onder de gekozen weergave |
| F013 | Bevestigd op 9 oktober 2026, in de code | Schrijven in een onderdeel dat niet meedoet neemt het op in de offerte |
| F008 | Open | Een rollenlijst voor begroting, vacatures en standaardteksten vraagt een besluit over samenvoegen |
| F038, F039, F022 | Open | Stappenbalk na het besluit, label in de tijdbalk, zoeken in het corpus |

Nieuwe bevindingen uit deze reizen:

| Nr | Ernst | Waar, als wie | Wat er gebeurde | Wat je verwacht | Stand |
|---|---|---|---|---|---|
| T201 | Verwarrend | Activiteit; beheerder | Een recht intrekken staat er als "Recht in grip van <naam> gewijzigd"; toekennen noemt niet welk recht; "Rol op de opdracht van <naam> toegevoegd" noemt de opdracht niet | "Recht lezer van <naam> ingetrokken", "<naam> is manager van <opdracht>" | Open |
| T202 | Verwarrend | Kop van een opdracht; lezer en teamlid | "Je wacht op <eigenaar> of een manager, die maart 2026 afsluit. Jij hoeft nu niets te doen. Had klaar moeten zijn op 7 apr 2026" voor wie er niet bij betrokken is | voor wie niets met de stap te maken heeft alleen waar de opdracht staat | Opgelost: wie niets met de stap te maken heeft leest wie aan zet is, zonder termijn |
| T203 | Ruw | Persoonspagina van een nieuwe persoon; beheerder | Declarabiliteit toont "€ 0", een lege balk en twee keer "€ 0" terwijl er nog geen inzet en geen target is | het blok pas tonen als er iets te tonen is | Open |
| T204 | Ruw | Organisaties; beheerder | "Organisatie toevoegen" opent een formulier in de pagina met een eigen hoofdknop, naast "Haal het register op": twee accenten, en geen paneel zoals elders | toevoegen in een paneel | Open |
| T205 | Ruw | Diepe link naar een tab zonder recht | De tabbalk markeert "Overzicht" terwijl de inhoud "geen toegang" is | geen tab gemarkeerd | Opgelost: geen tab gemarkeerd |
| T206 | Ruw | Beheerpagina's; wie geen beheerder is | De teruglink zegt "Terug naar Beheer", een pagina die deze lezer niet heeft | terug naar Start | Open voor de pagina's die hun weigering zelf tonen |
| T207 | Ruw | Offerte aanvragen; aanvrager | Een alinea legt uit wat context is en dat het niet verplicht is | de uitleg weg, het veld zegt "optioneel" | Open |

Wat werkte en zo moet blijven: een persoon toevoegen landt op de pagina van die persoon; een recht toekennen toont vooraf wat het toestaat en intrekken vraagt bevestiging; de beheerder die zichzelf manager maakt, krijgt daarna de acties van een manager; een gedeeld onderdeel van de standaardteksten zegt in welke twaalf rollen het staat; de bestemming van een taak opent koud het juiste paneel; de terugknop na een paneel en na bewaren komt uit op de vorige pagina.

Niet gedaan: uitgelogd (de ontwikkelmodus kent geen uitgelogde stand), een tekenlink terwijl je bent uitgelogd, herladen midden in een paneel, twee tabbladen tegelijk, en de ontvangen offerte aan de kant van de opdrachtgever (daar zijn twee gekoppelde instanties voor nodig; het verkeer stond uit, de pagina zegt dat).

## Ronde drie

Gedaan op de werkmap, met een eigen database, eigen servers en een eigen hostnaam, in een echte browser. Het was daarbij kort na middernacht, zodat de dag in UTC nog gisteren was. Gelopen: interne goedkeuring van begin tot eind (aanzetten, het recht toekennen, een offerte maken, goedkeuring vragen, goedkeuren, aanbieden met een tekenlink, tekenen als de uitgenodigde); "Herschrijf selectie" in de teksteditor van de offerte met het taalmodel van de ontwikkelaar; het Inzet-bord met de hand (plannen, inkorten, een einddatum voor de begindatum, boven 100% plannen, onzin als percentage); een passkey vastleggen met een virtuele sleutel in de browser, intrekken, opnieuw vastleggen en er een goedkeuring mee bevestigen; en alle hoofdpagina's op 390 breed als eigenaar.

| Nr | Ernst | Waar, als wie | Wat er gebeurde | Wat je verwacht | Stand |
|---|---|---|---|---|---|
| H001 | Kapot | elke pagina met een datum van een moment; kort na middernacht | "Gemaakt op 8 okt 2026" voor een offerte die op 9 oktober om 00:56 was gemaakt: het scherm nam de eerste tien tekens van het moment, en dat is de dag in UTC | de dag in Nederland | Hersteld: de gedeelde datumopmaak neemt de dag van een moment op de kalender van de instantie; tijden staan op de klok van de instantie, wat het apparaat ook zegt; test |
| H002 | Kapot | schrijfpagina van de offerte, "Herschrijf selectie"; eigenaar; een stukje van een zin geselecteerd | het voorstel was een complete nieuwe inleiding van 80 woorden, met de looptijd en de rollen van de opdracht erin; overnemen zet die op de plek van twee woorden | de passage herschreven, ongeveer even lang | Hersteld: een herschrijving krijgt alleen de passage en de aanwijzing mee, niet de gegevens van de opdracht, met een eigen opdracht aan het model; een voorstel dat veel langer is dan de passage wordt geweigerd met een zin die zegt wat te doen; tests. Daarna gaf een hele zin een kortere zin terug en bleef een fragment een fragment |
| H003 | Kapot | Inzet-bord, "Open rollen"; planner; iemand ingekort tot en met april op een rol die tot en met juni loopt | de rol verdween uit "Open rollen", terwijl mei en juni niemand hadden; dezelfde telling voedt de open rollen bij Vacatures en het aantal in de rapportage | een rol die een deel van haar periode leeg is, staat open voor dat deel | Hersteld: geteld per maand van de periode van de rol, zoals de bemensing van een opdracht dat doet; het bord toont de rol in de maanden die open zijn; tests |
| H004 | Kapot | kop van een opdracht, "Neem deze stap over"; eigenaar die wacht op de interne goedkeurder | de kop zegt daarna tegen de eigenaar "Beoordeel de offerte, keur haar goed of stuur haar terug", terwijl zij het recht niet heeft en haar eigen offerte niet mag goedkeuren; bij de goedkeurder verdween de taak uit Taken (ze stond nog wel onder "Offertes ter goedkeuring") | een stap die een recht vraagt, kan alleen worden overgenomen door wie dat recht heeft | Opgelost: overnemen kan alleen wie het recht van de stap zelf al heeft, en nooit een stap waar een ander moet beslissen (goedkeuring, advies, akkoord, oordeel, het besluit van de opdrachtgever); de server weigert het ook, en de goedkeuring zelf weigert wie de offerte maakte of de goedkeuring vroeg |
| H005 | Verwarrend | schrijfpagina van een offerte die al gemaakt en goedgekeurd is; eigenaar; adres geopend | "De offerte is klaar om te maken", met "Maak offerte" als hoofdknop, alsof er nog niets is gemaakt | zeggen dat er al een offerte ligt en wat een nieuwe daarmee doet | Hersteld: de schrijfpagina toont de gemaakte offerte met de weg terug naar de tab; een nieuw concept begint alleen via "Maak een nieuwe offerte" |
| H006 | Verwarrend | Inzet-bord, "Nieuwe inzet"; planner; iemand die al 80% heeft krijgt er 100% bij | het formulier zegt niets; pas na het bewaren staat er "Boven 100% in jan, feb, mrt, apr" bij de persoon | vooraf zeggen op hoeveel de persoon uitkomt en in welke maanden | Hersteld: het formulier vraagt de server op hoeveel de persoon uitkomt en noemt de maanden; de knop wordt "Bewaar boven 100%" |
| H007 | Verwarrend | Inzet-bord en tab Bemensing; planner; inzet per vergissing vastgelegd | nergens is een inzet te verwijderen: inkorten kan, een einddatum voor de begindatum wordt geweigerd; de server kent het verwijderen wel | een vergissing weghalen, met een bevestiging | Hersteld: "Verwijder de inzet" in het menu van het paneel waarmee beide schermen een inzet openen, met bevestiging; de server weigert bij een afgesloten maand en het paneel toont de reden |
| H008 | Ruw | tab Offerte, kaart van een aangeboden of getekende offerte; eigenaar | de regel "Intern goedgekeurd op ... door ..." verdwijnt van de kaart zodra de offerte is aangeboden | wie goedkeurde blijft bij de offerte staan | Hersteld: wie goedkeurde blijft op de kaart staan, ook na aanbieden en tekenen |
| H009 | Ruw | Inzet-bord op 390 breed | het bord opent op juli, augustus en september; de lopende maand staat buiten beeld | de lopende maand in beeld bij openen | Hersteld: het bord opent met de lopende maand als eerste naast de namen |
| H010 | Ruw | "Nieuwe inzet", keuzelijst Persoon; planner | ook wie alleen een recht heeft (een aanvrager, een tekenbevoegde van de opdrachtgever die als persoon is toegevoegd) staat in de lijst om in te plannen | alleen wie in dienst is of wordt ingehuurd | Hersteld: de keuzelijst biedt wie een inzetschaal of een inhuur heeft die niet is afgelopen, of in dienst is of komt |
| H011 | Ruw | opdracht, tab Overzicht; lezer | de pagina vroeg de lijst van corpora op en kreeg een weigering, zonder dat de lezer iets met context kan doen | niet vragen wat niet nodig is | Hersteld: de kiezer wordt pas geladen als het paneel opengaat |
| H012 | Ruw | `just check-access` met een naam met een spatie | de taak gaf de aanhalingstekens niet door en vond niemand | de argumenten zoals ze zijn getypt | Hersteld |

**De meting** (`just check-access`) op de huidige stand: 78 adressen, 8 lezers, 624 pagina's, 619 zonder bevinding. De 109 weigeringen zonder uitleg in de twee koppen zijn weg. Wat overblijft is vier keer de tarievenpagina (F033, wacht op een besluit); de ene nieuwe bevinding was H011.

| Lezer | Inhoud | Leeg | Geen toegang | Niet gevonden | Blijft laden | Weigering zonder uitleg | Actie die niet mag | Bedrag of schaal | Fout |
|---|---|---|---|---|---|---|---|---|---|
| Beheerder | 62 | 9 | 1 | 6 | 0 | 0 | 0 | 0 | 0 |
| Eigenaar | 31 | 8 | 12 | 27 | 0 | 0 | 0 | 0 | 0 |
| Planner en manager | 45 | 8 | 17 | 8 | 0 | 0 | 0 | 0 | 0 |
| Alleen planner | 39 | 8 | 21 | 10 | 0 | 0 | 0 | 1 | 0 |
| Lezer | 45 | 9 | 17 | 7 | 0 | 0 (was 1, H011) | 0 | 0 | 0 |
| Teamlid | 14 | 6 | 13 | 45 | 0 | 0 | 0 | 1 | 0 |
| Aanvrager | 10 | 9 | 13 | 46 | 0 | 0 | 0 | 1 | 0 |
| Zonder rechten | 8 | 11 | 13 | 46 | 0 | 0 | 0 | 1 | 0 |

Wat werkte en zo moet blijven: een recht dat om half één 's nachts is toegekend telde meteen bij het goedkeuren; de goedkeurder ziet het verzoek op Start, onder Taken en onder "Offertes ter goedkeuring", met het bedrag en wie het vroeg; na het besluit staat er wie, namens wie, wanneer en waarmee is bevestigd, met het bewijs erbij; "Bied aan" weigert een leeg e-mailadres met een zin; de tekenlink werkt alleen voor het genoemde adres; de uitgenodigde tekent met functie en bevoegdheid en de eigenaar ziet daarna "Zet in uitvoering"; een passkey vastleggen, intrekken en gebruiken werkt, en de pagina toont wanneer hij het laatst is gebruikt; het bord weigert een einddatum voor de begindatum en elk percentage buiten 0 tot en met 100 met een zin; op 390 breed loopt geen enkele pagina buiten beeld.

Niet gedaan: tekenen als iemand zonder persoon in grip (de ontwikkelmodus kent geen gast; de uitgenodigde is als persoon toegevoegd), opnieuw inloggen bij een echte inlogdienst na de passkey, en een passkey op een echt apparaat.

## Ronde zes, deel A

Gelopen op 9 oktober 2026 op commit `5bd1c57`, op een eigen kopie met een echte browser en, waar een formulier tegenwerkte, rechtstreeks via de API (dat staat er per reis bij). Deel A deed drie reizen: de rest van werven, kosten en tarieven, en bemensen met de hand.

| Reis | Hoe ver |
|---|---|
| 4. Werven, vanaf de tekst | Standaardtekst genomen en de open plekken ingevuld in de editor (browser); een tekst op maat opgesteld (9,7 seconden, met de context uit het corpus); om een oordeel gevraagd, opmerking op een onderdeel, terug met opmerkingen, beantwoord, nieuwe versie, een verouderde opslag geweigerd (409), tweede ronde, akkoord, vastgesteld; de schrijver kan haar eigen tekst niet beoordelen (API). Link naar de gepubliceerde vacature (alleen https), verwijzing naar het wervingssysteem, vervuld met een nieuwe collega die op de rol en het bord staat (API, schermen bekeken). De variant met een bekende kandidaat vanaf een ingevulde rol, tot en met vervuld; openstellen wordt geweigerd (API). Niet: de formulieren voor beoordelen en opmerkingen in de browser |
| 6. Kosten en tarieven | Kostenpost met twee verwachte facturen, een ontvangen factuur met bijlage, dekking over twee opdrachten met een restant, dekking boven 100 procent geweigerd, "Verdeel het restant" geopend met 20 ingevuld (API en schermen bekeken). Tarievenkaart vanaf 1 juli met 5 procent op tientallen, de voorvertoning gelezen in de browser, vastgesteld (API), het gevolg bekeken op Financieel, de afsluittab en de persoonspagina. Niet: een factuur boven het verwachte bedrag apart, de volgorde van de lijst beoordeeld |
| 3. Bemensen | Vanaf de tab Bemensing een nieuwe inzet voor iemand die vol zit: de waarschuwing staat er voor het bewaren, de knop wordt "Bewaar boven 100%" (browser). Inplannen, inkorten, verwijderen, en de weigering in een afgesloten maand (API). Een promotie per de 16e: voorvertoning, opgeslagen, de oorzaak staat op Financieel bij de regel. Niet: het bord Inzet met de hand, vanuit een maandcel, "Open een vacature voor deze rol" |

Twee ketens van bedragen, nagerekend:

- Kostenpost: begroot € 20.000; ontvangen € 6.500 plus verwacht € 10.000 is € 16.500 verwacht totaal; ruimte € 3.500; dekking 50 procent (€ 8.250) en 30 procent (€ 4.950) is € 13.200; ongedekt 20 procent is € 3.300. Op de opdracht komt de helft van de ontvangen factuur, € 3.250, bij het gerealiseerde: € 73.450 werd € 76.700.
- Herprijsde maanden: categorie B ging per 1 juli van € 12.500 naar € 13.130, C van € 15.000 naar € 15.750. Twee aangeleverde maanden van een halve inzet in C: 2 keer € 375 is € 750 naverrekening, gelijk in de voorvertoning, de taak, Financieel ("€ 750 nog aan te leveren") en de afsluittab (afgesloten € 15.750, aangeleverd € 15.000). Promotie per 16 september van B naar C: september 15 dagen tegen elk tarief is € 14.440, oktober € 15.750; verwacht totaal van de regel € 162.950, gelijk op Financieel en op de persoonspagina.

| Id | Ernst | Reis, stap, wie | Wat er gebeurde | Verwacht | Stand |
|---|---|---|---|---|---|
| A601 | Verwarrend | reis 4, vacaturetekst schrijven; aanvrager | "Ga naar de volgende" sloeg na elke ingevulde plek de volgende over (er werd geteld hoe vaak er was gedrukt, terwijl de lijst korter werd): zeven invullingen kwamen op verkeerde plekken terecht | de eerstvolgende open plek na de cursor | Hersteld: `ui/text/openPlaces.ts` met test, gebruikt in `ui/TextEditor.tsx`; opnieuw gelopen: drie invullingen op volgorde, geen open plek overgeslagen |
| A602 | Ruw | reis 4, "Vraag om een oordeel"; aanvrager | de lijst met beoordelaars toont iedereen in de instantie, ook de aanvrager en de tekenbevoegde van een opdrachtgever; geen voorkeur | alleen collega's die de vacature mogen lezen, de waarschijnlijke beoordelaar bovenaan | Hersteld (ronde zeven): een regel voor wie iets intern kan beoordelen; wie alleen een recht namens een opdrachtgever heeft staat niet in de lijst en wordt door de server geweigerd, voor beoordelaar, adviseur, akkoordgever en geadresseerde; test |
| A603 | Ruw | reis 4, tab Tekst met een concept; aanvrager | drie gelijke knoppen ("Vraag om een oordeel", "Schrijf verder", "Stel een tekst op maat op") zonder accent; de regel erboven zegt nog "Jij: schrijf de vacaturetekst" terwijl de tekst af is | de volgende stap als accent en in de zin | Hersteld (ronde zeven): de zin en de taak volgen de stand van de tekst ("Leg de vacaturetekst voor of stel haar vast", "Stel de vacaturetekst vast") en leiden naar de tab; de stap staat vooraan en is het accent als de kop er geen heeft |
| A604 | Verwarrend | reis 4, kop van een vacature; een beheerder die geen deel heeft, en de beoordelaar van de tekst | leest "Je wacht op <aanvrager>, die ... Jij hoeft nu niets te doen"; de beoordelaar van de vacaturetekst leest dat zij wacht op het schrijven van de motivatie | wie meekijkt leest wie aan zet is, zonder "je wacht" (zoals T202 bij opdrachten) | Hersteld in deel B: `tasks/access.py`, `tasks/course.py`, test; opnieuw gelopen |
| A605 | Ruw | reis 4, link naar de gepubliceerde vacature; aanvrager | een link voor "rijksbreed" is vast te leggen terwijl de procedure die stap nog weigert; de kop toont dan "Bekijk de vacature op Werken voor Nederland" | de plekken volgen de stappen die gezet zijn | Open |
| A606 | Ruw | reis 4, vervulde vacature; aanvrager | na het vervullen heeft de kop geen zin meer (wie, per wanneer) en de tab Aanvraag biedt nog "Maak aanvraagformulier" | een slotzin "Vervuld: <naam> start op <datum>", geen actie die niets meer doet | Hersteld (ronde zeven): de kop sluit met "Vervuld: <naam> start op <datum>"; voor een vervulde, ingetrokken of afgewezen vacature wordt geen aanvraagformulier meer gemaakt of aangeboden; op beeld gezien |
| A607 | Ruw | reis 6, dekking boven 100 procent; manager | de weigering zei "komt op 110.00 procent" | "110 procent" | Hersteld: `services/costs.py`, test |
| A608 | Ruw | reis 6, dekking kiezen; manager | dekking en "Verdeel het restant" bieden ook personeelsregels aan (een kostenpost gedekt door de regel "Productmanager") | alleen regels met een vast bedrag, of zeggen dat het mag | Open; vraag aan de opdrachtgever van grip. Voorbereid: in de keuzelijst staan regels met een vast bedrag eerst en heet een personeelsregel zo; de regel zelf is niet gewijzigd |
| A609 | Ruw | reis 6, kostenpost als beheerder die haar maakte | ziet de dekking zonder actie en heeft zelf geen regels om uit te kiezen | een regel die zegt wie de dekking vastlegt | Hersteld: wie geen regel kan kiezen leest dat de eigenaar of manager van een opdracht de dekking vastlegt; niet in de browser bekeken |
| A610 | Verwarrend | reis 4 en 6, vervullen met een nieuwe collega; aanvrager, daarna eigenaar | een nieuwe collega die bij het vervullen meteen wordt ingezet had geen inzetschaal; Financieel van de opdracht zei daarna "1 regel kon niet worden berekend" en "Gerealiseerde inzet: niet bekend" | de nieuwe collega krijgt de schaal van de vacature vanaf de startdatum | Hersteld: `services/vacancy_hire.py`, test. Aanname: de schaal van de vacature is de inzetschaal bij aanvang |
| A611 | Ruw | reis 3, inzet wijzigen of verwijderen in een afgesloten maand; eigenaar, planner | de weigering zei "De maand 2026-01 is afgesloten" | "De maand januari 2026 is afgesloten" | Hersteld: `services/errors.py`, test |
| A612 | Verwarrend | reis 6, een tarievenkaart vaststellen; beheerder, daarna eigenaar | een nieuwe kaart herprijst ook de begroting van een opdracht met een getekende offerte; Financieel meldt daarna "De begroting is € 14.580 hoger dan de getekende offerte" zonder dat iemand de begroting wijzigde | een besluit: volgt de begroting van een getekende opdracht de tarieven, of staat ze vast op de tarieven van de offerte | Open; vraag aan de opdrachtgever van grip. Zichtbaar gemaakt: de voorvertoning zegt hoeveel van de herprijsde opdrachten een getekende offerte hebben en hoeveel de begroting daar samen afwijkt van wat is getekend; tests |
| A613 | Ruw | reis 6, nieuwe tarievenkaart; beheerder | een kaart die voor een latere kaart begint krijgt van de server geen einddatum als die niet wordt meegegeven; pas het vaststellen weigert, met een duidelijke zin | de server stelt de dag voor de volgende kaart voor, zoals het formulier doet | Open: een bestaande test legt vast dat een concept zonder einddatum mag en dat pas het vaststellen weigert; niet gewijzigd |

Wat goed was en zo moet blijven: de voorvertoning van een tarievenkaart leest als gewone zinnen en noemt de naverrekening per maand; een verouderde opslag van een tekst wordt geweigerd met de naam van wie intussen opsloeg; een vacature voor een bekende kandidaat heeft een korter verloop zonder openstellen; de kostenpost toont het ongedekte deel in beeld en in de tabel met hetzelfde bedrag.

## Ronde zes, deel B

Gelopen op 9 oktober 2026 op commit `5bd1c57`, op een eigen kopie met een echte browser, een eigen postvanger en het achtergrondproces; waar een formulier tegenwerkte rechtstreeks via de API (dat staat erbij). Deel B deed de controle van eerdere herstellingen, de dag van de beheerder, de randen, de kant van de opdrachtgever voor zover één instantie dat toelaat, en de ochtend erna.

| Deel | Hoe ver |
|---|---|
| Controle van herstellingen | 26 nagelopen, zie de tabel hieronder. Niet: wat een moment rond middernacht vraagt (G008, H001), de naverrekening als pdf (G012), het gat tussen tarievenkaarten (G014, G015), de deels open rol (H003), de lopende vacature in "Nieuwe vacature" (F041) |
| 7. De dag van de beheerder | Een opdracht gemaakt via het scherm; een persoon toegevoegd (API, het formulier geopend); elk recht toegekend en ingetrokken, ook "Interne goedkeurder van offertes" (API); zichzelf manager gemaakt van de opdracht van een ander en de regel in Activiteit gelezen; een tekstblok gewijzigd: het pdf van een bestaande offerte blijft byte voor byte gelijk, een nieuw concept neemt de tekst over; instelling voor goedkeuring; Activiteit bekeken; "Bekijk als" een ander en terug (browser); een passkey vastgelegd met een virtuele sleutel en daarmee de offerte van een ander goedgekeurd, met bewijs "Bevestigd met Passkey" (browser); een maand heropend met reden en opnieuw aangeleverd. Niet: standaardteksten van vacatures, het formulier met voorbeeld en bronnen, het voorvoegsel van het kenmerk, Meldingen op beeld, een passkey intrekken, organisaties ophalen (overgeslagen: niet zeker dat de bron alleen-lezen is) |
| Mail | Voor het eerst gezien: de mail met de tekenlink komt aan, met afzender, antwoordadres, een link op het eigen adres en de uitleg "Zo controleert u dit bericht"; de kaart toont "Gemaild op 9 okt 2026" |
| Tekenen en bewijs | Als uitgenodigde gast getekend via het scherm; het bewijs gedownload en gecontroleerd: geldig, met drie bewezen en vier niet bewezen punten; één teken gewijzigd: ongeldig, met twee gewone zinnen. Een ander die de link opent leest "Deze offerte staat niet voor je klaar". Verlopen en ingetrokken: de server geeft 404, vernieuwen opent hem weer (API; het scherm daarbij niet bekeken) |
| Randen | Offerte schrijven: bewaren sluit het onderdeel en opent het volgende lege; herladen midden in een onderdeel zet de niet bewaarde tekst terug en zegt dat; hetzelfde onderdeel in twee tabbladen: het tweede leest wie het intussen wijzigde, dat er niets is overschreven, en kiest tussen "Bewaar mijn tekst" en "Neem de andere tekst over". Terugknop na een taaklink die een formulier opent: terug naar Taken, vooruit opent het formulier niet opnieuw. Koude links als lezer zonder recht: Beheer, vacaturetekst, goedkeuren en een persoon geven een eigen zin; een onbekend adres zegt "Pagina niet gevonden". Een maand tweemaal afsluiten wordt geweigerd. Niet: herladen met een open formulier (het script kreeg het formulier niet open), de terugknop na elk formulier |
| Kant van de opdrachtgever | De aanvrager ziet Start, Taken, Vacatures en Aanvragen; het formulier "Offerte aanvragen" zegt dat het verkeer met andere organisaties uitstaat en heeft geen opdrachtnemer om te kiezen. Verder is er in één instantie niets te lopen: versturen, ontvangen, de ontvangen offerte en akkoord als opdrachtgever vragen twee gekoppelde instanties |
| De ochtend erna | Feed en Taken gelezen als twaalf personen, met een nieuwe zuivere planner. Geen bedrag in de feed. De planner krijgt de open rollen als taak en nieuws over nieuwe opdrachten; de aanvrager heeft niets; teamleden lezen "Je bent ingezet op ...". Elke link in elke feed geopend als die lezer: vijf openden niet (B604, hersteld). De tekenbevoegde leest nog steeds nieuws over vacatures (R502) |

De vraag over de feed, met bewijs: een leidinggevende leest dat haar medewerker is ingezet op een opdracht die zij zelf niet kan openen, en een teamlid leest over zijn eigen inzet op een opdracht die is afgerond. Het nieuws is van hen en de naam van de opdracht mogen zij weten; de link gaf "Niet gevonden". Nu staat de naam er zonder link voor wie de opdracht niet kan openen, en met link voor wie dat wel kan.

Nagerekend: na heropenen van februari en opnieuw aanleveren is afgesloten € 105.200 gelijk aan aangeleverd € 105.200; het tweede verzoek zegt dat het februari uit het eerste vervangt (€ 32.900) en dat het verschil € 500 is.

| Id | Ernst | Reis, stap, wie | Wat er gebeurde | Verwacht | Stand |
|---|---|---|---|---|---|
| B601 | Verwarrend | interne goedkeuring, na terugsturen; maker | de kop zei "Pas de begroting aan en maak daarna een nieuwe offerte" zonder de reden van de beoordelaar, ook als de reden over de tekst ging | de reden in de zin, en niet alleen de begroting als uitweg | Hersteld: de zin noemt de reden en zegt "Verwerk dat in de begroting of de tekst"; `tasks/telling.py`, `data/tasks/guidance.json`, test; opnieuw gelopen. De knop heet nog "Pas de begroting aan" |
| B602 | Ruw | reis 5, aanleveren zonder factuurgegevens; eigenaar | "het factuuradres en postcode en plaats ontbreekt" | "ontbreken" bij meer dan één | Hersteld: `services/billing_deliveries.py`, test |
| B603 | Verwarrend | Beheer, Activiteit; beheerder | het scherm maakte zijn eigen zinnen uit de ruwe velden: "Status draft", en regels als "Gegevens toegevoegd: Totaal € 33.400" voor een soort zonder naam, terwijl de server elke regel al in woorden meegeeft | de woorden van de server | Hersteld: het scherm neemt de zin en de regels van de server; `features/history/words.ts`, test; opnieuw bekeken |
| B604 | Verwarrend | "Wat is er gebeurd"; leidinggevende, teamlid | vijf links naar een opdracht die de lezer niet kan openen | de naam zonder link | Hersteld: `events/news.py`, test; opnieuw gelopen |
| B605 | Ruw | interne opdracht; eigenaar | de server noemt bij een interne opdracht ook "offerte gemaakt" en "aangevraagd" als toegestane overgang | alleen wat een interne opdracht kan worden | Bevestigd: de server laat bij een interne opdracht de stappen naar de opdrachtgever weg |
| B606 | Ruw | reis 3, formulier van een inzet; planner | "Verwijder de inzet" zit achter een los menu met drie punten onderaan het formulier; de waarschuwing boven 100 procent eindigt met "De knop zegt wat je bewaart", een zin over de interface | de actie waar je haar zoekt; een waarschuwing die alleen over de inzet gaat | Open; gebied van deel A |
| B607 | Ruw | Team, voorstellen uit Wies; beheerder | de pagina toont blijvend "Ophalen op 8 okt 2026 is mislukt, Wies gaf status 403" | een zin die zegt wat de beheerder kan doen, of niets als er niets te doen is | Hersteld (ronde zeven) voor Rollen: een rustige regel die zegt wat te doen, geen blijvende foutbalk; de pagina met voorstellen uit Wies zelf is niet aangepast |
| B608 | Verwarrend | Beheer, tekstblokken van de offerte; beheerder, daarna eigenaar | een gewijzigd tekstblok komt in een nieuw concept, niet in een concept dat al bestond en waarvan niemand dat onderdeel had aangeraakt | een onderdeel dat niemand wijzigde volgt het blok, zoals de code zelf belooft | Hersteld: een onderdeel dat niemand schreef volgt de tekst van de organisatie tot de offerte wordt gemaakt; een onderdeel dat hier is geschreven houdt zijn tekst, zegt dat de standaardtekst sindsdien is gewijzigd en biedt 'Neem de nieuwe tekst over'; tests, in de browser gezien |
| B609 | Ruw | rechten; beheerder | een beheerder kan zijn eigen recht als beheerder intrekken zonder vraag zolang er een tweede is; daarna kan alleen die ander het teruggeven | een bevestiging, of alleen een ander kan het | Hersteld (ronde zeven): je eigen recht intrekken vraagt "Je eigen recht ... intrekken?" met wat het gevolg is; test. De server staat het nog toe zolang er een tweede beheerder is |
| B610 | Ruw | begrotingsregel in twee tabbladen; eigenaar | de laatste die bewaart wint, zonder melding; onderdelen van een offerte en vacatureteksten weigeren een verouderde opslag wel | dezelfde weigering | Hersteld: opdracht, begrotingsregel, inzet, kostenpost, factuur, dekking, tarievenkaart en tarief tellen hun wijzigingen; een opslag op een oudere versie wordt geweigerd met wie en wanneer; het formulier toont wat er nu staat naast de eigen invoer en laat kiezen (begrotingsregel, inzet, opdracht, kostenpost, factuur); bij tarieven en dekking alleen de zin; tests per soort, met twee tabbladen gelopen op een begrotingsregel |
| B611 | Verwarrend | reis 5, maand afsluiten; eigenaar | mei is af te sluiten terwijl april nog open is | een besluit: mag dat, en zo ja, zegt het scherm het | Open; vraag aan de opdrachtgever van grip. Zichtbaar gemaakt: het formulier noemt de eerdere maand die nog open is, zonder te blokkeren; in de browser gezien |

### Ronde zes: controle van eerdere bevindingen

| Nr | Uitkomst op 9 oktober 2026 (5bd1c57) |
|---|---|
| G002 | bevestigd: een verouderde offerte biedt "Details" en "Maak nieuwe offerte", geen "Bied aan" |
| G005, G013 | bevestigd: een nieuwe kaart stelt de dag na de laatste kaart voor, welke stand die ook heeft |
| G006 | bevestigd: geen lege kop "Contactpersoon"; maken wordt geweigerd met wat de afzender nog mist |
| G009 | deels: de geschiedenis van het verzoek heeft wie, wanneer en waarom (API); de zin op de kaart niet op beeld gezien |
| G010 | bevestigd: na terugsturen zegt de kop niet meer "Vraag die aan" (zie B601 voor de zin die er nu staat) |
| G011 | bevestigd, zie nagerekend |
| T202 | bevestigd: wie meekijkt op een opdracht leest "... is aan zet"; voor een vacature gold dat nog niet (A604, hersteld in deze ronde) |
| H002 | bevestigd: een passage herschrijven geeft in ruim drie seconden een tekst terug |
| H004 | de weigering van de server opnieuw bevestigd (maker en planner 403); de knop niet opnieuw op beeld |
| H006 | bevestigd: vanuit een maandcel staat de waarschuwing er voor het bewaren, met "Bewaar boven 100%" |
| H007 | bevestigd, maar verstopt (B606) |
| H008 | bevestigd: de kaart houdt "Intern goedgekeurd op ... door ..." na het aanbieden |
| H009 | bevestigd op beeld: het bord opent op 390 breed met de lopende maand naast de namen |
| H010 | niet te beoordelen in deze kopie: de voorbeeldpersonen met alleen een recht hebben hier ook een schaal |
| H011 | bevestigd: geen geweigerd verzoek aan het corpus voor een lezer |
| H012 | bevestigd: de controle met een naam met een spatie vindt de persoon |
| F003 | bevestigd: een nieuwe opdracht toont geen nullen en zegt "Maak de begroting" |
| F011 | bevestigd: bewaren sluit het onderdeel, meldt het en opent het volgende lege |
| F029 | bevestigd: het factuurverzoek van een kwartaal met drie rollen is één pagina |
| R402 | bevestigd: "Vul de rol in" met knop bij een interne opdracht |
| R403 | bevestigd: "Heropen <maand>" in het menu van de periode voor de beheerder; de eigenaar wordt geweigerd; een reden is verplicht |
| R404 | bevestigd: de lijst zegt "Jij: maak de aanvraag compleet" |
| R410 | bevestigd: "De volgende offerte heet ..." |
| R411 | deels: bij lege onderdelen is "Maak offerte" gedimd; het accent op "Schrijf" niet op beeld beoordeeld |
| R501 | bevestigd: de beheerder leest "Leg het advies vast ..." met knop |
| R502 | nog open: de tekenbevoegde leest nieuws over vacatures |
| R503, R504 | bevestigd: 422 met de zin, de bewijsstap wordt bij het aanmaken geweigerd |
| A604 | hersteld in deze ronde: op een vacature is wie haar mag wijzigen niet vanzelf wie haar loopt. De aanvrager en wie een tekst schreef wachten; een beheerder zonder deel en een beoordelaar lezen "... is aan zet"; de beoordelaar is alleen aan zet voor haar eigen oordeel. `tasks/access.py`, `tasks/service.py`, `tasks/course.py`, test met de drie standen voor de vacature en de tekst; opnieuw gelopen als beheerder, lezer en planner |
| G008, H001, G012, G014, G015, H003, F041 | niet nagelopen |

## Ronde zeven, deel B: open bevindingen nagelopen

Op 9 oktober 2026, op een eigen kopie met een echte browser en de API, na de herstellingen van deze ronde.

| Nr | Stand |
|---|---|
| R502 | Hersteld: de regel klopte, de voorbeeldgegevens niet. In de seed geeft een directeur van de eigen organisatie akkoord op vacatures; `just fix-internal-judges` brengt een eerder gevulde voorbeelddatabase in lijn. Daarna leest de tekenbevoegde "Niets nieuws" (op beeld gezien) |
| A602, A603, A606, B605, B607, B609 | Zie de eigen rij |
| B606 | Open; gebied van het andere deel |
| F008 | Deels: Wies neemt een bestaande rol over en een rol kent haar andere namen; de losse rol "po" staat nog in de lijst van de voorbeeldgegevens |
| F022 | Niet nagelopen: zoeken in het corpus is gebouwd, het corpus was in deze opstelling niet aangeroepen |
| F038 | Vervallen: de offertekaart tekent geen stappenbalk meer |
| F041 | Niet nagelopen |
| G009 | Niet op beeld gezien; rust op de test |
| H003 | Niet nagelopen |
| H010 | Bevestigd: wie alleen een recht namens een opdrachtgever heeft, heeft in de seed geen inzetschaal meer en staat niet in de lijst om in te plannen (API) |
| G008, H001 | Niet nagelopen: de klok heeft geen instelling om de tijd vast te zetten buiten de tests, en die is niet toegevoegd |
| T201 | Bevestigd: "Recht lezer van <naam> ingetrokken", "Recht lezer aan <naam> toegekend" (API) |
| T203 | Bevestigd op beeld: een nieuwe persoon toont alleen "Stel target in" |
| T204 | Deels: "Organisatie toevoegen" staat in de actiebalk; het formulier is niet geopend |
| T206 | Bevestigd op beeld voor de beheerder; niet bekeken als lezer zonder Beheer |
| T207 | Bevestigd op beeld: "Context (optioneel)" zonder uitleg |
| Verouderde opslag | Een vacature en een rol in de catalogus tellen hun wijzigingen; een opslag op een oudere stand wordt geweigerd met wie en wanneer. Persoon, taak, organisatie en koppeling nog niet |

## Ronde acht: wat nog niet was nagelopen

Op 9 oktober 2026, op een eigen kopie van de voorbeelddatabase met een echte browser, na de herstellingen van deze ronde. De telling bovenaan is opnieuw gemaakt door de nummers te tellen.

| Nr | Stand |
|---|---|
| G012, G014, G015 | Bevestigd op 9 okt: staan in hun eigen rij als in de browser gelopen |
| F041 | Bevestigd op 9 okt, in de browser: "Nieuwe vacature" noemt de rollen waarvoor al een vacature loopt |
| F008 | Bevestigd op 9 okt, in de browser: "PO" in het rolveld van een begrotingsregel biedt Product owner aan. De losse rol "po" in een bestaande database wordt Product owner met `just fix-role-po` |
| F039 | Bevestigd op 9 okt, in de browser: de balk zegt alleen percentage en opdracht, het signaal is een teken. Hersteld: de legenda op de persoonspagina noemt het teken nu ook |
| T204 | Bevestigd op 9 okt, in de browser: "Organisatie toevoegen" opent een paneel |
| T206 | Bevestigd op 9 okt, in de browser: wie geen beheerder is leest "Terug naar Start" |
| H003 | Niet op beeld: de acht tests in `tests/vacancies/test_open_stretch.py` zijn groen |
| F022 | Niet nagelopen: het corpus is in deze opstelling niet bereikbaar |
| A609, B609, B610 | Bevestigd op 9 okt, in de browser: de zin over wie de dekking vastlegt, de vraag bij je eigen recht intrekken, en het paneel bij een begrotingsregel die een ander intussen wijzigde |
| A608, B611 | Wat is voorbereid is gezien: de keuzelijst voor dekking per opdracht met vaste bedragen eerst en de personeelsregel bij naam; de regel over de eerdere open maand bij afsluiten. Het besluit staat open |
| B606 | Deels hersteld: de waarschuwing boven 100 procent gaat alleen nog over de inzet. "Verwijder de inzet" staat nog achter het menu |
| A605, A613 | Open, niet gewijzigd |
| Smal en licht | Elke pagina op 390 breed en in het lichte thema, als eigenaar en als beheerder (156 metingen per reeks). Hersteld op 390: de weergaven van Aanvragen zijn een keuzelijst in plaats van afgekapte knoppen; in het Functiegebouw staat het aantal onder de naam; de tabel van de procedure en de tabellen in de rapportage passen. `check-spacing` kiest per persoon een opdracht die zij ziet en kent `--scheme light` |
