/** Field descriptions for Lakeflow Jobs & Pipelines (gold workflow tables). */
export const lakeflowJobFieldDescriptions = {
  status:
    'Statut du dernier run terminé ou en cours (`gold_dbx_workflow_runs.status`). Couleur : vert = succès, rouge = échec, orange = timeout, gris = annulé, bleu = en cours.',
  job: 'Nom affiché du workflow Databricks (Jobs & Pipelines) et identifiant technique `workflow_id`.',
  history:
    'Jusqu’à 10 derniers runs du workflow sur la période sélectionnée (header From/To), source `gold_dbx_workflow_runs`. Couleur = statut final ; hauteur = durée relative au run le plus long de la série. Gauche = plus ancien, droite = plus récent. Cliquer une barre ouvre le détail du run.',
  runs: 'Nombre de runs terminés (succès, échec, timeout, annulé) sur la période sélectionnée (`terminal_runs` depuis `gold_dbx_workflow_success_rate`).',
  cost: 'Coût d’exécution cumulé sur la période sélectionnée (`gold_dbx_compute_job_cluster_cost_daily.cost_usd`). Ne couvre que les clusters de type JOB — vide (—) si ce job tourne uniquement sur du compute interactif ou serverless, pas de coût connu plutôt qu’un coût nul.',
  success24h:
    'Taux de succès glissant 24 h et volume n associé (`success_rate_24h_pct`, `success_rate_24h_n`).',
  success7d:
    'Taux de succès glissant 7 jours et volume n associé (`success_rate_7d_pct`, `success_rate_7d_n`).',
  success: 'Taux de succès sur la période sélectionnée dans le header (`success_rate_pct`).',
  durationDrift:
    'Durée moyenne des runs sur la période et dérive vs baseline 14 jours (`avg_duration_seconds`, `duration_drift_pct` depuis `gold_dbx_workflow_duration_drift`).',
  p50: '50e percentile de durée des runs sur la période (`gold_dbx_workflow_duration_percentiles`).',
  p95: '95e percentile de durée des runs sur la période.',
  p99: '99e percentile de durée des runs sur la période.',
  wait: 'Temps moyen d’attente avant exécution : file d’attente cluster (bleu) vs retard de planification (orange).',
  retries: 'Nombre moyen de retries par run sur la période.',
  trigger: 'Type de déclenchement du dernier run (scheduled, manual, retry, etc.).',
  runType: 'Type d’exécution du dernier run (job run, submit run, etc.).',
  lastDuration: 'Durée du dernier run terminé ou en cours.',
  lastRun:
    'Horodatage de début et fin du dernier run (`start_time`, `end_time` depuis `gold_dbx_workflow_runs`).',
} as const;

export const lakeflowJobKpiDescriptions = {
  totalWorkflows:
    'Nombre total de workflows Databricks correspondant aux filtres et à la période sélectionnée.',
  terminalRuns:
    'Somme des runs terminés affichés sur la page courante (indicateur page, pas global).',
  avgSuccess:
    'Taux de succès moyen sur la page courante pour la période sélectionnée dans le header.',
  driftCount: 'Workflows de la page courante avec une dérive de durée > 20 % vs baseline 14 jours.',
  totalCost:
    'Somme des coûts d’exécution de tous les jobs correspondant aux filtres actifs (pas seulement la page affichée), depuis `gold_dbx_compute_job_cluster_cost_daily`. Ne couvre que les clusters de type JOB.',
  detailSuccess24h:
    'Taux de succès glissant 24 h pour ce workflow (`gold_dbx_workflow_success_rate`).',
  detailSuccess7d: 'Taux de succès glissant 7 jours pour ce workflow.',
  detailAvgDuration: 'Durée moyenne des runs sur la période header et dérive vs baseline 14 jours.',
  detailLastRun: 'Durée et horodatage du dernier run enregistré sur la période.',
} as const;

export const lakeflowRunFieldDescriptions = {
  startTime: 'Horodatage de début du run (`start_time` depuis `gold_dbx_workflow_runs`).',
  endTime: 'Horodatage de fin du run (`end_time`).',
  runId: 'Identifiant technique Databricks du run. Cliquer pour ouvrir le détail N3.',
  runType: 'Type d’exécution (job run, submit run, etc.).',
  trigger: 'Mode de déclenchement (scheduled, manual, retry, etc.).',
  duration: 'Durée totale du run (`duration_seconds`).',
  lag: 'Retard par rapport à l’heure planifiée (`schedule_lag_seconds`).',
  status: 'Statut final du run (succeeded, failed, timed_out, cancelled, running).',
  tasks: 'Nombre de tâches en échec sur le total (`tasks_failed` / `tasks_total`).',
  retries: 'Nombre de retries Databricks pour ce run (`retry_count`).',
  error: 'Code de terminaison Databricks (`error_message`) : code + message court.',
} as const;
