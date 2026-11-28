# 0061 Een bericht dat niet aankomt, blijft het proberen en valt op

Status: voorgesteld (2026-11-28)

## Context

Op het platform vroeg MOZa voorbeeld een kostenpost aan bij Voorbeeldgilde voordat die instantie MOZa voorbeeld kende. Voorbeeldgilde antwoordde met HTTP 403, "Deze peer is niet bekend bij deze instantie". De outbox zag elke 4xx van 400, 403, 404, 409, 410 en 422 als definitief. Het verzoek stond daarna als geweigerd en ging verloren tot iemand het zag en opnieuw aanvroeg.

Een 403 of 404 tussen grip-instanties zegt vaak alleen dat de andere kant nog niet zover is: de ontvanger kent de afzender nog niet, of heeft nog niet waar het bericht over gaat. Dat lost zich op zodra de beheerder aan de andere kant de koppeling legt. Ook een tijdelijke storing hoort niet ongemerkt te blijven. Na twaalf pogingen in ongeveer vijf uur gaf de outbox het op; de kostenpost stond dan op "Niet aangekomen", maar wie de koppeling beheert, kreeg geen signaal.

## Besluit

**Wat definitief is.** Alleen een antwoord dat zegt dat het bericht zelf niet klopt of botst, is meteen definitief: 400, 409, 410 en 422. Herhalen helpt dan niet. Al het andere dat geen 200 of 201 is, is tijdelijk: geen verbinding, geen antwoord op tijd, 5xx, 401, 403, 404, 429, elke andere code, en een ontbrekende instelling (geen outway, geen grant hash, een peer buiten de groep).

**Hoe lang.** Een tijdelijke fout wordt opnieuw geprobeerd tot `FEDERATION_RETRY_DAYS` (standaard 7) dagen na de eerste mislukte poging. De pauze begint bij 30 seconden, verdubbelt per poging en is hooguit vier uur. De laatste poging valt op het einde van die periode. Daarna is het bericht definitief: niet afgeleverd. `FEDERATION_MAX_ATTEMPTS` vervalt.

**Opnieuw versturen.** De beheerder kan een definitief bericht opnieuw in de wachtrij zetten, bij Beheer, Koppelingen. Het is hetzelfde bericht, met hetzelfde id: een ontvanger die het weigerde, heeft het niet bewaard, en een ontvanger die het toch had, antwoordt dat het er al is. De periode van zeven dagen begint opnieuw. Waar het bericht over gaat, wacht weer: een aangevraagde kostenpost staat weer op "Wacht op". Een offerte en de berichten van een opdrachtgever lezen de stand van het bericht zelf en volgen vanzelf. Wacht dat niet meer op het bericht, omdat de kostenpost weg is of een nieuwer verzoek het verving, dan gaat het niet opnieuw.

**Niet meer versturen.** De beheerder kan een definitief bericht ook opzij zetten. Het blijft definitief, waar het over gaat houdt het antwoord dat het kreeg, en het telt niet meer als bericht dat niet aankomt. Dat is de weg voor een bericht dat de ontvanger voorgoed weigert, of dat niet meer nodig is.

Opnieuw versturen en niet meer versturen staan bij Beheer, Activiteit, als wijziging van de koppeling, met wie het deed.

**Wat opvalt.** Een bericht valt op vanaf de derde mislukte poging op rij, of meteen als het definitief is.

- Spoor B meldt na elke ronde van de outbox per peer aan een service van spoor A wat niet aankomt: sinds wanneer, hoeveel berichten, of er een definitief is, tot wanneer grip het probeert en de reden als code uit een vaste lijst. Spoor A bewaart dat in een eigen tabel, een rij per peer zolang er iets niet aankomt, en legt elke wijziging vast als gebeurtenis. De naad van ADR 0015 blijft: spoor B raakt de tabel niet zelf, de takenlaag kent geen federatie.
- Wat de ontvanger antwoordde, blijft in de outbox, voor het logboek. Niemand krijgt het te zien. Het scherm en de taak tonen alleen de reden in woorden van grip.
- De beheerder krijgt per peer een taak zolang berichten aan die peer niet aankomen. De taak hoort bij de instantie zelf: een nieuwe soort zaak zonder pagina en zonder verloop, waarvan alleen wie de instantie beheert de taken leest. Zolang grip het nog probeert, is de knop "Test de verbinding". Is een bericht zeven dagen geprobeerd, dan wordt het "Opnieuw versturen"; heeft de ontvanger het voorgoed geweigerd, dan "Niet meer versturen". Komt alles aan of staat wat niet aankwam opzij, dan is de taak klaar.
- Beheer, Koppelingen toont bij een peer waar iets niet aankomt "Berichten komen niet aan", en in de peer de berichten die niet aankomen: wat voor bericht, waarom, sinds wanneer, en tot wanneer grip het probeert of dat het definitief is.

## Gevolgen

- Een verzoek dat werd verstuurd voordat de andere kant de afzender kende, komt aan bij de eerste poging nadat die de koppeling heeft gelegd. Zolang staat een kostenpost op "Wacht op" en is het totaal onvolledig, hooguit zeven dagen lang.
- Een peer die een week lang niet antwoordt, houdt de outbox bezig met een poging per vier uur per bericht. Een ronde blijft zo lang als de time-out per bericht hem maakt.
- Een voorbeeldinstantie leegt elke nacht de outbox en de taken. Daar speelt de periode van zeven dagen niet; een bericht wordt na de reset opnieuw gemaakt en verstuurd (ADR 0054).
- Een bericht aan een uitgeschakelde peer wordt ook zeven dagen geprobeerd. Of de outbox zo'n peer moet overslaan, is niet uitgezocht.
- Een taak die opnieuw opengaat omdat er weer iets niet aankomt, houdt haar id. Wie al een melding over die taak kreeg, krijgt geen tweede.
- De code van de reden staat aan beide kanten van de naad. Een test houdt de lijsten gelijk.
- Een bericht dat al definitief was voor deze wijziging, krijgt bij de migratie zijn reden en staat meteen opzij. Wat er van zo'n bericht werd, was toen al afgehandeld, dus een upgrade opent er geen taak voor.
- Een bericht over een kostenpost die weg is, blijft definitief tot de beheerder het opzij zet. De domeinlaag zet het niet zelf opzij.
