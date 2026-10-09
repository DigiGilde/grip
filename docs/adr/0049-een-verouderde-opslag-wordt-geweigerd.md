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

De stand per soort gegeven dat een mens wijzigt, nagelopen op 9 oktober 2026. De server controleert in de service; elk antwoord draagt `version`. "Paneel" is het conflictpaneel met de twee keuzes; "zin" is alleen de melding van de server, bij een handeling van één klik waar niets ingevuld verloren gaat.

| Soort gegeven | Server | Hoe | Scherm stuurt versie | Bij een weigering |
|---|---|---|---|---|
| Opdracht | ja | `Versioned` | ja | paneel, per veld |
| Eigenaar en managers van een opdracht | ja | `Versioned` op de opdracht | ja | zin |
| Begrotingsregel | ja | `Versioned` | ja | paneel, per veld |
| Inzet | ja | `Versioned` | ja | paneel, per veld |
| Kostenpost, factuurregel, dekking | ja | `Versioned` | ja | paneel, per veld |
| Rol in de catalogus | ja | `Versioned` | ja | paneel |
| Tarievenkaart, tarief, schaal naar categorie | ja | `Versioned` | ja | paneel |
| Vacature: aanvraag, rol, besluit, stap | ja | `Versioned` op de vacature | ja | paneel |
| Vacature: link naar de publicatie, verwijzing naar werving | ja | `Versioned` op de vacature | ja | paneel |
| Persoon: gegevens, leidinggevende, schaal, inhuur, rollen, startdatum | ja | `EditCounted` op de persoon | ja | paneel |
| Persoon: in of uit dienst zetten | ja | `EditCounted` op de persoon | ja | zin |
| Target van een persoon | ja | `EditCounted`, naam `target:` | ja | paneel |
| Taak: status en overdracht | ja | `EditCounted` | ja | zin |
| Organisatie | ja | `EditCounted` | geen scherm dat wijzigt | n.v.t. |
| Peer | ja | eigen kolom, zelfde werking | ja | paneel |
| Uitgaande factuur (correctie) | ja | `EditCounted` | ja | paneel |
| Afspraken over factureren | ja | `EditCounted`, naam `terms:` | ja | paneel |
| Functiefamilie, functiegroep | ja | `EditCounted` | ja | paneel |
| Koppeling van een aanvraagformulier | ja | `EditCounted` op het formulier | ja | paneel |
| Standaardtekst, gedeeld tekstonderdeel | ja | `EditCounted` | ja | paneel |
| Instellingen: afzender, tekstblokken, offertes, vacatureteksten | ja | één geheel, `instance-settings` | ja | paneel |
| Concept van een offerte | eigen versie | per onderdeel in het verzoek zelf | ja | eigen melding per onderdeel |
| Maandafsluiting | nee | een tweede afsluiting wordt al geweigerd | n.v.t. | n.v.t. |
| Notitie bij een taak | nee | een notitie komt erbij en vervangt niets | n.v.t. | n.v.t. |
| Eigen voorkeur voor meldingen | nee | niemand anders wijzigt haar | n.v.t. | n.v.t. |
| Een recht toekennen | nee | het resultaat is gelijk, wie het ook doet | n.v.t. | n.v.t. |

De server controleert zodra een formulier de versie meestuurt; zonder versie is er geen controle. Het paneel is in de browser gezien op de begrotingsregel; de andere formulieren gebruiken dezelfde onderdelen (`useStaleRecord`, `useStaleForm`, `ConflictPanel`) en zijn op de code nagelopen.
