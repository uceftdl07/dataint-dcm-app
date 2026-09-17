# SQL Warehouses

## Positionnement dans la navigation
`Databricks > Compute > SQL Warehouses`.

## Table des sous-vues
| Subview | Gold source | KPI cards | Filters | Personas |
|---|---|---|---|---|
| Cost | `gold_dbx_compute_warehouse_cost_daily` | `dbu_quantity`, `cost_usd`, `query_count` | search `warehouse_name`; select `warehouse_size` | FinOps, Analyst |
| Utilization | `gold_dbx_compute_warehouse_utilization_daily` | `idle_pct`, `active_to_running_ratio`, `has_auto_stop`, `estimated_savings_usd` | search `warehouse_name`; select `utilization_status`; pill `has_auto_stop` | FinOps, Data Engineer |

## User Scenarios
FinOps compares cost and unit economics. Data Engineers identify idle capacity and scaling signals.

## Functional Requirements
Two panels correspond exactly to two calculable Gold tables. Query performance and forecast are excluded.

## Table KPI / Persona / Objectif / Valeur
| KPI | Persona | Objectif | Valeur |
|---|---|---|---|
| `cost_usd` | FinOps | Identify spend | Budget control |
| `query_count` | FinOps, Analyst | Compare workload | Unit economics |
| `idle_pct` | FinOps | Detect idle runtime | Waste reduction |
| `active_to_running_ratio` | FinOps | Compare work to runtime | Auto-stop decision |
| `has_auto_stop` | FinOps, Governance | Detect missing control | Cost protection |

## Moteur de recommandations
Use only calculable utilization fields. Idle and missing auto-stop can produce illustrative action text.

## Ce qui n'est pas sur cette page
Query performance and forecast are excluded by Gold truth status.

## Drawer détail
Use shared `.drawer`, `.drawer-overlay`, `.drawer-header`, `.drawer-body`, `.id-card`, `.drawer-kpis`, `.mini-kpi`, `.mini-reco`, `.drawer-cta` and `.close-btn` contract. Content shows warehouse id, size, auto-stop, cost/query and idle.

## Contrat de données
Gold grain: `(cloud_provider, source_lz_id, workspace_id, warehouse_id, period_start)`.

## Contrat d'interaction des filtres
Search is case-insensitive substring on `warehouse_name`; selects use exact categorical match; pills use boolean match; controls combine with AND. Empty state: `Aucun résultat ne correspond à ce filtre.`

## Corrections techniques
Canonical design-system CSS is used as source. Two subviews match two calculable Gold tables. Thresholds absent from inputs remain `à valider avec le PO avant implémentation réelle`.

## checklist
- [ ] Validate active-ratio formula.
- [ ] Confirm API fields before implementation.
