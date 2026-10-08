# Toegang

Schaal-, tarief- en KPI-gegevens zijn persoonsgegevens onder de AVG. In Grist was delen alles of niets. Grip schermt af tot op veldniveau, en doet dat op de server.

## Drie begrippen in plaats van rollen

Het woord "rol" dekt in de praktijk drie verschillende dingen: wat iemand in de organisatie doet, hoe iemand zich tot een bepaalde opdracht of persoon verhoudt, en hoe gevoelig een gegeven is. Het model houdt ze uit elkaar.

### Functie in de instantie

Een functie wordt toegekend, per eenheid en voor een periode.

| Functie | Mag |
|---|---|
| Beheerder | Tarievenkaarten, gebruikers, functies toekennen, gesloten jaren wijzigen met auditregel |
| Planner | Inzet en open rollen bewerken over alle opdrachten |
| Lezer | Opdrachten en totalen inzien |
| Aanvrager | Aanvragen doen als opdrachtgever |
| Tekenbevoegde | Offertes accepteren namens de eenheid |

### Relatie tot een object

Een relatie wordt niet toegekend. Ze volgt uit de gegevens.

| Relatie | Volgt uit |
|---|---|
| Eigenaar of manager van een opdracht | De rol op de opdracht: een eigenaar, een of meer managers |
| Lid van een opdracht | Een inzet op die opdracht |
| Leidinggevende van een persoon | `manager_id` |
| Zelf | Het eigen persoonsrecord |
| Gast-ondertekenaar | Een uitnodiging voor een offerte |
| Tegenpartij (peer) | Het peer-id is opdrachtgever van die opdracht |
| Moeder (peer) | Het peer-id is de moederinstantie |

### Gegevensklasse

Elk veld hoort bij precies een klasse.

| Klasse | Inhoud |
|---|---|
| A Opdracht-basis | Naam, partijen, status, periode, context-URI's, voortgang |
| B Opdracht-financieel | Begroting, uitputting, beschikbaar, offertebedrag, factuurgegevens, kosten en dekking |
| C Bemensing | Wie, rol, percentage, periode |
| D Persoon-tarief | Inzetschaal, categorie, inzetbedrag per persoon |
| E Persoon-kosten | Kostprijs van inhuur, marge |
| F Persoon-KPI | Declarabiliteitstarget en realisatie |

De salarisschaal wordt niet opgeslagen. De berekeningen hebben alleen de inzetschaal nodig.

## Matrix

b = bewerken, l = lezen, leeg = geen toegang.

| Wie | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| Beheerder | l | l | l | l | l | l |
| Lezer | l | l | | | | |
| Planner | l | | b | | | |
| Eigenaar of manager, eigen opdracht | b | b | b | l | l | |
| Lid, eigen opdracht | l | | l (namen en rollen) | | | |
| Leidinggevende, eigen medewerkers | | | l | l | | l |
| Zelf | | | l | l | | l |
| Gast-ondertekenaar | alleen die offerte | | | | | |
| Tegenpartij | l | op verzoek | | | | |
| Moeder | l | l | l (aantallen) | | | |

De beheerder bewerkt daarnaast de stamgegevens uit de functietabel hierboven: tarievenkaarten, gebruikers en functies.

Functies en relaties tellen op. Wie planner is en ook leidinggevende, heeft de rechten van beide.

## Hoe gangbare rollen hierop passen

| In de praktijk | In het model |
|---|---|
| Opdrachtmanager | Manager op een opdracht |
| Opdrachteigenaar | Eigenaar op een opdracht |
| Teamleider | Leidinggevende van eigen medewerkers, meestal ook planner |
| Planner zonder team | Alleen de functie planner |
| Medewerker | Zelf, en lid van de opdrachten waar hij op is ingezet |

## Waarom zo

De matrix in de oorspronkelijke Grist-beschrijving was bijna helemaal relationeel: "eigen opdrachten", "eigen medewerkers", "het eigen record". Alleen beheerder en lezer waren daar echte functies. Een relatie die uit de gegevens volgt hoeft niemand te beheren, en ze kan niet verouderen wanneer iemand van opdracht wisselt.

Een planner die geen leidinggevende is ziet geen bedragen en ook geen tariefcategorie. Regel R14 signaleert dat iemand in een andere categorie declareert dan de begrotingsregel aanneemt. De planner krijgt dat als signaal ("categorie wijkt af"), zonder de categorie zelf.

Een lid van een opdracht ziet geen geld. Begrotingsregels noemen een tariefcategorie per rol, en een categorie omvat twee schalen. Wie de regels ziet, kent dus de schaalrange van collega's.

