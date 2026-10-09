# Beveiliging

Grip is op 9 oktober 2026 nagelopen zoals een aanvaller dat zou doen, vlak voor de eerste uitrol van een voorbeeldinstantie. Dit document zegt wat er is bekeken, wat er is gevonden en hersteld, wat er nog open staat en wat de organisatie en het platform zelf moeten regelen.

Dit is geen pentest. Het is een doorlichting door de bouwer, met kennis van de code. Een onafhankelijke test blijft nodig voordat er echte gegevens in grip komen; zie [Wat de organisatie nog moet doen](#wat-de-organisatie-nog-moet-doen).

## Hoe er is gekeken

Alles is aangetoond met een test of met een echt verzoek aan een eigen opstelling: een eigen database, een eigen server en het echte nginx-image van de frontend ervoor.

- **Zonder sessie.** Elke route die zonder login antwoordt, de inlogronde, de tekenlink voor een gast, de sleutel van het overzicht voor systemen, de grenzen op aantallen verzoeken en hoe het adres van de beller wordt bepaald.
- **Met zo weinig mogelijk rechten.** Elk leesbaar adres dat de beheerder kan openen (372 adressen over 101 routes) is opnieuw opgevraagd als medewerker, lezer, aanvrager, ingehuurde en planner. Daarnaast: extra velden in verzoeken, het antwoord bij een gelijktijdige wijziging, CSRF op elke wijzigende route en de bezoeker in een voorbeeldinstantie.
- **Invoer die wordt getoond of uitgevoerd.** Teksten met opmaak op het scherm en in pdf's, bestanden die worden geüpload, CSV-uitvoer, logregels.
- **Sleutels en ondertekening.** Waar geheimen staan, de geschiedenis van de repository, de controle van tokens en handtekeningen, passkeys.
- **De rand zoals hij is gebouwd.** De antwoordkoppen van frontend en backend, CORS, de service worker, de API-documentatie, foutmeldingen, de ontwikkelschakelaars en bekende kwetsbaarheden in afhankelijkheden.
- **Overbelasting door een ingelogde gebruiker.** De pdf-maker, het taalmodel, grote verzoeken.

## Wat er is gevonden en hersteld

De ernst volgt deze indeling: **kritiek** is gegevens van een ander of handelen als een ander, daaronder **hoog**, **middel** en **laag**.

Er is niets kritieks gevonden. De toegang per route en per veld hield stand: geen enkel adres gaf een persoon met minder rechten iets wat de toegangsregels niet toestaan.

### Hoog

**Een bezoeker van een voorbeeldinstantie kon blijvend en zonder eigen naam binnenkomen.** Een bezoeker kijkt mee als een voorbeeldpersoon, ook als de beheerder. Daarmee waren er drie wegen om de bezoekerslijst te omzeilen:

1. Een passkey vastleggen voor de voorbeeldpersoon. Daarna kon de bezoeker inloggen zonder de identiteitsprovider, ook nadat het adres van de lijst was gehaald, en zonder dat de eigen aanmelding nog bij de handelingen stond.
2. Een voorbeeldpersoon het eigen mailadres geven. De volgende login gold dan als die van een gewone persoon, buiten de lijst om.
3. De lijst werd alleen bij het inloggen gelezen. Wie eraf werd gehaald, hield de lopende sessie.

Hersteld: een voorbeeldinstantie kent geen passkeys, elke login daar is een bezoek (ook als een voorbeeldpersoon hetzelfde adres draagt), een sessie zonder bezoeker bestaat er niet, en de lijst wordt bij elk verzoek opnieuw gelezen. Tests in `backend/tests/test_example_mode.py`.

### Middel

| Wat | Hoe het misging | Herstel |
|---|---|---|
| Elk verzoek zonder sessie maakte een opgeslagen sessie | Een lus met `curl` op een willekeurig adres onder `/api/` vulde de sessietabel, met een bewaartijd van zeven dagen. Een eigen meting maakte er in een paar minuten ruim tweeduizend. | Een sessie zonder login ontstaat alleen nog op het adres waarmee de browser de toepassing opent, hooguit 120 per minuut per adres, en verloopt na twaalf uur. |
| Geen grens op de grootte van een verzoek | Een JSON-verzoek van honderden megabytes werd helemaal ingelezen voordat er een veld werd bekeken. | Een plafond voor alles: 1 MiB voor gewone verzoeken, 12 MiB voor een upload, 13 MiB voor een bewijsbundel. Het antwoord is 413, ook als de afzender geen lengte opgeeft. |
| Geen grens op het taalmodel | Een ingelogde persoon kon het model onbeperkt aanroepen; een aanroep kon tien minuten open blijven staan. | 40 aanroepen per persoon per uur en 400 per instantie per uur; een aanroep wacht hooguit twee minuten. Een bezoeker telt op de eigen aanmelding. |
| Geen grens op het voorbeeld van een offerte | Er wordt één pdf tegelijk gemaakt. Een maximale offerte kost anderhalve seconde; acht gelijktijdige aanvragen hielden de maker twaalf seconden bezet voor iedereen. | 20 voorbeelden per persoon per minuut. |
| Geen Content-Security-Policy | Frontend en backend stuurden er geen. Een fout in een component had daardoor vrij spel gehad. | De pagina's laden alleen van het eigen adres, zonder script in de paginatekst en zonder inlijsten door een andere site. De API antwoordt met een gesloten beleid. Zie [De koppen](#de-koppen). |
| De koppen ontbraken op weigeringen | Een 401, een geweigerd CSRF-token en een te groot verzoek kwamen zonder beveiligingskoppen terug. | De koppen staan nu om alles heen. |
| Antwoorden van de API zonder regel voor bewaren | Een antwoord met gegevens over personen kon in een tussenliggende cache blijven. | `Cache-Control: private, no-store`, tenzij een route zelf anders kiest. |
| De pdf-maker mocht alles ophalen | Tekst van een persoon wordt volledig ontsnapt, dus er was geen weg naartoe. Maar één vergeten plek had de server een intern adres laten opvragen of een bestand laten lezen. | De maker laadt alleen nog het ingesloten lint en het lettertype. Een test rendert een pagina met een extern plaatje en een lokaal bestand en ziet dat er niets wordt opgevraagd. |

### Laag

| Wat | Herstel |
|---|---|
| De controle van een token nam elk algoritme aan. Een token met HS256 eindigde in een fout die niemand opving, en een token zonder einddatum werd geaccepteerd. Niet te misbruiken, want het token komt van de provider en staat in de sessie op de server. | Alleen handtekeningen met een privésleutel, een einddatum is verplicht, een misvormd token is gewoon ongeldig. |
| Een uitgerolde instantie startte met een kort of bekend sessiegeheim, en met `DEBUG` aan. | Beide worden bij de start geweigerd als `PUBLIC_HOST` is gezet. |
| De tabel van een verzoekgrens groeide zonder einde, en de passkey-routes hadden een eigen kopie van die grens. | De tabel is begrensd en er is één grens. |
| Het getekende document van een offerte werd teruggegeven met de bestandsnaam onbewerkt in de kop; een naam met tekens buiten Latijns schrift gaf een fout. | Dezelfde veilige koppen als bij elke andere bijlage: altijd opslaan, nooit tonen. |
| nginx nam hooguit 1 MB aan, terwijl grip documenten tot 10 MB belooft, en meldde zijn versie. | 13 MB, en geen versie meer in de kop. |
| `/.well-known/security.txt` gaf de startpagina terug. | Het adres verwijst naar de security.txt van de organisatie (`SECURITY_TXT_URL`), of antwoordt 404. |

## Wat standhield

- **Toegang.** De herhaling van 372 adressen als vijf personen gaf alleen wat de regels in [toegang.md](toegang.md) toestaan. Een onbekend en een verboden id geven hetzelfde antwoord waar het bestaan zelf vertrouwelijk is.
- **Extra velden.** Een verzoek met `status`, `version`, `created_by`, `id` of `uri` erbij verandert die niet.
- **CSRF.** Elke wijzigende route weigert zonder token, met het token van een andere sessie en met een afwijkend inhoudstype.
- **De inlogronde.** State, nonce en PKCE (S256) komen van de bibliotheek; het adres om naar terug te keren wordt twee keer gecontroleerd en kan alleen een pad binnen de toepassing zijn; na een login krijgt de sessie een nieuw id; het adres na uitloggen is vast.
- **De tekenlink.** De link bevat geen geheim. Toegang hangt aan het mailadres waarvoor de provider instaat. Een andere aanmelding met dezelfde link ziet niets.
- **Het overzicht voor systemen.** Dicht zolang er geen sleutel is; de sleutel reist alleen in de `Authorization`-kop en wordt in constante tijd vergeleken.
- **Het adres van de beller.** Een vervalste `X-Forwarded-For` verandert niets: via nginx gaf de 21e poging in een minuut een 429, wat er ook in de kop stond.
- **Tekst.** Opmaak van personen wordt overal ontsnapt. Een opdracht met `<script>` in de naam staat als tekst op het scherm, in het rapport en in de pdf. De twee routes die een pagina teruggeven hebben een beleid dat geen script toelaat.
- **CSV.** Cellen die met `=`, `+`, `-` of `@` beginnen krijgen een apostrof ervoor.
- **Bestanden.** Het type wordt aan de inhoud getoetst, de grootte is begrensd, en een bijlage wordt altijd als download teruggegeven met `nosniff` en een gesloten beleid.
- **Passkeys.** Het adres en de partij worden gecontroleerd, verificatie van de gebruiker is verplicht en de teller van de sleutel wordt bijgehouden.
- **Mail.** Een regeleinde in een onderwerp of naam kan geen extra kop toevoegen; de bibliotheek weigert zo'n waarde.
- **Handtekeningen tussen organisaties.** Alleen ES256 en PS256; de sleutel hoort bij de bekende partij en niet bij wat het bericht zelf zegt.
- **Logregels.** Geen tokens, cookies of mailadressen. Een login schrijft de vorm van de gegevens weg, niet de inhoud.
- **Ontwikkelschakelaars.** `DEV_NO_AUTH`, de cookie voor een andere persoon, de diagnosepagina en het ontwikkelmodel doen niets of worden geweigerd zodra `PUBLIC_HOST` is gezet. De API-documentatie staat uit zodra er een identiteitsprovider is.
- **Geheimen.** De hele geschiedenis van de repository is doorzocht op sleutels en tokens: niets gevonden behalve voorbeeldwaarden voor de lokale opstelling, die een uitgerolde instantie nu weigert. Het image van de backend neemt geen `.env` mee.
- **Afhankelijkheden.** Geen bekende kwetsbaarheden in de vastgelegde versies van de backend en de frontend op de dag van de doorlichting.

## De koppen

De frontend (nginx) stuurt op elke pagina en elk bestand:

```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
  img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; worker-src 'self';
  manifest-src 'self'; frame-src 'self' blob:; object-src 'none'; base-uri 'self';
  form-action 'self'; frame-ancestors 'none'
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Referrer-Policy: same-origin
Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()
```

Scripts komen alleen uit eigen bestanden; er is geen `unsafe-inline` en geen `eval` voor scripts. Voor stijlen is `unsafe-inline` nodig: de componenten van het ontwerpsysteem en de toepassing zetten stijlen op elementen. Dit is gemeten in een echte browser tegen het gebouwde image: 28 pagina's doorlopen, geen enkele overtreding, het lettertype laadt en de service worker registreert.

De backend stuurt op elk antwoord `default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'`, behalve op een pdf (de viewer van de browser toont die) en op de twee pagina's met een eigen beleid.

`Strict-Transport-Security` zet grip niet. Dat hoort bij wie het certificaat beheert: het platform.

## Wat open staat

| Wat | Risico in gewone woorden | Ernst |
|---|---|---|
| De grenzen op verzoeken staan in het geheugen van één proces. | Met meerdere kopieën van de backend telt elke kopie voor zich, en na een herstart begint de telling opnieuw. Ze remmen een enkele gebruiker; een echte aanval moet het platform tegenhouden. | middel |
| Staat de ingress van het platform niet in `TRUSTED_PROXIES`, dan heeft iedereen voor grip hetzelfde adres. | Dertig inlogpogingen per minuut voor alle bezoekers samen. Iemand kan het inloggen voor anderen dan even blokkeren. Niemand komt er door binnen. | middel |
| Elke wijziging schrijft naar één keten van gebeurtenissen, achter één slot. | Wijzigingen gaan na elkaar. Een verzoek dat na zijn eerste wijziging lang bezig blijft, laat de rest wachten. Het maken van een offerte is het langste geval: enkele seconden. | laag |
| De lijsten hebben niet overal een maximum. | Bij veel gegevens wordt een lijst traag. Dit is apart gemeten bij realistische omvang; zie het verslag daarvan. | laag |
| Een formulier (pdf) dat een beheerder uploadt, wordt door een bibliotheek gelezen. | Een kwaadaardig gemaakt pdf kan dat lezen traag maken. Alleen wie formulieren mag beheren kan er een aanbieden. | laag |
| De sessiecookie heeft geen `__Host-`-voorvoegsel. | Op een domein dat met andere projecten wordt gedeeld zou een buurproject een cookie met dezelfde naam kunnen zetten. De cookie is ondertekend, dus een vreemde waarde is ongeldig; het ergste is dat iemand wordt uitgelogd. | laag |
| Uitloggen is een gewoon adres (`GET`). | Een andere site kan iemand laten uitloggen. Hinderlijk, niet schadelijk. | laag |
| De code waarmee de provider terugkomt staat in het toegangslog. | Die code is eenmalig en binnen seconden verbruikt. Wie het log mag lezen, kan er niets meer mee. | laag |
| De ketting van gebeurtenissen bewijst volgorde en ongewijzigdheid tegenover wie de keten niet beheert. | Wie de database beheert, kan de hele keten opnieuw schrijven. Zie [gebeurtenissen.md](gebeurtenissen.md) en [bewijs.md](bewijs.md) voor wat dat wel en niet aantoont. | bekend |

## Wat niet is bekeken

- De echte inlogronde bij SSO Rijk. De ronde is tegen een lokale Keycloak en met nagebootste antwoorden getest; het echte gedrag (welke gegevens, hoe vers) blijkt bij de eerste login.
- Het platform zelf: de ingress, TLS, het netwerk tussen de onderdelen, de opslag van geheimen, de back-ups.
- De federatie tussen organisaties met een echte tegenpartij. In een voorbeeldinstantie staat die uit en weigert grip te starten als ze aan staat.
- De pdf in elke browser. Het beleid op pagina's is gemeten in Chrome.
- Mail met een echte mailserver. Een voorbeeldinstantie verstuurt niets; de opbouw van een bericht is in de code gelezen.
- Verschillen in antwoordtijd tussen "bestaat niet" en "geen toegang". De antwoorden zelf zijn gelijk; de tijd is niet gemeten.

## Wat de organisatie nog moet doen

Code kan dit niet regelen. De Baseline Informatiebeveiliging Overheid (BIO) is het verplichte kader; de richtlijn "Maak veilige systemen" van de NeRDS verwijst ernaar.

| Wat | Stand |
|---|---|
| **Een pentest door een onafhankelijke partij** voordat er echte gegevens in grip komen. Geef de tester dit document mee. | niet geregeld |
| **Een security.txt** op het adres van de instantie (RFC 9116, verplichte standaard voor de overheid). Grip verwijst door naar het bestand van de organisatie: zet `SECURITY_TXT_URL` op de frontend. | de doorverwijzing is gebouwd; het adres moet de organisatie aanleveren |
| **Een manier om een kwetsbaarheid te melden** (coordinated vulnerability disclosure), met iemand die de melding leest. Zie ook `SECURITY.md` in de repository. | niet geregeld |
| **Een risicoanalyse en classificatie** van de gegevens (BIO): grip bevat tarieven, inzet en namen van medewerkers. | niet geregeld |
| **Een gegevensbeschermingseffectbeoordeling** voordat er echte personen in staan. | niet geregeld |
| **Afspraken over logging en bewaking**: wie leest het logboek, wie krijgt een signaal bij een reeks geweigerde logins. | niet geregeld |
| **Beheer van sleutels**: wie maakt het sessiegeheim en de ondertekensleutel, waar staan ze, wanneer worden ze vervangen. De stappen staan in [uitrol-zad.md](uitrol-zad.md). | beschreven, niet belegd |
| **Bijhouden van afhankelijkheden**: een geautomatiseerde melding bij een nieuwe kwetsbaarheid in een bibliotheek. | niet geregeld |

## Wat het platform moet leveren

- **TLS en `Strict-Transport-Security`** op het publieke adres.
- **Een grens op verzoeken per adres** aan de rand. De grenzen in grip zijn een tweede lijn.
- **Het adresbereik van de ingress**, zodat het in `TRUSTED_PROXIES` kan. Zonder dat deelt iedereen één grens.
- **Geen andere weg naar de backend** dan via de frontend of de router van het platform. Poort 8090 (de federatie) mag alleen bereikbaar zijn voor de inway.
- **Geheimen als geheim**: het sessiegeheim, de ondertekensleutel, het clientgeheim van de provider en de sleutel van het taalmodel horen in de geheimopslag en niet in gewone variabelen of in het logboek van een uitrol.
- **Een eigen database per instantie**, met back-ups die de organisatie kan terugzetten. Een voorbeeldinstantie deelt nooit een database met echt werk; grip weigert dat bij de start.
- **Een domein zonder buren** als dat kan. Op een gedeeld domein blijven de cookies bij het eigen adres, maar een eigen domein sluit meer uit.

## Voor de eerste uitrol

Niets van wat open staat hoeft de eerste uitrol van een voorbeeldinstantie tegen te houden. Twee dingen horen bij die uitrol zelf:

1. Zet `TRUSTED_PROXIES` op het bereik van de ingress en van de frontend, en controleer in het logboek dat een login het adres van de bezoeker laat zien en niet dat van de proxy.
2. Houd `EXAMPLE_VISITORS` zo kort als kan. Wie op de lijst staat, kan alles in de voorbeeldinstantie zien en wijzigen tot de nachtelijke terugzetting.

Voor een instantie met echte gegevens geldt de tabel onder [Wat de organisatie nog moet doen](#wat-de-organisatie-nog-moet-doen): eerst de pentest en een meldpunt.
