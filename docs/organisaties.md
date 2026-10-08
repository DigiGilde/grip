# Organisaties

Een opdracht heeft een opdrachtgever en een opdrachtnemer. Beide kies je uit één lijst. Die lijst bevat de overheidsorganisaties uit het openbare register en wat een instantie er zelf aan toevoegt.

## Waar de lijst vandaan komt

De overheidsorganisaties komen uit de organisatie-export van organisaties.overheid.nl. Dat is dezelfde bron die Wies gebruikt, gelezen met dezelfde regels. Daardoor hebben grip en Wies dezelfde lijst en blijft de koppeling tussen de twee kloppen.

Grip haalt de lijst niet bij Wies op. Elke instantie draait dezelfde software, ook bij organisaties zonder Wies, en elke instantie heeft opdrachtgevers en opdrachtnemers nodig.

De regels voor het lezen en bijwerken zijn overgenomen uit de organisatiesynchronisatie van Wies, die onder de EUPL 1.2 is uitgebracht. De herkomst staat in de modules onder `backend/grip/integrations/organisations`.

## Twee soorten organisaties

| Soort | Wat | Bewerken |
|---|---|---|
| Uit het register | Ministeries, agentschappen, zbo's, gemeenten, provincies, waterschappen en hun onderdelen | Volgt het register. Alleen het adres van de grip-instantie is hier te wijzigen |
| Zelf toegevoegd | Een partij buiten het register, zoals een stichting of een bedrijf, of een eenheid binnen een organisatie, zoals een gilde of een team | Naam en einddatum zijn te wijzigen |

Een eenheid die je zelf toevoegt onder een organisatie uit het register krijgt de TOOI-URI van de dichtstbijzijnde organisatie erboven die er een heeft, plus een eigen kenmerk. Twee eenheden van dezelfde organisatie delen dus een TOOI-URI en verschillen in kenmerk.

## Het register ophalen

Ophalen brengt de lijst in lijn met het register:

- Een organisatie wordt herkend aan haar TOOI-URI. Heeft ze die niet, dan aan het eigen nummer van het register. Dat laatste geldt voor bijna alle onderdelen, zoals een directie of een directoraat-generaal.
- De hiërarchie volgt de nesting in het register.
- Een organisatie die in het register al is opgeheven komt er niet bij. Kent grip haar al, dan krijgt ze haar einddatum.
- Een organisatie die uit het register is verdwenen krijgt vandaag als einddatum.
- Een opgeheven organisatie waar niets naar verwijst wordt verwijderd. Verwijst er een opdracht naar, of valt er een zelf toegevoegde eenheid onder, dan blijft ze staan.
- Een organisatie die zelf was toegevoegd met een TOOI-URI die het register ook kent, wordt overgenomen: ze volgt daarna het register.
- De inlichtingendiensten en wat eronder valt worden niet overgenomen.
- Wat grip zelf bijhoudt, zoals het adres van de grip-instantie, blijft staan.

Ophalen kan op twee manieren:

- Op de pagina Beheer, onder Organisaties, met de knop "Haal het register op". Alleen de beheerder kan dat.
- Met `just sync-organisations`. Met `--file PAD` verwerk je een export die je eerder hebt gedownload.

Het register antwoordt traag: het ophalen van de export duurt enkele minuten. Vanaf het scherm loopt het daarom op de achtergrond door en vraagt de pagina de stand op. Het verwerken zelf duurt een paar seconden. Er is nog geen vast ritme; ophalen gebeurt wanneer iemand het start.

Er wordt nooit half bijgewerkt. De export wordt eerst helemaal binnengehaald en daarna in één keer verwerkt. Is het register onbereikbaar, is de export onleesbaar, of bevat hij minder dan de helft van wat grip al heeft, dan verandert er niets. Elke poging wordt vastgelegd met de uitkomst, ook een mislukte.

`just seed --reset` leegt ook deze lijst. Haal daarna het register opnieuw op.

## Zoeken en kiezen

`GET /api/organisations` zoekt in de hele lijst.

| Parameter | Betekenis |
|---|---|
| `q` | Zoekt in naam en afkortingen. Elk woord moet voorkomen. Hoofdletters en accenten maken niet uit |
| `type` | Alleen organisaties van dit soort, bijvoorbeeld `Ministerie` |
| `source` | `registry` of `manual` |
| `include_ended` | Ook opgeheven organisaties |
| `page`, `page_size` | Bladeren; hooguit 100 per pagina |

De volgorde: eerst een afkorting die precies klopt, dan een naam die precies klopt, dan een afkorting of naam die met de zoekterm begint, dan een woord in de naam dat ermee begint, dan de rest. Binnen een groep staan organisaties voorop waar al een opdracht aan hangt. Zonder zoekterm begint de lijst met die organisaties, daarna wat zelf is toegevoegd en daarna de ministeries.

Elke treffer heeft een `path`: de namen van boven naar beneden, zoals "Ministerie X > Directoraat-generaal Y > Directie Z". Zo zijn twee directies met dezelfde naam uit elkaar te houden. Een agentschap, zbo, adviescollege of inspectie zonder bovenliggende organisatie staat onder het ministerie waar het register het aan koppelt.

Verder: `GET /api/organisations/{id}`, `GET /api/organisations/types` voor de soorten met aantallen, `POST /api/organisations` om er zelf een toe te voegen met een naam en eventueel een `parent_id`, en `PATCH /api/organisations/{id}`.

Wie een naam toevoegt die op dezelfde plek al bestaat, krijgt de bestaande organisatie terug en geen tweede.

## Wie wat mag

| Handeling | Wie |
|---|---|
| Zoeken en bekijken | Iedereen in de instantie |
| Zelf een organisatie toevoegen | Wie een opdracht mag aanmaken, en de beheerder |
| Een organisatie wijzigen | De beheerder |
| Het register ophalen | De beheerder |

## In een formulier

Het frontend heeft één onderdeel om een organisatie te kiezen:

```tsx
import { OrganisationPicker } from '@/features/organisations';

<OrganisationPicker
  label="Opdrachtgever"
  value={clientOrganisationId}
  onChange={(organisation) => setClientOrganisationId(organisation?.id ?? null)}
/>
```

Je typt een naam of afkorting en kiest uit de treffers. Staat de organisatie er niet tussen, dan is de laatste keuze in de lijst "Staat er niet tussen? Voeg een organisatie toe". Die opent een klein formulier met een naam en, voor een eenheid, de organisatie waar ze onder valt. Zet geen los tekstveld voor een nieuwe organisatie naast de kiezer: toevoegen loopt via de kiezer.

## Wat je over de gegevens moet weten

- Ongeveer een kwart van de organisaties in het register heeft een TOOI-URI. Onderdelen van organisaties hebben er bijna nooit een. Grip en Wies herkennen die aan het nummer van het register.
- Het register kent van een organisatie soms alleen het hoogste niveau. Een directie die er niet in staat voeg je zelf toe onder de organisatie waar ze bij hoort.
- Opgeheven organisaties staan niet in de lijst. Een opdracht voor een ministerie dat intussen is opgeheven kies je dus niet uit het register.
- De namen zijn die van het register. Een ministerie heet daar bijvoorbeeld "Financiën"; grip toont "Ministerie van Financiën" en vindt het op beide.
