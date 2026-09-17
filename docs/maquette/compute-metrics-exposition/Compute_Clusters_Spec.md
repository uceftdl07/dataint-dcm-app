# Page Compute › Clusters — Spec V1

> Page fille de **Compute**, route `Databricks > Compute > Clusters`.
> Issue du découpage de l'ancienne page unique `Compute` (V1 mélangeait Clusters + SQL Warehouses + Recommandations & Forecast dans 3 onglets d'une même page — cf. décision de scission en pages filles).
> Maquette : `dcm-compute-clusters.html`.

---

## 1. Positionnement dans la navigation

```
Databricks
 ├─ Overview
 ├─ Jobs & Pipelines
 ├─ Compute
 │   ├─ Clusters                     ← cette page
 │   ├─ SQL Warehouses
 │   └─ Recommandations & Forecast
 ├─ FinOps
 └─ Usage Data Product
```

`Compute` n'est plus une page cliquable en elle-même : c'est un groupe de navigation qui expose ses 3 pages filles (cohérent avec le pattern déjà utilisé pour `Anomalies > Rules / Reports`).

---

## 2. Sous-vues (4)

| Sous-vue | Table gold | KPI cards | Colonnes tableau | Filtres locaux | Persona |
|---|---|---|---|---|---|
| **Overview** | agrégat `cluster_cost_daily` + `cluster_efficiency_daily` + `cluster_governance` | Coût total (Δ%), Clusters actifs, Zombies, Reco ouvertes | nom, LZ, coût, CPU p95, idle%, statut util., gouvernance | — | Tous |
| **Cost** | `gold_dbx_compute_cluster_cost_daily` | Coût période (Δ%), DBU consommés, Top coûteux | cluster, sku_group, dbu, coût, Δ vs J-1, rang LZ | recherche texte, sku_group, tri coût | PO Data, FinOps |
| **Efficiency** | `gold_dbx_compute_cluster_efficiency_daily` | CPU p95 moyen, Mem p95 moyen, Zombies, Économies estimées | cluster, cpu_p95, mem_p95, idle%, statut util., node recommandé, économie | statut util. (Sur-dim. / Sous-dim. / Optimal) | Data Eng |
| **Governance** | `gold_dbx_compute_cluster_governance` | Tags manquants, DBR obsolète, Sans auto-termination, Sévérité haute | cluster, owner tag, cost-center tag, DBR (+LTS?), auto_termination_minutes, action recommandée, sévérité | sévérité, "tags manquants", "DBR obsolète", "sans auto-stop" | SysOps, PO Data |

> `has_auto_termination` / `auto_termination_minutes` restent dans **Governance** (config directe issue de `compute_clusters`), pas dans une vue Reliability — cette dernière n'existe pas sur cette page (cf. §4).

---

## 3. Moteur de recommandations — règles actives concernant les clusters (5)

| Règle | Catégorie | Source |
|---|---|---|
| `efficiency.utilization_status='OVER'` | RIGHTSIZING | `cluster_efficiency_daily` |
| `efficiency.is_zombie=true` | FINOPS | `cluster_efficiency_daily` |
| `governance.has_auto_termination=false` | FINOPS | `compute_clusters` (config directe) |
| `governance.has_owner_tag=false` | GOVERNANCE | `cluster_governance` |
| `governance.dbr_is_lts_current=false` | GOVERNANCE | `cluster_governance` |

Ces règles alimentent `gold_dbx_compute_recommendations` (`object_type='CLUSTER'`) et sont consultables en détail sur la page **Recommandations & Forecast**. La page Clusters n'affiche que le compteur agrégé (KPI "Reco ouvertes") et le détail par objet dans le drawer.

**Point ouvert (non tranché)** : aucune règle ne couvre aujourd'hui un cluster `utilization_status='UNDER'` (sous-dimensionné, risque de saturation) — angle mort assumé ou 6e règle à ajouter ? À valider avec le PO.

---

## 4. Ce qui n'est PAS sur cette page (V2)

| Élément | Blocage | Suivi |
|---|---|---|
| Sous-vue **Reliability** (démarrages, redémarrages, terminaisons anormales) | `curated_dbx_access_audit` n'expose ni `cluster_id`, ni statut de terminaison | Chantier 1 — voir `Compute_V2_Spec_DataEng.md` §Chantier 1 |
| Timeline d'événements cluster dans le drawer | idem | idem |
| Règle reco "cluster sous-dimensionné" | dépend du point ouvert §3 | À trancher indépendamment du chantier data |

