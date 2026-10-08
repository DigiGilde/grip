# 0031 De tekenlink gaat per mail, via een wachtrij

Status: aanvaard (2026-10-08)

## Context

Wie een offerte aanbiedt "met een tekenlink", kreeg de link op het scherm en moest hem zelf naar de ondertekenaar sturen. Het hostingplatform biedt sinds kort een dienst om e-mail te versturen: een centrale mailrelay waar een project na goedkeuring door een beheerder een eigen SMTP-account op krijgt. De relay zet zelf het afzenderadres, ondertekent de post en geeft haar door aan de mailserver van de organisatie. Ontvangen kan niet.

Een mail van een overheidsorganisatie met een link om in te loggen is precies het bericht dat mensen leren wantrouwen. En mail is geen vertrouwelijk kanaal.

## Besluit

**Een wachtrij, geen verzending in het verzoek.** Een bericht wordt in de wachtrij gezet in dezelfde transactie als de wijziging die het veroorzaakt. Het bestaat dus alleen als de wijziging bestaat. De worker verstuurt het, probeert het bij een tijdelijke weigering opnieuw met een oplopende pauze, en geeft het na een vast aantal pogingen op. Een bericht staat op wachtend, verstuurd of mislukt, het laatste met de reden.

**Uit zonder instellingen.** Zonder `SMTP_HOST` en `SMTP_FROM` wordt er niets in de wachtrij gezet en niets verstuurd. De link kopieren blijft dan de weg. De namen van de instellingen zijn die van de dienst op het platform, zodat er niets te vertalen valt.

**De eerste mail is de tekenlink.** Bij aanbieden met een tekenlink gaat er een bericht naar het uitgenodigde adres. Het noemt de organisatie, de opdrachtgever, het kenmerk en het onderwerp van de offerte, de link, tot wanneer die geldt, en dat de link alleen werkt voor dit adres na inloggen.

**Geen bedrag en geen namen van medewerkers in het bericht.** De offerte zelf staat achter de login.

**Het bericht zegt hoe je het controleert.** Het adres van de instantie staat uitgeschreven, zodat de lezer het zelf kan typen. Het kenmerk is na te vragen bij de organisatie. Het bericht vraagt nooit om een wachtwoord. In de HTML-versie is de tekst van de link gelijk aan het adres waar hij heen gaat.

**Sober.** Platte tekst met een eenvoudige HTML-versie. Geen afbeeldingen, niets dat van elders wordt opgehaald, niets dat volgt of iemand het bericht opent.

**Antwoorden gaan naar wie aanbood.** De afzender is de organisatie, onder het adres dat de relay oplegt. Het antwoordadres is dat van de persoon die de offerte aanbood, als dat bekend is.

**De tekst blijft niet bewaard.** Na verzenden of opgeven verdwijnt de tekst uit de wachtrij. Wat blijft is dat een bericht van deze soort naar dit adres ging, wanneer, en met welke uitkomst. Dat staat ook in de stroom van gebeurtenissen, zonder de tekst.

**Per instantie uit te zetten.** De instelling `mail.signing_link` staat aan zodra de instantie kan mailen. Een beheerder zet haar uit.

**Opnieuw sturen.** Wie de opdracht beheert kan het bericht opnieuw laten sturen, desgewenst met verlenging van de link. Zolang een eerder bericht nog wacht, komt er geen tweede bij.

## Gevolgen

- "Verstuurd" betekent dat de relay het bericht heeft aangenomen. Of het in een postbus is aangekomen weet grip niet: een melding van onbestelbaarheid komt later terug als mail, en grip ontvangt geen mail. Het scherm zegt "Gemaild op", niet "Afgeleverd".
- Het afzenderadres kiest de instantie niet. Op het platform is het `noreply-rijksapp+<project>@rijksoverheid.nl`, met de naam van het project ernaast. De naam van de organisatie stelt de beheerder van het project in bij de dienst; wat grip in `From` zet, vervangt de relay.
- SPF, DKIM en DMARC van het afzenderdomein zijn de zaak van wie dat domein beheert. Op het platform is dat de relay met het mailteam erachter, niet grip. Een instantie die buiten het platform draait met een eigen afzenderdomein moet ze zelf regelen: zonder die drie komt de post bij veel ontvangers niet aan, en ze staan op de lijst van verplichte standaarden van het Forum Standaardisatie. Grip controleert dit niet.
- De verbinding met de relay loopt over STARTTLS. Het certificaat van de relay is van het cluster zelf; de controle ervan vraagt een eigen instelling (`SMTP_TLS_CA_FILE`), of staat binnen het clusternetwerk uit (`SMTP_TLS_VERIFY`).
- De worker moet draaien, anders blijft post wachten.
- De wachtrij is algemeen. Andere berichten kunnen erop aansluiten; de meeste horen bij een taak. Ze zijn niet gebouwd.
- Een adres en het feit dat er naar gemaild is, zijn persoonsgegevens. Ze vallen onder dezelfde bewaartermijn als de uitnodiging waar ze bij horen.
