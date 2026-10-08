# 0003 Grip is leidend voor de opdracht

Status: aanvaard (2026-10-08)

## Context

Bouwmeester heeft een eigen opdrachtentabel met opdrachtgever, opdrachtnemer, budget per begrotingsjaar en status, gekoppeld aan instrumenten en gesynchroniseerd met Fortes Change Cloud. Bouwmeester noemt die opdracht zelf een losse transactionele entiteit, geen node.

Als grip daarnaast opdrachten beheert, bestaan er twee administraties van hetzelfde.

## Besluit

Grip beheert de opdracht, zowel aan de kant van de opdrachtgever als van de opdrachtnemer. Bouwmeester houdt het corpus en toont opdrachten alleen-lezen bij een node, opgehaald uit grip.

De opdrachtentabel en de synchronisatie met Fortes Change Cloud in Bouwmeester blijven tot na de eerste mijlpaal bestaan en worden daarna overgedragen.

## Gevolgen

- Tot de overdracht bestaan er twee plaatsen met opdrachten. Wat er in die periode gebeurt met een opdracht die in beide staat, is niet uitgewerkt.
- Bouwmeester moet opdrachten bij een node kunnen opvragen bij een of meer grip-instanties.
- De koppeling met Fortes Change Cloud verhuist naar grip of vervalt. Dat besluit is nog niet genomen.
