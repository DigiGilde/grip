# Visuele hiërarchie: opdrachten, startpagina, Inzet en de basis

Ronde A van de doorloop op visuele hiërarchie. Dit deel gaat over de lijst van opdrachten, de pagina van een opdracht met haar tabs, de startpagina, het bord Inzet, de context uit het corpus en de gedeelde bouwstenen in `frontend/src/ui`.

## De toets

Per scherm en per soort lezer is nagegaan:

1. Wat komt deze lezer hier doen of leren? Daar moet het oog als eerste landen.
2. Hooguit drie niveaus: wat nu speelt, het verloop of de lijst, en detail op aanvraag.
3. Eén niveau met een rand, afstanden uit de schaal, één linkerrand.
4. Niets dat de interface uitlegt, niets twee keer, niets dat er niet is.
5. Wie alleen leest, ziet geen acties en één rustige regel over wie wel kan.
6. Smal (390): niets afgekapt, niets schuift zijwaarts.

Elk scherm is vastgelegd met een browser zonder venster, op 1440 en 390 breed, donker. Van elk scherm is een wazige kopie bekeken om te zien waar het oog landt. De startpagina, het overzicht van een opdracht en Financieel zijn ook licht bekeken.

## Per scherm

| Scherm | Lezer | Oog vooraf: eerst, dan, dan | Gewijzigd | Oog nu: eerst, dan, dan |
|---|---|---|---|---|
| Startpagina | Eigenaar | De vier omrande cijfertegels, de kop van de lijst, pas dan taken en aandacht | Taken staan eerst, daarna aandacht. Aandachtspunten zijn één lijst: de zin is de link naar waar je het oplost, de opdracht staat eronder. De cijfers staan zonder kader en zonder uitleg. Een som van niets is weg. "Pijplijn" heet "Potentiële opdrachten" | Mijn taken, wat aandacht vraagt, de cijfers |
| Startpagina | Planner, lezer, teamlid | Als boven; bij een lezer een lege kolom taken | Dezelfde opbouw; de rest volgt uit wat de server geeft | Taken of aandacht, cijfers (wie geld mag zien), lijst |
| Opdrachten | Beheerder, eigenaar | De knop, de tabs, een kolom met op elke rij "In uitvoering" | De status staat achter de naam en alleen als ze meer zegt dan de weergave. "Pijplijn" heet "Potentieel". Smal: één kolom | De knop, de weergave, de namen |
| Kop van een opdracht | Iedereen | De titel, een teruglink eronder, een label, twee losse regels, een tabel met kerncijfers | Teruglink boven de titel. Label, opdrachtgever, periode en "als wie je kijkt" op één regel. Kerncijfers zonder tabel. Smal: de tabs zijn één keuzelijst en de cijfers staan twee aan twee | Titel, kerncijfers, tabs |
| Overzicht, lopende opdracht | Eigenaar | Een omrande lijst gegevens (opdrachtgever en periode stonden ook in de kop), drie losse knoppen onderaan, de context twee keer (kaarten en een tabel met adressen) | Eén balk met "Wijzig gegevens" en een menu voor de stappen in de status; annuleren en afwijzen vragen nu om bevestiging. Gegevens zonder kader en zonder wat de kop al zegt. De context staat één keer; verwijderen zit op de kaart | Kerncijfers, de gegevens, eigenaar en managers |
| Overzicht, potentiële opdracht | Eigenaar | De stappenbalk, de hoofdknop, daarna vijf gelijke knoppen | De vijf knoppen zitten in het menu | Stappenbalk, "Bied de offerte aan", gegevens |
| Financieel | Eigenaar | Twee omrande tabellen met een alinea uitleg, daarna vijf gekleurde balken van gelijk gewicht | Aandachtspunten eerst, als één lijst met een dunne markering (rood voor wat nu mis is). Offerte en facturering als zes cijfers zonder kader. Drie alinea's uitleg weg. Downloads hebben hun vaste icoon | Aandachtspunten, de stand per regel, de cijfers |
| Begroting | Eigenaar | Een regel "Looptijd" met een knop, een kop "Begroting" onder de tab "Begroting", subtotaal en totaal gelijk | De looptijd staat in de kop; wijzigen zit in de balk. Geen dubbele kop. Subtotaal alleen bij meer jaren, offertebedrag alleen als het afwijkt. Smal: het bedrag blijft in beeld | De hoofdknop, de regels, het totaal |
| Bemensing | Eigenaar, planner | De knoppen, een gewone zin, de tijdbalk | De zin over de stand staat eerst en groter. Dubbel geboekt is een lijst met een link naar de persoon. Smal: het aantal FTE staat onder de rolnaam, vrij van het menu | De zin, de hoofdknop, de balken |
| Inzet | Planner | Op elke rij zonder werk twaalf keer "vrij 100%"; een legenda van zeven onderdelen | Een rij zonder inzet zegt dat één keer onder de naam. De legenda toont alleen wat in beeld is. Het uitroepteken en het ongelijkteken zijn vervangen door het icoon voor aandacht en de woorden "Ander tarief" | De balken, de hoofdknop, de rij boven 100% |

