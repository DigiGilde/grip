# Wat op iemand wacht

Deze pagina verzamelt wat niet verder kan zonder een beslissing of een antwoord. Elk punt staat een keer, bij wie het kan beantwoorden, met een verwijzing naar de plek waar het is uitgewerkt. Wat technisch nog niet af is staat hier niet: dat staat in [plan.md](plan.md) en [rondgang.md](rondgang.md).

Stand: 9 oktober 2026.

## De opdrachtgever van grip

Beslissingen over wat grip moet doen.

| Punt | De keuze | Waar |
|---|---|---|
| Tarieven en een getekende opdracht | Na het vaststellen van een tarievenkaart volgt de begroting van een opdracht met een getekende offerte de nieuwe tarieven; het verschil met de offerte wordt getoond. Klopt dat, of houdt een getekende opdracht haar prijs? | [rondgang.md](rondgang.md), A612 |
| Maanden op volgorde | Een maand kan worden afgesloten terwijl een eerdere nog open is. Mag dat? | [rondgang.md](rondgang.md), B611 |
| Dekking van een kostenpost | De keuzelijst biedt ook personeelsregels aan als dekking. Hoort een kostenpost alleen door een vast bedrag gedekt te worden? | [rondgang.md](rondgang.md), A608 |
| Open rollen bij de eigenaar | Een rol invullen is nu ook de stap van de eigenaar of manager; haar teller en meldingen tellen open rollen op eigen opdrachten mee | [werkstromen.md](werkstromen.md) |
| Het merk | Richting a (greep) of b (letter), of geen van de vier. Nu staat a erin, voorlopig | [merk.md](merk.md), het vel in `docs/merk/richtingen.png` |
| Na het akkoord | De begroting kan na een getekende offerte nog worden gewijzigd; grip laat het verschil zien en blokkeert niets. Het voorstel is een aanvullende offerte op dezelfde opdracht, terwijl ze in uitvoering blijft. Dat is ontworpen, niet gebouwd | [werkstromen.md](werkstromen.md), "Ontwerp: verlengen of groeien na akkoord" |
| Een bevestigingscode per mail bij het tekenen | Alleen nodig als SSO Rijk opnieuw aanmelden niet afdwingt en de juristen het tijdstip van belang vinden. Niet gebouwd | [bewijs.md](bewijs.md), [sso-rijk.md](sso-rijk.md) |
| Advies van iemand zonder account | Nu legt alleen een beheerder het advies vast van een adviseur die niet in grip zit; de aanvrager wacht. Mag de aanvrager het zelf vastleggen? Let op de scheiding van taken: de aanvrager legt dan vast wat een ander besloot, niet een eigen oordeel | [taken.md](taken.md), ADR 0048 |
| Een of twee soorten opmaak | Een vacaturetekst kent cursief en opsommingen; een offerte ook vet en genummerde lijsten. Gelijktrekken kan | [vacatureteksten.md](vacatureteksten.md), [offerte-document.md](offerte-document.md) |
| Namen in een offerte | Grip weigert namen van medewerkers in een offerte. Een van de voorbeeldoffertes noemde ze wel, met een tarief per persoon. Blijft de regel? | ADR 0032 |
| Een heropende maand | Een maand die na het aanleveren is heropend wordt opnieuw volledig aangeleverd en vervangt het eerdere verzoek, ook als dat al gefactureerd was. Past dat, of moet het dan een verschil zijn? | ADR 0047, en de vraag aan de financiële administratie hieronder |
| De definitie van investeerruimte | Er staan twee voorlopige lezingen, in geld en in tijd | [domein.md](domein.md), begrippen |
| Deeltijd | Iedereen telt als voltijds. Een factor per persoon ontbreekt | [domein.md](domein.md) |
| Het menu | Variant E is gekozen en gebouwd. De aannames erachter zijn niet bij gebruikers getoetst | zie "Gebruikers" hieronder |
| Wijzigingen in Bouwmeester en Wies | De wijzigingen staan op lokale branches. Mogen ze worden voorgelegd? | [plan.md](plan.md), "Wijzigingen buiten grip" |
| De werkbranch | Al het werk staat op een eigen branch van de grip-repo, niet op de hoofdbranch | |
| Het Grist-document | De import wacht op een download van het document | [import-grist.md](import-grist.md) |
| Keuzes voor Wies | Of de privacyverklaring van Wies de uitwisseling met grip noemt, welk merk collega's uit grip krijgen, wie als actief telt, en hoe vaak er wordt gesynchroniseerd | [wies.md](wies.md) |
| Bestaande interne opdrachten | Een interne opdracht krijgt nu taken ("Maak de begroting", "Start de opdracht"). Bestaande concepten tonen die vanaf de volgende beoordeling | [werkstromen.md](werkstromen.md) |
| Een lijst-inzage en de persoon zelf | Het bekijken van een lijst met mensen wordt als een gebeurtenis vastgelegd en is alleen voor de beheerder zichtbaar. Een persoon ziet het niet onder "wie las mijn gegevens" | [gebeurtenissen.md](gebeurtenissen.md) |

