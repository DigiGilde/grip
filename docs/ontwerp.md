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

- Eén accent, voor de ene hoofdactie van het scherm. De rest is neutraal.
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

## De bouwstenen

Ze staan in `frontend/src/ui/layout/` en `frontend/src/ui/`.

| Bouwsteen | Waarvoor |
|---|---|
| `Page` | Een pagina in de schil: de titel in de kop van de sectie, daaronder de inhoud op één ritme. Eén per route. |
| `Section` | Een deel van een pagina met een eigen kop en hooguit één regel uitleg. |
| `Stack` | Onderdelen onder elkaar, met een afstand uit de schaal. |
| `Facts` | Feiten als "label: waarde", met de labels in één kolom. Voor lezen. |
| `CardGrid` | Kaarten in rijen van gelijke hoogte. |
| `FormSheet` | Een formulier in een zijpaneel. Het ene patroon voor toevoegen en wijzigen. |
| `FormFields` | De velden van een formulier op één afstand, ook op een pagina. |
| `FilterSelect` | Eén keuzelijst op de gewone maat. |
| `OpenRow`, `OpenCell`, `RowActions` (`@/ui/RowActions`) | Een rij die opent, en één stille knop met een menu voor de overige acties. |
| `ActionBar` (`@/ui/ActionBar`) | Filters links, de hoofdactie rechts, alles op één maat. |
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

**Een status is een label.** Gebruik `nldd-tag` of `nldd-badge` met de kleur uit de bestaande toewijzing. De kleur draagt nooit als enige de betekenis.

**Schrijf gewoon Nederlands.** Lees elke zin als iemand die het systeem niet heeft gebouwd. Zinnen beginnen met een hoofdletter en hebben verder kleine letters, zonder uitroepteken. Je schrijft "je". Een knop zegt wat er gebeurt.

### Vaste woorden

| Woord | Betekenis |
|---|---|
| Begroot, Gerealiseerd, Nog gepland, Kosten, Verwacht totaal, Afwijking | De bedragen van een opdracht |
| Uitputting | Het deel van de begroting dat is gerealiseerd, als percentage |
| Aangeleverd | Factuurgegevens zijn doorgegeven aan de financiële administratie |
| Gefactureerd | Er is een factuur verstuurd en vastgelegd |
| Potentiële opdracht | Een opdracht tot het akkoord |
| Offerte maken | De begroting vastleggen als offerte. Daarna wijzigt de offerte niet meer; ze krijgt een kenmerk |
| Aanbieden | Een gemaakte offerte naar de opdrachtgever brengen |
| Getekend, afgewezen | De beslissing van de opdrachtgever over een aangeboden offerte |
| Rechten in grip | Wat iemand in grip mag: beheerder, planner, lezer, aanvrager, tekenbevoegde |
| Aanvraag voorbereiden, aanvragen, advies en akkoord, openstellen, vervullen | De stappen van een vacature |

## Navigatie

De hoofdbalk staat in `frontend/src/layout`; welke onderdelen er zijn, voor wie en welke pagina's erbij horen staat in `frontend/src/routes.ts`. Het waarom staat in ADR 0033.

**Een nieuw onderdeel van Beheer** voeg je toe met één regel in de lijst van `pages/AdminPage.tsx`. Het adres begint met `/beheer/`, dan blijft Beheer actief. Kan dat niet, zet het adres dan bij `also` van Beheer in de routetabel.

**Binnen een onderdeel kies je één middel:**

| Middel | Wanneer |
|---|---|
| Tabs | Meerdere kanten van één ding dat je open hebt: een opdracht, een vacature. Elk tabblad heeft een eigen adres |
| Overzichtspagina | Losse pagina's die bij elkaar horen maar niet over hetzelfde ding gaan: Beheer, Rapportage. De pagina zelf is het menu |
| Link in de `ActionBar` | Eén afgeleide lijst van dezelfde gegevens, zoals "Open rollen" bij Vacatures. Hooguit één; worden het er meer, dan zijn het tabs |

**Waar je bent.** Een pagina onder een overzicht of een lijst heeft boven de titel één link terug: "Terug naar" met de naam van het onderdeel zoals die in de balk staat, bijvoorbeeld "Terug naar Opdrachten". Geen kruimelpad: grip is twee lagen diep.

Deze pagina's volgen dat nog niet:

| Pagina | Wat er nog moet gebeuren |
|---|---|
| `features/assignments/AssignmentLayout.tsx` | De link staat onder de titel en zegt "opdrachten" met een kleine letter |
| `features/team/PersonPage.tsx` | Een kruimelpad in plaats van de link |
| `features/vacancies/VacancyLayout.tsx` | Geen link terug |
| De pagina's onder Beheer (tarieven, offertes, afzender, koppelingen, organisaties, rollen, activiteit, functiegebouw) | Geen link terug naar Beheer |
| `features/wies/WiesProposalsPage.tsx` | Staat onder Beheer en linkt terug naar "team" |
| `features/reports` | "Terug naar de rapportage" naast "Terug naar Rapportage" |
| `features/vacancies/VacanciesPage.tsx` | Twee links in de `ActionBar`; "Formulier en taalmodel" hoort alleen onder Beheer |
| `features/signing/SigningLayout.tsx` | Een eigen kop met losse tekst; de naam van de instantie als link naar het begin en het account als knop met een menu, zoals in de hoofdbalk |

## Twee valkuilen in het designsysteem

**`nldd-form` verplaatst zijn kinderen.** Het zet zijn directe kinderen in een eigen formulierelement. Verschijnt er daarna een veld, dan vindt React de plek niet meer en wordt de pagina leeg. Zet de velden daarom in één vast element: `FormSheet` en `FormFields` doen dat.

**Een keuzelijst in `nldd-dropdown` verstuurt zijn eigen gebeurtenis.** De dropdown houdt de `change` van de `select` erin tegen en verstuurt er zelf een. Een `onChange` op de `select` alleen gaat dus nooit af. Luister met `useNlddEvent` op de dropdown: `FilterSelect` en `ActionBar` doen dat.

## Meten in een browser

Een scherm is pas gecontroleerd als het in een browser is gemeten. Wat je meet:

- de horizontale positie van koppen, tekst en tabellen: één waarde;
- de verzameling afstanden op de pagina: alleen waarden uit de schaal;
- de hoogte van bedieningselementen in een rij: één waarde;
- de hoogte van het document tegenover het venster, voor een pagina die past.

Meet in een tabblad dat zichtbaar is, of wek de schil eerst. In een verborgen tabblad vuurt de browser geen `ResizeObserver`. De schil denkt dan dat het scherm smal is en telt de hoogte van de werkbalk niet mee, waardoor elke pagina 73 pixels te hoog lijkt. Dat is een meetfout, geen fout in grip: in een zichtbaar venster is het document precies zo hoog als het venster.

## Controlelijst voor een nieuw scherm

1. Eén regel: wat komt iemand hier doen?
2. `Page` met een titel. Meerdere delen: `spacing="sections"` en per deel een `Section`.
3. Filters en de hoofdactie in een `ActionBar`.
4. Gegevens in een `nldd-table` met `columns`, feiten in `Facts`.
5. Toevoegen en wijzigen in een `FormSheet`.
6. Laden, fout en leeg met de drie vaste onderdelen.
7. Elke zin gelezen als buitenstaander, met de vaste woorden.
8. Gemeten in een browser, in licht en donker.

## Nog over te zetten

Deze schermen gebruiken de bouwstenen nog niet. Tot ze over zijn, houdt `index.css` twee noodregels aan: een afstand tussen de kinderen van een sectie, en een afstand tussen de velden in een `div.form-fields`.

| Bestand | Wat er nog moet gebeuren |
|---|---|
| `features/assignments/ui.tsx` | `FormSheet`, `Loading`, `ErrorNotice`, `EmptyNotice` en `SectionHeading` vervangen door die uit `@/ui/layout`. De eigen `SectionHeading` staat op maat 3, de afspraak is 4. `InlineSelect` staat op een kleinere maat dan de knoppen ernaast. |
| `features/assignments`, `features/allocations`, `features/overview` | De pagina's opbouwen met `Page` en `Section`. |
| `features/team/ui/` | De eigen `Sheet`, `Form` en `QueryState` samenvoegen met `FormSheet` en de vaste toestanden. |
| `features/team`, `features/rates` | De pagina's opbouwen met `Page` en `Section`. |
| `features/vacancies/VacancyDetailPage.tsx` | Zes secties onder elkaar, ruim drie schermen hoog. Tabs, zoals de opdrachtpagina. |
| `features/function-framework` | Zestig groepen onder elkaar. Een zoekveld erboven. |
