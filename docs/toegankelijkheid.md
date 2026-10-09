# Toegankelijkheid

Grip is een toepassing van de overheid. Digitale toegankelijkheid is daarmee een wettelijke plicht: de toepassing moet voldoen aan EN 301 549, in de praktijk WCAG 2.1 op niveau A en AA, en de organisatie legt daarover verantwoording af in een toegankelijkheidsverklaring.

Dit document zegt wat er is getest en hoe, wat de uitkomst is per succescriterium, wat nog niet goed is, en wat de organisatie nog moet doen. De stand is die van 9 oktober 2026. Het is een eigen onderzoek van de bouwers, geen onafhankelijke inspectie.

## Wat de plicht inhoudt

Het Besluit digitale toegankelijkheid overheid geldt voor websites en apps van overheidsinstanties, ook voor intranetten en extranetten die na 23 september 2019 zijn gemaakt of ingrijpend vernieuwd. Grip valt daar op twee manieren onder:

| Deel | Voor wie | Wat geldt |
|---|---|---|
| De toepassing zelf | Rijksambtenaren van de eigen organisatie, na inloggen | Een intern systeem (intranet). De norm geldt volledig. De verklaring hoeft niet voor het publiek vindbaar te zijn, wel voor de gebruikers: een link in de toepassing en een vermelding in het register |
| De pagina's voor gasten: een offerte bekijken en tekenen, een aanvraag doen, een bewijs controleren | Medewerkers van een opdrachtgever, na inloggen bij hun eigen organisatie | Een extranet. De norm geldt volledig. Deze lezers kiezen grip niet zelf en kennen het niet; voor hen weegt een drempel het zwaarst |
| Documenten die grip maakt: de offertebrief, het factuurverzoek, het ingevulde aanvraagformulier, de bewijspagina | Wie ze ontvangt | Vallen onder dezelfde norm zodra ze via de toepassing worden aangeboden |
| Mail die grip verstuurt | De ontvanger | Valt niet onder het besluit, wel onder goed fatsoen. Is meegenomen |

Wat de organisatie moet doen, los van de code:

1. Een toegankelijkheidsverklaring opstellen met de invulassistent van het register van toegankelijkheidsverklaringen, en die publiceren. Het concept staat onderaan dit document.
2. Een onderzoek laten doen volgens WCAG-EM, met handmatige toetsing door een deskundige. Zonder zo'n onderzoek kan de verklaring geen hogere status hebben dan "eerste maatregelen genomen". De status "voldoet gedeeltelijk" vraagt een volledig onderzoek dat niet te oud is.
3. Een meldpunt noemen waar een gebruiker een drempel kan melden, en een termijn waarbinnen antwoord komt.
4. De verklaring elk jaar herzien, en na elke ingrijpende wijziging.

Controleer deze vier punten tegen de actuele uitleg van DigiToegankelijk voordat de verklaring wordt gepubliceerd; de regels en de statussen worden af en toe aangepast.

## Wat er is getest en hoe

### Met de machine

`just check-a11y` draait axe-core in een echte browser (Chrome, zonder venster) op elke route uit `frontend/src/paths.ts`, met echte gegevens uit de voorbeelddatabase. De controle kijkt door de schaduw-DOM van de componenten van het designsysteem heen. Zij meldt ook een eigen regel, `element-not-registered`: een element van het designsysteem waarvan het onderdeel niet geladen is. Elke pagina laadt haar eigen bestanden; een pagina die een onderdeel tekent zonder het te registreren toont het als losse tekst zonder rol. Bij het splitsen van de pagina's kwamen er zo twee boven (de bevestiging van een rijmenu en een formulierdeel bij vacatures); beide zijn hersteld.

| Wat | Hoe |
|---|---|
| Routes | 82, met een opdracht per fase, elke tab van een opdracht en een vacature, elk onderwerp van de rapportage, een pagina die niet bestaat en een opdracht die niet bestaat |
| Lezers | De beheerder, een eigenaar van een opdracht zonder verdere rechten, en waar de voorbeeldgegevens die hebben een tekenbevoegde |
| Breedtes | 1280 en 390 pixels |
| Thema's | Donker en licht |
| Open toestanden (`--open`) | Elk formulier dat een pagina aanbiedt (59), het eerste rijmenu (49), het accountmenu |
| Regels | WCAG 2.1 A en AA, en de goede gebruiken van axe voor structuur |

