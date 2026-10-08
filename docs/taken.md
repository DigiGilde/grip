# Taken

Dit document beschrijft de takenlaag van grip: welke feiten er zijn, welk plan wordt meegeleverd, en hoe de begrippen zich verhouden tot zaakgericht werken. Het besluit en de redenen staan in [ADR 0024](adr/0024-taken-feiten-en-het-plan.md).

## In het kort

- Een **zaak** is een opdracht of een vacature.
- Een **feit** is iets wat grip over een zaak weet uit de eigen gegevens.
- Een **taak** ontstaat als haar voorwaarden gelden en sluit als haar feit geldt.
- Het **plan** is de lijst sjablonen waaruit taken ontstaan.

Een taak afvinken verandert niets aan de zaak. Het werk gebeurt op het scherm waar de taak naar verwijst, en de taak sluit daarna vanzelf.

## Wat een taak je vertelt

Een taak zegt wat jij moet doen, niet hoe de takenlaag werkt ([ADR 0038](adr/0038-een-taak-vertelt-wat-de-lezer-moet-doen.md)):

1. wat je moet doen, of wie wat moet doen als het niet aan jou is;
2. waarover, als link naar de vacature of de opdracht;
3. waarom de taak er nu is;
4. vóór wanneer, en wat erna komt;
5. één knop, met dezelfde naam als de knop op de pagina waar het werk gebeurt.

De naam van een taak die jij moet doen, brengt je naar die pagina. Bovenaan staat dan voor welke taak je er bent, en na het werk dat de taak gedaan is. Een taak waarop je wacht, opent als paneel om te lezen.

## Waar je taken ziet

| Plek | Wat er staat |
|---|---|
| Taken, in de navigatie | Twee groepen. "Te doen": wat jij nu moet doen, wat het eerst af moet bovenaan. "Wacht op anderen": wat van jou is en op een ander wacht, en de taken van anderen op de opdrachten waarvan je eigenaar bent en de vacatures die je hebt aangevraagd. Het getal in de navigatie telt alleen "Te doen". |
| Taken, weergave Bord | Alle taken van de zaken die je mag inzien, in de kolommen te doen, bezig, wacht op een ander en klaar. Te filteren op opdracht of vacature, op persoon en op spoor. |
| Tabblad Taken van een opdracht of vacature | De stand per spoor in één regel, en de taken per spoor. Wie de zaak mag bewerken, kan een eigen taak toevoegen. |

Een taak verplaats je met het menu aan het eind van de rij of op de kaart. Slepen is niet nodig. In hetzelfde menu staat "Bekijk de taak", met de notities.

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

Bij advies en akkoord hangt wat de aanvrager leest af van wie er is genoemd:

| Stand | Wat de aanvrager leest |
|---|---|
| Nog niemand genoemd | "Noem wie het advies geeft", te doen. Wie het besluit zelf mag vastleggen (een beheerder) leest "Leg het advies vast". |
| Iemand met een account | De taak is van die persoon. De aanvrager wacht en leest op wie. |
| Iemand zonder account | De aanvrager wacht en vraagt het advies zelf op. Alleen een beheerder kan het daarna vastleggen. |

Wacht een taak op een recht in grip dat niemand heeft, dan staat dat bij de taak, met wie het kan toekennen.

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
| `billing_period` | Factuurperiode van de opdracht waarin een maand is afgesloten: een maand of een kalenderkwartaal |

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
| `period_ready` | Factuurperiode | Elke maand met inzet in de periode is afgesloten |
| `period_delivered` | Factuurperiode | De periode is aangeleverd |
| `period_invoiced` | Factuurperiode | De factuur over de periode is vastgelegd |

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
| `request_form_in_use` | De instantie heeft een aanvraagformulier in gebruik, en de vacature is aangevraagd of net goedgekeurd |
| `request_form_current` | Het aanvraagformulier is gemaakt en klopt met de vacature |
| `request_form_signed` | Het getekende formulier is vastgelegd |

### Ankerdata

