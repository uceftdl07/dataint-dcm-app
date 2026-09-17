# Page Compute › Recommandations & Forecast — Spec V1

> Page fille de **Compute**, route `Databricks > Compute > Recommandations & Forecast`.
> Issue du découpage de l'ancienne page unique `Compute`. Vue transverse : agrège les recommandations et
> les projections des deux autres pages filles (Clusters, SQL Warehouses).
> Maquette : `dcm-compute-recommendations-forecast.html`.

---

## 1. Positionnement dans la navigation

```
Databricks > Compute > Recommandations & Forecast
```
Item de nav avec **badge de comptage** = nombre de recommandations au statut `OPEN` (actuellement 9), visible sans avoir à cliquer.

---

## 2. Structure de la page

Pas de sous-onglets : une seule vue, structurée en 3 blocs verticaux.

### 2.1 KPI cards

| KPI | Calcul |
|---|---|
| Reco ouvertes | `count(status='OPEN')` sur `gold_dbx_compute_recommendations`, clusters + warehouses |
| Économies potentielles | `sum(estimated_savings_usd)` sur les reco ouvertes chiffrables |
| Résolues (30j) | `count(status='RESOLVED' AND last_seen_date >= today-30)` |
| Sévérité haute | `count(status='OPEN' AND severity='HIGH')` |

### 2.2 Table des recommandations

Source : `gold_dbx_compute_recommendations` (socle réactif unifié clusters + warehouses).

Colonnes : Objet (`object_name`), Catégorie, Titre, Sévérité, Économie estimée, Statut, Depuis (`first_seen_date`).

Filtres : Tous / Clusters / Warehouses (`object_type`) · catégorie (FinOps / Rightsizing / Governance / Reliability) · sévérité (Low/Medium/High).

**Contrat d'interaction** : chaque ligne est cliquable → ouvre un **mini-drawer** (résumé objet + reco) avec un CTA *"Ouvrir la fiche [cluster|warehouse] complète →"* qui renvoie vers la page fille correspondante (`Compute > Clusters` ou `Compute > SQL Warehouses`).
> Différence avec la V1 mono-page : à l'époque, cliquer sur une ligne ouvrait directement le drawer complet de l'objet (fiche d'identité + KPIs + tendance + historique) car tout vivait sur la même page. Avec l'architecture multi-pages, la page Reco & Forecast n'a plus accès aux données complètes de l'objet (coût 90j détaillé, id-card, etc.) : elle affiche un résumé (catégorie, sévérité, économie, ancienneté) et renvoie vers la page dédiée pour le détail complet. À valider en revue UX — alternative possible : dupliquer les données objet nécessaires pour garder un drawer complet ici aussi, au prix d'une redondance de données front.

### 2.3 Moteur de recommandations — les 9 règles actives en V1

| # | Règle | Objet | Catégorie | Source |
|---|---|---|---|---|
| 1 | `efficiency.utilization_status='OVER'` | CLUSTER | RIGHTSIZING | `cluster_efficiency_daily` |
| 2 | `efficiency.is_zombie=true` | CLUSTER | FINOPS | `cluster_efficiency_daily` |
| 3 | `governance.has_auto_termination=false` | CLUSTER | FINOPS | `compute_clusters` |
| 4 | `governance.has_owner_tag=false` | CLUSTER | GOVERNANCE | `cluster_governance` |
| 5 | `governance.dbr_is_lts_current=false` | CLUSTER | GOVERNANCE | `cluster_governance` |
| 6 | `warehouse.has_auto_stop=false` | WAREHOUSE | FINOPS | `compute_warehouses` |
| 7 | `query_perf.queue_time_p95_ms > seuil` | WAREHOUSE | RIGHTSIZING | `warehouse_query_performance_daily` |
| 8 | `query_perf.failure_rate_pct > seuil` | WAREHOUSE | RELIABILITY | `warehouse_query_performance_daily` |
| 9 | `query_perf.spill_query_count > seuil` | WAREHOUSE | RIGHTSIZING | `warehouse_query_performance_daily` |
| ~~10~~ | ~~`utilization.utilization_status='OVER'`~~ | WAREHOUSE | RIGHTSIZING | ❌ V2 — nécessite `warehouse_utilization_daily` |

**Point ouvert** (reporté depuis la spec V1 globale) : pas de règle côté cluster `UNDER` (sous-dimensionné) — à trancher avec le PO : angle mort assumé, ou 11e règle à construire ?

### 2.4 Widget Forecast

Projections issues de `gold_dbx_compute_forecast_daily` (méthode `ai_forecast`), sélecteur de métrique + graphique historique/prévision avec bande de confiance.

**5/5 métriques actives en V1** (conformément à la table gold) :

| Métrique | `metric_name` | Objet |
|---|---|---|
| Coût total | `cost_usd` | LZ / cluster / warehouse |
| DBU consommés | `dbu_quantity` | clusters + warehouses |
| CPU p95 moyen | `cpu_util_p95_pct` | clusters |
| Volume de requêtes | `query_count` | warehouses |
| Queue time p95 | `queue_time_p95_ms` | warehouses |

> **Correction apportée par rapport à la première maquette** : le sélecteur n'exposait que 3 métriques (coût, CPU, queue time) alors que la spec V1 annonce 5/5 métriques actives. La maquette dédiée à cette page corrige l'écart en ajoutant `dbu_quantity` et `query_count` au sélecteur.

---

## 3. Ce qui n'est PAS sur cette page (V2)

| Élément | Blocage |
|---|---|
| 10e règle reco (warehouse `UNDER`) | dépend de `warehouse_utilization_daily`, cf. `Compute_V2_Spec_DataEng.md` chantier 2 |
| Projection de `idle_pct` / `unexpected_termination_count` | ces métriques n'existent pas encore en gold (dépendent des chantiers V2) |

---

## 4. Filtres globaux (topbar, communs aux 3 pages filles)

Landing zone · cloud provider · workspace · plage de dates (30j/90j/6m/1an).

---

## 5. Contrat de données (rappel)

`gold_dbx_compute_recommendations` — grain `(recommendation_id)`, `recommendation_id = sha2(object_type || object_id || category || generated_date)`, rafraîchissement quotidien (materialized view, règles à seuils).
`gold_dbx_compute_forecast_daily` — grain `(cloud_provider, source_lz_id, object_type, object_id, metric_name, horizon_date)`, job SQL `ai_forecast`, rafraîchissement quotidien/hebdo.

---

## 6. Contrat d'interaction des filtres (maquette fonctionnelle)

La maquette `dcm-compute-recommendations-forecast.html` filtre réellement le tableau de recommandations, avec **3 filtres combinables entre eux** (ET logique) :

| Contrôle | Comportement |
|---|---|
| Pills Tous / Clusters / Warehouses | Filtre exact sur `object_type` |
| Select catégorie | Filtre exact sur `category` (FinOps / Rightsizing / Governance / Reliability) |
| Select sévérité | Filtre exact sur `severity` (Low / Medium / High) |

Un message "Aucune recommandation ne correspond à ce filtre" s'affiche si la combinaison ne renvoie aucune ligne. Le widget Forecast (sélecteur de métrique) reste indépendant de ces filtres — il n'est pas croisé avec le tableau de recommandations dans cette itération.

**Correctif technique appliqué** (partagé avec les 2 autres pages filles) : ajout de `.subpanel[hidden]{display:none;}` dans la feuille de style commune — sans impact direct sur cette page (elle n'a pas de sous-onglets), mais nécessaire pour que Clusters et SQL Warehouses fonctionnent correctement puisque les 3 pages partagent le même bloc CSS.

