# Koppeling met Wies

Wies laat zien wie waar werkt. Grip legt vast wie op welke opdracht is ingezet. Zonder koppeling typ je dat twee keer. Dit document beschrijft wat er tussen de twee systemen loopt en hoe je het aanzet. Het besluit erachter staat in [ADR 0013](adr/0013-wies-zonder-fsc.md).

## De verdeling

| Wat | Bron | Richting |
|---|---|---|
| Collega's: naam, e-mailadres, vaardigheden, labels, merk | Wies | grip leest uit Wies |
| Opdrachten, rollen, plaatsingen, open rollen | grip | Wies haalt op uit grip |
| Een nieuwe collega, vanaf de aanname tot Wies die kent | grip | grip stelt voor, staf van Wies bevestigt |

De derde regel is de uitzondering op de eerste, en staat verderop uitgewerkt onder "Een nieuwe collega". Het besluit staat in [ADR 0022](adr/0022-een-nieuwe-collega-is-eerst-in-grip-bekend.md).

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
| `WIES_DEFAULT_SUBORGANIZATION` | Het merk waaronder grip een nieuwe collega voorstelt als er bij de aanname geen is opgegeven |
| `PROSPECTIVE_RETENTION_DAYS` | Dagen dat een persoon bewaard blijft nadat een aanname niet doorging. Standaard 28 |

In Wies: `GRIP_BASE_URL`, `GRIP_EXPORT_KEY`, `GRIP_READ_API_KEY` en eventueel `GRIP_FULLTIME_HOURS` (standaard 36).

`GRIP_BASE_URL` in Wies moet het adres zijn waarop `/api` van grip bereikbaar is.

## Wat Wies bij grip ophaalt

`GET /api/integrations/wies/export` met `Authorization: Bearer <GRIP_EXPORT_KEY>`.

Per opdracht: `id`, `url`, `name`, `status`, `start_date`, `end_date`, `client_tooi_uri`, `client_registry_id`, `owner_email` en `roles`.
Per rol: `id`, `url`, `description`, `role_name`, `role_wies_id`, `start_date`, `end_date`, `fte`, `open` en `placements`. `role_name` is de rol uit de catalogus en `role_wies_id` het kenmerk van de bijbehorende rol in Wies; Wies zoekt eerst op dat kenmerk en dan op de naam. Zie [rollen.md](rollen.md).
Per plaatsing: `id`, `person_uri`, `person_email`, `start_date`, `end_date`. De URI is de sleutel; het adres ontbreekt bij een aanstaande collega.

Wat erin zit:

- Alleen opdrachten waarover overeenstemming is: akkoord, in uitvoering, afgerond en verantwoord. Concepten, aanvragen, uitstaande offertes en afgewezen of geannuleerde opdrachten gaan niet mee.
- Een personeelsregel van de begroting levert een rol per inzet op: de plek die iemand vult, met het eigen aandeel en de eigen periode van die persoon. Wies telt uren per rol, dus zo kloppen de uren per collega. Wat van de regel overblijft is een open rol. Vaste posten zijn geen rollen.
- De opdrachtgever gaat mee als TOOI-URI en als nummer van het overheidsregister. Wies zoekt de organisatie op de TOOI-URI en anders op dat nummer, want de meeste onderdelen van organisaties hebben geen TOOI-URI. Zie [organisaties.md](organisaties.md).

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

Personen koppelt Wies eerst op de persoons-URI en daarna op e-mailadres, zonder op hoofdletters te letten. De synchronisatie maakt nooit een collega aan omdat grip die noemt; dat gebeurt alleen nadat staf een voorstel heeft bevestigd. Een plaatsing van iemand die Wies niet kent wordt overgeslagen en geteld; de rol staat dan in Wies als gesloten en niet als aanvraag.

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

## Een nieuwe collega

Vier systemen, elk met een eigen taak:

| Systeem | Houdt bij |
|---|---|
| Het wervingssysteem (bij ODI: Emply) | Kandidaten, sollicitaties en de selectie |
| Grip | De vraag (rol, schaal, omvang, akkoord, formulier, tekst), en vanaf de aanname de aanstaande collega en de planning |
| Wies | De collega, zodra staf die heeft bevestigd |
| De personeelsadministratie | Uiteindelijk de bron van bestaan en dienstverband; nog niet aangesloten |

Grip bewaart geen kandidaten. Een vacature in grip heeft een verwijzing naar de vacature in het wervingssysteem: het kenmerk en een link, met de hand ingevuld (`PUT /api/vacancies/{id}/recruitment-ref`).

### Wie weet wat, en wanneer

