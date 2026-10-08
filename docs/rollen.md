# Rollen

Een personeelsregel op een begroting heeft een rol: developer, product owner, adviseur. Die rol komt uit een vaste lijst, de rollencatalogus. Zo heet dezelfde rol overal hetzelfde en is te tellen hoeveel er van een rol is begroot, ingezet en gezocht.

De catalogus is iets anders dan de functies van een persoon in de instantie (beheerder, planner) en iets anders dan het Functiegebouw Rijk met functiegroepen en schalen.

## Waar de lijst vandaan komt

Elke instantie heeft een catalogus, ook een zonder Wies. Is de koppeling met Wies ingesteld, dan volgt de catalogus de rollen die Wies kent (in Wies heten ze vaardigheden). Grip en Wies gebruiken dan dezelfde woorden. Zonder koppeling houdt de beheerder de lijst met de hand bij.

| Herkomst | Betekenis |
|---|---|
| Wies | Overgenomen uit Wies en daaraan gekoppeld. Een andere naam in Wies wordt hier ook de naam |
| Zelf toegevoegd | Door de beheerder, of ter plekke door wie een begroting invult |

Ophalen uit Wies kan op de pagina Beheer onder Rollen, of met `just sync-roles`. Wat er dan gebeurt:

- Een rol die Wies kent en grip niet, komt erbij.
- Een zelf toegevoegde rol met dezelfde naam wordt aan de rol in Wies gekoppeld en krijgt de schrijfwijze van Wies.
- Een rol die in Wies is hernoemd, wordt hier hernoemd, ook op de begrotingsregels.
- Een rol die uit Wies is verdwenen en nog op een begrotingsregel staat of bij een persoon hoort, wordt uitgeschakeld en blijft staan. Een rol die nergens in gebruik is, verdwijnt.
- Heeft een hernoemde rol een naam die een andere rol al heeft, dan blijft ze zoals ze was. De beheerder voegt de twee samen.

Geeft Wies niets terug of is Wies onbereikbaar, dan verandert er niets. Elke poging wordt vastgelegd met de uitkomst.

## Rol en omschrijving op een begrotingsregel

Een personeelsregel heeft een rol, een omschrijving, of allebei.

- De **rol** kies je uit de catalogus.
- De **omschrijving** is vrije tekst voor wat deze regel onderscheidt, zoals "#2, vanaf Q2". Met een rol erbij mag ze leeg blijven.
- De **naam** van de regel is de rol plus de omschrijving: "Developer: #2, vanaf Q2". Noemt de omschrijving de rol zelf al, dan is de naam de omschrijving. Regels van voor de catalogus houden daardoor hun woorden.

De API geeft de naam als `description`, de vrije tekst als `detail` en de rol als `role`. Wie een regel aanmaakt of wijzigt stuurt de naam van de rol in `role`. Grip zoekt de rol erbij zonder op hoofdletters of spaties te letten.

De naam van de rol staat ook op de regel zelf. De database houdt die gelijk aan de catalogus: hernoemen in de catalogus hernoemt elke regel, en een naam die de catalogus niet kent is niet op te slaan.

## Een rol die er niet tussen staat

Wie een begroting invult en een rol mist, kan die ter plekke toevoegen. Een begroting ophouden om een ontbrekend woord is erger dan een dubbele rol die later is samen te voegen. Zo'n rol is zelf toegevoegd en staat bij de beheerder als "te beoordelen".

Dat mag: de beheerder, de planner, wie een opdracht mag aanmaken en wie eigenaar of manager van een opdracht is. Vraagt iemand om een naam die al bestaat, dan krijgt die de bestaande rol.

Ook een rol die via een andere weg binnenkomt, zoals de import uit Grist, wordt een rol in de catalogus met het merk "te beoordelen". Er gaat geen waarde verloren.

## Beheren

Op de pagina Beheer onder Rollen staat de lijst met per rol de herkomst, het aantal begrotingsregels en of de rol te kiezen is. De beheerder kan:

- **Hernoemen.** De naam verandert op elke begrotingsregel. Een offerte die al is uitgegeven houdt de woorden waarmee ze is uitgegeven.
- **Uitschakelen.** De rol blijft op de regels die haar gebruiken en is niet meer te kiezen.
- **Samenvoegen.** De begrotingsregels en de personen van de ene rol krijgen de andere, en de eerste verdwijnt. Was alleen de verdwenen rol aan Wies gekoppeld, dan neemt de overgebleven rol die koppeling over. Twee rollen die allebei uit Wies komen voeg je in Wies samen.
- **Beoordelen.** Een rol bewaren haalt het merk "te beoordelen" weg.

Elke wijziging laat een regel achter in de auditlog. Bij samenvoegen staat daar hoeveel regels zijn omgezet.

## De eerste keer

Bij de overgang naar de catalogus zijn de bestaande rolteksten overgenomen. Teksten die alleen in hoofdletters of spaties verschilden zijn één rol geworden, in de schrijfwijze die het meest voorkwam. Elke overgenomen rol staat als te beoordelen, en in de auditlog staat per rol uit welke schrijfwijzen ze is ontstaan en hoeveel regels het waren. "Developer" en "Ontwikkelaar" zijn dus nog twee rollen; samenvoegen is aan de beheerder.

## De rollen van een persoon

Een persoon kan een of meer rollen uit de catalogus hebben. Daarmee kan grip een rol voorstellen als je iemand kiest, bijvoorbeeld als beoogde persoon op een begrotingsregel.

| Herkomst | Betekenis |
|---|---|
| Wies | De persoon heeft deze rol in Wies |
| Zelf toegevoegd | De beheerder heeft de rol bij de persoon gezet |

Wat Wies zegt, overschrijft nooit iets vanzelf. Grip vergelijkt de rollen van een collega in Wies met wat de persoon hier heeft en doet voorstellen:

- Heeft de collega in Wies een rol die de persoon hier niet heeft, dan stelt grip voor die toe te voegen.
- Is een rol die uit Wies kwam daar vervallen, dan stelt grip voor die weg te halen.
- Een rol die met de hand is gezet wordt nooit voorgesteld om weg te halen, en niet opnieuw voorgesteld als Wies haar ook kent.

De beheerder bevestigt de voorstellen. Grip past alleen toe wat Wies op dat moment nog onderbouwt.

De rollen van een persoon zijn bemensing (klasse C in [toegang.md](toegang.md)): te zien voor wie de bemensing van die persoon mag zien, te wijzigen door de beheerder.

## API

| Route | Wat | Wie |
|---|---|---|
| `GET /api/catalogue-roles?q=&include_inactive=` | De rollen, met per rol het gebruik, en of de lezer mag toevoegen en beheren | Iedereen |
| `POST /api/catalogue-roles` | Rol toevoegen. Een bestaande naam geeft de bestaande rol terug | Beheerder, en wie een begroting invult (dan te beoordelen) |
| `GET /api/catalogue-roles/{id}` | Een rol | Iedereen |
| `PATCH /api/catalogue-roles/{id}` | Hernoemen, toelichten, in- of uitschakelen, beoordeeld | Beheerder |
| `POST /api/catalogue-roles/{id}/merge` | Samenvoegen met `into_id` | Beheerder |
| `GET` en `POST /api/catalogue-roles/sync` | Stand en uitvoeren van het ophalen uit Wies | Beheerder |
| `GET /api/people/{id}/roles` | De rollen van een persoon met herkomst | Wie de bemensing van de persoon mag zien |
| `PUT /api/people/{id}/roles` | De rollen van een persoon zetten (`role_ids`) | Beheerder |
| `GET` en `POST /api/integrations/wies/role-proposals` | Voorstellen uit Wies voor rollen van personen, en bevestigen | Beheerder |

In code leest `roles_of_person(db, person_id)` in `grip.services.person_roles` de rollen van een persoon.

## In een formulier

```tsx
import { RolePicker } from '@/features/roles';

<RolePicker
  label="Rol"
  value={form.role}
  onChange={(role) => set({ role: role?.name ?? null })}
/>
```

Je typt en kiest. Heeft geen rol de getypte naam en mag je toevoegen, dan is de laatste keuze "Staat er niet tussen? Voeg ... toe als rol". Zet geen vrij tekstveld voor een rol naast de kiezer.
