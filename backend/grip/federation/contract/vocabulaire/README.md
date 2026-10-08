# Woordenlijst

Gegenereerd uit `kern.source.json` met `just build`. Niet met de hand bewerken.

> **Naamruimte is een plaatshouder.** `https://grip-koppelvlakken.example/` staat op een plek, in `kern.source.json`,
> en moet worden vervangen door een duurzaam domein voordat versie 1.0.0 wordt vastgesteld.

## Node-typen

| Id | Naam | Betekenis | URI |
|---|---|---|---|
| `dossier` | Dossier | Bundeling van samenhangende nodes rond een beleidsonderwerp. | https://grip-koppelvlakken.example/def/node-type/dossier |
| `doel` | Doel | Wat met beleid bereikt moet worden. | https://grip-koppelvlakken.example/def/node-type/doel |
| `instrument` | Instrument | Middel waarmee een doel wordt nagestreefd, zoals wetgeving, een subsidie of een opdracht aan een uitvoerder. | https://grip-koppelvlakken.example/def/node-type/instrument |
| `beleidskader` | Beleidskader | Kader of principe waarbinnen beleid tot stand komt. | https://grip-koppelvlakken.example/def/node-type/beleidskader |
| `maatregel` | Maatregel | Concrete actie die een doel of instrument uitvoert. | https://grip-koppelvlakken.example/def/node-type/maatregel |
| `politieke_input` | Politieke input | Politieke wens of opdracht, zoals een passage uit het coalitieakkoord, een motie of een toezegging. | https://grip-koppelvlakken.example/def/node-type/politieke_input |
| `probleem` | Probleem | Maatschappelijk of bestuurlijk probleem waar beleid op reageert. | https://grip-koppelvlakken.example/def/node-type/probleem |
| `effect` | Effect | Beoogd of gemeten gevolg van beleid: output, outcome of impact. | https://grip-koppelvlakken.example/def/node-type/effect |
| `beleidsoptie` | Beleidsoptie | Mogelijke aanpak die wordt verkend, voorgesteld, gekozen of afgewezen. | https://grip-koppelvlakken.example/def/node-type/beleidsoptie |
| `bron` | Bron | Document of publicatie waar andere nodes naar verwijzen. | https://grip-koppelvlakken.example/def/node-type/bron |

## Edge-typen

| Id | Naam | Betekenis | URI |
|---|---|---|---|
| `implementeert` | Implementeert | Het ene item implementeert of voert het andere uit. | https://grip-koppelvlakken.example/def/edge-type/implementeert |
| `draagt_bij_aan` | Draagt bij aan | Het ene item draagt bij aan de realisatie van het andere. | https://grip-koppelvlakken.example/def/edge-type/draagt_bij_aan |
| `vloeit_voort_uit` | Vloeit voort uit | Het ene item vloeit voort uit of is afgeleid van het andere. | https://grip-koppelvlakken.example/def/edge-type/vloeit_voort_uit |
| `conflicteert_met` | Conflicteert met | Spanningen of tegenstrijdigheden tussen twee items. | https://grip-koppelvlakken.example/def/edge-type/conflicteert_met |
| `verwijst_naar` | Verwijst naar | Het ene item verwijst expliciet naar het andere. | https://grip-koppelvlakken.example/def/edge-type/verwijst_naar |
| `vereist` | Vereist | Het ene item is een voorwaarde voor het andere. | https://grip-koppelvlakken.example/def/edge-type/vereist |
| `evalueert` | Evalueert | Het ene item beoordeelt of evalueert het andere. | https://grip-koppelvlakken.example/def/edge-type/evalueert |
| `vervangt` | Vervangt | Het ene item vervangt het andere. | https://grip-koppelvlakken.example/def/edge-type/vervangt |
| `onderdeel_van` | Onderdeel van | Het ene item is een onderdeel of deelstrategie van het andere. | https://grip-koppelvlakken.example/def/edge-type/onderdeel_van |
| `leidt_tot` | Leidt tot | Causale relatie: het ene item leidt tot het andere (probleem naar doel, maatregel naar effect). | https://grip-koppelvlakken.example/def/edge-type/leidt_tot |
| `adresseert` | Adresseert | Het ene item adresseert of pakt het andere aan (maatregel of instrument naar probleem). | https://grip-koppelvlakken.example/def/edge-type/adresseert |
| `meet` | Meet | Het ene item meet of monitort het andere (effect naar doel). | https://grip-koppelvlakken.example/def/edge-type/meet |

## Eigen typen

Een corpus mag typen gebruiken die niet in de kernlijst staan. Daarvoor geldt:

1. Een eigen type staat in een naamruimte van het corpus zelf, bijvoorbeeld
   `{corpus}/def/node-type/{id}` of `{corpus}/def/edge-type/{id}`. Nooit in de naamruimte van de kernlijst.
2. In een bericht staat een kerntype als kort id (`doel`) en een eigen type als volledige URI.
3. Het corpus beschrijft zijn eigen typen via `GET /woordenlijst` van de dienst `corpus-context`, met `eigen: true`.
4. Een ontvanger die een eigen type niet kent, toont de node of edge met het type als URI en verwerkt de rest gewoon.
5. Een eigen type dat in meerdere corpora nodig blijkt, wordt voorgesteld voor de kernlijst (zie CONTRIBUTING.md).

De ids in de kernlijst komen overeen met de node-typen en edge-typen die Bouwmeester standaard kent.
De omschrijvingen van de node-typen zijn een eerste voorstel en moeten met de beheerders van het corpus worden vastgesteld.
