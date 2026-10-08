# Domein

Deze specificatie is overgenomen uit de basisbeschrijving van het Grist-document dat grip vervangt, aangevuld met wat het plan voor federatie, tekenen en verrekening toevoegt. Alle opdrachtnamen, bedragen en tarieven in de voorbeelden zijn fictief.

## Wat Grist deed en waar het knelde

Het Grist-document plant en volgt opdrachten: de begroting per opdracht, wie erop werkt tegen welk tarief, externe kosten en welke begroting die dekt, en een declarabiliteits-KPI per persoon. De tabellen heten Opdracht, Begroting, Inzet, Team, Tarievenleaflet, Kosten, Factuur, Kostendekking en KPI per persoon. Het dashboard "Stand van zaken" toont per opdracht Begroot, Uitputting en Beschikbaar.

Vier knelpunten:

1. **Delen is alles of niets.** Alles staat in een document, terwijl opdrachteigenaren, teamleden en managers elk een ander beeld nodig hebben.
2. **Schaal is geen data.** De schaal van iemand staat in vrije tekst ("Schaal 11, maar rekent met 12"). Begrotingsregels verstoppen rol, FTE, schaal en startdatum in hun omschrijving ("Developer #2 (vanaf Q2, schaal 10/11)").
3. **Maar een jaar.** Er is een tarieventabel en opdrachten zijn per jaar geknipt ("Opdracht Alfa 2026"). Inzet die over 31 december loopt is niet te prijzen.
4. **De offerte is handwerk.** De begroting is de basis, maar de offerte ontstaat buiten de tool.

## Begrippen

UI-termen zijn Nederlands; code en schema gebruiken de Engelse naam.

