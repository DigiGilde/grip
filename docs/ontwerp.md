# Ontwerp van de schermen

Dit document beschrijft hoe een scherm in grip wordt opgebouwd. Het doel is dat een nieuw scherm er vanaf de eerste versie uitziet als de rest, zonder dat iemand een maat of een kleur kiest.

De vormgeving komt uit het NLDD Designsysteem. Dit document voegt daar geen eigen stijl aan toe. Het legt vast welke onderdelen grip gebruikt en in welke volgorde.

## Wanneer een scherm af is

Een scherm is af als het aan deze eisen voldoet. Meet ze in een browser; een test zonder browser ziet ze niet.

**Strak**

- Koppen, tekst, velden en de inhoud van tabellen beginnen op dezelfde horizontale positie.
- Getallen staan rechts uitgelijnd, in cijfers van gelijke breedte.
- Er is één schaal voor afstanden. Twee afstanden naast elkaar verschillen alleen als dat iets betekent.
- Bedieningselementen in één rij hebben dezelfde hoogte.
- Wat gelijk is, ziet er gelijk uit: kaarten in een rij zijn even hoog, knoppen van dezelfde rang even groot.
- Een rij in een tabel is één regel hoog met hooguit één gedempte regel eronder. Er staan geen tekstknoppen in een rij.

**Mooi**

- Eén accent in de inhoud: de hoofdknop is het enige gevulde vlak. De rest is neutraal. De hoofdbalk is navigatie en volgt het designsysteem.
- Ruimte laat zien wat bij elkaar hoort: veel ruimte om een groep, weinig erbinnen. Een rand of een vlak is daar niet voor nodig.
- De typografie heeft weinig stappen, en elke stap heeft één taak.
- Ondersteunende tekst is gedempt.
- Een status staat in een label uit een kleine, vaste set.

**Rustig**

- Geen zin die de interface uitlegt.
- Geen melding over wat iets niet is.
- Geen formulier dat standaard openstaat.
- Geen foutmelding voordat iemand iets heeft ingevuld.
- Hetzelfde feit staat één keer op het scherm.

**Dichtheid die bij de taak past**

- Lijsten en formulieren ruim.
- Tabellen met gegevens compact, en uitgelijnd.

## Soorten scherm

Elke pagina zegt wat ze is, met `kind` op `Page`. Dat bepaalt hoe breed de inhoud leest: een lijst en een stuk staan in een leeskolom van 720 pixels aan de linkerrand, een werkblad gebruikt de volle breedte. Titel, terugverwijzing en inhoud beginnen zo op elk scherm op dezelfde linkerrand.

| Soort | `kind` | Schermen |
|---|---|---|
| Lijst | `list` | Start, Taken, Opdrachten, Vacatures, Aanvragen, Geld, Beheer, Kosten, Factureren, Zoeken, Ik, Wat is er gebeurd, de landing van een opdracht en van een vacature, Geschiedenis, Alle taken van een zaak |
| Werkblad | `worksheet` | Begroting, Team, Afsluiten en factureren, het rapport van een opdracht, Lopende opdrachten, Omzet, Investeerruimte, Potentieel, Jaarverantwoording, de lijst Mensen, het bord, Bezetting, Declarabiliteit, het bord van Taken, Tarieven |
| Stuk | `document` | Offerte en tekenpagina, ontvangen offerte, aanvraag, persoon, kostenpost, factuurverzoek, vacaturetekst, Gegevens, Advies en akkoord, Tekst en openstellen, Vervullen |

Een lijst heeft rijen en één hoofdknop, zoals een dienst voor burgers. Een werkblad zet alle kolommen van een rekenregel in één rij, met een totaalrij. Een stuk is één ding dat je als geheel leest. De toets bij de hoofdvraag van een scherm: kun je het antwoord uit één rij lezen, zonder iets op te tellen of te vergelijken? Dan is het een lijst, anders een werkblad. Een nieuw scherm krijgt een plek in deze tabel.

## De bouwstenen

Ze staan in `frontend/src/ui/layout/` en `frontend/src/ui/`.

