# Vacatureteksten

Grip levert een bibliotheek van standaard vacatureteksten mee, per rol. Een standaardtekst gebruik je direct op een vacature, of als voorbeeld voor een concept op maat. Deze pagina beschrijft waar de teksten vandaan komen, hoe de bibliotheek werkt en wat er naar het taalmodel gaat. Het besluit staat in ADR 0034.

## Analyse van de voorbeelden

De bibliotheek is gebouwd op acht vacatureteksten van de organisatie zelf: software engineer (twee varianten, waarvan een voor een bepaald productteam), programmamanager, product owner, staff of senior engineer, standards engineer, een gecombineerde rol van UX designer, researcher en frontend developer, en wetgevingsjurist. De voorbeelden zelf staan niet in de repo.

### De opbouw die ze delen

| Onderdeel | Wat erin staat | Lengte | Vast of per rol |
|---|---|---|---|
| Inleiding | Waarom dit werk ertoe doet, vaak als vraag of "Stel je voor" | 40 tot 90 woorden | Per rol, bij een productteam per opdracht |
| Dit ga je doen | De rol in twee of drie alinea's, dan "Een greep uit je werkzaamheden" als lijst van vijf tot zeven punten | 150 tot 300 woorden | Per rol |
| Dit doe je bij het project | Wat het team maakt en wat jouw plek daarin is | 60 tot 120 woorden | Per opdracht |
| Dit krijg je | Schaal, contract, uren, standplaats | Vier of vijf regels | Vast, ingevuld uit de vacature |
| Dit bieden we nog meer | Keuzebudget, ontwikkeling, reiskosten, verlof, pensioen | 80 tot 120 woorden | Vast |
| Dit vragen wij | Een alinea over wie je bent, dan een lijst van zes tot tien eisen | 120 tot 220 woorden | Per rol, de zwaarte per schaal |
| Hier kom je te werken | Het onderdeel en de organisatie erboven | 120 tot 180 woorden | Vast |
| Bijzonderheden | Hoe je solliciteert, de procedure, bij wie je terecht kunt | 80 tot 120 woorden | Vast, contact uit de instellingen |
| Slot | Dat iedereen welkom is | 40 woorden | Vast |

### Wat per rol verschilt

- **De inleiding en "Dit ga je doen".** Hier zit het vak: bouwen, ontwerpen, adviseren, richting geven.
- **De eisen.** Opleiding of denkniveau, jaren ervaring, vakkennis en houding.
- **Zwaarte.** Tot en met schaal 12 gaat het om uitvoeren en adviseren, vanaf schaal 13 om richting geven, prioriteren en bestuurders meekrijgen. Het aantal jaren ervaring loopt mee: vijf jaar in de meeste teksten, tien in een tekst op schaal 13.
- **Het team of product.** Teksten voor een productteam beginnen met het product en hebben een eigen onderdeel over het project. Algemene teksten beginnen met de organisatie.

### Toon

De teksten spreken de lezer aan met je, in actieve zinnen. De algemene teksten zijn uitbundig (uitroeptekens, "gepassioneerd", "dé specialist"), de teksten voor het productteam zijn zakelijker en concreter. De standaardteksten volgen de zakelijke variant.

### Waar de voorbeelden elkaar tegenspreken

Dit zijn keuzes voor de organisatie. De standaardteksten kiezen steeds de eerste mogelijkheid; pas ze aan als jullie anders willen.

