# 0054 Voorbeeldinstanties federeren in een besloten groep

Status: voorgesteld (2026-10-10)

## Context

[ADR 0050](0050-een-voorbeeldinstantie-is-een-eigen-soort-instantie.md) maakt federatie voor een voorbeeldinstantie een startfout: een voorbeeld wisselt niets uit. Sinds [ADR 0053](0053-een-gegeven-heeft-een-eigenaar-elders-een-verwijzing.md) bewaart een Grip geen kopie van wat een ander bezit, maar leest het federatief. Een online demo met drie voorbeeldinstanties laat zonder federatie het belangrijkste niet zien: een kostenpost bij een leverancier blijft "niet op te halen", en een aanvraag komt nergens aan.

Het programma MijnOverheid Zakelijk draait al een gedeeld FSC-testnet op ZAD: OpenFSC met een eigen test-CA, één directory, per peer een eigen project, certificaten als attachments en TLS in de pod.

## Besluit

**Voorbeeldinstanties mogen federeren, alleen met elkaar.** Ze vormen een eigen FSC-groep met een eigen test-CA en een eigen directory, los van elke groep voor echt werk. Wat ADR 0050 verder zegt blijft gelden: geen mail, geen Wies, geen uitvoer naar buiten, alles draagt "Voorbeeld".

**De grens dwingt de server af, in beide richtingen.** Een voorbeeldinstantie start alleen met federatie als de groep is ingesteld als voorbeeldgroep. Ze accepteert en verstuurt alleen berichten naar peers die in haar register als voorbeeld zijn gemarkeerd. Een instantie voor echt werk weigert een peer die als voorbeeld is gemarkeerd, en een voorbeeldinstantie weigert een peer die dat niet is.

**Elke voorbeeldinstantie is een eigen peer.** De identiteit van de aanroeper blijft de FSC-peer (ADR 0007): één manager per instantie, geen gedeelde peer.

**De opzet volgt het MOZa-testnet.** Images van OpenFSC zoals ze worden geleverd, een dun wrapper-image dat eerst migreert, configuratie met omgevingsvariabelen en attachments, een directory-project met een manager in directorymodus. Wat we overnemen staat in `deploy/zad/fsc/`, met een verwijzing naar de bron.

**De voorbeelden blijven samen kloppen.** Alle voorbeeldinstanties gaan op hetzelfde uur terug naar hun beginstand. Een verwijzing die bij het vullen ontstaat, wacht op de eigenaar en wordt na de reset opnieuw verstuurd (ADR 0053).

## Gevolgen

- ADR 0050 krijgt een verwijzing naar dit besluit; de startfout geldt alleen nog voor federatie buiten een voorbeeldgroep. `EXAMPLE_FSC_GROUP` noemt de groep en is buiten een voorbeeldinstantie zelf een startfout.
- Een peer draagt de markering `is_example`, te zien en te zetten onder Beheer > Koppelingen. De controle zit op twee plekken die alles dekken: de outwayclient voor elke aanroep naar buiten (outbox, opvragen, sleutels, verbindingstest) en de peer-afhankelijkheid van de listener voor elke aanroep naar binnen. Voor het domein bestaat een peer aan de andere kant niet.
- Een tweede signaal, los van het register: een voorbeeldinstantie neemt een aanroep alleen aan als het FSC-toegangstoken dat de inway doorgeeft in haar eigen groep is uitgegeven (de claim `gid` uit FSC Core). Dat steunt op hetzelfde vertrouwen als het peer-id in de kop. Niet gekozen: een markering in de sleutelset (JWKS) van een instantie. Dat is een wijziging van het contract, een instantie haalt die sleutelset alleen op om een handtekening te controleren, en een instantie die zich niet als voorbeeld meldt, valt er niet mee op. Een instantie voor echt werk heeft als tweede lijn FSC zelf: haar inway vertrouwt de test-CA van de voorbeelden niet.
- Het peerregister van een voorbeeldinstantie blijft bij de reset staan: het is de koppeling met de andere voorbeelden, geen voorbeeldgegeven. In de eerste tien minuten van het resetuur verstuurt een voorbeeldinstantie niets, zodat geen verzoek aankomt bij een instantie die nog terug moet en daarna verdwijnt.
- Waar de andere voorbeelden staan, zegt `EXAMPLE_INSTANCE_URIS`; zonder die instelling gelden de adressen van de lokale opstelling.
- Op ZAD draait elke voorbeeldinstantie als eigen uitrol in het project van de voorbeeldinstantie, met een eigen database; de directory is ook een uitrol. Het project krijgt acht onderdelen extra: per instantie manager, controller, inway, outway, transactielog en de listener van grip, plus de directory en haar overzicht. Zie [uitrol-zad.md](../uitrol-zad.md#voorbeeldinstanties-met-federatie).
- De sleutel van de test-CA staat niet op een werkplek. Waar hij wel staat, is een open punt.
- Aansluiten bij het testnet van MOZa of de demogroep van OpenFSC in plaats van een eigen groep blijft mogelijk; dat vraagt hun akkoord.

## Later gewijzigd (2026-11-27)

Bij het inrichten van de groep op ZAD bleek het platform anders te werken dan gedacht: een bijlage hoort bij een onderdeel en niet bij een uitrol, en de beheer-API's van een peer zijn alleen binnen zijn uitrol bereikbaar. Het besluit blijft; zo wordt de groep daar ingericht.

- **Certificaten per peer, niet per uitrol.** De uitrollen van het project delen de bijlagen van manager, controller, inway, outway en transactielog. Elke peer heeft daarom eigen paden in de pod (`/etc/fsc/<k>/`), en de instellingen van een uitrol wijzen naar die van de eigen peer. Een pod bevat zo ook de sleutels van de andere peers in het project. In deze besloten voorbeeldgroep is dat aanvaard, in een groep voor echt werk niet.
- **Elke peer richt zichzelf in, en de groep tekent verbindingen bij aankomst.** In de uitrol van elke peer draait een bootstrap (`fscboot-<k>`, zoals bij de berichtenbox van MOZa) die de dienst registreert en publiceert en een verbinding vraagt met de dienst van elke andere peer. Het project krijgt zo per peer een onderdeel extra. De managers van de peers tekenen een verbindingscontract zodra het binnenkomt (`AUTO_SIGN_GRANTS=serviceConnection`). Daarmee valt het moment weg waarop een aanbieder beslist wie hij toelaat: in deze groep zit alleen wie van de test-CA een certificaat kreeg. In een groep voor echt werk blijft dat een besluit van de aanbieder.
- **Elke instantie een eigen sleutel, per uitrol.** `FEDERATION_SIGNING_KEY` komt als instelling op `component-2` en `federation` van de uitrol, niet als bijlage: een bijlage zou in elke uitrol gelden.

Het open punt over de sleutel van de test-CA is gesloten: hij hoeft niet bewaard te worden. De groep is een voorbeeld; is er een nieuw certificaat nodig, dan maakt `pki.sh --fresh` een nieuwe groep, met nieuwe bijlagen en lege FSC-databases. De sleutel gaat nooit in de repo en niet naar het platform. Zie [uitrol-zad.md](../uitrol-zad.md#voorbeeldinstanties-met-federatie).
