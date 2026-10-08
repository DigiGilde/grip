# 0010 Tekenen in drie vormen

Status: aanvaard (2026-10-08)

## Context

De opdrachtgever moet een offerte digitaal kunnen tekenen. Niet elke opdrachtgever draait grip, en niet elke opdrachtgever heeft een Rijksaccount. Een externe ondertekendienst was een optie.

## Besluit

Een akkoord legt vast: het offerte-id, de hash van de momentopname, wie tekende, namens welke organisatie, wanneer en in welke vorm. Er zijn drie vormen:

1. **Eigen grip.** Een tekenbevoegde geeft akkoord in de instantie van de opdrachtgever. Die instantie ondertekent het bericht (JWS) en verstuurt het.
2. **Tekenlink.** De opdrachtnemer nodigt een e-mailadres uit. Die persoon logt met SSO Rijk in op de instantie van de opdrachtnemer en ziet alleen die ene offerte.
3. **Pdf.** De offerte gaat als document weg. De manager van de opdracht legt het getekende exemplaar vast.

Er komt geen externe ondertekendienst.

## Gevolgen

- Dit is een gewone elektronische handtekening. Mandaat en bewijskracht moeten met juristen zijn afgestemd voor de eerste echte offerte.
- De tekenlink laat mensen van buiten de organisatie inloggen op een instantie. Hun toegang is beperkt tot een offerte en loopt via dezelfde beslisfunctie.
- Bij de pdf-vorm controleert grip de handtekening niet. Het akkoord rust dan op de vastlegging door de manager.
- Elke instantie heeft een eigen sleutel voor het ondertekenen van berichten. Beheer en rotatie daarvan zijn niet uitgewerkt.
