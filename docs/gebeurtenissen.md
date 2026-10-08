# Gebeurtenissen

Grip houdt één stroom bij van wat er in een instantie gebeurt. De geschiedenis van een opdracht, de auditlog, de feed voor andere systemen en de reacties van de federatie en de taken lezen allemaal diezelfde stroom. Het besluit staat in ADR 0028; dit document beschrijft hoe het werkt.

## Het record

Een gebeurtenis is een rij in `stream_event`. Ze wordt geschreven in de transactie van de wijziging die ze beschrijft, en daarna nooit meer gewijzigd.

| Veld | Betekenis |
|---|---|
| `seq` | De plaats in de stroom. Oplopend zonder gaten, in de volgorde waarin transacties vastliggen. |
| `id` | Uniek id van de gebeurtenis. |
| `occurred_at` | Het begin van de transactie. Gebeurtenissen van één transactie delen dit moment. |
| `type` | Vaste naam met een punt: `quote.accepted`, `budget_line.updated`. |
| `action` | `create`, `update` of `delete` bij een gewone wijziging, anders leeg. |
| `subject_kind`, `subject_id` | Waar de gebeurtenis over gaat. |
| `case_kind`, `case_id` | De zaak: een opdracht of een vacature. |
| `person_id` | De persoon over wiens gegevens het gaat. |
| `actor_kind`, `actor_person_id`, `actor_ref` | Wie het deed: een persoon, een gast, een andere instantie (met haar peer-id) of het systeem (met de naam van de taak). |
| `origin`, `origin_peer` | Eigen, of ontvangen van welke instantie. |
| `correlation_id` | Verbindt alles wat één verzoek of één inkomend bericht veroorzaakte. 32 hexadecimale tekens, zodat het ook een trace-id is. |
| `purpose` | Waarvoor gegevens zijn ingezien, voor zover bekend. |
| `old_value`, `new_value` | De wijziging per veld. |
| `payload` | Wat een domeingebeurtenis aan haar afhandelaars meldt. |
| `note` | Toelichting of reden. |
| `refs` | Verwijzingen naar bewijs dat elders ligt, op hash. |
| `existence_class` | De gegevensklasse die bepaalt wie mag weten dat dit gebeurde. Leeg betekent beheer van de instantie. |
| `field_classes` | De gegevensklasse per veld. `*` geldt voor elk ander veld, de payload en de toelichting. |
| `salt`, `*_digest` | Gezouten afdrukken van de waarden, waarover de keten gaat. |
| `prev_hash`, `hash` | De schakel van de keten. |
| `erased_at` | Wanneer de waarden zijn gewist. |

De zaak en de persoon hoeven niet te worden meegegeven. Ontbreken ze, dan zoekt grip ze op uit de waarden en uit het onderwerp: een begrotingsregel hoort bij de opdracht van die regel.

## Schrijven

```python
from grip.events import stream

stream.append(db, subject=("budget_line", line.id), action="update",
              old={"amount_cents": 100}, new={"amount_cents": 200})
await stream.record(db, "quote.accepted", payload={...})
```

`append` voegt de gebeurtenis toe aan de transactie. `record` doet dat ook en roept daarna de transactionele afhandelaars van het type aan. `record_audit` en `emit` zijn dunne lagen over deze twee en blijven werken.

Actor, herkomst en correlatie-id komen uit de context van het verzoek (`grip.events.context`). Een webverzoek, een inkomend bericht van een andere instantie en een achtergrondtaak zetten die context één keer.

Er zijn twee soorten afhandelaars:

- `stream.on_event(type, handler)` loopt in de transactie. Wat de afhandelaar schrijft vervalt met de wijziging, en een fout weigert de wijziging. De federatie (bericht in de uitbak) en de taken (stand verouderd) werken zo.
- `stream.after_commit(type, handler)` loopt nadat de transactie duurzaam is, en niet bij het vrijgeven van een savepoint. Een fout wordt gelogd en draait niets terug. De gebeurtenis staat in de stroom, dus een afhandelaar kan vanaf zijn cursor inhalen.

## Typen

