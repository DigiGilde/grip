# De offerte als document

De offerte is het stuk dat de deur uit gaat. Dit document beschrijft hoe het wordt gemaakt en wat een organisatie daarvoor instelt.

## Wat het is

- "Bekijk pdf" toont het bewaarde pdf-bestand in de browser; daar is het ook te downloaden. Er is geen losse weergave als webpagina meer: wat je bekijkt is wat de opdrachtgever krijgt.
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

## De offerte als brief

Sinds [ADR 0032](adr/0032-een-offerte-is-een-brief-met-tekst.md) heeft een offerte tekst. De opbouw volgt de brief die een organisatie van het Rijk verstuurt:

| Deel | Soort | Bron |
|---|---|---|
| Lint, naam van het ministerie | Vast | Afzender onder Beheer, logo uit de uitrol |
| Geadresseerde | Geschreven | Het concept; begint met de opdrachtgever van de opdracht |
| Kolom met afzender, adressen, datum, kenmerk | Vast en afgeleid | Afzender onder Beheer; datum en kenmerk van de offerte |
| Betreft, aanhef, opening | Geschreven | Het concept; de opening begint met de standaardzin |
| Onderdelen zoals inleiding, opdracht, team, werkwijze, governance | Geschreven | Een persoon, per offerte; het taalmodel mag een concept voorstellen |
| Kosten | Afgeleid, met een zin erbij | De begroting, via de rekenmodule |
| Wijzigingen, leveringsvoorwaarden | Vast | Tekstblokken onder Beheer |
| Afsluiting met contactpersoon | Vast | Brieftekst en afzender onder Beheer |
| Tekenblok voor beide partijen | Vast en geschreven | Ondertekenaar onder Beheer; die van de opdrachtgever in het concept |
| Echtheidskenmerk | Afgeleid | De inhoud |
| Bijlage Factuurinformatie | Vast | Aan of uit per offerte |

### Tekst schrijven

Een onderdeel is platte tekst met een paar tekens:

| Je typt | Het wordt |
|---|---|
| Een lege regel | Een nieuwe alinea |
| `- ` aan het begin van een regel | Een punt van een opsomming |
| `1. ` aan het begin van een regel | Een punt van een genummerde lijst |
| `### ` aan het begin van een regel | Een tussenkop |
| `**tekst**` en `*tekst*` | Vet en cursief |

In een standaardtekst vult grip tussen accolades in: `{organisatie}`, `{eenheid}`, `{opdrachtenadres}`, `{contactpersoon}` en `{jaar}`. Dat gebeurt een keer, bij het begin van een concept; daarna is het gewone tekst.

### Afzender en standaardteksten

Onder Beheer, "Afzender en teksten van offertes" (`/beheer/afzender`). De beheerder zet er de organisatie, de contactpersoon, de ondertekenaar, de onderdelen met hun standaardtekst en de opening en afsluiting. Een instantie zonder naam kan de startwaarden van een profiel overnemen; `just quote-profile <naam>` doet hetzelfde vanaf de opdrachtregel.

### Wat naar het taalmodel gaat

Alleen bij "Stel een concept op" en "Herschrijf", en alleen voor een onderdeel dat de organisatie daarvoor heeft opengesteld.

| Gegeven | Gaat mee | Toelichting |
|---|---|---|
| Kop en aanwijzing van het onderdeel | Ja | |
| Naam van de opdracht | Ja | |
| Opdrachtgever en opdrachtnemer | Ja | Als organisatie |
| Looptijd van de opdracht | Ja | |
| Per begrotingsregel: rol, omvang in fte, periode | Ja | |
| Titel, soort, omschrijving, beherende organisatie, status en geldigheid van de contextnodes | Ja | Beleidstekst uit het corpus, geen persoonsgegevens; na de controle op namen |
| De keten omhoog van elke contextnode: elk niveau met de relatie in woorden, titel, soort en omschrijving, tot en met de politieke opdracht (soort, referentie, datum) | Ja | Alle takken; een verwijzing naar een ander corpus alleen met de naam van dat corpus |
| Notities bij de opdracht | Nee | |
| De koppen van de offerte | Ja | |
| Tekst van onderdelen die al zijn vastgesteld | Ja | Hooguit zes; na de controle op namen |
| Bij herschrijven: de gekozen passage en de aanwijzing | Ja | Na de controle op namen |
| Tarieven, bedragen, schalen, categorieen | Nee | Klasse B en D |
| Kostprijs, marge, declarabiliteit | Nee | Klasse E en F |
| Namen van medewerkers, beoogde personen | Nee | Tekst met een naam uit de instantie wordt geweigerd |
| De naam van de contactpersoon bij de opdrachtgever | Nee | Staat in de geadresseerde, niet in wat meegaat |
| Standaardteksten van de organisatie | Nee | |

De context is hetzelfde als wat een persoon ziet in het contextpaneel van de opdracht, opgehaald met dezelfde koppeling (`grip/services/context_brief.py` en `context_fetch.py`). Ze heeft een budget van 6000 tekens: titels, soorten en relaties gaan altijd mee, omschrijvingen eerst van de politieke opdracht en dan van dichtbij naar veraf; wat niet past wordt weggelaten. Is het corpus niet bereikbaar, dan wordt het concept zonder context opgesteld en staat dat bij het concept (`generated.context` is `unreachable`). Het concept van een vacaturetekst krijgt hetzelfde blok.

De lijst is in de code gesloten (`SectionInput` in `grip/services/quote_drafting.py`); een test faalt als er een veld bijkomt.

Een concept telt niet tot iemand het onderdeel opslaat. Bij de offerte wordt per onderdeel bewaard hoe de tekst tot stand kwam. Of dat in de brief staat, kiest de organisatie onder Beheer. De Europese AI-verordening vraagt bij tekst die een taalmodel maakt een vermelding wanneer die tekst wordt gepubliceerd om het publiek te informeren over zaken van algemeen belang, en zondert tekst uit die een mens heeft beoordeeld en waarvoor iemand de redactionele verantwoordelijkheid draagt (artikel 50, vierde lid). Een offerte is geen publicatie voor het publiek en wordt door een persoon vastgesteld. Wat de handreiking van de Rijksoverheid voor generatieve AI hierover zegt, is voor dit besluit niet nagelezen; leg de keuze voor aan wie binnen de organisatie over het gebruik van AI gaat.

