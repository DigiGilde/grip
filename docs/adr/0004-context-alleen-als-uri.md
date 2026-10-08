# 0004 Context gaat alleen als URI mee

Status: aanvaard (2026-10-08)

## Context

Een opdracht komt voort uit nodes in een corpus: een politieke input, een doel, een instrument. De opdrachtnemer moet die context kunnen zien. Dat kan door een kopie van de keten in de opdracht mee te sturen, of door alleen te verwijzen.

Soms is er weinig of geen context, omdat het initiatief bij de opdrachtnemer ligt.

## Besluit

Een opdracht draagt alleen URI's naar nodes. Er gaat geen kopie mee. De lijst mag leeg zijn.

De opdrachtnemer haalt de node en de keten op bij het corpus van de URI. Voor verantwoording achteraf gebeurt dat met een peildatum.

## Gevolgen

- De opdrachtnemer heeft leestoegang tot het corpus van de opdrachtgever nodig. Elk corpus wordt daarmee een deelnemer in de FSC-groep.
- Is het corpus onbereikbaar of de toegang ingetrokken, dan ziet de opdrachtnemer alleen de URI.
- Nodes veranderen na verstrekking. De toestand op een eerder moment is alleen terug te halen voor wat het corpus aan historie bijhoudt. Bouwmeester bewaart nu de historie van titel en status, niet van de edges.
- Een opdrachtgever kan later nodes toevoegen aan een opdracht die zonder context begon.
