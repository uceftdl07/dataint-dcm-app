# Contract — API : NULL-tolérance + fraîcheur `as_of`

> Aucune route Lakeflow ne disparaît, aucun champ n'est retiré des réponses (P15).
> Deux évolutions **additives / non-cassantes** : (1) champs nullable tolérés, (2) champ `as_of`.

## 1. Routes concernées (inchangées en surface)

| Route / service | Rôle | Évolution |
|---|---|---|
| `lakeflow_overview.py` | Overview (success rate, percentiles, drift, concurrency, failures) | + `as_of` ; percentiles queue/lag → `null` |
| `lakeflow_jobs.py` | Jobs N1/N2/N3 (runs, tasks, matrice, task health) | champs NULL tolérés (queue/lag/exec, `workspace_name`, `error_message`) ; + `as_of` |
| `routes/databricks.py` → `/workspaces` | résolution nom workspace | repli : gold/curated `workspace_name` NULL → tags compute (`dcm_workspace_name`/`Project`, `dbw-%`) → `workspace_id` |

## 2. NULL-tolérance Pydantic (P15)

- Tous les champs devenus NULL doivent être typés `... | None` dans les modèles de réponse
  (vérifier/aligner : `queued_duration_seconds`, `execution_duration_seconds`, `schedule_lag_seconds`,
  `workspace_name`, et agrégats `avg_queued_duration_seconds`, `avg_schedule_lag_seconds`,
  `max_schedule_lag_seconds`).
- `creator_user_name` : reste `str | None`, contient désormais `creator_id`.
- `error_message` : `str | None`, contenu = `termination_code` + message court.
- **Aucun champ retiré** — les clients existants continuent de désérialiser.

## 3. Champ `as_of` (fraîcheur réelle — clarif. Q5)

```jsonc
// Ajout additif aux réponses overview + jobs
{
  "as_of": "2026-08-17T01:12:00Z",   // = max(_ingested_at) des curated_dbx_lakeflow_* servant la réponse
  // ... reste du contrat inchangé
}
```

- **Source** : `max(_ingested_at)` (colonne d'enveloppe socle) des tables curated lakeflow réellement
  interrogées. Valeur **réelle**, jamais une constante.
- **Sémantique** : instant de la dernière ingestion connue ; le frontend en dérive « données à ~X h »
  (âge = `now - as_of`).
- **Backward-compat** : champ optionnel ajouté ; absence tolérée par les anciens clients.

## 4. `/workspaces` — ordre de résolution du nom

1. ~~`gold_dbx_workflow_runs.workspace_name`~~ → NULL (ne renvoie plus).
2. ~~`curated_dbx_workflow_runs.workspace_name`~~ → NULL.
3. **Tags compute** (`dcm_workspace_name`/`Project`, motif `dbw-%`) — voie principale désormais.
4. **`workspace_id`** — repli final (jamais un nom inventé).

Tests `test_databricks_workspaces.py` : adapter les fixtures pour `workspace_name = NULL` en gold/curated
et vérifier la bascule sur tags puis id.

## 5. Frontend — bandeau fraîcheur & colonnes NULL-safe (P16, clarif. Q3/Q5)

- **Bandeau** « données à ~X h » calculé depuis `as_of` (pas un texte statique).
- **Colonnes durée/attente** : `null` → « n/d » / tiret, **jamais `0`**.
- **Colonne « Attente »** (queue | lag) : **masquée par défaut** (source NULL).
- **Tooltip cron** du Trigger : retiré (donnée absente) ; `trigger_type` conservé.
- **Workspace / Propriétaire** : fallback `workspace_id` / `creator_id` si nom absent.
- Tests Vitest : fixtures NULL, assertion rendu « n/d », bandeau `as_of`.
- `app-routes.ts` inchangé.