| Bouwsteen | Waarvoor |
|---|---|
| `Page` | Een pagina in de schil: de titel in de kop van de sectie, daaronder de inhoud op één ritme. Eén per route. `kind` is verplicht; zie "Soorten scherm". |
| `lead` op `Page` | Eén zin onder de titel over waar de pagina voor is; laat haar weg als de titel het zegt. Heeft de pagina een `action`, dan staat de zin onder de regel van de titel, zodat een lange zin de knop niet van zijn regel duwt. |
| `action` op `Page` | De ene hoofdknop van de pagina, rechts op de regel van de titel (smal: eronder). |
| `tabs` op `Page` | De onderdelen van een ding of de weergaven van een lijst, onder de titel, via `TabNav`. |
| `tabName` op `Page` | Wat het tabblad van de browser zegt als de titel niet zegt welk ding dit is: "Team, Opdracht Alfa 2026". De h1 blijft de titel. |
| `Section` | Een deel van een pagina met een eigen kop en hooguit één regel uitleg. |
| `Stack` | Onderdelen onder elkaar, met een afstand uit de schaal. |
| `Facts` | Feiten als "label: waarde", met de labels in één kolom. Voor lezen. |
| `CardGrid` | Kaarten in rijen van gelijke hoogte. |
| `FormSheet` | Een formulier in een zijpaneel. Het ene patroon voor toevoegen en wijzigen. |
| `FormFields` | De velden van een formulier op één afstand, ook op een pagina. |
| `FilterSelect` | Eén keuzelijst op de gewone maat. |
| `OpenRow`, `OpenCell`, `RowActions` (`@/ui/RowActions`) | Een rij die opent, en één stille knop met een menu voor de overige acties. |
| `ActionBar` (`@/ui/ActionBar`) | Filters links, acties rechts, alles op één maat. De hoofdknop staat hier of op de regel van de titel, niet op beide. |
| `search` op `ActionBar` | Zoeken in de lijst onder de balk: één zoekveld, vóór de filters. Op een smal scherm staat het op een eigen regel over de volle breedte, want een zoekveld past niet in het menu van de balk. De woorden staan in het adres (`?zoek=`). |
| `PageRange`, `Pager` (`@/ui/Pager`), `usePaging` (`@/ui/paging`) | Een lange lijst in pagina's van vijftig. Boven de rijen staat welke het zijn ("51 tot en met 100 van 300 opdrachten"), eronder de weg naar de andere pagina's. De pagina staat in het adres (`?pagina=2`). Een lijst van één pagina toont geen van beide. |
| `NameLine` | Een naam met zijn status: het label staat op de regel van de naam, in het midden ervan, met hooguit één gedempte regel eronder. |
| `back` op `Page` | De ene terugverwijzing boven de titel: `back={{ href, text }}`. |
| `KeyFigures` | Een paar cijfers die een pagina samenvatten: een gedempt label boven de waarde, zonder kader. Een tabel is voor rijen van één soort. |
| `SignalList` | Wat aandacht vraagt, als één lijst: een zin per punt, met eronder waar het over gaat. Geen stapel balken. |
| `LinkRows` (`@/ui/LinkRows`) | Rijen die elk ergens heen leiden: de onderdelen van een ding, de blokken van Start, de pagina's van Geld en Ik. Per rij een regel tekst, gedempt eronder wat er speelt (`notice`), een stand als badge (`tag`) en een korte waarde aan het eind (`end`). Een rij met een adres eindigt met het icoon `open`. |
| `TabNav` | De onderdelen van één geopend ding of de weergaven van een lijst, elk een pagina met een eigen adres: gewone tekst op één regel, een haarlijn onder de rij en een lijn onder waar je bent. `narrow="hide"` voor onderdelen (op een smal scherm wissel je via de landing), `narrow="bar"` voor weergaven, met korte tekst in `short`. Past de balk niet, dan staat de rest achter zijn knop Meer. Nooit een keuzelijst. |
| `omitEmpty` op `Facts` | Laat een feit zonder waarde weg, waar een lege waarde geen nieuws is. Op een smal scherm staat het label boven de waarde, zodat een waarde nooit midden in een woord breekt. |
| `hideBelow`, `hideAbove`, `narrowText` op `OpenCell` | Een kolom die op smal wegvalt, vouw je in de naam: `narrowText` is de gedempte regel die alleen smal verschijnt. |
| `TOP_ALIGNED` (`@/ui/layout`), `verticalAlignment` op `OpenCell` | Voor een rij waarvan de cellen in hoogte verschillen: elke cel begint bovenaan. |
| `href` op `OpenCell` | Het echte adres van de rij, zodat openen in een nieuw tabblad werkt. |
| `useNarrow` | Waar de smalle opbouw een andere structuur is en niet alleen een andere maat. |
| `more` op `ActionBar` | Wat zelden gebeurt of niet terug kan, in één menu aan het eind van de balk, met bevestiging. |
| `Loading`, `ErrorNotice`, `EmptyNotice` | Laden, een fout, en niets om te tonen, steeds in dezelfde vorm. |

### Afstanden

| Naam | Stap | Tussen |
|---|---|---|
| `tight` | 4 | Een label en zijn waarde |
| `close` | 8 | Regels van één soort |
| `related` | 16 | Een kop en wat eronder hoort |
| `group` | 24 | Blokken op een pagina: een filterrij, een tabel, een melding |
| `section` | 48 | Secties met een eigen kop |

Tussen de paginatitel en de inhoud zet het designsysteem zelf 32. Velden in een formulier staan op 20.

Schrijf geen marge of padding in pixels. Kies een bouwsteen, of een `nldd-container` met een `gap` uit de schaal.

### Typografie

| Rol | Onderdeel |
|---|---|
| Paginatitel, de enige h1 | `nldd-title` maat 2, via `Page` |
| Kop van een sectie, h2 | `nldd-title` maat 4, via `Section` |
| Kop binnen een sectie, h3 | `nldd-title` maat 5 |
| Tekst | De standaard |
| Ondersteunend | `nldd-text` met `color="secondary"` en `size="sm"` |

Een rij in een lijst of tabel is nooit een kop.

## Regels

**Begin bij wat iemand komt doen.** Schrijf in één regel op wat de gebruiker op dit scherm komt doen of leren. Het eerste scherm dient precies dat. Het antwoord staat boven de tabel.

**Eén hoofdactie.** Een scherm heeft één primaire knop. "Annuleer" en "Verwijder" staan er niet naast.

**Lezen en bewerken zijn twee schermen.** Een onderdeel laat zien wat er is, met hooguit één actie. De actie opent een `FormSheet`. Een formulier staat nooit standaard open.

**Controleer bij opslaan.** Een fout verschijnt na het versturen, met wat er mis is en hoe het op te lossen is.

**Toon niet wat er niet is.** Een onderdeel dat iemand niet mag zien of dat niet van toepassing is, staat er niet. Geen lege of vergrendelde vakken.

**Kolommen staan één keer vast.** Gebruik `nldd-table` met `columns`, zodat elke cel op dezelfde plek begint. Een rij die doorklikt eindigt met een pijl.

**Acties van een rij.** De rij zelf is de weg naar openen of wijzigen: een klik op de rij of Enter op de naam opent het detail of het `FormSheet`. Er staat geen knop "Bewerk" in een rij. Wat een rij verder kan, staat achter één stille knop aan het eind ("Meer acties voor ...") met een menu. Een actie die iets weghaalt is in het menu als zodanig gemarkeerd en vraagt om bevestiging, met wat er mee verdwijnt. De kolom met die knop heeft een vaste smalle breedte en geen kop, zodat de kolom ervoor in elke rij en in de totaalrij op dezelfde plek eindigt. Gebruik `OpenRow`, `OpenCell`, `RowActions` en `ROW_ACTIONS_COLUMN` uit `@/ui/RowActions`.