Contrairement à la V1 mélangée, cette page ne montre **aucune vue grisée "Bientôt disponible V2"** : tant que la donnée n'est pas prête, la sous-vue n'existe simplement pas dans la nav. Le retour V2 se fera par un déploiement de la 5e sous-vue une fois le chantier livré.

---

## 5. Drawer détail cluster

Ouvert au clic sur une ligne de n'importe quelle sous-vue.

- **Fiche d'identité** : Landing zone, Owner, Cost-center, DBR, Node type, Auto-termination
- **KPIs rapides** : CPU p95, Mem p95, Idle %, Statut
- **Tendance coût 90j** (sparkline)
- **Recommandations liées** (0..n, avec sévérité + catégorie) + CTA *"Voir dans Recommandations & Forecast →"* qui renvoie vers la page dédiée (nouveau contrat d'interaction : dans l'ancienne V1 mono-page, ce lien pointait vers un onglet ; il pointe désormais vers une page distincte)
- Pas de timeline d'événements (V2)

---

## 6. Filtres globaux (topbar)

Landing zone · cloud provider · workspace · plage de dates (30j/90j/6m/1an).

---

## 7. Contrat de données (rappel)

Grain des tables `*_daily` : `(cloud_provider, source_lz_id, workspace_id, cluster_id, period_start)`. `cluster_governance` est un snapshot (dernier `change_time`), pas un grain journalier. Rafraîchissement quotidien best-effort, historique ≥30 jours croissant, lecture idempotente.

---

## 8. Contrat d'interaction des filtres (maquette fonctionnelle)

La maquette `dcm-compute-clusters.html` filtre désormais réellement les tableaux au clic/à la saisie (logique JS côté client sur données mockées ; en implémentation réelle, ces filtres deviendront des paramètres de requête envoyés au backend).

| Sous-vue | Contrôle | Comportement |
|---|---|---|
| Cost | Champ recherche | Filtre par sous-chaîne sur le nom du cluster (insensible à la casse) |
| Cost | Select SKU | Filtre exact sur `sku_group` (Classic / Photon / Serverless) |
| Cost | Select tri | Réordonne les lignes visibles par `cost_usd` décroissant ou par nom |
| Efficiency | Pills statut | Filtre exact sur `utilization_status` — **5 valeurs** : Tous / Sur-dimensionné / Sous-dimensionné / Optimal / **Zombie** (la pill Zombie a été ajoutée : le statut existait dans les données mais n'avait pas de filtre dédié en V1) |
| Governance | Pills | Filtre sur 3 conditions combinées à l'état des données : "Tags manquants" = `has_owner_tag=false OR has_cost_center_tag=false`, "DBR obsolète" = `dbr_is_lts_current=false`, "Sans auto-stop" = auto-termination non configurée |
| Section (persiste entre les 4 sous-onglets, sous les tabs Overview/Cost/Efficiency/Governance — **pas dans la topbar globale**) | Select granularité (Jour/Semaine/Mois) | Ré-agrège la **tendance de coût affichée dans le drawer** (moyenne par groupe de 1/7/28 jours). Par défaut sur "Semaine". N'affecte ni les KPI cards ni les colonnes des tableaux, qui restent des totaux sur la plage de dates sélectionnée (30j/90j/6m/1an) — cf. note technique ci-dessous |

Recherche/select/pills ne se combinent pas entre sous-vues (chaque sous-vue a son propre état de filtre, remis à zéro en changeant d'onglet). Un message "Aucun cluster ne correspond à ce filtre" s'affiche si le filtre ne renvoie aucune ligne.

**Correctif technique appliqué** : le changement de sous-onglet (Overview/Cost/Efficiency/Governance) ne fonctionnait pas initialement — la règle CSS `.subpanel{display:flex}` était plus prioritaire que l'attribut `hidden` basculé par le JS. Ajout de `.subpanel[hidden]{display:none;}` dans la feuille de style commune aux 3 pages.

**Note technique — granularité** : la maquette simule une série "quotidienne" sur 84 jours (croissante vers le total affiché, avec une légère oscillation) puis l'agrège côté client (moyenne par groupe de jours) pour donner un aperçu réaliste du rendu à chaque granularité — ce ne sont pas de vraies données jour par jour. **En implémentation réelle**, cette agrégation doit être portée par le backend/la requête SQL (`date_trunc('week', period_start)` / `date_trunc('month', period_start)` sur `gold_dbx_compute_cluster_cost_daily`), pas recalculée côté frontend à partir du grain journalier brut — à documenter avec l'équipe backend au moment du chiffrage.