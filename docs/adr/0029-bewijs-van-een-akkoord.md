# 0029 Bewijs van een akkoord

Status: aanvaard (2026-10-08)

Vult aan: [0010 Tekenen in drie vormen](0010-tekenen-in-drie-vormen.md), [0020 Een offerte heeft een canonieke vorm en een hash](0020-een-canonieke-vorm-en-een-hash-per-offerte.md), [0025 Interne goedkeuring van een offerte](0025-interne-goedkeuring-van-een-offerte.md)

## Context

Een akkoord was een regel in de database van de instantie: een sessie met een bepaald e-mailadres drukte op "akkoord" bij een offerte met een bepaalde hash. De hash bewijst wat er is geaccordeerd. Wie het deed, berustte op het eigen logboek van de partij die er belang bij heeft, uit een login die uren oud kon zijn, zonder dat een ander er iets voor had getekend. Een derde kon achteraf niet nagaan dat deze persoon op dat moment met dit document instemde, zonder de database te vertrouwen.

Dezelfde vraag speelt bij een afwijzing, een interne goedkeuring en het terugsturen van een offerte.

## Besluit

Een besluit krijgt bewijs dat buiten grip is na te rekenen. Het bestaat uit vijf delen.

**1. Opnieuw aanmelden, gebonden aan het document.** Wie op de knop drukt, gaat voor dit ene besluit opnieuw langs de identiteitsprovider. Grip vraagt daar om opnieuw inloggen (`prompt=login`, `max_age=0`) en geeft een nonce mee die is berekend uit de vingerafdruk van de inhoud, de hash van het pdf-bestand, het besluit, het kenmerk en een willekeurige waarde. Het ID-token dat terugkomt is ondertekend door de provider en bevat die nonce, wie het is en wanneer die persoon zich aanmeldde. Grip bewaart het token zoals het is uitgegeven, de sleutels waarmee het op dat moment te controleren is, en de gegevens van de provider.

**2. De verklaring.** Per besluit is er een document in canonieke vorm (RFC 8785): wat, welk besluit, wie, wanneer, hoe vastgesteld, namens wie en op welke grondslag. De instantie ondertekent het. Deze verklaring is het besluit. De kolommen ernaast (wie tekende, namens wie, wanneer, via welk kanaal) worden eruit gelezen en nergens anders vandaan gevuld.

**3. Een tijd van een derde, als de instantie dat instelt.** Een instantie kan een tijdstempelautoriteit (RFC 3161) opgeven. Die krijgt alleen de hash van de verklaring en ondertekent die samen met haar eigen tijd. Zonder autoriteit is het tijdstip de klok van de instantie, en dat staat dan in het bewijs.

**4. Een bewijs voor beide partijen.** De bundel bevat de offerte in canonieke vorm, het pdf-bestand, de verklaring, het ID-token, de sleutels en een eventuele tijdstempel. Wie tekent kan hem downloaden, samen met een leesbare pagina, de akkoordverklaring. Het is hetzelfde bestand dat de opdrachtnemer bewaart.

**5. Narekenen zonder grip.** `python -m grip.proof.verify bewijs.json` controleert een bundel zonder database en zonder netwerk, en zegt wat bewezen is en wat niet. Zie [bewijs.md](../bewijs.md).

Daarnaast:

- **Bevoegdheid is geen identiteit.** In de verklaring staat op welk recht of welke uitnodiging grip zich baseerde, sinds wanneer en door wie toegekend. Het mandaat zelf ligt buiten grip vast.
- **Niet vers is niet vers.** Laat de provider iemand niet opnieuw inloggen, dan blijkt dat uit het tijdstip van aanmelden in het token. Grip legt dat vast als de zwakkere vaststelling die het is. Een instantie kan instellen dat zo'n besluit wordt geweigerd.
- **Verwijzen, niet kopiëren.** De gebeurtenissen en de auditregel van een besluit noemen de hash van de verklaring. De verklaring zelf en het token gaan niet de stroom in en niet naar een andere instantie.

