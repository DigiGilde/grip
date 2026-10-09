# 0049 Een opslag op een verouderde versie wordt geweigerd, op een manier voor elk formulier

Status: aanvaard (2026-10-09)

## Context

Twee mensen kunnen hetzelfde gegeven tegelijk open hebben. Bij een begrotingsregel, een inzet of een tarief won de laatste die bewaarde, zonder melding. Onderdelen van een offerte en vacatureteksten weigerden zo'n opslag al, elk op een eigen manier.

## Besluit

**Een gegeven dat mensen in een formulier wijzigen, telt zijn wijzigingen.** Het model krijgt de mixin `Versioned` (`grip/models/_columns.py`): een kolom `version` die bij elke wijziging vanzelf ophoogt.

**Het formulier stuurt mee waar het van uitging.** De kop `If-Match` draagt het id van het gegeven en de versie die het formulier las. Een middleware zet die waarde klaar voor het verzoek; de dienst roept `stale.check(session, rij, "deze begrotingsregel")` aan voordat ze wijzigt.

**Een oudere versie is een weigering, geen samenvoeging.** Het antwoord is 409 met de code `StaleWriteError`, een zin met wie het gegeven intussen wijzigde en wanneer, en de velden `changed_by` en `changed_at`. Er wordt niets overschreven.

**Het formulier houdt wat de lezer invulde.** De hook `useStaleRecord` en het onderdeel `ConflictPanel` in `@/ui` halen het gegeven opnieuw op en tonen per veld wat er nu staat naast de eigen invoer. De lezer kiest: de eigen wijziging bewaren, of de andere overnemen.

**Zonder de kop is er geen controle.** Een aanroep van een ander systeem of een script werkt zoals voorheen.

## Gevolgen

- Een nieuw formulier dat een opgeslagen gegeven wijzigt gebruikt deze onderdelen en bouwt geen eigen variant.
- Een nieuw model dat zo gewijzigd wordt krijgt de mixin en een migratie voor de kolom.
- De kolom `version` is intern: ze zit in het antwoord om teruggestuurd te worden en hoort in geen momentopname van een offerte.
- Wie het gegeven wijzigde komt uit de gebeurtenissenstroom. Staat de wijziging daar onder een ander onderwerp dan het gegeven zelf (een tarief staat onder de kaart en de categorie), dan geeft de dienst dat onderwerp mee.
- Een afgesloten maand heeft geen eigen controle: een wijziging in een gesloten maand wordt al geweigerd.

## Aanvulling: gegevens die ook het systeem schrijft, en de lijst per soort

**Een gegeven dat ook het systeem schrijft, telt alleen wat mensen wijzigen.** Een persoon wordt bij elke aanmelding bijgewerkt, een taak door de voortgang van het werk, een organisatie door de koppeling met het register. Zou elke schrijfactie tellen, dan kreeg een formulier een weigering zonder dat iemand iets wijzigde. Zo'n model krijgt de mixin `EditCounted`: dezelfde kolom `version`, die alleen ophoogt waar een dienst na de controle `stale.touch(rij)` aanroept. `Versioned` blijft voor gegevens die alleen mensen wijzigen.

**Een gegeven zonder eigen id heeft een naam.** De afspraken over factureren heten `terms:<opdracht>`, een gedeeld tekstonderdeel `shared:<sleutel>`, het target van een persoon `target:<persoon>:<jaar>`. De instellingen van de omgeving worden samen bewaard en zijn één geheel met de naam `instance-settings`.

**Een formulier dat niet per veld vergelijkt gebruikt `useStaleForm`.** Het toont wie wijzigde en wanneer, met dezelfde twee keuzes; de pagina erachter is dan al opnieuw gelezen.

**De test `tests/test_stale_save_guard.py` laat de build falen** als een route met PATCH of PUT niet op de lijst van beschermde routes staat en ook niet op de lijst van uitzonderingen met een reden.

| Soort gegeven | Beschermd | Hoe |
|---|---|---|
| Opdracht, rollen op een opdracht | ja | `Versioned` op de opdracht |
| Begrotingsregel, inzet | ja | `Versioned` |
| Kostenpost, factuurregel, dekking | ja | `Versioned` |
| Rol in de catalogus | ja | `Versioned` |
| Tarievenkaart, tarief, schaal naar categorie | ja | `Versioned` |
| Vacature: aanvraag, rol, besluit, stap, publicatie, verwijzing naar werving | ja | `Versioned` op de vacature |
| Persoon: gegevens, leidinggevende, schaal, inhuur, rollen, startdatum | ja | `EditCounted` op de persoon |
| Target van een persoon | ja | `EditCounted`, naam `target:` |
| Taak: status en overdracht | ja | `EditCounted` |
| Organisatie | ja | `EditCounted` |
| Peer | ja | eigen kolom, zelfde werking |
| Uitgaande factuur (correctie) | ja | `EditCounted` |
| Afspraken over factureren | ja | `EditCounted`, naam `terms:` |
| Functiefamilie, functiegroep | ja | `EditCounted` |
| Koppeling van een aanvraagformulier | ja | `EditCounted` op het formulier |
| Standaardtekst, gedeeld tekstonderdeel | ja | `EditCounted` |
| Instellingen: afzender, tekstblokken, offertes, vacatureteksten | ja | één geheel, `instance-settings` |
| Concept van een offerte | eigen versie | per onderdeel in het verzoek zelf |
| Maandafsluiting | nee | een tweede afsluiting wordt al geweigerd |
| Notitie bij een taak | nee | een notitie komt erbij en vervangt niets |
| Eigen voorkeur voor meldingen | nee | niemand anders wijzigt haar |
| Een recht toekennen | nee | het resultaat is gelijk, wie het ook doet |

De server controleert zodra een formulier de versie meestuurt. Het blad voor de link naar een gepubliceerde vacature stuurt haar nog niet mee.
