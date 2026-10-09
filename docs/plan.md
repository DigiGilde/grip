# Plan

## Eerste mijlpaal

De mijlpaal is geen demo. Ze is gehaald wanneer dit allemaal waar is:

- De DigiGilde-instantie is in dagelijks gebruik met de echte opdrachten, mensen en bedragen. Het Grist-document staat op alleen-lezen.
- Een opdrachtgever buiten de eigen lijn (NLDD of EZK) heeft in een eigen instantie minstens een echte offerte ontvangen en getekend.
- Medewerkers loggen in met SSO Rijk.
- Heeft de opdrachtgever een corpus, dan opent een context-URI op die opdracht in de Bouwmeester van dat corpus. Zonder corpus is de context leeg; dat mag.

Niet vereist voor deze mijlpaal: een tweede organisatie op eigen infrastructuur, productie-FSC met PKIoverheid, urenregistratie.

## Waar het staat (9 oktober 2026)

De mijlpaal is niet gehaald. Grip is gebouwd en draait lokaal met fictieve voorbeeldgegevens; het is niet in gebruik, staat niet op het hostingplatform, en er is nooit via het echte SSO Rijk ingelogd. Wat lokaal is aangetoond staat in [lokaal.md](lokaal.md); wat het zelf gebruiken van grip opleverde staat in [rondgang.md](rondgang.md); wat op een beslissing of antwoord wacht staat in [openstaand.md](openstaand.md).

| Eis van de mijlpaal | Stand |
|---|---|
| DigiGilde in dagelijks gebruik, Grist op alleen-lezen | Niet begonnen. De import wacht op het document |
| Een opdrachtgever buiten de eigen lijn heeft een echte offerte ontvangen en getekend | Niet begonnen. Tussen twee lokale instanties is het verkeer aangetoond |
| Medewerkers loggen in met SSO Rijk | Voorbereid, nooit uitgevoerd. Er ligt een diagnose klaar voor de eerste echte aanmelding ([sso-rijk.md](sso-rijk.md)) |
| Een context-URI opent in de Bouwmeester van het corpus | Lokaal aangetoond tegen een lokale Bouwmeester; de wijzigingen in Bouwmeester staan op lokale branches en zijn niet voorgelegd |

## Twee sporen

De sporen lopen tegelijk. Spoor A vervangt Grist, spoor B bouwt de federatie. Wat ze van elkaar mogen weten staat in [architectuur.md](architectuur.md) onder "De naad tussen de twee sporen".

### Spoor A: Grist vervangen

| Stap | Stand | Toelichting |
|---|---|---|
| 1. Skelet | Deels | Applicatie, configuratie, aanmelden, sessies, CSRF, justfile, compose en CI staan. Uitrol naar het hostingplatform is niet gedaan |
| 2. Kern | Klaar | Schema met migraties; de rekenmodule met tests voor R1 t/m R14. Tarieven gelden sindsdien per periode en de prijs volgt de dag (ADR 0027) |
| 3. Import | Deels | Gebouwd en getest op een nagemaakt document. Het echte document is niet gelezen; de koppeling van kolommen en de formules zijn daardoor onbevestigd ([import-grist.md](import-grist.md)) |
| 4. Toegang | Deels | De beslisfunctie, antwoorden per gegevensklasse, lektests en een meting die elke pagina als elke soort lezer opent. SSO Rijk zelf is niet beproefd |
| 5. Schermen | Klaar | Alle genoemde schermen, en meer: zie "Wat het plan niet voorzag" |
| 6. Offerte | Klaar | Uit de begroting, als brief met tekst, met kenmerk, bewaard pdf-bestand, interne goedkeuring, aanbieden per kanaal en een bewijs bij het akkoord |
| 7. Maandafsluiting en factuurgegevens | Klaar | Vaststellen per maand, aanleveren per factuurperiode als factuurverzoek, de factuur vastleggen, naverrekeningen; inhuur met kostprijs en marge. Het formaat dat de financiële administratie wil is onbekend |
| 8. Vacatures en rapportage | Deels | Open rol, de stappen van de procedure, het aanvraagformulier van de organisatie gevuld en bewaard, standaardteksten en teksten als werk; sturing en jaarverantwoording. VLAM is nooit aangeroepen; lokaal staat een ontwikkelmodel in zijn plaats |
| 9. Overstap | Niet begonnen | |

### Spoor B: federatie

