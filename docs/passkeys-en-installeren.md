# Passkeys en grip installeren

Wat grip hier doet staat in [ADR 0037](adr/0037-passkeys-en-een-installeerbare-applicatie.md). Deze pagina is voor wie het instelt, uitprobeert of erop bouwt.

## Instellingen

| Instelling | Standaard | Betekenis |
|---|---|---|
| `PASSKEY_RP_ID` | de host uit `FRONTEND_URL` | Het adres waaraan passkeys gebonden zijn |
| `PASSKEY_ORIGIN` | de oorsprong uit `FRONTEND_URL` | De oorsprong die een apparaat moet melden |
| `PASSKEY_RP_NAME` | `INSTANCE_NAME` | De naam die het apparaat toont |
| `PASSKEY_SESSION_TTL_SECONDS` | 43200 | Hoe lang een sessie duurt die met een passkey begon |
| `PASSKEY_LOGIN_MAX_AGE_DAYS` | 30 | Hoeveel dagen na de laatste login bij de identiteitsprovider een passkey alleen kan inloggen. `0` zet inloggen met een passkey uit; bevestigen van een besluit blijft werken |

Het platform hoeft niets te leveren: geen sleutels en geen dienst. Passkeys werken alleen over https, of op `localhost`.

## Routes

| Route | Voor wie | Wat |
|---|---|---|
| `GET /api/passkeys` | de persoon zelf | De eigen passkeys en wat hier kan |
| `POST /api/passkeys/register/options`, `/register/verify` | de persoon zelf, in een sessie van de identiteitsprovider | Een passkey vastleggen |
| `DELETE /api/passkeys/{id}` | de persoon zelf | Intrekken |
| `GET` en `DELETE /api/people/{id}/passkeys[/{id}]` | wie gebruikers beheert | Zien en intrekken |
| `POST /api/auth/passkey/options`, `/verify` | zonder sessie | Inloggen |
| `POST /api/proof/intents/{id}/passkey/options`, `/passkey` | wie het besluit begon | Een besluit bevestigen |
| `POST /api/signing/intents/{id}/passkey/options`, `/passkey` | een persoon van de instantie die via een tekenlink tekent | Hetzelfde |

## Een besluit bevestigen, voor wie een scherm bouwt

Het antwoord op `POST .../intents` heeft een veld `passkey`. Is het `null`, dan gaat de browser meteen naar `authorize_url`. Anders bevat het `options_url` en `verify_url`:

1. `POST options_url` geeft `options_json` voor `navigator.credentials.get`.
2. Het antwoord van het apparaat gaat als `{"credential": "<json>"}` naar `verify_url`.
3. Daarna gaat de browser naar `authorize_url`, ook als stap 1 of 2 mislukte of de persoon het venster sloot.

`leaveForDecision` in `frontend/src/features/quotes/proof.ts` doet dit voor alle schermen.

## Wat de service worker bewaart

Alleen de schil: `index.html` en de bestanden van de build. Nooit iets onder `/api/`. De regels staan bovenaan `frontend/public/sw.js` en worden getest in `frontend/src/pwa/serviceWorker.test.ts` tegen het bestand dat wordt uitgeleverd.

De worker draait niet onder `npm run dev`. Uitproberen kan met een build:

```
cd frontend && npm run build && npx vite preview --port 5190
```

## Lokaal uitproberen

Zonder identiteitsprovider (`DEV_NO_AUTH`) is er geen login, dus ook geen inloggen met een passkey. Vastleggen en een besluit bevestigen werken wel, op `localhost`, met de vingerafdruklezer of pincode van je eigen apparaat. De registratie vermeldt dan dat er geen aanmelding was.

Geautomatiseerd kan het met de virtuele authenticator van Chromium (`WebAuthn.addVirtualAuthenticator` over het DevTools-protocol). De tests in de backend gebruiken een authenticator in software, `backend/tests/software_authenticator.py`.

## Meldingen

Meldingen op het apparaat zijn gebouwd; zie [meldingen.md](meldingen.md). De service worker toont ze en zet het getal op het pictogram.

## Niet gebouwd

- **Een passkey voor een uitgenodigde ondertekenaar.** Een gast heeft geen persoonsrecord om een sleutel aan te hangen, en tekent meestal een keer.
- **Delen naar grip** (share target), zoals Bouwmeester heeft. Grip heeft geen plek waar gedeelde tekst of beelden landen.
- **Een melding dat er een nieuwe versie is.** Een pagina komt altijd van het netwerk, dus opnieuw laden volstaat.
