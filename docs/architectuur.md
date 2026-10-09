# Architectuur

## Aanleiding

Beleid loopt van een politieke wens via doelen naar instrumenten: een wet, een subsidie, een opdracht aan een uitvoerder. Dat deel staat als corpus met nodes in Bouwmeester. Wat daarna gebeurt, de uitvoering van zo'n opdracht, stond bij DigiGilde in een Grist-document. Dat document kende geen verband met de nodes waar een opdracht uit voortkomt en geen verkeer met de opdrachtgever.

Grip vervangt het document en maakt de uitvoering federatief. Elke organisatie of elk onderdeel draait een eigen instantie met een eigen database.

## Domeinen

| Domein | Vraag | Eigenaar |
|---|---|---|
| Corpus | Waarom | Bouwmeester: nodes en edges |
| Opdrachtverkeer | Wat, tussen organisaties | Het koppelvlak tussen instanties |
| Uitvoering | Hoe, binnen een organisatie | Grip |

Grip is leidend voor de opdracht, aan beide kanten. Bouwmeester houdt het corpus en toont opdrachten alleen-lezen bij een node.

Een instantie is symmetrisch: dezelfde software is opdrachtnemer voor de een en opdrachtgever voor de ander. De opdrachtgeversrol is dun (aanvragen, tekenen, inzien).

Een opdracht is lokaal volledig. Het federatieve verkeer is een laag erbovenop, want een interne opdracht heeft geen tegenpartij en een opdrachtgever zonder grip ontvangt de offerte als document.

## Hoe een opdracht ontstaat

| Vorm | Verloop |
|---|---|
| Aanvraag | De opdrachtgever stuurt een aanvraag met context; de opdrachtnemer antwoordt met een offerte |
| Voorstel | De opdrachtnemer stuurt op eigen initiatief een offerte, met weinig of geen context |
| Tegenpartij zonder grip | De offerte wordt aangeboden als document of met een tekenlink in de eigen grip |
| Interne opdracht | Werk zonder externe opdrachtgever |

Hoe een offerte de opdrachtgever bereikt is geen eigenschap van de opdracht. Een offerte wordt eerst uitgegeven en daarna aangeboden, via een kanaal dat op dat moment wordt gekozen: via de grip van de opdrachtgever (alleen als die gekoppeld is), met een tekenlink in de eigen grip, of als document. Een offerte mag vaker en langs meer dan een weg worden aangeboden; elke aanbieding wordt vastgelegd (ADR 0021).

Of een opdracht met een andere instantie wordt gedeeld is een feit dat uit een uitwisseling ontstaat: een aanvraag van of naar die instantie, of een offerte die eraan is aangeboden of ervan is ontvangen. Alleen over een gedeelde opdracht gaat iets naar die instantie, en alleen een gedeelde opdracht is voor haar op te vragen.

## Identiteit

- Een instantie heeft een eigen basis-URI, een eigen kenmerk, een FSC-peer-id en optioneel een moederinstantie.
- Daarnaast draagt ze de TOOI-URI van de dichtstbijzijnde geregistreerde organisatie. Een instantie mag kleiner zijn dan wat organisaties.overheid.nl registreert; voor DigiGilde nemen we aan dat dat zo is.
- Organisaties worden overal op TOOI-URI gekoppeld. Bouwmeester en Wies doen dat al.
- Elke opdracht, offerte en vacature krijgt een URI van de instantie die haar aanmaakt: `{basis}/id/opdracht/{uuid}`.

## Opdrachtverkeer

Elke instantie biedt achter de eigen inway de REST-dienst `grip-opdrachtverkeer` aan, opgezet volgens de API Design Rules. Om een andere instantie aan te roepen stuurt de applicatie een verzoek naar de eigen outway met de header `Fsc-Grant-Hash`. De inway aan de andere kant geeft het peer-id van de aanroeper door, afgeleid van het certificaat.

| Bericht | Richting | Vorm |
|---|---|---|
| Aanvraag met context-URI's | gever naar nemer | push |
| Offerte (canonieke vorm plus hash), wanneer ze via de grip van de opdrachtgever wordt aangeboden | nemer naar gever | push |
| Akkoord of afwijzing, ondertekend | gever naar nemer | push |
| Voortgang | gever haalt op | pull |
| Uitputting en factuurgegevens | gever haalt op, op verzoek | pull |
| Eindrapport | nemer naar gever | push |
| Vacature en aanbod | tussen instanties met een contract | push |
| Doorgifte aan de moeder | moeder haalt op | pull |