**Een actie ziet eruit als een knop.** Er zijn drie rangen, uit `@/ui/Button`, en geen vierde:

| Rang | Wanneer |
|---|---|
| Primair | De ene volgende stap van een pagina of een stand. Het enige gevulde vlak in de inhoud |
| Secundair | Elke andere actie: een echte knopvorm, neutraal. Dit is de standaard |
| Destructief | Wat niet terug kan, in de dialoog of het paneel dat er eerst om vraagt |

Een actie als kale tekst leest naast een knop met een rand als een label; die vorm is er daarom niet om te kiezen. `QuietButton` is de uitzondering met een vaste lijst van plekken: de weg uit een formulier ("Annuleer") en een kleine actie binnen een regel van een gesprek (antwoord op een opmerking). In een tabelrij staat geen knop: de rij opent en de rest zit in het menu.

Ergens heen gaan is een link, nooit een knop. Een actie is nooit als link vormgegeven. De ene uitzondering: de volgende stap op de landing van een opdracht of een vacature is de hoofdknop, ook als hij naar het onderdeel leidt waar de stap wordt gezet. Op dat onderdeel staat de stap in de kop als het adres iets opent, zoals het paneel van een maand; anders zet de eigen knop van het onderdeel hem.

Kan iets nu niet, dan staat de knop er niet, of hij staat uit met de reden ernaast. De volgende stap volgt uit de stand: een tekst met plekken die nog ingevuld moeten worden biedt "Schrijf verder" en niet "Vraag om een oordeel".

De test `ui/controls.guard.test.ts` faalt op de kale tekstknop buiten de basis en op `QuietButton` buiten zijn plekken.

**Tekst invoeren: het veld volgt uit wat de tekst is.** Alle invoer gebruikt de velden van het designsysteem, via één bouwsteen per soort:

| Soort tekst | Bouwsteen | Voorbeelden |
|---|---|---|
| Eén regel | `TextField` uit `@/ui/fields` | Een naam, een kenmerk, een adres |
| Platte tekst van meer regels, die plat blijft | `MultiLineField` uit `@/ui/fields` | Een reden, een toelichting, een notitie, een opmerking bij een tekst, een aanwijzing voor het taalmodel, de motivatie voor het aanvraagformulier |
| Tekst die met opmaak wordt bewaard en opgemaakt wordt getoond | `TextEditor` uit `@/ui/TextEditor` | Een vacaturetekst, een onderdeel van een offerte, een standaardtekst, de afsluiting van de brief |

De editor staat alleen waar de tekst opmaak kan bevatten en ergens opgemaakt wordt getoond. Een veld dat als platte tekst wordt getoond krijgt hem niet: de tekens voor opmaak zouden als sterretjes op het scherm of in een pdf komen, en een werkbalk bij een veld "Reden" is ruis. De motivatie voor het aanvraagformulier is daarom plat: ze komt in een formulierveld dat alleen platte tekst kan bevatten.

De editor is die van het designsysteem (`nldd-text-editor`): de tekst blijft platte tekst met een paar tekens, de opmaak is tijdens het schrijven te zien en een teken verschijnt alleen waar de cursor het raakt. De werkbalk biedt precies wat de tekst kan bevatten (`@/ui/text/marks`): een vacaturetekst kent een kop, een lijst en cursief; een onderdeel van een offerte ook een genummerde lijst en vet. Wat iemand typt of plakt wordt naar die set teruggebracht. Een plek die nog ingevuld moet worden, "[vul aan: ...]", is in de editor gemarkeerd en geteld, met een stap naar de volgende.

Een bewaarde tekst wordt overal getoond met `RichText` uit `@/ui/RichText`, uit dezelfde vorm: wat je bewerkt is wat je ziet. De test `ui/controls.guard.test.ts` faalt op een kaal `textarea`, `input` of `contenteditable` in een scherm.

**Een status is een badge.** Een stand die het systeem bijhoudt ("Te laat", "Klaar", "Nu aan de beurt", "Overschrijding") is een `nldd-badge`, met de kleur uit de bestaande toewijzing; in een rij zet `LinkRows` hem met `tag`. Een eigenschap die iemand toekent (een soort, een rol) is een `nldd-tag`. Zo onderscheidt het designsysteem ze. De kleur draagt nooit als enige de betekenis. Zegt de zin van een rij het al, dan staat er geen label: de rijen van Geld zeggen tekort en ongedekt in hun zin.

**Schrijf gewoon Nederlands.** Lees elke zin als iemand die het systeem niet heeft gebouwd. Zinnen beginnen met een hoofdletter en hebben verder kleine letters, zonder uitroepteken. Je schrijft "je". Een knop zegt wat er gebeurt.

**Een lange lijst komt in pagina's van de server.** Opdrachten en Kosten vragen één pagina van vijftig rijen; de server zoekt, sorteert en telt, en doet dat pas na de toegangsbeslissing, zodat een telling nooit iets verraadt. Geen lijst die vanzelf verder laadt: de lezer ziet waar hij is en hoeveel er is. De pagina en de zoekwoorden staan in het adres, dus een pagina is te delen en de terugknop werkt. Na een andere pagina gaat de focus naar de regel boven de rijen. De pagina waar je bent is in de paginering een rustig neutraal vlak en geen gevuld accent (`ui/pager.css`): het ene gevulde accent blijft de hoofdknop. De tellingen op tabs volgen de zoekwoorden.

### Vaste woorden

