# De voorbeeldketen zichtbaar op ZAD

Ontwerp voor ronde 1 van stap 3. Datum: 28 november 2026. Status: voor de eigenaar van grip, na een controle door een bouwer.

## 1. Waarom

Op https://grip-voorbeeld.rijks.app/ staan twee voorbeeldinstanties: DigiGilde voorbeeld en MOZa voorbeeld. De eigenaar wil de hele keten zien, met de ministeries en ODI: "ik wil dus vooral ook EZK / NLDD en BZK / GDI erbij hebben in de demo opstelling", en "goed om eerst die instantie op de ZAD omgeving neer te zetten. dan wordt het ook al zichtbaar".

De keten zoals die echt loopt (de eigenaar, 28 november):

1. GDI keurt het voorstel en het programma MOZa goed.
2. BZK is gedelegeerd opdrachtgever namens GDI, en opdrachtgever van MOZa.
3. BZK verstrekt de opdracht aan opdrachtnemer ODI.
4. ODI laat haar uitvoeren door DigiGilde, een merk van ODI. De programmamanager van MOZa werkt vanuit DigiGilde.

Daarnaast: NLDD is een dienst van EZK, en EZK is de moederinstantie van NLDD (beslissing van 27 november).

MOZa is een programma met een eigen instantie, en blijft dat. BZK is een ministerie dat veel meer doet dan MOZa, en krijgt een eigen instantie (de eigenaar, 28 november).

## 2. Doelen, niet-doelen, anti-doelen

**Doelen**

1. Zeven voorbeeldinstanties draaien op ZAD in de groep `grip-voorbeeld`, elk met FSC, een eigen dataset en personas, en een knop op het portaal.
2. De keten staat in de gegevens: wie opdrachtgever is van wie, wie moeder is van wie, welke opdracht waar loopt.
3. De koppelingen staan in elk peerregister, met de rol die bij de relatie hoort (opdrachtgever of opdrachtnemer, moeder, dochter).
4. Na de nachtelijke terugzetting is alles er weer.

**Niet-doelen** (dat zijn de projecten na deze ronde)

- NLDD als opdrachtgever met bemensing (project 1), volgen (project 2), meelezen door een moeder en ODI als administratie (project 3), mandaten met RegelRecht.
- Een scherm voor een moederinstantie. Een moeder heeft in deze ronde een dataset en personas, maar nog geen scherm dat doorgifte toont.

**Anti-doelen**

- Een instantie die de gegevens van een andere laadt (zoals BZK nu zou doen met de dataset van DigiGilde).
- Een uitrol die de lopende voorbeelden breekt: inloggen bij `gilde`, de kostenpost Zaalhuur en de koppelingen moeten blijven werken.
- Echte namen van personen. Organisaties heten "voorbeeld"; mensen zijn verzonnen.

## 3. De zeven instanties

| Instantie | Uitrol op ZAD | Peer | Moeder | Rol in de keten |
|---|---|---|---|---|
| GDI voorbeeld | `gdi` (nieuw) | g | | keurt het programma MOZa goed, delegeert het opdrachtgeverschap aan BZK |
| Ministerie van BZK voorbeeld | `bzk` (nieuw) | b | | ministerie; opdrachtgever van MOZa, namens GDI; verstrekt de opdracht aan ODI |
| MOZa voorbeeld | `programma` (bestaat) | d | BZK | het programma; geeft opdrachten aan DigiGilde en boekt kosten |
| ODI voorbeeld | `odi` (nieuw) | o | | opdrachtnemer en contractpartij van MOZa |
| DigiGilde voorbeeld | `gilde` (bestaat) | a | ODI | voert MOZa uit; de programmamanager werkt hier |
| Ministerie van EZK voorbeeld | `ezk` (nieuw) | z | | moeder van NLDD |
| NLDD voorbeeld | `nldd` (nieuw) | e | EZK | dienst van EZK, opdrachtgever van eigen projecten bij DigiGilde |

**Keuze van de ontwerper:** BZK krijgt peer b, die daar al voor bedoeld was; de sjablonen `b-*.env` krijgen een eigen dataset voor BZK in plaats van die van DigiGilde. MOZa voorbeeld blijft wat het is, in de uitrol `programma` met peer d. BZK is de moeder van MOZa: daar liggen het budget en de verantwoording (de Centrale Financiering GDI staat op de begroting van BZK). GDI leest mee op MOZa, waarschijnlijk via BZK, voor inzicht in uitgaven en voortgang (de eigenaar, 28 november); dat meelezen hoort bij het project waarin moeders meelezen, niet bij deze ronde. De TOOI van MOZa voorbeeld is nu die van het ministerie (`mnre9001`); die gaat naar BZK, en MOZa krijgt een eigen TOOI als onderdeel.