| Punt | In de voorbeelden | Gekozen in de standaardtekst |
|---|---|---|
| Naam van het onderdeel | De voorbeelden noemen een eerdere naam van het onderdeel | Een instelling, `{eenheid}`; de beginwaarde is de huidige naam |
| Salaris | Soms alleen de schaal, soms ook een bedrag in euro's | Alleen de schaal: een bedrag veroudert bij elke cao |
| Contract | Jaarcontract met uitzicht op vast, of zes maanden met kans op verlenging | Uit het soort contract van de vacature |
| Procedure | Met of zonder telefonische intake | Twee gesprekken en een arbeidsvoorwaardengesprek |
| Opleidingseis | Soms hbo of wo, soms geen | Benoemd waar het voorbeeld het vraagt; denkniveau waar dat volstaat |
| Opsomming | Met of zonder hoofdletter en puntkomma | Kleine letter, puntkomma, punt aan het eind |
| Contactpersoon | Namen en telefoonnummers in de tekst | Een instelling, `{contact}`; geen naam in een standaardtekst |
| Volgorde | "Dit vragen wij" voor of na "Dit krijg je" | Eerst het werk, dan wat je krijgt, dan wat we vragen |

### Getoetst aan wat de overheid zelf vraagt

- **Functiegebouw Rijk.** Elke standaardtekst noemt de functiegroep waar de rol meestal in valt. De schalen van de tekst vallen binnen de schalen van die groep.
- **Begrijpelijke taal.** De standaardteksten houden zinnen kort, vermijden vaktaal die een buitenstaander niet kent en gebruiken geen Engelse modewoorden. Dat wijkt bewust af van enkele voorbeelden.
- **Niemand uitsluiten.** De teksten vragen ervaring en vaardigheden. Ze vragen geen eigenschappen die niets met het werk te maken hebben. Het slot nodigt iedereen uit.
- **Geen belofte die grip niet kan waarmaken.** Bedragen, verlofuren en percentages die per cao wijzigen staan alleen in het gedeelde onderdeel "Dit bieden we nog meer", zodat ze op één plek zijn bij te werken.

## De rollen

De rollencatalogus van grip (`catalogue_role`) bevat de rollen waarop mensen worden ingezet. Ze komen uit Wies waar die koppeling is ingesteld, en anders uit de begrotingsregels: wie een rol typt die nog niet bestaat, voegt haar toe. De bibliotheek brengt twaalf rollen mee. Bestaat een rol al onder dezelfde naam of onder een van de andere namen, dan wordt die gebruikt.

| Rol | Schaal | Functiegroep | Herkomst van de tekst |
|---|---|---|---|
| Software engineer | 11 t/m 13 | (Senior) Adviseur | Uit de voorbeelden |
| Staff engineer | 12 t/m 13 | (Senior) Adviseur | Uit de voorbeelden |
| Standards engineer | 12 t/m 13 | (Senior) Adviseur | Uit de voorbeelden |
| UX designer | 11 t/m 12 | (Senior) Adviseur | Uit de voorbeelden |
| Frontend developer | 11 t/m 12 | (Senior) Adviseur | Afgeleid, nog niet nagelezen |
| Product owner | 12 t/m 13 | Expert Iv | Uit de voorbeelden |
| Productmanager | 13 t/m 14 | Coördinerend / Specialistisch Adviseur | Afgeleid, nog niet nagelezen |
| Programmamanager | 13 t/m 14 | Project-/Programmamanager | Uit de voorbeelden |
| Wetgevingsjurist | 12 t/m 13 | (Senior) Adviseur | Uit de voorbeelden |
| Analist | 11 t/m 13 | (Senior) Adviseur | Uit de voorbeelden |
| Adviseur | 11 t/m 13 | (Senior) Adviseur | Afgeleid, nog niet nagelezen |
| Lab manager | 12 t/m 13 | (Senior) Adviseur | Afgeleid, nog niet nagelezen |

Een afgeleide tekst is geschreven vanuit de gedeelde opbouw en het dichtstbijzijnde voorbeeld. Het is geen tekst van de organisatie. Hij staat als "Afgeleid, nog niet nagelezen" tot een beheerder hem heeft gelezen.

## De bibliotheek

Een standaardtekst bestaat uit onderdelen. Een onderdeel heeft een kop en een tekst van alinea's, lijsten (een streepje per regel) en nadruk (tussen sterretjes). Meer kan er niet in.