Een eigenaar of manager ziet wel het inzetbedrag en de categorie van mensen op de eigen opdracht, want zonder die bedragen valt een begroting niet te bewaken. De KPI van die mensen ziet hij niet.

De relatie "zelf" zit vanaf het begin in het model, ook al krijgen medewerkers in de eerste mijlpaal alleen een eenvoudig scherm. Het past bij het inzagerecht uit de AVG.

Personen, gasten met een tekenlink en andere instanties gaan door dezelfde beslisfunctie. Een verzoek bestaat uit wie, welke actie, welk object en welke context. Dat is de vorm van een AuthZEN-verzoek, zodat Federatieve Toegangsverlening later kan aanhaken zonder de applicatie te verbouwen.

## Peers

Een andere instantie is geen gebruiker. FSC bepaalt per contract welke dienst een peer mag aanroepen. Daarbinnen koppelt de applicatie het peer-id aan een organisatie en beslist per opdracht:

- Een tegenpartij leest klasse A van opdrachten waarvan zij opdrachtgever is. Klasse B levert de opdrachtnemer alleen als de tegenpartij erom vraagt. Klassen C t/m F gaan nooit naar een tegenpartij.
- De moederinstantie leest A, B en C van de opdrachten van het onderdeel. Klassen D t/m F blijven binnen de instantie.

Inkomende routes voor peers vertrouwen alleen verzoeken die via de inway binnenkomen.

## Afdwingen

Een functie neemt elke beslissing:

```
decide(subject, action, resource, data_class)
```

- Functies per eenheid staan in de tabellen `role` en `person_role`, naar het patroon van Bouwmeester.
- Relaties worden bij elke beslissing afgeleid uit de domeingegevens.
- Antwoordschema's zijn per gegevensklasse opgebouwd. Een klasse die niet is toegestaan zit niet in het antwoord; ze wordt niet achteraf weggefilterd in de UI.
- Wijzigingen in tarievenkaarten, schalen, begrotingsregels, inzet en dekking komen in het auditlog: wie, wanneer, oude en nieuwe waarde.

## Testen

- Per gegevensklasse en per relatie is er een test op API-niveau met een verzoek dat geweigerd moet worden.
- Een eigenaar van een opdracht kan de KPI van een ander niet opvragen, niet via de UI en niet via de API.
- Een inventaristest loopt alle routes langs en laat de build falen als een route geen autorisatie-afhankelijkheid heeft.

## Open

- Een tekenbevoegdheid is nu ja of nee per eenheid. Een grens op het bedrag is niet uitgewerkt.
- De matrix geeft de moeder klasse C. Of bezetting met namen of alleen als aantallen naar de moeder gaat, is niet beslist.

## Nadere regels

**Kostprijs en marge (klasse E).** Deze gegevens hangen aan een persoon, niet aan een opdracht. Een eigenaar of manager ziet ze alleen van personen die in de getoonde periode een inzet hebben op de eigen opdracht.

**Bemensing naar de moeder (klasse C).** De moederinstantie krijgt standaard aantallen: hoeveel mensen ingezet, beschikbaar en gezocht, per rol en per periode. Namen gaan alleen mee als de beheerder van de dochterinstantie dat aanzet.

**Kostenposten (klasse B).** Een kostenpost hoort niet bij een opdracht. De beheerder mag kostenposten aanmaken en wijzigen. Daarnaast wijzigt een kostenpost wie een opdracht beheert waarvan de begroting hem dekt; zolang nog niets hem dekt, is dat wie hem heeft aangemaakt.

**Offerte uitgeven en maand afsluiten.** Dat doet alleen de eigenaar of manager van de opdracht, ook de beheerder niet. Een afgesloten maand heropenen kan alleen de beheerder.

**Gast-ondertekenaar zonder account.** Wie is uitgenodigd om een offerte te tekenen en geen persoon is in de instantie, krijgt na het inloggen een gastsessie. Dat gebeurt alleen als de identiteitsprovider het e-mailadres heeft bevestigd en er voor dat adres een uitnodiging openstaat die niet is verlopen. Een gastsessie bereikt alleen de tekenpagina's; elk ander deel van de API weigert haar.

**Niets te tellen.** Een lijst waarvan de lezer de inhoud niet mag zien ontbreekt in het antwoord, ook als ze leeg is. Een regel waarvan geen enkel veld overblijft wordt weggelaten. Zo verraadt een antwoord niet hoeveel schaalperiodes, offerteregels of kostenposten er zijn.