## HR

| Punt | Vraag | Waar |
|---|---|---|
| Gerede en beoogde kandidaat | Wat is het verschil? Het aanvraagformulier legt het niet uit en verwijst naar HR. Grip behandelt de twee gelijk, op een vakje op het formulier na | [vacatureteksten.md](vacatureteksten.md), ADR 0018 |
| Wie beoordeelt een vacaturetekst | Nu kiest de schrijver per tekst een of meer personen. Is er een vaste beoordelaar? | [vacatureteksten.md](vacatureteksten.md), "Een tekst is werk" |
| De afgeleide standaardteksten | Vier teksten zijn afgeleid en niet nagelezen: Frontend developer, Productmanager, Adviseur, Lab manager | [vacatureteksten.md](vacatureteksten.md), "De rollen" |
| Keuzes in de teksten | Bedragen of alleen de schaal, de formulering van het contract, de toon, de naam van de eenheid | [vacatureteksten.md](vacatureteksten.md), "Analyse van de voorbeelden" |
| De sluitingsdatum | Een vacature heeft geen veld voor de datum tot wanneer reageren kan | [vacatureteksten.md](vacatureteksten.md) |
| De motivatie | Een aanvraag vraagt nu een vastgestelde aanleiding en motivatie. Klopt dat met de procedure? | [taken.md](taken.md) |

## De juristen

De zes vragen staan uitgeschreven onderaan [bewijs.md](bewijs.md). Kort:

1. Welk niveau van elektronische handtekening is nodig, binnen het Rijk en daarbuiten?
2. Hoe kwalificeert het bewijs dat grip maakt?
3. Volstaat de verklaring van de ondertekenaar dat hij bevoegd is?
4. Hoe lang mag het bewijs van de aanmelding worden bewaard?
5. Is een gekwalificeerde tijdstempel nodig?
6. Wat is de status van een offerte waarvan het bestand pas na het maken is vastgelegd?

Daarnaast: grip bewaart het aanvraagformulier van een vacature met namen van collega's, en ruimt het op na een termijn die de instantie instelt. Die termijn staat op nul dagen (direct na het sluiten van de vacature), maar het opruimen gebeurt alleen als iemand de opdracht daarvoor draait; een vast ritme is er niet ([ADR 0018](adr/0018-vacatureformulier-en-vacaturetekst.md)). En: hoe lang blijven gebeurtenissen met persoonsgegevens bewaard ([gebeurtenissen.md](gebeurtenissen.md), "Bewaren en wissen").

## De financiële administratie

De zes vragen staan in [ADR 0039](adr/0039-afsluiten-per-maand-aanleveren-per-periode.md). Kort:

1. Verrekenen onderdelen van het Rijk onderling met een factuur, of met een interne doorbelasting?
2. Welke gegevens heeft een factuurverzoek nodig?
3. In welk formaat wil een systeem de regels?
4. Mag de specificatie rollen noemen, of vraagt de opdrachtgever namen?
5. Aan wie en naar welk adres wordt aangeleverd?
6. Hoe komt het factuurnummer terug bij grip?

En een zevende, uit het werk daarna: als een maand na het aanleveren wordt heropend, is een nieuw volledig verzoek dat het eerdere vervangt dan werkbaar, ook als het eerdere al is gefactureerd? Zie [ADR 0047](adr/0047-een-naverrekening-is-een-opgeslagen-verschil-per-factuurperiode.md).

## Het platformteam

