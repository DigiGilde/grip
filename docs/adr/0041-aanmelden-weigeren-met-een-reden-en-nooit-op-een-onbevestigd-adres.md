# 0041 Aanmelden: weigeren met een reden, en nooit op een onbevestigd adres

Status: aanvaard (2026-10-08)

Vult aan: [0028 Een stroom van gebeurtenissen als bron](0028-een-stroom-van-gebeurtenissen-als-bron.md), [0029 Bewijs van een akkoord](0029-bewijs-van-een-akkoord.md)

## Context

Grip logt in via de Keycloak van het hostingplatform, die doorstuurt naar SSO Rijk. Een persoon wordt bij de eerste aanmelding gevonden op het e-mailadres en daarna op de vaste identiteit van de provider. Niemand had nog via het echte SSO Rijk ingelogd, en een geweigerde aanmelding liet alleen een regel in het logbestand achter. Onbekend was of de provider het adres als bevestigd meldt, in welke vorm het adres en de organisatie binnenkomen en of opnieuw aanmelden wordt afgedwongen.

Het platform heeft een incident gehad waarbij een gebruiker het eigen adres bij de provider naar dat van een ander kon zetten. Toepassingen die alleen op het adres afgingen lieten die gebruiker als de ander binnen. De controle op een bevestigd adres had dat tegengehouden.

Bouwmeester logt al langer zo in. De code, de geschiedenis en de configuratie van het platform laten zien wat de provider stuurt.

## Besluit

- **Een adres telt alleen als de provider ervoor instaat.** Ontbreekt de claim, dan telt het adres niet. Dit wordt geen instelling.
- **Een weigering heeft een reden uit een vaste lijst** en staat, met het aangeboden adres, in de gebeurtenissen. Alleen beheer leest die. Een gelukte aanmelding staat er ook, met de regel waarop de persoon is gevonden.
- **Een bekend adres met een andere identiteit bindt niets opnieuw.** De beheerder ontkoppelt.
- **Naam en organisatie komen uit de claims zoals het platform ze stuurt.** De organisatie is een bewering van de provider.
- **Voor een eerste aanmelding tegen een nieuwe provider is er een verslag** dat gemaskeerd toont wat er binnenkwam en of opnieuw aanmelden echt een nieuwe aanmelding gaf. Het staat alleen aan met een instelling die in een uitgerolde omgeving wordt geweigerd.

## Gevolgen

- De bezoeker leest bij een weigering alleen dat er geen toegang is. De reden is voor de beheerder.
- Het aangeboden adres van iemand zonder toegang wordt bewaard zolang gebeurtenissen worden bewaard.
- Wie bij de provider afbreekt krijgt een eigen code (`geannuleerd`); het scherm toont daar nu de loginpagina zonder melding.
- De rem op aanmelden staat in het geheugen van een proces. Een rem aan de rand blijft nodig.
- Wat het platform voor de client van grip moet inrichten staat in [sso-rijk.md](../sso-rijk.md).
