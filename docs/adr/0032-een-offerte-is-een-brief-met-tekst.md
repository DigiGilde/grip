# 0032 Een offerte is een brief met tekst

Status: aanvaard (2026-10-08)

Bouwt voort op: [0018 Vacatureformulier en vacaturetekst](0018-vacatureformulier-en-vacaturetekst.md), [0020 Een canonieke vorm](0020-een-canonieke-vorm-en-een-hash-per-offerte.md), [0026 Kenmerk en pdf van een offerte](0026-kenmerk-en-pdf-van-een-offerte.md), [0030 Het bestand van een offerte ligt vast](0030-het-bestand-van-een-offerte-ligt-vast.md)

## Context

Een offerte van grip was een tabel: regels, tarieven en een totaal uit de begroting. De offertes die de organisatie werkelijk verstuurt zijn brieven. Ze beginnen met een aanleiding, beschrijven de opdracht en het team, geven de bedragen, en sluiten met de leveringsvoorwaarden, een contactpersoon en een tekenblok voor beide partijen. Die tekst werd buiten grip in een tekstverwerker geschreven en met de hand naast de bedragen gezet.

Drie soorten inhoud lopen in zo'n brief door elkaar:

| Soort | Voorbeeld | Waar het vandaan komt |
|---|---|---|
| Afgeleid | De regels, tarieven, subtotalen, het totaal, het kenmerk, de datum | De begroting en de offerte zelf |
| Vast | Leveringsvoorwaarden, de zin over wijzigingen, de afsluiting, de adressen | De organisatie; verandert zelden |
| Geschreven | Inleiding, opdracht, opbouw van het team, werkwijze, governance | Een persoon, per offerte |

Wat een opdrachtgever tekent is de hele brief. Tot nu dekte het echtheidskenmerk alleen de bedragen.

## Besluit

**De tekst hoort bij de inhoud van de offerte.** De bevroren inhoud krijgt een onderdeel `brief`: betreft, geadresseerde, aanhef, opening, de onderdelen in volgorde, de afsluiting, de gegevens van de afzender, de tekenblokken en of de bijlage Factuurinformatie meegaat. Het valt onder de canonieke vorm en dus onder het echtheidskenmerk: een komma anders is een andere offerte. Een offerte zonder tekst blijft de tabel van voorheen.

**Tekst is tekst met een paar tekens, geen opmaakcode.** Een onderdeel is platte tekst. Een lege regel begint een alinea, een regel met een streepje is een opsomming, met een nummer een genummerde lijst, met drie hekjes een tussenkop; sterretjes geven vet en cursief. Er is geen HTML. Zo is wat getekend wordt leesbaar zonder grip, en kan een ontvangende instantie het zelf opmaken.

**De tekst in voorbereiding hoort bij de opdracht.** De begroting is het concept van de bedragen; een offerte in voorbereiding (`quote_draft`, een per opdracht) is het concept van de woorden. Bij het maken van een offerte wordt de tekst bevroren. Het concept blijft staan als begin van een volgende offerte.

**De organisatie beheert haar eigen opbouw en vaste teksten.** Onder Beheer staan de onderdelen van een offerte, in volgorde. Een onderdeel met tekst is een standaardtekst; een onderdeel zonder tekst schrijft iemand per offerte, met een aanwijzing wat erin hoort. Een nieuw concept begint met deze onderdelen. Een offerte bevriest de tekst waarmee ze is gemaakt: een gewijzigde standaardtekst geldt voor de volgende offerte.

**De afzender is een instelling van de instantie.** Naam, waar de organisatie onderdeel van is, de eenheid, bezoek- en postadres, het adres voor opdrachten, een contactpersoon en wie tekent staan onder Beheer, in de database. De omgeving geeft alleen de beginwaarde van de naam en de regels van het briefhoofd, zoals bij het voorvoegsel van het kenmerk. Het logo en het lettertype blijven instellingen van de uitrol: dat zijn bestanden.

**Startwaarden per organisatie zijn gegevens, geen code.** Een profiel (`grip/data/profiles`) bevat de gegevens van een organisatie en haar standaardteksten. De beheerder neemt het over met een klik. Een profiel noemt geen personen: contactpersoon en ondertekenaar vult de beheerder zelf in.

**Geen namen van medewerkers in de tekst.** De regel dat een offerte rollen en niveaus noemt en geen personen, geldt ook voor de tekst. Bij het maken wordt elk onderdeel vergeleken met de namen van de mensen in de instantie; een naam weigert de offerte, met de plek. De contactpersoon en de ondertekenaar staan er met opzet op en zijn uitgezonderd.

**Het taalmodel stelt voor, een mens stelt vast.** Per onderdeel dat de organisatie daarvoor openstelt kan het taalmodel een concept opstellen of een passage herschrijven, via dezelfde laag als de vacatureteksten. Een concept is niet vastgesteld tot een persoon het onderdeel opslaat; een offerte met een niet-vastgesteld onderdeel kan niet worden gemaakt. Bij de offerte wordt per onderdeel bewaard of het geschreven, vast of met het model opgesteld is, met welk model en wanneer. Dat staat naast de inhoud en niet in de brief, tenzij de organisatie ervoor kiest het te vermelden.

Naar het model gaan: de kop en de aanwijzing van het onderdeel, de naam van de opdracht, de opdrachtgever en de opdrachtnemer als organisatie, de looptijd, per begrotingsregel de rol, de omvang en de periode, de titels van de beleidsnodes waar de opdracht naar verwijst met de politieke opdracht waaruit ze volgen, de koppen van de offerte, en de tekst van onderdelen die al zijn vastgesteld. Er gaan geen tarieven, bedragen, schalen of categorieen naar het model, en geen namen: tekst met de naam van een persoon uit de instantie wordt niet verstuurd. De bedragen en de standaardteksten worden nooit door het model opgesteld.

**Het document is een brief in de Rijkshuisstijl.** Hetzelfde sjabloon, uitgebreid: het lint met de naam van het ministerie, links de geadresseerde, rechts in een smalle kolom de afzender met adressen, datum en kenmerk, dan betreft, aanhef, de genummerde onderdelen met de tabel waar de offerte de bedragen zet, de afsluiting, het tekenblok voor beide partijen, het echtheidskenmerk en de bijlage Factuurinformatie op een eigen pagina.

## Gevolgen

- De inhoud van een offerte groeit met `brief`. Het koppelvlak tussen instanties moet dit onderdeel opnemen (optioneel, aanvullend); tot dan staan de termen in grip als "in afwachting van het contract".
- Een ontvangende instantie die `brief` nog niet kent, kan de offerte niet verliesvrij tonen. Het echtheidskenmerk klopt wel: dat is over de bytes berekend.
- Een offerte maken wordt een offerte voorbereiden: het scherm toont de afgeleide delen zoals ze komen te staan en laat de geschreven delen invullen, met een voorbeeld dat de echte pdf is.
- De controle op namen kent alleen de mensen in de instantie. Een naam van iemand anders in de tekst ziet ze niet.
- Tekst die naar het model gaat, is een verwerking buiten de instantie. Welke gegevens dat zijn staat in `docs/offerte-document.md`, als tabel, en is in de code afgedwongen door een gesloten lijst van velden.
- Het aanvraagformulier vacature wordt door grip zelf getekend: de tekst van een veld komt uit het lettertype dat het formulier meedraagt, met dezelfde regelafstand en afbreking als het programma waarmee het formulier is gemaakt. Een ingevuld formulier ziet er daardoor in elke viewer hetzelfde uit en houdt de eigen aankruisvakjes van het formulier.
