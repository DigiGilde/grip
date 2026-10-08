# 0021 Het kanaal hoort bij het aanbieden van een offerte

Status: aanvaard (2026-10-08)

## Context

Een opdracht had een veld voor het verkeer met de opdrachtgever: geen, de offerte als document, of via de grip van de opdrachtgever. Wie een opdracht aanmaakte moest dat meteen kiezen.

Die keuze hoort daar niet. Hoe een offerte de opdrachtgever bereikt is geen eigenschap van de opdracht. Het is een beslissing op het moment dat een offerte wordt aangeboden, het kan per offerte verschillen, en het kan veranderen: eerst via de grip van de opdrachtgever, en als dat blijft liggen alsnog als document. Er ontbrak bovendien een mogelijkheid: de offerte aanbieden in de eigen grip, waar de opdrachtgever tekent via de tekenlink.

Het veld stuurde ook het verkeer tussen instanties. Een uitgegeven offerte ging vanzelf naar de instantie van de opdrachtgever als de opdracht op "federatief" stond.

## Besluit

Een opdracht heeft geen verkeersvorm meer. Uitgeven en aanbieden zijn twee stappen.

- **Uitgeven** bevriest de offerte: canonieke vorm en hash (ADR 0020). Er gaat niets naar iemand toe.
- **Aanbieden** gebeurt daarna, via een kanaal dat op dat moment wordt gekozen:
  1. *via de grip van de opdrachtgever*: de offerte gaat naar de instantie van de opdrachtgever. Dit kan alleen als die organisatie gekoppeld is: er is een actieve koppeling met haar instantie, met een contract voor `grip-opdrachtverkeer`. Kan het niet, dan zegt grip waarom.
  2. *met een tekenlink in de eigen grip*: iemand bij de opdrachtgever wordt uitgenodigd, logt in met SSO Rijk en tekent hier.
  3. *als document*: de offerte gaat als document mee; het getekende exemplaar wordt later vastgelegd.
- Elke aanbieding wordt bij de offerte vastgelegd: het kanaal, wanneer, door wie en aan wie (de instantie, het uitgenodigde adres, of niemand bij een document). Een offerte mag vaker en langs meer dan een weg worden aangeboden.
- Een beslissing (akkoord of afwijzing) sluit de offerte, langs welk kanaal ze ook is aangeboden. De vorm van het akkoord (ADR 0010) legt vast hoe er werkelijk is getekend.
- Wat blijft is het soort opdracht: extern of intern. Intern betekent dat er geen opdrachtgever is.
- Of een opdracht met een andere instantie wordt **gedeeld** is geen instelling maar een feit dat uit een uitwisseling ontstaat: er kwam een aanvraag van die instantie, er ging een aanvraag naar toe, of er is een offerte aan aangeboden of van ontvangen. Dat feit staat op de opdracht. Alleen over een gedeelde opdracht gaat iets naar die instantie (een akkoord, een afwijzing, het eindrapport), en alleen een gedeelde opdracht is voor die instantie op te vragen.
- Een opdracht die als aanvraag van een instantie binnenkwam is vanaf het begin met die instantie gedeeld. De offerte terug aanbieden via de grip van de opdrachtgever is dan het voorstel, geen verplichting.

## Gevolgen

- Het formulier voor een opdracht verliest een veld. Een aanroep die het veld nog meestuurt wordt niet geweigerd; het veld wordt genegeerd.
- Na het uitgeven van een offerte volgt op het scherm een stap "Aanbieden" met de drie kanalen, de aanbiedingen die al zijn gedaan, en bij de grip van de opdrachtgever de stand van de aflevering (klaar om te versturen, afgeleverd, niet afgeleverd).
- Een uitnodiging voor de tekenlink is een aanbieding en wordt als zodanig vastgelegd, ook als ze langs de bestaande weg wordt gedaan.
- Het domein weet niet hoe instanties gekoppeld zijn (ADR 0015). Het vraagt aan het onderdeel dat dat wel weet of een offerte naar een instantie kan, en krijgt een reden terug als het niet kan. Staat het verkeer met andere instanties uit, dan is dat de reden.
- Bestaande opdrachten met de verkeersvorm "federatief" zijn bij de migratie gedeeld met de instantie van de andere partij. De oude waarde staat in de auditlog.
- Dit vult ADR 0010 aan: de drie vormen van tekenen blijven, maar ze volgen niet meer uit een keuze bij het aanmaken van de opdracht.
