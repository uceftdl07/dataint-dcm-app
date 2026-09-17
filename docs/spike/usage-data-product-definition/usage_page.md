# Feature Usage Data Product — Description fonctionnelle

## Le problème adressé

Les Landing Zones du groupe publient des dizaines de **data products** (tables et schémas gouvernés dans Unity Catalog : couches curated / gold, datasets exposés aux consommateurs data). Aujourd'hui, personne ne sait objectivement **qui consomme quoi, à quelle fréquence, pour quel volume et à quel coût**. Les questions restent sans réponse factuelle : quels data products sont réellement utilisés ? Lesquels sont abandonnés (candidats à la dépréciation) ? Qui sont les gros consommateurs ? Un dataset est-il encore frais quand on le lit ? Combien coûte l'exploitation d'un data product ?

Résultat : dépréciations à l'aveugle (risque de casser un consommateur non identifié), data products « zombies » maintenus sans usage, aucune base de refacturation, et impossibilité de prioriser les efforts de qualité/optimisation sur les datasets qui comptent.

DCM apporte une **couche d'observabilité de l'usage des data products, unifiée, multi-cloud et multi-LZ**, alimentée par les **system tables Databricks** (Unity Catalog : `access.audit`, `access.table_lineage`, `query.history`, `billing.usage`) — données réelles d'accès, pas d'agent intrusif ni de déclaratif.

## Ce que la feature apporte concrètement

### 1. Popularité & adoption
- Vue consolidée du **nombre de lectures, de consommateurs distincts et de requêtes** par data product, LZ et cloud.
- Classement des data products les plus / moins utilisés → identifier les datasets phares et les datasets morts.
- Ventilation par **type de consommateur** (utilisateur, service principal, job, dashboard, notebook, pipeline) via le lineage.

### 2. Consommateurs & dépendances
- Qui consomme un data product (top consommateurs par lectures / requêtes / volume).
- **Fan-out downstream** : combien d'objets (jobs, dashboards, tables dérivées) dépendent d'un data product → mesure du risque de dépréciation.
- Base factuelle de **refacturation / responsabilisation** par consommateur, équipe et cloud.

### 3. Fraîcheur & fiabilité de la donnée servie
- Dernière écriture (fraîcheur) vs dernière lecture (usage) → détecter la **donnée périmée encore consommée**.
- Data products lus mais jamais rafraîchis (pipeline amont cassé) → alerte qualité.
- Taux d'échec des accès (droits manquants, table absente) via `access.audit`.

### 4. Coût & FinOps de la donnée
- Coût d'exploitation attribuable à un data product (compute des requêtes qui le lisent), en $ et DBU.
- Coût par requête, coût par consommateur → détecter les consommateurs / usages les plus chers.

### 5. Gouvernance & cycle de vie
- **Data products inutilisés** (aucune lecture sur N jours) → candidats à la dépréciation / suppression.
- Data products **orphelins** (sans tag owner / domaine / cost-center) → refacturation impossible.
- Data products **sans consommateur connu** vs data products **critiques** (fort fan-out).

## Bénéfices par persona

| Persona | Ce que DCM lui apporte |
|---|---|
| **Data Product Owner** | Sait qui utilise son produit, mesure l'adoption, décide dépréciation sur des faits |
| **Data Platform Lead / FinOps** | Coût par data product / consommateur, refacturation, ménage des datasets morts |
| **Data Engineer / Producteur** | Repère la donnée périmée encore lue, priorise la qualité sur les datasets utilisés |
| **Consommateur data (analyste)** | Découvre les data products populaires et fiables, évite les datasets abandonnés |
| **Gouvernance / Sécurité** | Data products orphelins/non taggés, accès en échec, conformité du catalogue |

## Positionnement dans DCM

Cette feature étend le monitoring DCM de la couche **compute** (clusters + warehouses) vers la couche **donnée servie** : elle observe l'usage des **data products** exposés dans Unity Catalog, en cohérence avec le domaine `usage` du modèle de données et avec la table de service existante `gold_data_product_usage`. Elle enrichit la promesse multi-cloud / multi-LZ de la plateforme avec une dimension **adoption + valeur + cycle de vie** de la donnée, actionnable.

---

## Légendes

**Personas** : `OWN` = Data Product Owner · `FIN` = FinOps / Data Platform Lead · `DE` = Data Engineer / Producteur · `AN` = Consommateur data · `GOV` = Gouvernance / Sécurité

