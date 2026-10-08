# 0036 Een productmerk naast de organisatie

Status: aanvaard (2026-10-08)

## Context

Grip had geen eigen gezicht. In de balk stond de naam van de instantie als tekst, met het product en een aantekening over de omgeving in dezelfde regel ("Grip <organisatie> (voorbeeld)"). Het pictogram van het tabblad was het rijkslogo uit het designsysteem, zodat grip in een rij tabbladen niet te onderscheiden was van elke andere applicatie van de Rijksoverheid. Voor een app op het beginscherm was er geen pictogram.

Tegelijk is grip federatief: elke organisatie draait een eigen instantie, en wat de deur uit gaat (een offerte, een mail, een akkoord) komt van die organisatie en niet van het gereedschap.

Het rijkslogo en de huisstijl zijn voorbehouden aan de Rijksoverheid en aan wie in haar opdracht werkt. Wat de huisstijlrichtlijnen zeggen over een eigen beeldmerk voor een product is niet na te lezen zonder account op rijkshuisstijl.nl.

## Besluit

1. **Twee lagen, overal uit elkaar gehouden.** Het product is grip en is overal gelijk. De organisatie is een instelling van de instantie. Elke plek toont beide op een vaste manier; de tabel staat in [Het merk van grip](../merk.md).
2. **Een ingetogen productmerk.** Een haak die een balk vasthoudt, getekend op een raster met een dikte, in een kleur, in het blauw van het lint. Het is geen logo van een organisatie, staat nooit op de plek van het rijkslogo en nooit op een document van de organisatie.
3. **Het rijkslogo is geen pictogram van grip.** Het pictogram van het tabblad en van de app is het productmerk. Het rijkslogo blijft waar het hoort: op het briefhoofd van een organisatie die het mag voeren.
4. **Een bron.** De tekening staat in `frontend/brand/mark.svg`. Alle pictogrammen komen daaruit met `just brand` en worden vastgelegd in de repo.
5. **Een titel voor elk tabblad:** pagina, organisatie, grip.
6. **De aantekening over de omgeving is een label**, geen deel van de naam van de organisatie.

## Gevolgen

- De naam van de instantie hoort de naam van de organisatie te zijn. Een oudere instelling met "Grip" ervoor en een aantekening tussen haakjes erachter wordt in de schermen uit elkaar gehaald, maar hoort te worden opgeschoond.
- Het script dat het rijkslogo als pictogram uit het designsysteem kopieerde is vervallen.
- De mail en de offerte zijn van de organisatie. Grip noemt zichzelf daar niet, behalve in de uitleg hoe een ontvanger de mail controleert en in een regel onder een bewijs van een akkoord.
- Voor het bijwerken van de pictogrammen zijn librsvg en ImageMagick nodig. Voor het bouwen van de frontend niet.
- Voor een brede uitrol moet bij de huisstijlcoordinator van het departement worden nagevraagd of een productmerk naast het rijkslogo is toegestaan. Tot dan is dit een eigen oordeel.
- Vier richtingen zijn getekend en bewaard, zodat de keuze kan worden herzien zonder opnieuw te beginnen.