| Stap | Stand | Toelichting |
|---|---|---|
| 1. Proef | Deels | Lokaal draait een eigen FSC-groep met twee grip-instanties en een Bouwmeester, en een echt bericht in beide richtingen. De vragen aan het platformteam zijn niet beantwoord |
| 2. Contract | Klaar | De contractrepo met `grip-opdrachtverkeer` en `corpus-context` 1.0.0, in het Nederlands (ADR 0019). Twee aanvullingen staan lokaal klaar en zijn niet gepubliceerd; grip heeft de laatste nog niet overgenomen |
| 3. Federatiemodule | Klaar | Peerregister, outbox en inbox met worker, aanroep via de outway, inkomende routes op een eigen proces |
| 4. Aanvraag, offerte en akkoord | Deels | Gebouwd en getest met twee instanties in de tests; lokaal is een bericht over FSC aangetoond. De hele gang van aanvraag tot akkoord is niet in een browser tussen twee gekoppelde instanties doorlopen |
| 5. Bouwmeester | Deels | `corpus-context` en "opdrachten bij een node" staan op lokale branches van Bouwmeester, niet voorgelegd. Een opdracht met nodes uit twee corpora is niet aangetoond |
| 6. Inzage en eindrapport | Deels | De routes voor voortgang, uitputting, factuurgegevens en het eindrapport bestaan met tests; niet tussen twee echte instanties gebruikt |
| 7. Moeder en dochter | Deels | De routes voor doorgifte bestaan met tests; niet gebruikt. Of bezetting met namen of als aantallen naar de moeder gaat is een instelling, standaard aantallen |
| 8. Wies en federatieve vacatures | Deels | Wies lokaal in beide richtingen, op een lokale branch van Wies, niet voorgelegd. Een vacature gaat naar een andere instantie; ontvangen vacatures hebben nog geen scherm |

### Wat het plan niet voorzag

Tijdens het bouwen is meer ontstaan dan het plan noemde, meestal omdat het gebruik erom vroeg.

| Onderdeel | Wat het is | Meer |
|---|---|---|
| Taken en werkstromen | Feiten sluiten taken; elke opdracht en vacature toont waar ze staat, wie aan zet is en de ene volgende stap | [taken.md](taken.md), [werkstromen.md](werkstromen.md) |
| Stroom van gebeurtenissen | Elke wijziging is een gebeurtenis; geschiedenis, activiteit en "wat is er gebeurd" lezen eruit | [gebeurtenissen.md](gebeurtenissen.md) |
| Bewijs van een akkoord | Opnieuw aanmelden bij het besluit, gebonden aan het document, buiten grip te controleren | [bewijs.md](bewijs.md) |
| De offerte als brief | Tekst per onderdeel, standaardteksten en afzender per organisatie | [offerte-document.md](offerte-document.md) |
| Potentiële opdracht | Een opdracht bestaat voor het akkoord; een afgewezen offerte sluit haar niet | ADR 0045 |
| Aanleveren per factuurperiode | Een factuurverzoek per periode, en naverrekeningen als opgeslagen feit | ADR 0039, ADR 0047 |
| Tarieven per periode | Een kaart geldt van datum tot datum; een promotie midden in een maand prijst goed | ADR 0027 |
| Rollen, organisaties, functiegebouw | Lijsten uit Wies, uit het openbare register en uit het Functiegebouw Rijk | [rollen.md](rollen.md), [organisaties.md](organisaties.md) |
| Vacatureteksten | Standaardteksten per rol, de tekst als werk met een beoordeling | [vacatureteksten.md](vacatureteksten.md) |
| Mail, meldingen, passkeys, installeerbaar | De tekenlink per mail; meldingen voor taken; passkeys; grip als applicatie | ADR 0031, ADR 0037, ADR 0040 |
| Scheiding van taken en een klok | Wie het werk maakte beslist er niet over; een datum is de dag van de instantie | ADR 0048, ADR 0046 |
| Ontwerp | Bouwstenen, zeven plekken in de balk, vaste woorden, een merk, en metingen voor tussenruimte en toegang | [ontwerp.md](ontwerp.md), [merk.md](merk.md) |
| Lokaal ontwikkelmodel | Teksten laten opstellen zonder VLAM, alleen in de ontwikkelmodus | ADR 0035 |

## Rapportages

| Rapportage | Voor wie | Stap |
|---|---|---|
| Per opdracht: wat is afgesproken, geleverd en besteed | De opdrachtgever | B6 |
| Opdrachten bij een node, met fase en besteding | Wie in Bouwmeester naar een doel of instrument kijkt | B5 |
| Sturing: bezetting, potentiële opdrachten, kostendekking | De eigen organisatie | A8 |
| Jaarverantwoording per begrotingsjaar | De financiële verantwoording | A8 |

