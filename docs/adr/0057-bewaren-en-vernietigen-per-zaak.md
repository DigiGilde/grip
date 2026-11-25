# 0057 Bewaren en vernietigen per zaak

Status: aanvaard (2026-11-25), op één punt na: wat er na de termijn van een zaak overblijft, is nog open.

Vult aan: [0028 Een stroom van gebeurtenissen als bron](0028-een-stroom-van-gebeurtenissen-als-bron.md), [0056 De kroniek van een opdracht als bron](0056-de-kroniek-van-een-opdracht-als-bron.md)

## Context

Grip legt de bedrijfsvoering vast van een organisatie binnen het Rijk. Voor die stukken geldt de Archiefwet. De selectielijst van de zorgdrager waardeert elk soort dossier: vernietigen na een termijn (V), of blijvend bewaren en overbrengen naar een archief (B). Een termijn loopt vanaf het sluiten van het dossier. Zolang hij loopt, geldt het recht op vergetelheid in principe niet (AVG art. 17 lid 3 onder b). Daarna moet het dossier weg, en de zorgdrager maakt een verklaring van vernietiging (Archiefbesluit 1995 art. 8; vanaf 1 januari 2027 Archiefbesluit 2026 art. 4.1). Persoonsgegevens die voor de taak niet nodig zijn, mogen ook tijdens de termijn niet blijven. Binnen één proces mogen verschillende termijnen gelden.

Grip wiste tot nu toe op leeftijd, per gebeurtenis (ADR 0028), en niets voerde dat uit. Wist het een feit van een lopende zaak, dan is elke latere stand onvolledig (ADR 0056). Een opdracht kende geen sluitdag. Een getypte tekst die er nooit in hoorde, was alleen weg te krijgen door een heel feit te wissen, want de database staat niets anders toe.

## Besluit

**Een dossier sluit met een feit.** `dossier_closed` legt de dag vast in `assignment.dossier_closed_on`, `dossier_reopened` maakt dat ongedaan. Sluiten kan als de opdracht is afgerond, verantwoord of geannuleerd, op vandaag of een eerdere dag, maar niet voor de laatste wijziging aan de zaak. Het is optioneel: zonder sluitdag loopt geen termijn. Een gesloten dossier verandert niet; wie het wil wijzigen, laat het eerst heropenen. Heropenen kan tot de zaak is vernietigd.

**Alleen de beheerder heropent een dossier, met een reden.** Eigenaar en managers sluiten een dossier en houden het open, maar heropenen het niet zelf, net als een afgesloten maand. Is een dossier onterecht gesloten, ook door Grip zelf terwijl er nog iets moest gebeuren zoals een factuur, dan heropent de beheerder het. De reden staat in `dossier_reopened` en in de wijzigingsregel. De kroniek toont haar onder het moment, met wie heropende; een herstelfeit kan haar er weer uit halen.

**Een dossier dat niemand sluit, krijgt een voorstel en sluit daarna vanzelf.** Is een opdracht afgerond, verantwoord of geannuleerd en is er een jaar niets aan veranderd, dan krijgt de eigenaar de taak het dossier te sluiten. Wie het open wil houden, legt dat vast met `dossier_kept_open`; dat telt als activiteit, dus de klok begint opnieuw. Staat de taak er drie maanden en is er sindsdien niets veranderd, dan sluit Grip het dossier zelf, op die dag. Zonder voorstel sluit Grip niets. Activiteit is een wijziging aan de zaak door een persoon of een andere organisatie: geen inzage, niets wat Grip zelf doet, niet het oppakken, toewijzen of overnemen van een taak, en ook geen herstelfeit. Beide termijnen zijn instellingen; leeg zet ze uit. Zo blijft geen dossier voorgoed open, en begint de bewaartermijn altijd een keer te lopen.

**Een gesloten dossier beëindigt het werk aan de zaak.** De andere open taken van de zaak vervallen. Wordt een zaak heropend die nog niet is verantwoord, dan komen ze terug.

**Een termijn per soort zaak.** Een instelling zegt per soort zaak wat de selectielijst zegt: vernietigen zoveel jaar na het sluiten, of blijvend bewaren. Staat er niets, dan wordt niets vernietigd. Welke regel uit de lijst geldt, bepaalt de informatiebeheerder van de zorgdrager.

**Na de termijn wordt de zaak vernietigd.** Grip vernietigt de rijen van de zaak, de waarden van haar gebeurtenissen in de stroom en elke kopie: berichten aan en van andere organisaties, mail en meldingen in de wachtrij, tekenlinks, bewijs en opgeslagen documenten. Een zaak die blijvend wordt bewaard, blijft heel. Wat er na de vernietiging overblijft, is nog open. Voorstel: alleen de verklaring van vernietiging (kenmerk, naam, opdrachtgever, periode, sluitdag, de regel, en wanneer en hoe er is vernietigd), zonder bedragen en zonder personen. Het andere antwoord is dat de zaak zelf zichtbaar blijft met haar gegevens zonder personen, zoals voor welk onderdeel ze liep.

