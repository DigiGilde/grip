# 0037 Passkeys, en grip als installeerbare applicatie

Status: aanvaard (2026-10-08)

Vult aan: [0029 Bewijs van een akkoord](0029-bewijs-van-een-akkoord.md)

## Context

Bouwmeester, waar grip zijn stack en zijn login van heeft, is installeerbaar als applicatie en laat mensen na een eerste login met een passkey terugkomen. Grip had geen van beide.

Voor grip is er een tweede reden. Een besluit over een offerte wordt bewezen door de persoon voor dat besluit opnieuw langs de identiteitsprovider te sturen (ADR 0029). Of de provider de persoon dan echt opnieuw laat inloggen, heeft grip niet in de hand. Doet hij dat niet, dan zegt het bewijs alleen wanneer de sessie begon en wanneer het besluit viel.

Wat Bouwmeester doet is overgenomen waar het goed is. Op drie punten wijkt grip af, omdat grip bedragen, schalen en kosten per persoon toont achter toegangsregels per veld.

## Besluit

### Passkeys

Een persoon legt een passkey vast op de pagina Beveiliging, in een sessie die bij de identiteitsprovider begon. Grip bewaart de publieke sleutel en de registratie: wanneer, voor welk adres, en op welke aanmelding de sessie berustte. De geheime sleutel verlaat het apparaat niet.

Elke handeling met een passkey vraagt het apparaat zijn gebruiker te verifieren (vingerafdruk, gezicht of pincode). Bouwmeester vraagt dat bij inloggen alleen als voorkeur.

Een passkey dient twee doelen.

**Opnieuw inloggen.** Met een passkey begint een sessie zonder de identiteitsprovider. Die sessie duurt korter (`PASSKEY_SESSION_TTL_SECONDS`, twaalf uur) en kan alleen beginnen binnen een aantal dagen na de laatste login bij de provider (`PASSKEY_LOGIN_MAX_AGE_DAYS`, dertig). Daarna vraagt grip weer om de provider. Zo kan iemand die de provider niet meer kent, niet met een sleutel blijven binnenkomen. Bouwmeester kent die grens niet. Het inlogscherm noemt geen persoon: het apparaat biedt zelf de passkeys aan die het voor dit adres heeft, en de server zegt niet wie er een heeft.

**Een besluit bevestigen.** Wie een passkey heeft en een offerte accepteert, afwijst, goedkeurt of terugstuurt, bevestigt dat eerst met de passkey. Het apparaat ondertekent een uitdaging die grip berekent uit dezelfde gegevens als de nonce van de provider: de vingerafdruk van de inhoud, de hash van het bestand, het besluit, het kenmerk en een willekeurige waarde. De verklaring noemt de publieke sleutel, de registratie en de hash van wat het apparaat ondertekende; de bundel bevat de ondertekening zelf. `python -m grip.proof.verify` rekent het na.

Dit is een aanvulling. Zonder passkey, of als het apparaat weigert, verloopt het besluit zoals in ADR 0029. Een uitgenodigde ondertekenaar zonder persoonsrecord heeft geen passkey; daar verandert niets.

Wat het bewijst: een apparaat met de geheime sleutel van deze vastgelegde passkey tekende voor precies dit besluit, nadat het zijn gebruiker had geverifieerd. Wat het niet bewijst: welke mens dat was. Dat de passkey bij de persoon hoort, berust op de registratie van de instantie, en zo staat het in het bewijs.

Verder:

- Een nieuwe passkey kan niet worden gemaakt in een sessie die zelf met een passkey begon. Elke passkey gaat zo terug op een aanmelding bij de provider.
- Een ingetrokken passkey houdt zijn rij. Wat ermee is bevestigd, blijft na te rekenen.
- Wie gebruikers beheert, kan een passkey van een ander intrekken, niet maken.
- Vastleggen, gebruiken en intrekken staan in de stroom van gebeurtenissen, zonder sleutelmateriaal.
- Een passkey hoort bij het adres waarop grip draait (`PASSKEY_RP_ID`, afgeleid van `FRONTEND_URL`). Verhuist grip naar een ander domein, dan leggen mensen hun passkeys opnieuw vast.

### Installeerbaar

Grip heeft een manifest en een service worker (`frontend/public/sw.js`, met de hand geschreven, zonder bouwplugin).

- **De worker bewaart nooit een antwoord van de API.** Alles onder `/api/` raakt hij niet aan. Bouwmeester bewaart API-antwoorden een uur en wist ze bij uitloggen; een sessie die verloopt wist niets. Grip bewaart ze helemaal niet, zodat er op een gedeeld apparaat niets is om te lekken.
- Een pagina komt van het netwerk. Alleen zonder netwerk antwoordt de bewaarde schil, en de applicatie zegt dan dat er geen verbinding is. Een deploy bereikt daardoor iedereen bij de volgende keer laden.
- Bestanden van de build worden bewaard: die met een hash in de naam blijvend, de rest wordt op de achtergrond ververst.
- Uitloggen leegt alles wat bewaard is.
- De worker draait alleen in een gebouwde applicatie, niet onder de ontwikkelserver.

De pagina's voor ondertekenaars werken in een gewoon tabblad zoals voorheen.

## Gevolgen

- Nieuwe afhankelijkheden: `webauthn` in de backend en `@simplewebauthn/browser` in de frontend, dezelfde als Bouwmeester.
- Migratie `0031_passkeys`: de tabel `passkey_credential`, en een kolom `passkey` bij een lopend besluit en bij het bewijs.
- De twee routes om met een passkey in te loggen hebben geen sessie nodig en zijn begrensd per adres, in het geheugen van het proces. Dat vervangt geen grens aan de rand van het platform.
- Meldingen op het apparaat (web push) heeft Bouwmeester niet en grip nu ook niet. Het ligt voor de hand voor "er wacht een taak op je"; zie [passkeys-en-installeren.md](../passkeys-en-installeren.md).