## Wijzigingen buiten grip

### Bouwmeester

- Een stabiele URI per node, op een duurzaam domein per corpus, in de API en als adres dat naar de node leidt.
- De dienst `corpus-context` volgens het contract: node, keten en zoeken, met peildatum. Alleen bereikbaar via de inway en geautoriseerd op peer-id. Met contracttests.
- Deelname aan de FSC-groep.
- Opdrachten bij een node ophalen uit grip en alleen-lezen tonen.
- Na de eerste mijlpaal: de eigen opdrachtentabel en de synchronisatie met Fortes Change Cloud overdragen aan grip.

Bouwmeester heeft nu geen machine-toegang voor andere systemen behalve een sleutel per agent, geen uitgaande gebeurtenissen en geen stabiele URI per node. De beschrijving van de API staat in productie uit.

Stand: de dienst `corpus-context` en het tonen van opdrachten bij een node zijn gebouwd op lokale branches van Bouwmeester en lokaal beproefd. Ze zijn niet voorgelegd. Een bekende fout daar: het adres van een grip-instantie wordt alleen met https aanvaard.

### Wies

- Een bron `grip` naast de bestaande bronnen.
- Een leeskoppelvlak voor collega's, beveiligd met een sleutel.
- Een synchronisatietaak die opdrachten, rollen en plaatsingen uit grip overneemt.

Wies heeft nu geen machine-koppelvlak; alles loopt via de browser.

Stand: de drie wijzigingen zijn gebouwd op een lokale branch van Wies en lokaal beproefd. Ze zijn niet voorgelegd.

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

**Juridische waarde van het akkoord.** Bij een akkoord hoort nu een bewijs dat buiten grip te controleren is. Welk niveau van elektronische handtekening dat is, bepaalt grip niet. Mandaat en bewijskracht moeten met juristen zijn afgestemd voor de eerste echte offerte; de vragen staan in [bewijs.md](bewijs.md).

**Welke opdrachtgever.** NLDD of EZK is niet gekozen. Onbekend is ook of die opdrachtgever een corpus in Bouwmeester heeft. Zonder corpus is de context leeg; dat mag, maar dan toont de mijlpaal geen context-URI.

**Financieel systeem.** Grip levert per factuurperiode een factuurverzoek als pdf en een bestand voor een systeem. Welk formaat de financiële administratie wil, en of onderdelen van het Rijk onderling met een factuur of met een interne doorbelasting verrekenen, is onbekend. De vragen staan in ADR 0039.

**Toegang tot Grist.** De import heeft een API-sleutel en het document-id nodig.

**Vragen aan de Grist-formules.** Hoe gedeeltelijke maanden geprijsd worden, wat de grondslag van het dekkingspercentage is, en of begrote bedragen op personeelsregels berekend of ingevoerd zijn. Zie [domein.md](domein.md).

**Woordenlijst van typen.** Bouwmeester kent vrije node-typen en zelfgemaakte edge-typen. Welke tot de gedeelde kern horen moet met de beheerders van het corpus worden vastgesteld.

**Duurzame domeinen.** Per corpus is een vast domein nodig dat een verhuizing van hosting overleeft. Wie die domeinen uitgeeft en beheert is niet belegd.

**Instantie zonder eigen registratie.** DigiGilde staat voor zover bekend niet zelf in organisaties.overheid.nl. Hoe het eigen kenmerk van zo'n instantie eruitziet en hoe het FSC-peer-id zich verhoudt tot een OIN is niet uitgewerkt.

**Persoonskoppeling met Wies.** De koppeling gaat op e-mailadres. Na te gaan: of beide systemen in dezelfde Keycloak-realm zitten.

**Echte aanmelding.** De aanmelding is aangetoond tegen een lokale Keycloak. Tegen SSO Rijk is ze nooit uitgevoerd; daarvoor is het geheim van de ontwikkelclient nodig. Of opnieuw aanmelden bij een besluit doorwerkt tot bij SSO Rijk is niet bekend. Zie [sso-rijk.md](sso-rijk.md).

**Getest door de bouwers, niet door gebruikers.** De schermen zijn in een echte browser doorlopen en gemeten, maar niemand die het werk doet heeft grip gebruikt. Hoe vaak iemand een pagina nodig heeft is afgeleid uit het domein, niet gemeten ([navigatie-evaluatie.md](navigatie-evaluatie.md)).