**Mode d'usage** :
- `R` (**Réactif**) = état courant → alerte / action immédiate (ex. data product périmé encore lu, accès en échec, dataset orphelin).
- `P` (**Prédictif**) = série temporelle → anticipation par tendance / saisonnalité (ex. déclin d'usage, montée de charge sur un data product).
- `R+P` = exploitable dans les deux modes selon l'agrégation.

**Définition d'un data product** : objet Unity Catalog gouverné exposé à la consommation — une **table** (ou vue matérialisée) des couches curated/gold, identifiée par un tag catalogue (`data_product`, `domain`, `owner`) ou par appartenance à un schéma/catalogue publié. Le **registre** des data products provient de `system.information_schema` + tags (cf. data model §1.4).

---

## Page 1 — Data Products (vue produit)

### Popularité / adoption
| Indicateur | Détail | Source system table | Persona | Mode | Reco / action générée |
|---|---|---|---|---|---|
| Nb lectures | accès en lecture par data product / jour, tendance | `system.access.table_lineage` (target=DP) | OWN, FIN | R+P | Prévoir la charge ; détecter un déclin d'adoption |
| Consommateurs distincts | nb d'identités uniques (user/SP/job) | `table_lineage.created_by` / `access.audit.user_identity` | OWN, GOV | R+P | Mesurer l'adoption réelle ; alerter si → 0 |
| Nb requêtes | requêtes touchant le data product | `system.query.history` (via lineage) | OWN, AN | R+P | Prioriser qualité/perf sur les DP les plus interrogés |
| Rang popularité | classement global par lectures | dérivé `table_lineage` | OWN, FIN | R+P | Top N = datasets phares ; bottom N = candidats dépréciation |
| Répartition par type consommateur | user / SP / job / dashboard / notebook / pipeline | `table_lineage.entity_type` | OWN, GOV | R | Comprendre l'usage (interactif vs industrialisé) |

### Fraîcheur / fiabilité
| Indicateur | Détail | Source | Persona | Mode | Reco / action générée |
|---|---|---|---|---|---|
| Dernière écriture (fraîcheur) | dernier write sur la table | `table_lineage` (target write) / `information_schema` | DE, OWN | R | Alerter si fraîcheur > SLA |
| Dernière lecture (usage) | dernier accès en lecture | `table_lineage` / `access.audit` | OWN | R | Base de la détection « inutilisé » |
| Donnée périmée encore lue | fraîcheur ancienne MAIS lectures récentes | dérivé (écart write vs read) | DE, OWN | R | Corriger le pipeline amont / prévenir les consommateurs |
| Taux d'échec d'accès | accès refusés / table absente | `access.audit.response` | GOV, DE | R | Corriger droits / migration ; alerter |

### Coût / FinOps
| Indicateur | Détail | Source | Persona | Mode | Reco / action générée |
|---|---|---|---|---|---|
| Coût $ attribué au data product | compute des requêtes qui le lisent | `query.history` × `billing.usage` × `list_prices` | FIN, OWN | R+P | Forecast coût ; cibler les DP les plus chers |
| DBU consommés | idem en DBU | `billing.usage` | FIN | R+P | Dérive de consommation |
| Coût par requête moyen | coût / nb requêtes | dérivé | FIN, OWN | R+P | Détecter un usage inefficient d'un DP |
| Volume lu (bytes / rows) | données lues par jour | `query.history.read_bytes/read_rows` | FIN, DE | R+P | Efficience I/O ; pruning/partitionnement en amont |

### Gouvernance / cycle de vie
| Contrôle | Source | Persona | Mode | Reco / action générée |
|---|---|---|---|---|
| Data product inutilisé (0 lecture sur N jours) | `table_lineage` (absence) | OWN, FIN, GOV | R | Proposer dépréciation / suppression |
| Data product orphelin (sans owner/domaine/cost-center) | `information_schema.table_tags` | GOV, FIN | R | Imposer les tags ; rendre la refacturation possible |
| Data product critique (fort fan-out) | `table_lineage` downstream | OWN, GOV | R | Protéger ; interdire dépréciation sans plan |
| Data product sans consommateur connu | `table_lineage` | OWN | R | Investiguer (produit non promu ou mort) |

---

## Page 2 — Consommateurs (vue usage)

### Classement & refacturation
| Indicateur | Détail | Source | Persona | Mode | Reco / action générée |
|---|---|---|---|---|---|
| Top consommateurs | par lectures / requêtes / volume / coût | `table_lineage` + `query.history` + `billing.usage` | FIN, OWN | R+P | Refacturation ; sensibiliser les gros consommateurs |
| Data products consommés par identité | largeur d'usage d'un consommateur | `table_lineage.created_by` | OWN, GOV | R | Comprendre les dépendances d'une équipe |
| Coût par consommateur | $ attribué par identité / équipe | `billing.usage` + lineage | FIN | R+P | Budget par équipe ; détecter dérive |
| Type d'usage (interactif vs job) | entity_type de la consommation | `table_lineage.entity_type` | OWN, DE | R | Distinguer ad-hoc vs production |

### Performance d'accès (côté consommation)
| Indicateur | Détail | Source | Persona | Mode | Reco / action générée |
|---|---|---|---|---|---|
| Latence des requêtes sur le DP | p50/p95 durée totale | `query.history.total_duration_ms` | AN, DE | R+P | Tuning / matérialisation si lectures lentes fréquentes |
| Volume scanné par requête | bytes/rows lus | `query.history` | DE | R+P | Partitionnement / Z-order en amont du DP |
| Taux d'échec requêtes | FAILED/CANCELED sur le DP | `query.history.execution_status` | DE, AN | R | Corriger requêtes / droits / timeouts |

---

## Synthèse Réactif vs Prédictif

**Socle réactif (alerting état courant)** — déclenche une action immédiate :
- Data product inutilisé, orphelin (tags manquants), donnée périmée encore lue, accès en échec, data product critique menacé de dépréciation.
- Valeur : nettoyer le catalogue et sécuriser les dépréciations *maintenant*, sans casser de consommateur.

**Socle prédictif (séries temporelles agrégées)** — anticipe par tendance :
- Trajectoire des lectures et du nombre de consommateurs (déclin d'adoption = candidat dépréciation ; montée = besoin de robustesse), coût $ attribué (forecast budget), volume scanné (dimensionnement amont).
- Valeur : arbitrer le cycle de vie et le coût des data products *avant* la dérive.

> Recommandation : historiser au grain **jour × data product × consommateur** dès le MVP (aligné sur la table existante `gold_data_product_usage`) pour rendre le prédictif possible sans re-collecte. Les états courants (registre, fraîcheur, gouvernance) gardent le dernier état connu.
