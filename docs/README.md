# Documentatie van grip

Grip legt vast hoe een organisatie binnen de Rijksoverheid een opdracht uitvoert: van de begroting en de offerte tot de inzet van mensen, de maandafsluiting en wat er gefactureerd moet worden. Elke organisatie draait een eigen instantie; instanties wisselen aanvragen, offertes en akkoorden met elkaar uit. Een opdracht verwijst naar de plek in een beleidscorpus waar ze uit voortkomt, zodat zichtbaar blijft waarom het werk gebeurt.

## Hoe de documentatie is opgebouwd

| Soort | Waar | Wat je er vindt |
|---|---|---|
| Het geheel | [architectuur.md](architectuur.md), [domein.md](domein.md), [toegang.md](toegang.md) | Hoe grip in elkaar zit, de begrippen en rekenregels, en wie wat mag |
| De stand | [plan.md](plan.md), [openstaand.md](openstaand.md), [rondgang.md](rondgang.md) | Wat er gebouwd is, wat op iemand wacht, en wat een rondgang door de schermen opleverde |
| Per onderwerp | de overige pagina's in deze map | Een onderwerp per pagina: taken, werkstromen, bewijs, aanmelden, meldingen, teksten |
| Besluiten | [adr/](adr/README.md) | Elk besluit dat anderen bindt, met context, besluit en gevolgen |
| Schermen | [ontwerp.md](ontwerp.md), [merk.md](merk.md), [hierarchie/](hierarchie/), [toegankelijkheid.md](toegankelijkheid.md) | De regels voor een scherm, het merk, de doorloop op visuele hiërarchie met beelden voor en na, en wat er aan toegankelijkheid is getest met het concept van de verklaring |
| Snelheid | [snelheid.md](snelheid.md) | Meten op een database van ware grootte (`just seed-scale`, `just check-speed`), het budget en wat er nog boven zit |

De code is Engels, de schermen en deze documentatie zijn Nederlands. Welke codenaam bij welk woord op het scherm hoort staat in de begrippenlijst van [domein.md](domein.md).

Dezelfde pagina's, de besluiten en het personaboek staan ook opgemaakt en doorzoekbaar in het ontwikkelportaal, met een link naar de instanties van de demo. Hoe je het lokaal draait staat in [lokaal.md](lokaal.md#ontwikkelportaal), de uitrol in [uitrol-zad.md](uitrol-zad.md#ontwikkelportaal).

## Waar begin je

**Je wilt het lokaal draaien**

1. De [README van de repo](../README.md): starten in een paar opdrachten.
2. [lokaal.md](lokaal.md): de omgeving zoals die op het platform draait, met een echte login en met FSC tussen twee instanties.
3. [import-grist.md](import-grist.md): als je de gegevens uit het Grist-document wilt overnemen.

**Je beslist erover**

1. [plan.md](plan.md): wat er staat, wat niet, en wat niet is aangetoond.
2. [openstaand.md](openstaand.md): de beslissingen en vragen die op iemand wachten, per persoon of partij.
3. [rondgang.md](rondgang.md): wat het zelf gebruiken van grip opleverde.
4. [werkstromen.md](werkstromen.md): de praktijkgevallen en hoe grip ze ondersteunt.

**Je bouwt eraan**

1. [CLAUDE.md](../CLAUDE.md) in de repo: de regels, kort.
2. [architectuur.md](architectuur.md) en [domein.md](domein.md).
3. [toegang.md](toegang.md): de beslisfunctie en de gegevensklassen.
4. [taken.md](taken.md) en [werkstromen.md](werkstromen.md): feiten, taken en het verloop van een zaak.
5. [gebeurtenissen.md](gebeurtenissen.md): de stroom waar alles in landt.
6. [ontwerp.md](ontwerp.md): hoe een scherm wordt opgebouwd en wanneer het af is.
7. [adr/](adr/README.md): waarom het zo is.

**Je gaat over beveiliging of privacy**

0. [beveiliging.md](beveiliging.md): wat een doorlichting als aanvaller vond, wat is hersteld, wat open staat en wat de organisatie en het platform zelf moeten regelen.
1. [toegang.md](toegang.md): gegevensklassen, de matrix en hoe ze wordt afgedwongen en getest.
2. [gebeurtenissen.md](gebeurtenissen.md): het logboek, de keten tegen ongemerkt wijzigen, inzage, bewaren en wissen, en de verhouding tot Logboek Dataverwerkingen.
3. [sso-rijk.md](sso-rijk.md): aanmelden, wat grip uit een aanmelding leest en wanneer het weigert.
4. [bewijs.md](bewijs.md): wat een bewijs van een akkoord aantoont en wat niet.
5. [passkeys-en-installeren.md](passkeys-en-installeren.md) en [meldingen.md](meldingen.md): wat op een apparaat wordt bewaard en wat er over de lijn gaat.
6. [offerte-document.md](offerte-document.md) en [vacatureteksten.md](vacatureteksten.md): wat naar een taalmodel gaat en wat nooit.

