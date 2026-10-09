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