**Keuze van de ontwerper:** GDI krijgt een eigen instantie. Grip volgt de organisatie, en een instantie mag kleiner zijn dan een geregistreerde organisatie (ADR 0016). GDI heeft een eigen besluit (het programma goedkeuren) en een eigen relatie met BZK.

## 4. Datasets

Elke instantie krijgt een eigen dataset in `backend/grip/dev/datasets/`, gekozen met `SEED_DATASET`, zoals `programma` nu. Een dataset is klein: de instantie zelf, haar personas met rechten, de organisaties waarmee ze te maken heeft (met TOOI en het adres van hun instantie, uit `EXAMPLE_INSTANCE_URIS`), en de opdrachten waarin ze partij is.

- **GDI voorbeeld:** de programmaraad of het bestuur dat goedkeurt; het programma MOZa als goedgekeurd voorstel. Hoe dat in grip staat zonder een nieuw begrip, is aan de bouwer; een opdracht van GDI aan BZK met de status "In uitvoering" volstaat als niets beters bestaat.
- **Ministerie van BZK voorbeeld:** een nieuwe dataset: een directie met de opdrachtgever van MOZa (namens GDI) en de opdracht aan ODI. Personas met een code `BZK-`.
- **MOZa voorbeeld:** de dataset `programma` blijft, met de opdracht MOZa voorbeeld 2026 bij DigiGilde, de kostenposten en de Zaalhuur. BZK staat erin als moederorganisatie en opdrachtgever. **Keuze van de ontwerper:** de opdrachtnemer blijft in deze ronde DigiGilde; ODI ertussen hoort bij project 3.
- **ODI voorbeeld:** de directie (ODI-AD, ODI-DIG, ODI-BV, ODI-BC), DigiGilde als dochter. Geen eigen opdrachten in deze ronde.
- **Ministerie van EZK voorbeeld:** een kleine directie, NLDD als dochter. Personas naar het voorbeeld van het personaboek; nieuwe personas krijgen een code `EZK-`.
- **NLDD voorbeeld:** de dataset uit het ontwerp voor NLDD voorbeeld (branch `ontwerp-nldd-voorbeeld`, hoofdstuk 7), zonder de bemensing, want die hoort bij project 1. De twee eigen opdrachten Fundament en RegelRecht staan als ontvangen offertes van DigiGilde.
- **DigiGilde voorbeeld:** blijft, met ODI als moederorganisatie en de opdrachten van NLDD erbij, zoals het ontwerp voor NLDD beschrijft.

**Keuzes van de ontwerper na de controle door een bouwer:**

- **De opdracht MOZa voorbeeld 2026** (het programmabudget) loopt nu van een rij "Ministerie van BZK voorbeeld" zonder instantie naar de eenheid MOZa. Ze wordt een opdracht tussen twee echte instanties: BZK is opdrachtgever, MOZa opdrachtnemer. Beide datasets beschrijven haar uit één gedeelde module met vaste uuid's en URI's, met een test die beide kanten gelijk houdt, zoals het ontwerp voor NLDD dat voor NLDD en DigiGilde doet. Het goedkeuren door GDI staat op dezelfde manier als opdracht van GDI aan BZK.
- **De sleutel `ministerie`** in `EXAMPLE_INSTANCE_URIS` wijst naar de instantie `bzk`; `INSTANCE_KEY` en de eenheid van MOZa blijven.
- **NLDD "zonder de bemensing"** betekent smal: alleen `getStaffing`, het contract 1.3.0, `staffing_with_names` en het onderdeel Bemensing vallen weg. De vijf nieuwe mensen bij DigiGilde met hun inzet, de inhuur, en de twee herstellingen aan de schermen (de links naar Aanvragen, en geen "Niet verstuurd" waar geen aanvraag was) gaan mee, omdat NLDD anders schermen toont die iets onwaars zeggen. Financiële inzage voor NLDD bij `gilde` gaat aan.
- **Lokaal krijgt dezelfde opstelling** als ZAD, in `deploy/local`: anders draait lokaal BZK nog met de gegevens van DigiGilde, en dat is precies het anti-doel. Lokaal komt eerst, omdat een ronde daar sneller is.
- **De personas MIN-\*** gaan als voorbeeldpersonen met rechten in de dataset van BZK. GDI krijgt eigen personas (`GDI-`), naar het voorbeeld van de Programmeringsraad GDI.

## 5. Op ZAD