De uitkomst, geteld als combinatie van regel en pagina (met de open toestanden, breed en donker, 397 metingen):

| Regel | Voor | Na | Wat het was |
|---|---|---|---|
| `region` | 229 pagina's, 770 elementen | 0 | De balk bovenaan stond buiten elk oriëntatiepunt |
| `empty-table-header` | 65 pagina's, 82 elementen | 0 | De kolom met het rijmenu had een lege kop |
| `heading-order` | 13 pagina's, 14 elementen | 0 | Een kop van niveau 3 direct onder niveau 1 |
| Regels van WCAG zelf (namen, rollen, labels, contrast) | 0 | 0 | |

De machine kon van 1.444 elementen het contrast niet zelf beoordelen, omdat tekst en achtergrond in verschillende schaduwbomen staan. Die zijn apart gemeten, zie hieronder.

Een machine vindt naar schatting een derde van wat de norm vraagt. Nul bevindingen is geen bewijs van toegankelijkheid.

### Met de hand, in een gestuurde browser

Alles hieronder is gedaan met scripts die een echte browser bedienen met alleen het toetsenbord, en die uitlezen wat er gebeurt. Er is geen schermlezer gebruikt en er heeft geen gebruiker met een beperking getest.

| Onderwerp | Wat is gedaan | Uitkomst |
|---|---|---|
| Toetsenbord | Zeventien pagina's met alleen Tab doorlopen; per stop de naam, de rol en of de focus zichtbaar is | Alles bereikbaar. Geen stop zonder naam. De volgorde volgt het scherm |
| Zichtbare focus | Per soort bedieningselement een afbeelding van de gefocuste toestand bekeken; de ring gemeten | Ring van 2 pixels, contrast met de achtergrond 4,6:1 (donker) en 6,2:1 (licht) |
| Paginawissel | Via het menu naar een andere pagina | De focus staat op de paginatitel; de titel van het venster noemt de pagina |
| Formulier in een zijpaneel | Openen, doorlopen, leeg versturen, sluiten met Escape, bewaren | Focus gaat het paneel in en blijft erin; Escape sluit en zet de focus terug op de knop die opende; een fout wordt als waarschuwing voorgelezen; bewaren wordt nu gemeld (zie "Wat is hersteld") |
| Rijmenu | Openen met Enter, pijltjes, Escape | Focus op het eerste onderdeel, pijltjes lopen, Escape zet de focus terug. De knop heet "Meer acties voor" met de naam van de rij |
| Menu op een smal scherm | Idem op 390 pixels | Werkt hetzelfde. De knop zegt waar je bent en hoeveel taken er zijn |
| Teksteditor | Met Tab erin en eruit | Geen val: Tab verlaat de editor. Zie "De teksteditor" |
| Tweede navigatiebalk en tabs | Uitgelezen wat een schermlezer krijgt | Navigatie met een naam ("Pagina's van Team", "Onderdelen van" de opdracht), links, de huidige met `aria-current="page"`. Geen tabrollen |
| Verloop in stappen | Uitgelezen | Een lijst, elke stap met zijn toestand in woorden ("Akkoord, Afgerond", "Uitvoeren, Huidige stap"). Op een smal scherm een zin |
| Tijdlijn en het bord Inzet | Uitgelezen en met pijltjes doorlopen | Een echte tabel: een kolomkop per maand, een rijkop per persoon, en in elke cel in woorden wat de balken tonen (totaal, vrij, per opdracht met rol en periode). Eén tabstop, pijltjes lopen de cellen af, Enter opent de maand |
| Kerncijfers en dekkingsbalken | Uitgelezen | Kerncijfers als termen met waarden. Elke balk heeft een tekst met de bedragen en percentages, en ernaast een lijst met dezelfde waarden |
| Tabellen | Uitgelezen | Elke tabel heeft een naam en kolomkoppen |
| Statusmeldingen | In de code en de browser nagegaan | Een fout is een `alert`, een waarschuwing (ook het conflictpaneel) een `status`; geen van beide verplaatst de focus |
| Links naar een nieuw tabblad | Uitgelezen | Zeggen "Opent in nieuw tabblad" |
| Taal | Uitgelezen | `lang="nl"` op de pagina, in de pdf's en in de mail |
| Smal scherm (reflow) | 31 pagina's op 320 bij 256 pixels | Geen pagina schuift nog opzij. Tabellen en het bord schuiven binnen hun eigen kader, wat de norm toestaat. De startpagina was 36 pixels te breed en is hersteld |
| Tekstafstand | De vier waarden uit criterium 1.4.12 opgelegd op 31 pagina's | Geen afgekapte of overlappende tekst |
| Contrast van tekst | Elke zichtbare tekst op 29 pagina's gemeten tegen zijn werkelijke achtergrond, door de schaduw-DOM heen, in twee thema's en twee breedtes | Zie "Contrast" |
| Contrast van niet-tekst | Randen van velden, de focusring, de stappen, de dekkingsbalken | Zie "Contrast" |
| Pdf's | De structuur uitgelezen met pikepdf | Zie "Documenten" |
| Mail | De opbouw gelezen | Platte tekst met een HTML-variant, `lang="nl"`, een echte lijst. De link staat voluit, met de zin "Open de offerte:" ervoor. Dat is bewust: de ontvanger kan zien waar de link heen gaat |