Elk bericht heeft een UUID en is idempotent. Uitgaand verkeer gaat via een outbox-tabel en een worker, inkomend via een inbox-tabel. De applicatie blijft daardoor werken als de tegenpartij onbereikbaar is.

De opdrachtgever ziet standaard status en voortgang. Uitputting en factuurgegevens haalt hij zelf op wanneer hij ze nodig heeft, binnen het FSC-contract met de opdrachtnemer. Namen van mensen op de opdracht gaan niet over de organisatiegrens.

## Context uit het corpus

Er komen meerdere Bouwmeester-instanties, bijvoorbeeld een per departement. Grip kent dus niet een vaste Bouwmeester.

- De Bouwmeester-instantie die een node beheert geeft de URI uit: `{corpus-basis}/id/node/{uuid}`. De basis is een duurzaam domein per corpus, geen hostnaam van het hostingplatform, zodat de URI een verhuizing overleeft.
- Elke Bouwmeester publiceert dezelfde FSC-dienst `corpus-context` v1.
- Grip houdt een register bij van corpus-basis naar peer en contract, gevuld vanuit de FSC-directory, en kiest de peer aan de hand van de URI.
- Een opdracht mag naar nodes uit meerdere corpora verwijzen. De context mag ook leeg zijn, bijvoorbeeld bij een voorstel van de opdrachtnemer.

De opdracht draagt alleen URI's, geen kopie van de node. De opdrachtgever kiest nodes in de eigen grip, die daarvoor in het corpus zoekt. De opdrachtnemer haalt de node en de keten omhoog naar de politieke input op bij de Bouwmeester van de URI. Omdat nodes na verstrekking veranderen, vraagt grip ze voor verantwoording achteraf op met een peildatum; Bouwmeester houdt titel- en statushistorie al bij. De peildatum geldt voor titel en status van een node. De keten is de keten van nu: Bouwmeester bewaart geen historie van edges.

In de andere richting haalt Bouwmeester bij een node de bijbehorende opdrachten op uit de grip-instanties.

Verwijzingen tussen corpora onderling, zoals een doel van het ene departement dat bijdraagt aan een doel van het andere, vallen buiten grip. Het contract laat node-URI's uit een ander corpus wel toe.

## Het contract voor nodes

Het koppelvlak is een contract waar elk corpus-systeem aan kan voldoen. Bouwmeester is de eerste implementatie.

- **Contract eerst.** Een OpenAPI 3.1-document voor de dienst en JSON Schema-bestanden (2020-12) voor node, edge en keten. OpenAPI 3.1 gebruikt JSON Schema rechtstreeks, dus er is een definitie.
- **Eigen repo.** De contracten `corpus-context` en `grip-opdrachtverkeer` staan in een neutrale repo, omdat meerdere systemen ze implementeren.
- **De FastAPI-pagina is een weergave.** Ze volgt de code van een implementatie en is daarom geen contract. Elke implementatie serveert het contract wel op `/v1/openapi.json`, met een leesbare pagina erbij.
- **Versies.** Semver, met `/v1` in het pad. De Spectral-regels van de API Design Rules controleren het document.
- **Contracttests in CI.** De door FastAPI gegenereerde beschrijving wordt vergeleken met het contract, en antwoorden worden tegen de schema's gevalideerd.
- **Woordenlijst.** Een vaste kernlijst van node-typen en edge-typen, elk met een URI. Bouwmeester laat nu vrije node-typen en zelfgemaakte edge-typen toe; tussen instanties moeten typen hetzelfde betekenen. Eigen typen mogen in een eigen naamruimte.
- **JSON-LD-context.** Een bestand dat de schema's leesbaar maakt als linked data, voor aansluiting op het federatief datastelsel. RDF en SHACL horen niet bij de eerste mijlpaal.

Node v1 bevat: URI, type, titel, omschrijving, status, geldigheid, beherende organisatie (TOOI-URI), corpus, de keten omhoog naar de politieke input en de peildatum. Per type komt er een kleine uitbreiding bij, zoals de soort politieke input met referentie en de soort instrument.

## Tekenen

Een offerte heeft een canonieke vorm en een hash (ADR 0020). De canonieke vorm is de inhoud in de termen van het contract, als canonieke JSON volgens RFC 8785. Ze wordt bij uitgifte een keer gemaakt en als bytes opgeslagen; de hash is de SHA-256 daarover. Die ene hash staat op het document, op de pagina's van de tekenlink, in elk akkoord en in de berichten tussen instanties. Een ontvangen offerte wordt opgeslagen zoals ze is ontvangen, zodat beide instanties dezelfde bytes en dezelfde hash hebben. Wat een scherm of rapportage toont wordt uit die bytes gelezen.

