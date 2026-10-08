# 0013 Wies koppelen zonder FSC

Status: aanvaard (2026-10-08)

## Context

Wies houdt bij welke collega op welke opdracht geplaatst is. Grip moet mensen uit Wies halen, en Wies moet de plaatsingen en open rollen uit grip tonen. Wies heeft geen machine-koppelvlak; alles loopt via de browser. Het heeft wel velden voor een externe bron per record.

Een FSC-deelnemer kost zes componenten en tot drie databases. Wies en de DigiGilde-instantie horen bij dezelfde organisatie.

## Besluit

De koppeling tussen grip en Wies loopt in de eerste mijlpaal via een machine-koppelvlak met een sleutel, zonder FSC.

- Grip leest collega's uit Wies en koppelt op e-mailadres.
- Wies haalt periodiek opdrachten, rollen en plaatsingen op uit grip en slaat ze op met bron `grip`.
- Een open rol in grip wordt in Wies een Service zonder Placement.

## Gevolgen

- Wies moet worden aangepast: een bron erbij, een leeskoppelvlak, een synchronisatietaak.
- De regel dat verkeer via FSC loopt geldt tussen organisaties, niet binnen een organisatie.
- Een instantie bij een andere organisatie kan Wies zo niet bereiken. Wordt dat nodig, dan wordt Wies alsnog een FSC-deelnemer.
- Wies kent alleen binaire bezetting. Percentages uit grip gaan niet mee.
- De zichtbaarheidsregels van Wies blijven aan de Wies-kant gelden.
