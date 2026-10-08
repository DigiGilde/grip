# Taken

Dit document beschrijft de takenlaag van grip: welke feiten er zijn, welk plan wordt meegeleverd, en hoe de begrippen zich verhouden tot zaakgericht werken. Het besluit en de redenen staan in [ADR 0024](adr/0024-taken-feiten-en-het-plan.md).

## In het kort

- Een **zaak** is een opdracht of een vacature.
- Een **feit** is iets wat grip over een zaak weet uit de eigen gegevens.
- Een **taak** ontstaat als haar voorwaarden gelden en sluit als haar feit geldt.
- Het **plan** is de lijst sjablonen waaruit taken ontstaan.

Een taak afvinken verandert niets aan de zaak. Het werk gebeurt op het scherm waar de taak naar verwijst, en de taak sluit daarna vanzelf.

## Waar je taken ziet

| Plek | Wat er staat |
|---|---|
| Taken, in de navigatie | Je eigen open taken, in de groepen te laat, deze week en later. Het getal in de navigatie is het aantal open taken dat van jou is. |
| Taken, weergave Bord | Alle taken van de zaken die je mag inzien, in de kolommen te doen, bezig, wacht op een ander en klaar. Te filteren op opdracht of vacature, op persoon en op spoor. |
| Tabblad Taken van een opdracht of vacature | De stand per spoor in één regel, en de taken per spoor. Wie de zaak mag bewerken, kan een eigen taak toevoegen. |

Een taak verplaats je met het menu aan het eind van de rij of op de kaart. Slepen is niet nodig.

## Statussen

| Status | Betekenis |
|---|---|
| Te doen | Nog niet begonnen |
| Bezig | Iemand werkt eraan |
| Wacht op een ander | Het werk ligt bij een ander; de taak noemt bij wie |
| Klaar | Gesloten, door het feit of door een mens |
| Vervallen | Niet meer van toepassing, bijvoorbeeld omdat de opdracht is geannuleerd |

## Voor wie een taak is

Een sjabloon noemt een rol. Bij het lezen bepaalt grip wie die rol heeft.

| Rol in het plan | Wie |
|---|---|
| `owner` | De eigenaar van de opdracht |
| `manager` | De eigenaar of een manager van de opdracht |
| `planner`, `beheerder`, `tekenbevoegde`, `aanvrager`, `offertegoedkeurder` | Iedereen met dat recht in grip |
| `maker` | Wie om goedkeuring van de offerte vroeg; anders de eigenaar van de opdracht |
| `requester` | De aanvrager van de vacature |
| `decision:hr_advice`, `decision:control_advice`, `decision:approval` | Wie op de vacature voor dat advies of akkoord is genoemd; voor het akkoord anders degene aan wie de aanvraag is gericht. Heeft die persoon geen account, dan is de taak van de aanvrager en staat ze op "wacht op een ander". |

Wie een zaak mag bewerken, kan een taak overdragen aan een persoon. Dat blijft staan tot iemand het terugzet.

## De catalogus

Een plan kan alleen deze namen gebruiken. De catalogus staat in `backend/grip/tasks/catalogue.py`; de feiten worden afgeleid in `backend/grip/tasks/cases.py`.

### Onderwerpen

Een sjabloon is voor de zaak als geheel, of herhaalt zich per onderwerp.

| Onderwerp | Eén taak per |
|---|---|
| `case` | Zaak |
| `quote_round` | Offerteronde; een afwijzing opent een nieuwe ronde |
| `rejected_quote` | Afgewezen offerte |
| `received_quote` | Offerte die deze instantie als opdrachtgever ontving |
| `quote_approval` | Verzoek om interne goedkeuring van een offerte |
| `sent_back_quote` | Offerte die bij de interne goedkeuring is teruggestuurd |
| `correction_month` | Aangeleverde maand waarvan de prijs daarna is veranderd (nog zonder bron, zie onder) |
| `open_role` | Begrotingsregel met personeel die nog niet is ingevuld |
| `month_to_close` | Verstreken maand met inzet die nog niet is afgesloten |
| `closed_month` | Afgesloten maand |

### Feiten over een opdracht

| Feit | Geldt als |
|---|---|
| `external` | De opdracht een externe opdrachtgever heeft |
| `contractor` | Deze instantie de opdracht uitvoert |
| `client` | Deze instantie de opdrachtgever is |
| `potential` | De opdracht nog een potentiële opdracht is |
| `agreed` | De offerte is aanvaard; blijft gelden als de opdracht verder is |
| `started` | De opdracht in uitvoering is, of verder |
| `completed` | De opdracht is afgerond |
| `closed` | De opdracht is verantwoord, afgewezen of geannuleerd |
| `budget_has_line` | De begroting een regel heeft |
| `budget_has_personnel_line` | De begroting een regel met personeel heeft |
| `staffing_in_view` | Er akkoord is, mondeling of schriftelijk, of er een offerte is uitgegeven |
| `may_close_months` | De status het afsluiten van maanden toelaat |
| `may_bill` | De status het aanleveren van factuurgegevens toelaat |
| `final_report_issued` | Het eindrapport is uitgegeven |

