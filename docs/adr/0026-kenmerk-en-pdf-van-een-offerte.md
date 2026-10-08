# 0026 Een offerte heeft een kenmerk en is een pdf

Status: aanvaard (2026-10-08)

Vult aan: [0020 Een offerte heeft een canonieke vorm en een hash](0020-een-canonieke-vorm-en-een-hash-per-offerte.md)

## Context

Een offerte had als kenmerk haar URI. Dat is een adres voor systemen; een mens kan het niet voorlezen aan de telefoon of in een mail noemen. De download was een HTML-pagina, terwijl een offerte de deur uit gaat als pdf. En het document had geen briefhoofd.

## Besluit

**Kenmerk.** Elke offerte krijgt bij het maken een kenmerk: voorvoegsel van de organisatie, jaar, volgnummer per jaar. Voorbeeld: `DG-2026-0007`.

- Het nummer wordt uitgegeven in dezelfde transactie als de offerte, uit een teller per jaar. Een nummer wordt nooit opnieuw gebruikt. Een offerte die niet gemaakt kan worden, verbruikt geen nummer.
- Een nieuwe offerte voor dezelfde opdracht krijgt een eigen nummer. Er is geen versie-achtervoegsel: twee offertes zijn twee stukken, en "vervangen" staat bij de offerte zelf.
- Het kenmerk hoort bij de canonieke vorm (`kenmerk`) en valt dus onder de hash. Daarnaast kan de maker het kenmerk van de opdrachtgever meegeven (`uw_kenmerk`), en staat de afzender erin (`afzender`).
- Offertes van voor dit besluit kregen een kenmerk in volgorde van maken. Hun vastgelegde inhoud en hash zijn niet veranderd; het kenmerk staat bij die offertes alleen in de kolom.
- De URI blijft het kenmerk voor systemen. Op een scherm of document heet alleen het leesbare kenmerk "Kenmerk".

**Pdf.** De download is een pdf, gemaakt met WeasyPrint uit hetzelfde sjabloon als de weergave in de browser, en alleen uit de vastgelegde inhoud.

- Dezelfde offerte geeft elke keer dezelfde bytes: datum en identificatie in het bestand komen van het moment van maken en van de hash.
- De pdf is getagd (PDF/UA): titel, taal, leesvolgorde, kopcellen. Lettertypen zijn ingesloten.
- WeasyPrint is gekozen boven een bibliotheek die een pdf met coördinaten tekent, omdat één sjabloon voor scherm en bestand geen tweede opmaak vraagt, en omdat het tags, herhaalde tabelkoppen en "pagina x van y" zelf doet. De prijs is een systeembibliotheek (pango) in het image.

**Briefhoofd.** De afzender is de organisatie, niet de naam van de omgeving. Het Rijkslint, het rijkswapen en het huisstijllettertype staan uit tot een organisatie ze instelt, want of zij ze mag voeren bepaalt grip niet. Zonder instelling is het briefhoofd sober en het lettertype Verdana of het dichtstbijzijnde schreefloze lettertype. Zie [De offerte als document](../offerte-document.md).

**Echtheidskenmerk.** De hash heet op scherm en document "echtheidskenmerk", met een uitleg in gewone woorden. Het woord hash staat alleen in de technische regel eronder.

## Gevolgen

- Het contract (`offerte.schema.json`, `momentopname`) moet `kenmerk`, `uw_kenmerk` en `afzender` kennen, en `schalen` op een personeelsregel. Tot die versie er is staan de termen in `PENDING_PROPERTIES` in `services/terms.py`.
- Een ontvangende omgeving neemt het kenmerk over uit de inhoud en geeft geen eigen nummer uit.
- Het image en de CI installeren pango.