Een termijn telt werkdagen vanaf een anker: `month_end` (einde van de maand), `closed_on` (dag van afsluiten), `delivered_on` (dag van aanleveren), `requested_on` (dag van aanvragen), `needed_from` (begin van de rol), `approval_requested_on` (dag van het verzoek om goedkeuring), `correction_arose_on` (dag waarop de naverrekening ontstond), `ready_on` (dag waarop de laatste maand van de periode is afgesloten). Feestdagen tellen nog als werkdag.

### Gebeurtenissen

De takenlaag luistert naar alle bestaande domeingebeurtenissen en doet bij elk hetzelfde: de stand als verouderd markeren. Er is geen gebeurtenis toegevoegd. Wijzigingen zonder gebeurtenis (een begrotingsregel, inzet, een afgesloten of heropende maand, een aanlevering, een stap van een vacature, een aanname) komen in beeld bij de eerstvolgende evaluatie: direct op de takenschermen, binnen vijftien seconden in de teller.

## Het meegeleverde plan

Versie 2026.3, in `backend/grip/data/tasks/plan.json`; 29 sjablonen. De titels hieronder zijn die voor wie het werk doet, uit `guidance.json`.

### Opdracht

| Spoor | Taak | Sluit door | Voor | Termijn |
|---|---|---|---|---|
| Offerte | Maak de begroting | Feit: de begroting heeft een regel | Eigenaar |  |
| Offerte | Maak de offerte | Feit: de offerte is uitgegeven | Eigenaar |  |
| Offerte | Beoordeel offerte (kenmerk) | Feit: de offerte is goedgekeurd of teruggestuurd | Offertegoedkeurder | 3 werkdagen na het verzoek |
| Offerte | Maak een nieuwe offerte | Feit: er is een nieuwe offerte uitgegeven | Wie om goedkeuring vroeg |  |
| Offerte | Bied de offerte aan | Feit: de offerte is aangeboden | Eigenaar |  |
| Offerte | Leg het akkoord van de opdrachtgever vast | Feit: de opdrachtgever heeft akkoord gegeven | Eigenaar |  |
| Offerte | Maak een nieuwe offerte na de afwijzing | Feit: er is een nieuwe offerte uitgegeven | Eigenaar |  |
| Offerte | Beoordeel de ontvangen offerte | Feit: er is akkoord gegeven of afgewezen | Tekenbevoegde |  |
| Bemensing | Vul de rol (rol) in | Feit: de rol is ingevuld | Planner |  |
| Uitvoering | Zet de opdracht in uitvoering | Feit: de opdracht is in uitvoering | Eigenaar |  |
| Uitvoering | Sluit (maand) af | Feit: de maand is afgesloten | Eigenaar of manager | 5 werkdagen na het einde van de maand |
| Uitvoering | Lever het eindrapport op | Feit: het eindrapport is uitgegeven | Eigenaar |  |
| Financiën | Lever (periode) aan | Feit: de periode is aangeleverd | Eigenaar of manager | 5 werkdagen na het afsluiten van de laatste maand |
| Financiën | Leg de factuur over (periode) vast | Feit: de factuur over de periode is vastgelegd | Eigenaar of manager | 10 werkdagen na het aanleveren |
| Financiën | Lever de naverrekening van (maand) aan | Feit: de naverrekening is aangeleverd | Eigenaar of manager | 5 werkdagen na het ontstaan |

Afsluiten gaat per maand. Aanleveren en de factuur vastleggen gaan per factuurperiode van de opdracht: een maand of een kalenderkwartaal. Een periode is klaar om aan te leveren als elke maand met inzet erin is afgesloten.

Een verzoek om goedkeuring bestaat alleen als de instantie interne goedkeuring vraagt. Wie offertes mag goedkeuren, ziet de taak ook zonder rol op de opdracht. De taak voor de naverrekening staat in het plan en ontstaat nog niet: grip bewaart nog niet per maand dat er een naverrekening is ontstaan.

### Vacature

