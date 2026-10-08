# Meldingen

Wat grip meldt en waarom zo staat in [ADR 0040](adr/0040-meldingen-op-het-eigen-apparaat.md). Deze pagina is voor wie het instelt, uitprobeert of erop bouwt.

## Wat het platform moet leveren

1. **Een geheim:** `PUSH_VAPID_PRIVATE_KEY`, het sleutelpaar van de instantie. Maak het een keer met `just push-key` en bewaar het als geheim van het project. Verandert het, dan vervallen alle aanmeldingen.
2. **Uitgaand https vanaf de worker** naar de diensten van de browserleveranciers. Welke dienst het is bepaalt de browser van de persoon, niet grip:

| Browser | Hosts |
|---|---|
| Chrome, Edge, en de meeste Android-browsers | `fcm.googleapis.com` |
| Firefox | `updates.push.services.mozilla.com` |
| Safari (macOS, iOS, iPadOS) | `*.push.apple.com` |
| Edge op Windows, deels | `*.notify.windows.com` |

3. **De worker** (`python -m grip.worker`) moet draaien.

De applicatie zelf moet over https bereikbaar zijn; dat is ze.

### Vragen voor het platformteam

- Mag de worker uitgaand https naar deze hosts? Staat er een lijst van toegestane bestemmingen, en hoe komen deze erop?
- Is er een uitgaande proxy, en moet de worker die gebruiken?
- Mag het sleutelpaar als geheim van het project worden opgeslagen, en blijft het gelijk bij een herstart en bij een nieuwe uitrol?
- Het gaat naar diensten van Google, Mozilla, Apple en Microsoft. De inhoud is versleuteld en bevat geen persoonsgegevens, maar die diensten zien wel dat deze instantie een bericht stuurt naar een bepaald apparaat, en wanneer. Is dat akkoord?

## Instellingen

| Instelling | Standaard | Betekenis |
|---|---|---|
| `PUSH_VAPID_PRIVATE_KEY` | leeg | Het sleutelpaar. Leeg: geen meldingen |
| `PUSH_VAPID_SUBJECT` | `FRONTEND_URL` | Waar een dienst de afzender kan bereiken: `mailto:` of `https:` |
| `PUSH_DAILY_CAP` | 6 | Hooguit zoveel meldingen per persoon per dag |
| `PUSH_BATCH_SECONDS` | 90 | Taken die binnen deze tijd na elkaar openen worden een melding |
| `PUSH_TTL_SECONDS` | 43200 | Hoe lang een dienst een melding bewaart voor een apparaat dat uit staat |
| `PUSH_SCAN_INTERVAL_SECONDS` | 60 | Hoe vaak de worker kijkt |
| `PUSH_TIMEZONE` | `Europe/Amsterdam` | De tijdzone van stille uren en van "vandaag" |

## Wat er over de lijn gaat

Een bericht aan een apparaat is, na ontsleutelen:

```json
{"v": 1, "k": "tasks", "n": 3, "p": "/taken", "i": "<id>", "b": 3}
```

`k` is de soort, `n` het aantal, `p` het pad om te openen, `i` een id zonder betekenis, `b` het getal voor het pictogram. Meer velden zijn er niet, en de service worker toont alleen tekst uit zijn eigen lijst (`WORDS` in `frontend/public/sw.js`).

| Soort | Wat het apparaat toont |
|---|---|
| `tasks` | "Er wacht een taak op je" of "3 taken wachten op je" |
| `overdue` | "Een taak is over de datum" of "2 taken zijn over de datum" |
| `quote_accepted` | "Een offerte is getekend" |
| `quote_rejected` | "Een offerte is afgewezen" |
| `approval_given` | "Een offerte is intern goedgekeurd" |
| `approval_sent_back` | "Een offerte is teruggestuurd naar jou" |
| `test` | "Meldingen van grip werken" |

Een nieuwe soort vraagt een regel in `models/push.py`, in `scan.py` en in `WORDS`. De test van de service worker faalt als een soort geen tekst heeft.

## Routes

Alles gaat over de persoon die vraagt.

| Route | Wat |
|---|---|
| `GET /api/notifications` | Of het hier kan, de publieke sleutel, de voorkeur en de eigen apparaten |
| `PUT /api/notifications/preference` | De voorkeur, in delen |
| `POST /api/notifications/devices` | Deze browser aanmelden |
| `DELETE /api/notifications/devices/{id}` | Een eigen apparaat intrekken |
| `POST /api/notifications/test` | Een proefmelding naar de eigen apparaten |

Het adres van een apparaat komt nooit terug in een antwoord en staat niet in de stroom van gebeurtenissen.

## Het aanbod op een pagina

`PushOffer` uit `frontend/src/features/notifications/PushOffer.tsx` toont een zin en de knop zolang meldingen hier kunnen en nog niet aanstaan, en anders niets. Het hoort op de pagina met taken.

## Lokaal uitproberen

```
just push-key                      # een keer; zet de regel in backend/.env
just preview                       # de server
cd backend && uv run python -m grip.worker
cd frontend && npm run build && npx vite preview --port 5190
```

De service worker draait niet onder `npm run dev`; daarom de build. Open de pagina Meldingen, zet ze aan en kies "Stuur een proefmelding". In een gewone Chrome of Firefox op `localhost` werkt dat met de echte dienst van de browser.

## Nog niet gebouwd

- **De samenvatting per mail.** De voorkeur bestaat (`mail_summary`); het versturen niet. Het is een lus naast die voor de tekenlink, een keer per werkdag, met dezelfde vraag aan de takenlaag.
- **Een melding intrekken op afstand** als de taak dicht is voordat ze is gezien. Een browser eist dat elke push iets toont; grip ruimt op zodra de persoon grip opent.
- **Meldingen voor een uitgenodigde ondertekenaar.** Een gast heeft geen persoonsrecord en geen taken.
