# 0025 Een offerte kan eerst intern worden goedgekeurd

Status: aanvaard (2026-10-08)

## Context

In sommige organisaties gaat een offerte pas de deur uit nadat iemand met gezag er intern naar heeft gekeken, bijvoorbeeld de directeur van de eenheid. De oude administratie kende daarvoor de status "Interne afstemming". Andere organisaties hebben die stap niet, of alleen boven een bedrag.

Sinds ADR 0021 zijn een offerte maken en haar aanbieden twee stappen. De interne goedkeuring hoort daartussen.

## Besluit

Tussen maken en aanbieden zit een stap die per instantie aan of uit staat.

- **Wanneer.** De beheerder stelt in wanneer een offerte intern moet worden goedgekeurd voor ze mag worden aangeboden: nooit (de standaard), altijd, of vanaf een bedrag. Dat is een regel van de organisatie en staat daarom in de database, bij de instellingen van de instantie, en niet in de omgeving van de installatie.
- **Wie.** Er is een nieuw recht in grip: interne goedkeurder van offertes. Wie dat recht heeft keurt goed of stuurt terug. Wie de goedkeuring vroeg kan de eigen offerte niet goedkeuren (vier ogen), tenzij de instantie dat toestaat; de vastlegging en de auditregel zeggen dan dat het zo is gegaan.
- **Wat er wordt vastgelegd.** Bij een gemaakte offerte: het verzoek (wie, wanneer, een toelichting voor de goedkeurder) en de beslissing (goedgekeurd of teruggestuurd, door wie, wanneer, met een toelichting). De vastlegging noemt de hash van de offerte: een goedkeuring gaat over precies die bytes (ADR 0020). Een goedkeuring die een andere hash noemt keurt niets goed.
- **Terugsturen** verandert de offerte niet; die ligt vast. De maker maakt een nieuwe offerte, de oude wordt vervangen, en de reden van het terugsturen blijft bewaard. Terugsturen vraagt een toelichting, zodat de maker verder kan.
- **Intrekken.** De maker kan een verzoek intrekken zolang er niet is beslist. Een goedkeuring kan worden ingetrokken zolang de offerte niet is aangeboden.
- **De regel.** Is goedkeuring nodig voor een offerte, dan weigert grip haar aan te bieden, langs elk kanaal, tot er een goedkeuring is. De melding zegt wat er ontbreekt. Is goedkeuring niet nodig, dan verandert er niets en hoeft er niets te worden vastgelegd. Goedkeuring vragen mag dan nog steeds.
- **Niemand heeft het recht.** Dan blijft aanbieden geblokkeerd. De melding noemt het recht dat ontbreekt en zegt dat de beheerder het toekent bij een persoon, onder de rechten in grip.
- **Alleen intern.** Interne goedkeuring is kennis van de organisatie die de offerte maakt, net als een mondeling akkoord. Ze is geen inhoud van de offerte, verandert de status niet die anderen zien, en gaat niet mee in berichten naar een andere instantie of in de rapportage aan de opdrachtgever.

Toegang:

- Zien waar een offerte staat met de goedkeuring kan wie de offerte mag zien.
- Goedkeuring vragen kan de eigenaar of een manager van de opdracht.
- Beslissen kan wie het recht heeft. Die persoon leest de offerte waarvoor goedkeuring is gevraagd volledig, ook zonder andere band met de opdracht, zoals een tekenbevoegde en een uitgenodigde ondertekenaar dat doen. Verder gaat er niets van de opdracht open.

## Gevolgen

- Er is een tabel met instellingen van de instantie die de beheerder wijzigt, met een auditregel bij elke wijziging. Andere regels van de organisatie, zoals een standaard indexatiepercentage, horen daar ook.
- Er is een zesde recht in grip. Het recht geeft geen toegang tot opdrachten; alleen tot offertes die aan een goedkeurder zijn voorgelegd.
- Wie goedkeurt heeft een eigen lijst: offertes die op goedkeuring wachten, over alle opdrachten heen.
- Het verzoek, de goedkeuring en het terugsturen worden als gebeurtenis gemeld. Daar kan een taak uit volgen voor de goedkeurder of voor de maker. De gebeurtenissen dragen kenmerken en het offertekenmerk, geen bedragen.
- Een goedkeuring geldt voor een offerte, niet voor een opdracht. Een nieuwe offerte voor dezelfde opdracht heeft een eigen goedkeuring nodig.
- Wie het bedrag van de drempel verlaagt, maakt daarmee offertes die al zijn gemaakt en nog niet zijn aangeboden alsnog goedkeuringsplichtig. Dat is bedoeld: de regel geldt op het moment van aanbieden.
- Er is geen vervanger of mandaatregeling. Is de enige goedkeurder afwezig, dan kent de beheerder het recht aan een ander toe.