| Spoor | Taak | Sluit door | Voor | Termijn |
|---|---|---|---|---|
| Werving | Vraag de vacature aan | Feit: de aanvraag is ingediend | Aanvrager |  |
| Werving | Geef het advies van HR | Feit: het advies van HR is vastgelegd | Wie voor het advies is genoemd | 5 werkdagen na het aanvragen |
| Werving | Geef het advies van concern control | Feit: het advies van concern control is vastgelegd | Wie voor het advies is genoemd | 5 werkdagen na het aanvragen |
| Werving | Geef akkoord op de vacature | Feit: het akkoord is vastgelegd | Wie voor het akkoord is genoemd |  |
| Werving | Stel de vacature open | Feit: de vacature is opengesteld | Aanvrager |  |
| Werving | Leg vast wie is aangenomen | Feit: de aanname is vastgelegd | Aanvrager |  |
| Werving | Stel de nieuwe collega voor aan Wies | Feit: de collega is bekend in Wies | Aanvrager |  |
| Werving | Vraag een account en e-mailadres aan | Feit: de collega heeft een e-mailadres | Aanvrager |  |
| Teksten | Schrijf de (tekst) | Feit: de tekst is vastgesteld | Schrijver van de tekst |  |
| Teksten | Beoordeel de (tekst) | Feit: het oordeel is gegeven | Beoordelaar | 3 werkdagen na het aanbieden |
| Teksten | Verwerk de opmerkingen op de (tekst) | Feit: er is een nieuwe versie of de tekst is vastgesteld | Schrijver van de tekst |  |
| Werving | Leg de link naar de gepubliceerde vacature vast | Feit: de link naar de gepubliceerde vacature is vastgelegd | Aanvrager |  |
| Werving | Maak het aanvraagformulier | Feit: het aanvraagformulier is gemaakt en klopt met de vacature | Aanvrager |  |
| Werving | Leg het getekende formulier vast | Feit: het getekende formulier is vastgelegd | Aanvrager |  |

De taken voor het aanvraagformulier ontstaan alleen als de instantie een formulier in gebruik heeft. "Stel de nieuwe collega voor aan Wies" en "Vraag een account en e-mailadres aan" sluiten door hun feit en zijn ook af te vinken, omdat het werk buiten grip gebeurt. Een taak die iemand zelf toevoegt, sluit alleen met de hand.

### Een nieuwe versie van het plan

Een zaak houdt de versie waarmee ze begon. Een plan kan onder `replaces` oudere versies noemen waarvan het de lopende zaken overneemt; dat is voor een versie waarin het werk verkeerd was ingedeeld, niet voor elke wijziging. Versie 2026.3 neemt de zaken van 2026.2 over. Bij de eerstvolgende evaluatie krijgt zo'n zaak de taken van het nieuwe plan. Een open taak die het nieuwe plan niet meer vraagt, vervalt; een taak die beide plannen vragen, blijft dezelfde taak.

Een taak vervalt als haar voorwaarden niet meer gelden voordat haar feit geldt, of als haar onderwerp verdwijnt. Geldt een feit later niet meer (een heropende maand), dan gaat de taak weer open.

## Een sjabloon toevoegen

Een sjabloon in het plan krijgt een vermelding met dezelfde sleutel in `backend/grip/data/tasks/guidance.json`. Zonder vermelding faalt de test.

| Veld | Wat |
|---|---|
| `title` | Wat de doener moet doen, kort en in de gebiedende wijs |
| `awaited` | Waar een ander op wacht, als zelfstandig naamwoord: "Het advies van HR" |
| `do` | De zin voor wie het werk doet |
| `wait` | De zin voor wie wacht, met `{wie}` |
| `action` | De naam van de knop; dezelfde als op de pagina van het werk |
| `why` | Wat er gebeurde waardoor de taak er is |
| `then` | Wat erna komt (optioneel) |
| `destination` | Een naam uit `destinations` in hetzelfde bestand: de pagina waar het werk gebeurt |
| `situations` | Andere `title`, `awaited`, `do`, `wait` of `action` voor een stand die grip herkent (optioneel) |

In een zin kunnen staan: `{opdracht}`, `{opdrachtgever}`, `{functie}`, `{aanvrager}`, `{ingediend_op}`, `{wie}`, `{kenmerk}`, `{maand}`, `{periode}`, `{rol}`, `{tekst}`, `{gevraagd_door}` en `{gevraagd_op}`. Een nieuwe naam of een nieuwe stand komt erbij in `backend/grip/tasks/telling.py`.

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