| UI-term | Codenaam | Betekenis |
|---|---|---|
| Opdracht | `assignment` | De eenheid waarvoor een offerte wordt gemaakt |
| Begrotingsregel | `budget_line` | Een regel van de begroting van een opdracht: een rol (personeel) of een vaste post |
| Begroot | `budgeted` | Gepland bedrag |
| Gerealiseerd | `realised` | Inzet van afgesloten maanden, tegen de vastgestelde inzet. Bij kosten: het deel dat op gerealiseerde factuurregels rust |
| Nog gepland | `planned` | Inzet van open maanden, tegen de geplande inzet. De rapportages gebruiken hetzelfde woord |
| Kosten | `costs` | Externe kosten die een begrotingsregel dekt (R7), gesplitst in gerealiseerd en ingeschat |
| Verwacht totaal | `expected_total` | Gerealiseerd plus nog gepland plus kosten: wat de regel naar verwachting kost als alles loopt zoals gepland. Dit is het bedrag dat R9 `used` noemt |
| Afwijking | `variance` | Begroot min verwacht totaal, in euro en als percentage van begroot. Positief is ruimte, negatief is een overschrijding |
| Uitputting | `realised_pct` | Het deel van de begroting dat al is gerealiseerd (inzet en kosten), als percentage. Grist gebruikte het woord voor het vastgelegde bedrag; dat heet in grip verwacht totaal |
| Investeerruimte in geld (voorlopig) | `room` | Wat de organisatie in een jaar verdient boven wat zij moet verdienen: de verwachte omzet van externe opdrachten met akkoord (gerealiseerd plus nog gepland, ook op mondeling akkoord), min de som van de declarabiliteitstargets, min ongedekte kosten, min wat interne opdrachten volgens hun begroting gebruiken. Negatief is een tekort. De pijplijn telt niet mee en staat er apart bij. De definitie is nog niet bevestigd; het scherm zegt daarom wat er geteld is |
| Investeerruimte in tijd (voorlopig) | `free capacity` | De capaciteit die deze maand en de drie maanden erna niet is ingepland, in FTE en gewaardeerd tegen het inzettarief van elke persoon in die maand. Iedereen telt als voltijds, tot er een deeltijdfactor per persoon is |
| Peildatum van de stand | `reference_month` | De laatst afgesloten maand van een opdracht. Tot en met die maand zijn bedragen werkelijk, daarna planning |
| Aangeleverd | `delivered` | De factuurgegevens van een afgesloten maand zijn geëxporteerd voor de financiële administratie. Het is geen factuur |
| Nog aan te leveren | `to_deliver` | De vastgestelde inzet van afgesloten maanden, geprijsd, min wat is aangeleverd |
| Gefactureerd | `invoiced` | Er is een factuur verstuurd. Grip weet dat alleen doordat iemand het heeft vastgelegd; tot dan heet geen bedrag gefactureerd |
| Nog te factureren | `to_invoice` | Aangeleverd min gefactureerd: aangeleverd, en in grip nog geen factuur vastgelegd |
| Potentiële opdracht | `phase: potential` | Een opdracht zonder akkoord van de opdrachtgever. Haar bedragen zijn pijplijn en tellen nooit mee in het lopende werk; inzet erop is onder voorbehoud |
| Team, medewerker | `person` | Iemand die kan worden ingezet |
| Inzetschaal | `billing_scale` | De schaal waartegen iemand wordt gedeclareerd |
| Categorie | `rate_category` | Tariefband A t/m E, elk voor twee schalen |
| Maandtarief | `monthly_rate` | Tarief per FTE per maand voor een categorie in een jaar |
| Tarievenleaflet | `rate_card` | Alle tarieven van een kalenderjaar |
| Inzet | `allocation` | Een persoon op een begrotingsregel, voor een periode, tegen een FTE-percentage |
| Kostenpost | `cost_item` | Externe kosten, bijvoorbeeld een hostingcontract |
| Factuurregel op een kostenpost | `invoice_line` | Een bedrag op een kostenpost, gerealiseerd of ingeschat. Dit is de inkoopkant |
| Realisatie, inschatting | `actual`, `estimate` | Soort factuurregel |
| Kostendekking | `cost_coverage` | Welke begrotingsregel welk deel van een kostenpost dekt |
| Target KPI % declarabel | `billability_target` | Deel van iemands jaar dat declarabel moet zijn |
| Offerte | `quote` | Document dat uit de begroting van een opdracht wordt gemaakt. Na het maken wijzigt het niet meer |
| Offerte maken | `issue_quote` | De begroting vastleggen als offerte. In de code heet dat uitgeven (`issued`); voor de gebruiker is het maken |
| Kenmerk | `reference` | Het nummer waarmee mensen een offerte aanduiden, zoals "DG-2026-0007": voorvoegsel van de organisatie, jaar en een volgnummer per jaar dat nooit opnieuw wordt gebruikt. Het staat in de vastgelegde inhoud en valt dus onder het echtheidskenmerk. De URI blijft het kenmerk voor systemen |
| Uw kenmerk | `client_reference` | Het eigen kenmerk van de opdrachtgever, zoals een zaak- of ordernummer. Optioneel, bij het maken van de offerte |
| Echtheidskenmerk | `snapshot_hash` | Een code die uit de inhoud van een offerte is berekend (de hash). Dezelfde code staat in het akkoord, zodat vaststaat dat er voor precies deze offerte is getekend. Op scherm en document heet het echtheidskenmerk, nooit hash |
| Tekenlink | `quote_invitation` | De link waarmee één uitgenodigde persoon een offerte opent en tekent. Werkt 30 dagen, is in te trekken en te verlengen |
| Akkoord | `quote_acceptance` | De vastlegging dat de opdrachtgever een offerte heeft aanvaard |
| Interne goedkeuring | `quote_approval` | De goedkeuring van een gemaakte offerte binnen de eigen organisatie, voordat ze wordt aangeboden. Per instantie in te stellen: nooit, altijd of vanaf een bedrag. Gaat over precies de bytes van die offerte en blijft intern |
| Terugsturen | `sent_back` | De goedkeurder keurt een offerte niet goed en zegt waarom. De offerte verandert niet; de maker maakt een nieuwe |
| Instelling van de instantie | `instance_setting` | Een regel van de organisatie die de beheerder wijzigt, zoals wanneer interne goedkeuring nodig is |
| Maandafsluiting | `month_close` | De vastgestelde werkelijke inzet van een maand |
| Factuurgegevens, aanlevering | `billing_export` | Wat per afgesloten maand naar de financiële administratie gaat. Een export is een aanlevering |
| Factuur | `outgoing_invoice` | De vastlegging dat een factuur aan de opdrachtgever is verstuurd, voor een of meer aanleveringen: nummer, datum, bedrag, wie het vastlegde en de bron (met de hand of het financiële systeem) |
| Inhuur | `hire` | Kostprijs en marge van een ingehuurde persoon |
| Recht in grip | `function` | Wat iemand in grip mag bovenop de eigen relaties: beheerder, planner, lezer, aanvrager, tekenbevoegde, interne goedkeurder van offertes. De code zegt functie, het scherm zegt recht |
| Functie | `function_title` | De functie van iemand in de organisatie of op een vacature: de functietitel. Niet het recht in grip |
| Functiegroep | `function_group` | De groep uit het Functiegebouw Rijk waar een functie onder valt |
| Bijlage | `stored_document` | Een bestand dat bij precies een object hoort, zoals de ontvangen factuur bij een factuurregel of de getekende offerte bij een akkoord |
| Vacature | `vacancy` | Een open rol op een begrotingsregel, met het soort vacature, het soort contract, de stappen van de procedure en een vacaturetekst |
| Stand van zaken | `status_overview` | Dashboard per opdracht |