Een gewone wijziging heet `<soort>.created`, `<soort>.updated` of `<soort>.deleted`. De soorten staan in `grip.events.classification`, elk met haar gegevensklassen.

Daarnaast zijn er gebeurtenissen met een eigen betekenis:

| Type | Betekenis |
|---|---|
| `assignment_request.created` | Een offerte is aangevraagd bij een opdrachtnemer. |
| `assignment.status_changed` | De status van een opdracht is gewijzigd. |
| `quote.issued` | Een offerte is gemaakt. |
| `quote.offered` | Een offerte is aangeboden, via een kanaal. |
| `quote.accepted`, `quote.rejected` | Een offerte is aanvaard of afgewezen. De hash van de ondertekende verklaring staat in `refs`. |
| `quote_approval.requested`, `.approved`, `.sent_back`, `.withdrawn` | Interne goedkeuring van een offerte. Verlaat de instantie nooit. |
| `final_report.issued` | Het eindrapport is uitgebracht. |
| `vacancy.published` | Een vacature is opengesteld. |
| `invoice.recorded`, `invoice.withdrawn` | Vastgelegd of teruggenomen dat een factuur is verstuurd. |
| `person_scale.changed` | De inzetschaal van een persoon is vastgelegd of gewijzigd. |
| `billing_correction.arose` | Een al aangeleverde maand heeft een andere prijs gekregen. |
| `data.read` | Iemand heeft gegevens van de klassen D, E of F ingezien. |
| `stream.erased` | Waarden uit de stroom zijn gewist. |

## Volledigheid

Een wijziging van domeingegevens zonder gebeurtenis is een fout. De testsuite volgt elk verzoek (`grip.events.completeness`) en faalt als een domeintabel is gewijzigd zonder gebeurtenis die dat dekt. Een tabel is gedekt door een gebeurtenis over die tabel zelf, of over een soort die er in `COVERED_BY` voor is genoemd. Tabellen zonder domeingegevens (sessies, de uitbak, wat de takenmotor onthoudt, de stroom zelf) staan in `NOT_DOMAIN` met de reden.

## De keten

Elke gebeurtenis draagt de hash van de vorige. De hash is SHA-256 over een canonieke vorm (RFC 8785) van de vaste gegevens van de gebeurtenis en van de afdrukken van haar waarden. Een waarde wordt dus niet zelf gehasht, maar via een gezouten afdruk.

```
uv run python -m grip.events.check
```

De opdracht loopt de stroom af en zegt per breuk wat er mis is: de gebeurtenis sluit niet aan op de vorige (iets is verwijderd, tussengevoegd of verplaatst), de gebeurtenis zelf is gewijzigd, of een waarde past niet meer bij haar afdruk. De beheerder kan dezelfde controle opvragen via `GET /api/events/chain`.

De database weigert het verwijderen van een gebeurtenis en elke wijziging behalve het wissen van waarden.

Wie de hele database kan herschrijven, kan ook een nieuwe keten maken. Daartegen helpt alleen de laatste hash buiten de instantie bewaren. Dat is een latere stap.

## Lezen als geschiedenis

`GET /api/events` geeft de gebeurtenissen die de lezer mag kennen, nieuwste eerst, met filters op zaak, persoon over wie het gaat, actor, type, soort onderwerp en periode.

Elke gebeurtenis wordt apart voorgelegd aan het toegangsmodel:

1. Mag de lezer weten dat dit gebeurde? Dat is een leesvraag op de `existence_class`, over de zaak of de persoon van de gebeurtenis.
2. Mag de lezer de waarde van dit veld zien? Dat is een leesvraag op de klasse van het veld.

Een planner ziet zo dat de schaal van een collega is gewijzigd, zonder de oude en de nieuwe schaal. Een lid van een opdracht ziet dat de begroting is gewijzigd, zonder bedragen.

De parameter `kind` kiest tussen `changes` (de standaard: alles behalve inzage), `reads` en `all`. Hij werkt in de zoekvraag, vóór de limiet: een pagina wijzigingen is gevuld met wijzigingen, hoeveel inzage er ook tussen ligt. Elk antwoord bevat per gebeurtenis ook `title` en `lines`: de gebeurtenis in het Nederlands, op de server geschreven (`grip.events.words`). Een veld zonder Nederlandse naam en een codewaarde zonder label worden niet getoond.

