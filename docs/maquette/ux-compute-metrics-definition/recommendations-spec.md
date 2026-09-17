# Recommendations

## Positionnement dans la navigation
`Databricks > Compute > Recommendations`.

## Table des sous-vues
| Subview | Gold source | KPI cards | Filters | Personas |
|---|---|---|---|---|
| Reactive queue | `gold_dbx_compute_recommendations` | `estimated_savings_usd`, `severity`, `status` | search `object_name`; select `object_type`; select `category`; select `severity`; select `status` | FinOps, Data Engineer, Governance |

## User Scenarios
Teams triage actionable recommendations by object, category, severity and lifecycle status.

## Functional Requirements
One calculable Gold table produces one view. No `.subtabs` or invented Summary view is generated.

## Table KPI / Persona / Objectif / Valeur
| KPI | Persona | Objectif | Valeur |
|---|---|---|---|
| `estimated_savings_usd` | FinOps | Quantify opportunity | Prioritize work |
| `severity` | Governance, FinOps | Find urgent actions | Reduce risk |
| `status` | FinOps, Data Engineer | Track remediation | Close backlog |

## Moteur de recommandations
The Gold table is the action source. Display `title`, `detail` and `recommended_action` from Gold; do not invent rules or cloud observations.

## Ce qui n'est pas sur cette page
Forecast and blocked/partially covered domains are excluded.

## Drawer détail
Shared drawer contract: `.drawer`, `.drawer-overlay`, `.drawer-header`, `.drawer-body`, `.id-card`, `.drawer-kpis`, `.mini-kpi`, `.mini-reco`, `.drawer-cta`, `.close-btn`. Content shows recommendation id, object, category, severity, status, savings and action CTA.

## Contrat de données
Gold grain: `(recommendation_id)`.

## Contrat d'interaction des filtres
Search is case-insensitive substring over `object_name`, `object_id` and `title`. Selects use exact match. Controls combine with AND. Empty state: `Aucun résultat ne correspond à ce filtre.`

## Corrections techniques
One calculable Gold table means one view and no domain toggle. Global shell is identical to clusters and warehouses.

## checklist
- [ ] Validate recommendation thresholds with DataEng.
- [ ] Replace illustrative values after API contract exists.
