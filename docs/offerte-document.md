# De offerte als document

De offerte is het stuk dat de deur uit gaat. Dit document beschrijft hoe het wordt gemaakt en wat een organisatie daarvoor instelt.

## Wat het is

- "Bekijk" toont de offerte als pagina in de browser. "Download pdf" geeft het bestand.
- Beide komen uit één sjabloon en uit de vastgelegde inhoud van de offerte. Er komt niets bij uit de actuele gegevens, en geen naam van een medewerker.
- De pdf is een getagde pdf (PDF/UA): titel, taal Nederlands, echte tekst in leesvolgorde, kopcellen in de tabel. Lettertypen zijn ingesloten.
- Dezelfde offerte geeft elke keer hetzelfde bestand, byte voor byte: de datum in het bestand is het moment waarop de offerte is gemaakt.
- A4, paginanummer ("pagina x van y") en het kenmerk onder aan elke pagina. De kop van de tabel herhaalt op een volgende pagina; het tekenblok blijft bij elkaar.

De pdf wordt gemaakt met WeasyPrint. Die zet HTML en CSS om naar pdf, zodat de pagina één keer is opgemaakt. Het vraagt de bibliotheek pango op de server; het image installeert die. Op een Mac: `brew install pango`.

## Kenmerk

Elke offerte krijgt bij het maken een kenmerk, zoals `DG-2026-0007`: een voorvoegsel van de organisatie, het jaar en een volgnummer per jaar. Een nummer wordt één keer uitgegeven. Een nieuwe offerte voor dezelfde opdracht krijgt een eigen nummer; er is geen versie-achtervoegsel.

Het kenmerk hoort bij de vastgelegde inhoud en valt dus onder het echtheidskenmerk. De URI van de offerte blijft het kenmerk voor systemen en staat klein onderaan.

"Uw kenmerk" is het eigen kenmerk van de opdrachtgever. Het is optioneel en wordt ingevuld bij het maken van de offerte.

## Instellingen per organisatie

| Instelling | Betekenis | Zonder instelling |
|---|---|---|
| `ORGANISATION_NAME` | De afzender op het document | De opdrachtnemer van de opdracht, anders de naam van de omgeving |
| `LETTERHEAD_LINES` | Waar de organisatie onder valt, als regels onder de naam, gescheiden door een verticale streep | Geen extra regels |
| `LETTERHEAD_LOGO_PATH` | Pad naar de SVG met het Rijkslint en het rijkswapen | Een sober briefhoofd met alleen de naam |
| `DOCUMENT_FONT_DIR` | Map met het lettertype van de Rijkshuisstijl | Verdana, of het dichtstbijzijnde schreefloze lettertype |
| `QUOTE_REFERENCE_PREFIX` | Voorvoegsel van het kenmerk waarmee de omgeving begint. De beheerder wijzigt het daarna onder Beheer, Offertes | Afgeleid van `INSTANCE_KEY` |
| `QUOTE_DEFAULT_CONDITIONS` | Voorwaarden die bij het maken van een offerte worden voorgesteld | Geen voorstel |

## Rijkslogo en lettertype

Het Rijkslint, het rijkswapen en het lettertype van de Rijkshuisstijl zijn alleen bestemd voor de Rijksoverheid en voor wie in haar opdracht werkt. Of een organisatie ze mag voeren, bepaalt grip niet. Daarom staan ze uit tot ze zijn ingesteld.

Het designsysteem levert het beeldmerk en het lettertype mee in zijn pakket. Verwijs daarnaar met de twee instellingen; zet geen kopie in de repo.

Met het lint staat het gecentreerd boven aan de eerste pagina, 23 mm hoog vanaf de rand, met de naam van de afzender ernaast. De maten volgen wat andere overheidssites voor hun pdf's gebruiken.