| Woord | Betekenis |
|---|---|
| Begroot, Gerealiseerde inzet, Nog gepland, Kosten, Verwacht totaal, Afwijking | De kolommen van een opdracht. Gerealiseerde inzet, nog gepland en kosten tellen op tot het verwacht totaal |
| Gerealiseerd | Gerealiseerde inzet plus gerealiseerde kosten: wat werkelijk is besteed. Bij kosten het deel dat op ontvangen facturen rust ("€ 3.000 gerealiseerd, € 1.500 ingeschat"); dat is hetzelfde begrip. Heet de inzet apart, dan is het "Gerealiseerde inzet" |
| Uitputting | Gerealiseerd als deel van de begroting, als percentage. Op een totaalrij staat het bedrag eronder ("€ 73.450 gerealiseerd") |
| Niets gepland, Nog geen inzet gepland | Een regel of opdracht zonder inzet: "Niets gepland" in een tabel, "Nog geen inzet gepland" op de landing. Nooit "100%, ruimte" |
| Aangeleverd | Factuurgegevens zijn doorgegeven aan de financiële administratie |
| Gefactureerd | Er is een factuur verstuurd en vastgelegd |
| Potentiële opdracht, Potentieel | Een opdracht tot het akkoord, ook na een afgewezen offerte. Potentieel is ook een weergave van Opdrachten en een pagina onder Geld. Nooit "pijplijn" |
| Open rol | Een rol zonder persoon, ook als er een vacature voor loopt. Een opengestelde vacature heet vacature |
| Offerte maken | De begroting vastleggen als offerte. Daarna wijzigt de offerte niet meer; ze krijgt een kenmerk |
| Aanbieden | Een gemaakte offerte naar de opdrachtgever brengen |
| Getekend, afgewezen | De beslissing van de opdrachtgever over een aangeboden offerte |
| Rechten in grip | Wat iemand in grip mag: beheerder, planner, lezer, aanvrager, tekenbevoegde, interne goedkeurder van offertes. Nooit "functie" |
| Stel vast | Een concept definitief maken: een tarievenkaart, een maand, een tekst. Nooit "activeer" |
| Naverrekening | Het verschil als de prijs van een aangeleverde maand verandert |
| Factuurverzoek | Het document van een aanlevering aan de financiële administratie |
| Echtheidskenmerk, bestandskenmerk | De code over de inhoud van een offerte, en die over haar pdf. Nooit "hash" of "vingerafdruk" |
| Bekijk pdf | De ene link naar het document van een offerte |
| Stand | Waar een zaak staat en wie aan zet is: "Jij: ..." of "Wacht op ..." |
| Moment | Eén vastgelegd feit van een opdracht, op het onderdeel Geschiedenis. De lijst heet Momenten; "verloop" blijft de stappen van een zaak |
| Stand op ... | Hoe opdracht, begroting en offerte er op een moment voorstonden. De kop van een stand noemt de dag en het uur van het moment |
| Besluit | Het merkteken op een moment waarop wie het vastlegde zelf besloot. Nooit "decretogram", "uitvoering" of "regel" |
| Later vastgelegd | Wat na een moment is vastgelegd maar al telde vanaf een dag die dat moment had gezien, onder de stand van dat moment |
| Later verwijderd, Tekst verwijderd | Een getypte tekst die een beheerder later uit een moment haalde, onder de stand van dat moment; "Tekst verwijderd" staat waar een naam of omschrijving niet leeg mag zijn |
| Te doen, Wacht op anderen | De twee groepen taken |
| Start, Taken, Opdrachten, Aanvragen, Vacatures, Mensen, Geld, Beheer | De plekken in de hoofdbalk; op een smal scherm ook Ik, het account |
| Team, Mensen | Team is wie op een opdracht werkt: een onderdeel van de opdracht. Mensen is de plek met iedereen die kan worden ingezet. Nooit "Bemensing" |
| Meldingen instellen, Mijn aanvragen | De regel in het account naar de meldingen, en de eigen aanvragen van een opdrachtgever |
| Geschiedenis, Activiteit, Wat is er gebeurd | Wat er met een zaak gebeurde, wat er in de instantie gebeurde, en het nieuws voor de lezer |
| Aanvraag voorbereiden, aanvragen, advies en akkoord, openstellen, vervullen | De stappen van een vacature |

## Navigatie

De schil staat in `frontend/src/layout`; welke plekken er zijn, voor wie en waar ze openen staat in `frontend/src/routes.ts`. Het waarom staat in ADR 0055 en ADR 0059.

**De plekken.** Start, Taken, Opdrachten, Aanvragen, Vacatures, Mensen en Geld, en apart aan het eind Beheer. De balk biedt alleen aan wat iets voor de lezer kan bevatten (`for` in de routetabel). Dat is een hulp voor de balk en geen toegangsregel: de server beslist per pagina en per veld, en een adres dat je intikt opent gewoon. Een plek staat voor iedereen op dezelfde plaats; op welke pagina ze opent mag de lezer volgen (`landing`): Mensen opent voor een planner op het bord. Een pagina die bij een plek hoort zonder onder haar adres te staan, staat bij `also`: de offertes ter goedkeuring horen bij Taken, Wat is er gebeurd bij Start.

**Een plek verdien je.** Een pagina krijgt een plek als iemand haar minstens wekelijks nodig heeft én het een plek is waar je heen gaat, niet iets dat je vanuit een opdracht of vacature bereikt. Wat over hetzelfde gaat, is een weergave van één plek.

**Een nieuw onderdeel van Beheer** voeg je toe met één regel in de lijst van `pages/AdminPage.tsx`. Het adres begint met `/beheer/`, dan blijft Beheer actief. Kan dat niet, zet het adres dan bij `also` van Beheer in de routetabel.

