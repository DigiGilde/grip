# 0030 Het bestand van een offerte ligt vast

Status: aanvaard (2026-10-08)

Herziet op een punt: [0026 Een offerte heeft een kenmerk en is een pdf](0026-kenmerk-en-pdf-van-een-offerte.md)

## Context

Van een offerte lag de inhoud vast, met een vingerafdruk. De pdf werd bij elk verzoek opnieuw opgemaakt, met de instellingen van dat moment: het lint, het lettertype, de naam van de afzender, het sjabloon. ADR 0026 ging ervan uit dat dezelfde offerte elke keer dezelfde bytes geeft. Dat klopte alleen zolang de instellingen niet veranderden. Een server die zonder de instelling voor het lint was herstart, gaf dezelfde offerte als een ander document.

De vingerafdruk bewijst de inhoud. Wat een opdrachtgever in handen heeft, leest en tekent, is een bestand. "Welk document is getekend" moet te beantwoorden zijn met de bytes.

## Besluit

De pdf van een offerte wordt een keer opgemaakt, op het moment dat de offerte wordt gemaakt, en bij de offerte bewaard met een eigen SHA-256 over het bestand.

- Elke weergave, download, aanbieding, tekenpagina en bewijsbundel geeft de bewaarde bytes. Er wordt niets opnieuw opgemaakt.
- Lukt het opmaken niet, dan wordt de offerte niet gemaakt. Er komt geen kenmerk vrij en er blijft niets achter.
- Een wijziging van briefhoofd of sjabloon geldt alleen voor offertes die daarna worden gemaakt.
- De verklaring van een besluit noemt beide: de vingerafdruk van de inhoud en de hash van het bestand. De nonce van het opnieuw aanmelden is over beide berekend. De bundel bevat het bestand, en de controle rekent beide na.

**Waar de bytes staan.** In het bestaande mechanisme voor bewaarde documenten, met de offerte als eigenaar. Dat houdt bestanden al apart van de rij waar ze bij horen (de inhoud wordt alleen geladen als erom wordt gevraagd), controleert soort en grootte, en bewaart ook de getekende offerte en de ontvangen factuur. De offerte zelf draagt de verwijzing en de hash. Een kolom met de bytes op de offerte zou bij elke lijst van offertes meekomen, of een eigen uitzondering vragen.

**Drie herkomsten, eerlijk vastgelegd.**

| Herkomst | Wanneer | Wat het betekent |
|---|---|---|
| Bij het maken | De offerte is hier gemaakt, na dit besluit | Het bestand is het document zoals het toen was |
| Na het maken | Een offerte van voor dit besluit | Het bestand is een keer opgemaakt met de instellingen van dat latere moment, en ligt vanaf dan vast. Bij de offerte staat "document vastgelegd na het maken", met de datum |
| Bij ontvangst | Een offerte die een andere instantie stuurde | Het contract tussen instanties draagt de inhoud, niet het bestand van de afzender. Dit is de eigen opmaak van die inhoud, vastgelegd bij het eerste gebruik |

Een offerte van voor dit besluit krijgt haar bestand de eerste keer dat erom wordt gevraagd. Dat is een feit dat wordt vastgelegd: wanneer, en dat het er eerder niet was.

## Gevolgen

- Een offerte maken duurt een fractie langer, en kan niet op een server waar de opmaakbibliotheek ontbreekt.
- Het antwoord met het document draagt de hash van de bytes in de kop `X-Document-SHA256`.
- Voor een ontvangen offerte bewijst de hash van het bestand niets over wat de afzender zag. Wil je dat, dan moet het bestand of zijn hash met het bericht meekomen: een uitbreiding van het contract.
- Het bestand van een oude offerte is niet het document dat destijds is getoond. Dat valt niet meer te herstellen, alleen eerlijk te vermelden.
