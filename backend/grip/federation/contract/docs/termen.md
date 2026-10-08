# Termen

De interface van het contract is Nederlands. Een implementatie mag intern andere namen voeren en
vertaalt dan op een plek, aan de grens. Deze tabel geeft bij elke term van het contract de
codenaam die grip gebruikt. Termen die hier niet staan zijn in contract en code gelijk (`id`,
`uri`, `type`, `status`, `jws`, `fte`, `email`, `peildatum` en dergelijke).

De vertaling is omkeerbaar: elke term heeft precies een codenaam en andersom. Binnen
`type_details` van een node en binnen `keys` van een sleutelset wordt niets vertaald.

## Velden

| Contract | Code |
|---|---|
| `aangeboden_op` | `offered_at` |
| `aantal` | `headcount` |
| `aanvraag_id` | `request_id` |
| `afgesloten_op` | `closed_at` |
| `afgesproken` | `agreed` |
| `afgewezen_op` | `rejected_at` |
| `bedrag` | `amount` |
| `bedrag_centen` | `amount_cents` |
| `begindatum` | `start_date` |
| `begroot` | `budgeted` |
| `begrotingsregel` | `budget_line` |
| `beherende_organisatie` | `managing_organisation` |
| `bericht_id` | `message_id` |
| `beschikbaar` | `available` |
| `beschikbaar_vanaf` | `available_from` |
| `beschikbare_fte` | `available_fte` |
| `besteding` | `spending` |
| `bovenliggende_opdracht_uri` | `parent_assignment_uri` |
| `budgetindicatie` | `budget_indication` |
| `canonicalisatie` | `canonicalization` |
| `context_uris` | `context_refs` |
| `contractversie` | `contract_version` |
| `edge_typen` | `edge_types` |
| `eenheid_kenmerk` | `unit_key` |
| `eigen` | `custom` |
| `einddatum` | `end_date` |
| `externe_node_uris` | `external_node_uris` |
| `functie` | `function` |
| `gedekt` | `covered` |
| `geldig_tot_en_met` | `valid_until` |
| `geldigheid` | `validity` |
| `geleverd` | `delivered` |
| `gepubliceerd_op` | `published_at` |
| `getekend_op` | `signed_at` |
| `gewenste_periode` | `desired_period` |
| `gezochte_fte` | `sought_fte` |
| `grondslag` | `basis` |
| `hash_algoritme` | `hash_algorithm` |
| `ingezette_fte` | `deployed_fte` |
| `inhoud_base64` | `content_base64` |
| `instantie_uri` | `instance_uri` |
| `jaar` | `year` |
| `kandidaat_referentie` | `candidate_reference` |
| `kostendekking` | `coverage` |
| `maand` | `month` |
| `maandtarief` | `monthly_rate` |
| `maandtarieven_per_jaar` | `monthly_rates_per_year` |
| `mediatype` | `media_type` |
| `mijlpalen` | `milestones` |
| `momentopname` | `snapshot` |
| `momentopname_hash` | `snapshot_hash` |
| `naam` | `name` |
| `naamruimte` | `namespace` |
| `naar` | `to` |
| `niet_geleverd` | `not_delivered` |
| `node_typen` | `node_types` |
| `offerte_hash` | `quote_hash` |
| `offerte_id` | `quote_id` |
| `offertebedrag` | `quoted_amount` |
| `omschrijving` | `description` |
| `ondertekenaar` | `signer` |
| `ontvangen_op` | `received_at` |
| `opdracht` | `assignment` |
| `opdracht_uri` | `assignment_uri` |
| `opdrachtgever` | `client` |
| `opdrachtnemer` | `contractor` |
| `open_rollen` | `open_roles` |
| `organisatie` | `organisation` |
| `peilmoment` | `as_of` |
| `periode` | `period` |
| `persoon` | `person` |
| `positie` | `position` |
| `profiel` | `profile` |
| `prognose` | `forecast` |
| `reageren_voor` | `respond_by` |
| `reden` | `reason` |
| `regels` | `lines` |
| `resultaten` | `results` |
| `rol` | `role` |
| `samenvatting` | `summary` |
| `soort` | `kind` |
| `stand` | `state` |
| `streefdatum` | `due_date` |
| `subtotalen_per_jaar` | `subtotals_per_year` |
| `tariefcategorie` | `rate_category` |
| `titel` | `title` |
| `totaal` | `total` |
| `totale_kosten` | `total_cost` |
| `uitgegeven_op` | `issued_at` |
| `uitkomst` | `outcome` |
| `uitputting` | `used` |
| `vacature_id` | `vacancy_id` |
| `valuta` | `currency` |
| `van` | `from` |
| `verzonden_op` | `sent_at` |
| `volledig` | `complete` |
| `voorwaarden` | `conditions` |
| `vorm` | `form` |