Het antwoord bevat geen totaal. Een gebeurtenis die de lezer niet mag kennen is afwezig, ook als een filter er precies op past. Wie filtert op een persoon, krijgt alleen gebeurtenissen waarvan hij mag weten over wie ze gaan.

In het scherm staat de geschiedenis als tabblad "Geschiedenis" bij een opdracht en een vacature, en als pagina "Activiteit" onder Beheer.

## Wat is er gebeurd

Naast de geschiedenis is er een overzicht voor de vraag "wat heb ik gemist" (ADR 0043). Het leest dezelfde stroom met een andere selectie.

`GET /api/updates?limiet=<aantal>&na=<cursor>` geeft berichten, nieuwste eerst. Een bericht heeft een zin in delen (`parts`, waarvan het onderwerp een `href` naar de plek in grip heeft), de zin als platte tekst (`text`), de tijd in woorden (`when_text`), de dag waaronder het staat (`day`), de soort (`kind`), het aantal gebeurtenissen dat erin is samengenomen (`count`) en of het nieuw is (`new`). Het antwoord bevat ook `new_count`, het aantal nieuwe berichten, en `next`, de cursor om verder terug te lezen. `POST /api/updates/seen` legt vast dat de lezer heeft gekeken.

Wat nieuws is, staat in `grip.events.news`:

- `NEWS` is de lijst: per soort nieuws de typen, een voorwaarde op de waarden waar dat nodig is (een opdracht is nieuws als haar status naar "in uitvoering" gaat, niet bij elke wijziging), een rang, de functies die het voor de hele instantie krijgen, en de zinnen voor één en voor meer.
- `OFF_KINDS` en `OFF_TYPES` zijn wat uitdrukkelijk geen nieuws is.
- `SUPERSEDES` zegt welk nieuws eerdere stappen op dezelfde dag overbodig maakt.

Een test eist dat elk type op de lijst staat of er uitdrukkelijk af is.

De rang doet één ding: nieuws van rang 3 dat een lezer alleen via een functie bereikt (en niet omdat hij er zelf bij hoort) vervalt na twee dagen.

Het overzicht legt geen inzage vast: er staan geen waarden van de klassen D, E en F in.

Het overzicht is lokaal. Dezelfde lijst is de natuurlijke basis voor wat een andere instantie later over een gedeelde opdracht mag zien (status en voortgang). Dat is niet gebouwd.

## Lezen als stroom

`GET /api/gebeurtenissen?na=<volgnummer>&limiet=<aantal>` geeft alles na een volgnummer, in volgorde. Het antwoord bevat `gebeurtenissen`, `volgende` (de cursor voor de volgende aanroep) en `meer`.

De feed staat dicht tot `EVENTS_FEED_KEY` is ingesteld. Een systeem biedt die sleutel aan als bearer-token. Zonder instelling verlaat niets de instantie.

Een gebeurtenis in de feed is een CloudEvent volgens het NL GOV-profiel:

| Attribuut | Waarde |
|---|---|
| `specversion` | `1.0` |
| `id` | Het id van de gebeurtenis. |
| `source` | `urn:nld:oin:<OIN>:systeem:grip-<instantie>`. Zonder `INSTANCE_OIN` het adres van de instantie; dat staat CloudEvents toe, het profiel niet. |
| `type` | `nl.grip.<soort>.<wat>`, in het Nederlands: `nl.grip.offerte.aanvaard`. |
| `subject` | Het id van het onderwerp. Nooit een naam of een nummer van een persoon. |
| `time` | Het moment van vastleggen. |
| `datacontenttype` | `application/json` |
| `sequence`, `sequencetype` | Het volgnummer, `Integer`. |
| `data` | Onderwerp, zaak, soort actor, herkomst, correlatie, de hash en de vorige hash. Geen waarden. |

De vertaling van de Engelse namen in de code naar het Nederlands van de interface staat in `grip.events.cloudevents` en nergens anders.

