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
| Tegenpartij zonder grip | De offerte gaat als document weg; het akkoord wordt handmatig vastgelegd |
| Interne opdracht | Werk zonder externe opdrachtgever |

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
| Offerte (bevroren momentopname plus hash) | nemer naar gever | push |
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

Een akkoord legt vast: het offerte-id, de hash van de momentopname, wie tekende, namens welke organisatie, wanneer en in welke vorm.

| Vorm | Verloop |
|---|---|
| Eigen grip | Een tekenbevoegde geeft akkoord in de instantie van de opdrachtgever. De instantie ondertekent het bericht (JWS) en verstuurt het |
| Tekenlink | De opdrachtnemer nodigt een e-mailadres uit. Die persoon logt met SSO Rijk in op de instantie van de opdrachtnemer en ziet alleen die ene offerte |
| Pdf | De offerte gaat als document weg. De opdrachtmanager legt het getekende exemplaar vast |

Dit is een gewone elektronische handtekening. Mandaat en bewijskracht moeten met juristen zijn afgestemd voordat de eerste echte offerte zo wordt getekend.

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
