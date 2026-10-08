# Bewijs van een besluit

Bij een akkoord, een afwijzing, een interne goedkeuring en het terugsturen van een offerte maakt grip een bundel: een bestand waarmee is na te gaan wie wat besloot over welk document, zonder toegang tot grip. Het besluit hierachter staat in [ADR 0029](adr/0029-bewijs-van-een-akkoord.md); dat het document een vast bestand is in [ADR 0030](adr/0030-het-bestand-van-een-offerte-ligt-vast.md).

## Wat er in een bundel zit

| Deel | Wat het is |
|---|---|
| `offerte.canoniek_b64` en `vingerafdruk` | De inhoud van de offerte in haar canonieke vorm, en de SHA-256 daarvan |
| `offerte.bestand_b64` en `bestand_sha256` | De pdf zoals die is getoond, en de SHA-256 van het bestand |
| `verklaring.jws` | De verklaring van het besluit, ondertekend door de instantie |
| `aanmelding.id_token` | Het ID-token dat de identiteitsprovider voor dit besluit uitgaf |
| `aanmelding.sleutels` en `ontdekking` | De sleutels van de provider van dat moment, en zijn gegevens |
| `instantie.sleutels` | De publieke sleutels van de instantie |
| `tijdstempel` | Het antwoord van een tijdstempelautoriteit, als de instantie er een heeft ingesteld |

De verklaring zegt: wat (vingerafdruk, hash van het bestand, kenmerk), welk besluit, wie (naam, e-mailadres, kenmerk bij de provider, organisatie zoals de provider die noemt), namens wie, wanneer (aangemeld en ontvangen), hoe (kanaal, of de aanmelding vers was, de gegevens van de nonce) en op welke grondslag.

## Een bundel controleren

```
python -m grip.proof.verify bewijs.json
python -m grip.proof.verify bewijs.json --bestand offerte.pdf
python -m grip.proof.verify bewijs.json --online --tsa-root autoriteit.pem
```

Het commando gebruikt de bundel en verder niets: geen database, geen instellingen, en alleen met `--online` het netwerk. Het stopt met 0 als de bundel in zichzelf klopt en met 1 als iets niet past. Een bundel kan kloppen en toch dingen onbewezen laten; die staan er dan bij.

Wat wordt nagerekend:

1. De inhoud van de offerte past bij de vingerafdruk.
2. De handtekening van de instantie onder de verklaring klopt, en de verklaring gaat over deze offerte.
3. Het pdf-bestand past bij de hash die de verklaring noemt. Met `--bestand` wordt een pdf die je zelf hebt byte voor byte vergeleken.
4. De handtekening van de provider onder het ID-token klopt met de bewaarde sleutels; uitgever en ontvanger zijn de juiste; het token gaat over de persoon uit de verklaring.
5. De nonce in het token is dezelfde als de waarde die opnieuw wordt berekend uit de vingerafdruk, de hash van het bestand, het besluit, het kenmerk en de willekeurige waarde in de verklaring. Daarmee is het token gebonden aan dit besluit over dit document.
6. Het tijdstip van aanmelden ligt vlak voor het besluit (binnen vijf minuten).
7. De tijdstempel, als die er is, is over deze verklaring gezet. Met `--tsa-root` wordt ook de handtekening van de autoriteit gecontroleerd.
8. Met `--online`: de sleutel van de provider staat nu nog bij de provider gepubliceerd.

Dezelfde controle zit achter `POST /api/proof/verify` (voor een persoon van de instantie), `POST /api/signing/verify` (voor wie tekent, ook een uitgenodigde gast) en achter de samenvatting die grip bij een besluit toont. Beide vragen een sessie en weigeren een bundel boven 12 MB. Zonder sessie controleer je met het commando.

## Wat een bundel niet bewijst

Het commando zegt het zelf, per bundel. De vaste punten:

- **De sleutel van de instantie is niet aan een organisatie gebonden.** De instantie heeft hem zelf gemaakt.
- **Het mandaat.** De verklaring noemt het recht of de uitnodiging waarop grip zich baseerde. Of de persoon namens de organisatie mocht beslissen, ligt buiten grip vast.
- **De tijd, zonder tijdstempelautoriteit.** Dan is het de klok van de instantie die het besluit vastlegde.
- **Opnieuw inloggen achter een doorgevende provider.** Meldt de provider de persoon door aan een andere partij, zoals SSO Rijk, dan zegt het tijdstip van aanmelden iets over de sessie bij de provider waar grip mee praat.
- **De sleutels van de provider**, zolang ze niet met `--online` zijn vergeleken of op een andere manier zijn vastgesteld.
- **Een lokale testomgeving.** Een provider op een lokaal adres bewijst niets over een echt persoon.

## Voor wie een scherm bouwt

Een besluit loopt in drie stappen.

1. `POST /api/signing/quotes/{id}/intents` (tekenlink) of `POST /api/proof/intents` (akkoord op een ontvangen offerte, interne goedkeuring). Het antwoord bevat `authorize_url` en `reauthentication` (of er opnieuw wordt ingelogd).
2. Laat de browser naar `authorize_url` navigeren. Het is een volledige paginawissel, geen fetch.
3. De browser komt terug op `return_path` met `?bewijs=<id>` als het besluit is genomen, of `?besluit_fout=<code>` als het niet is genomen. Bij een fout is er niets vastgelegd.

