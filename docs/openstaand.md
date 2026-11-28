# Wat op iemand wacht

Deze pagina verzamelt wat niet verder kan zonder een beslissing of een antwoord. Elk punt staat een keer, bij wie het kan beantwoorden, met een verwijzing naar de plek waar het is uitgewerkt. Wat technisch nog niet af is staat hier niet: dat staat in [plan.md](plan.md) en [rondgang.md](rondgang.md).

Stand: 9 oktober 2026, en voor wat de herinrichting van de interface openliet 7 november 2026.

## De opdrachtgever van grip

Beslissingen over wat grip moet doen.

| Punt | De keuze | Waar |
|---|---|---|
| Gegevens in een geschreven onderdeel van een offerte | Een standaardtekst van de offerte die niemand aanpaste volgt de tariefjaren, het factuurritme en de afzender. Een onderdeel dat iemand herschreef houdt die waarden als gewone tekst vast en zegt niet dat ze verouderd zijn. Moet de offerte gegevens bij sleutel bewaren, zoals de vacaturetekst? | [vacatureteksten.md](vacatureteksten.md), "Gegevens en open plekken" |
| Tarieven en een getekende opdracht | Na het vaststellen van een tarievenkaart volgt de begroting van een opdracht met een getekende offerte de nieuwe tarieven; het verschil met de offerte wordt getoond. Klopt dat, of houdt een getekende opdracht haar prijs? | [rondgang.md](rondgang.md), A612 |
| Maanden op volgorde | Een maand kan worden afgesloten terwijl een eerdere nog open is. Mag dat? | [rondgang.md](rondgang.md), B611 |
| Dekking van een kostenpost | De keuzelijst biedt ook personeelsregels aan als dekking. Hoort een kostenpost alleen door een vast bedrag gedekt te worden? | [rondgang.md](rondgang.md), A608 |
| Open rollen bij de eigenaar | Een rol invullen is nu ook de stap van de eigenaar of manager; haar teller en meldingen tellen open rollen op eigen opdrachten mee | [werkstromen.md](werkstromen.md) |
| Het merk | Richting a (greep) of b (letter), of geen van de vier. Nu staat a erin, voorlopig | [merk.md](merk.md), het vel in `docs/merk/richtingen.png` |
| Na het akkoord | De begroting kan na een getekende offerte nog worden gewijzigd; grip laat het verschil zien en blokkeert niets. Het voorstel is een aanvullende offerte op dezelfde opdracht, terwijl ze in uitvoering blijft. Dat is ontworpen, niet gebouwd | [werkstromen.md](werkstromen.md), "Ontwerp: verlengen of groeien na akkoord" |
| Een nieuw factuuradres van een gast | Een opdrachtgever zonder eigen grip, die met een tekenlink tekende, kan het factuuradres daarna niet zelf wijzigen; de opdrachtmanager doet het met de hand. Een nieuwe link per mail kan dat oplossen. Niet gebouwd | ADR 0058 |
| Een bevestigingscode per mail bij het tekenen | Alleen nodig als SSO Rijk opnieuw aanmelden niet afdwingt en de juristen het tijdstip van belang vinden. Niet gebouwd | [bewijs.md](bewijs.md), [sso-rijk.md](sso-rijk.md) |
| Advies van iemand zonder account | Nu legt alleen een beheerder het advies vast van een adviseur die niet in grip zit; de aanvrager wacht. Mag de aanvrager het zelf vastleggen? Let op de scheiding van taken: de aanvrager legt dan vast wat een ander besloot, niet een eigen oordeel | [taken.md](taken.md), ADR 0048 |
| Een of twee soorten opmaak | Een vacaturetekst kent cursief en opsommingen; een offerte ook vet en genummerde lijsten. Gelijktrekken kan | [vacatureteksten.md](vacatureteksten.md), [offerte-document.md](offerte-document.md) |
| Namen in een offerte | Grip weigert namen van medewerkers in een offerte. Een van de voorbeeldoffertes noemde ze wel, met een tarief per persoon. Blijft de regel? | ADR 0032 |
| Een heropende maand | Een maand die na het aanleveren is heropend wordt opnieuw volledig aangeleverd en vervangt het eerdere verzoek, ook als dat al gefactureerd was. Past dat, of moet het dan een verschil zijn? | ADR 0047, en de vraag aan de financiële administratie hieronder |
| De definitie van investeerruimte | Er staan twee voorlopige lezingen, in geld en in tijd | [domein.md](domein.md), begrippen |
| Deeltijd | Iedereen telt als voltijds. Een factor per persoon ontbreekt | [domein.md](domein.md) |
| Het menu | De inrichting met vijf plekken en een smalle wisselbalk is gekozen en gebouwd. De aannames erachter zijn niet bij gebruikers getoetst | [ADR 0055](adr/0055-vijf-plekken-en-een-rustig-geopend-ding.md), en "Gebruikers" hieronder |
| Een hoofd op Start | Een hoofd zonder rechten op personen of op het geld van alle opdrachten krijgt op Start geen bezetting en geen "Hoe staan we ervoor", en dus ook geen tegel die 0% zegt. Krijgt een hoofd de bezetting als totaal zonder namen, en de cijfers over alle opdrachten, of niet? | ADR 0055 |
| De blokken van Start | Welk blok iemand krijgt volgt uit rechten en relaties: een planner Planning, een eigenaar of manager Mijn opdrachten, een leidinggevende Mijn mensen, wie het geld van alle opdrachten leest Hoe staan we ervoor. "Binnenkort" is deze maand en de drie maanden erna, het venster van Bezetting: daarbinnen waarschuwt Je werkt aan voor inzet die stopt, en telt Planning wie leeg valt, ook wie nu al geen inzet heeft. Kloppen de blokken per lezer, en is vier maanden de goede grens? | [ontwerp.md](ontwerp.md), "Start" |
| Vervullen zonder het recht om te wijzigen | De taak "Leg vast wie is aangenomen" is van de aanvrager, maar een aanvrager mag een vacature als zodanig niet wijzigen. Zonder dat recht staat de taak er zonder weg erheen en zonder rij Vervullen, tot iemand die het wel mag haar overneemt. Hoort de taak dan bij een ander, of mag de aanvrager de aanname vastleggen? | [taken.md](taken.md), [toegang.md](toegang.md) |
| Twee zoekvelden | Op Opdrachten en Kosten staan twee zoekvelden: dat in de balk zoekt overal op naam, dat op de pagina filtert de lijst, en op Opdrachten ook de tellingen van de weergaven. Blijft dat zo, of krijgt het filter van de lijst een andere vorm? | [ontwerp.md](ontwerp.md), "Navigatie" |
| Lopende opdrachten | De lijst die eerst op de startpagina stond, toonde ook afgesloten opdrachten met een subtotaal, een subtotaal "Als alles doorgaat" voor het potentieel, en kon sorteren op aandacht of op naam. Op Lopende opdrachten onder Geld is dat bewust weggevallen: afgesloten opdrachten staan op Jaarverantwoording, het potentieel op Potentieel, en een keuze van de volgorde is er niet. Is dat genoeg? | ADR 0055 |
| De eigen knop van een onderdeel | Leidt de volgende stap naar een onderdeel met een adres dat iets opent, dan staat de stap in de kop en valt de eigen hoofdknop van het onderdeel weg, zoals "Nieuwe begrotingsregel" of "Nieuwe taak", in plaats van terug te stappen naar een gewone knop. Nu gebeurt dat alleen bij een maand op Afsluiten, dat geen eigen knop heeft; het sluimert. Moet de eigen knop dan als gewone knop blijven staan? | [ontwerp.md](ontwerp.md), "Regels" |
| Een begroting na afronden | Op een afgeronde opdracht is "Nieuwe begrotingsregel" nog de hoofdknop van Begroting: de server staat het wijzigen toe. Dat was al zo, maar het valt nu meer op in de kop. Mag een begroting na afronden nog wijzigen? | [werkstromen.md](werkstromen.md) |
| Wijzigingen in Bouwmeester en Wies | De wijzigingen staan op lokale branches. Mogen ze worden voorgelegd? | [plan.md](plan.md), "Wijzigingen buiten grip" |
| Leesgebeurtenissen na het antwoord | Een inzage wordt nu vastgelegd voordat het antwoord vertrekt, achter hetzelfde slot als elke wijziging. Na het antwoord vastleggen laat een lezer nooit wachten, maar een inzage kan dan ontbreken als het proces op dat moment stopt. Blijft het zo? | [snelheid.md](snelheid.md), [bewijs.md](bewijs.md) |
| Een lege omschrijving van de organisatie | Het taalmodel krijgt "Over de organisatie" uit het gedeelde onderdeel "Hier kom je te werken" van de standaardteksten. Is dat leeg, dan krijgt het model niets en meldt geen scherm dat | [vacatureteksten.md](vacatureteksten.md) |
| Het Grist-document | De import wacht op een download van het document | [import-grist.md](import-grist.md) |
| Keuzes voor Wies | Of de privacyverklaring van Wies de uitwisseling met grip noemt, welk merk collega's uit grip krijgen, wie als actief telt, en hoe vaak er wordt gesynchroniseerd | [wies.md](wies.md) |
| Bestaande interne opdrachten | Een interne opdracht krijgt nu taken ("Maak de begroting", "Start de opdracht"). Bestaande concepten tonen die vanaf de volgende beoordeling | [werkstromen.md](werkstromen.md) |
| Een lijst-inzage en de persoon zelf | Het bekijken van een lijst met mensen wordt als een gebeurtenis vastgelegd en is alleen voor de beheerder zichtbaar. Een persoon ziet het niet onder "wie las mijn gegevens" | [gebeurtenissen.md](gebeurtenissen.md) |

