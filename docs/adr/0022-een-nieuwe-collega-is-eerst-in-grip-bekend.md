# 0022 Een nieuwe collega is eerst in grip bekend

Status: aanvaard (2026-10-08). Vervangt in ADR 0013 de regel dat Wies nooit iemand aanmaakt vanuit grip.

## Context

ADR 0013 legde vast dat Wies de bron is van mensen en grip de bron van plaatsingen. Voor een nieuwe collega klopt dat niet. Zodra een vacature is vervuld weet grip wie er komt, in welke rol en vanaf wanneer. Dat is vaak weken voordat die persoon een account, een e-mailadres van de organisatie of een vermelding in Wies heeft. Planning en begroting hebben de persoon dan al nodig.

Er zijn vier systemen in het spel, en geen ervan mag het werk van een ander overdoen:

| Systeem | Houdt bij |
|---|---|
| Het wervingssysteem (bij ODI: Emply) | Kandidaten, sollicitaties en de selectie |
| Grip | De vraag: rol, schaal, omvang, akkoord, formulier en tekst. Vanaf de aanname: de aanstaande collega en de planning |
| Wies | De collega, zodra staf die heeft bevestigd: wie iemand is, merk, vaardigheden |
| De personeelsadministratie | Uiteindelijk de bron van bestaan en dienstverband |

De koppeling zocht personen op e-mailadres. Een nieuwe medewerker heeft dat adres nog niet, en een persoon in grip kon zonder adres niet bestaan.

## Besluit

**Grip bewaart geen kandidaten.** Wie solliciteert en wie in beeld is, staat in het wervingssysteem. Een vacature in grip krijgt een verwijzing naar de vacature daar: het systeem, het kenmerk en een link, met de hand ingevuld. Er is geen veld voor een kandidaat, ook niet bij een gerede of beoogde kandidaat.

**Een persoon komt in grip op het moment van aanname.** "Vervuld" legt vast door wie en vanaf wanneer. Dat maakt een aanstaande collega: een persoon met een startdatum en zonder e-mailadres, die direct is in te plannen en meetelt in de bezetting. Inloggen kan pas als het adres er is.

**De sleutel is de persoons-URI, niet het e-mailadres.** Elke persoon krijgt een URI van de instantie, zoals opdrachten die hebben. Het adres komt later en kan wijzigen.

**De bron verschilt per gegeven en wisselt in de tijd.**

| Gegeven | Bron |
|---|---|
| Bestaan en naam | Grip vanaf de aanname, Wies zodra staf de collega heeft bevestigd |
| E-mailadres | Altijd Wies |
| Aangenomen met startdatum, vertrokken | Vastgelegd in grip met een bronveld: grip, Wies, wervingssysteem of personeelsadministratie |
| Merk | Grip bij het voorstel, daarna Wies |
| Vaardigheden en labels | Wies |
| Plaatsingen en open rollen | Grip |

**Grip stelt de nieuwe collega voor aan Wies; staf van Wies bevestigt of wijst af.** Wies maakt niemand automatisch aan. Na bevestiging bestaat de collega in Wies zonder account en zonder adres, met de URI erbij. Wies meldt terug wat staf besloot. Een afgewezen voorstel komt alleen terug als grip er iets aan wijzigt.

**Het adres komt terug via de URI.** Zodra Wies het adres heeft, stelt grip de beheerder voor het aan de bestaande persoon te koppelen. Er ontstaat geen tweede persoon. Heeft staf van Wies de collega los aangemaakt, zonder URI, dan biedt grip de koppeling aan op gelijke naam en beslist de beheerder.

**Gaat een aanname niet door,** dan vervalt de planning, wordt het voorstel aan Wies ingetrokken en verwijdert Wies de collega die alleen daardoor bestond. Grip verwijdert de persoon na een bewaartermijn. Die is een instelling, `PROSPECTIVE_RETENTION_DAYS`, met vier weken als standaard. Laat de privacyfunctionaris die termijn bevestigen.

## Gevolgen

- Een persoon in grip kan zonder e-mailadres bestaan. Elke plek die een adres aannam is daarop aangepast: inloggen, de lijst met voorstellen uit Wies, de export, het teamscherm.
- De export naar Wies noemt bij een plaatsing de URI naast het adres. Wies zoekt eerst op URI.
- Er is een tweede lijst: naast "Voorstellen uit Wies" in grip staat "Voorstellen uit grip" in Wies.
- De stand van een persoon (aanstaande collega, collega, vertrokken) is een eigen gegeven met een bron. Sluit het wervingssysteem of de personeelsadministratie later aan, dan verandert de bron en niet de vorm. Dat is dezelfde keuze als bij FTV in ADR 0008.
- Grip is geen kandidatenadministratie en heeft dus geen bewaartermijn voor afgewezen kandidaten nodig. De enige persoonsgegevens die grip vóór de eerste werkdag heeft zijn naam en startdatum van wie is aangenomen.
- Een vervulde vacature kan niet terug naar open. Gaat de aanname niet door, dan is een nieuwe vacature nodig.
- Een aanname wordt nu met de hand vastgelegd. Een koppeling met het wervingssysteem is niet gebouwd.