## Voor en na

| | Voor | Na |
|---|---|---|
| Startpagina | ![](a/start-priya-voor.png) | ![](a/start-priya-na.png) |
| Overzicht van een opdracht | ![](a/alfa-overzicht-priya-voor.png) | ![](a/alfa-overzicht-priya-na.png) |
| Financieel | ![](a/alfa-financieel-priya-voor.png) | ![](a/alfa-financieel-priya-na.png) |
| Begroting | ![](a/alfa-begroting-priya-voor.png) | ![](a/alfa-begroting-priya-na.png) |
| Bemensing | ![](a/alfa-bemensing-priya-voor.png) | ![](a/alfa-bemensing-priya-na.png) |
| Potentiële opdracht | ![](a/eps-overzicht-lotte-voor.png) | ![](a/eps-overzicht-lotte-na.png) |
| Inzet | ![](a/inzet-pim-voor.png) | ![](a/inzet-pim-na.png) |
| Opdrachten | ![](a/lijst-beheer-voor.png) | ![](a/lijst-beheer-na.png) |
| Opdracht, smal | ![](a/alfa-overzicht-390-voor.png) | ![](a/alfa-overzicht-390-na.png) |

## Tabs die geen knoppen zijn

Na de eerste ronde kwam de vraag of tabs er zo uit horen te zien: onder de hoofdknop "Vraag aan" stond een tabbalk waarvan het huidige tabblad dezelfde kleur, vorm en hoogte had. Dat is hoe de tabbalk van het designsysteem tekent, en het breekt de regel van één accent op elke pagina met tabs.

| | |
|---|---|
| Vacature | ![](a/vacature-tabs-na.png) |
| Opdracht | ![](a/opdracht-tabs-na.png) |
| Vacature, smal | ![](a/vacature-tabs-smal-na.png) |

Bekeken: een vacature en een opdracht op 1440, 1024 en 390, donker en licht; de lijst van opdrachten op 1440 en 390; een persoon onder de tweede balk van Team; het bord Inzet. Op elk van die schermen is de hoofdknop het enige gevulde vlak in de accentkleur. De documenttabbalk van het designsysteem is voor geopende documenten die je sluit en verschuift, en past hier niet.

## Gedeelde oorzaken, opgelost in de basis

