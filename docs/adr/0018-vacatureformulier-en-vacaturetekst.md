# 0018 Vacatureformulier vullen en vacaturetekst opstellen met VLAM

Status: aanvaard (2026-10-08)

## Context

Een open rol op een opdracht leidt bij werving tot twee stukken handwerk. Het eerste is het aanvraagformulier vacature van de organisatie: een invulbare pdf met de aanvrager, het soort vacature, het soort contract, functie, schaal, FTE, de aanleiding, en daarna advies van HR en concern control en het akkoord van een directielid. Het tweede is de vacaturetekst zelf.

Bijna alles wat op het formulier staat is in grip al bekend: de rol, de schaal en de omvang komen van de begrotingsregel, de aanvrager is de ingelogde gebruiker, en of de vacature declarabel is volgt uit de opdracht.

Voor het opstellen van tekst is er VLAM, het taalmodel dat de overheid zelf beheert. Het hostingplatform biedt het aan als dienst en levert het adres van een interne proxy aan de applicatie. Bouwmeester gebruikt dezelfde dienst.

## Besluit

Grip vult het aanvraagformulier en stelt een concept van de vacaturetekst op.

Het formulier:

- Het lege formulier is een bestand dat de beheerder per instantie aanlevert, samen met een veldkoppeling van formuliervelden naar gegevens in grip. Het staat niet in de repo: elke organisatie heeft een eigen formulier.
- Grip vult de velden van de pdf en levert een bestand dat invulbaar blijft, zodat een adviseur buiten grip kan aanvullen.
- Advies en akkoord kunnen in grip worden vastgelegd. Is dat gebeurd, dan staan ze ook op het gegenereerde formulier.
- De stappen van de wervingsprocedure (aanvraag, advies, akkoord, interne openstelling, voorrangskandidaten, rijksbrede openstelling, externe arbeidsmarkt) zijn stappen op de vacature in grip.

De tekst:

- Grip vraagt VLAM om een concept van de vacaturetekst en van de aanleiding en motivatie, op basis van de rol, de opdracht en eerdere vacatures van de instantie.
- Een concept is een voorstel. Een mens leest, past aan en stelt vast; pas de vastgestelde tekst gaat naar het formulier, naar Wies of naar een andere instantie.
- Bij elke tekst staat of die met een taalmodel is opgesteld, met welk model en wanneer.
- Naar het model gaan geen namen van kandidaten of medewerkers en geen gegevens uit de klassen D, E en F.
- De aansluiting op het model zit achter een eigen servicelaag met een enkele instelling voor adres, sleutel en model. Zonder die instelling werkt alles behalve het opstellen van een concept.

## Gevolgen

- Het model `vacancy` krijgt het soort vacature, het soort contract, de functienaam uit het functiegebouw, de stappen met advies en akkoord, en een tekst met herkomst.
- Er komt een beheerscherm om het lege formulier en de veldkoppeling te beheren.
- Een formulier dat wijzigt bij de organisatie vraagt een nieuwe veldkoppeling, geen nieuwe versie van grip.
- De kwaliteit van een concept hangt af van het model dat VLAM aanbiedt. De prompt en een paar vaste voorbeelden staan in de repo en hebben tests op vorm, niet op inhoud.
- Het gegenereerde formulier bevat namen van collega's. Het valt onder klasse C en wordt niet langer bewaard dan de vacature loopt.
