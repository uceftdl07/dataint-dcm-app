# Rapport d'usage DCM — `019-usage-data-product-gold`

Trace de chaque step du workflow : **modèle utilisé** + **tokens consommés**.

| | |
|--|--|
| **Spec** | `019-usage-data-product-gold` |
| **Epic Jira** | — |
| **Stories Jira** | — |
| **Période** | 2026-09-01T12:21:08Z → 2026-09-01T13:01:23Z |
| **Généré** | 2026-09-01T13:01:23Z UTC |
| **Total tokens** | **0** (in 0 / out 0 / cache 0) |
| **Coût estimé** | **$—** |
| **Qualité données** | estimé — réel 0 / estimé 4 |

---

## 1. Timeline par step (détails)

> **Détails complets** : Voir `specs/019-usage-data-product-gold/usage-log.jsonl` — chaque ligne = un passage (specify, plan, tasks, implement, review…) avec modèle, tokens, coût.  
> **Résumé** : Voir section 2 ci-dessous.

---

## 2. Totaux par step

Vue consolidée : combien de tokens **par étape** du workflow.

| Step | Runs | Tokens | % du total | Modèles utilisés | Coût USD |
|------|-----:|-------:|-----------:|------------------|---------:|
| `specify` | 1 | **0** | 0% | `claude-sonnet-5` | 0.0000 |
| `clarify` | 1 | **0** | 0% | `claude-sonnet-5` | 0.0000 |
| `plan` | 1 | **0** | 0% | `claude-sonnet-5` | 0.0000 |
| `tasks` | 1 | **0** | 0% | `claude-sonnet-5` | 0.0000 |

---

## 3. Jira (Epic + Stories)

| Type | Key | Task | Branch | PR |
|------|-----|------|--------|----|
| — | — | — | — | — |

> L’Epic et les Stories viennent de `jira-mapping.json` / `dispatch-manifest.json`.  
> Enrichis aussi ligne par ligne dans le log (`jira_keys`).

---

## 4. Synthèse rapide

| Dimension | Détail |
|-----------|--------|
| Runs | 4 (dont 4 sans tokens) |
| Providers | copilot |
| Models | claude-sonnet-5 |
| Work modes | speckit |
| AC coverage | — (pas de section Acceptance Criteria dans spec.md) |
| Pref modèle match | 25% (1/4) |

### Tokens par provider

| Provider | Runs | Tokens | Coût USD | % réel |
|----------|-----:|-------:|---------:|-------:|
| `copilot` | 4 | 0 | 0.0000 | 0% |

### Tokens par modèle

| Modèle | Provider | Runs | Tokens | Coût USD |
|--------|----------|-----:|-------:|---------:|
| `claude-sonnet-5` | `copilot` | 4 | 0 | 0.0000 |

---

## 5. Skills consultés par l'agent

Skills chargés / appliqués pour chaque step de cette Epic.

> **Epic — skills uniques** : — (aucun skill loggé)

| Step | Runs | Skills | Source |
|------|-----:|--------|--------|
| `specify` | 1 | — | non loggé |
| `clarify` | 1 | — | non loggé |
| `plan` | 1 | — | non loggé |
| `tasks` | 1 | — | non loggé |

> **Source** `explicite` = loggé via `--skills` dans usage-log · `non loggé` = aucun skill enregistré pour ce step.

---

## Notes

- Qualité **réel** = Claude `message.usage` ou Copilot OTel ; **estimé** = Copilot `ccreq` / saisie manuelle.
- Coût USD = indicatif (rates dans `dcm-append-usage.sh`), pas une facture.
- **Steps** : `scope` → `specify` → `plan` → `tasks` → `dispatch` → `implement` → `review` → `publish-pr` — inférés depuis les timestamps des fichiers spec.
- Régénérer : `/speckit.dcm.usage-report` ou `scripts/dcm-render-usage-report.sh --feature-dir …`
- Log brut : `specs/019-usage-data-product-gold/usage-log.jsonl`
- Rapport : `rapports/019-usage-data-product-gold.md`