## Wat elk kanaal bewijst, en op wiens woord

| Kanaal | Wat er ligt | Op wiens woord |
|---|---|---|
| Tekenlink, of akkoord in de eigen instantie, met opnieuw aanmelden | Verklaring van de instantie, ID-token van de provider met de nonce van dit besluit over dit document | De identiteitsprovider staat in voor wie zich aanmeldde en wanneer. De instantie staat in voor de rest |
| Hetzelfde, maar de provider liet niet opnieuw inloggen | Als hierboven, met de vermelding dat de aanmelding niet vers was | De provider staat in voor de identiteit bij dit verzoek, niet voor het moment van inloggen |
| Een instantie zonder identiteitsprovider (lokale ontwikkeling) | Alleen de verklaring van de instantie | Alleen de instantie zelf |
| Akkoord dat binnenkomt van de instantie van de opdrachtgever | Het ondertekende bericht uit het contract tussen instanties | De instantie van de opdrachtgever. Haar eigen bundel blijft bij haar |
| Interne goedkeuring | Verklaring met het recht waarop grip zich baseerde, en het ID-token | Provider en instantie, als bij de tekenlink |
| Getekende pdf, geüpload | Het bestand en wie het vastlegde | Wie het bestand vastlegde. Het bestand zelf wordt niet gecontroleerd |

In elk geval geldt: de sleutel van de instantie is door de instantie zelf gemaakt en niet aan een organisatie gebonden, en zonder tijdstempelautoriteit is de tijd de eigen klok.

## De juridische niveaus

De eIDAS-verordening kent de gewone, de geavanceerde en de gekwalificeerde elektronische handtekening. Dit besluit zegt niet welk niveau de bundel haalt. Het zegt welke eigenschappen de bundel heeft:

- hij is gebonden aan het document: elke wijziging in inhoud of bestand is te zien;
- hij is gebonden aan een persoon, voor zover de identiteitsprovider die vaststelt;
- een deel is ondertekend door een derde (de provider, en als ingesteld de tijdstempelautoriteit);
- de persoon heeft geen eigen sleutel en geen eigen middel om te tekenen: er is geen certificaat op naam.

Welke kwalificatie daarbij hoort, en welk niveau een afspraak tussen onderdelen van het Rijk nodig heeft, is een vraag voor de juristen van de organisatie.

## Gevolgen

- Een besluit kost de gebruiker een keer opnieuw inloggen.
- De terugkeer van de provider komt binnen op het bestaande adres van de login. Er hoeft bij de provider geen adres bij.
- Achter SSO Rijk meldt de provider waar grip mee praat de persoon door aan een andere partij. Het tijdstip van aanmelden zegt dan iets over de sessie bij die provider. Of de persoon daarachter opnieuw zijn middel gebruikte, is niet aangetoond en moet met een echte login worden gemeten.
- De organisatie van de persoon staat alleen in het token als de provider die meegeeft. De koppeling met SSO Rijk kent naam en nummer van de organisatie als gebruikersattribuut; of ze in het token komen is een instelling van de client.
- Een akkoord in de eigen instantie van de opdrachtgever levert een bundel op bij de opdrachtgever. De opdrachtnemer krijgt het bericht uit het contract. De bundel meesturen vraagt een uitbreiding van dat contract.
- De directe routes zonder opnieuw aanmelden bestaan nog. Ze maken geen verklaring.
- Het uploaden van een pdf die iemand met een eigen certificaat heeft ondertekend, en het controleren van die handtekening, is onderzocht en niet gebouwd. Dat is de weg naar een handtekening die niet van grip of van de login afhangt.
- De bibliotheek voor tijdstempels leest het antwoord van een van de twee geprobeerde autoriteiten niet. Voor een instantie een autoriteit instelt, moet die autoriteit zijn geprobeerd.
