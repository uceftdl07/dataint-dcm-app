# Rapport d'usage DCM — `demo-usage-tokens`

Trace de chaque step du workflow : **modèle utilisé** + **tokens consommés**.

| | |
|--|--|
| **Spec** | `demo-usage-tokens` |
| **Epic Jira** | [DCINT-200](https://tdf.atlassian.net/browse/DCINT-200) |
| **Stories Jira** | [DCINT-213](https://tdf.atlassian.net/browse/DCINT-213) |
| **Période** | 2026-08-09T23:56:43Z → 2026-08-09T23:56:43Z |
| **Généré** | 2026-08-23T21:09:40Z UTC |
| **Total tokens** | **30,600** (in 23,500 / out 7,100 / cache 8,000) |
| **Coût estimé** | **$0.1794** |
| **Qualité données** | mixte (25% réel) — réel 1 / estimé 3 |

---

## 1. Timeline par step (détails)

> **Détails complets** : Voir `spec-kit-dcm-workflow/specs/demo-usage-tokens/usage-log.jsonl` — chaque ligne = un passage (specify, plan, tasks, implement, review…) avec modèle, tokens, coût.  
> **Résumé** : Voir section 2 ci-dessous.

---

## 2. Totaux par step

Vue consolidée : combien de tokens **par étape** du workflow.

| Step | Runs | Tokens | % du total | Modèles utilisés | Coût USD |
|------|-----:|-------:|-----------:|------------------|---------:|
| `specify` | 1 | **15,700** | 51% | `claude-sonnet` | 0.0879 |
| `tasks` | 1 | **8,900** | 29% | `gpt-4.1` | 0.0519 |
| `implement` | 1 | **6,000** | 20% | `composer` | 0.0396 |
| `review` | 1 | **0** | 0% | `n/a` | 0.0000 |

---

## 3. Jira (Epic + Stories)

| Type | Key | Task | Branch | PR |
|------|-----|------|--------|----|
| Epic | [DCINT-200](https://tdf.atlassian.net/browse/DCINT-200) | — | — | — |
| Story | [DCINT-213](https://tdf.atlassian.net/browse/DCINT-213) | T001 | `feat/dcm-workflow-usage-report` | — |

> L’Epic et les Stories viennent de `jira-mapping.json` / `dispatch-manifest.json`.  
> Enrichis aussi ligne par ligne dans le log (`jira_keys`).

---

## 4. Synthèse rapide

| Dimension | Détail |
|-----------|--------|
| Runs | 4 (dont 0 sans tokens) |
| Providers | claude, copilot, cursor, estimate |
| Models | claude-sonnet, composer, gpt-4.1, n/a |
| Work modes | direct, manual, speckit |
| AC coverage | 2/3 (67%) |
| Pref modèle match | 25% (1/4) |

### Tokens par provider

| Provider | Runs | Tokens | Coût USD | % réel |
|----------|-----:|-------:|---------:|-------:|
| `claude` | 1 | 15,700 | 0.0879 | 100% |
| `copilot` | 1 | 8,900 | 0.0519 | 0% |
| `cursor` | 1 | 6,000 | 0.0396 | 0% |
| `estimate` | 1 | 0 | 0.0000 | 0% |

### Tokens par modèle

| Modèle | Provider | Runs | Tokens | Coût USD |
|--------|----------|-----:|-------:|---------:|
| `claude-sonnet` | `claude` | 1 | 15,700 | 0.0879 |
| `gpt-4.1` | `copilot` | 1 | 8,900 | 0.0519 |
| `composer` | `cursor` | 1 | 6,000 | 0.0396 |
| `n/a` | `estimate` | 1 | 0 | 0.0000 |

---

## 5. Skills consultés par l'agent

Skills chargés / appliqués pour chaque step de cette Epic.

> **Epic — skills uniques** : — (aucun skill loggé)

| Step | Runs | Skills | Source |
|------|-----:|--------|--------|
| `specify` | 1 | — | non loggé |
| `tasks` | 1 | — | non loggé |
| `implement` | 1 | — | non loggé |
| `review` | 1 | — | non loggé |

> **Source** `explicite` = loggé via `--skills` dans usage-log · `non loggé` = aucun skill enregistré pour ce step.

---

## Notes

- Qualité **réel** = Claude `message.usage` ou Copilot OTel ; **estimé** = Copilot `ccreq` / Cursor manuel.
- Coût USD = indicatif (rates dans `dcm-append-usage.sh`), pas une facture.
- **Steps** : `scope` → `specify` → `plan` → `tasks` → `dispatch` → `implement` → `review` → `publish-pr` — inférés depuis les timestamps des fichiers spec.
- Régénérer : `/speckit.dcm.usage-report` ou `scripts/dcm-render-usage-report.sh --feature-dir …`
- Log brut : `spec-kit-dcm-workflow/specs/demo-usage-tokens/usage-log.jsonl`
- Rapport : `rapports/DCINT-200-demo-usage-tokens.md`
