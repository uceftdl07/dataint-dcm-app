# T002 — Databricks Overview

**Domain**: Fullstack  
**Packages**: `packages/dcm-frontend` · `packages/dcm-backend`  
**Branch**: `feature/DCINT-212-databricks-overview`  
**Jira**: [DCINT-212](https://tdf.atlassian.net/browse/DCINT-212)  
**Parent**: [DCINT-173](https://tdf.atlassian.net/browse/DCINT-173)  
**Depends on**: T001 (nav + hub)  
**Work type**: feature  
**Maquette**: `maquette_overview.html`

---

## 1. Intention de la page

Répondre à une seule question, en moins de 5 secondes : **« est-ce que le parc de workflows Databricks va bien en ce moment ? »**

Toute carte qui ne contribue pas à cette réponse relève de `/Lakeflow/Jobs`. Corollaire opérationnel : **aucune carte n'est un cul-de-sac** — chacune est cliquable et amène sur `/Lakeflow/Jobs` pré-filtré.

---

## 2. Tables gold consommées

| Table gold | Grain | Clés / dimensions | Ce qu'elle porte |
|---|---|---|---|
| `gold_dbx_workflow_success_rate` | jour × workflow | `execution_date`, `workflow_id`, `workflow_name`, `workspace_id`, `source_lz_id`, `cloud_provider` | `terminal_runs`, `succeeded_runs`, `failed_runs`, `cancelled_runs`, `timed_out_runs`, `success_rate_24h_pct`, `success_rate_7d_pct` |
| `gold_dbx_workflow_duration_percentiles` | jour × workflow | idem | `total_runs`, `avg_duration_seconds`, `p50`, `p95`, `p99`, `max_duration_seconds`, `avg_queued_duration_seconds`, `avg_schedule_lag_seconds`, `max_schedule_lag_seconds`, `avg_retry_count` |
| `gold_dbx_workflow_duration_drift` | jour × workflow | idem | `avg_duration_seconds`, `baseline_avg_14d`, `duration_drift_pct` |
| `gold_dbx_workflow_task_failure_rate` | jour × workflow | idem | `runs_with_tasks`, `tasks_total`, `tasks_failed`, `task_failure_rate_pct` |
| `gold_dbx_workflow_concurrency_1min` | minute × workspace | `minute_bucket`, `workspace_id`, `source_lz_id` | `concurrent_runs_active` |
| `gold_dbx_workflow_runs` *(détail)* | run | `(source_lz_id, workspace_id, workflow_id, run_id)` | `status`, `error_message`, `start_time`, `duration_seconds`… |

---

## 3. ⚠️ Trois points structurants

### 3.1 Agrégats au grain jour × workflow — jamais moyenner les pourcentages

`success_rate_24h_pct` existe **par workflow et par jour**. La page affiche un taux **global sur le parc**. Il faut ré-agréger.

> **Interdiction formelle : ne jamais faire `AVG(success_rate_24h_pct)`.**

**Formule correcte pour tous les KPI globaux :**

```sql
SELECT
  SUM(succeeded_runs) / NULLIF(SUM(terminal_runs), 0) * 100 AS success_rate_pct,
  SUM(terminal_runs)                                         AS n
FROM gold_dbx_workflow_success_rate
WHERE execution_date >= :date_from
  AND workspace_id IN (:workspaces)
```

Même principe pour `task_failure_rate_pct` : `SUM(tasks_failed) / SUM(tasks_total)`.

### 3.2 `concurrent_runs_active` n'est pas du temps réel

La table `gold_dbx_workflow_concurrency_1min` est **reconstruite a posteriori** (intervalles `[start_time, coalesce(end_time, current_timestamp())]` éclatés en buckets 1 min).

Conséquences :
1. Fraîcheur dépend de la latence collecteur → gold, pas d'une sonde live.
2. **Badge « LIVE » clignotant à retirer.** → Libellé retenu : **« Runs actifs »** avec mention `à HH:MM`.
3. Pas de décomposition `queued`/`pending`/`running` en V1 (§7 écart n°4).

### 3.3 Le drift est calculé sur la moyenne, pas la médiane

`gold_dbx_workflow_duration_drift` compare `avg_duration_seconds` du jour à `baseline_avg_14d`. Le libellé affiché doit être **« Durée moyenne »**, pas « médiane ». Le `p50` vient de `duration_percentiles` — ne pas les mélanger.

---

## 4. Structure de la page

```
┌─────────────────────────────────────────────────────────────────────┐
│  Landing Zone ▾ │ Workspaces ▾ │ Fenêtre : [Aujourd'hui] 7j 30j │ MAJ 14:32 ⟳ │
├─────────────────────────────────────────────────────────────────────┤
│  ACTIVITÉ                                                           │
│  [ Runs actifs ]   [ Runs sur la fenêtre ]   [ Runs en échec ]      │
├─────────────────────────────────────────────────────────────────────┤
│  FIABILITÉ                                                          │
│  [ ◕ Succès 24h ]  [ ◕ Succès 7j ]   [ Tâches KO ]                 │
├─────────────────────────────────────────────────────────────────────┤
│  PERFORMANCE                                                        │
│  [ Durée moy. + drift ]  [ p95/p99/p50 ]  [ Attente moy. ]         │
├─────────────────────────────────────────────────────────────────────┤
│  [ Barres empilées — Runs terminés par statut ]                     │
├──────────────────────────────┬──────────────────────────────────────┤
│ [ Top 5 workflows instables ]│ [ 5 derniers runs en échec ]         │
└──────────────────────────────┴──────────────────────────────────────┘
```

### Filtres globaux (persistants, transmis au drill-down)

| Filtre | Champ gold | Comportement |
|---|---|---|
| Landing Zone | `source_lz_id` | Multi-select ; « Toutes » par défaut |
| Workspace | `workspace_id` | Multi-select, alimenté depuis `gold_dbx_workflow_success_rate` |
| Fenêtre | `execution_date` | **Aujourd'hui** (défaut) / 7j / 30j |
| Fraîcheur | `MAX(collected_at)` | Badge orange si > 30 min |

> **Note fenêtre « Aujourd'hui »** : le grain gold étant journalier, cela signifie `execution_date = current_date()` — pas les 24 h glissantes. À indiquer clairement dans l'UI pour éviter des chiffres bas le matin.

---

## 5. Spec carte par carte

### Bandeau 1 — Activité

#### Carte 1.1 — Runs actifs

| | |
|---|---|
| **Valeur** | `concurrent_runs_active` du dernier `minute_bucket` |
| **Table** | `gold_dbx_workflow_concurrency_1min` |
| **Secondaire** | Sparkline 24 h, buckets 15 min, agrégat `MAX` |
| **Sous-titre** | `à HH:MM` — horodatage du dernier bucket. **Pas de badge LIVE** |
| **Couleur** | Neutre |
| **Alerte** | Badge orange si dernier bucket > 15 min |
| **Clic** | → `/lakeflow/jobs?status=running` |

```sql
SELECT minute_bucket, SUM(concurrent_runs_active) AS active
FROM gold_dbx_workflow_concurrency_1min
WHERE minute_bucket >= current_timestamp() - INTERVAL 24 HOURS
  AND workspace_id IN (:workspaces) AND source_lz_id IN (:lz)
GROUP BY minute_bucket ORDER BY minute_bucket
```

#### Carte 1.2 — Runs sur la fenêtre

| | |
|---|---|
| **Valeur** | `SUM(terminal_runs)` |
| **Table** | `gold_dbx_workflow_success_rate` |
| **Secondaire** | Barre segmentée succeeded / failed / timed_out / cancelled |
| **Clic** | → `/lakeflow/jobs` sans filtre statut |

#### Carte 1.3 — Runs en échec

| | |
|---|---|
| **Valeur** | `SUM(failed_runs) + SUM(timed_out_runs)` |
| **Table** | `gold_dbx_workflow_success_rate` |
| **Secondaire** | Delta vs période précédente de même durée |
| **Couleur** | Rouge si > 0 |
| **Clic** | → `/lakeflow/jobs?status=failed,timed_out` — **chemin prioritaire, à soigner** |

### Bandeau 2 — Fiabilité

#### Cartes 2.1 & 2.2 — Taux de succès Aujourd'hui · 7j

| | |
|---|---|
| **Table** | `gold_dbx_workflow_success_rate` |
| **Calcul** | `SUM(succeeded_runs) / NULLIF(SUM(terminal_runs),0) * 100` (§3.1) |
| **Composant** | Jauge radiale semi-circulaire |
| **Seuils** | 🟢 > 95 % · 🟠 90–95 % · 🔴 < 90 % |
| **Secondaire** | `n = SUM(terminal_runs)` + delta vs période précédente |
| **Garde-fou** | Si `n < 5` → gris neutre, mention `n = X`, aucun code couleur |
| **Survol** | Décomposition succeeded / failed / timed_out / cancelled |

> Ne pas utiliser `success_rate_7d_pct` de la table pour le KPI global — elle est calculée par workflow, l'agréger reviendrait à moyenner des pourcentages (§3.1).

#### Carte 2.3 — Taux d'échec des tâches

| | |
|---|---|
| **Table** | `gold_dbx_workflow_task_failure_rate` |
| **Calcul** | `SUM(tasks_failed) / NULLIF(SUM(tasks_total),0) * 100` |
| **Secondaire** | Fraction brute `41 / 1 204` + delta |
| **Seuils** | 🟢 < 2 % · 🟠 2–5 % · 🔴 > 5 % *(à calibrer sur 2 semaines de données réelles)* |
| **Clic** | → `/lakeflow/jobs` trié par taux d'échec de tâches desc |

> Intentionnellement décorrélé du taux de succès runs : 98 % succès + 15 % échecs tâches = parc fragile qui ne tient qu'aux retries.

### Bandeau 3 — Performance

#### Carte 3.1 — Durée moyenne + dérive

| | |
|---|---|
| **Valeur** | `SUM(avg_duration_seconds * total_runs) / SUM(total_runs)` (pondérée) |
| **Tables** | `gold_dbx_workflow_duration_percentiles` (valeur) + `gold_dbx_workflow_duration_drift` (dérive) |
| **Dérive** | Recalcul du `duration_drift_pct` au niveau parc (même formule pondérée sur `baseline_avg_14d`) |
| **Affichage** | `+23 % ↗` rouge / `-4 % ↘` vert |
| **Alerte** | ⚠️ si drift > +20 % |
| **Libellé** | **« Durée moyenne »** — surtout pas « médiane » (§3.3) |
| **Clic** | → `/lakeflow/jobs` trié par `duration_drift_pct` desc |

Garde-fous API :
- `null` (`n/a`) si `baseline_avg_14d` < 5 runs
- `null` si `baseline_avg_14d < 30 s`

#### Carte 3.2 — Distribution des durées

| | |
|---|---|
| **Valeurs** | `p95` principal, `p99` et `p50` secondaires |
| **Table** | `gold_dbx_workflow_duration_percentiles` |
| **⚠️ Agrégation** | Les percentiles **ne s'additionnent ni ne se moyennent**. Recommandation : calculer p95 parc depuis `gold_dbx_workflow_runs` au grain run (option B §7 écart n°3). En V1 acceptable : `MAX(p95)` avec libellé « pire p95 du parc » |
| **Clic** | → `/lakeflow/jobs` trié par `p95` desc |

#### Carte 3.3 — Attente moyenne

| | |
|---|---|
| **Valeur** | `SUM(avg_queued_duration_seconds × total_runs) / SUM(total_runs)` |
| **Table** | `gold_dbx_workflow_duration_percentiles` |
| **Secondaire** | Barre empilée `queue` \| `schedule lag` via `avg_schedule_lag_seconds` |
| **Alerte** | ⚠️ si `max_schedule_lag_seconds` > 900 s |

---

## 6. Blocs de bas de page

### 6.1 Runs terminés par statut (barres empilées)

Source : `gold_dbx_workflow_success_rate`, colonnes `succeeded_runs`, `failed_runs`, `timed_out_runs`, `cancelled_runs`, un point par `execution_date`.

| Statut | Couleur | Hex |
|---|---|---|
| `succeeded` | vert | `#16a34a` |
| `failed` | rouge | `#dc2626` |
| `timed_out` | orange foncé | `#ea580c` |
| `cancelled` | gris | `#94a3b8` |

> Sur fenêtre « Aujourd'hui », une seule barre → **masquer le bloc en V1** ; activer avec la fenêtre horaire (§7 écart n°2).

### 6.2 Top 5 des workflows instables

```sql
SELECT workflow_name, workflow_id, workspace_id,
       SUM(failed_runs) + SUM(timed_out_runs) AS ko,
       SUM(terminal_runs)                     AS total
FROM gold_dbx_workflow_success_rate
WHERE execution_date >= :date_from AND workspace_id IN (:workspaces)
GROUP BY ALL HAVING ko > 0 ORDER BY ko DESC LIMIT 5
```

Chaque ligne → `/lakeflow/jobs/{workflow_id}`.

### 6.3 5 derniers runs en échec (remplace « Top 5 erreurs » en V1)

⚠️ `termination_code` absent du modèle gold actuel — un `GROUP BY error_message` brut produit 200 groupes de 1 (messages avec `run_id`, timestamps variables).

**V1 : afficher les 5 derniers runs en échec** (workflow, heure, message tronqué, `run_page_url`).

Options futures par ordre de préférence :
- **A** — Ajouter `termination_code` au collecteur → curated → gold *(recommandé)*
- **B** — Regex de classification côté API *(fragile)*
- **C** — Reporter en V1.1

---

## 7. Écarts modèle gold / besoin UI (à arbitrer avec Adrien)

| # | Manque | Impact UI | Priorité |
|---|---|---|---|
| 1 | Pas de `termination_code` en gold | Bloc §6.3 inexploitable | **Haute** |
| 2 | Agrégats au grain jour uniquement | « Aujourd'hui » = jour courant, graphe 1 seule barre | **Haute** |
| 3 | Percentiles non ré-agrégeables | p95 parc approximatif | Moyenne |
| 4 | Pas de décomposition queued/pending/running dans `concurrency_1min` | Carte En attente supprimée | Moyenne |
| 5 | `tags` non propagés en gold | Impossible filtrer par domaine métier | Moyenne |
| 6 | `SUCCESS_WITH_FAILURES` non distinct | Runs partiellement KO comptés en succès | Moyenne |
| 7 | `setup_duration_seconds` / `cleanup_duration_seconds` absents | Décomposition fine durée impossible | Basse |
| 8 | Pas de `trigger_type` dans agrégats | Impossible filtrer par type déclenchement | Basse |

---

## 8. Contrat d'API

**Un seul appel pour toute la page.**

```
GET /api/lakeflow/overview
  ?lz=<source_lz_id[]>&workspaces=<workspace_id[]>&window=today|7d|30d
```

```jsonc
{
  "as_of": "2026-08-03T14:32:00Z",         // MAX(collected_at) — pilote badge fraîcheur
  "window": { "from": "2026-08-03", "to": "2026-08-03", "grain": "day" },
  "activity": {
    "concurrent_runs_active": 12,
    "concurrency_as_of": "2026-08-03T14:31:00Z",
    "concurrency_sparkline": [ { "t": "...", "v": 8 } ],
    "runs_total": 143,
    "runs_by_status": { "succeeded": 136, "failed": 3, "timed_out": 1, "cancelled": 3 },
    "runs_ko": 4,
    "runs_ko_delta": -2
  },
  "reliability": {
    "success_rate_24h_pct": 97.2, "success_rate_24h_n": 143, "success_rate_24h_delta": 1.1,
    "success_rate_7d_pct": 94.1,  "success_rate_7d_n": 1021,  "success_rate_7d_delta": -0.8,
    "task_failure_rate_pct": 3.4, "tasks_failed": 41, "tasks_total": 1204
  },
  "performance": {
    "avg_duration_seconds": 252,
    "duration_drift_pct": 23.4,            // null si baseline < 5 runs ou < 30 s
    "p50": 228, "p95": 1120, "p99": 2531,
    "avg_queued_duration_seconds": 48,
    "avg_schedule_lag_seconds": 17,
    "max_schedule_lag_seconds": 940
  },
  "timeline": [
    { "date": "2026-08-01", "succeeded": 480, "failed": 12, "timed_out": 2, "cancelled": 6 }
  ],
  "top_unstable": [
    { "workflow_id": "...", "workflow_name": "...", "ko": 7, "total": 42 }
  ],
  "recent_errors": [
    { "workflow_name": "...", "run_id": "...", "start_time": "...",
      "error_message": "...", "run_page_url": "https://..." }
  ]
}
```

- **Cache** 60 s · **Rafraîchissement auto** 60 s côté client · **Timeout** 5 s
- Dégradation carte par carte : une carte en erreur ne blanche pas la page

---

## 9. États non nominaux

| Situation | Comportement |
|---|---|
| Aucun run sur la fenêtre | Toutes cartes en gris · « Aucune exécution sur la période » + lien vers 7j |
| `n < 5` sur un dénominateur | Valeur en gris · mention `n = X` · **aucun code couleur** |
| Données > 30 min | Badge orange « Données de HH:MM » dans la barre haute |
| `gold_dbx_workflow_concurrency_1min` vide | Carte 1.1 affiche `—` + « Indisponible », reste de la page intact |
| Une table gold en erreur | Cartes concernées en erreur individuelle, jamais de page blanche |
| Baseline drift insuffisante | `n/a` sur dérive, durée reste affichée |

---

## 10. Points à valider avec Adrien (Techlead)

1. **Fenêtre « Aujourd'hui »** — accepte-t-on « jour courant » en V1, ou ajoute-t-on un agrégat horaire (écart n°2) ?
2. **`termination_code`** — ajout au collecteur validé pour V1 ? Conditionne §6.3.
3. **Seuils taux d'échec tâches** — 2 %/5 % à confirmer après 2 semaines d'observation.
4. **Latence collecteur → gold** — chiffre réel ? Détermine honnêteté sous-titre carte 1.1.
5. **`SUCCESS_WITH_FAILURES`** — quelle valeur `status` remonte aujourd'hui ? Si écrasée en `succeeded`, signal perdu (écart n°6).
6. **Multi-workspace** — agrégation multi-workspace a-t-elle un sens métier, ou force-t-on la sélection d'un seul ?

---

## Acceptance Criteria

- [ ] Route `/databricks/overview` charge tous les KPIs depuis `GET /api/lakeflow/overview`
- [ ] Bandeau 1 (Activité) : 3 cartes avec valeurs, sparkline, drill-down
- [ ] Bandeau 2 (Fiabilité) : jauges radiales avec seuils de couleur + garde-fou `n < 5`
- [ ] Bandeau 3 (Performance) : durée pondérée + drift + percentiles + attente
- [ ] Barres empilées timeline (masquées sur fenêtre Aujourd'hui)
- [ ] Top 5 instables + 5 derniers runs en échec avec `run_page_url`
- [ ] Filtres LZ / Workspace / Fenêtre fonctionnels et transmis au drill-down
- [ ] Badge fraîcheur orange si données > 30 min
- [ ] États vides/erreur par carte (pas de page blanche)
- [ ] Libellé **« Durée moyenne »** (pas médiane), **« Aujourd'hui »** (pas 24h), pas de badge LIVE
- [ ] PR → `develop` avec cette sub-spec liée

## Tests

```bash
cd packages/dcm-frontend && npm run test -- --run databricks-overview
```
