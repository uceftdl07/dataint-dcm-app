# Rapport d'usage DCM — `{SPEC_SLUG}`

Trace de chaque step du workflow : **modèle utilisé** + **tokens consommés**.

| | |
|--|--|
| **Spec** | `{SPEC_SLUG}` |
| **Epic Jira** | {EPIC} |
| **Stories Jira** | {STORIES} |
| **Période** | {PERIOD_START} → {PERIOD_END} |
| **Généré** | {GENERATED_AT} UTC |
| **Total tokens** | **{TOTAL_TOKENS}** (in {TOTAL_INPUT} / out {TOTAL_OUTPUT} / cache {TOTAL_CACHE_READ}) |
| **Coût estimé** | **${TOTAL_COST}** |
| **Qualité données** | {ACCURACY_LABEL} — réel {REAL_COUNT} / estimé {EST_COUNT} |

---

## 1. Timeline par step (détails)

> **Détails complets** : Voir `{FEATURE_DIR}/usage-log.jsonl` — chaque ligne = un passage (specify, plan, tasks, implement, review…) avec modèle, tokens, coût.  
> **Résumé** : Voir section 2 ci-dessous.

---

## 2. Totaux par step

Vue consolidée : combien de tokens **par étape** du workflow.

| Step | Runs | Tokens | % du total | Modèles utilisés | Coût USD |
|------|-----:|-------:|-----------:|------------------|---------:|
<!-- BY_STEP -->

---

## 3. Jira (Epic + Stories)

| Type | Key | Task | Branch | PR |
|------|-----|------|--------|----|
<!-- JIRA_TABLE -->

> L’Epic et les Stories viennent de `jira-mapping.json` / `dispatch-manifest.json`.  
> Enrichis aussi ligne par ligne dans le log (`jira_keys`).

---

## 4. Synthèse rapide

| Dimension | Détail |
|-----------|--------|
| Runs | {STEP_COUNT} (dont {UNKNOWN_COUNT} sans tokens) |
| Providers | {PROVIDERS} |
| Models | {MODELS} |
| Work modes | {WORK_MODES} |
| AC coverage | {AC_COVERAGE} |
| Pref modèle match | {PREF_MATCH} |

### Tokens par provider

| Provider | Runs | Tokens | Coût USD | % réel |
|----------|-----:|-------:|---------:|-------:|
<!-- BY_PROVIDER -->

### Tokens par modèle

| Modèle | Provider | Runs | Tokens | Coût USD |
|--------|----------|-----:|-------:|---------:|
<!-- BY_MODEL -->

---

## 5. Skills consultés par l'agent

Skills chargés / appliqués pour chaque step de cette Epic.

> **Epic — skills uniques** : {EPIC_SKILLS}

| Step | Runs | Skills | Source |
|------|-----:|--------|--------|
<!-- SKILLS_USED -->

> **Source** `explicite` = loggé via `--skills` dans usage-log · `non loggé` = aucun skill enregistré pour ce step.

---

## Notes

- Qualité **réel** = Claude `message.usage` ou Copilot OTel ; **estimé** = Copilot `ccreq` / saisie manuelle.
- Coût USD = indicatif (rates dans `dcm-append-usage.sh`), pas une facture.
- **Steps** : `scope` → `specify` → `plan` → `tasks` → `dispatch` → `implement` → `review` → `publish-pr` — inférés depuis les timestamps des fichiers spec.
- Régénérer : `/speckit.dcm.usage-report` ou `scripts/dcm-render-usage-report.sh --feature-dir …`
- Log brut : `{FEATURE_DIR}/usage-log.jsonl`
- Rapport : `rapports/{REPORT_NAME}`