- **Gedeelde onderdelen** staan één keer in de bibliotheek. Elke standaardtekst verwijst ernaar. Wie "Dit bieden we nog meer" wijzigt, wijzigt het voor elke rol.
- **Invulplekken** staan tussen accolades: `{functie}`, `{schaal}`, `{uren}`, `{contract}`, `{standplaats}`, `{organisatie}`, `{eenheid}`, `{website}`, `{contact}`, `{sluitingsdatum}`, `{opdracht}`. De vacature en de instellingen vullen ze. Wat niet te vullen is, blijft staan als `[vul aan: ...]`. Een tekst met zo'n plek kan niet worden vastgesteld.
- **Meegeleverd.** De teksten staan in `backend/grip/data/vacancy_texts/`. Bij het starten laadt grip het profiel uit `VACANCY_TEXT_PROFILE`. Laden voegt toe wat ontbreekt en werkt bij wat niemand heeft gewijzigd. Een tekst die een mens heeft aangepast blijft staan.
- **Beheer.** Onder Vacatures, Standaardteksten: per rol de stand (uit de voorbeelden, afgeleid, aangepast door wie en wanneer), wijzigen per onderdeel, een gedeeld onderdeel in één keer wijzigen met de rollen waarin het staat, een tekst bekijken zoals een vacature hem krijgt, en een tekst kopiëren naar een nieuwe rol.
- **Gedeeld met de offerte.** De naam van de organisatie komt uit de afzender onder Beheer, dezelfde die op een offerte staat. De tekst over het onderdeel in een vacature is een eigen gedeeld onderdeel, omdat een vacature een andere lezer heeft dan een offerte.

## Een tekst op een vacature

Op het tabblad Tekst van een vacature zijn er twee ingangen.

1. **Begin met de standaardtekst.** Grip zoekt de tekst van de rol: eerst op de rol van de begrotingsregel, dan op de functienaam of een andere naam van de rol, en anders de tekst van een rol in dezelfde functiegroep. Dat laatste zegt het scherm erbij. De invulplekken worden gevuld en het resultaat is een concept met de herkomst "Uit de standaardtekst Software engineer, versie 2026-10-08".
2. **Stel een tekst op maat op.** Het taalmodel schrijft de onderdelen van de rol opnieuw voor deze vacature, met de standaardtekst als voorbeeld. De gedeelde onderdelen worden daarna ingevoegd uit de bibliotheek en niet door het model geschreven.

In beide gevallen is het resultaat een concept. Een mens leest het, past het aan en stelt het vast. Alleen een vastgestelde tekst gaat grip uit.

### Wat er naar het taalmodel gaat

| Gaat mee | Waarvandaan |
|---|---|
| De rol, de schaal, de omvang in fte, de periode en het soort contract | De vacature |
| De naam van de opdracht en van de opdrachtgever | De opdracht van de begrotingsregel |
| De naam van het onderdeel | De instellingen |
| Titels van de context van de opdracht en van de politieke wens waar die uit volgt | Het corpus, als de opdracht eraan gekoppeld is |
| De aanwijzing die je typt | Het formulier |
| De eigen onderdelen van de standaardtekst van de rol en van hooguit één verwante rol | De bibliotheek |

| Gaat niet mee | Waarom |
|---|---|
| Namen van collega's en kandidaten | Een tekst met een naam van iemand uit de instantie wordt geweigerd voor hij is verstuurd |
| Tarieven, kostprijzen, marges, declarabiliteit | Gegevensklassen D, E en F; ze worden hier niet gelezen |
| De gedeelde onderdelen | Die staan vast en worden ingevoegd |
| Teksten van andere vacatures | Alleen de standaardtekst is voorbeeld |

De stijlregels in de opdracht aan het model komen uit de analyse hierboven: je-vorm, taalniveau B1, zinnen van hooguit twintig woorden, niets beloven over salaris of contract, geen eisen die mensen uitsluiten.

## Een tekst is werk

Een tekst doorloopt een weg, zo vaak heen en terug als nodig is.