| Moment | Grip | Wies |
|---|---|---|
| Selectie loopt | Niets over personen | Niets |
| Aangenomen, startdatum afgesproken | Aanstaande collega: naam, startdatum, rol; in te plannen | Voorstel "nieuwe collega" |
| Staf van Wies bevestigt | Hoort dat het voorstel is bevestigd | Collega zonder account en zonder adres; plaatsingen zichtbaar |
| Account en adres bestaan | Krijgt het adres voorgesteld en koppelt het; inloggen kan | Bron van wie de persoon is |
| Vertrek | Voorstel om te deactiveren, zoals altijd | Account vervalt |

### Hoe het loopt

1. Op de vacature wordt de aanname vastgelegd: `POST /api/vacancies/{id}/hire` met een naam of een bestaande persoon, en de startdatum. De vacature is daarmee vervuld. Voor een nieuwe naam ontstaat een aanstaande collega; hangt de vacature aan een begrotingsregel, dan stelt grip de inzet voor, of legt die meteen vast.
2. Elke persoon heeft een URI van de instantie: `{basis}/id/persoon/{id}`. Dat is de sleutel tussen de twee systemen. Het e-mailadres is het niet, want dat bestaat nog niet.
3. Wies haalt de voorstellen op bij `GET /api/integrations/wies/proposed-colleagues`, met dezelfde sleutel als de export. Per voorstel: `person_uri`, `name`, `suborganization`, `start_date` en `state` (`open` of `withdrawn`). Meer gaat er niet mee.
4. Staf van Wies bevestigt of wijst af onder "Voorstellen uit grip". Bij bevestigen kan staf een collega aanwijzen die al in Wies staat; dan komt er geen tweede bij.
5. Wies meldt de beslissing terug in het antwoord waarmee grip collega's leest. Het scherm "Voorstellen uit Wies" toont de uitgaande voorstellen met hun stand.
6. Zodra Wies het e-mailadres heeft, verschijnt in grip het voorstel "koppelen". De beheerder bevestigt en het adres komt bij de bestaande persoon. Heeft Wies de URI niet (staf maakte de collega los aan), dan biedt grip de koppeling aan op gelijke naam, naast "toevoegen". Kies er een; beide tegelijk levert toch maar een persoon op.

Een persoon zonder adres wordt nooit voorgesteld om te deactiveren.

### Als de aanname niet doorgaat

`POST /api/vacancies/{id}/hire/withdraw`, of op het teamscherm via `POST /api/people/{id}/withdraw-hire`. De planning van de persoon vervalt, het voorstel aan Wies wordt ingetrokken (Wies verwijdert de collega als die nog geen account en geen adres had) en de persoon verdwijnt uit grip na `PROSPECTIVE_RETENTION_DAYS`. Het opruimen zelf is een functie (`standing.purge_withdrawn`) die nog op een vast ritme moet worden gestart.

De vacature blijft vervuld. Voor dezelfde rol is een nieuwe vacature nodig.

### Privacy

Grip ontvangt een persoon pas op het moment van aanname; kandidaten blijven in het wervingssysteem. Vóór de eerste werkdag heeft grip van die persoon alleen de naam en de startdatum, en Wies krijgt daarvan de naam, het merk en de startdatum.

Voorgestelde zin voor de privacyverklaring van grip:

> Van een nieuwe collega leggen wij vanaf de aanname de naam en de startdatum vast, om de inzet te kunnen plannen. Deze gegevens delen wij met Wies, het systeem van dezelfde organisatie dat laat zien wie waar werkt. Gegevens van sollicitanten staan niet in grip. Gaat een aanname niet door, dan verwijderen wij de gegevens binnen vier weken.

Voorgestelde zin voor de privacyverklaring van Wies:

> Wies wisselt gegevens uit met grip, het systeem van dezelfde organisatie waarin opdrachten worden gepland. Grip leest naam, e-mailadres, vaardigheden, labels en merk van collega's. Wies ontvangt uit grip de plaatsingen, en van een nieuwe collega de naam, het merk en de startdatum zodra die is aangenomen. Gaat een aanname niet door, dan wordt die collega uit Wies verwijderd.

De termijn van vier weken is een instelling. Laat de privacyfunctionaris die bevestigen.

## Wat nog ontbreekt

- Een koppeling met het wervingssysteem. De aanname wordt met de hand vastgelegd.
- Een vast ritme voor het opruimen na een aanname die niet doorging.
- Vaardigheden en labels uit Wies worden gelezen en getoond bij een voorstel, maar niet opgeslagen in grip.
- De export wordt op verzoek opgebouwd. Wies haalt hem op wanneer een beheerder daar op de knop drukt; een vast ritme is er nog niet.