### Feiten over een onderwerp

| Feit | Onderwerp | Geldt als |
|---|---|---|
| `quote_issued` | Offerteronde | In deze ronde een offerte is uitgegeven |
| `quote_offered` | Offerteronde | Die offerte is aangeboden |
| `quote_accepted` | Offerteronde | De opdrachtgever akkoord heeft gegeven |
| `quote_superseded` | Afgewezen offerte | Er daarna een nieuwe offerte is uitgegeven |
| `quote_decided` | Ontvangen offerte | Er akkoord is gegeven of is afgewezen |
| `approval_decided` | Verzoek om goedkeuring | De offerte is goedgekeurd of teruggestuurd |
| `quote_superseded` | Teruggestuurde offerte | Er daarna een nieuwe offerte is uitgegeven |
| `correction_delivered` | Maand met naverrekening | De naverrekening is aangeleverd |
| `role_staffed` | Open rol | De rol is ingevuld |
| `month_closed` | Maand | De maand is afgesloten |
| `billing_delivered` | Afgesloten maand | De factuurgegevens zijn aangeleverd |
| `invoice_recorded` | Afgesloten maand | De factuur is vastgelegd |

### Feiten over een vacature

| Feit | Geldt als |
|---|---|
| `draft` | De aanvraag nog wordt voorbereid |
| `requested` | De aanvraag is ingediend |
| `in_procedure` | De aanvraag wacht op advies en akkoord |
| `hr_advice_given`, `control_advice_given`, `advices_given` | Het advies van HR, van concern control, of beide is vastgelegd |
| `approval_given`, `approved` | Het akkoord is vastgelegd; de vacature is goedgekeurd |
| `needs_opening` | De vacature moet worden opengesteld (niet bij een gerede kandidaat) |
| `opened` | De vacature is opengesteld |
| `ready_to_fill` | De vacature kan worden vervuld |
| `hire_recorded` | Is vastgelegd wie is aangenomen |
| `colleague_known_in_wies` | De nieuwe collega is bekend in Wies |
| `colleague_has_email` | De nieuwe collega heeft een e-mailadres |

### Ankerdata

Een termijn telt werkdagen vanaf een anker: `month_end` (einde van de maand), `closed_on` (dag van afsluiten), `delivered_on` (dag van aanleveren), `requested_on` (dag van aanvragen), `needed_from` (begin van de rol), `approval_requested_on` (dag van het verzoek om goedkeuring), `correction_arose_on` (dag waarop de naverrekening ontstond). Feestdagen tellen nog als werkdag.

### Gebeurtenissen

De takenlaag luistert naar alle bestaande domeingebeurtenissen en doet bij elk hetzelfde: de stand als verouderd markeren. Er is geen gebeurtenis toegevoegd. Wijzigingen zonder gebeurtenis (een begrotingsregel, inzet, een afgesloten of heropende maand, een aanlevering, een stap van een vacature, een aanname) komen in beeld bij de eerstvolgende evaluatie: direct op de takenschermen, binnen vijftien seconden in de teller.

## Het meegeleverde plan

Versie 2026.2, in `backend/grip/data/tasks/plan.json`. Drieëntwintig sjablonen.

### Opdracht

| Spoor | Taak | Ontstaat | Sluit door | Voor | Termijn |
|---|---|---|---|---|---|
| Offerte | Werk de aanvraag uit: maak de begroting | Externe potentiële opdracht | Feit: de begroting heeft een regel | Eigenaar | |
| Offerte | Stel de offerte op | Per ronde, zodra er een begroting is | Feit: de offerte is uitgegeven | Eigenaar | |
| Offerte | Beoordeel offerte (kenmerk) | Per verzoek om interne goedkeuring | Feit: de offerte is goedgekeurd of teruggestuurd | Offertegoedkeurder | 3 werkdagen na het verzoek |
| Offerte | Maak een nieuwe offerte | Offerte teruggestuurd bij de goedkeuring | Feit: er is een nieuwe offerte uitgegeven | Wie om goedkeuring vroeg | |
| Offerte | Bied de offerte aan | Offerte uitgegeven | Feit: de offerte is aangeboden | Eigenaar | |
| Offerte | Wacht op akkoord van de opdrachtgever | Offerte aangeboden | Feit: de opdrachtgever heeft akkoord gegeven | Eigenaar, wacht op de opdrachtgever | |
| Offerte | Verwerk de reactie van de opdrachtgever in een nieuwe offerte | Offerte afgewezen | Feit: er is een nieuwe offerte uitgegeven | Eigenaar | |
| Offerte | Beoordeel en teken de ontvangen offerte | Offerte ontvangen als opdrachtgever | Feit: er is akkoord gegeven of afgewezen | Tekenbevoegde | |
| Bemensing | Vul de rol in | Per open rol, zodra er akkoord is of een offerte is uitgegeven | Feit: de rol is ingevuld | Planner | |
| Uitvoering | Zet de opdracht in uitvoering | Er is akkoord | Feit: de opdracht is in uitvoering | Eigenaar | |
| Uitvoering | Sluit de maand af | Per verstreken maand met inzet, de oudste eerst | Feit: de maand is afgesloten | Eigenaar of manager | 5 werkdagen na het einde van de maand |
| Uitvoering | Lever het eindrapport op | Externe opdracht afgerond | Feit: het eindrapport is uitgegeven | Eigenaar | |
| Financiën | Lever de factuurgegevens aan | Per afgesloten maand, de oudste eerst | Feit: de factuurgegevens zijn aangeleverd | Eigenaar of manager | 5 werkdagen na het afsluiten |
| Financiën | Leg vast dat de factuur is verstuurd | Factuurgegevens aangeleverd | Feit: de factuur is vastgelegd | Eigenaar of manager | 10 werkdagen na het aanleveren |
| Financiën | Lever de naverrekening aan | Per aangeleverde maand met een naverrekening | Feit: de naverrekening is aangeleverd | Eigenaar of manager | 5 werkdagen na het ontstaan |

