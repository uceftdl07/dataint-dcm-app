# Page Compute › SQL Warehouses — Spec V1

> Page fille de **Compute**, route `Databricks > Compute > SQL Warehouses`.
> Issue du découpage de l'ancienne page unique `Compute`.
> Maquette : `dcm-compute-warehouses.html`.

---

## 1. Positionnement dans la navigation

```
Databricks > Compute > SQL Warehouses
```
(cf. `Compute_Clusters_Spec.md` §1 pour l'arborescence complète)

---

## 2. Sous-vues (4)

| Sous-vue | Table gold | KPI cards | Colonnes tableau | Filtres locaux | Persona |
|---|---|---|---|---|---|
| **Overview** | agrégat `warehouse_cost_daily` + `warehouse_query_performance_daily` | Coût total, Warehouses actifs, Requêtes exécutées, Requêtes en échec, Reco ouvertes | nom, taille, coût, requêtes, failure rate, latence p95 | — | Tous |
| **Cost** | `gold_dbx_compute_warehouse_cost_daily` | Coût période (Δ%), Coût/requête moyen, Top consommateur | warehouse, taille, dbu, coût, Δ, requêtes, coût/requête | taille, tri coût | PO Data, FinOps |
| **Query performance** | `gold_dbx_compute_warehouse_query_performance_daily` | Failure rate moyen, Latence p95 moyenne, Queue time p95, Requêtes avec spill | warehouse, requêtes, failure%, p50/p95/p99, queue p95, spill, cache hit% | "avec échecs", "avec spill", seuil latence | Data Eng, DataOps |
| **Requêtes à investiguer** (drill-down non agrégé) | `warehouse_slow_queries` | — (liste directe) | statement_id, warehouse, exécuté par, début, durée, statut, raison (badge filtrable), lien "Ouvrir" vers query profile natif | raison (Échec/Lente/Spill), warehouse | Data Eng, DataOps |

**Bandeau explicatif** sur *Requêtes à investiguer* : le texte SQL (`statement_text`) n'est jamais affiché (sensibilité des données) — seul un lien de sortie vers le query profile natif Databricks est proposé. Décision actée, pas un point ouvert.

**Deux colonnes distinctes** sur cette même sous-vue : un badge **Raison** (catégorie filtrable : Timeout / Spill / Table introuvable...) et un texte court dérivé d'`error_message` — ne pas les fusionner, ça casserait le filtre par catégorie.

---

## 3. Moteur de recommandations — règles actives concernant les warehouses (4)

| Règle | Catégorie | Source |
|---|---|---|
| `warehouse.has_auto_stop=false` | FINOPS | `compute_warehouses` (config directe) |
| `query_perf.queue_time_p95_ms > seuil` | RIGHTSIZING | `warehouse_query_performance_daily` |
| `query_perf.failure_rate_pct > seuil` | RELIABILITY | `warehouse_query_performance_daily` |
| `query_perf.spill_query_count > seuil` | RIGHTSIZING | `warehouse_query_performance_daily` |

Consultables en détail sur la page **Recommandations & Forecast** ; ici, seul le compteur agrégé (KPI "Reco ouvertes") et le détail par objet dans le drawer sont affichés.

---

## 4. Ce qui n'est PAS sur cette page (V2)

| Élément | Blocage | Suivi |
|---|---|---|
| Sous-vue **Utilization** (idle%, ratio actif/running, événements de scaling) | `curated_dbx_compute_warehouse_events` n'existe pas (aucune collecte aujourd'hui) | Chantier 2 — voir `Compute_V2_Spec_DataEng.md` §Chantier 2 |
| Timeline scale-up/scale-down dans le drawer | idem | idem |
| Règle reco "warehouse `utilization_status='OVER'`" | dépend de `warehouse_utilization_daily` | idem — 10e règle du moteur, actuellement 9/10 actives (cf. page Recommandations & Forecast) |

Comme pour Clusters, aucune vue grisée "Bientôt disponible" n'est affichée : la sous-vue Utilization apparaîtra dans la nav uniquement une fois le chantier 2 livré.

