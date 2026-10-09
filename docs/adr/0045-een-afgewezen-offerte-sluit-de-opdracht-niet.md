# 0045 Een afgewezen offerte sluit de opdracht niet

Status: aanvaard (2026-10-09)

## Context

Als de opdrachtgever een offerte afwees, ging de opdracht naar de status `rejected` en daarmee naar de fase Afgesloten. In de praktijk is een afwijzing zelden het einde: de begroting wordt aangepast en er gaat een nieuwe offerte uit. De opdracht stond dan onder Afgesloten, telde niet mee als potentieel en had geen volgende stap, terwijl er wel aan gewerkt werd.

## Besluit

Een afgewezen offerte is een feit van de offerte. De opdracht blijft een potentiële opdracht.

- De status `rejected` van een opdracht betekent voortaan "de laatste offerte is afgewezen" en heet op het scherm "Offerte afgewezen". De fase is Potentieel; in prognoses telt de opdracht als pijplijn en geplande inzet als voorlopig.
- Het verloop staat terug op de stap Offerte. De taak "Maak een nieuwe offerte na de afwijzing" zegt wie afwees, wanneer en waarom.
- Een opdracht eindigt pas zonder opdracht als iemand met het recht dat besluit: "Sluit af zonder opdracht", met een reden. De status wordt `cancelled`; het verloop noemt dat einde "Niet doorgegaan". Na een afgewezen offerte is de reden verplicht.
- "Markeer als afgewezen" bestaat niet meer als losse statusstap op het scherm. Een afwijzing wordt bij de offerte vastgelegd.
- Aan de kant van de opdrachtgever die afwees eindigt het verloop als "Afgewezen", tot er een nieuwe offerte binnenkomt.

De waarde `rejected` in de database blijft dezelfde. Er is geen migratie nodig: alleen de betekenis verandert, en opdrachten die bewust zijn beëindigd hebben al de status `cancelled`.

## Gevolgen

- Bestaande opdrachten met de status `rejected` verschijnen weer onder Potentieel, met een open taak voor de eigenaar zodra de taken opnieuw worden berekend. Wie zo'n opdracht niet meer wil, sluit haar af zonder opdracht.
- De stuurrapportage en de telling van potentiële opdrachten nemen deze opdrachten weer mee in de pijplijn. Inzet erop telt weer als voorlopige bezetting.
- Wies krijgt deze opdrachten nog steeds niet: daar gaat alleen afgesproken werk heen.