## HR

| Punt | Vraag | Waar |
|---|---|---|
| Gerede en beoogde kandidaat | Wat is het verschil? Het aanvraagformulier legt het niet uit en verwijst naar HR. Grip behandelt de twee gelijk, op een vakje op het formulier na | [vacatureteksten.md](vacatureteksten.md), ADR 0018 |
| Wie beoordeelt een vacaturetekst | Nu kiest de schrijver per tekst een of meer personen. Is er een vaste beoordelaar? | [vacatureteksten.md](vacatureteksten.md), "Een tekst is werk" |
| De afgeleide standaardteksten | Vier teksten zijn afgeleid en niet nagelezen: Frontend developer, Productmanager, Adviseur, Lab manager | [vacatureteksten.md](vacatureteksten.md), "De rollen" |
| Keuzes in de teksten | Bedragen of alleen de schaal, de formulering van het contract, de toon, de naam van de eenheid | [vacatureteksten.md](vacatureteksten.md), "Analyse van de voorbeelden" |
| De sluitingsdatum | Een vacature heeft geen veld voor de datum tot wanneer reageren kan | [vacatureteksten.md](vacatureteksten.md) |
| De volle werkweek | Een vacaturetekst rekent de uren uit met 36 uur per week, vast in de code. Moet dat een instelling zijn? | [vacatureteksten.md](vacatureteksten.md), "Gegevens en open plekken" |
| De motivatie | Een aanvraag vraagt nu een vastgestelde aanleiding en motivatie. Klopt dat met de procedure? | [taken.md](taken.md) |

