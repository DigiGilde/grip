# Koppeling met Wies

Wies laat zien wie waar werkt. Grip legt vast wie op welke opdracht is ingezet. Zonder koppeling typ je dat twee keer. Dit document beschrijft wat er tussen de twee systemen loopt en hoe je het aanzet. Het besluit erachter staat in [ADR 0013](adr/0013-wies-zonder-fsc.md).

## De verdeling

| Wat | Bron | Richting |
|---|---|---|
| Collega's: naam, e-mailadres, vaardigheden, labels, merk | Wies | grip leest uit Wies |
| Opdrachten, rollen, plaatsingen, open rollen | grip | Wies haalt op uit grip |

Beide systemen horen bij dezelfde organisatie. Daarom loopt dit via een koppelvlak met een sleutel en niet via FSC.

## Aanzetten

Elke richting staat uit zolang de instelling leeg is.

In grip:

| Instelling | Betekenis |
|---|---|
| `WIES_BASE_URL` | Adres van Wies |
| `WIES_API_KEY` | Sleutel waarmee grip collega's leest. In Wies heet dezelfde waarde `GRIP_READ_API_KEY` |
| `GRIP_EXPORT_KEY` | Sleutel waarmee Wies de export ophaalt. In Wies heet die ook `GRIP_EXPORT_KEY` |
| `WIES_SUBORGANIZATIONS` | Merken waaruit deze instantie mensen overneemt, gescheiden door komma's. Leeg betekent alle merken |

In Wies: `GRIP_BASE_URL`, `GRIP_EXPORT_KEY`, `GRIP_READ_API_KEY` en eventueel `GRIP_FULLTIME_HOURS` (standaard 36).

`GRIP_BASE_URL` in Wies moet het adres zijn waarop `/api` van grip bereikbaar is.

## Wat Wies bij grip ophaalt

`GET /api/integrations/wies/export` met `Authorization: Bearer <GRIP_EXPORT_KEY>`.

Per opdracht: `id`, `url`, `name`, `status`, `start_date`, `end_date`, `client_tooi_uri`, `owner_email` en `roles`.
Per rol: `id`, `url`, `description`, `start_date`, `end_date`, `fte`, `open` en `placements`.
Per plaatsing: `id`, `person_email`, `start_date`, `end_date`.

Wat erin zit:

- Alleen opdrachten waarover overeenstemming is: akkoord, in uitvoering, afgerond en verantwoord. Concepten, aanvragen, uitstaande offertes en afgewezen of geannuleerde opdrachten gaan niet mee.
- Een personeelsregel van de begroting levert een rol per inzet op: de plek die iemand vult, met het eigen aandeel en de eigen periode van die persoon. Wies telt uren per rol, dus zo kloppen de uren per collega. Wat van de regel overblijft is een open rol. Vaste posten zijn geen rollen.
- De opdrachtgever gaat mee als TOOI-URI. Wies zoekt daar de organisatie bij.

Wat er nooit in zit: bedragen, tarieven, tariefcategorieën, notities en contactpersonen. Het aandeel van een persoon gaat wel mee, als omvang van de rol in FTE; dat is bemensing en geen geld. De export bevat alleen gegevens uit de klassen A (opdracht-basis) en C (bemensing) uit [toegang.md](toegang.md). Het schema heeft geen veld voor iets anders, en een test controleert het antwoord daarop.

### Wanneer een rol open is

Grip kijkt naar een peildag: vandaag, of de eerste dag van de regel als die nog niet begonnen is. De inzet die op die dag loopt wordt opgeteld en vergeleken met de omvang van de regel.

| Situatie | In de export |
|---|---|
| Niemand ingezet | Een open rol voor de hele regel |
| Deels ingezet | De gevulde rollen, en een open rol voor de rest |
| Volledig ingezet (verschil kleiner dan 0,05 FTE) | Alleen gevulde rollen |
| Inzet is afgelopen, regel loopt nog | De rol met de oude plaatsing, plus een open rol voor de hele omvang |
| Gepubliceerde vacature op een volledig ingezette regel | Toch een open rol voor de hele omvang, met de functietitel van de vacature |
| Regel is afgelopen | Geen open rol |