Daarna: `GET .../evidence/{id}` (samenvatting met wat bewezen is en wat niet), `.../bundle` (het bestand) en `.../page` (de akkoordverklaring als pagina), onder `/api/signing/` voor wie tekende en onder `/api/proof/` voor wie de offerte mag lezen.

Foutcodes: `verlopen`, `al_gebruikt`, `offerte_gewijzigd`, `token_ongeldig`, `andere_persoon`, `aanmelding_niet_vers`, `aanmelding_mislukt`, `geen_aanmelding`, `geen_recht`, `geweigerd`, `geen_sleutel`, `provider_onbereikbaar`, `niet_ingelogd`.

## Instellingen van de instantie

| Instelling | Wat het doet |
|---|---|
| `proof.stale_authentication` | `record`: een besluit na een niet-verse aanmelding wordt vastgelegd met die vermelding. `refuse`: het wordt geweigerd |
| `proof.timestamp_authority_url` | Het adres van een tijdstempelautoriteit. Leeg: geen tijdstempel |

Voor een tijdstempel met rechtsgevolg is een gekwalificeerde aanbieder nodig. Wie dat zijn staat op de vertrouwenslijst die de toezichthouder (RDI) bijhoudt en in het overzicht van de Europese Commissie. Grip noemt er geen. Een autoriteit moet eerst worden geprobeerd: het antwoord van een van de twee openbare autoriteiten waarmee is getest, wordt door de gebruikte bibliotheek niet gelezen.

## Een pdf met een persoonlijke handtekening (onderzocht, niet gebouwd)

De sterkste vorm hangt niet van grip en niet van de login af: de persoon ondertekent het pdf-bestand zelf met een certificaat op naam (PAdES). Wat het onderzoek opleverde:

- **Kan het worden gecontroleerd in Python?** Ja. pyHanko valideert handtekeningen in een pdf tegen opgegeven vertrouwensankers, inclusief de keten, intrekking en de varianten voor langdurige geldigheid. De documentatie zegt zelf dat de validatie voor langdurige geldigheid de specificatie niet volledig volgt, en dat de validatie volgens de Europese norm experimenteel is.
- **Wat zou grip controleren?** Dat de handtekening klopt; dat de keten uitkomt bij een root van PKIoverheid; dat het certificaat op het moment van tekenen niet was ingetrokken; dat het een certificaat voor handtekeningen is (onweerlegbaarheid) en geen certificaat voor authenticatie; en dat de ondertekende bytes de bewaarde pdf van de offerte zijn, met alleen de handtekening eraan toegevoegd.
- **Welke certificaten?** PKIoverheid kent per persoon drie certificaten: authenticiteit, vertrouwelijkheid en handtekening. Het handtekeningcertificaat is een gekwalificeerd certificaat in de zin van eIDAS.
- **Staat dat op de Rijkspas?** Volgens een onderzoek in opdracht van het ministerie uit 2019 niet: de Rijkspas droeg toen authenticatiecertificaten van een eigen infrastructuur en geen certificaat om mee te ondertekenen. Dat kan zijn veranderd en moet bij de uitgever van de pas worden nagevraagd. Tot dan is de aanname dat elke rijksambtenaar een pdf gekwalificeerd kan ondertekenen niet houdbaar.
- **Wat het toevoegt.** De persoon tekent met een eigen sleutel op een eigen middel; een derde (de uitgever van het certificaat) staat in voor wie dat is; de handtekening zit in het document zelf en is met gewone pdf-software te controleren. Het bewijs hierboven steunt op een login en op de sleutel van de instantie.

Bronnen:

- pyHanko, validatie van handtekeningen: https://pyhanko.readthedocs.io/en/0.6.1/lib-guide/validation.html
- pyHanko, bekende beperkingen: https://github.com/MatthiasValvekens/pyHanko/blob/0.17.2/docs/known-issues.rst
- Onderzoek naar het gebruik van PKIoverheid (2019): https://www.kennisopenbaarbestuur.nl/site/binaries/site-content/collections/documents/2019/04/19/pkioverheid/onderzoek_stimulering-pkioverheid-innovalor_19-4-2019.pdf
- Certification Practice Statement van een uitgever van PKIoverheid-certificaten: https://certificaat.kpn.com/files/CPS/KPN_PKIoverheid_CPS_v5.2.3.pdf
- Aanbieders van vertrouwensdiensten in Nederland (RDI): https://rdi.nl/onderwerpen/elektronische-vertrouwensdiensten/trust-service-providers

## Vragen voor de juristen

1. Welk niveau van elektronische handtekening is nodig voor een afspraak tussen onderdelen van het Rijk, en voor een opdracht van buiten het Rijk?
2. Hoe kwalificeert een bundel als deze: gebonden aan document en persoon, deels ondertekend door de identiteitsprovider, zonder eigen sleutel van de persoon?
3. Is de verklaring van de ondertekenaar dat hij bevoegd is voldoende, of moet het mandaat worden aangetoond, en waar ligt dat vast?
4. Mag grip het ID-token bewaren zolang de afspraak loopt, en hoe lang daarna? Het bevat naam, e-mailadres en een kenmerk van de persoon.
5. Is een gekwalificeerde tijdstempel nodig, of volstaat de tijd van de instantie?
6. Wat is de status van een offerte waarvan het bestand pas na het maken is vastgelegd?
