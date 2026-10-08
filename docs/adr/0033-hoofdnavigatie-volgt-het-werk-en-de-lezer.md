# 0033 De hoofdnavigatie volgt het werk en de lezer

Status: aanvaard (2026-10-08)

## Context

De balk bovenaan toonde tien onderdelen van gelijk gewicht, in de volgorde waarin ze zijn gebouwd, voor iedereen dezelfde. Het was een tabbalk, terwijl de onderdelen pagina's zijn. Het aantal open taken stond als tekst in het label. Beheer stond tussen het dagelijkse werk. De balk zei niet wie je bent of als wie je kijkt, en dat gaf verwarring: wie als beheerder keek, dacht dat een begroting op slot zat.

Grip heeft lezers met heel verschillend werk:

| Lezer | Dagelijks | Af en toe |
|---|---|---|
| Eigenaar of manager van opdrachten | Taken, Opdrachten, Inzet | Team, Vacatures, Kosten, Rapportage |
| Planner | Inzet, Vacatures, Team | Opdrachten |
| Leidinggevende | Team, Inzet | Vacatures |
| Beheerder | Team, Beheer | alles om mee te kijken |
| Lezer | Opdrachten, Rapportage | Kosten |
| Teamlid | Taken, de eigen opdracht | Vacatures |
| Aanvrager of tekenbevoegde | Aanvragen, Taken | |

## Besluit

**Volgorde volgt het werk.** Eerst wat naar je toe komt (Stand van zaken, Taken), dan het werk zelf (Opdrachten, Inzet, Vacatures, Team), dan het terugkijken (Kosten, Rapportage), dan de rol van opdrachtgever (Aanvragen). Beheer staat apart aan het eind, bij het account: het is geen dagelijks werk.

**Stand van zaken en Taken blijven twee plekken.** De startpagina toont wat aandacht vraagt over alle opdrachten heen. Taken is de plek van het werk dat op jou wacht, met het bord voor het team. Alleen Taken krijgt een getal.

**De balk biedt alleen aan wat iets voor je kan bevatten.** Welke onderdelen iemand ziet volgt uit de rechten in grip en uit de soorten relatie die de sessie meldt (eigenaar of manager van een opdracht, leidinggevende, teamlid). Dit is een hulp voor de balk en geen toegangsregel: de server beslist per pagina en per veld, en een adres dat je intikt opent gewoon.

**Een menubalk met links, geen tabs.** De onderdelen staan in `nldd-menu-bar`, het onderdeel dat het designsysteem voor hoofdnavigatie noemt, in de werkbalk van de schil (het patroon voor een applicatie). Elk onderdeel is een link met een eigen tabstop; het onderdeel waar je bent draagt `aria-current="page"`. Een bovenbalk en geen zijbalk: na groeperen zijn het hooguit acht woorden, en het planbord en de tijdlijn hebben de breedte nodig.

**Een getal is een badge naast het label.** Alleen voor werk dat op jou wacht; nul toont niets. De toegankelijke naam zegt het in woorden: "Taken, 5 open taken".

**Rechts staat wie je bent.** Je naam op de knop; daarachter als wie je kijkt in woorden, "Mijn gegevens" en uitloggen. Lokaal staat op dezelfde knop dat je als een voorbeeldpersoon kijkt; de zwevende melding in de hoek vervalt.

**Smal klapt de balk in.** Vanaf 1008 pixels staat de menubalk er; wat niet past gaat achter "Meer", de laatste onderdelen eerst. Daaronder staan alle onderdelen achter één menuknop die het onderdeel noemt waar je bent, en wordt het account een pictogram. De onderbalk met pictogrammen vervalt.

**Waar je bent.** Een diepere pagina houdt haar onderdeel actief, ook als het adres anders doet vermoeden: het vacatureformulier staat onder Beheer, goedkeuren hoort bij Taken. De regel staat op één plek, in de routetabel.

## Gevolgen

- De sessie meldt naast de rechten ook de soorten relatie (`relations`). Geen route vertrouwt erop.
- "Kosten en facturen" heet in de balk "Kosten"; de pagina houdt haar titel.
- Goedkeuren van offertes heeft geen eigen onderdeel in de balk: je komt er via een taak.
- Het menubalk-onderdeel van het designsysteem heeft geen plek voor een badge. Grip zet de badge in het onderdeel en maakt er met eigen CSS één regel van. Dat hoort als voorstel bij het designsysteem.
- De regels voor navigatie binnen een onderdeel (tabs, overzichtspagina, terugkoppeling) staan in `docs/ontwerp.md`. Een aantal pagina's volgt ze nog niet; de lijst staat daar.
- De kop van de tekenpagina's heeft een eigen opzet en volgt deze balk nog niet.
