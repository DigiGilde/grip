# 0059 Taken en de stappen terug, Nieuw als tijdlijn, één tekstkleur

Status: aanvaard (2026-11-28)

Stelt bij: [0055 Vijf plekken en een rustig geopend ding](0055-vijf-plekken-en-een-rustig-geopend-ding.md), [0044 Een verloop per zaak, uit dezelfde feiten als de taken](0044-een-verloop-per-zaak-uit-dezelfde-feiten-als-de-taken.md)

## Context

De opdrachtgever keek op 28 november 2026 voor het eerst door de bouw van ADR 0055, als beheerder, op een breed scherm en op een telefoon. Vier dingen vielen op.

- Taken stond niet meer in de balk. Wie bij Opdrachten was, kwam alleen via Start bij al zijn taken. ADR 0055 rekende dat al tot de zeven taken die slechter werden.
- Een opdracht zei niet meer zichtbaar waar ze in haar verloop staat. Het verloop was één regel tekst in de regel onder de titel, en die las niemand als "waar staan we".
- Nieuw op Start was een rijtje van drie. Wat er gebeurde laat zich beter lezen als een tijdlijn, zoals de Activity van Basecamp: per dag, terug in de tijd, te filteren op project en op persoon.
- Tekst stond in twee kleuren. Een hele zin in grijs, zoals de regel boven de tabel van Begroting, maakte een pagina onrustiger in plaats van rustiger.

## Besluit

**Taken staat weer in de balk**, direct na Start, voor iedereen. Het aantal taken dat op de lezer wacht staat bij Taken. Start houdt Te doen, met "Alle taken".

**Een opdracht toont haar verloop weer als stappen**: de stappenbalk van het designsysteem, onder de zin wie aan zet is. Dat geldt op de landing, in een moment onder Geschiedenis en op de pagina voor de opdrachtgever. Op een smal scherm staan de stap waar ze is en de volgende in woorden. De regel onder de titel herhaalt het niet. Een vacature houdt haar stappen als rijen.

**Nieuw is een tijdlijn.** Op Start staan de laatste vijf berichten, per dag, op het spoor van het designsysteem, met daaronder "Alles wat er gebeurd is". Die pagina toont dezelfde tijdlijn, terug in de tijd, met een filter op opdracht en een op persoon. Wat een filter aanbiedt, komt uit wat de lezer al ziet.

**Eén tekstkleur.** Alle tekst die grip zelf schrijft staat in de gewone kleur; wat minder belangrijk is, is kleiner. Grijs blijft alleen waar het designsysteem het zelf tekent, zoals de tweede regel van een rij. Een kleur met een betekenis, zoals rood bij een overschrijding of een verlopen termijn, blijft.

## Gevolgen

- Een teamlid ziet vier plekken, een aanvrager of tekenbevoegde vier, een planner vijf, een lezer vijf, een eigenaar zes en de beheerder zes plus Beheer. Op een telefoon van 390 pixels staan bij de beheerder Geld, Beheer en Ik achter "Meer tabs".
- Van de zeven taken die in ADR 0055 slechter werden, zijn "Alle taken" en "Nieuwe taak" weer één klik vanaf elke plek. De balk boven een taak leidt terug naar Taken, zoals op main.
- De stappen komen van de server, zoals de zin over wat er nu moet; het scherm tekent ze met `CourseBar` uit `@/ui/Workflow`. Er is geen tweede bron voor de stand.
- `GET /api/updates` filtert met `opdracht` en `persoon`, en `GET /api/updates/filters` geeft de keuzes. Een filter knipt in de berichten die de lezer zonder filter krijgt, over hetzelfde venster, en een id dat de lezer niet mag zien antwoordt als een id dat niet bestaat. Wie een besluit van een ander alleen vastlegde, krijgt het niet op zijn naam. Alle velden zijn klasse A, met lektests. Zie `docs/toegang.md`.
- Het filter op persoon toont alles wat één collega deed, aan ieder die die berichten mag zien. Zo'n voorziening is geschikt voor controle op gedrag of prestaties: voordat grip voor echt werk wordt gebruikt, is instemming van de ondernemingsraad nodig (artikel 27 lid 1 onder l van de Wet op de ondernemingsraden), en onder de AVG moet het noodzakelijk en in verhouding zijn. In deze fase, waarin we ontdekken wat grip moet doen, staat het erin. Zonder instemming gaat het filter op persoon eruit; dat op opdracht heeft dit bezwaar niet. Zie `docs/openstaand.md`, "De ondernemingsraad".
- De zinnen van het nieuws noemen bij een getekende offerte en bij een besluit over een vacature nog wie het vastlegde als wie het deed ("is getekend door ..."). Het filter neemt dat niet over; de zinnen zelf zijn niet veranderd.
- `Quiet` is klein in de gewone kleur. De `lead` van een pagina staat altijd als gewone tekst onder de regel van de titel, met en zonder knop. Onze stylesheets gebruiken voor tekst de gewone kleur, en `ui/layout/text.guard.test.ts` faalt op grijze tekst. Wat alleen grijs was om een stand te tonen, zegt het nu in woorden: een bedrag van nul, "Nog niet ingevuld", een afgesloten maand, verwachte kosten.
