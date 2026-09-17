# Feature Compute Monitoring — Description fonctionnelle

## Le problème adressé

Les équipes data platform (DataHub, produits digitaux data) opèrent des dizaines de clusters et SQL warehouses Databricks répartis sur plusieurs Landing Zones et clouds. Aujourd'hui la visibilité est fragmentée : chaque LZ regarde ses propres consoles Databricks, sans vue consolidée coût / usage / fiabilité. Résultat : gaspillage invisible (clusters idle, warehouses surdimensionnés), dérive de coût non maîtrisée, et aucune base factuelle pour arbitrer le rightsizing.

DCM apporte une **couche d'observabilité compute unifiée, multi-cloud et multi-LZ**, alimentée par les system tables Databricks (données réelles, pas d'agent intrusif).

## Ce que la feature apporte concrètement

### 1. Maîtrise des coûts (FinOps)
- Vue consolidée du coût réel du compute ($ et DBU) par cluster, warehouse, équipe, LZ et cloud.
- Identification immédiate des postes les plus coûteux et de leur tendance.
- Ventilation par tag/owner → **refacturation et responsabilisation** des équipes.
- Estimation du **gaspillage récupérable** (idle, sur-provisionnement) en euros.

### 2. Optimisation / rightsizing
- Mesure factuelle de l'utilisation CPU/mémoire (moyenne + p95) → détecte le sous et le sur-dimensionnement.
- Repère les clusters "zombie", warehouses sans auto-stop, node types surdimensionnés.
- Recommandations d'actions concrètes (réduire la taille, activer l'auto-stop, migrer serverless).

### 3. Fiabilité & performance
- Suivi de la disponibilité, des temps de démarrage, des terminaisons inattendues des clusters.
- Latence des requêtes (p50/p95/p99), temps de file d'attente, taux d'échec sur les warehouses.
- Détection des goulots (queue, spill disque, cache faible) qui dégradent l'expérience utilisateur data.

### 4. Gouvernance
- Contrôle du respect des standards (tags obligatoires, auto-termination, versions DBR à jour).
- Inventaire des ressources inactives candidates à la suppression.

## Bénéfices par persona

| Persona | Ce que DCM lui apporte |
|---|---|
| **Data Platform Lead / FinOps** | Vision coût consolidée, arbitrage rightsizing, budget maîtrisé |
| **Data Engineer** | Comprend l'efficience de ses clusters, tune ses jobs, réduit les latences |
| **Analyste / consommateur SQL** | Warehouses dimensionnés justes → requêtes rapides et fiables |
| **Gouvernance / Sécurité** | Conformité aux standards compute, ressources orphelines identifiées |

## Positionnement dans DCM

Cette feature étend le monitoring DCM au-delà des pipelines : elle couvre désormais la **couche compute** (clusters + SQL warehouses), en cohérence avec le domaine `compute` du modèle de données, et enrichit la promesse multi-cloud / multi-LZ de la plateforme avec une dimension **coût + efficience + fiabilité** actionnable.

---

## Légendes

**Personas** : `FIN` = FinOps / Data Platform Lead · `DE` = Data Engineer · `AN` = Analyste / consommateur SQL · `GOV` = Gouvernance / Sécurité

**Mode d'usage** :
- `R` (**Réactif**) = état courant → alerte / action immédiate (ex. cluster idle maintenant, query en échec).
- `P` (**Prédictif**) = série temporelle → anticipation par tendance / saisonnalité / seuil projeté (ex. dérive de coût, pic de charge à venir).
- `R+P` = exploitable dans les deux modes selon l'agrégation.

---

## Page 1 — Clusters (all-purpose + job compute)

### FinOps / Coût
| Indicateur | Détail | Source system table | Persona | Mode | Reco d'optimisation générée |
|---|---|---|---|---|---|
| DBU consommés | par jour/cluster/LZ, tendance | `system.billing.usage` | FIN, DE | R+P | Prévision de consommation ; alerte si projection > budget |
| Coût estimé $ | usage × list_price | `usage` × `system.billing.list_prices` | FIN | R+P | Forecast dépense fin de mois ; détection dérive |
| Coût par équipe/tag | ventilation `custom_tags` / owner | `usage.custom_tags` + `system.compute.clusters` | FIN, GOV | R | Refacturation ; cibler l'équipe la plus dépensière |
| Top N clusters coûteux | classement + delta vs période précédente | `usage` | FIN, DE | R+P | Prioriser le rightsizing sur ces clusters |
| Split DBU photon/serverless/classic | par SKU | `usage.sku_name` | FIN, DE | R | Migrer classic→serverless/photon si moins cher à charge égale |

### Utilisation / Efficience (le cœur rightsizing)
| Indicateur | Détail | Source | Persona | Mode | Reco d'optimisation générée |
|---|---|---|---|---|---|
| CPU util % moyen/p95 | user+system, détecte sous/sur-provision | `system.compute.node_timeline` | DE, FIN | R+P | Réduire node type si p95 < 40 % ; agrandir si p95 > 85 % |
| Mem util % moyen/p95 | pression mémoire | `node_timeline` | DE | R+P | Passer sur node memory-optimized si p95 mem > 85 % |
| Idle % | temps RUNNING sans requête = gaspillage | `node_timeline` + `system.query.history` | FIN, DE | R+P | Baisser auto-termination ; alerte idle > seuil = $ récupérable |
| CPU wait % | I/O bound | `node_timeline` | DE | R | Optimiser I/O / partitionnement ; node I/O-optimized |
| Clusters "zombie" | up longtemps, util basse | dérivé node_timeline | FIN, DE | R | Éteindre / activer auto-stop immédiatement |
| Autoscaling efficacité | workers actifs vs max, oscillation | `node_timeline` + `clusters` | DE | R+P | Ajuster min/max workers ; lisser l'oscillation |