**Je bent van het platform**

1. [lokaal.md](lokaal.md): de processen van een instantie en wat lokaal is aangetoond.
2. [openstaand.md](openstaand.md), het deel voor het platformteam: FSC, mail, meldingen en de instellingen van de identiteitsprovider.
3. [sso-rijk.md](sso-rijk.md): de verzoeken voor de eigen client van grip.

**Je bent jurist**

1. [bewijs.md](bewijs.md), met onderaan de vragen.
2. [adr/0029](adr/0029-bewijs-van-een-akkoord.md), [adr/0030](adr/0030-het-bestand-van-een-offerte-ligt-vast.md) en [adr/0048](adr/0048-een-stap-overnemen-geeft-geen-recht.md).
3. [toegang.md](toegang.md): welke persoonsgegevens er zijn en wie ze ziet.

**Je bent van de financiële administratie**

1. [adr/0039](adr/0039-afsluiten-per-maand-aanleveren-per-periode.md): afsluiten per maand, aanleveren per factuurperiode, en de vragen aan jullie.
2. [adr/0047](adr/0047-een-naverrekening-is-een-opgeslagen-verschil-per-factuurperiode.md): wat er gebeurt als een prijs achteraf verandert.
3. [domein.md](domein.md), de woorden aangeleverd, gefactureerd, factuurverzoek en naverrekening.

## Alle pagina's

| Pagina | Onderwerp |
|---|---|
| [architectuur.md](architectuur.md) | Domeinen, identiteit, opdrachtverkeer, context uit het corpus, tekenen, en hoe de delen van grip samenhangen |
| [domein.md](domein.md) | Begrippen, datamodel, rekenregels R1 t/m R14, tarieven in de tijd, migratie vanuit Grist |
| [toegang.md](toegang.md) | Rechten, relaties, gegevensklassen, de matrix, scheiding van taken, wat het scherm zegt als iets niet mag |
| [plan.md](plan.md) | De stand per stap van het plan, en wat er buiten het plan is gebouwd |
| [openstaand.md](openstaand.md) | Wat op een beslissing of antwoord wacht, per persoon of partij |
| [rondgang.md](rondgang.md) | Bevindingen uit het zelf doorlopen van grip, en hun stand |
| [ontwerp.md](ontwerp.md) | Wanneer een scherm af is, de bouwstenen, vaste woorden, navigatie, iconen, meten |
| [merk.md](merk.md) | Het productmerk naast de organisatie, naam, zin en toon |
| [navigatie-evaluatie.md](navigatie-evaluatie.md) | Wat in het menu hoort, met bewijs en varianten |
| [hierarchie/](hierarchie/) | De doorloop op visuele hiërarchie, per gebied, met beelden |
| [taken.md](taken.md) | Feiten, taken en het plan; wat een taak vertelt |
| [werkstromen.md](werkstromen.md) | Praktijkgevallen, het verloop van een zaak, stappen en taken, wat nog niet kan |
| [gebeurtenissen.md](gebeurtenissen.md) | De stroom van gebeurtenissen, geschiedenis, "wat is er gebeurd", logboek |
| [bewijs.md](bewijs.md) | Het bewijs van een akkoord en hoe je het controleert |
| [sso-rijk.md](sso-rijk.md) | Aanmelden via het platform en SSO Rijk |
| [passkeys-en-installeren.md](passkeys-en-installeren.md) | Passkeys en grip als installeerbare applicatie |
| [meldingen.md](meldingen.md) | Meldingen op het eigen apparaat |
| [offerte-document.md](offerte-document.md) | De offerte als document en als brief, afzender, standaardteksten |
| [vacatureteksten.md](vacatureteksten.md) | Standaardteksten per rol en de tekst als werk |
| [rollen.md](rollen.md) | De lijst van rollen en waar ze vandaan komt |
| [organisaties.md](organisaties.md) | Het register van overheidsorganisaties |
| [wies.md](wies.md) | De koppeling met Wies |
| [lokaal.md](lokaal.md) | De lokale omgeving en wat ermee is aangetoond |
| [uitrol-zad.md](uitrol-zad.md) | Uitrollen op ZAD: eerst een voorbeeldinstantie, dan een echte |
| [import-grist.md](import-grist.md) | De import uit het Grist-document |
| [personas/](personas/README.md) | Het personaboek: wie met grip werkt, met een vaste code per persona |