"Factuur" betekent in Grist een regel aan de inkoopkant, op een kostenpost. Het is geen verkoopfactuur. In grip heet die een factuurregel op een kostenpost. Wat grip richting de opdrachtgever oplevert heet factuurgegevens.

Grip verstuurt geen facturen. Het kent drie feiten met elk een eigen woord: aangeleverd (de export bestaat), gefactureerd (iemand heeft vastgelegd dat de factuur is verstuurd) en betaald (dat weet grip niet). Zie ADR 0023.

## Datamodel

Afspraken:

- Geld in hele centen, nooit floating point.
- FTE en percentages als exacte decimalen, datums als datum.
- Een waarde die hieronder "afgeleid" heet wordt berekend met de rekenregels en niet opgeslagen, zodat ze niet kan afwijken.
- De uitzondering is een uitgegeven offerte. Haar inhoud wordt bij uitgifte in de canonieke vorm gezet (de termen van het contract, als canonieke JSON) en als bytes opgeslagen. De hash van de offerte is de SHA-256 over die bytes, en is overal dezelfde (ADR 0020).

### Tarieven

| Entiteit | Velden | Bron in Grist |
|---|---|---|
| `rate_card` | `year` (PK), `status` (`draft`, `active`, `closed`) | nieuw |
| `rate_band` | `year`, `category` (A t/m E), `monthly_rate`; uniek op (`year`, `category`) | Tarievenleaflet |
| `scale_band` | `year`, `scale` (int), `category`; uniek op (`year`, `scale`) | Tarievenleaflet |

Tarieven en de koppeling van schaal naar categorie zijn allebei per jaar, dus elk jaar kan een van beide veranderen.

### Mensen

| Entiteit | Velden | Bron in Grist |
|---|---|---|
| `person` | `name`, `manager_id` naar person, `digi_gilde` (bool), `active` | Team |
| `person_scale` | `person_id`, `valid_from`, `valid_to` (optioneel), `billing_scale` | Team.Notitie (vrije tekst) |
| `billability_target` | `person_id`, `year`, `target_pct` | Team, KPI per persoon |
| `hire` | kostprijs en marge bij een ingehuurde persoon | nieuw |

De salarisschaal wordt niet opgeslagen. Het kenmerk `digi_gilde` heeft voor zover bekend geen invloed op een berekening.

### Opdrachten en begroting