### Contrast

De verwachting was dat de gedempte tweede tekst en de stappen die nog komen zouden zakken. Dat is niet zo. Alle gemeten tekst haalt 4,5:1, in beide thema's; er waren geen kleuren aan te passen.

| Wat | Donker | Licht | Oordeel |
|---|---|---|---|
| Alle tekst op 29 pagina's | minimaal 4,5:1 | minimaal 4,5:1 | Voldoet |
| Nummer in een stap die nog komt | 4,5:1 | 4,6:1 | Voldoet, zonder marge |
| Rand van een invoerveld | 5,3:1 | 5,3:1 | Voldoet |
| Focusring | 4,6:1 | 6,2:1 | Voldoet |
| Schijf van een stap die nog komt, tegen de pagina | 1,4:1 | 1,4:1 | Het nummer en het woord dragen de betekenis, niet de schijf |
| Deel "nog verwacht" en "ongedekt" van een dekkingsbalk | 2,1:1 | 2,5:1 | Onder 3:1. De waarden staan als tekst naast de balk, dus de tekening is niet de enige drager. Verbeterpunt |

De meting gaf twee keer een label op het bord Inzet onder de grens. Dat was een fout van de meting: een label dat niet in zijn balk past staat ernaast, op de achtergrond van het bord, en werd tegen de kleur van de balk gemeten.

### De teksteditor

De editor (`TextEditor`, op de teksteditor van het designsysteem) is een tekstvak met de naam van het veld en `aria-multiline`. Tab springt niet in en gaat naar het volgende element: eerst de aantekeningen bij open plekken in de tekst, dan de knoppen eronder. Shift+Tab gaat terug naar de werkbalk. Er is dus geen toetsenbordval en er is geen aparte uitweg nodig. De knoppen van de werkbalk hebben een naam die zegt wat ze doen ("Maak van deze regel een kop") en melden hun toestand met `aria-pressed`.

### Documenten

| Document | Wat is vastgesteld | Wat niet |
|---|---|---|
| Offertebrief | Getagd, PDF/UA-1 in de metagegevens, taal `nl`, een titel die in de vensterbalk komt, koppen, een lijst, een tabel met kopcellen met bereik, het beeldmerk met een tekstalternatief | Niet gevalideerd met veraPDF. Niet voorgelezen met een schermlezer |
| Factuurverzoek | Wordt met dezelfde aanroep en dezelfde instelling gemaakt als de offertebrief (in de code gelezen) | Geen exemplaar gegenereerd en uitgelezen: de voorbeelddatabase had geen aanlevering |
| Bewijspagina | HTML met taal, titel, een kop en een tabel met rijkoppen (in de code gelezen) | Niet in een browser gecontroleerd |
| Ingevuld aanvraagformulier | Het proefexemplaar uitgelezen: getagd, taal `nl-NL`, tabvolgorde volgt de structuur | Voldoet niet: de 27 invulvelden hebben geen naam voor een schermlezer, het beeld heeft geen alternatief, de titel is de naam van het sjabloon. Het formulier is van de organisatie, grip vult het in. Zie "Bekende punten" |