Een akkoord legt vast: het offerte-id, de hash van de offerte, wie tekende, namens welke organisatie, wanneer en in welke vorm. De vorm zegt hoe er werkelijk is getekend, los van het kanaal waarlangs de offerte is aangeboden.

| Vorm | Verloop |
|---|---|
| Eigen grip | Een tekenbevoegde geeft akkoord in de instantie van de opdrachtgever. De instantie ondertekent het bericht (JWS) en verstuurt het |
| Tekenlink | De opdrachtnemer nodigt een e-mailadres uit. Die persoon logt met SSO Rijk in op de instantie van de opdrachtnemer en ziet alleen die ene offerte |
| Pdf | De offerte gaat als document weg. De opdrachtmanager legt het getekende exemplaar vast |

Naast de inhoud ligt ook het pdf-bestand van een offerte vast: het wordt een keer opgemaakt, bij het maken, en bewaard met een eigen hash (ADR 0030). Bekijken, aanbieden, tekenen en het bewijs gebruiken dat ene bestand. De offerte is een brief: de tekst van de onderdelen hoort bij de inhoud waarover de hash gaat (ADR 0032).

Bij een besluit (akkoord, afwijzing, interne goedkeuring, terugsturen) hoort een bewijs dat buiten grip te controleren is. De persoon meldt zich voor het besluit opnieuw aan, de aanmelding is aan precies dit document gebonden, en het besluit wordt een verklaring die de instantie ondertekent. Wie een passkey heeft, bevestigt daarnaast met het eigen apparaat. Wat een bundel aantoont en wat niet staat in [bewijs.md](bewijs.md); de besluiten zijn ADR 0029 en ADR 0037. Wie de offerte maakte, kan haar niet zelf goedkeuren of als opdrachtgever tekenen (ADR 0048).

Welk niveau van elektronische handtekening dit is, bepaalt grip niet. Mandaat en bewijskracht moeten met juristen zijn afgestemd voordat de eerste echte offerte zo wordt getekend; de vragen staan in [bewijs.md](bewijs.md).

## Hoe de delen binnen een instantie samenhangen

Vier dingen dragen de rest. Wie ze kent, vindt de weg in de code.

**De stroom van gebeurtenissen is de bron van wat er gebeurd is.** Elke wijziging van domeingegevens legt in dezelfde transactie een gebeurtenis vast: wat, wie, wanneer, de oude en de nieuwe waarde, en per veld de gegevensklasse. Een test laat een verzoek falen dat een domeintabel wijzigt zonder gebeurtenis. De geschiedenis van een opdracht, het overzicht voor de beheerder, het nieuws op de startpagina ("Wat is er gebeurd"), de taken en de berichten naar andere instanties lezen allemaal uit die stroom. Een keten van hashes maakt een wijziging achteraf zichtbaar. Zie [gebeurtenissen.md](gebeurtenissen.md), ADR 0028 en ADR 0043.

**Feiten, taken en het verloop van een zaak komen uit een plek.** De takenlaag leidt uit de gegevens feiten af ("er is een offerte", "alle maanden van het kwartaal zijn afgesloten"). Het plan, dat als gegevens bij de code staat, zegt welke taak bij welke feiten ontstaat en door welk feit ze sluit; niemand vinkt een taak af. Uit dezelfde feiten komt het verloop van een zaak: de stappen, waar de zaak staat, wat de volgende stap is en voor wie. De kop van een opdracht of vacature, de kolom "Stand" in een lijst, de takenlijst en een melding op een apparaat kunnen elkaar daardoor niet tegenspreken. Zie [taken.md](taken.md), [werkstromen.md](werkstromen.md), ADR 0024, 0038 en 0044.

**Rekenen gebeurt op een plek, en een datum is de dag van de instantie.** De rekenregels staan in een module zonder database of klok (ADR 0017). Een tarievenkaart geldt van een datum tot een datum en de prijs volgt de dag (ADR 0027). "Vandaag" is overal de kalenderdag van de instantie, standaard in de Nederlandse tijdzone; momenten worden in UTC opgeslagen (ADR 0046). Een test faalt als code een andere klok vraagt.

**Elke toegangsbeslissing loopt door een functie.** Zie [toegang.md](toegang.md).

Daarop rusten de onderdelen:

