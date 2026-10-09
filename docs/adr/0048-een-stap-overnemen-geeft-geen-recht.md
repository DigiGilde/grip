# 0048 Een stap overnemen geeft geen recht, en wie anders moet beslissen blijft dat doen

Status: aanvaard (2026-10-09)

## Context

Wie een zaak leidt en niet aan zet is, kan een stap van een ander overnemen (ADR 0044). Dat houdt werk in beweging als iemand ziek is of weg.

In de eerste uitwerking kon een eigenaar zo de stap van de interne goedkeurder nemen. De kop van de opdracht zei daarna dat zij haar eigen offerte kon goedkeuren, en de goedkeurder was de taak kwijt. Dat haalt het doel van interne goedkeuring onderuit: een tweede persoon die beslist.

Bij het herstel bleek dat de handelingen zelf de scheiding ook niet overal afdwongen. Interne goedkeuring weigerde wie erom vroeg, maar niet wie de offerte maakte. Advies en akkoord op een vacature kon de aanvrager voor zichzelf vastleggen. En waar beide kanten van een offerte in een instantie leven, kon de maker als opdrachtgever tekenen.

## Besluit

**Een stap overnemen geeft nooit een recht.** Overnemen kan alleen wie de handeling van die stap zelf al mag doen. De beslissing loopt door dezelfde beslisfunctie als de handeling. Het scherm en de server lezen dezelfde regel, zodat het scherm niet kan aanbieden wat de server weigert.

**Een stap waar een ander moet beslissen is niet over te nemen en niet aan iemand anders te geven.** Zulke stappen dragen in het plan het kenmerk `separation`. Dat zijn: de interne beoordeling van een offerte, het beoordelen en tekenen door de opdrachtgever, het advies van HR en van control op een vacature, het akkoord op een vacature, en het beoordelen van een tekst.

**De handeling zelf weigert het ook.**

| Handeling | Regel |
|---|---|
| Interne goedkeuring | Wie de offerte maakte of om de goedkeuring vroeg, keurt haar niet goed. De instelling die zelf goedkeuren toestaat blijft bestaan |
| Advies en akkoord op een vacature | De aanvrager wordt niet vastgelegd als degene die adviseerde of akkoord gaf op de eigen aanvraag. Vastleggen wat een ander besloot blijft mogelijk |
| Akkoord van de opdrachtgever | Wie de offerte maakte, tekent er niet voor als opdrachtgever |
| Een tekst beoordelen | Alleen een genoemde beoordelaar oordeelt; de schrijver kan niet de enige beoordelaar zijn. Dit gold al |

**Voor de overige stappen** geldt: een stap van een recht in grip (planner, tekenbevoegde, interne goedkeurder) neemt alleen over wie dat recht heeft. Een stap van de eigenaar, een manager of de maker neemt alleen over wie de opdracht zelf mag wijzigen; mogen bemensen is niet genoeg. Een stap op een vacature neemt alleen over wie de vacature mag bewerken. Een stap die op iemand buiten grip wacht, is niet over te nemen.

**Wie aan zet is volgt dezelfde regels.** De zin in de kop en de lijst Taken zeggen niet tegen iemand dat zij moet doen wat de handeling haar weigert: wie de offerte maakte of de goedkeuring vroeg en zelf het recht interne goedkeurder heeft, leest dat een ander beslist, en als er geen ander is, wie het recht kan toekennen. Omgekeerd wacht niemand op een ander voor wat zij zelf mag: een rol invullen is ook de zet van wie de opdracht mag bemensen (de eigenaar of een manager), niet alleen van een planner. Dat is geen overnemen; de stap is dan gewoon ook van haar.

## Gevolgen

- Het overnemen blijft zichtbaar en terug te draaien: de taak zegt van wie ze is overgenomen en de oorspronkelijke eigenaar kan haar terugnemen.
- Een organisatie met maar een persoon die mag goedkeuren en die ook offertes maakt, loopt vast tot er een tweede is of de instelling voor zelf goedkeuren aan staat. Het scherm zegt dan wie het recht kan toekennen.
- Een nieuwe stap in het plan waar een ander moet beslissen krijgt het kenmerk `separation`, en de service van die handeling dwingt de scheiding zelf af. Een test loopt de gemarkeerde stappen na.
- De toegangsmatrix in `docs/toegang.md` noemt de scheiding als nadere regel.
