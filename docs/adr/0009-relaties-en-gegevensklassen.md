# 0009 Relaties en gegevensklassen in plaats van vaste rollen

Status: aanvaard (2026-10-08)

## Context

De basisbeschrijving van het Grist-document stelde vijf rollen voor (beheerder, manager, opdrachteigenaar, teamlid, lezer) met een matrix per soort gegeven. In gesprekken over het gebruik kwamen andere namen voor: opdrachtmanager, planner, teamleider, opdrachteigenaar, beheerder.

Bijna alle cellen in die matrix zeggen "eigen": eigen opdrachten, eigen medewerkers, het eigen record. Dat zijn geen rollen maar verhoudingen tot een object.

## Besluit

Het toegangsmodel kent drie losse begrippen:

- **Functie**: toegekend per eenheid en periode. Beheerder, planner, lezer, aanvrager, tekenbevoegde.
- **Relatie**: afgeleid uit de gegevens. Eigenaar of manager van een opdracht, lid van een opdracht, leidinggevende, zelf, gast-ondertekenaar, tegenpartij, moeder.
- **Gegevensklasse**: elk veld hoort bij een van zes klassen, A t/m F.

De matrix van wie welke klasse mag lezen of bewerken staat in `docs/toegang.md`.

Drie keuzes wijken af van de basisbeschrijving:

- Een planner die geen leidinggevende is ziet geen bedragen en geen tariefcategorie.
- Een lid van een opdracht ziet geen begroting.
- De eigenaar of manager van een opdracht ziet de kostprijs en marge van inhuur op de eigen opdracht.

## Gevolgen

- Relaties hoeven niet te worden beheerd.
- Elk nieuw veld moet bij een klasse worden ingedeeld, en krijgt een lektest.
- Antwoordschema's worden per klasse opgebouwd. Dat is meer werk dan een schema per entiteit.
- De namen die mensen in de praktijk gebruiken komen niet een op een terug in het model. De documentatie moet de vertaling geven.

## Later gewijzigd (2026-10-09)

De klassen A tot en met F zijn gebleven. Erbij gekomen zijn smallere weergaven die uit een bredere klasse volgen (zoals de teamlijst zonder percentages) en de klasse voor de bedragen van een tarievenkaart: de prijslijst leest alleen de beheerder, de lezer en wie een opdracht beheert. De indeling van schalen in categorieen leest iedereen. Zie `docs/toegang.md`.