### Fiabilité / Activité
| Indicateur | Détail | Source | Persona | Mode | Reco d'optimisation générée |
|---|---|---|---|---|---|
| Uptime / heures actives | par cluster | `node_timeline` / `clusters` | FIN, DE | R+P | Détecter clusters allumés en continu sans besoin |
| Nb démarrages, temps startup | latence spin-up | `clusters` (SCD) + audit | DE | R+P | Pré-chauffer (pools) si spin-up récurrent lent |
| Terminaisons inattendues | cause termination | `system.compute.clusters` (`termination_reason` via audit) | DE, GOV | R | Alerter sur échecs (quota, spot eviction) ; corriger config |
| Auto-termination configuré | % clusters sans auto-stop = risque coût | `clusters.auto_termination_minutes` | FIN, GOV | R | Imposer auto-stop par policy sur clusters non conformes |

### Gouvernance / rightsizing (recommandations)
| Contrôle | Source | Persona | Mode | Reco d'optimisation générée |
|---|---|---|---|---|
| Clusters sans tag owner/coût-center | `system.compute.clusters` | GOV, FIN | R | Bloquer / taguer ; rendre la refacturation possible |
| DBR obsolète (LTS non à jour) | `clusters` | GOV, DE | R | Planifier montée de version (sécu + perf) |
| Node type surdimensionné vs util p95 | `clusters` + `node_types` + `node_timeline` | FIN, DE | R+P | Recommander node cible ; estimer $ économisés |
| Single-node vs util réelle | `clusters` + `node_timeline` | DE | R | Basculer single↔multi-node selon charge |

---

## Page 2 — SQL Warehouses

### FinOps / Coût
| Indicateur | Détail | Source | Persona | Mode | Reco d'optimisation générée |
|---|---|---|---|---|---|
| DBU + coût $ par warehouse | dépense par warehouse | `usage` × `list_prices` | FIN | R+P | Forecast coût ; alerte dérive budget |
| Coût par requête moyen | usage / nb queries | `usage` + `system.query.history` | FIN, AN | R+P | Détecter inflation du coût/query ; tuning ciblé |
| Coût par utilisateur/équipe | ventilation | `query.history.executed_by` + tags | FIN, GOV | R | Refacturation ; sensibiliser gros consommateurs |

### Utilisation / Efficience
| Indicateur | Détail | Source | Persona | Mode | Reco d'optimisation générée |
|---|---|---|---|---|---|
| Idle % | RUNNING sans query | `system.compute.warehouse_events` | FIN | R+P | Réduire auto-stop ; $ récupérable estimé |
| Auto-stop config | warehouses sans auto-stop | `system.compute.warehouses` | FIN, GOV | R | Imposer auto-stop par policy |
| Scaling events | scale up/down, taille cluster | `warehouse_events` | DE, FIN | R+P | Ajuster min/max clusters ; réduire oversizing |
| Peak concurrency | requêtes simultanées vs max clusters | `query.history` | DE, AN | P | Anticiper saturation ; planifier montée de concurrence |
| Ratio actif/allumé | heures query / heures RUNNING | `warehouse_events` + `query.history` | FIN | R+P | Cible >70 % ; sinon réduire taille/auto-stop |

### Performance requêtes (fort valeur data platform)
| Indicateur | Détail | Source | Persona | Mode | Reco d'optimisation générée |
|---|---|---|---|---|---|
| Latence p50/p95/p99 | durée totale query | `system.query.history` | AN, DE | R+P | Détecter dégradation ; tuning ou upsize ciblé |
| Queue time | temps d'attente = sous-dimension | `query.history` | AN, DE, FIN | R+P | Si queue ↑ → +clusters (scaling) ; anticiper pics |
| Volume queries | par warehouse/jour | `query.history` | FIN, AN | P | Prévoir charge ; dimensionner à l'avance |
| Taux échec | queries FAILED/CANCELED | `query.history.execution_status` | DE, AN | R | Alerter ; corriger requêtes / droits / timeout |
| Spill disk/mem | requêtes lourdes mal tunées | `query.history` | DE | R | Réécrire query ; upsize ; broadcast/partition |
| Cache hit % | efficacité cache | `query.history` | DE, AN | R+P | Réordonner charges ; garder warehouse chaud si rentable |
| Top queries lentes/coûteuses | drill-down par user | `query.history` | DE, AN | R | Tuning prioritaire des requêtes phares |
| Bytes/rows scannés | data efficiency | `query.history` | DE | R+P | Pruning/partitionnement ; Z-order/liquid clustering |

---

## Synthèse Réactif vs Prédictif

**Socle réactif (alerting temps quasi réel)** — état courant, déclenche action immédiate :
- Cluster idle / zombie, warehouse sans auto-stop, terminaisons inattendues, taux d'échec queries, spill, tags manquants, DBR obsolète.
- Valeur : coupe le gaspillage et les incidents *maintenant*.

**Socle prédictif (séries temporelles agrégées)** — anticipe par tendance / saisonnalité :
- Trajectoire DBU & coût $ (forecast budget), util CPU/mem p95 (rightsizing anticipé), volume queries & peak concurrency (dimensionnement proactif), queue time (saturation à venir).
- Valeur : arbitrer *avant* la dérive de coût ou la dégradation de perf.

> Recommandation : historiser au grain jour/heure les champs `R+P` et `P` dès le MVP pour rendre le prédictif possible sans re-collecte. Les champs purement `R` peuvent rester au dernier état connu.