| Onderdeel | Kern | Meer |
|---|---|---|
| Offerte | Een brief met tekst, een kenmerk, een bewaard bestand, interne goedkeuring waar ingesteld, aanbieden per kanaal, een bewijs bij het besluit | [offerte-document.md](offerte-document.md), [bewijs.md](bewijs.md) |
| Afsluiten en factureren | Vaststellen per maand; aanleveren per factuurperiode van de afspraak als factuurverzoek; de factuur op de aanlevering; een prijswijziging achteraf als opgeslagen naverrekening | ADR 0039, ADR 0047 |
| Vacatures | Aanvraag met het formulier van de organisatie, advies en akkoord, teksten uit een bibliotheek en als werk met een beoordeling | [vacatureteksten.md](vacatureteksten.md), ADR 0018, ADR 0034 |
| Aanmelden | Via de identiteitsprovider van het platform; alleen op een bevestigd adres; een weigering heeft een reden; daarna kan een passkey | [sso-rijk.md](sso-rijk.md), [passkeys-en-installeren.md](passkeys-en-installeren.md) |
| Berichten naar mensen | Mail via een wachtrij; meldingen op het eigen apparaat voor wat op de lezer wacht, zonder namen of bedragen | ADR 0031, [meldingen.md](meldingen.md) |
| Taalmodel | Een servicelaag met een instelling. In productie VLAM; alleen in de lokale ontwikkelmodus kan een eigen model die plaats innemen. Er gaan geen namen en geen gegevens van de klassen D, E en F naar een model | ADR 0018, ADR 0035 |
| Schermen | Gedeelde bouwstenen, een hoofdbalk met zeven plekken, vaste woorden, en metingen die de regels bewaken | [ontwerp.md](ontwerp.md), ADR 0042 |

## Wies

Wies houdt bij wie waar geplaatst is. Wies en de DigiGilde-instantie horen bij dezelfde organisatie, dus dit is geen verkeer tussen organisaties. In de eerste mijlpaal loopt de koppeling via een machine-koppelvlak met een sleutel, zonder FSC. Dat scheelt een volledige FSC-deelnemer.

- Grip leest collega's uit Wies en koppelt op e-mailadres.
- Wies haalt periodiek opdrachten, rollen en plaatsingen op uit grip en slaat ze op met bron `grip`. Wies toont extern beheerde velden al met een slotje.
- Een open rol in grip wordt in Wies een Service zonder Placement en verschijnt zo op de pagina Aanvragen.
- De zichtbaarheidsregels van Wies gelden aan de Wies-kant. Percentages gaan niet mee, want Wies kent alleen binaire bezetting.

## Moeder en dochter

Naast het horizontale verkeer tussen opdrachtgever en opdrachtnemer is er verticaal verkeer van een onderdeel naar de moederorganisatie. DigiGilde krijgt een eigen instantie en geeft door aan de instantie van ODI.

Wat naar de moeder gaat: opdrachten met status en bedragen, factuurgegevens, bezetting en capaciteit, en kosten met overhead en dekking. De moeder haalt het op.

Twee vormen komen voor:

- De opdracht loopt via de moeder, die haar doorzet. Doorzetten in een keten (bijvoorbeeld BZK naar ODI naar DigiGilde) is een opdracht met een verwijzing naar de URI van de bovenliggende opdracht.
- Het onderdeel is zelf tegenpartij van de opdrachtgever en de moeder kijkt mee.

## De naad tussen de twee sporen

Grip wordt in twee sporen gebouwd: spoor A vervangt Grist, spoor B bouwt de federatie. Ze raken elkaar op een plek.

- Spoor A levert een servicelaag: offerte uitgeven, akkoord verwerken, statusovergangen en leesfuncties per gegevensklasse.
- Elke relevante gebeurtenis schrijft spoor A naar `federation_outbox`. Spoor B verstuurt die berichten en schrijft inkomende berichten via dezelfde servicelaag.
- Spoor B raakt geen domeintabellen rechtstreeks. Spoor A weet niets van FSC.
- De contractrepo is de gedeelde waarheid en wordt in beide sporen getest.

## Toegang tussen organisaties

Tussen organisaties regelt een FSC-contract per tegenpartij welke dienst bereikbaar is. Binnen de applicatie bepaalt de beslisfunctie wat een peer per opdracht mag zien; zie [toegang.md](toegang.md). Federatieve Toegangsverlening (FTV) is nog niet aangesloten. De beslisfunctie heeft de vorm van een AuthZEN-verzoek, zodat een extern beslispunt later kan aanhaken.

## Hosting

Elke instantie is een eigen project op ZAD met een eigen database. FSC draait in de eerste mijlpaal in een eigen testgroep met eigen certificaten. Per deelnemer gaat het om een manager, inway, outway, controller en transactielog met tot drie databases, plus een directory en een gedeelde CA voor de groep. Productie-FSC met PKIoverheid volgt later.
