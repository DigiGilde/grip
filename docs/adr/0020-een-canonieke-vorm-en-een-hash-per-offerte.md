# 0020 Een offerte heeft een canonieke vorm en een hash

Status: aanvaard (2026-10-08)

## Context

Een hash op een offerte bewijst dat wat getekend is, hetzelfde is als wat is uitgegeven. Dat werkt alleen als een offerte precies een hash heeft.

Dat was niet zo. De inhoud van een uitgegeven offerte stond opgeslagen in de namen die de code gebruikt, en de hash ging daarover. Tussen instanties gaat de offerte in de Nederlandse termen van het contract (ADR 0019), en het contract rekent de hash over die vorm. De koppeling tussen instanties rekende de ene hash om naar de andere. Een offerte had daardoor twee vingerafdrukken: een op het document, bij de tekenlink en bij een geuploade pdf, en een andere in het ondertekende akkoord tussen instanties.

Beide waarden waren te herleiden, maar alleen door de inhoud opnieuw te vertalen en opnieuw te serialiseren. Elke wijziging in de vertaling had daarna stilzwijgend een andere hash kunnen opleveren voor een offerte die al was getekend.

## Besluit

Een offerte heeft een canonieke vorm en een hash, overal.

- De canonieke vorm is de inhoud van de offerte in de termen van het contract (de momentopname zoals `grip-opdrachtverkeer` die beschrijft), geserialiseerd als canonieke JSON volgens RFC 8785. Dat is het document dat tussen organisaties gaat en waar een handtekening over gaat, dus dat is de vorm die vast moet staan.
- Bij uitgifte wordt die vorm een keer gemaakt. De exacte bytes worden opgeslagen. De hash van de offerte is de SHA-256 over die bytes.
- Daarna rekent niets de hash van een offerte opnieuw uit een vertaalde of opnieuw geserialiseerde inhoud. Een controle vergelijkt met de opgeslagen hash, en de database bewaakt dat die hash bij de opgeslagen bytes hoort.
- Dezelfde hash staat op het offertedocument, op de pagina's van de tekenlink, in een akkoord van elke vorm (eigen grip, tekenlink, geuploade pdf), in de berichten tussen instanties en in de antwoorden van de API.
- Een ontvangen offerte wordt opgeslagen zoals ze is ontvangen: dezelfde bytes en dezelfde hash als bij de instantie die haar uitgaf. Een offerte waarvan de bytes niet bij de genoemde hash horen wordt geweigerd.
- Wat een scherm, het document of een rapportage van een uitgegeven offerte toont, wordt gelezen uit de opgeslagen bytes, via de termenlijst. Er is geen tweede kopie van de inhoud.
- De termenlijst die contracttermen en codenamen koppelt is een documentformaat en geen transport. Ze staat bij de domeindiensten; het onderdeel dat met andere instanties praat gebruikt dezelfde lijst (ADR 0015 blijft gelden: het domein weet niets van FSC).

## Gevolgen

- Een wijziging van een tarievenkaart of van de termenlijst verandert de opgeslagen bytes en de hash van een uitgegeven offerte niet. Verandert de termenlijst, dan kan een scherm een veld onder een andere naam tonen; de offerte zelf blijft wat ze was.
- De inhoud van een offerte staat in de database als bytes en niet meer als doorzoekbare JSON. Het totaalbedrag staat er als kolom naast, afgeleid bij uitgifte.
- Bestaande offertes hebben bij de migratie hun canonieke vorm en hun nieuwe hash gekregen. De oude hash, ook in akkoorden en afwijzingen die ernaar verwezen, staat in de auditlog.
- Velden die het contract niet kent maar die in een ontvangen offerte staan, blijven in de bytes en dus in de hash. Een instantie die een nieuwere versie van het contract volgt, breekt een oudere ontvanger daarmee niet.
- Een vaste regel in een offerte draagt het jaar waarvoor hij geldt. Het contract beschrijft dat veld nog niet op een offerteregel; het moet erbij als `jaar`.
- Het akkoord tussen instanties is ondertekend over het bericht zoals het over de grens gaat. Die ondertekende bytes zitten in de handtekening zelf (JWS). De velden die ernaast zijn opgeslagen zijn een weergave daarvan.

## Later gewijzigd (2026-10-09)

De hash over de inhoud heet op het scherm het echtheidskenmerk. Daarnaast ligt sindsdien ook het pdf-bestand vast, met een eigen hash, het bestandskenmerk (ADR 0030). Een akkoord noemt beide. Het bericht tussen instanties is niet gewijzigd.