| Stand | Betekenis | Wat erna kan |
|---|---|---|
| Nog niet begonnen | Er is geen versie | Beginnen met de standaardtekst, een tekst op maat, of zelf schrijven |
| In de maak | Er is een versie die niet is vastgesteld | Verder schrijven, om een oordeel vragen, vaststellen |
| Ter beoordeling | De laatste versie ligt bij een of meer mensen | Oordelen (wie gevraagd is), terugnemen (de schrijver) |
| Terug met opmerkingen | Iemand vraagt om wijzigingen | De opmerkingen verwerken in een nieuwe versie |
| Akkoord, nog vaststellen | Iedereen die gevraagd is, is akkoord | Vaststellen |
| Vastgesteld | Deze versie gaat grip uit | Aanpassen: dat maakt een nieuwe ronde, en tot die is vastgesteld geldt de oude tekst |

- **Meer mensen.** Elke versie blijft bewaard met wie en wanneer. Wie opslaat, noemt de versie waar hij van uitging. Heeft iemand anders intussen opgeslagen, dan weigert grip en blijven beide teksten staan: die van de ander als versie, die van jou in het formulier.
- **Opmerkingen** horen bij een onderdeel van de tekst. Ze worden beantwoord en afgehandeld.
- **Wat er wijzigde** staat per onderdeel in woorden: "Dit ga je doen: 1 alinea herschreven, 12 woorden langer."
- **Wie beoordeelt** kiest de schrijver per ronde. Grip stelt voor: de motivatie naar wie de aanvraag goedkeurt, de vacaturetekst naar de HR-adviseur van de vacature. Wie gevraagd is, ziet de vacature zonder namen en kan oordelen en opmerkingen plaatsen, niets anders.
- **Welke tekst nodig is.** De motivatie staat op het aanvraagformulier: elke vacature heeft er een. Een vacaturetekst is nodig voor een vacature die wordt opengesteld. Een vacature voor een beoogde of gerede kandidaat wordt niet gepubliceerd; daar toont grip niets over een vacaturetekst.

### Taken

| Taak | Ontstaat | Sluit door | Voor |
|---|---|---|---|
| Schrijf de motivatie en stel haar vast | De vacature is in voorbereiding of aangevraagd | De motivatie is vastgesteld | Wie het laatst schreef, anders de aanvrager |
| Schrijf de vacaturetekst en stel haar vast | De vacature wordt opengesteld en is nog niet open | De vacaturetekst is vastgesteld | Wie het laatst schreef, anders de aanvrager |
| Beoordeel de tekst | De tekst is aangeboden | Het oordeel is gegeven | Elke beoordelaar, binnen drie werkdagen |
| Verwerk de opmerkingen | De tekst kwam terug met opmerkingen | Er is een nieuwe versie, of de tekst is vastgesteld | De schrijver |
| Leg de link naar de gepubliceerde vacature vast | De vacature is opengesteld | De link is vastgelegd | De aanvrager |

De taken staan in planversie 2026.3. Een vacature die onder een eerdere versie is begonnen, houdt die versie en krijgt deze taken niet.

## Gepubliceerd

Een opengestelde vacature heeft een adres dat iedereen kan openen. Dat leg je vast op het tabblad Tekst, per plek: de interne vacaturepagina, Werken voor Nederland, een externe site. Het staat daarna in de kop van de vacature.

Dit is iets anders dan de verwijzing naar het wervingssysteem op het tabblad Vervulling. Die link opent alleen voor recruiters. Grip haalt niets op uit het wervingssysteem: kenmerk en link worden met de hand ingevuld.

## Nog niet gebouwd

- De link naar de gepubliceerde vacature gaat nog niet mee naar Wies of naar een andere instantie. Het koppelvlak heeft er geen veld voor.
- Een beoordelaar krijgt een taak, geen mail.
- Een rol als beoordelaar ("de HR-adviseurs") kan nog niet: je kiest mensen.
- Twee versies naast elkaar vergelijken kan via de API, het scherm toont alleen wat er in de laatste versie wijzigde.