## Wat is hersteld

| Wat | Waar | Criterium |
|---|---|---|
| De balk bovenaan is een oriëntatiepunt met de naam "Navigatie en account" | `frontend/src/layout/AppShell.tsx` | 1.3.1, 2.4.1 |
| De kolom met het rijmenu heeft een kop die wordt voorgelezen en niet getoond (`RowActionsHeader`) | `frontend/src/ui/RowActions.tsx` en vijftien tabellen | 1.3.1 |
| Koppen slaan geen niveau meer over; een kop kan klein getekend worden en toch het juiste niveau hebben | `SectionHeading` in `frontend/src/ui/layout/primitives.tsx`, de offertekaart, de investeerruimte, de contextkiezer | 1.3.1, 2.4.6 |
| Een formulier dat bewaard is zegt dat: "titel: opgeslagen", via één beleefde live-regio, zonder de focus te verplaatsen. Annuleren zegt niets | `frontend/src/ui/announce.ts`, `frontend/src/ui/layout/FormSheet.tsx` | 4.1.3 |
| De startpagina past op 320 pixels | `frontend/src/features/overview/overview.css` | 1.4.10 |

## Uitkomst per succescriterium

Voldoet betekent: in dit eigen onderzoek geen afwijking gevonden. Het is geen verklaring van een onafhankelijke inspecteur.