| Entiteit | Velden | Bron in Grist |
|---|---|---|
| `assignment` | `name`, `status`, `quote_date`, `client_contact`, `quoted_amount`, `start_date`, `end_date`, `notes` | Opdracht |
| | URI, soort (extern, intern), opdrachtgever en opdrachtnemer als organisatie, URI van de bovenliggende opdracht, `context_refs` (node-URI's), en met welke instantie de opdracht is gedeeld (ontstaat uit een uitwisseling, wordt niet ingesteld) | nieuw |
| `assignment_role` | persoon, opdracht, eigenaar of manager | Opdracht (eigenaar) |
| `budget_line` | `assignment_id`, `description`, `kind` (`personnel`, `fixed`), `position` | Begroting |
| | personeel: `role`, `fte`, `rate_category`, `start_date`, `end_date`; `budgeted` afgeleid | uit de omschrijving gehaald |
| | vast: `amount`, `year`; `budgeted` = `amount` | Begroot |
| `allocation` | `person_id`, `budget_line_id` (alleen personeelsregels), `start_date`, `end_date`, `fte_pct` | Inzet |
| `quote` | `assignment_id`, `issued_at`, `issued_by`, `canonical` (de canonieke vorm als bytes: regels, tarieven en totalen zoals uitgegeven), de hash daarover, `total` | nieuw |
| `quote_offer` | offerte, kanaal (grip van de opdrachtgever, tekenlink, document), wanneer, door wie, aan wie | nieuw |
| `quote_acceptance` | hash van de offerte, ondertekenaar, organisatie, tijdstip, vorm, handtekening of bestand | nieuw |
| `month_close` | opdracht, maand, vastgestelde inzet per persoon, vastgesteld door | nieuw |
| `billing_export` | periode, regels, exportrun | nieuw |
| `vacancy` | begrotingsregel, profiel, status, kanaal (intern, federatief, werving), stappen | nieuw |

Statussen van een opdracht: concept, aangevraagd, offerte gemaakt, akkoord, in uitvoering, afgerond, verantwoord. Daarnaast afgewezen en geannuleerd.

### Kosten

| Entiteit | Velden | Bron in Grist |
|---|---|---|
| `cost_item` | `description`, `budgeted`; `forecast` en `covered` afgeleid | Kosten |
| `invoice_line` | `reference` (bijvoorbeeld "HOST-26-01"), `description`, `kind` (`actual`, `estimate`), `amount`, `cost_item_id`, `period` | Factuur; `period` is nieuw |
| `cost_coverage` | `cost_item_id`, `budget_line_id`, `pct`; `amount` afgeleid | Kostendekking |

Een kostenpost hoort niet bij een opdracht. De dekking kan over begrotingsregels van meerdere opdrachten verdeeld zijn.

### Federatie en controle

| Entiteit | Inhoud |
|---|---|
| `peer` | Een andere instantie of een corpus: peer-id, organisatie, contract |
| `federation_outbox` | Uitgaande berichten, verstuurd door een worker |
| `federation_inbox` | Inkomende berichten, idempotent op bericht-UUID |
| `audit_log` | Wie, wanneer, oude en nieuwe waarde |

## Rekenregels

Een maand is een kalendermaand. De voorbeelden gebruiken fictieve bedragen; bij de import worden ze vervangen door gevallen uit de echte Grist-export, en die worden de unittests.

| # | Regel |
|---|---|
| R1 | `rate(person, month)` = `monthly_rate(year, category)`, waarbij `category` = `scale_band(year, billing_scale(person, month))` |
| R2 | Inzet per maand = `fte_pct × rate(person, month) × month_fraction`. `month_fraction` is 1 voor een hele maand |
| R3 | Inzetbedrag = som van R2 over de maanden in [`start_date`, `end_date`] |
| R4 | `budgeted` van een personeelsregel = som over de maanden van `fte × monthly_rate(year, rate_category)` |
| R5 | `budgeted` van een vaste regel = `amount` |
| R6 | `forecast` (prognose realisatie) van een kostenpost = som van de factuurregels, realisatie en inschatting |
| R7 | Dekkingsbedrag `amount` = `pct × cost_item.forecast` |
| R8 | `covered` (dekking) van een kostenpost = som van de dekkingsbedragen. De som van `pct` per kostenpost mag niet boven 100% uitkomen; toon het ongedekte restant |
| R9 | `used` van een begrotingsregel = som van de inzetbedragen + som van de dekkingsbedragen |
| R10 | `available` = `budgeted - used`. Negatief betekent overschrijding en moet opvallen |
| R11 | Totalen per opdracht = som over de begrotingsregels |
| R12 | KPI-realisatie(persoon, jaar) = som van de inzetbedragen van die persoon in de maanden van dat jaar |
| R13 | KPI-target(persoon, jaar) = `target_pct ×` som over de maanden van het jaar van `rate(person, month)` |
| R14 | Signaleer inzet van iemand die in een andere categorie declareert dan de begrotingsregel aanneemt: die regel gaat onder- of overschrijden |

Reken in exacte decimalen en rond pas af op centen bij het tonen of vastleggen van een totaal.

### Rekenvoorbeelden

Alle voorbeelden gaan uit van categorie D met een maandtarief van € 18.000 in 2026.

| Regel | Geval | Uitkomst |
|---|---|---|
| R4 | Productmanager, 0,8 FTE, categorie D, heel 2026: 0,8 × 12 × € 18.000 | € 172.800 |
| R7 | 30% van een hostingcontract met een prognose van € 15.000 | € 4.500 |
| R12 | 12 maanden 100% inzet, categorie D | € 216.000 |
| R13 | Target 90%: 90% × 12 × € 18.000 | € 194.400 |

### Maandafsluiting

De regels hierboven rekenen met geplande inzet. Verrekening gaat per maand op werkelijke inzet. De geplande inzet staat klaar als voorstel; de manager van de opdracht past afwijkingen aan en sluit de maand af. De vastgestelde inzet in `month_close` voedt de uitputting en de factuurgegevens.

Voor uitputting (R9) en KPI-realisatie (R12) geldt:

- Een afgesloten maand telt met de vastgestelde inzet. Het vastgestelde percentage geldt voor de hele maand, zonder verdere verrekening naar kalenderdagen; een latere start of een eerder einde zit in het percentage dat de manager vaststelt.
- Een open maand telt met de geplande inzet, geprijsd volgens R2.
- Overzichten tonen de twee delen apart: gerealiseerd (afgesloten maanden) en prognose (open maanden).

## Meerdere jaren

- Er is een tarievenkaart per kalenderjaar. Een nieuw jaar begint als conceptkopie van het vorige.
- Een gesloten jaar is vergrendeld. Wijzigen vraagt het recht beheerder en laat een auditregel achter.
- Opdrachten, begrotingsregels en inzet hebben datums en mogen over 31 december lopen. Bedragen worden per maand gesplitst en geprijsd met het jaar van die maand (R1 t/m R4).
- Een maand zonder actieve tarievenkaart is een validatiefout, nooit stilletjes nul.
- De schaalhistorie per persoon (`person_scale.valid_from`) zorgt dat een promotie halverwege het jaar goed geprijsd wordt.
- Elk overzicht heeft een jaarfilter plus een optie "hele looptijd". Standaard staat het huidige jaar.
- Een vaste begrotingsregel geldt voor een jaar. Loopt een vaste post over meerdere jaren, dan is er een regel per jaar.

## Schermen

- **Stand van zaken**: per opdracht Begroot, Gerealiseerd, Nog gepland, Kosten, Verwacht totaal, Afwijking en Uitputting, met de peildatum van de stand en een jaarfilter. Potentiële opdrachten staan apart van lopend werk, met een eigen subtotaal. Het tabblad Financieel van een opdracht toont dezelfde cijfers per begrotingsregel, de bedragen erachter, het verloop per maand en de aandachtspunten; bemensing staat op een eigen tabblad zonder bedragen.
- **Opdrachten** met de begrotingseditor per opdracht.
- **Inzet**: per persoon en per begrotingsregel, met de waarschuwingen van R14.
- **Kosten en facturen**, met de dekking per kostenpost.
- **Tarieven**: tarievenkaarten per jaar.
- **Team** en **KPI per persoon**, afgeschermd volgens [toegang.md](toegang.md).
- **Offerte**: gegenereerd uit de begrotingsregels. Per regel omschrijving, FTE, periode, categorie, maandtarief en bedrag; subtotalen per jaar; totaal.

## Migratie vanuit Grist

1. Bevries een bron: download het document als SQLite (`GET /api/docs/{docId}/download`) en bewaar het bij de importrun.
2. Lees de kolom-metadata (`GET /api/docs/{docId}/tables/{tableId}/columns`) en controleer de formules achter R2, R6 en R7 voordat de rekenmodule definitief is.
3. Haal de records op (`GET /api/docs/{docId}/tables/{tableId}/records`) en zet ze om volgens de kolom "Bron in Grist" hierboven.
4. Zet vrije tekst om naar velden: schalen uit Team.Notitie, en rol, FTE, schaal en start uit de omschrijvingen van begrotingsregels. Lever elke omzetting als lijst die een mens bevestigt. De import gokt niet.
5. Laad de Tarievenleaflet als tarievenkaart van een jaar. Welk jaar wordt bij de import bevestigd; de basisbeschrijving gaat uit van 2026.
6. Sluit aan: elk totaal per opdracht, begrotingsregel, kostenpost en KPI is tot op de euro gelijk aan de Grist-waarde uit dezelfde momentopname.
7. De import is herhaalbaar tot de overstap. Daarna wordt het Grist-document alleen-lezen.

Vorm van het aansluitrapport, met fictieve cijfers:

| Opdracht | Begroot | Uitputting | Beschikbaar |
|---|---:|---:|---:|
| Opdracht Alfa 2026 | € 1.250.000 | € 1.100.000 | € 150.000 |
| Opdracht Beta 2026 | € 480.000 | € 452.500 | € 27.500 |

Opdrachten die in Grist per jaar zijn geknipt blijven bij de import zoals ze zijn. Nieuwe opdrachten mogen meerdere jaren beslaan.

## Acceptatiecriteria

- Een import van een Grist-momentopname reproduceert elk totaal per opdracht, begrotingsregel, kostenpost en KPI tot op de euro.
- Inzet van 2026-07-01 tot 2027-06-30 wordt voor de maanden in 2026 tegen de tarieven van 2026 geprijsd en voor de maanden in 2027 tegen die van 2027.
- Een maand prijzen zonder actieve tarievenkaart geeft een duidelijke foutmelding.
- De manager van een opdracht kan de KPI van een ander niet opvragen, niet via de UI en niet via de API. Tests op API-niveau dekken dat af.
- Een gegenereerde offerte telt op tot de begroting van de opdracht. Een uitgegeven offerte verandert niet als tarieven worden aangepast.
- Een offerte heeft een hash: op het document, in een akkoord van elke vorm en in het bericht tussen instanties staat dezelfde waarde, de SHA-256 over de opgeslagen canonieke vorm.
- Een offerte die instantie B uitgeeft en instantie A ontvangt heeft aan beide kanten dezelfde bytes en dezelfde hash.
- Na het uitgeven van een offerte is er niets verstuurd. Een offerte gaat naar de opdrachtgever wanneer ze wordt aangeboden, via het kanaal dat dan wordt gekozen.
- Unittests dekken R1 t/m R14, inclusief de rekenvoorbeelden.

## Open vragen die de import beantwoordt

Elke vraag heeft een voorlopige keuze. De bouwer houdt die aan tot de Grist-formules anders uitwijzen.

| Vraag | Voorlopige keuze | Raakt |
|---|---|---|
| Hoe worden gedeeltelijke maanden geprijsd? | Naar rato van kalenderdagen | R2 |
| Gaat het dekkingspercentage over de prognose of over het begrote bedrag? | Prognose | R7 |
| Telt de prognose van een kostenpost realisatie en inschatting bij elkaar op? | Ja | R6 |
| Is Begroot op personeelsregels in Grist ingevoerd of berekend, en wijken regels af van FTE × tarief? | Berekend; afwijkingen opsommen tijdens de import | R4 |
| Is het bedrag op een opdracht het afgesproken offertebedrag of afgeleid uit de begroting? | Afgesproken bedrag, ingevoerd; toon het verschil met de begroting | `quoted_amount` |
| Voor welk jaar geldt de huidige Tarievenleaflet? | 2026 | `rate_card` |

## Open vragen die de import niet beantwoordt

- Welke vorm heeft de export van factuurgegevens? Het financiële systeem en zijn formaat zijn niet bekend.
- Welk formaat en sjabloon krijgt de offerte? De basisbeschrijving stelt een pdf uit een HTML-sjabloon voor.
