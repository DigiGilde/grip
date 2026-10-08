# 0008 Een beslisfunctie, FTV later

Status: aanvaard (2026-10-08)

## Context

Federatieve Toegangsverlening (FTV) moet toegangsbeslissingen op termijn buiten applicaties leggen. Wat FTV concreet voorschrijft en of het al bruikbaar is, is niet uitgezocht. AuthZEN beschrijft de vorm van zo'n beslisverzoek: wie, welke actie, welk object, welke context.

Bouwmeester beslist in de applicatie zelf, met functies en eenheden in de database.

## Besluit

Elke toegangsbeslissing in grip loopt via een functie:

```
decide(subject, action, resource, data_class)
```

De functie beslist nu op gegevens in de eigen database. Haar vorm volgt een AuthZEN-verzoek, zodat een extern beslispunt haar later kan vervangen. Tussen organisaties regelt FSC de toegang per contract.

## Gevolgen

- Routes en services bevatten geen eigen toegangscontroles.
- Personen, gasten met een tekenlink en peers gaan door dezelfde functie.
- De aansluiting op FTV is voorbereid en niet gebouwd. Ze kan tegenvallen als FTV een andere vorm vraagt dan AuthZEN.