Het `id` van een open rol is het id van de regel met `:open` erachter. Het `id` van een gevulde rol is het id van de inzet.

Een gat verderop in de tijd telt niet mee. Loopt de inzet af voordat de regel afloopt, dan wordt de rol pas open op de dag dat de inzet voorbij is.

Een vacature zonder begrotingsregel gaat niet naar Wies. Wies hangt een rol altijd aan een opdracht, en die is er dan niet.

### Wat Wies ermee doet

Wies slaat alles op met bron `grip`. Zulke gegevens zijn in Wies niet te bewerken; wijzigen doe je in grip. Een open rol verschijnt op de pagina Aanvragen. Grip rekent in FTE en Wies in uren per week, dus Wies zet de omvang om met 36 uur per FTE.

Personen koppelt Wies op e-mailadres, zonder op hoofdletters te letten. Wies maakt nooit een collega aan omdat grip die noemt. Een plaatsing van iemand die Wies niet kent wordt overgeslagen en geteld; de rol staat dan in Wies als gesloten en niet als aanvraag.

Wat uit de export verdwijnt, sluit Wies af of verwijdert het: een plaatsing die al liep eindigt die dag, een toekomstige verdwijnt. Een lege export verandert niets, omdat die eerder op een verkeerd adres wijst dan op het verdwijnen van alle opdrachten.

## Wat grip uit Wies leest

Grip leest collega's op `GET {WIES_BASE_URL}/koppelvlak/grip/collegas/`. Per collega: `public_id`, `name`, `email`, `skills`, `labels`, `suborganization` en `active`. Plaatsingen zitten er niet in.

Inloggen in grip kan alleen met een persoon die vooraf is aangemaakt. Deze lijst is dus de manier waarop mensen toegang krijgen. Grip maakt of deactiveert daarbij niemand uit zichzelf: het stelt wijzigingen voor en de beheerder bevestigt ze.

`GET /api/integrations/wies/reconciliation` geeft de voorstellen en verandert niets.

| Voorstel | Wanneer |
|---|---|
| Toevoegen | Collega met een actief account in Wies, binnen de merken van deze instantie, die nog geen persoon is in grip |
| Deactiveren | Persoon in grip die in Wies geen actief account meer heeft |
| Deactiveren, met reden "Niet bekend in Wies" | Persoon in grip die Wies helemaal niet kent. Kijk hier goed naar: niet iedereen hoeft in Wies te staan |
| Opnieuw activeren | Inactieve persoon in grip met een actief account in Wies |
| Naam wijzigen | De naam in Wies is anders |

Een collega van een ander merk wordt niet voorgesteld om toe te voegen. Het is ook geen reden om iemand te deactiveren.

`POST /api/integrations/wies/reconciliation` met `{"changes": [{"action": "add", "email": "..."}]}` voert de bevestigde wijzigingen door. Grip haalt de lijst op dat moment opnieuw op en past alleen toe wat Wies dan nog onderbouwt. Een wijziging die niet (meer) wordt voorgesteld komt terug als niet toegepast, met de reden. Jezelf deactiveren kan niet. Elke wijziging laat een regel achter in de auditlog.

Beide routes zijn alleen voor de beheerder.

Een nieuwe persoon heeft nog geen functie. Die kent de beheerder daarna toe.

De beheerder doet dit op het scherm "Voorstellen uit Wies", te bereiken vanaf de pagina Team: de voorstellen per soort, een vinkje per regel, en na het bevestigen per regel of die is doorgevoerd.

## Wat nog ontbreekt

- Vaardigheden en labels uit Wies worden gelezen en getoond bij een voorstel, maar niet opgeslagen in grip.
- De export wordt op verzoek opgebouwd. Wies haalt hem op wanneer een beheerder daar op de knop drukt; een vast ritme is er nog niet.
