# 0044 Een verloop per zaak, uit dezelfde feiten als de taken

Status: aanvaard (2026-10-09)

Vult aan: [0024 Taken, feiten en het plan](0024-taken-feiten-en-het-plan.md), [0038 Een taak vertelt wat de lezer moet doen](0038-een-taak-vertelt-wat-de-lezer-moet-doen.md)

## Context

Elk proces in grip vertelde zijn stand op een eigen manier. De potentiële opdracht rekende haar stappen uit in de browser, uit de velden van de opdracht en haar offertes. De vacature deed hetzelfde met een eigen functie. De taken kwamen uit het plan op de server, uit feiten. Drie berekeningen van dezelfde stand konden elkaar tegenspreken, en deden dat: een stappenbalk op stap 1 naast een label "Aangeboden", een taak "Bied aan" voor een offerte die nog goedgekeurd moest worden.

De gebruiker vroeg om werkstromen die overal hetzelfde lezen, met taken, soepel waar het werk buigt en toch eenvoudig, met een heldere visuele hiërarchie.

## Besluit

1. **De server beslist waar een zaak staat en wie aan zet is.** Het verloop van een zaak is een leesmodel (`GET /api/tasks/cases/{soort}/{id}/course`, en `GET /api/tasks/courses` voor een lijst): de stappen met hun stand, de volgende stap met wie, wat ontbreekt, de termijn, en hoe de zaak eindigde. De browser tekent het alleen.
2. **Het verloop staat in het plan**, naast de taaksjablonen: stappen, namen, de feiten die een stap afronden, de taken die erbij horen. Dezelfde feiten openen en sluiten de taken, dus de balk, de zin en de takenlijst kunnen het niet oneens zijn.
3. **Een stap telt zodra zijn feiten kloppen**, waar hij ook staat. De eerste stap die nog niet telt is de huidige. Zo dwingt het verloop geen volgorde af die het domein niet eist.
4. **De volgende stap is een taak.** De zin, de knop en de naam komen uit de toelichting bij de taak. Een taak onthoudt de situatie waarin zij verkeert (de offerte is verlopen, de begroting is gewijzigd), zodat de lijst en de pagina dezelfde woorden gebruiken.
5. **Een gedeeld onderdeel tekent het**: de zin onder de titel, de ene knop naast de titel, het verloop klein eronder. De kop van een opdracht en van een vacature gebruiken het; hun lijsten tonen dezelfde stand in een kolom.
6. **Een accent per pagina.** De kop meldt dat zij de volgende stap draagt; de gedeelde knop en actiebalk tekenen een hoofdknop eronder dan als gewone knop.

Het patroon, de praktijkgevallen en de tabel van stappen en taken staan in `docs/werkstromen.md`.

## Gevolgen

- Migratie `0035_task_situation`: een taak krijgt een kolom voor haar situatie.
- Het plan (2026.3) heeft `courses` en `ends`. Een zaak op een ouder plan zonder verloop gebruikt het verloop van het huidige plan.
- Nieuwe feiten in de catalogus, waaronder of interne goedkeuring nodig is en gevraagd is, en of een offerte nog geldt en bij de begroting past. Het laatste rekent de begroting door bij elke taakberekening van een potentiële opdracht met een offerte; dat kost tijd en is alleen dan nodig.
- De functies die de stand in de browser uitrekenden (`standing`, `vacancySteps`) sturen de schermen niet meer. Ze bestaan nog voor de kaart van een offerte en als terugval in de vacaturelijst.
- Een later instelscherm voor werkstromen heeft nodig: een opslag voor plannen per instantie in plaats van een bestand, een controle vooraf die zegt welke lopende zaken van stap veranderen, en een grens aan wat instelbaar is (namen, termijnen, wie handelt, welke stappen gelden), omdat de feiten zelf code blijven.

## Later gewijzigd (2026-10-09)

Een afgewezen offerte is voor de opdrachtnemer een stap terug en geen einde (ADR 0045). Een stap overnemen geeft geen recht, en een stap waar een ander moet beslissen is niet over te nemen (ADR 0048). Een naverrekening is een stap van haar factuurperiode zolang ze openstaat (ADR 0047).