## De juristen

De zes vragen staan uitgeschreven onderaan [bewijs.md](bewijs.md). Kort:

1. Welk niveau van elektronische handtekening is nodig, binnen het Rijk en daarbuiten?
2. Hoe kwalificeert het bewijs dat grip maakt?
3. Volstaat de verklaring van de ondertekenaar dat hij bevoegd is?
4. Hoe lang mag het bewijs van de aanmelding worden bewaard?
5. Is een gekwalificeerde tijdstempel nodig?
6. Wat is de status van een offerte waarvan het bestand pas na het maken is vastgelegd?

Daarnaast: grip bewaart het aanvraagformulier van een vacature met namen van collega's, en ruimt het op na een termijn die de instantie instelt. Die termijn staat op nul dagen (direct na het sluiten van de vacature), maar het opruimen gebeurt alleen als iemand de opdracht daarvoor draait; een vast ritme is er niet ([ADR 0018](adr/0018-vacatureformulier-en-vacaturetekst.md)). En: hoe lang blijven gebeurtenissen met persoonsgegevens bewaard ([gebeurtenissen.md](gebeurtenissen.md), "Bewaren en wissen").

## De financiële administratie

De zes vragen staan in [ADR 0039](adr/0039-afsluiten-per-maand-aanleveren-per-periode.md). Kort:

1. Verrekenen onderdelen van het Rijk onderling met een factuur, of met een interne doorbelasting?
2. Welke gegevens heeft een factuurverzoek nodig?
3. In welk formaat wil een systeem de regels?
4. Mag de specificatie rollen noemen, of vraagt de opdrachtgever namen?
5. Aan wie en naar welk adres wordt aangeleverd?
6. Hoe komt het factuurnummer terug bij grip?

