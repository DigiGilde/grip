# Verder werken op een andere machine

Wat je nodig hebt om het werk aan grip op een andere machine voort te zetten. Stand: 9 oktober 2026.

## Wat al op GitHub staat

De repo `DigiGilde/grip`, branch `golf-5`. Daar staat al het werk aan grip zelf, met de documentatie. `main` loopt achter en wordt bijgewerkt voor de eerste uitrol.

```
git clone git@github.com:DigiGilde/grip.git
cd grip
git checkout golf-5
```

## Wat alleen op de oude machine staat

Deze dingen staan niet op GitHub. Neem de map `~/grip-overdracht` mee (ongeveer 2,5 MB); daar zit alles in.

| Bestand | Wat het is | Terugzetten |
|---|---|---|
| `grip-koppelvlakken-main.bundle` | Twee commits op `main` van de contract-repo, bewust niet gepusht | `git clone git@github.com:DigiGilde/grip-koppelvlakken.git` naast grip, daarna `git pull ~/grip-overdracht/grip-koppelvlakken-main.bundle main` |
| `wies-feat-grip-koppeling.bundle` | De branch `feat/grip-koppeling` van Wies, zeven commits, alleen lokaal | In een checkout van Wies: `git fetch ~/grip-overdracht/wies-feat-grip-koppeling.bundle feat/grip-koppeling:feat/grip-koppeling` |
| `bouwmeester-corpus-context.bundle` | De branches `feat/corpus-context` en `feat/opdrachten-bij-node` van Bouwmeester, alleen lokaal | In een checkout van Bouwmeester: `git fetch ~/grip-overdracht/bouwmeester-corpus-context.bundle 'refs/heads/*:refs/heads/*'` |
| `voorbeelden.tar.gz` | De echte voorbeelddocumenten (formulier, offertes, vacatureteksten). Bevat namen en bedragen; staat bewust buiten de repo | Uitpakken in de map van grip: `tar xzf ~/grip-overdracht/voorbeelden.tar.gz` |
| `grip_preview.sql.gz` | De voorbeelddatabase met wat er met de hand aan is toegevoegd | Zie "De voorbeeldomgeving" hieronder |
| `plan.md` | Het oorspronkelijke, goedgekeurde plan | Naslag |
| `claude-memory/` | Wat de assistent over dit project heeft onthouden | Zie "De assistent" hieronder |

Voor de eerste uitrol en voor gewoon doorwerken aan grip zijn alleen de repo en, voor de koppelvlakken, de eerste bundel nodig. De rest is voor wie aan Wies, Bouwmeester of de voorbeelddocumenten verder wil.

## Wat er op de machine moet staan

- Docker (voor Postgres en de lokale opstelling)
- `uv` (Python), `just`, Node met `npm`
- De systeembibliotheek pango, voor de pdf's: op macOS `brew install pango`
- Google Chrome, voor de hulpmiddelen `just check-spacing` en `just check-access`
- Optioneel de Claude-CLI, als lokaal ontwikkelmodel voor de tekstfuncties

## De voorbeeldomgeving

Met verse voorbeeldgegevens, zoals in de README:

```
just dev
just seed
```

Met de meegenomen database, inclusief wat er met de hand is toegevoegd:

```
docker compose up -d db
docker compose exec -T db psql -U grip -d postgres -c "create database grip_preview"
gunzip -c ~/grip-overdracht/grip_preview.sql.gz | docker compose exec -T db psql -q -U grip grip_preview
just preview
```

`just preview` start de server op poort 8010 met die database; de schermen start je in `frontend` met `npx vite`.

De lokale sleutels en certificaten onder `deploy/local/state` zijn gegenereerd en gaan niet mee. `just local-up` maakt ze opnieuw.

## De assistent

Een nieuwe sessie op de andere machine kent dit gesprek niet. Wat de stand draagt staat in de repo:

- [openstaand.md](openstaand.md): alles wat op een mens wacht
- [rondgang.md](rondgang.md): wat er getest is, wat werkt en wat niet
- [plan.md](plan.md): de stand per stap van het plan
- [uitrol-zad.md](uitrol-zad.md): de stappen voor de eerste uitrol
- [ontwerp.md](ontwerp.md): de ontwerpregels
- de besluiten in `adr/`

Het geheugen van de assistent hoort bij de map waarin de repo staat. Zet de inhoud van `claude-memory/` in de geheugenmap van het project op de nieuwe machine; de assistent zegt in een nieuwe sessie waar die staat. De persoonlijke werkafspraken komen uit de eigen dotfiles en gaan daarmee al mee.

## Wat er nog loopt

Controleer voor het overstappen dat de werkmap schoon is (`git status`) en dat `golf-5` gepusht is. Werk dat nog niet is vastgelegd, bestaat alleen op de oude machine.

## Zo begin je de nieuwe sessie

Geef de assistent op de nieuwe machine dit als eerste bericht:

> Lees docs/overdracht.md, docs/openstaand.md en docs/rondgang.md. We gaan verder met de eerste uitrol naar ZAD volgens docs/uitrol-zad.md.

## Waar het werk staat

Stand bij het overstappen, 9 oktober 2026, branch `golf-5`.

Bij de laatste commit waren de schermtests groen (832), net als de servertests voor toegang, domein, de API en de uitrolbestanden (899), en de migraties liepen op een lege database tot en met de nieuwste. De hele servertest was op die commit nog niet afgerond. Draai haar als eerste:

```
cd backend
uv run pytest -q --deselect tests/federation/test_two_instances.py --deselect tests/api/client/test_two_instances_api.py
uv run pytest -q tests/federation/test_two_instances.py tests/api/client/test_two_instances_api.py
```

De twee bestanden met twee instanties gebruiken vaste databases en draaien daarom apart.

## Wat nog moet gebeuren voor de eerste uitrol

1. De hele servertest groen op de laatste commit.
2. De lokale opstelling met Keycloak nalopen (`just local-up`): inloggen, uitloggen, de sessie na een herstart, twee hostnamen achter een proxy, en de voorbeeldmodus met een echte login. Dit is nog niet gedaan.
3. `golf-5` naar `main` in de grip-repo. Een push naar `main` bouwt de images.
4. Op het platform een project aanmaken, eerst voor een voorbeeldinstantie; de stappen staan in [uitrol-zad.md](uitrol-zad.md).
5. Het project en de sleutel in GitHub zetten. Draai dit zelf, zodat de sleutel nergens in een gesprek komt:

```
gh variable set ZAD_PROJECT_ID --repo DigiGilde/grip --body "<project-id>"
gh secret set ZAD_API_KEY --repo DigiGilde/grip
```

## Wat op een antwoord van een mens wacht

Alles staat in [openstaand.md](openstaand.md). Wat de uitrol of de eerste gebruikers raakt:

- Twee eenmalige commando's op de eigen voorbeelddatabase, nog niet gedraaid: `just fix-internal-judges` (de akkoordgever van de voorbeeldvacatures) en `just fix-role-po` (de losse rol "po" wordt Product owner).
- Het clientgeheim van de ontwikkelclient voor de eerste echte login via SSO Rijk; daarna `just sso-check`.
- Drie beslissingen: of een getekende opdracht een nieuwe tarievenkaart volgt, of een maand mag worden afgesloten terwijl een eerdere open is, en of een kostenpost door een personeelsregel gedekt mag worden.
- Het merk: richting a of b.
