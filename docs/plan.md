# Plan

## Eerste mijlpaal

De mijlpaal is geen demo. Ze is gehaald wanneer dit allemaal waar is:

- De DigiGilde-instantie is in dagelijks gebruik met de echte opdrachten, mensen en bedragen. Het Grist-document staat op alleen-lezen.
- Een opdrachtgever buiten de eigen lijn (NLDD of EZK) heeft in een eigen instantie minstens een echte offerte ontvangen en getekend.
- Medewerkers loggen in met SSO Rijk.
- Heeft de opdrachtgever een corpus, dan opent een context-URI op die opdracht in de Bouwmeester van dat corpus. Zonder corpus is de context leeg; dat mag.

Niet vereist voor deze mijlpaal: een tweede organisatie op eigen infrastructuur, productie-FSC met PKIoverheid, urenregistratie.

## Twee sporen

De sporen lopen tegelijk. Spoor A vervangt Grist, spoor B bouwt de federatie. Wat ze van elkaar mogen weten staat in [architectuur.md](architectuur.md) onder "De naad tussen de twee sporen".

### Spoor A: Grist vervangen

Elke stap levert iets bruikbaars op.

1. **Skelet.** Repo naar het voorbeeld van Bouwmeester: applicatie, configuratie, OIDC-login, sessies, CSRF, justfile, compose, CI, uitrol naar ZAD.
2. **Kern.** Schema en migraties; de rekenmodule met unittests voor R1 t/m R14.
3. **Import.** Herhaalbare import van het Grist-document, omzetting van vrije tekst als lijst ter bevestiging, aansluitrapport tot op de euro.
4. **Toegang.** De beslisfunctie, antwoordschema's per gegevensklasse, lektests, SSO Rijk.
5. **Schermen.** Stand van zaken, opdrachten met begrotingseditor, inzet, kosten en facturen, tarieven, team en KPI.
6. **Offerte.** Genereren uit de begroting, momentopname, pdf; akkoord via een geuploade pdf.
7. **Maandafsluiting en factuurgegevens.** Werkelijke inzet vaststellen, export per periode; inhuur met kostprijs en marge.
8. **Vacatures en rapportage.** Open rol, werving volgen met de stappen van de vacatureprocedure, het aanvraagformulier vacature automatisch vullen, een concept van de vacaturetekst opstellen met VLAM; sturingsoverzicht en jaarverantwoording.
9. **Overstap.** Laatste import, Grist op alleen-lezen.

### Spoor B: federatie