De feed is dun met opzet. Wie meer wil weten, vraagt het ding zelf op en wordt dan beoordeeld door het toegangsmodel.

## Logboek Dataverwerkingen

De standaard vraagt per verwerking van persoonsgegevens een logregel in de vorm van een OpenTelemetry-span, met een verwijzing naar de verwerkingsactiviteit in het register en een gepseudonimiseerde aanduiding van de betrokkene. Verwerkingen over organisaties heen delen een trace-id.

| De standaard | In grip |
|---|---|
| `trace_id` | `correlation_id`. Een inkomend `traceparent` wordt overgenomen. |
| `span_id` | De eerste 16 tekens van het id van de gebeurtenis. |
| `name` | Het type. |
| `start_time`, `end_time` | `occurred_at`. |
| `status` | `Unset`: een gebeurtenis in de stroom is gelukt. |
| `dpl.core.processing_activity_id` | `LOGBOEK_PROCESSING_ACTIVITY_URI`. |
| `dpl.core.data_subject_id` | Een HMAC van `person_id`. |
| `dpl.core.foreign_operation.processor` | `origin_peer`. |

Een gebeurtenis is een dataverwerking in de zin van de standaard als ze over de gegevens van een persoon gaat (`person_id` is gevuld). Dat geldt ook voor inzage.

Gebouwd:

- Het vastleggen van inzage in de klassen D, E en F. Elk antwoord wordt opgebouwd door `build_response`. Komt daarin een veld van een van die klassen terecht, dan schrijft het verzoek één `data.read`: wie, wanneer, welke klassen en via welk verzoek. De waarden zelf worden niet vastgelegd. Gaat het antwoord over één persoon, dan gaat de gebeurtenis over die persoon, en kan die zelf zien wie zijn gegevens inzag. Is het een lijst, dan is het één gebeurtenis met het aantal personen; wie het waren staat in de payload en is alleen voor de beheerder. De standaard vraagt een logregel per betrokkene (`dpl.core.data_subject_id` is verplicht), en `to_log_records` maakt die regels uit de ene gebeurtenis. Dat scheelt in opslag een rij per persoon per keer dat een lijst wordt geopend.
- De vertaling van een gebeurtenis naar een logregel (`grip.events.logboek.to_log_record`).

Nog niet gebouwd:

- Het doorsturen van logregels naar een logboek (OTLP), met bevestiging van ontvangst.
- Een verwerkingsactiviteit per soort verwerking. Nu is er één instelling voor de hele instantie.
- Het meesturen van `traceparent` op uitgaande berichten naar andere instanties.
- Inzage in de klassen A, B en C, en inzage via documenten en exports die niet door `build_response` gaan.

## Bewaren en wissen

Twee instellingen van de instantie, in dagen, met nul voor "nooit": `events.retention_days` voor de waarden in de stroom en `events.read_retention_days` voor wie wat inzag. De taak `python -m grip.events.retention` wist wat ouder is.

Wissen haalt de waarden en het zout van een gebeurtenis weg. De gebeurtenis zelf blijft, met haar afdrukken, zodat de keten controleerbaar blijft. Voor een verzoek om verwijdering van één persoon is er `retention.erase_person`. Elke wisactie is een gebeurtenis `stream.erased` met de reden en het bereik.

Wat blijft staan na wissen: dat er iets gebeurde, wanneer, over welk onderwerp en door wie, als id. Het id van een persoon verwijst na verwijdering van die persoon nergens meer naar.

## Later

- **Abonnementen.** Een systeem meldt een adres en een filter aan en krijgt gebeurtenissen toegestuurd. De stroom is er klaar voor: een afleveraar is een afhandelaar na vastlegging met een cursor per abonnement, zodat hij na een storing inhaalt.
- **De keten verankeren buiten de instantie.** Periodiek de laatste hash delen met een andere partij, bijvoorbeeld een andere instantie over FSC, zodat ook het herschrijven van de hele stroom zichtbaar wordt.
- **De federatie op de stroom.** De uitbak wordt nu gevuld door een transactionele afhandelaar. Hij kan ook de stroom volgen met een cursor.
- **Een logboek aansluiten** volgens Logboek Dataverwerkingen.
