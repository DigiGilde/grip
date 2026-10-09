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

## Later gewijzigd (2026-10-09)

De drie vormen zijn gebleven. Erbij gekomen is het bewijs van een besluit: de persoon meldt zich bij het besluit opnieuw aan, de aanmelding is aan het document gebonden en het besluit wordt een ondertekende verklaring die buiten grip te controleren is (ADR 0029). Wie een passkey heeft, bevestigt daarnaast met het eigen apparaat (ADR 0037). Wie de offerte maakte, kan haar niet zelf als opdrachtgever tekenen (ADR 0048). De zin over de gewone elektronische handtekening blijft staan: de kwalificatie is aan de juristen.