1. **Proef.** De vragen aan het ZAD-team beantwoord krijgen (zie risico's). Twee FSC-deelnemers en een directory in een eigen groep, met een echodienst.
2. **Contract.** Een eigen repo met OpenAPI 3.1 en JSON Schema voor `grip-opdrachtverkeer` v1 en `corpus-context` v1, de woordenlijst van node- en edge-typen, een JSON-LD-context, Spectral-controle en een gepubliceerde leespagina.
3. **Federatiemodule.** Peerregister, outbox en inbox met worker, aanroep via de outway, inkomende routes die alleen de inway vertrouwen.
4. **Aanvraag, offerte en akkoord** tussen twee instanties, met tekenen in de eigen grip en de tekenlink.
5. **Bouwmeester.** Zie hieronder. Getest met twee Bouwmeester-instanties.
6. **Inzage en eindrapport.** Voortgang, en op verzoek uitputting en factuurgegevens.
7. **Moeder en dochter.** Doorgifte aan ODI; doorzetten in de keten.
8. **Wies en federatieve vacatures.**

## Rapportages

| Rapportage | Voor wie | Stap |
|---|---|---|
| Per opdracht: wat is afgesproken, geleverd en besteed | De opdrachtgever | B6 |
| Opdrachten bij een node, met fase en besteding | Wie in Bouwmeester naar een doel of instrument kijkt | B5 |
| Sturing: bezetting, offertes in de pijplijn, kostendekking | De eigen organisatie | A8 |
| Jaarverantwoording per begrotingsjaar | De financiële verantwoording | A8 |

## Wijzigingen buiten grip

### Bouwmeester

- Een stabiele URI per node, op een duurzaam domein per corpus, in de API en als adres dat naar de node leidt.
- De dienst `corpus-context` volgens het contract: node, keten en zoeken, met peildatum. Alleen bereikbaar via de inway en geautoriseerd op peer-id. Met contracttests.
- Deelname aan de FSC-groep.
- Opdrachten bij een node ophalen uit grip en alleen-lezen tonen.
- Na de eerste mijlpaal: de eigen opdrachtentabel en de synchronisatie met Fortes Change Cloud overdragen aan grip.

Bouwmeester heeft nu geen machine-toegang voor andere systemen behalve een sleutel per agent, geen uitgaande gebeurtenissen en geen stabiele URI per node. De beschrijving van de API staat in productie uit.

### Wies

- Een bron `grip` naast de bestaande bronnen.
- Een leeskoppelvlak voor collega's, beveiligd met een sleutel.
- Een synchronisatietaak die opdrachten, rollen en plaatsingen uit grip overneemt.

Wies heeft nu geen machine-koppelvlak; alles loopt via de browser.

## Verificatie

- Unittests voor R1 t/m R14 met de rekenvoorbeelden, daarna met gevallen uit de echte Grist-export.
- Het aansluitrapport: elk totaal gelijk aan Grist, tot op de euro.
- Lektests per gegevensklasse en per relatie.
- Lokaal twee instanties plus FSC-componenten in compose. Een geautomatiseerde test doorloopt aanvraag, offerte, akkoord en inzage.
- Contracttests tegen de contractrepo, in grip en in Bouwmeester.
- Een opdracht met nodes uit twee Bouwmeester-instanties toont beide ketens.
- Schermtests worden met Playwright opgenomen door een persoon.

## Risico's en open punten

**ZAD en FSC.** FSC op ZAD lijkt haalbaar: het platform kent een TLS-modus waarbij de pod zelf het verkeer afhandelt, een voorziening om certificaten te koppelen en een manier om poorten tussen projecten open te zetten. Niet bevestigd is of die drie op productie aanstaan. Verder na te vragen: een hostnaam per component, de limiet op componenten en databases per project, waar de directory draait, en of het register van de FSC-images is toegestaan. Zolang dit open staat, staat spoor B stil vanaf stap 1.

**Omvang van FSC.** Een deelnemer draait manager, inway, outway, controller en transactielog, met tot drie databases. Met een opdrachtgever, DigiGilde, ODI en Bouwmeester gaat het om ruim twintig componenten. Elke extra Bouwmeester-instantie is weer een deelnemer.

**Juridische waarde van het akkoord.** Tekenen in grip is een gewone elektronische handtekening. Mandaat en bewijskracht moeten met juristen zijn afgestemd voor de eerste echte offerte.

**Welke opdrachtgever.** NLDD of EZK is niet gekozen. Onbekend is ook of die opdrachtgever een corpus in Bouwmeester heeft. Zonder corpus is de context leeg; dat mag, maar dan toont de mijlpaal geen context-URI.

**Financieel systeem.** Het formaat van de export van factuurgegevens is onbekend.

**Toegang tot Grist.** De import heeft een API-sleutel en het document-id nodig.

**Vragen aan de Grist-formules.** Hoe gedeeltelijke maanden geprijsd worden, wat de grondslag van het dekkingspercentage is, en of begrote bedragen op personeelsregels berekend of ingevoerd zijn. Zie [domein.md](domein.md).

**Woordenlijst van typen.** Bouwmeester kent vrije node-typen en zelfgemaakte edge-typen. Welke tot de gedeelde kern horen moet met de beheerders van het corpus worden vastgesteld.

**Duurzame domeinen.** Per corpus is een vast domein nodig dat een verhuizing van hosting overleeft. Wie die domeinen uitgeeft en beheert is niet belegd.

**Instantie zonder eigen registratie.** DigiGilde staat voor zover bekend niet zelf in organisaties.overheid.nl. Hoe het eigen kenmerk van zo'n instantie eruitziet en hoe het FSC-peer-id zich verhoudt tot een OIN is niet uitgewerkt.

**Persoonskoppeling met Wies.** De koppeling gaat op e-mailadres. Na te gaan: of beide systemen in dezelfde Keycloak-realm zitten.