| Oorzaak | Bouwsteen | Gebruik |
|---|---|---|
| De teruglink stond op elke pagina anders | `Page` en `TitleBlock` nemen `back={{ href, text }}` | De link staat boven de titel. `TitleBlock` is voor een schil die haar eigen sectie opbouwt |
| Een paar cijfers stonden in een tabel of in tegels | `KeyFigures` met `label` en `figures` (`label`, `value`, `detail`, `critical`) | Zonder kader, zoveel kolommen als passen |
| Aandachtspunten als stapel balken | `SignalList` met `label` en `signals` (`key`, `text`, `href`, `detail`, `tone`) | Eén lijst; `tone: 'critical'` voor wat nu mis is |
| Tabs worden op smal tot één letter afgekapt | `TabNav` met `label`, `items` (`key`, `text`, `href`) en `current` | Breed de tabbalk, smal één keuzelijst |
| Vijf gelijke knoppen naast elkaar | `ActionBar` neemt `more={{ name, actions }}` | Zeldzame en onomkeerbare acties in één menu, met bevestiging |
| Legenda groter dan het plaatje | `occurringLegend(groups)` in `@/ui/timeline/layout` | Alleen wat getekend is |
| Een waarde in `Facts` brak op smal midden in een woord | `Facts`: smal staat het label boven de waarde; `omitEmpty` laat lege feiten weg | Breed is de opbouw ongewijzigd |
| Een tabel liet op smal een kolom vallen | `OpenCell` neemt `hideBelow`, `hideAbove` en `narrowText` | De weggevallen kolom staat als gedempte regel onder de naam |
| Korte cellen zweefden in het midden van een hoge rij | `TOP_ALIGNED` uit `@/ui/layout`, en `verticalAlignment` op `OpenCell` | De cellen van het designsysteem kennen `vertical-alignment="top"`; dit is de vaste manier om het te zetten |
| Een rij kon niet in een nieuw tabblad open | `OpenCell` neemt `href` | Een gewone klik roept `onOpen` aan, een klik met een toets erbij volgt de link |
| `RouterLinks` slokte een slot op | `RouterLinks` neemt `slot` en maakt zelf geen vak (`display: contents`) | Een titelblok erin komt in de kop van de sectie |
| De kop boven tabs stond twee keer uitgeschreven | `ThingHead` met `title`, `instanceName`, `back`, `tabs={{ label, items, current }}` en de inhoud tussen titel en tabs | De schil van een opdracht gebruikt hem; die van een vacature kan volgen |
| Het huidige tabblad was een gevuld vlak, even hoog en rond als de hoofdknop | `TabNav` tekent de menubalk van het designsysteem: tekst, een haarlijn onder de rij, een lijn onder het tabblad waar je bent | Ook voor de weergaven van de lijst van opdrachten. Smal blijft het één keuzelijst |
| De hoofdknop stond direct op de tabs | `ThingHead` neemt `action` (rechts van de titel) en `course` (de stappenbalk, tussen kop en tabs) | De schil van een vacature gebruikt `ThingHead` nu ook |
| Tekens als icoon in de tijdbalk | `mark` op een balk is `'attention'` of `'mismatch'` | Het icoon voor aandacht, of de woorden "Ander tarief" |

Alle bestaande eigenschappen werken als voorheen.

## Bewust gelaten

- Inzet staat sinds het nieuwe menu onder een tweede balk (Mensen, Inzet). Die balk staat boven de titel en is navigatie; de balk met filters en de hoofdknop staat eronder. Ze lezen als twee verschillende dingen. De pagina heeft geen teruglink: haar buren staan in de tweede balk.

- De tabel "Inzet per maand" op Financieel heeft zeven kolommen. Ze is een gegevenstabel voor wie haar zoekt, onderaan de tab.
- De tab Taken en het blok "Mijn taken" horen bij de taken; die zijn in een andere ronde bekeken.
- De startpagina zegt "7 maanden zijn nog niet afgesloten" als aandachtspunt en "Sluit maart 2026 af" als taak. Dat is hetzelfde feit van twee kanten. Kiezen welke van de twee het zegt, vraagt een besluit over wat een aandachtspunt is naast een taak.
- De keuze "Volgorde" op de startpagina staat boven de inhoud. Ze is klein en neutraal; weghalen is een keuze over de functie, niet over de vorm.

## Niet bekeken

- De formulieren voor een nieuwe opdracht, een begrotingsregel en een inzet zijn geopend en vastgelegd, maar alleen het formulier voor een nieuwe opdracht is bekeken.
- De lichte modus van Begroting, Bemensing en Inzet.
- Het detail van een node en het kiezen van een node.
- Een opdracht met een overschrijding op de kerncijfers in de kop.
