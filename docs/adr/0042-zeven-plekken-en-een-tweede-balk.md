# 0042 Zeven plekken in de hoofdbalk, en een tweede balk voor pagina's die bij elkaar horen

Status: aanvaard (2026-10-08)

Vult aan: [0033 De hoofdnavigatie volgt het werk en de lezer](0033-hoofdnavigatie-volgt-het-werk-en-de-lezer.md)

## Context

Met Factureren telde de balk elf onderdelen. Gemeten in een browser pasten er negen op 1280 pixels en zes op 1024; de rest stond achter een knop. De balk was gegroeid in de volgorde van het bouwen.

De evaluatie in `docs/navigatie-evaluatie.md` legde vijf varianten naast elkaar, elk getekend voor de beheerder, een eigenaar en een planner op vier breedtes. Het bewijs in het kort:

- Van de 29 taaksjablonen sturen er 26 naar een tab van een opdracht of een vacature. Geen enkele stuurt naar Inzet, Team, Kosten, Factureren of Beheer. Het menu is er voor oriëntatie, niet voor het werk zelf.
- Team en Inzet gaan over hetzelfde: de mensen, als lijst en over de tijd. Kosten en Factureren gaan allebei over geld over opdrachten heen.
- Aanvragen is een rol, geen onderdeel van het werk van een opdrachtnemer. De beheerder zag het altijd.
- De schermen van het eerste niveau hingen aan de lijst van het menu. Een pagina die uit het menu ging, verloor haar adres.

De gebruiker koos de aanbevolen variant.

## Besluit

**Zeven plekken voor het werk:** Start, Taken, Opdrachten, Team, Vacatures, Financieel, Rapportage. Aanvragen staat er alleen voor wie de rol van aanvrager of tekenbevoegde heeft. Beheer blijft apart aan het eind.

**Een plek verdien je.** Een pagina krijgt een plek als iemand haar minstens wekelijks nodig heeft én het een plek is waar je heen gaat. Geen lezer krijgt meer dan zeven plekken.

**Pagina's die bij elkaar horen delen een plek en een tweede balk.** Team heeft Mensen en Inzet, Financieel heeft Kosten en Factureren. De tweede balk staat in de schil, onder de hoofdbalk, op dezelfde linkerrand als de pagina. Het zijn links naar pagina's: een navigatiegebied met een naam ("Pagina's van Team"), de pagina waar je bent draagt `aria-current="page"`. Een diepere pagina houdt haar plek en haar pagina in de tweede balk: een persoon staat onder Team en Mensen, een factuurverzoek onder Financieel en Factureren.

**De tweede balk is rustig.** Het is navigatie, geen inhoud: dezelfde soort balk als de hoofdbalk, kleiner, in de kleur van tekst, direct onder de hoofdbalk, met een dunne lijn onder de pagina waar je bent. Geen gevuld vlak, zodat een pagina haar ene accent houdt voor de hoofdknop.

**Een diepere pagina heeft geen link terug naar wat de tweede balk al aanwijst.** De pagina van een persoon stond onder "Terug naar Team" terwijl de tweede balk Mensen al markeert: twee middelen voor hetzelfde. De link terug vervalt als zijn doel precies de pagina is die de tweede balk markeert. Dat gold voor de persoon en de kostenpost; het factuurverzoek had geen link.

**Het onderdeel waar je bent staat nooit achter de knop "Meer".** De menubalk zet weg wat niet past, de laatste onderdelen eerst, en kent geen manier om er een vast te zetten. Raakt het onderdeel waar je bent daar terecht, dan schuift het naar de laatste plaats die nog past en gaat het onderdeel dat daar stond achter de knop. Bij een andere breedte of een andere pagina geldt weer de gewone volgorde.

Dit vult de regel uit 0033 aan. Die kende tabs voor de kanten van één ding dat openstaat en een overzichtspagina voor losse pagina's. De tweede balk is voor het geval ertussen: twee of drie pagina's van één onderdeel waar je even vaak direct heen wilt. Bij meer dan drie is het een overzichtspagina.

**Hetzelfde onderdeel op dezelfde plaats, de landing volgt de lezer.** Team staat voor iedereen op dezelfde plek. Voor wie het recht planner heeft, opent het op Inzet: het planbord is het dagelijkse scherm van de planner en mag geen klik dieper liggen dan voorheen. Voor ieder ander opent het op Mensen. De tweede balk laat zien waar je bent geland.

**Geen adres verandert.** `/inzet`, `/kosten`, `/factureren` en `/team` blijven. Een pagina heeft haar adres, of de balk haar noemt of niet: de schermen hangen niet meer aan de lijst van het menu.

**Woorden.** "Stand van zaken" heet in de balk "Start"; de pagina houdt haar titel. "Financieel" is hetzelfde woord als de tab van een opdracht.

**Smal.** Het menu achter de knop noemt de zeven plekken, met de pagina's van een plek eronder, ingesprongen en zonder pictogram.

## Gevolgen

- De routetabel kent `views` (de pagina's van een plek) en `landingFor` (voor wie een pagina de landing is).
- De beheerder van een instantie die ook opdrachtgever is, bereikt Aanvragen via Beheer, of krijgt het recht aanvrager.
- De lijst Goedkeuren krijgt een link op Taken, voor wie mag goedkeuren. "Open rollen" wordt een weergave van Vacatures en de instellingen van vacatures gaan naar Beheer. Die pagina's liggen bij andere sporen.
- Op 1024 pixels valt bij de beheerder Rapportage achter de knop "Meer", behalve op Rapportage zelf: dan wijken Vacatures en Financieel. Voor ieder ander past alles.
- De tweede balk zet de grootte en de kleur van het menubalk-onderdeel via waarden die het designsysteem voor zichzelf houdt, net als de badge in 0033. Een kleine, rustige variant hoort als voorstel bij het designsysteem.
- Vanaf een kostenpost ging de link terug naar Kosten met het gekozen jaar. De tweede balk gaat naar Kosten zonder dat jaar.
- De frequenties waarop dit rust zijn afgeleid uit het domein en de taken, niet gemeten. De vragen voor gebruikers staan in de evaluatie. Zeggen planners dat ze het bord niet onder "Team" zoeken, dan krijgt Inzet zijn plek terug.