**De balk komt uit het designsysteem en staat alleen in de schil.** Vanaf `md` staat bovenaan één werkbalk: het merk, de plekken in `nldd-tab-bar` met `navigation`, het zoekveld in het midden, en aan het eind Beheer en het account. Op een smal scherm staan de plekken onderaan, als icoon met hun woord, met als laatste Ik: het account als pagina (`/ik`), met Mijn gegevens, Meldingen instellen, Beveiliging en Uitloggen. De plek waar je bent is een gevuld vlak, zoals het designsysteem het tekent. Wat niet past staat achter "Meer tabs"; de plek waar je bent blijft in de balk. De balk heeft één tabstop, de andere plekken bereik je met de pijlen. Het aantal taken staat bij Taken: breed in de tekst ("Taken (10)"), smal als badge op de hoek van het icoon, en in woorden in de naam van de balk ("Plekken in Grip, 10 taken te doen"). Het merk staat met de naam van de organisatie vanaf 1200 pixels, daaronder alleen het merk, en op een smal scherm niet. Schrijf `nldd-tab-bar` niet in een scherm; daar is `TabNav`.

**Zoeken.** Het zoekveld in de balk (`SearchField`) zoekt op naam in opdrachten, vacatures en mensen. Enter opent `/zoeken?q=` met de treffers per soort; er wordt niet bij elke toets gezocht, en korter dan twee tekens vraagt niets. Past het veld niet in de balk, dan staat "Zoek op naam" in het menu van de balk en heeft `/zoeken` een eigen veld; op een smal scherm staat het veld boven de titel van Start. Zoeken vervangt geen plek. Een lijst filteren is iets anders: dat doet `search` op een `ActionBar`.

**Binnen een plek of een ding wissel je met `TabNav`.** Eén vorm, de balk met onderlijn, en elke keuze is een pagina met een eigen adres:

| Wat | Hoe | Waar |
|---|---|---|
| De onderdelen van een geopend ding | `narrow="hide"`: op een breed scherm de wisselbalk onder de titel, op een smal scherm niets; daar wissel je via de landing | Een opdracht, een vacature |
| De weergaven van een lijst | `narrow="bar"`: ook op een smal scherm, met korte tekst in `short` | Opdrachten (Potentieel, Lopend, Afgesloten), Vacatures (Alle vacatures, Opengesteld), Mensen (Lijst, Bord, Bezetting, Declarabiliteit), Taken (Mijn taken, Bord), Aanvragen (Mijn aanvragen, Ontvangen offertes, Ontvangen aanvragen) |
| Losse pagina's die bij elkaar horen | Een overzichtspagina met `LinkRows` die melden wat ertoe doet; de pagina zelf is het menu | Geld, Beheer, Ik |

Een weergave die de lezer niet heeft staat er niet; Mensen vraagt de server welke dat zijn (`/api/people/views`) en toont bij één weergave geen balk. Er is geen keuzelijst voor een weergave en geen tweede balk. In een `ActionBar` staat hooguit één link naar een andere pagina.

**Tabs zijn nooit gevuld.** `TabNav` leest als de kanten van het ding, niet als knoppen. De tabbalk van het designsysteem (`nldd-tab-bar`) tekent het huidige tabblad als een gevuld vlak in de accentkleur, even hoog en even rond als de hoofdknop; onder een hoofdknop zijn dat twee dezelfde dingen boven elkaar. `TabNav` gebruikt daarom de menubalk van het designsysteem, die links tekent in een navigatiegebied met een lijn onder de huidige pagina. In de hoofdbalk speelt dat niet: daar staat geen hoofdknop.

**Twee lagen.** De hoofdbalk zegt waar je in grip bent en staat in de schil. `TabNav` zegt welk onderdeel of welke weergave je ziet en staat onder de titel, over de breedte van de kop, met een haarlijn. In de inhoud is de hoofdknop het enige gevulde vlak.

**De hoofdknop staat op de regel van de titel**, rechts (smal: onder de titel), via `action` op `Page`, of rechts in de `ActionBar`; nooit op de wisselbalk. Met een knop staat de `lead` onder de regel van de titel.

**Voorstel voor het designsysteem.** De tabbalk kent alleen de gevulde vorm. Een variant met een onderlijn (`variant="underline"`, of een eigen onderdeel voor navigatie tussen de kanten van één ding) zou dit oplossen zonder dat een toepassing de menubalk leent. De menubalk heeft daarnaast geen eigen maat of toon voor een onderdeel: grip zet in `.thing-tabs` in `index.css` de interne waarden `--_menu-bar-item-font` en `--_menu-bar-item-content-color`. Een `size` en een `tone` op `nldd-menu-bar-item` maken dat overbodig.

**Waar je bent.** Een pagina onder een plek, een overzicht of een ding heeft boven de titel één link terug: "Terug naar" met de naam van de plek of van het ding, bijvoorbeeld "Terug naar Geld" of "Terug naar Opdracht Alfa 2026". Geen kruimelpad: grip is twee lagen diep. Wie voor een taak op een pagina is, leest in de taakbalk "Terug naar Start".

Deze pagina's volgen dat nog niet:

| Pagina | Wat er nog moet gebeuren |
|---|---|
| `features/rates/RatesPage.tsx` | Geen link terug, zoals de andere pagina's onder Beheer die hebben (`useAdminBack`) |
| Wat is er gebeurd in `features/history/UpdateFeed.tsx` | Hoort bij Start, zonder link terug naar Start |
| `features/signing/SigningLayout.tsx` | Een eigen kop met losse tekst; de naam van de instantie als link naar het begin en het account als knop met een menu, zoals in de hoofdbalk |

## Een geopend ding

Een opdracht en een vacature openen op hun landing: wat er nu moet, en daaronder hun onderdelen als rijen. Het patroon van de zin en de knop staat onder Werkstromen hieronder.

**De landing van een opdracht** heeft van boven naar beneden: de link terug naar Opdrachten, de naam met de ene knop, een `lead` met voor wie, wanneer en waar ze staat ("Voorbeeldministerie, 1 jan t/m 31 dec 2026. Uitvoeren, daarna verantwoorden."), de zin wat er nu moet, de kerncijfers Begroot, Verwacht totaal en Afwijking over de hele looptijd, de link naar de taken, voor een teamlid "Jij: Developer, 100%, tot 31 dec 2026", en de rijen. De kerncijfers staan alleen hier. Een potentiële opdracht zegt dat in woorden, zonder label.