Een verzoek om goedkeuring bestaat alleen als de instantie interne goedkeuring vraagt. Het verzoek zelf is dus de aanleiding; het plan leest de instelling niet. Wie offertes mag goedkeuren, ziet de taak ook zonder rol op de opdracht, zoals die persoon de offerte zelf mag lezen. Verder gaat er niets van de opdracht open.

De taak voor de naverrekening staat in het plan en ontstaat nog niet: grip bewaart nog niet per maand dat er een naverrekening is ontstaan. Een sjabloon kan een soort gebeurtenis eisen (`requires_event`); bestaat die soort niet in deze versie van grip, dan wordt het sjabloon gecontroleerd en overgeslagen.

### Vacature

| Spoor | Taak | Ontstaat | Sluit door | Voor | Termijn |
|---|---|---|---|---|---|
| Werving | Bereid de aanvraag voor en dien haar in | Vacature in voorbereiding | Feit: de aanvraag is ingediend | Aanvrager | |
| Werving | Geef advies van HR | Aanvraag ingediend | Feit: het advies van HR is vastgelegd | Wie voor het advies is genoemd | 5 werkdagen na het aanvragen |
| Werving | Geef advies van concern control | Aanvraag ingediend | Feit: het advies van concern control is vastgelegd | Wie voor het advies is genoemd | 5 werkdagen na het aanvragen |
| Werving | Geef akkoord | Beide adviezen vastgelegd | Feit: het akkoord is vastgelegd | Wie voor het akkoord is genoemd | |
| Werving | Stel de vacature open | Goedgekeurd, en openstellen is nodig | Feit: de vacature is opengesteld | Aanvrager | |
| Werving | Vervul de vacature | De vacature kan worden vervuld | Feit: de aanname is vastgelegd | Aanvrager | |
| Werving | Stel de nieuwe collega voor aan Wies | Aanname vastgelegd | Feit, of met de hand | Aanvrager | |
| Werving | Vraag een account en e-mailadres aan | Aanname vastgelegd | Feit, of met de hand | Aanvrager | |

Eenentwintig sjablonen sluiten alleen door hun feit. De laatste twee sluiten door hun feit en zijn ook af te vinken, omdat het werk buiten grip gebeurt en het feit later kan volgen. Een taak die iemand zelf toevoegt, sluit alleen met de hand.

Een taak vervalt als haar voorwaarden niet meer gelden voordat haar feit geldt, of als haar onderwerp verdwijnt. Geldt een feit later niet meer (een heropende maand), dan gaat de taak weer open.

## Zaakgericht werken

Grip gebruikt de woorden van zaakgericht werken en niet de componenten. Er is geen zakenregister en geen catalogus buiten grip.

| Zaakgericht werken | In grip |
|---|---|
| Zaak | Een opdracht of een vacature |
| Zaaktype | De soort zaak met haar deel van het plan, in een versie |
| Statustype en status | De feiten van de zaak; de stand per spoor is de leesbare vorm |
| Deelzaak | Een vacature die bij een begrotingsregel van een opdracht hoort |
| Taak | Een taak |
| Rol bij een zaak | Eigenaar, manager, aanvrager, en wie voor advies of akkoord is genoemd |
| Resultaat | De eindstatus van de zaak: verantwoord, afgewezen, geannuleerd, vervuld of ingetrokken |
| Besluit | Het akkoord op een offerte, en advies en akkoord op een vacature |
| Zaakobject | De context van een opdracht, als URI (ADR 0004) |

Een koppelvlak volgens de ZGW-standaarden is niet gebouwd. Komt het er, dan is het een rand om deze begrippen: een zaak en haar taken worden naar buiten in die vorm getoond, en het model in grip verandert er niet door.

## Beheer

| Wat | Hoe |
|---|---|
| Taken voor bestaande zaken maken | `uv run python -m grip.tasks.backfill` in `backend`. Veilig om te herhalen. |
| Evaluatie op tijd | Het achtergrondproces, elke `TASKS_EVALUATE_INTERVAL_SECONDS` seconden (standaard 300). Nul zet het uit. |
| Een ander plan | Nog niet in te stellen. Het plan wordt met grip meegeleverd. |
