# Tasks — Métriques Usage & FinOps Databricks (Azure + AWS) → curated

**Feature**: `010-databricks-usage-finops-curated`
**Spec**: [`spec.md`](./spec.md) · **Plan**: [`plan.md`](./plan.md)
**Work type**: feature · **Domain**: DataEng · **Dispatch mode**: one_per_domain (split par sujet)
**Expected stories**: 2

> ✅ **GATE lev\u00e9 (spike)** — E1 (sch\u00e9ma `__d` mapp\u00e9 par target), E2 (workspace dev AWS `dbc-16a9ad66-c301`), **E3 (m\u00e9canisme lecture Azure)** tranch\u00e9s. Cf. `plan.md` §3 et [`docs/spike/delta-sharing-azure-to-aws-billing.md`](../../docs/spike/delta-sharing-azure-to-aws-billing.md).
>
> **D\u00e9cisions cl\u00e9s** :
> - **E3** : Delta Sharing UC\u2192UC **bloqu\u00e9** (firewall ADLS Gen2). Lecture Azure = **SP OAuth M2M \u2192 Azure SQL Warehouse** via **JDBC** (spike Option A) ; AWS re\u00e7oit seulement les lignes r\u00e9sultats.
> - **E5** : **Pas de DLT** \u2014 Job Databricks **PySpark** (`spark.read` + `MERGE INTO`), disjoint du DLT collecteur.
> - **Tables mutualis\u00e9es** Azure \u228e AWS (colonne `cloud_provider`) ; **MERGE idempotent** anti-doublon.
>
> \u26a0\ufe0f **Pr\u00e9requis externes \u00e0 confirmer DAP/IAM/Network** (spike §Pr\u00e9requis) : SP Entra ID + secret, Azure SQL Warehouse d\u00e9di\u00e9 + `CAN USE`, firewall endpoint warehouse joignable depuis AWS, vue mat\u00e9rialis\u00e9e Azure `billing.usage`.

---

## Index

| ID | Domain | Titre | Package | Branch | Sub-spec | Jira | Statut |
|----|--------|-------|---------|--------|----------|------|--------|
| T001 | DataEng | Usage Databricks (compute, access.audit, table_lineage, query.history) Azure+AWS → curated | `packages/dcm-databricks-pipeline` | `feature/010_metrics_system` | [stories/T001-usage-metrics.md](./stories/T001-usage-metrics.md) | [DCINT-192](https://tdf.atlassian.net/browse/DCINT-192) | ☐ To Do |
| T002 | DataEng | FinOps Databricks (`billing.usage × list_prices`) Azure+AWS → curated | `packages/dcm-databricks-pipeline` | `feature/010_metrics_system` | [stories/T002-finops-metrics.md](./stories/T002-finops-metrics.md) | [DCINT-193](https://tdf.atlassian.net/browse/DCINT-193) | ☐ To Do |

**Dépendance** : T002 réutilise le socle **connexion Azure JDBC** (SP OAuth M2M \u2192 Azure SQL Warehouse) + Job bundle `job_dcm_system_tables.yml` créé en T001 (`Depends on: T001` pour la resource commune, sinon parallélisable).

---

## Out of scope (rappel)

- Backend routes API / Frontend dashboards → futur Epic.
- Delta Sharing UC→UC (**bloqué** firewall ADLS Gen2 — cf. spike). Feature 010 hybrid (supprimée).
- Pipeline **DLT** (inadapté — E5) ; couche **gold** / agrégats FinOps.
- Lakehouse Federation (spike Option C) — cible industrialisation, hors POC.