| Criterium | Uitkomst | Toelichting |
|---|---|---|
| 1.1.1 Niet-tekstuele content | Voldoet niet | De toepassing voldoet: iconen hebben een naam of zijn verborgen, tekeningen hebben een tekst. Het ingevulde aanvraagformulier (pdf) niet |
| 1.2.1 t/m 1.2.5 Audio en video | Niet van toepassing | Er is geen audio of video |
| 1.3.1 Info en relaties | Voldoet niet | Hersteld: oriëntatiepunten, koppen, tabelkoppen. Open: een toelichting onder een veldlabel is niet aan het veld gekoppeld (designsysteem); invulvelden van het aanvraagformulier |
| 1.3.2 Betekenisvolle volgorde | Voldoet | |
| 1.3.3 Zintuiglijke eigenschappen | Voldoet | Geen aanwijzing die alleen op plaats of kleur leunt gevonden |
| 1.3.4 Weergavestand | Voldoet | Geen vergrendeling |
| 1.3.5 Doel van de invoer | Niet getest | Grip vraagt nauwelijks gegevens over de gebruiker zelf; de velden die dat doen zijn niet nagelopen op `autocomplete` |
| 1.4.1 Gebruik van kleur | Voldoet | Toestanden hebben een woord of teken naast de kleur. Niet elk scherm is hierop met het oog nagelopen |
| 1.4.2 Geluidsbediening | Niet van toepassing | |
| 1.4.3 Contrast (minimum) | Voldoet | Gemeten, zie "Contrast" |
| 1.4.4 Herschalen van tekst | Voldoet | Afgeleid uit de meting op 320 pixels, wat gelijk is aan 400 procent zoom op 1280. Niet apart met alleen tekstvergroting getest |
| 1.4.5 Afbeeldingen van tekst | Voldoet | Geen |
| 1.4.10 Reflow | Voldoet | Na herstel van de startpagina |
| 1.4.11 Contrast van niet-tekstuele content | Voldoet | Met de kanttekening bij de dekkingsbalk |
| 1.4.12 Tekstafstand | Voldoet | |
| 1.4.13 Content bij aanwijzen of focus | Niet getest | Tooltips van het designsysteem zijn niet nagelopen op wegklikken en blijven staan |
| 2.1.1 Toetsenbord | Voldoet | Lijsten met handelingen per rij vragen pijltjes, zie "Voor de beheerders van het designsysteem" |
| 2.1.2 Geen toetsenbordval | Voldoet | Ook de teksteditor niet |
| 2.1.4 Enkele-toetsbediening | Voldoet | Er zijn geen sneltoetsen van één teken |
| 2.2.1 Timing aanpasbaar | Niet getest | De sessie verloopt; of de gebruiker daarvoor gewaarschuwd wordt en kan verlengen is niet onderzocht |
| 2.2.2 Pauzeren, stoppen, verbergen | Voldoet | Niets beweegt of ververst zichtbaar vanzelf, behalve het aantal taken in het menu, één keer per minuut |
| 2.3.1 Drie flitsen | Voldoet | |
| 2.4.1 Blokken omzeilen | Voldoet | Een link "Direct naar de inhoud" en oriëntatiepunten |
| 2.4.2 Paginatitel | Voldoet | Pagina, organisatie, grip |
| 2.4.3 Focusvolgorde | Voldoet | Niet getest: waar de focus staat nadat een rij is verwijderd en na "Neem deze stap over" |
| 2.4.4 Linkdoel | Voldoet | Een taak heet naar wat er moet gebeuren; "Bekijk pdf" staat in de kaart van de offerte waar het bij hoort |
| 2.4.5 Meerdere manieren | Voldoet | Het menu, de taken, links tussen de onderdelen. Er is geen zoekfunctie over alles |
| 2.4.6 Koppen en labels | Voldoet | |
| 2.4.7 Focus zichtbaar | Voldoet | |
| 2.5.1 Aanwijzergebaren | Voldoet | Geen gebaren met meer vingers of een pad |
| 2.5.2 Aanwijzerannulering | Niet getest | |
| 2.5.3 Label in naam | Voldoet | De zichtbare tekst staat in de naam; bij een taak komt er "ga naar het werk" achter |
| 2.5.4 Bewegingsactivering | Niet van toepassing | |
| 3.1.1 Taal van de pagina | Voldoet | |
| 3.1.2 Taal van onderdelen | Niet getest | Engelse termen in ingevoerde tekst zijn niet gemarkeerd |
| 3.2.1 Bij focus | Voldoet | |
| 3.2.2 Bij invoer | Voldoet | Een filter boven een lijst past de lijst direct aan; dat staat bij het filter |
| 3.2.3 Consistente navigatie | Voldoet | |
| 3.2.4 Consistente identificatie | Voldoet | Vaste woorden uit `docs/ontwerp.md`, één patroon voor rijhandelingen |
| 3.3.1 Foutidentificatie | Voldoet | De fout staat boven het formulier, in woorden die het veld noemen, en wordt voorgelezen. Het veld zelf wordt niet gemarkeerd, zie "Bekende punten" |
| 3.3.2 Labels of instructies | Voldoet | Elk veld heeft een label; wat niet hoeft heet "Optioneel" |
| 3.3.3 Foutsuggestie | Voldoet | |
| 3.3.4 Foutpreventie | Voldoet | Verwijderen en tekenen vragen een bevestiging; een offerte is na uitgifte bevroren |
| 4.1.1 Parsen | Niet van toepassing | Vervallen verklaard voor WCAG 2.1 |
| 4.1.2 Naam, rol, waarde | Voldoet niet | De toepassing: geen afwijking gevonden. Het aanvraagformulier: velden zonder naam |
| 4.1.3 Statusberichten | Voldoet | Voor formulieren. Een handeling uit een rijmenu die direct wordt uitgevoerd meldt nog niets, zie "Bekende punten" |

## Bekende punten

| Punt | Voor wie een drempel | Plan |
|---|---|---|
| Het ingevulde aanvraagformulier heeft velden zonder naam, een beeld zonder alternatief en de titel van het sjabloon | Wie de pdf met een schermlezer leest of invult | De eigenaar van het formulier vragen om een toegankelijk sjabloon. Tot dan kan grip bij het invullen de naam van elk veld uit de koppeling van het sjabloon erbij zetten en de titel vervangen; dat is een wijziging in de server |
| Een fout in een formulier staat boven het formulier; het veld zelf krijgt geen markering en de focus blijft op de knop | Wie niet ziet welk veld bedoeld is, in een lang formulier | De velden kennen `invalid`. Formulieren per stuk laten zeggen welk veld de fout draagt, het markeren en de focus erheen zetten. Begin bij de formulieren voor gasten |
| Een handeling die direct wordt uitgevoerd (uit een rijmenu, "Neem deze stap over", verwijderen na bevestiging) wordt niet gemeld, en waar de focus daarna staat is niet nagelopen | Schermlezergebruikers | `announce` uit `@/ui/announce` op die plekken aanroepen; na verwijderen de focus op de volgende rij of de kop van de tabel zetten |
| De toelichting onder een veldlabel wordt niet voorgelezen wanneer de focus in het veld staat | Schermlezergebruikers die met Tab door een formulier gaan | Ligt bij het designsysteem, zie hieronder. In de leesmodus is de tekst wel te vinden |
| Delen van de dekkingsbalk hebben minder dan 3:1 contrast | Slechtzienden | Een rand om de balk of een donkerder tint voor het open deel |
| Geen onderzoek met een schermlezer en geen onderzoek door een gebruiker met een beperking | | Het onafhankelijke onderzoek |