En een zevende, uit het werk daarna: als een maand na het aanleveren wordt heropend, is een nieuw volledig verzoek dat het eerdere vervangt dan werkbaar, ook als het eerdere al is gefactureerd? Zie [ADR 0047](adr/0047-een-naverrekening-is-een-opgeslagen-verschil-per-factuurperiode.md).

## Het platformteam

| Onderwerp | Wat nodig is | Waar |
|---|---|---|
| FSC | Staan de TLS-modus waarbij de pod het verkeer afhandelt, het koppelen van certificaten en het openzetten van poorten tussen projecten aan op productie? Een vaste hostnaam per component. De limiet op componenten en databases per project. Waar de directory van de groep draait. Of het register van de FSC-images is toegestaan | [plan.md](plan.md), "Risico's" |
| Aanmelden | Voor de eigen client van grip: de adressen waarnaar wordt teruggekeerd, de scopes, het kenmerk van SSO Rijk in het token, en of het verzoek om opnieuw aan te melden wordt doorgegeven. Voor de eerste proef: het geheim van de ontwikkelclient, dat de opdrachtgever zelf in `deploy/local/.env.sso` zet | [sso-rijk.md](sso-rijk.md) |
| Mail | De dienst voor uitgaande mail voor het project. Is de verbinding versleuteld? Mag de afzendernaam die van de organisatie zijn? Komt er terugkoppeling als een bericht niet aankomt? Is het dagmaximum per project in te stellen? | [ADR 0031](adr/0031-tekenlink-per-mail.md), [lokaal.md](lokaal.md), "Mail" |
| Meldingen | Een geheim voor de sleutel, een proces dat de wachtrij verstuurt, en uitgaand verkeer naar de meldingsdiensten van de browsermakers | [meldingen.md](meldingen.md), "Wat het platform moet leveren" |
| Taalmodel | De sleutel en de naam van het model bij VLAM. Welk model er achter zit is niet bevestigd | ADR 0018 |
| Processen | Een instantie draait een webproces, een proces voor verkeer van andere organisaties en een proces voor de wachtrijen. Kan het platform dat per instantie geven? | [lokaal.md](lokaal.md), "Een instantie" |
| Duurzame adressen | Een vast domein per instantie en per corpus, dat een verhuizing overleeft | [architectuur.md](architectuur.md), "Context uit het corpus" |

## De huisstijlcoördinator van het departement

Mag een product van het Rijk een eigen, ingetogen productmerk voeren naast de identiteit van de organisatie? De richtlijn zelf staat achter een login en is niet gelezen. Vast staat alleen dat het Rijkslogo, de huisstijl en het lettertype zijn voorbehouden aan het Rijk en wie in opdracht werkt. Zie [merk.md](merk.md), "Wat mag van de Rijkshuisstijl".

Daarbij: een organisatie buiten de Rijksoverheid die grip draait, krijgt nu nog steeds het lettertype en de kleuren van het Rijk. Dat is niet opgelost.

## Het bouwteam

Wat de herinrichting van november 2026 liet staan, gemeten of gelezen bij de eindcontrole. Elk punt is technisch, maar het kost tijd of verandert een regel, dus het staat hier.

