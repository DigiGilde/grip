# 0016 Een instantie is opdrachtgever en opdrachtnemer

Status: aanvaard (2026-10-08)

## Context

Het eerste idee was dat grip alleen de kant van de opdrachtnemer zou bouwen. De eerste mijlpaal vraagt echter een opdrachtgever met een eigen instantie. Organisaties zijn bovendien beide: een uitvoerder ontvangt opdrachten en zet zelf werk door.

Instanties volgen de organisatiestructuur en mogen kleiner zijn dan een geregistreerde organisatie. DigiGilde krijgt een eigen instantie en geeft door aan die van de moederorganisatie.

## Besluit

Er is een codebase. Elke instantie kan opdrachtgever en opdrachtnemer zijn. De opdrachtgeversrol is dun: aanvragen, tekenen en inzien.

Een instantie kan een moederinstantie hebben. De moeder haalt op: opdrachten met status en bedragen, factuurgegevens, bezetting en capaciteit, kosten met overhead en dekking.

## Gevolgen

- Een opdracht die in een keten wordt doorgezet verwijst naar de URI van de bovenliggende opdracht.
- Een instantie heeft naast de TOOI-URI van de dichtstbijzijnde geregistreerde organisatie een eigen kenmerk nodig. De vorm daarvan is niet uitgewerkt.
- Twee instanties binnen dezelfde organisatie delen een OIN. Hoe zij in FSC als aparte deelnemers worden onderscheiden moet bij de proef blijken.