**Een rij meldt, ze rapporteert niet.** Een rij noemt het onderdeel en zegt eronder gedempt wat er speelt ("8 maanden af te sluiten", "1 rol open", "Getekend op 18 dec 2025"); heeft ze niets te melden, dan staat er alleen de naam. Geen bedrag uit de kop komt er nog eens in. De rijen staan altijd in deze volgorde: Afsluiten en factureren, Begroting, Offerte, Team, Eindrapport, Gegevens, Geschiedenis. Ze komen en gaan met de fase; de volgorde verspringt niet. Welke rijen er zijn en wat ze zeggen, beslist de server per gegevensklasse (`/api/assignments/{id}/parts`; zie `docs/toegang.md`). Een taak wijst nooit naar een onderdeel zonder rij.

**Een onderdeel is een eigen pagina** (`AssignmentPartPage`, `VacancyPartPage`): de link terug naar het ding, de naam van het onderdeel als titel, de ene knop van het onderdeel, op een breed scherm de wisselbalk, en de inhoud. Het tabblad van de browser noemt onderdeel en ding (`tabName`). Een onderdeel zonder rij geeft geen toegang, ook als iemand het adres intikt. De ene uitzondering is het rapport van een lopende opdracht: wie het geld leest, opent het via Begroting en Jaarverantwoording, met de titel "Rapport".

**Begroting heeft een vorm per fase.** Tot het akkoord is het de invoer: regels met FTE, schaal en bedrag. Een mondeling akkoord valt daar nog onder. Daarna per regel zeven kolommen, met een totaalrij die gelijk is aan de kop en de offerte. Begroting opent op de hele looptijd; een jaar kiezen kan alleen als de opdracht over meer jaren loopt. Een rij opent de regel voor wie mag wijzigen.

**De landing van een vacature** toont haar stappen als rijen: Aanvraag, Advies en akkoord, Tekst en openstellen, Vervullen, elk met haar stand als badge ("Klaar", "Nu aan de beurt") of in de zin ("Wacht op ..."). Twee stappen mogen tegelijk aan de beurt zijn. Daaronder Gegevens en Geschiedenis. Een vacature voor een gerede kandidaat wordt niet opengesteld en heeft die rij niet, tenzij er toch een tekst te schrijven is; dan heet ze Tekst. Een stappenbalk is er niet. Wie alleen de opengestelde tekst mag lezen, ziet die tekst en geen rijen. Een taak die bij de aanvraag hoort, opent de aanvraag zelf.

## Start

Start zegt wat er voor de lezer ligt, in één kolom en voor iedereen in dezelfde volgorde, zonder filters, jaarkeuze of volgordekeuze. Wat er staat beslist de server (`/api/start`); een blok zonder inhoud of zonder recht ontbreekt.

| Blok | Voor wie | Wat er staat |
|---|---|---|
| Te doen | Iedereen | Per zaak één rij: de eerstvolgende taak, de zaak en wat erna komt ("daarna nog 7 maanden en 1 taak"), met "Te laat" als badge. Hooguit vijf zaken, op volgorde van termijn; de laatste plek gaat naar de eerste zaak zonder termijn als die anders wegvalt. Altijd "Alle taken (10)" eronder, met hetzelfde getal als bij Taken in de balk. Niets te doen is één regel |
| Je werkt aan | Wie zelf inzet heeft | Per opdracht de eigen inzet ("Developer, 100%, tot 31 dec 2026"), "Geen inzet vanaf januari 2027" als die binnenkort stopt, en een rij naar Mijn gegevens |
| Planning | Planner | De open rollen met hun FTE, en hoeveel mensen zonder inzet zijn vanaf welke maand; beide naar het bord |
| Mijn opdrachten | Eigenaar of manager | Per opdracht de stand en de eerste rij die iets vraagt ("Uitvoeren, 8 maanden af te sluiten"), met Ruimte of Overschrijding als badge; een overschrijding bovenaan |
| Mijn mensen | Leidinggevende | Per persoon de inzet nu en vanaf wanneer hij vrij is. Het oordeel over de declarabiliteit staat één klik verder |
| Hoe staan we ervoor | Wie het geld van alle opdrachten leest | Het verwacht totaal van begroot, de investeerruimte en het potentieel, elk met het jaar of "hele looptijd" |
| Mijn aanvragen | Aanvrager | Per eigen aanvraag de stand in haar woorden |
| Verbindingen | Beheerder, alleen bij een probleem | Hoeveel berichten niet aankomen bij een andere instantie |
| Nieuw | Wie er nieuws heeft | De laatste drie gebeurtenissen, en "Alles wat er gebeurd is" |

Elk ander blok toont hooguit acht rijen, wat aandacht vraagt bovenaan, met "Alle 50" naar de plek met de rest. Binnenkort is deze maand en de drie maanden erna, het venster van Bezetting: daarbinnen waarschuwt Je werkt aan voor inzet die stopt, en telt Planning wie leeg valt. Wie nu al geen inzet heeft telt daarbij mee, zodat het getal klopt met het bord. Op Start staat niets van de klassen D, E en F: zo'n veld zou bij elk bezoek een inzage vastleggen, en het scherm wordt in overleg gedeeld.

## Werkstromen