| Punt | Wat er is | Waar |
|---|---|---|
| Oudere verzoeken boven het budget | Op een database van ware grootte blijven drie oudere verzoeken boven 300 ms: `/api/reports/steering` 316 tot 538 ms op Geld, Lopende opdrachten, Omzet, Potentieel, Kosten en Factureren (12 meetpunten, het hoogste Factureren voor de beheerder); `/api/allocations/board` 565 ms op het bord voor een eigenaar, en 308 en 310 ms op Persoon; `/api/kpi` 798 tot 831 ms op Declarabiliteit, waar de pagina voor de beheerder daardoor boven 1000 ms komt. Eén keer boven 300 ms: `/api/vacancies/filled-roles`, `/api/vacancies` en `/api/reports/investment`. De oorzaak is niet nagezocht, en het aantal statements is niet gemeten | [snelheid.md](snelheid.md) |
| Rekenwerk in de frontend dat al bestond | Het open bedrag per periode (aangeleverd min gefactureerd) wordt uitgerekend in `month-close/BillingSheets.tsx`, het vrije deel (100 min inzet) in `allocations/board/model.ts` en `reports/occupancy/model.ts`. Dat hoort in `calc`. De server zou per factuurperiode het open bedrag moeten meegeven, en per persoon en maand het vrije percentage | `CLAUDE.md`, "Rekenen" |
| Pagina's zonder `Page kind` | `PersonPage`, `ClientAssignmentPage` en `RequestQuotePage` bouwen met `PageHeading` en `nldd-simple-section` in plaats van `Page`, terwijl [ontwerp.md](ontwerp.md) ze een Stuk noemt. Of: ze uit die tabel halen | [ontwerp.md](ontwerp.md), "Soorten scherm" |
| De hoofdknop op drie pagina's | Op `ClientPage`, `BillingPage` en `SecurityPage` staat de hoofdknop niet in de kop en niet in de balk. De regels van `CLAUDE.md` en [ontwerp.md](ontwerp.md) zeggen niet hetzelfde over waar de hoofdknop hoort; zolang dat open staat is niet te zeggen of deze drie afwijken | [ontwerp.md](ontwerp.md), "Regels" |
| Het bord vult op breed zijn kader niet | De tabel is 1104 breed in een kader van 1168 (op 1280) en 1328 (op 1440): rechts blijft 63 en 223 px leeg. De breedte staat vast in `ui/timeline/timeline.css`. Team vult zijn kader wel. Bestond al op main | `ui/timeline/timeline.css` |
| Het groepslabel "Open rollen" op 390 | Het label staat links -199 px over een tabelbreedte van 1016: `position: sticky` werkt niet omdat de cel de hele rij beslaat. Bestond al op main | `ui/timeline/timeline.css` |

## De makers van het designsysteem

Voorstellen en fouten die uit het bouwen kwamen. Waar grip eromheen werkt, doet het dat op een plek. De punten uit de herinrichting van november 2026 zijn gezien in versie 0.15.0 en nog niet gemeld. In 0.19.0, 0.23.0, 0.24.0 en 0.29.0 zijn alle punten opnieuw nagelopen. In 0.23.0 is de focus na een keuze in het menu Meer van een werkbalk opgelost, in 0.28.0 de tabstop van de tabbalk als de huidige plek verschuift; de rest bestaat in 0.29.0 nog. Van de acht punten onderaan kwamen er twee in 0.23.0 bij, twee in 0.24.0 en een in 0.29.0; daarna twee uit het werk op main en een uit het ontwikkelportaal, alle drie gezien in 0.29.0.