## Voor de beheerders van het designsysteem

Gevonden in `@nldd/design-system` 0.8.96. Deze punten zijn van buitenaf niet netjes op te lossen en zijn niet omzeild.

| Component | Wat de gebruiker merkt | Wat verwacht wordt | Criterium |
|---|---|---|---|
| `nldd-page` | Een schermlezer kondigt een banner en een voettekst aan die leeg zijn. Een schil met `nldd-bar-split-view` kan zijn eigen balk daardoor geen banner maken zonder dat er twee zijn | Geen `header` en `footer` in de structuur zolang hun slot leeg is, of een manier om de balk van de schil als banner aan te wijzen | 1.3.1, 2.4.1 |
| `nldd-form-field` | De tekst van `supporting-label` wordt niet voorgelezen wanneer de focus in het veld komt | De toelichting als beschrijving aan het veld in de slot koppelen (`aria-description`, of een verwijzing binnen dezelfde boom) | 1.3.1, 3.3.2 |
| `nldd-list` met rijen die een handeling hebben | De lijst is één tabstop; de rijen daarna zijn alleen met de pijltjes te bereiken. De rol is die van een gewone lijst, dus niets zegt dat pijltjes nodig zijn | Elke link een eigen tabstop, of een rol en een aanwijzing die bij dit gedrag horen | 2.1.1 (gehaald), 4.1.2 |
| `nldd-date-field` | In een formulier met twee datums heten beide knoppen "Datum kiezen" | De naam van het veld in de naam van de knop: "Datum kiezen voor Begindatum" | 2.4.6 |
| `nldd-step-bar` | Een verloop zonder links wordt aangekondigd als navigatie | Alleen een navigatie wanneer de stappen links zijn; anders een lijst met een naam | 1.3.1 |
| `nldd-step-bar-item` | De schijf van een stap die nog komt heeft 1,4:1 tegen de pagina; het nummer erin haalt 4,5:1 zonder marge | Een rand of tint die 3:1 haalt | 1.4.11 |
| `nldd-skip-link` | Geen drempel. Hulpmiddelen als axe melden de link als inhoud buiten een oriëntatiepunt, omdat de link zelf in de schaduwboom staat | Ter kennisgeving | |

## Concept van de toegankelijkheidsverklaring

Dit is een concept. De organisatie vult het aan (alles tussen rechte haken), neemt het over in de invulassistent van het register van toegankelijkheidsverklaringen en publiceert het. De bouwers kunnen deze verklaring niet namens de organisatie afleggen.

