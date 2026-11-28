# 0052 Een kostenpost bij een andere partij

Status: voorgesteld (2026-10-10)

## Context

Een programma heeft een eigen grip en een jaarbudget van een ministerie. Een deel van zijn uitgaven doet het niet zelf: een hotelovernachting of een zaal voor een bijeenkomst boekt en betaalt een leverancier die al een opdracht van het programma heeft. De factuur komt bij de leverancier binnen en staat in diens administratie. Het programma moet de uitgave toch in zijn eigen uitputting zien, op het moment van boeken al als verwachting en na de factuur als werkelijk bedrag.

Een kostenpost (`cost_item`) met factuurregels (`invoice_line`) bestaat al, maar alleen binnen één instantie. Volgens [ADR 0053](0053-een-gegeven-heeft-een-eigenaar-elders-een-verwijzing.md) heeft elk gegeven één eigenaar-Grip, en staat elders een verwijzing.

## Besluit

**De leverancier is eigenaar van de kostenpost.** Wie de uitgave doet, heeft de kostenpost: omschrijving, verwacht bedrag, factuurregels, bijlagen en de dekking met een eigen begrotingsregel, meestal van de opdracht van het programma. Het programma bewaart daarvan niets.

**Het programma vraagt de leverancier om de kostenpost aan te maken.** In de Grip van het programma kies je "Uitgevoerd door" een organisatie met een actieve koppeling met het contract `grip-opdrachtverkeer`. Het verzoek gaat via de outbox naar de leverancier: omschrijving, verwacht bedrag, periode en, als die er is, de URI van de opdracht waaronder de leverancier het werk doet. Het verzoek is idempotent op de URI van de verwijzing. Een wijziging van omschrijving of bedrag vraagt het programma op dezelfde manier aan; de leverancier voert haar uit.

**Bij het programma staat een verwijzing.** De verwijzing heeft een eigen URI, de uitvoerder en wat van het programma zelf is: de dekking met een eigen begrotingsregel en later de dienst. Tot de leverancier de kostenpost heeft aangemaakt, toont de verwijzing wat er is gevraagd, met "Wacht op" en de naam van de leverancier. Daarna wordt dat verzoek niet meer bewaard.

**De leverancier kent de vrager.** De kostenpost bij de leverancier draagt "Gevraagd door" en de URI van de verwijzing. Daaruit volgt wie haar mag lezen. Een abonnement of een melding is niet nodig.

**Het programma leest bij de leverancier.** Met de URI's van zijn verwijzingen haalt het programma omschrijving, verwacht bedrag en factuurregels op, met één verzoek per leverancier voor alle verwijzingen die het nodig heeft. Een verwijzing waarvan de leverancier nog geen kostenpost heeft, komt terug als "nog niet aangemaakt". De leverancier beslist met `decide()`: alleen de organisatie die de kostenpost heeft gevraagd, leest haar, en alleen de velden van klasse B.

**Rekenen gebeurt met wat is opgehaald.** De servicelaag geeft de opgehaalde regels aan `grip.calc`, als gewone factuurregels. Er komt geen rekenregel bij: prognose, gedekt, gebruikt en beschikbaar (R6 tot en met R10) tellen zoals altijd. Wat is opgehaald, wordt hooguit kort onthouden; het is geen bron.

**Onbereikbaar is onvolledig.** Kan de leverancier niet worden bereikt, dan toont de verwijzing "Niet op te halen bij" de leverancier, zonder bedrag, en telt ze niet mee. Elk totaal waar ze in hoort, zoals de uitputting van de begrotingsregel en de opdracht, heet dan onvolledig.

**Elke administratie telt de uitgave één keer.** Bij de leverancier telt ze in de begroting die haar dekt, bij het programma in de eigen begroting via de verwijzing. Dat zijn twee administraties, geen dubbeltelling binnen één instantie.

**Twee operaties in het contract.** `requestCostItem` (programma naar leverancier, push) en `getCostItems` (programma bij leverancier, ophalen op de URI's van de verwijzingen). De afzender volgt altijd uit de FSC-peer, nooit uit het bericht. Ze komen in `grip-opdrachtverkeer` 1.1.0 in de contractrepo; grip neemt ze over met `sync_contract`.

## Gevolgen

- Bij het programma is een kostenpost met een uitvoerder een verwijzing zonder eigen factuurregels. Bij de leverancier is het een gewone kostenpost met "Gevraagd door".
- Een verwijzing naar een organisatie zonder actieve koppeling kan niet ontstaan; het scherm biedt zo'n organisatie niet aan.
- Een verzoek dat de leverancier weigert, laat een verwijzing met "Geweigerd door" achter. Het programma kan haar verwijderen.
- Wat het programma op een peildatum aan het ministerie verantwoordt, wordt later een vastgelegd document met de stand van dat moment. Dat is geen werkkopie.
- Of de leverancier de uitgave daarna met een factuur of een interne doorbelasting verrekent, blijft de open vraag uit [ADR 0039](0039-afsluiten-per-maand-aanleveren-per-periode.md). Deze koppeling gaat alleen over zien wat er is uitgegeven.
- Meldingen bij wijziging en abonnementen voor meer luisteraars (NL GOV-profiel voor CloudEvents) komen pas als lezen op het moment zelf te traag of te vaak blijkt.
- Een jaarbudget op het niveau van een programma bestaat nog niet. Het budget van het programma is de begroting van de opdracht die het van het ministerie heeft.