| Onderwerp | Wat nodig is | Waar |
|---|---|---|
| FSC | Staan de TLS-modus waarbij de pod het verkeer afhandelt, het koppelen van certificaten en het openzetten van poorten tussen projecten aan op productie? Een vaste hostnaam per component. De limiet op componenten en databases per project. Waar de directory van de groep draait. Of het register van de FSC-images is toegestaan | [plan.md](plan.md), "Risico's" |
| Aanmelden | Voor de eigen client van grip: de adressen waarnaar wordt teruggekeerd, de scopes, het kenmerk van SSO Rijk in het token, en of het verzoek om opnieuw aan te melden wordt doorgegeven. Voor de eerste proef: het geheim van de ontwikkelclient, dat de opdrachtgever zelf in `deploy/local/.env.sso` zet | [sso-rijk.md](sso-rijk.md) |
| Mail | De dienst voor uitgaande mail voor het project. Is de verbinding versleuteld? Mag de afzendernaam die van de organisatie zijn? Komt er terugkoppeling als een bericht niet aankomt? Is het dagmaximum per project in te stellen? | [ADR 0031](adr/0031-tekenlink-per-mail.md), [lokaal.md](lokaal.md), "Mail" |
| Meldingen | Een geheim voor de sleutel, een proces dat de wachtrij verstuurt, en uitgaand verkeer naar de meldingsdiensten van de browsermakers | [meldingen.md](meldingen.md), "Wat het platform moet leveren" |
| Taalmodel | De sleutel en de naam van het model bij VLAM. Welk model er achter zit is niet bevestigd | ADR 0018 |
| Processen | Een instantie draait een webproces, een proces voor verkeer van andere organisaties en een proces voor de wachtrijen. Kan het platform dat per instantie geven? | [lokaal.md](lokaal.md), "Een instantie" |
| Duurzame adressen | Een vast domein per instantie en per corpus, dat een verhuizing overleeft | [architectuur.md](architectuur.md), "Context uit het corpus" |

## De huisstijlcoördinator van het departement

Mag een product van het Rijk een eigen, ingetogen productmerk voeren naast de identiteit van de organisatie? De richtlijn zelf staat achter een login en is niet gelezen. Vast staat alleen dat het Rijkslogo, de huisstijl en het lettertype zijn voorbehouden aan het Rijk en wie in opdracht werkt. Zie [merk.md](merk.md), "Wat mag van de Rijkshuisstijl".

Daarbij: een organisatie buiten de Rijksoverheid die grip draait, krijgt nu nog steeds het lettertype en de kleuren van het Rijk. Dat is niet opgelost.

## De makers van het designsysteem

Voorstellen die uit het bouwen kwamen. Grip werkt er nu omheen, op een plek, met interne waarden van het designsysteem.

| Voorstel | Waarom | Waar |
|---|---|---|
| Een variant van de tabbalk met een onderlijn | De tabbalk tekent het gekozen tabblad als gevuld vlak, gelijk aan de hoofdknop | [ontwerp.md](ontwerp.md), "Navigatie" |
| Een maat en een toon op een onderdeel van de menubalk | Voor een rustige tweede balk en voor tabs | [ontwerp.md](ontwerp.md), "Navigatie" |
| Een plek voor een badge in een onderdeel van de menubalk | Het aantal open taken naast "Taken" | ADR 0033 |
| De annotatie in de teksteditor zonder teller | Elke gemarkeerde plek krijgt een klein cijfer dat niet uit kan | [hierarchie/b.md](hierarchie/b.md) |
| De ingeklapte stappenbalk in gewone woorden | Op een smal scherm drukt zij "Stap 2 van 5" af; grip tekent daar een eigen zin | [werkstromen.md](werkstromen.md) |
| Een onderdeel van de menubalk dat altijd in beeld blijft | De plek waar je bent mag niet achter "Meer" verdwijnen | ADR 0042 |

## Gebruikers

Niemand die het werk doet heeft grip gebruikt. De vragen voor drie tot vijf mensen per rol staan in [navigatie-evaluatie.md](navigatie-evaluatie.md), "Niet vast te stellen zonder gebruikers". De belangrijkste:

- Welke pagina opent iemand als eerste?
- Zoekt een planner het planbord onder "Team"?
- Gaan eigenaren uit zichzelf naar Kosten en Factureren?
- Welk woord gebruikt iemand voor geld: financieel, kosten, facturen?
- Is de startpagina of Taken het thuis?

En breder: is de zin in de kop van een opdracht ("Jij: ...", "Wacht op ...") genoeg om te weten wat je moet doen, zonder uitleg?

## Wat alleen in het echt te beproeven is

Dit is geen vraag aan iemand, maar het staat hier omdat het niets zegt over hoe goed het werkt tot het is gedaan.

| Wat | Waarom lokaal niet |
|---|---|
| Een aanmelding via SSO Rijk, en opnieuw aanmelden bij een besluit | Er is een geheim van het platform voor nodig |
| Een melding op een echte telefoon | Een browser zonder venster heeft geen meldingsdienst |
| Mail in een echte postbus, en wat spamfilters ermee doen | Lokaal vangt een mailvanger alles op |
| Een passkey op een echt apparaat, in Safari en Firefox | Beproefd met een nagebootste sleutel in een browser |
| Twee instanties van twee organisaties | Lokaal draaien beide op een machine |
| VLAM | Er is geen sleutel |
| Het echte corpus | Lokaal staat er een Bouwmeester met fictieve nodes |