Een zaak met een verloop (een opdracht, een vacature) zegt overal op dezelfde plek: onder de titel in een zin wat er nu gebeurt en wie aan zet is, rechts van de titel de ene knop die de stap zet. Het verloop is één regel tekst, klein en rustig: de stap waar de zaak staat en de stap daarna. Op een opdracht staat die regel in de `lead`, op een vacature zijn de stappen de rijen van de landing. De server beslist het; een scherm tekent het met `CourseNow` en `CourseLine` uit `@/ui/Workflow` en de gegevens van `useCaseCourse`. Een lijst toont dezelfde stand met `courseLine`. Draagt de kop de volgende stap, dan zet zij `PrimaryTakenContext`; de gedeelde knop en actiebalk tekenen een hoofdknop eronder dan als gewone knop. Op het scherm staat geen woord van het systeem. Het patroon, de regels en de praktijkgevallen staan in [werkstromen.md](werkstromen.md).

## Vier valkuilen in het designsysteem

**`nldd-form` verplaatst zijn kinderen.** Het zet zijn directe kinderen in een eigen formulierelement. Verschijnt er daarna een veld, dan vindt React de plek niet meer en wordt de pagina leeg. Zet de velden daarom in één vast element: `FormSheet` en `FormFields` doen dat.

**Een keuze in `nldd-dropdown` komt binnen via de `select`.** Sinds 0.21.0 laat de dropdown de `change` van de `select` door, zonder `detail` en met de `select` als `target`. Een `onChange` op de `select` is genoeg; luister niet ook op de dropdown, want dan komt elke keuze twee keer binnen. `FilterSelect` en `ActionBar` doen het zo.

**Een keuze in een menu die een paneel of dialoog opent, wacht tot het menu dicht is.** Sinds 0.24.0 knippert een gekozen menu-item voordat het menu sluit, terwijl `select` meteen komt. Een paneel dat dan al opent, geeft bij het sluiten de focus aan de pagina in plaats van aan de knop van het menu. Dat geldt voor een menu onder een knop of een icoonknop; het menu Meer van een werkbalk geeft de focus sinds 0.26.2 zelf terug. Luister in zo'n menu daarom met `useMenuSelect` uit `@/components/nldd/events`; `RowActions` doet het zo.

**Een cel hoort in een rij.** `nldd-text-cell` en `nldd-cell` krijgen hun hoogte van de rij van een tabel of lijst. Los op een pagina heeft zo'n cel geen hoogte: de tekst wordt wel getekend, maar valt over wat eronder staat. Gebruik buiten een rij `Quiet`, `Facts` of gewone tekst.

## Meten in een browser

Een scherm is pas gecontroleerd als het in een browser is gemeten en bekeken. Daar is één commando voor:

```
just check-spacing
```

Het laadt elke route uit `AppRoutes.tsx` in een browser zonder venster, als beheerder en als eigenaar van een opdracht, op 1280 en 390 breed, en meldt per pagina:

| Bevinding | Betekenis |
|---|---|
| `collapsed` | Een onderdeel zonder hoogte waarvan de inhoud toch wordt getekend |
| `overlap` | Twee blokken onder elkaar die over elkaar vallen |
| `touching` | Twee verschillende blokken zonder ruimte ertussen |
| `off-scale` | Een afstand die geen stap van de schaal is |
| `edge` | Een blok dat niet op de linkerrand van zijn buren begint |
| `height` | Bedieningselementen in één rij met een verschillende hoogte |
| `tight` | Tekst dichter dan 8 op de rand van een eigen vlak |
| `badge` | Een label dat niet in het midden van de regel van zijn naam staat |
| `overflow` | De pagina schuift opzij |
| `clipped` | Tekst die door zijn vak wordt afgesneden |

De servers moeten draaien. Het commando gebruikt een eigen hostnaam (`spacing.localhost`), zodat het de sessie in je eigen browser niet raakt. Handige opties:

- `just check-spacing --only /beheer --verbose` meet een deel en toont elke bevinding met de plek.
- `just check-spacing --shots <map>` bewaart van elke pagina een afbeelding. Bekijk ze: de meting vindt afstanden en overlap, het oog vindt wat slecht leest.
- `just check-spacing --only /opdrachten --click "Nieuwe opdracht"` drukt eerst op een knop, om een geopend formulier te meten.

Een getekend raster dat zijn eigen cellen plaatst, zoals de tijdbalk, krijgt `data-spacing="grid"` en wordt als één blok gemeten, net als een tabel.

Twee meetfouten om te kennen. In een verborgen tabblad van een gewone browser vuurt geen `ResizeObserver`: de schil denkt dan dat het scherm smal is. En een afbeelding van de hele pagina in plaats van het venster doet hetzelfde. Het commando meet en fotografeert daarom in een eigen venster van vaste maat.

Naast de meting bewaakt een test de bron (`ui/layout/spacing.guard.test.ts`): een `gap` buiten de schaal of een marge in pixels in een nieuw bestand laat de build falen. De bestaande uitzonderingen staan er met hun aantal in en mogen alleen minder worden.

## Controlelijst voor een nieuw scherm

1. Eén regel: wat komt iemand hier doen?
2. `Page` met een titel en een soort (`kind`) uit de tabel onder "Soorten scherm". Meerdere delen: `spacing="sections"` en per deel een `Section`.
3. Filters in een `ActionBar`; de ene hoofdknop op de regel van de titel (`action`) of rechts in die balk.
4. Gegevens in een `nldd-table` met `columns`, feiten in `Facts`.
5. Toevoegen en wijzigen in een `FormSheet`.
6. Laden, fout en leeg met de drie vaste onderdelen.
7. Elke zin gelezen als buitenstaander, met de vaste woorden.
8. Gemeten in een browser, in licht en donker.

## Nog over te zetten

De meeste schermen zijn bij de doorloop op visuele hiërarchie overgezet op de bouwstenen (zie `docs/hierarchie/`). Wat nog eigen onderdelen gebruikt:

| Bestand | Wat er nog moet gebeuren |
|---|---|
| `features/assignments/ui.tsx` | Geeft door naar de basis, op de eigen invoervelden (`TextInput`, `DateInput`, `SelectInput`) na; die kunnen naar `@/ui/fields`. |
| `features/team/ui/` | De eigen `Sheet` en `Form` samenvoegen met `FormSheet`. Dat vraagt dat de toestand van elk formulier eerst uit het paneel wordt gehaald, omdat `FormSheet` zijn inhoud aangekoppeld houdt. |
| `features/team/PersonPage.tsx`, `features/client/ClientAssignmentPage.tsx` | Tekenen hun kop zelf, zonder `Page`, en hebben daardoor geen `kind`. Op de aanvraag staat de link terug onder de titel. |

`index.css` houdt tot dan twee noodregels aan: een afstand tussen de kinderen van een sectie, en een afstand tussen de velden in een `div.form-fields`. Of ze weg kunnen is niet beproefd.

## Iconen

Tekst gaat voor. Een icoon staat er alleen als het moet of als het het vaste beeld van een onderdeel is, en hetzelfde beeld betekent overal hetzelfde. Code noemt daarom nooit een icoon maar een begrip; `frontend/src/ui/icons.ts` beslist het beeld, de plek en de naam. De test `icons.guard.test.ts` faalt op een icoonnaam, een los icoonelement of een teken als icoon (pijl, vinkje, uitroepteken) buiten die basis.

Alle iconen komen uit het designsysteem. Heeft een begrip daar geen passend beeld, dan krijgt het geen icoon.

### Waar wel, waar niet

| | Plek |
|---|---|
| Verplicht | Een knop zonder tekst (het rijmenu, sluiten). Een link die de pagina verlaat: nieuw tabblad, document, andere site. Een download. Een stand of signaal dat los staat van tekst. |
| Toegestaan | De terugverwijzing boven een titel. Een rij die opent. Een keuze "voeg toe" onder in een keuzelijst. De balk onderaan op een smal scherm en het menu van een balk, waar elke plek haar beeld heeft. |
| Verboden | Naast een kop. In lopende tekst. Op een knop met een werkwoord ("Wijzig", "Nieuwe opdracht", "Bewaar"), ook de hoofdknop. In een menu met acties: het woord zegt het, verwijderen heeft zijn kleur. Op elke rij van een tabel wat de kolomkop kan zeggen. Twee iconen op een element. Een icoon dat alleen de tekst van een label herhaalt. |

### Plek, maat en naam

- Het icoon staat voor de tekst. Erachter staan alleen de beelden die verder wijzen: de pagina verlaten en een rij die opent.
- Een maat per plek: 16 in of naast tekst, 20 in een cel, 24 los. Nooit schalen met CSS.
- Een icoon naast tekst is versiering en onzichtbaar voor hulpsoftware. Een knop zonder tekst heet naar het vaste werkwoord van zijn begrip plus waar het over gaat: "Meer acties voor Developer", "Download offerte.pdf, 120 kB".
- Betekenis hangt nooit alleen aan beeld of kleur: een stand heeft ook een woord.
- Verwijderen heeft overal dezelfde vorm: het woord "Verwijder", de kleur van een onomkeerbare actie en een vraag om bevestiging. Het icoon (prullenbak) alleen waar geen plaats is voor het woord.

### Begrippen

| Begrip | Icoon | Wanneer |
|---|---|---|
| `more` | more | Het ene knopje met wat een rij of kaart nog meer kan |
| `add` | plus | Iets nieuws toevoegen vanuit een keuzelijst |
| `remove` | trash | Verwijderen, alleen zonder plaats voor het woord |
| `download` | download | Een bestand dat op het apparaat van de lezer komt |
| `upload` | upload | Een bestand dat de lezer aanlevert |
| `back` | arrow-left | Terug naar het onderdeel waar een pagina bij hoort |
| `elsewhere` | external-link, achter de tekst | Alles wat buiten deze pagina opent |
| `open` | chevron-right, achter de tekst | Een rij of regel die opent of uitklapt |
| `close` | close | Een paneel of dialoog sluiten |
| `copy` | copy | Naar het klembord, alleen zonder plaats voor het woord |
| `search` | search | Zoeken in een lijst |
| `undo` | arrow-u-turn-backward | Terug naar een eerdere stand |
| `done` | check-circle-filled | Klaar, vastgesteld, volledig |
| `todo` | circle | Nog te doen, niets mis |
| `waiting` | clock | Wacht, op tijd of op een ander |
| `attention` | warning | Vraagt aandacht: over begroting, te laat, dubbel geboekt |
| `error` | error | Misgegaan |
| `info` | info-circle | Goed om te weten |
| `locked` | lock | Vastgelegd en niet meer te wijzigen |
| `start`, `task`, `assignment`, `staffing`, `vacancy`, `team`, `cost`, `report`, `request`, `settings` | house, check-list, folder, calendar-event, person-badge-plus, person-2, euro-sign, chart-x-y-axis-line, paper-plane, gear | Het onderdeel in het hoofdmenu, en hetzelfde ding elders |
| `person`, `account`, `logout`, `menu` | person, person-circle, logout, list | Het accountmenu en de menuknop |
| `document`, `history`, `proof`, `security`, `organisation`, `node`, `mail` | document, clock-arrow-counter-clockwise, seal-check-mark, key, building, tree-structure, mail | Het ding zelf, waar het een beeld nodig heeft |

De meldingen (`nldd-inline-dialog` met `variant`) en de bevestigingsdialoog tekenen hun eigen icoon; grip zet daar niets overheen.

### In code

- `iconAttribute('download')` geeft het attribuut voor een knop of link met tekst; `iconOf` de naam voor een menu-item of label; `iconLabel('more', naam)` de naam van een knop zonder tekst.
- `@/ui/Icon`: `Icon`, `IconCell`, `MoreButton`, `BackLink`, `DocumentLink` (bekijken of downloaden) en `ExternalLink`.
- `ActionBar` neemt `kind: 'download' | 'elsewhere'` op een actie die de pagina verlaat.