| Voorstel | Waarom | Waar |
|---|---|---|
| Een variant van de tabbalk met een onderlijn | De tabbalk tekent het gekozen tabblad als gevuld vlak, gelijk aan de hoofdknop. Voor de onderdelen en weergaven (`TabNav`) leent grip daarom de menubalk | [ontwerp.md](ontwerp.md), "Navigatie" |
| Een maat en een toon op een onderdeel van de menubalk | Voor de onderdelen en weergaven in `TabNav`; grip zet nu interne waarden in `index.css`. Sinds 0.23.0 meldt `nldd lint` die twee als `local-variable-no-override` | [ontwerp.md](ontwerp.md), "Navigatie" |
| Een plek voor een getal en een eigen naam in een onderdeel van de tabbalk | Het aantal taken bij Start. Breed staat het in de tekst ("Start (10)"), smal als badge op de hoek van het icoon; een schermlezer hoort het daar alleen in de naam van de balk | ADR 0055 |
| De werkbalk meet opnieuw als de tekst van een tab verandert | Het aantal taken komt na de eerste meting binnen, en dan kapte de balk woorden af. Grip zet het label van het onderdeel daarom opnieuw als attribuut | ADR 0055 |
| De knop "Meer tabs" toont zijn tekst ook op de grote maat | Nu alleen met `variant="icon-and-text"`; een schermlezer hoort de naam wel. Niet omzeild | ADR 0055 |
| Enter in een combobox waarvan de opties net zijn bijgewerkt | `nldd-combo-box` markeert de eerste optie. Vervangt de pagina daarna de opties door wat de server vond, dan kiest Enter niets en wist het veld; pijl omlaag kiest de tweede. Grip ziet het bij het kiezen van een opdrachtgever | `features/organisations/OrganisationPicker.tsx` |
| Geen melding van Lit bij `collapse-anchor` | Elke `nldd-top-title-bar` met `collapse-anchor`, zoals in elk paneel van `FormSheet`, geeft bij het laden een waarschuwing in de console dat er na een update meteen een tweede komt. Geen gevolg gezien | `ui/layout/FormSheet.tsx` |
| `validity` op `nldd-date-field` | De eigenschap ontbreekt in 0.15.0 tot en met 0.29.0, al noemt de documentatie haar. Grip leest `ownValidity()` om een datum die niet bestaat te herkennen | `ui/layout/FormSheet.tsx` |
| Een eerste kolom die blijft staan als een tabel zijwaarts schuift | Op een telefoon schuift een werkblad zijwaarts en verdwijnt de naam van de rij uit beeld. Afsluiten toont op een smal scherm daarom alleen Periode, Stand en Bedrag | ADR 0055 |
| Keuzelijsten met drie opties | `nldd lint` geeft `dropdown-needs-six-options` vijf keer: twee op het bord (Per persoon, Iedereen), twee op Begroting en een op Afsluiten. Het designsysteem wil bij een paar opties een segmentbesturing of radioknoppen. Grip laat ze staan; niet nagezocht welke de twee op Begroting en de ene op Afsluiten zijn | `ui/layout/FilterSelect.tsx` |
| De schil van een pagina zonder sectie | `page-content-goes-in-section` komt op elke pagina, omdat de wrapper `div#inhoud` direct in `nldd-page` staat en de sectie bevat. Het is de schil, niet een pagina. Hint, geen fout; niet omzeild | `layout/AppShell.tsx` |
| De annotatie in de teksteditor zonder teller | Elke gemarkeerde plek krijgt een klein cijfer dat niet uit kan. Grip gebruikt de annotaties daarom niet meer en tekent open plekken en gegevens met een eigen uitbreiding op de editor | [vacatureteksten.md](vacatureteksten.md), "Gegevens en open plekken" |
| Een vast, niet te bewerken stukje in de teksteditor met een eigen sleutel | De editor kent dit alleen voor een vermelding van een persoon. Grip tekent een gegeven (`{schaal}`) zelf als waarde | [vacatureteksten.md](vacatureteksten.md), "Gegevens en open plekken" |
| `color` op `nldd-icon-cell` kleurt ook het icoon | Van 0.23.0 tot en met 0.29.0 tekent de cel het icoon uit `icon` in de tekstkleur, wat `color` ook zegt: de cel zet `color` maar niet `--context-content-color`, en `nldd-icon` leest sinds 0.23.0 alleen die. Een waarschuwing en het pijltje van een rij verloren zo hun kleur. Grip zet het icoon daarom zelf in de cel, met de kleur erop | `ui/Icon.tsx` |
| Een eigenschap die `undefined` wordt, haalt het attribuut weg | Laat React een eigenschap weg, dan zet het die op `undefined`, en veel componenten schrijven dan het attribuut `"undefined"`. Sinds 0.23.0 doet `icon` op `nldd-tab-bar-item` dat ook; met het icoon in het slot gaf dat op elke pagina `slot-attribute-no-effect`. Grip geeft Start in de balk onderin daarom een leeg icoon in plaats van geen | `layout/MainNavigation.tsx` |
| Een paneel dat opent vanuit een menu geeft de focus terug aan de knop van het menu | Sinds 0.24.0 knippert een gekozen item voordat het menu sluit, en `select` komt meteen. Een paneel of dialoog die bij `select` opent, onthoudt het item als plek voor de focus; als het sluit, is het menu dicht en valt de focus op de pagina. Het menu Meer van een werkbalk geeft de focus sinds 0.26.2 zelf terug; een menu onder een knop of icoonknop doet dat in 0.29.0 nog niet. Grip voert een keuze in zo'n menu daarom pas uit als het menu dicht is, ongeveer 0,3 s later | `components/nldd/events.ts` (`useMenuSelect`) |
| axe beoordeelt het contrast in een open menu | Sinds 0.24.0 vervaagt een menu aan de rand met een masker op zijn lijst. axe ziet daardoor bij bijna elk item een overlap en beslist het contrast niet; `check-a11y` telt die elementen bij wat met de hand moet (van 2434 naar 4421). De kleuren zijn gelijk aan 0.23.0. Niet omzeild | `frontend/scripts/check-a11y.mjs` |
| `only` op een balk van `nldd-bar-split-view` onder een naam zonder "on" vooraan | Sinds 0.28.0 staat wat in een paneel stond direct in de split view, met `above`, `below` of `only` op het element zelf. React schrijft op een gewoon element geen attribuut dat met "on" begint; het houdt het voor een event. Grip zet op de balk onderin daarom `below="sm"`, dat hetzelfde zegt | `layout/AppShell.tsx` |
| De plek van `nldd-status-bar` in een applicatie met `nldd-bar-split-view`, en `status-bar-goes-above-top-bar` ook voor een werkbalk in die split view | De documentatie en de controle noemen alleen `nldd-top-navigation-bar` en `nldd-top-title-bar`, en het patroon voor de opbouw van een pagina (`page-structure`) alleen de vorm van een website, in het slot `header` van `nldd-page`. Dat de balk in een applicatie als eerste kind van de split view een eigen slot krijgt, zoals `slot="status-bar"`, volgt alleen uit een voorbeeld in de beschrijving van `nldd-bar-split-view`. In 0.29.0 zoekt de controle in een dev-build nog alleen naar die twee titelbalken: een statusbalk onder een `nldd-toolbar` krijgt geen waarschuwing | `layout/AppShell.tsx` |
| Een lange `details` op `nldd-menu-item` laat de tekst ruimte | De tekst groeit vanaf nul (`flex: 1 1 0`), `details` begint op zijn volle breedte (`flex: 0 1 auto`) en breekt pas als de tekst geen breedte meer heeft. In 0.29.0 gemeten met een naam als tekst en een functie van drie woorden als `details`: in een item van 300 px breed krijgt de naam 0 px en staat ze letter voor letter onder elkaar; op 358 px krijgt ze 53 px. Grip zet de functie daarom achter de naam in `text`, dat gewoon afbreekt, en houdt `details` kort | `layout/ExampleMode.tsx` |
| De kopieerknop van `nldd-code-viewer` laat een lange eerste regel leesbaar | In 0.29.0 staat de knop midden op de eerste regel en scrolt het blok eronder door; op 390 staat hij over de tekst van een lange eerste regel. Onder 0.8.96 hield de regel ruimte vrij voor de knop. Gezien in het ontwikkelportaal, op Lokale omgeving; niet omzeild | `ontwikkelportaal/src/lib/rehype-code-viewer.mjs` |