## Waarden van codelijsten

Veld `vorm` (code: `form`):

| Contract | Code |
|---|---|
| `eigen_instantie` | `own_instance` |
| `geuploade_pdf` | `uploaded_pdf` |
| `tekenlink` | `signing_link` |

Veld `soort` (code: `kind`):

| Contract | Code |
|---|---|
| `extern` | `external` |
| `intern` | `internal` |
| `personeel` | `personnel` |
| `vast` | `fixed` |

Veld `status` (code: `status`):

| Contract | Code |
|---|---|
| `aangevraagd` | `requested` |
| `afgerond` | `completed` |
| `afgewezen` | `rejected` |
| `akkoord` | `accepted` |
| `concept` | `draft` |
| `geannuleerd` | `cancelled` |
| `in_uitvoering` | `in_progress` |
| `ingetrokken` | `withdrawn` |
| `ingevuld` | `filled` |
| `offerte_uitgegeven` | `quoted` |
| `open` | `open` |
| `verantwoord` | `accounted` |

Veld `grondslag` (code: `basis`):

| Contract | Code |
|---|---|
| `vast_bedrag` | `fixed_amount` |
| `werkelijke_inzet` | `actual_allocation` |
| `werkelijke_kosten` | `actual_costs` |

Veld `stand` (code: `state`):

| Contract | Code |
|---|---|
| `gepland` | `planned` |
| `gereed` | `done` |
| `vervallen` | `dropped` |

Veld `uitkomst` (code: `outcome`):

| Contract | Code |
|---|---|
| `aanvaard` | `accepted` |
| `duplicaat` | `duplicate` |

## Schema's

| Contract | Code |
|---|---|
| `aanbod` | `vacancy-offer` |
| `afwijzing` | `rejection` |
| `akkoord` | `acceptance` |
| `bedrag` | `money` |
| `doorgifte-bemensing` | `handover-staffing` |
| `doorgifte-capaciteit` | `handover-capacity` |
| `doorgifte-factuurgegevens` | `handover-billing-data` |
| `doorgifte-kosten` | `handover-costs` |
| `doorgifte-opdrachten` | `handover-assignments` |
| `eindrapport` | `final-report` |
| `factuurgegevens` | `billing-data` |
| `keten` | `chain` |
| `node-pagina` | `node-page` |
| `offerte` | `quote` |
| `ontvangstbevestiging` | `receipt` |
| `opdracht` | `assignment` |
| `opdracht-pagina` | `assignment-page` |
| `opdrachtaanvraag` | `assignment-request` |
| `organisatie-ref` | `organisation-ref` |
| `periode` | `period` |
| `uitputting` | `budget-usage` |
| `vacature` | `vacancy` |
| `voortgang` | `progress` |
| `woordenlijst` | `vocabulary` |

## Paden

| Contract | Was in 0.1.0 |
|---|---|
| `/doorgifte/bemensing` | `/handover/staffing` |
| `/doorgifte/capaciteit` | `/handover/capacity` |
| `/doorgifte/factuurgegevens` | `/handover/billing-data` |
| `/doorgifte/kosten` | `/handover/costs` |
| `/doorgifte/opdrachten` | `/handover/assignments` |
| `/nodes/{nodeId}/keten` | `/nodes/{nodeId}/chain` |
| `/offertes` | `/quotes` |
| `/offertes/{offerteId}/afwijzingen` | `/quotes/{quoteId}/rejections` |
| `/offertes/{offerteId}/akkoorden` | `/quotes/{quoteId}/acceptances` |
| `/opdrachtaanvragen` | `/assignment-requests` |
| `/opdrachten` | `/assignments` |
| `/opdrachten/{opdrachtId}` | `/assignments/{assignmentId}` |
| `/opdrachten/{opdrachtId}/eindrapport` | `/assignments/{assignmentId}/final-report` |
| `/opdrachten/{opdrachtId}/factuurgegevens` | `/assignments/{assignmentId}/billing-data` |
| `/opdrachten/{opdrachtId}/uitputting` | `/assignments/{assignmentId}/budget-usage` |
| `/opdrachten/{opdrachtId}/voortgang` | `/assignments/{assignmentId}/progress` |
| `/vacatures` | `/vacancies` |
| `/vacatures/{vacatureId}/aanbiedingen` | `/vacancies/{vacancyId}/offers` |
| `/woordenlijst` | `/vocabulary` |

## Parameters

| Contract | Code |
|---|---|
| `jaar` | `year` |
| `maand` | `month` |
| `maxDiepte` | `maxDepth` |
| `offerteId` | `quoteId` |
| `opdrachtId` | `assignmentId` |
| `vacatureId` | `vacancyId` |