---

## 5. Drawer détail warehouse

- **Fiche d'identité** : Taille, Auto-stop
- **KPIs rapides** : Requêtes, Failure rate, Latence p95, Cache hit
- **Tendance coût 90j** (sparkline)
- **Requêtes à investiguer liées** (liste filtrée sur ce warehouse, déjà livrée en V1 — pas besoin d'attendre le chantier 2 pour ce composant)
- **Recommandations liées** + CTA *"Voir dans Recommandations & Forecast →"*
- Pas de timeline d'événements (V2)

---

## 6. Filtres globaux (topbar)

Landing zone · cloud provider · workspace · plage de dates (30j/90j/6m/1an).

---

## 7. Contrat de données (rappel)

Grain des tables `*_daily` : `(cloud_provider, source_lz_id, workspace_id, warehouse_id, period_start)`. `warehouse_slow_queries` est la seule table à grain non-agrégé de cette page — clé `(cloud_provider, source_lz_id, workspace_id, warehouse_id, statement_id)`. Rafraîchissement quotidien best-effort, historique ≥30 jours croissant, lecture idempotente.

---

## 8. Contrat d'interaction des filtres (maquette fonctionnelle)

La maquette `dcm-compute-warehouses.html` filtre réellement les tableaux (logique JS côté client sur données mockées).

| Sous-vue | Contrôle | Comportement |
|---|---|---|
| Cost | Select taille | Filtre exact sur `warehouse_size` (Small / Medium / Large) |
| Cost | Select tri | Réordonne les lignes par `cost_usd` décroissant ou par nom |
| Query performance | Pills "Avec échecs" / "Avec spill" | Combinables **ET** avec le seuil de latence (voir ligne suivante) |
| Query performance | Select seuil latence | Filtre `latency_p95_ms > seuil` (toutes / 10s / 30s) |
| Requêtes à investiguer | Pills raison (Échec / Lente / Spill) | Combinables **ET** avec le select warehouse |
| Requêtes à investiguer | Select warehouse | Filtre exact sur le warehouse concerné |
| Section (persiste entre les 4 sous-onglets, sous les tabs Overview/Cost/Query performance/Requêtes à investiguer — **pas dans la topbar globale**) | Select granularité (Jour/Semaine/Mois) | Ré-agrège la **tendance de coût affichée dans le drawer** (moyenne par groupe de 1/7/28 jours). Par défaut sur "Semaine". N'affecte ni les KPI cards ni les colonnes des tableaux |

**⚠️ Seuils posés par défaut pour la maquette, à faire valider avec le PO / Data Eng avant implémentation réelle** (aucun seuil n'était documenté dans la spec V1 d'origine) :
- "Avec échecs" = `failure_rate_pct ≥ 1 %` (choisi pour correspondre à la bascule badge-success → badge-warning/danger déjà utilisée dans le tableau — à confirmer que c'est le bon seuil métier, ou s'il doit être piloté par une config)
- "Avec spill" = `spill_query_count > 0` (tout warehouse ayant eu au moins une requête avec spill sur la période)

Un message "Aucun warehouse ne correspond à ce filtre" / "Aucune requête ne correspond à ce filtre" s'affiche si le filtre ne renvoie aucune ligne.

**Correctif technique appliqué** (partagé avec les 2 autres pages filles, même feuille de style) : ajout de `.subpanel[hidden]{display:none;}` pour que le changement de sous-onglet fonctionne réellement — la règle `.subpanel{display:flex}` empêchait l'attribut `hidden` de masquer les sous-vues inactives.

**Note technique — granularité** : même principe que sur la page Clusters — série "quotidienne" simulée sur 84 jours, agrégée côté client pour la démo. En implémentation réelle, l'agrégation par semaine/mois doit être portée par la requête backend (`date_trunc` sur `gold_dbx_compute_warehouse_cost_daily`), pas recalculée depuis le grain journalier côté frontend.