**Per soort gegeven kan een kortere termijn gelden.** Kandidaten die niet doorgingen, de aanvraagformulieren van een vacature en wie wat inzag, hebben elk een eigen termijn. Wijkt die af van de selectielijst, dan legt de zorgdrager de afwijking vast (Archiefbesluit 2026 art. 3.9 en 3.10).

**Wissen op leeftijd raakt geen opdracht.** `events.retention_days` geldt voor gebeurtenissen buiten een opdracht. Wat bij een opdracht hoort, gaat met de zaak. Inzage valt onder haar eigen termijn.

**De worker voert het uit.** Eén keer per dag, op het uur `RETENTION_HOUR` in de zone van de instantie: dossiers sluiten waarvan het voorstel onbeantwoord bleef, wissen op leeftijd, kandidaten verwijderen en aanvraagformulieren verwijderen. Het vernietigen van zaken komt erbij zodra het is gebouwd.

**Een tekst die er nooit in hoorde, gaat eruit met een herstelfeit.** Een beheerder kiest in een moment een getypte tekst: een naam, notities, een omschrijving of een reden. Grip wist alle waarden van dat feit en legt in dezelfde transactie `fact_restated` vast: dezelfde vaststelling zonder die tekst, met wat er is weggehaald. Bij het lezen neemt het herstelfeit de plek in van het gewiste feit. De stand blijft dus compleet en zegt dat er later een tekst is verwijderd. Andere gebeurtenissen van de zaak die dezelfde tekst als getypte tekst bevatten, zoals een wijzigingsregel, worden ook gewist. Een gebeurtenis die de tekst alleen ergens anders noemt, houdt haar waarden: een besluit, een status of bewijs verdwijnt niet door een toevallige overeenkomst.

## Gevolgen

- `assignment.dossier_closed_on` is een nieuwe kolom. Oudere feiten noemen haar niet; een stand leest haar dan als leeg.
- Een gesloten dossier weigert elke wijziging aan de opdracht, haar regels, rollen, inzet, kostendekking, offertes en hun goedkeuring, maanden, aanleveringen en facturen. Dat geldt ook voor een bericht van een andere organisatie, zoals een eindrapport. Drie dingen schrijven nog wel: het samenvoegen van rollen in de catalogus, dat de rolnaam op elke regel bijwerkt, het bewaren van het bestand van een oudere offerte wanneer iemand het leest, en een herstelfeit.
- De schermen bieden op een gesloten dossier geen wijziging aan. Alleen de beheerder krijgt de handeling om het te heropenen. Eigenaar en managers lezen op het scherm en in de foutmelding dat wijzigen weer kan als de beheerder het dossier heropent. Wie de zaak beheert, kan alles blijven lezen en het bewijs van een besluit blijven downloaden.
- Het takenplan krijgt versie 2026.4 met de taak om een dossier te sluiten. Die versie neemt de lopende zaken van 2026.2 en 2026.3 over, anders krijgt geen bestaande zaak het voorstel. De takenmotor kijkt ook naar verantwoorde en geannuleerde opdrachten, tot hun dossier gesloten is; zo'n zaak krijgt dan alleen die taak.
- Een dossier dat Grip zelf sluit, staat in de kroniek met Grip als wie vaststelde, niet met een persoon.
- Na vernietiging is er geen rij meer, dus `kroniek-check` vindt de zaak niet. De verklaring is het spoor.
- Een herstelfeit haalt niets terug wat al naar een andere organisatie is gestuurd. De vaste kolommen van een gebeurtenis (wie, wanneer, welk type) blijven; alleen de waarden gaan. Een kopie buiten de getypte tekst, zoals de titel van een taak of een melding, blijft ook.
- Een ander feit van de zaak met dezelfde tekst krijgt ook een herstelfeit, en wordt nooit alleen gewist. Een uitgegeven offerte houdt haar bevroren inhoud, ook met die tekst.
- Een tekst korter dan acht tekens gaat alleen waar hij de hele waarde is; een langere ook als woord of zin binnen een andere waarde.
- Een vacature heeft nog geen kroniek. Tot ze een sluitdag en een vernietiging heeft, wist de leeftijdsregel haar gebeurtenissen; de termijnen per soort gegeven gelden al.
- `RETENTION_HOUR` staat standaard op 4; leeg zet de taak uit. Een voorbeeldinstantie gaat om 3 uur terug naar haar beginstand; daar mogen de twee uren niet samenvallen.
