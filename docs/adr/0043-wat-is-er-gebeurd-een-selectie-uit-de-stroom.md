# 0043 Wat is er gebeurd: een selectie uit de stroom

Status: aanvaard (2026-10-09)

## Context

De stroom van gebeurtenissen (ADR 0028) legt alles vast: elke wijziging, elke inzage. Als geschiedenis en als auditlog beantwoordt hij de vraag wat er precies is veranderd en door wie. Dat is verantwoording.

Wie 's ochtends grip opent, heeft een andere vraag: wat heb ik gemist? De auditlog geeft daar geen antwoord op. Hij is volledig, en daardoor staan er honderden regels tussen de paar die ertoe doen. Een lijst met taken geeft dat antwoord ook niet: een taak is wat je moet doen, niet wat er is gebeurd.

## Besluit

Er komt een overzicht "Wat is er gebeurd": een selectie uit dezelfde stroom, in zinnen. Het is geen gefilterde auditlog. De selectie en de bewoording zijn anders, de bron is dezelfde.

**Drie filters, in deze volgorde.**

1. Alleen nieuws. Wat nieuws is, staat als gegevens in `grip.events.news`: besluiten en overgangen, elk met een rang en met de functies die het voor de hele instantie krijgen. Al het andere staat uitdrukkelijk uit, per soort of per type: inzage, aanmelden, opgeslagen concepten, notities, instellingen, uitgaande mail, de boekhouding van taken. Een test eist dat elk type op een van beide lijsten staat. Een nieuw type kan dus niet ongemerkt wegvallen en ook niet ongemerkt het overzicht vullen.
2. Alleen wat de lezer aangaat: een opdracht waarvan hij eigenaar of manager is of waarop hij is ingezet, een vacature die hij aanvroeg of waarover hij beslist, mensen aan wie hij leiding geeft, en hijzelf. De stappen van een offerte en de maandafsluiting zijn voor wie de opdracht beheert, niet voor het hele team. De beheerder, de lezer en de planner krijgen de hele instantie, voor wat bij hun functie hoort.
3. Niet wat de lezer zelf deed.

Elk bericht gaat daarna door het toegangsmodel, precies zoals de geschiedenis: het overzicht toont nooit iets wat de lezer niet zou kunnen openen. Er staat nooit een waarde in. Het overzicht zegt dat iemand een nieuwe schaal heeft; de pagina van de persoon zegt welke, aan wie dat mag zien.

**De vorm.** Eén zin per bericht, in gewoon Nederlands, geschreven op de server zodat de bewoording op één plek staat. Het onderwerp is een link naar de plek waar het te zien is. Een reeks wordt één bericht ("3 maanden afgesloten op …"), en twee stappen kort na elkaar worden één zin ("Offerte gemaakt en aangeboden voor …"). Nieuws dat alles zegt, maakt de stappen ernaartoe overbodig: is de offerte getekend, dan staat er niet ook nog dat ze is gemaakt. Wat over de lezer zelf gaat, wordt tegen hem gezegd ("Je bent ingezet op …"). De tijd staat erbij zoals mensen die zeggen: vanochtend, gisteren, daarna een datum. De berichten staan per dag.

**Sinds je laatst keek.** Per persoon wordt één plek in de stroom bewaard: tot waar hij het overzicht heeft gezien. Wat daarna kwam is nieuw. Er is geen administratie per bericht. Het overzicht tonen zet de plek vooruit.

**Geen dubbeling met taken en meldingen.** Een gebeurtenis die voor de lezer een taak maakte, staat in het overzicht alleen als feit ("De offerte is ter goedkeuring aangeboden"), niet als opdracht. Meldingen op het eigen apparaat blijven voor taken en besluiten. Het overzicht stuurt niets.

## Gevolgen

- Een nieuw soort gebeurtenis vraagt een keuze: nieuws of niet. Zonder die keuze faalt een test.
- De lijst met nieuws is redactie, geen techniek. Ze hoort bijgesteld te worden op wat lezers ermee doen.
- Het overzicht leest bij elke aanvraag de recentste achthonderd nieuwswaardige gebeurtenissen en maakt daar berichten van. Verder terug dan dat gaat het niet; daarvoor is de geschiedenis.
- Het overzicht is van de eigen instantie. Dezelfde lijst is wel de natuurlijke basis voor wat een opdrachtgever of opdrachtnemer later over een gedeelde opdracht te zien krijgt, beperkt tot status en voortgang. Dat is niet gebouwd.
- Het overzicht staat niet in het menu (ADR 0042). Het is bereikbaar vanaf de startpagina.
