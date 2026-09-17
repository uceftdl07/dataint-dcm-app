# Clusters

## Positionnement dans la navigation
`Databricks > Compute > Clusters`.

## Table des sous-vues
| Subview | Gold source | KPI cards | Filters | Personas |
|---|---|---|---|---|
| Cost | `gold_dbx_compute_cluster_cost_daily` | `dbu_quantity`, `cost_usd` | search `cluster_name`; select `sku_group`; select `ba_name` | FinOps, Data Engineer |
| Efficiency | `gold_dbx_compute_cluster_efficiency_daily` | `cpu_util_p95_pct`, `idle_pct` | search `cluster_name`; select `utilization_status`; pill `is_zombie` | FinOps, Data Engineer |

## User Scenarios
FinOps identifies high spend and idle clusters. Data Engineers assess sustained CPU/memory pressure and rightsizing signals.

## Functional Requirements
Two panels correspond exactly to the two calculable Gold tables. No reliability, governance or forecast panel is generated.

## Table KPI / Persona / Objectif / Valeur
| KPI | Persona | Objectif | Valeur |
|---|---|---|---|
| `cost_usd` | FinOps | Prioritize spend | Budget control |
| `dbu_quantity` | FinOps, Data Engineer | Explain consumption | Usage visibility |
| `cpu_util_p95_pct` | Data Engineer | Assess pressure | Correct sizing |
| `idle_pct` | FinOps | Find waste | Cost reduction |

## Moteur de recommandations
Use only calculable efficiency fields. `is_zombie` and high idle support an illustrative recommendation; values are explicitly mockup-only.

## Ce qui n'est pas sur cette page
Reliability, governance, query performance and forecast are excluded by Gold truth status.

## Drawer détail
Shared drawer contract: `.drawer`, `.drawer-overlay`, `.drawer-header`, `.drawer-body`, `.id-card`, `.drawer-kpis`, `.mini-kpi`, `.mini-reco`, `.drawer-cta`, `.close-btn`. Content shows cluster id, LZ, owner, node types, p95 metrics, idle and recommendation.

## Contrat de données
Gold grain: `(cloud_provider, source_lz_id, workspace_id, cluster_id, period_start)`. KPI definitions are in `gap-analysis.md`.

## Contrat d'interaction des filtres
Search is case-insensitive substring on displayed cluster identifiers/names. Selects use exact match. Pills use boolean match. Controls combine with AND. Empty state: `Aucun résultat ne correspond à ce filtre.`

## Corrections techniques
Canonical design-system CSS is copied literally. Date range, sidebar footer and user chip match all pages. Two subviews match two calculable Gold tables.

## checklist
- [ ] Replace illustrative values after API contract exists.
- [ ] Validate formulas with DataEng.
