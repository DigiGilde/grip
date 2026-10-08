# 0035 Lokaal kan een ontwikkelmodel de plaats van VLAM innemen

Status: aanvaard (2026-10-08)

## Context

ADR 0018 koos VLAM voor het opstellen van teksten: het taalmodel dat de overheid zelf beheert. Lokaal heeft niemand een sleutel voor VLAM. Het opstellen van een vacaturetekst of van proza in een offerte was daardoor alleen tegen een nagebootst model te proberen. Of een concept bruikbaar is, zie je zo niet.

## Besluit

De servicelaag voor het taalmodel krijgt een tweede aanbieder, gekozen met `LLM_PROVIDER`: `vlam`, `claude_cli` of `none`. Leeg betekent VLAM als die is ingesteld.

`claude_cli` roept het opdrachtregelprogramma aan dat op de computer van de ontwikkelaar staat, met diens eigen login. Grip bewaart geen sleutel en gebruikt geen SDK. Het programma draait zonder gereedschappen, zonder bewaarde sessie en zonder instellingen van de gebruiker, als los proces dat de server niet blokkeert.

Het is een aanbieder voor ontwikkeling, en de code dwingt dat af:

- De instellingen weigeren `claude_cli` buiten lokale ontwikkeling. De voorwaarde is dezelfde als voor werken zonder login: `DEV_NO_AUTH` aan en geen `PUBLIC_HOST`.
- De aanbieder is niet te kiezen in een beheerscherm.
- Een concept dat zo is gemaakt, draagt dat in zijn herkomst: "Opgesteld met Claude via de lokale ontwikkelomgeving, <model>". Het kan niet doorgaan voor een concept van VLAM.

Alles wat de servicelaag al garandeert blijft gelden: geen namen van medewerkers of kandidaten en niets uit de gegevensklassen D, E en F in een verzoek.

## Gevolgen

- Tekst die naar deze aanbieder gaat, verlaat de eigen modeldienst van de overheid. Daarom alleen lokaal en alleen met verzonnen gegevens. De pagina "Vacatureformulier en taalmodel" zegt dat erbij.
- `just preview` zet de aanbieder aan als het programma is gevonden en er geen VLAM is ingesteld.
- Een concept duurt lokaal rond de twintig seconden. Het scherm zegt dat tijdens het wachten.
- Het publieke koppelvlak van de servicelaag is niet gewijzigd: `get_chat_client`, `is_llm_configured` en de fouten zijn dezelfde.