## Gebruikers

Niemand die het werk doet heeft grip gebruikt. De inrichting met vijf plekken rust op persona's die zijn verzonnen en op frequenties die zijn afgeleid uit het domein en de taken ([ADR 0055](adr/0055-vijf-plekken-en-een-rustig-geopend-ding.md)). Vragen voor drie tot vijf mensen per rol:

- Landt iemand vaker op een opdracht dan dat hij tussen haar onderdelen wisselt? Dat beslist of de wisselbalk nodig blijft.
- Welke pagina opent iemand als eerste, en zegt Start dan genoeg?
- Zoekt een planner het bord onder Mensen?
- Vinden eigenaren en wie het geld leest het geld over opdrachten heen onder Geld, nu het niet meer op Start staat? Mist iemand de tabel per opdracht op Start?
- Klopt de invoer van Begroting bij een mondeling akkoord, als er al werk loopt en er bedragen zijn?
- Vindt wie alleen het toetsenbord gebruikt de andere plekken met de pijlen? De balk heeft één tabstop.

En breder: is de zin op de landing van een opdracht ("Jij: ...", "Wacht op ...") genoeg om te weten wat je moet doen, zonder uitleg?

## Wat alleen in het echt te beproeven is

Dit is geen vraag aan iemand, maar het staat hier omdat het niets zegt over hoe goed het werkt tot het is gedaan.

| Wat | Waarom lokaal niet |
|---|---|
| Een aanmelding via SSO Rijk, en opnieuw aanmelden bij een besluit | Er is een geheim van het platform voor nodig |
| Een melding op een echte telefoon | Een browser zonder venster heeft geen meldingsdienst |
| Mail in een echte postbus, en wat spamfilters ermee doen | Lokaal vangt een mailvanger alles op |
| Een passkey op een echt apparaat, in Safari en Firefox | Beproefd met een nagebootste sleutel in een browser |
| Twee instanties van twee organisaties | Lokaal draaien beide op een machine |
| VLAM | Er is geen sleutel |
| Het echte corpus | Lokaal staat er een Bouwmeester met fictieve nodes |