> **Toegankelijkheidsverklaring van grip**
>
> [Naam van de organisatie] wil dat iedereen grip kan gebruiken en werkt eraan om te voldoen aan het Besluit digitale toegankelijkheid overheid.
>
> Deze verklaring geldt voor grip op [adres van de instantie], met de pagina's voor medewerkers van opdrachtgevers en de documenten die grip maakt.
>
> **Status: eerste maatregelen genomen.** [Na een volledig onafhankelijk onderzoek naar verwachting: voldoet gedeeltelijk.]
>
> **Onderbouwing.** Grip is in oktober 2026 door de bouwers zelf onderzocht: een geautomatiseerde controle van alle pagina's en een handmatige controle van toetsenbord, focus, namen, contrast, reflow en de documenten. Er is nog geen onderzoek volgens WCAG-EM door een onafhankelijke deskundige gedaan. Dat staat gepland voor [datum].
>
> **Wat nog niet voldoet**
>
> 1. Het ingevulde aanvraagformulier (pdf) heeft invulvelden zonder naam en een beeld zonder tekstalternatief (WCAG 1.1.1, 1.3.1, 4.1.2). Oorzaak: het sjabloon van het formulier. Gevolg: het formulier is met een schermlezer niet goed te lezen. Alternatief: de gegevens van de aanvraag staan volledig op de pagina van de vacature in grip. Maatregel: [een toegankelijk sjabloon, of namen bij de velden bij het invullen]. Planning: [datum].
> 2. De toelichting bij een formulierveld wordt niet voorgelezen wanneer het veld de focus heeft (WCAG 1.3.1). Oorzaak: het gebruikte designsysteem. Gevolg: een schermlezergebruiker mist de toelichting, tenzij die het formulier eerst leest. Maatregel: gemeld bij de beheerders van het designsysteem. Planning: [datum].
>
> **Wat nog niet is onderzocht:** het gebruik met een schermlezer, met spraakbesturing en met alleen tekstvergroting; de melding bij het verlopen van de sessie; tooltips.
>
> **Een probleem melden.** Loopt u tegen een drempel aan? Meld het bij [meldpunt]. U krijgt binnen [termijn] antwoord. Bent u niet tevreden met het antwoord, dan kunt u terecht bij de Nationale ombudsman.
>
> Deze verklaring is opgesteld op [datum] en wordt uiterlijk een jaar later herzien.

Wat het onafhankelijke onderzoek nog moet doen:

- Een steekproef volgens WCAG-EM, met de pagina's voor gasten erin.
- Toetsen met ten minste twee schermlezers (NVDA of JAWS op Windows, VoiceOver op macOS of iOS), met spraakbesturing en met schermvergroting.
- De criteria die hierboven "Niet getest" hebben.
- Het factuurverzoek, de bewijspagina en een echt ingevuld aanvraagformulier.
- De pdf's valideren met veraPDF en voorlezen.
- De schermen in de modus met hoog contrast van het besturingssysteem.

## Zo draai je de controle

De controle heeft draaiende servers nodig met voorbeeldgegevens, en een eigen hostnaam: de lezer wordt gekozen met het ontwikkelcookie, en dat mag niet op de `localhost` komen waar je zelf in werkt. Elke naam die op `.localhost` eindigt wijst naar de eigen machine.

```
just check-a11y --base http://a11y.localhost:5183
just check-a11y --base http://a11y.localhost:5183 --open --widths 1280 --themes dark
just check-a11y --base http://a11y.localhost:5183 --only /opdrachten --detail
```

| Optie | Wat het doet |
|---|---|
| `--open` | Opent ook formulieren en menu's en controleert die. Er wordt niets verstuurd, maar gebruik een database die weg mag |
| `--only <pad>` | Alleen routes die met dit pad beginnen |
| `--persons "<naam>,<naam>"` | Andere lezers dan de standaard drie |
| `--widths`, `--themes` | Standaard `1280,390` en `dark,light` |
| `--detail` | Per regel de pagina's en de elementen |
| `--json <bestand>` | Alle bevindingen als gegevens |

De volledige matrix duurt ongeveer een kwartier. De uitvoer is een tabel per regel; de code van afsluiten is 1 bij een bevinding. Wat de machine niet kon beslissen staat eronder en moet met de hand worden nagelopen.

Naast de controle in de browser staat een test die bij elke build draait, `frontend/src/ui/a11y.guard.test.ts`. Die faalt op een icoonknop zonder naam, een beeld zonder alternatief, een keuzelijst of veld zonder label, een tabel zonder naam en een lege kopcel.

Voor een nieuw scherm:

1. Draai `just check-a11y --only <pad> --open`.
2. Loop het scherm met alleen het toetsenbord door: alles bereikbaar, de focus zichtbaar, een paneel geeft de focus terug.
3. Zet een tekening nooit alleen: een tabel of een tekst met dezelfde waarden hoort erbij.
4. Meld wat er gebeurde met `announce` wanneer het scherm verandert zonder dat de focus meegaat.
