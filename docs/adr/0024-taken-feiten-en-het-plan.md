# 0024 Taken, feiten en het plan

Status: aanvaard (2026-10-08)

## Context

Grip weet wat er met een opdracht en een vacature is gebeurd, en zegt nergens wat er nu moet gebeuren. Wie een maand moet afsluiten, een offerte moet aanbieden of een advies moet geven, ziet dat alleen door het juiste tabblad te openen. Dat is werk dat op het bureau van één persoon hoort te liggen.

De voor de hand liggende oplossing is een workflowmotor: een proces met stappen, waarin een taak afvinken de zaak naar de volgende stap brengt. Dat maakt de takenlijst tot een tweede waarheid naast het domein. Een maand is dan afgesloten omdat iemand een vinkje zette, of juist niet afgesloten terwijl de afsluiting bestaat.

## Besluit

Er zijn drie lagen, en de richting is altijd dezelfde: het domein bepaalt de taken, nooit andersom.

1. **Feiten.** Een feit is een benoemde uitspraak over een zaak of over één onderwerp van een zaak: "de offerte is aangeboden", "de maand is afgesloten", "de rol is ingevuld". Grip leidt een feit af uit de gegevens van het domein. Niemand zet een feit met de hand.
2. **Taken.** Een taak is werk voor een rol of een persoon bij een zaak. Een taak ontstaat als de voorwaarden van haar sjabloon gelden, en sluit als haar feit geldt. Een taak afvinken verandert geen feit. Een taak die door een feit sluit, is niet af te vinken; het scherm zegt door welk feit ze sluit.
3. **Het plan.** Het plan is gegevens: per soort zaak een lijst sjablonen. Een sjabloon zegt voor welk onderwerp de taak is, onder welke feiten ze ontstaat, door welk feit ze sluit, voor welke rol ze is, in welk spoor ze hoort en wanneer ze af moet zijn. Een plan kan alleen noemen wat de catalogus kent: de onderwerpen, de feiten, de rollen en de ankerdata. Een plan met een onbekende naam wordt geweigerd bij het laden.

De motor vergelijkt per zaak wat er volgens het plan aan taken hoort te zijn met wat er is, en maakt het verschil goed: aanmaken, sluiten door een feit, laten vervallen, heropenen. Hij is idempotent. Een taak van het plan heeft een sleutel uit zaak, sjabloon en onderwerp, en de database staat die sleutel één keer toe.

De motor loopt op drie momenten: bij het lezen van een takenlijst, op een interval in het achtergrondproces (tijd maakt ook werk: een maand eindigt, een termijn verstrijkt), en op verzoek voor alle bestaande zaken. Een domeingebeurtenis doet zelf niets met taken. Ze meldt alleen dat de stand verouderd is, zodat de eerstvolgende lezer een verse stand krijgt.

Een zaak houdt de versie van het plan waarmee ze begon. Een taak bewaart de versie waaruit ze kwam.

Een taak valt in gegevensklasse A van haar zaak. Wie de zaak mag lezen, ziet haar taken. De titel van een taak noemt geen persoon en geen bedrag.

Sporen delen het werk van een zaak in: offerte, bemensing, uitvoering en financiën bij een opdracht, werving bij een vacature. Sporen lopen naast elkaar. De stand van een zaak is de stand van haar sporen.

"Wacht op een ander" is een status van een taak, met wie er gewacht wordt. De taak blijft van degene die wacht.

Naast de taken van het plan kan iemand met schrijfrecht op de zaak een eigen taak toevoegen. Die is van de mens: ze is af te vinken en de motor raakt haar niet aan.

Taken zijn van de eigen organisatie. Tussen organisaties gaan alleen gebeurtenissen (ADR 0015). Een ontvangen gebeurtenis verandert gegevens van het domein, en daaruit volgen aan de ontvangende kant de eigen taken.

De woorden volgen zaakgericht werken, zonder de componenten ervan: een opdracht en een vacature zijn een zaak, het plan is het zaaktype, een vacature bij een opdracht is een deelzaak, een taak is een taak. De afbeelding staat in [taken.md](../taken.md).

## Gevolgen

- De takenlijst kan niet uit de pas lopen met het domein. Wordt een maand heropend, dan staat haar taak weer open.
- Een nieuwe taak in het plan kost een regel gegevens zolang het feit bestaat. Een nieuw feit kost code in één module en een naam in de catalogus.
- Elk lezen van een takenlijst kost een evaluatie. Die leest alle open zaken in een vast aantal vragen aan de database, onafhankelijk van het aantal zaken, en de teller in de navigatie evalueert hooguit eens per vijftien seconden.
- Voor wie een taak is, wordt bij het lezen bepaald uit de rol. Wisselt de eigenaar van een opdracht, dan wisselen de taken mee. Draagt iemand een taak over aan een persoon, dan blijft dat staan.
- Het plan wordt met grip meegeleverd. Een scherm om het plan te bewerken, het beheer van versies en een koppelvlak volgens de ZGW-standaarden zijn latere stappen. Die stappen mogen de richting niet omkeren: geen taak die een feit zet, en geen sjabloon dat buiten de catalogus reikt.
- Het achtergrondproces draait voortaan ook als federatie uit staat, tenzij het interval voor taken op nul staat.

## Later gewijzigd (2026-10-09)

De regel dat een zaak de versie van het plan houdt waarmee ze begon, geldt niet meer zonder uitzondering: een plan kan een eerdere versie opvolgen, en een zaak op die eerdere versie gaat dan bij de volgende beoordeling over (ADR 0038). Wat een taak de lezer vertelt staat naast het plan en niet erin (ADR 0038). Waar een zaak staat en wat de volgende stap is komt uit dezelfde feiten als de taken (ADR 0044).