Wat de uitrol van de groep op 27 en 28 november vastlegde (`docs/uitrol-zad.md`, ADR 0054), geldt per nieuwe peer:

- PKI: `pki.sh` krijgt de nieuwe peers (b, g, o, z, e) erbij zonder `--fresh`, zodat a, d en de directory hun sleutels houden. Kan het script dat nog niet, dan breidt de bouwer het uit.
- Sjablonen per peer (negen per instantie), de bootstrap met de nieuwe `PEERS`, de rol van de koppeling (moeder, dochter of opdrachtgever/opdrachtnemer): de bootstrap zet nu altijd `counterpart` en moet de rol kunnen meegeven.
- Per uitrol een eigen database met 50 verbindingen, een eigen `SESSION_SECRET_KEY` en `FEDERATION_SIGNING_KEY`, het adres van de frontend in Keycloak.
- De variabelen `ZAD_DEPLOYMENTS` en `ZAD_FSC_DEPLOYMENTS` krijgen de nieuwe uitrollen.
- Het portaal krijgt zeven kaarten in de volgorde van de keten.
- Elke nieuwe uitrol gaat in een eigen venster zonder uitrol, zoals in het draaiboek, en daarna wordt gecontroleerd dat de draaiende uitrollen gezond blijven.

**Keuze van de ontwerper:** de koppelingen tussen instanties zet de bootstrap meteen in elk peerregister, in plaats van met de hand zoals bij stap 9. Bij zeven instanties zijn dat er veel, en de volgorde doet sinds ADR 0061 niet meer ter zake. De bootstrap schrijft ze via een route van grip voor de beheerder, of de bouwer kiest een andere weg die de rechten van grip niet omzeilt.

## 6. Welke koppelingen er zijn

| Van | Naar | Rol |
|---|---|---|
| MOZa | DigiGilde | opdrachtgever en opdrachtnemer (de Zaalhuur) |
| BZK | MOZa | moeder en dochter |
| BZK | GDI | opdrachtgever en opdrachtnemer (delegatie) |
| BZK | ODI | opdrachtgever en opdrachtnemer |
| ODI | DigiGilde | moeder en dochter |
| EZK | NLDD | moeder en dochter |
| NLDD | DigiGilde | opdrachtgever en opdrachtnemer |

Elke relatie staat aan beide kanten. Een verbindingscontract in FSC is er per richting, zoals nu.

## 7. Acceptatie

1. Op het portaal staan zeven kaarten met werkende links; de directory toont zeven peers met hun diensten.
2. Inloggen werkt bij elke instantie, en elke instantie toont haar eigen naam en voorbeeldpersonen.
3. Bij elke koppeling geeft "Test de verbinding" in orde.
4. De kostenpost Zaalhuur loopt nog van MOZa naar DigiGilde; inloggen bij `gilde` werkt.
5. Na de nachtelijke terugzetting is alles er weer.
6. De tests van elke dataset slagen, en geen dataset laadt de gegevens van een ander.

## 8. Opbouw

1. Een PR met de datasets, de personas, de nieuwe peers in de scripts en sjablonen, de bootstrap met rollen, en het draaiboek. De eigenaar ziet hem voor de merge.
2. Op ZAD per instantie een venster: eerst ODI, dan BZK, dan GDI, dan EZK, dan NLDD; `programma` en `gilde` krijgen hun moeder in het peerregister.
3. Het portaal en de variabelen.

## 9. Wat aan de bouwer is

- De namen van de nieuwe personas en hun aantal, naar het patroon van het personaboek.
- De TOOI van de nieuwe organisaties (verzonnen, zoals `oorg99002`).
- Hoe GDI het goedgekeurde programma toont, binnen wat grip al kent.
- Hoe de bootstrap de koppelingen in het peerregister zet, zolang de rechten van grip gelden.

## 10. Waarom MOZa een eigen instantie houdt

Inhoudelijk valt een programma onder GDI, financieel onder BZK, en het hoeft geen eigen organisatie te zijn. Toch houdt MOZa hier een eigen instantie: daar kan het werk van het programma zelf een plek krijgen, zoals planning, mijlpalen, risico's en besluiten. Dat is een weergave die de bedrijfsvoering niet heeft, maar die haar wel raakt (de eigenaar, 28 november). Volgens ADR 0053 is de instantie van het programma eigenaar van wat daar ontstaat, en verwijst ze naar wat elders ligt, zoals de opdracht bij BZK en de kosten bij ODI. Dat past bij het beeld van de eigenaar van eigen apps per organisatie of project, die informatie op verschillende plekken ophalen. Het uitwerken daarvan hoort niet bij deze ronde.
