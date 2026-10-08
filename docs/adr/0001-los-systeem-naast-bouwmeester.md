# 0001 Grip is een los systeem naast Bouwmeester

Status: aanvaard (2026-10-08)

## Context

Bouwmeester beheert het beleidscorpus: nodes en edges van politieke input tot instrument. De uitvoering van opdrachten stond in een Grist-document. De uitvoering had een module van Bouwmeester kunnen worden, of Bouwmeester had erin kunnen opgaan.

Bouwmeester is een enkele instantie waarin meerdere organisaties via een organisatieboom samenleven. Grip moet juist per organisatie of onderdeel apart draaien.

Er bestond al een eerdere vervanger voor twee Grist-documenten, met tarieven, bemensing en offertes maar zonder federatie.

## Besluit

Grip krijgt een eigen repo en een eigen database. Het koppelt met Bouwmeester via een koppelvlak en deelt geen tabellen.

De eerdere vervanger vervalt. Model en code daaruit mogen worden overgenomen waar dat helpt.

## Gevolgen

- Corpus en uitvoering kunnen los van elkaar worden uitgerold en beheerd.
- Wat grip van Bouwmeester nodig heeft moet als koppelvlak bestaan. Dat vraagt wijzigingen in Bouwmeester.
- Patronen voor login en autorisatie worden gekopieerd en lopen daarna uit elkaar, tenzij iemand ze bijhoudt.
