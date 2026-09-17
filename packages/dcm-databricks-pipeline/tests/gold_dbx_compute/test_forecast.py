"""Tests de `pipelines.gold_dbx_compute.forecast` (socle predictif, clusters + warehouses).

`render_forecast_query` est une fonction PURE (construit le texte SQL, ne
l'execute jamais) : les assertions portent directement sur ce texte, sans
double `FakeSpark` (`ai_forecast` s'execute via l'API Statement Execution
contre un SQL Warehouse, pas via `spark.sql`, cf. docstring module
`forecast.py`).
"""

from __future__ import annotations

from datetime import date

from pipelines.gold_dbx_compute.forecast import _coerce_forecast_row, render_forecast_query

_COST_DAILY_TABLE = "it.sch.gold_dbx_compute_cluster_cost_daily"
_EFFICIENCY_DAILY_TABLE = "it.sch.gold_dbx_compute_cluster_efficiency_daily"
_JOB_CLUSTER_COST_DAILY_TABLE = "it.sch.gold_dbx_compute_job_cluster_cost_daily"
_PIPELINE_COST_DAILY_TABLE = "it.sch.gold_dbx_compute_pipeline_cost_daily"
_WAREHOUSE_COST_DAILY_TABLE = "it.sch.gold_dbx_compute_warehouse_cost_daily"
_WAREHOUSE_QUERY_PERFORMANCE_DAILY_TABLE = (
    "it.sch.gold_dbx_compute_warehouse_query_performance_daily"
)

# Les 6 tables source, avec le nombre de fois que chacune est lue. Une passe
# DENSIFIEE lit sa source 5 fois (objets eligibles, calendrier, agregat
# journalier, plafond d'horizon, borne de plausibilite), une passe CREUSE 4 fois
# (pas de calendrier) — cf. `_observed_sql` et `_observed_bounds_sql`. La passe
# `cpu_util_p95_pct` n'en lit que 3 : son plafond est ABSOLU (100), donc sans
# borne relative a calculer. `warehouse_query_performance_daily` porte les DEUX
# natures de metrique, donc 5 + 4.
_SOURCE_READS = (
    (_COST_DAILY_TABLE, 5),
    (_EFFICIENCY_DAILY_TABLE, 3),
    (_JOB_CLUSTER_COST_DAILY_TABLE, 5),
    (_PIPELINE_COST_DAILY_TABLE, 5),
    (_WAREHOUSE_COST_DAILY_TABLE, 5),
    (_WAREHOUSE_QUERY_PERFORMANCE_DAILY_TABLE, 9),
)

# Les 7 passes `ai_forecast` : une par table source, deux pour la performance de
# requetes (`query_count` additif, `queue_time_p95_ms` de distribution).
_FORECAST_PASSES = 7


def _forecast_query(
    *,
    observed_lower_bound: date = date(2026, 8, 25),
    horizon_date: date = date(2026, 9, 8),
    horizon_days: int = 14,
    prediction_interval_width: float = 0.95,
    min_observed_days: int = 3,
    max_observed_ratio: float = 10.0,
) -> str:
    return render_forecast_query(
        cost_daily_table=_COST_DAILY_TABLE,
        efficiency_daily_table=_EFFICIENCY_DAILY_TABLE,
        job_cluster_cost_daily_table=_JOB_CLUSTER_COST_DAILY_TABLE,
        pipeline_cost_daily_table=_PIPELINE_COST_DAILY_TABLE,
        warehouse_cost_daily_table=_WAREHOUSE_COST_DAILY_TABLE,
        warehouse_query_performance_daily_table=_WAREHOUSE_QUERY_PERFORMANCE_DAILY_TABLE,
        observed_lower_bound=observed_lower_bound,
        horizon_date=horizon_date,
        horizon_days=horizon_days,
        prediction_interval_width=prediction_interval_width,
        min_observed_days=min_observed_days,
        max_observed_ratio=max_observed_ratio,
    )


def test_calls_ai_forecast_as_a_table_valued_function() -> None:
    # `ai_forecast` est table-valued : jamais un scalaire, toujours
    # `SELECT * FROM ai_forecast(...)` (aucune API DataFrame dediee en PySpark).
    # 7 passes : cluster cost/dbu, cluster cpu, job cost/dbu, pipeline cost/dbu,
    # warehouse cost/dbu, warehouse query_count, warehouse queue_time.
    query = _forecast_query()
    assert query.count("FROM ai_forecast(") == _FORECAST_PASSES


def test_cost_and_dbu_are_forecast_together_in_one_multi_metric_call() -> None:
    # cost_usd et dbu_quantity viennent de la MEME table source (cost_daily) et
    # sont de la meme nature (additives, donc le meme historique densifie) : un
    # seul appel ai_forecast multi-metriques (value_col => array(...), PAS une
    # chaine separee par virgule - cf. docstring module/build_compute_forecast :
    # `'a,b'` leve PYTHON_TVF_REFERENCED_COLUMN_NOT_FOUND, confirme par execution
    # reelle), pas 2 appels distincts.
    query = _forecast_query()
    assert "value_col => array('cost_usd', 'dbu_quantity')" in query
    assert "value_col => 'cost_usd'" not in query
    assert "value_col => 'dbu_quantity'" not in query


def test_cluster_cost_dbu_and_cpu_exclude_job_and_pipeline_clusters() -> None:
    # Un cluster JOB/PIPELINE a en moyenne 1 seul jour d'historique reel
    # (ephemere, recree a chaque execution) : serie degeneree pour ai_forecast.
    # Exclus du grain CLUSTER ; le grain JOB est projete depuis
    # job_cluster_cost_daily, le grain PIPELINE depuis pipeline_cost_daily (T001d).
    # Le filtre accompagne CHAQUE lecture des deux tables clusters (5 pour la
    # passe densifiee cost/dbu, 3 pour la passe creuse cpu) : une lecture qui
    # l'oublierait rendrait des objets eligibles, un calendrier ou une borne de
    # plausibilite que la passe ne projette pas.
    query = _forecast_query()
    assert "AND cluster_type NOT IN ('JOB', 'PIPELINE')" in query
    assert query.count("AND cluster_type NOT IN ('JOB', 'PIPELINE')") == 8
    assert "AND cluster_type != 'JOB'" not in query


def test_cpu_utilization_is_forecast_from_the_efficiency_table_separately() -> None:
    query = _forecast_query()
    assert "value_col => 'cpu_util_p95_pct'" in query
    assert f"FROM {_EFFICIENCY_DAILY_TABLE}" in query


def test_job_cost_and_dbu_are_forecast_together_from_job_cluster_cost_daily() -> None:
    # Rollup stable dans le temps (job_id), contrairement au grain cluster
    # ephemere exclu ci-dessus.
    query = _forecast_query()
    assert f"FROM {_JOB_CLUSTER_COST_DAILY_TABLE}" in query
    assert "concat_ws('::', cloud_provider, workspace_id, job_id)" in query


def test_pipeline_cost_and_dbu_are_forecast_together_from_pipeline_cost_daily() -> None:
    # Rollup billing-direct au grain dlt_pipeline_id (stable dans le temps),
    # contrairement au cluster PIPELINE ephemere exclu du grain CLUSTER. Pas de
    # filtre cluster_type : la table pipeline_cost_daily n'a pas cette colonne.
    query = _forecast_query()
    assert "pipeline_cost_and_dbu_forecast AS (" in query
    assert "concat_ws('::', cloud_provider, workspace_id, dlt_pipeline_id)" in query
    assert "cluster_type" not in query.split("pipeline_cost_and_dbu_forecast AS (")[1].split(
        "),"
    )[0]


def test_pipeline_observed_series_is_aggregated_across_compute_kind() -> None:
    # REGRESSION (T008) : la table source porte `compute_kind` dans son grain,
    # donc DEUX lignes le meme jour pour un pipeline mixte. Sans agregation,
    # `ai_forecast` recoit deux points au meme horodatage dans la meme serie
    # (`object_key` ne contient pas `compute_kind`) -- serie invalide, et rien
    # dans la requete ne le signalerait. La somme conserve la semantique voulue :
    # une prevision par pipeline, toutes formes de compute confondues.
    query = _forecast_query()
    assert "SUM(cost_usd) AS cost_usd" in query
    assert "SUM(dbu_quantity) AS dbu_quantity" in query
    # Groupe sur l'expression de cle ELLE-MEME (pas un alias : Spark n'autorise
    # pas un alias de SELECT dans un GROUP BY) + le jour.
    assert (
        "GROUP BY concat_ws('::', cloud_provider, workspace_id, dlt_pipeline_id), period_start"
        in query
    )
    # L'agregation au grain (objet, jour) est desormais SYSTEMATIQUE (les 4
    # passes additives, cf. `_observed_sql`) et non reservee aux deux sources a
    # `compute_kind` : elle n'a aucun effet sur une source deja au grain, et la
    # densification a besoin d'un agregat unique par jour de toute facon. Les
    # bornes de plausibilite reutilisent le meme agregat, d'ou le doublement.
    assert query.count("SUM(cost_usd)") == 8
    # `compute_kind` n'entre PAS dans object_key : la prevision reste par
    # pipeline. L'y ajouter serait un changement de contrat de sortie
    # (`_split_object_key_columns` n'eclate que 3 champs).
    assert "dlt_pipeline_id, compute_kind" not in query


def test_job_observed_series_is_aggregated_across_compute_kind() -> None:
    # REGRESSION (T001b) : meme piege que cote pipeline, en plus massif -- 926
    # jours-job mixtes mesures en dev contre 2 pipelines. La table source porte
    # `compute_kind` dans son grain, donc DEUX lignes le meme jour pour un job
    # mixte ; sans agregation `ai_forecast` recoit deux points au meme horodatage
    # dans la meme serie (`object_key` ne contient pas `compute_kind`) -- serie
    # invalide, et rien dans la requete ne le signalerait.
    query = " ".join(_forecast_query().split())
    assert (
        "SELECT concat_ws('::', cloud_provider, workspace_id, job_id) AS object_key, "
        "period_start, SUM(cost_usd) AS cost_usd, SUM(dbu_quantity) AS dbu_quantity "
        f"FROM {_JOB_CLUSTER_COST_DAILY_TABLE}" in query
    )
    # Groupe sur l'expression de cle ELLE-MEME (pas un alias : Spark n'autorise
    # pas un alias de SELECT dans un GROUP BY) + le jour.
    assert (
        "GROUP BY concat_ws('::', cloud_provider, workspace_id, job_id), period_start" in query
    )
    # `compute_kind` n'entre PAS dans object_key : la prevision reste par job,
    # toutes formes confondues. L'y ajouter serait un changement de contrat de
    # sortie (`_split_object_key_columns` n'eclate que 3 champs).
    assert "job_id, compute_kind" not in query


def test_additive_metrics_are_densified_with_zeros_on_the_days_without_activity() -> None:
    # LE point qui fausse une projection de cout : sans les jours a 0, le modele
    # ajuste le niveau sur les seuls jours ACTIFS, alors que l'aval lit la sortie
    # comme une valeur par jour CALENDAIRE -- surevaluation du rapport
    # jours_calendaires / jours_actifs (un cluster allume 5 jours sur 7 se voit
    # projeter ses jours ouvres comme des jours moyens). Les 5 passes additives
    # (4 x cost/dbu + query_count) croisent donc les objets eligibles avec le
    # calendrier de la fenetre, et comblent l'absence de ligne par 0.
    query = " ".join(_forecast_query().split())
    assert query.count("CROSS JOIN ( SELECT DISTINCT period_start") == 5
    assert query.count("COALESCE(daily.cost_usd, 0) AS cost_usd") == 4
    assert query.count("COALESCE(daily.dbu_quantity, 0) AS dbu_quantity") == 4
    assert query.count("COALESCE(daily.query_count, 0) AS query_count") == 1
    assert query.count("LEFT JOIN") == 5


def test_distribution_metrics_keep_a_sparse_history() -> None:
    # Un jour ou le cluster est eteint coute 0 $ mais n'a pas une utilisation CPU
    # de 0 % : il n'en a AUCUNE. Densifier a 0 ferait baisser un p95 qui n'a pas
    # bouge. Les deux passes de distribution restent donc creuses (pas de
    # calendrier, pas de COALESCE) et agregent au MAX, un p95 ne se sommant pas.
    query = " ".join(_forecast_query().split())
    assert "SELECT daily.object_key, daily.period_start, daily.cpu_util_p95_pct" in query
    assert "SELECT daily.object_key, daily.period_start, daily.queue_time_p95_ms" in query
    assert "MAX(cpu_util_p95_pct) AS cpu_util_p95_pct" in query
    assert "MAX(queue_time_p95_ms) AS queue_time_p95_ms" in query
    assert "COALESCE(daily.cpu_util_p95_pct" not in query
    assert "COALESCE(daily.queue_time_p95_ms" not in query


def test_the_densification_calendar_only_contains_days_the_source_has_delivered() -> None:
    # Le calendrier est l'ensemble des jours DISTINCTS presents dans la fenetre,
    # jamais un `sequence()` de dates fabriquees : un jour que la source n'a pas
    # encore charge (retard de collecte de 3-8 jours mesure sur la curated)
    # serait densifie a 0 et tirerait la projection vers le bas.
    query = _forecast_query()
    assert "sequence(" not in query
    assert "explode(" not in query
    # Un calendrier par passe additive, chacun lu sur SA source : deux sources de
    # fraicheur differente n'ont pas le meme dernier jour charge.
    assert query.count("SELECT DISTINCT period_start") == 5


def test_objects_with_too_little_history_are_excluded_from_every_pass() -> None:
    # Un objet vu 1 seul jour n'a pas de serie temporelle : le projeter extrapole
    # depuis un point isole, sur un volume proportionnel au parc (99,22 % des
    # `cluster_id` reels n'ont qu'un jour d'historique). Le filtre porte sur les
    # jours d'activite REELLE, donc sur la source AVANT densification -- sinon
    # tout objet aurait autant de jours que le calendrier.
    query = _forecast_query(min_observed_days=5)
    assert query.count("HAVING COUNT(DISTINCT period_start) >= 5") == _FORECAST_PASSES
    # Les deux formes d'historique restreignent bien sur cette liste : jointure
    # interne cote creux, base du produit cartesien cote densifie.
    assert "ON eligible.object_key = daily.object_key" in query
    assert "ON daily.object_key = eligible.object_key" in query


def test_frequency_is_pinned_to_daily_rather_than_inferred() -> None:
    # `ai_forecast` infere le pas de temps de la serie qu'on lui donne : sur un
    # historique a trous, le pas infere peut ne pas etre le jour, et la sortie
    # n'est alors plus comparable au grain journalier de la table cible.
    query = _forecast_query()
    assert query.count("frequency => 'D'") == _FORECAST_PASSES


def test_each_pass_caps_its_horizon_on_its_own_last_observed_day() -> None:
    # `horizon` est une date ABSOLUE : le nombre de jours projetes varie donc
    # avec la fraicheur de la source (une source en retard de 2 jours produit 2
    # jours de "prevision" deja passes, et 9 lignes la ou la table en annonce 7).
    # Chaque passe est plafonnee sur SON dernier jour observe, les 6 sources
    # n'ayant pas la meme fraicheur.
    query = " ".join(_forecast_query(horizon_days=7).split())
    window = "WHERE period_start >= DATE '2026-08-25' AND period_start < current_date()"
    for table in (
        _JOB_CLUSTER_COST_DAILY_TABLE,
        _PIPELINE_COST_DAILY_TABLE,
        _WAREHOUSE_COST_DAILY_TABLE,
        _WAREHOUSE_QUERY_PERFORMANCE_DAILY_TABLE,
    ):
        assert (
            "WHERE period_start >= current_date() AND period_start <= date_add("
            f"(SELECT MAX(period_start) FROM {table} {window}), 7)" in query
        ), table
    # Les deux passes clusters cherchent ce dernier jour sur la MEME population
    # que celle qu'elles projettent (exclusion JOB/PIPELINE incluse).
    for table in (_COST_DAILY_TABLE, _EFFICIENCY_DAILY_TABLE):
        assert (
            "WHERE period_start >= current_date() AND period_start <= date_add("
            f"(SELECT MAX(period_start) FROM {table} {window} "
            "AND cluster_type NOT IN ('JOB', 'PIPELINE')), 7)" in query
        ), table
    assert query.count("date_add(") == _FORECAST_PASSES


def test_no_pass_publishes_a_horizon_that_is_already_past() -> None:
    # Sur une passe de DISTRIBUTION la serie reste creuse : `ai_forecast` repart
    # de la derniere observation de CHAQUE objet, parfois vieille de plusieurs
    # jours (4 mesures en dev sur `queue_time_p95_ms`). Sans cette borne, la
    # table porte des "previsions" datees d'hier.
    query = _forecast_query()
    assert query.count("WHERE period_start >= current_date() AND period_start <= date_add(") == (
        _FORECAST_PASSES
    )


def test_query_count_and_queue_time_are_forecast_in_two_separate_passes() -> None:
    # Meme table source, mais deux natures de metrique : `query_count` est
    # additif (densifie a 0), `queue_time_p95_ms` est une distribution (serie
    # creuse). Un seul appel multi-metriques imposerait le meme historique aux
    # deux, donc soit des zeros sur un p95, soit l'absence de zeros sur un
    # compte.
    query = _forecast_query()
    assert "warehouse_query_count_forecast AS (" in query
    assert "warehouse_queue_time_forecast AS (" in query
    assert "value_col => 'query_count'" in query
    assert "value_col => 'queue_time_p95_ms'" in query
    assert "value_col => array('query_count', 'queue_time_p95_ms')" not in query


def test_warehouse_cost_and_dbu_are_forecast_together_from_warehouse_cost_daily() -> None:
    query = _forecast_query()
    assert "warehouse_cost_and_dbu_forecast AS (" in query
    assert f"FROM {_WAREHOUSE_COST_DAILY_TABLE}" in query


def test_horizon_date_and_prediction_interval_width_are_passed_through() -> None:
    query = _forecast_query(horizon_date=date(2026, 9, 8), prediction_interval_width=0.8)
    assert "horizon => DATE '2026-09-08'" in query
    assert "prediction_interval_width => 0.8" in query


def test_every_read_of_every_source_is_bounded_by_the_training_window() -> None:
    # Sans cette borne, ai_forecast fitte sur la totalite de l'historique
    # disponible et produit une ligne par jour depuis le jour APRES la
    # derniere donnee reelle jusqu'a l'horizon : pour un objet ephemere sans
    # activite depuis des mois/annees, ceci genere des centaines/milliers de
    # lignes de "prevision" pour un objet qui n'existe plus. Le meme filtre a le
    # double effet de bornage d'entrainement ET d'eligibilite (aucune ligne dans
    # la fenetre -> objet absent de `observed` -> aucune prevision produite).
    # L'invariant porte sur CHAQUE lecture : une sous-requete non bornee
    # (calendrier, plafond d'horizon) reintroduirait l'historique complet par un
    # autre chemin.
    query = _forecast_query(observed_lower_bound=date(2026, 8, 12))
    window = "WHERE period_start >= DATE '2026-08-12' AND period_start < current_date()"
    for table, reads in _SOURCE_READS:
        fragments = query.split(f"FROM {table}")[1:]
        assert len(fragments) == reads, table
        for fragment in fragments:
            assert fragment.lstrip().startswith(window), table


def test_the_day_in_progress_is_excluded_from_every_training_window() -> None:
    # Les tables `*_daily` portent le jour en cours des la premiere execution de
    # la journee, mais partiellement (562 $ de cout job a la mi-journee contre
    # ~4 400 $ sur une journee pleine, mesure en dev). Le modele lit ce creux
    # comme un effondrement reel, et l'horizon s'ancre sur un jour incomplet :
    # la prevision ne commence alors que DEMAIN, laissant aujourd'hui sans
    # valeur ni observee ni predite.
    query = _forecast_query()
    assert query.count("AND period_start < current_date()") == sum(
        reads for _, reads in _SOURCE_READS
    )


def test_predictions_above_the_observed_maximum_of_their_series_are_not_published() -> None:
    # `ai_forecast` ne leve aucune erreur sur une serie degeneree : elle ajuste
    # un modele explosif et projette plusieurs ordres de grandeur au-dessus du
    # reel (867 M$ projetes au grain JOB pour ~4 400 $/jour observes). Un
    # plafond scalaire est aveugle a ce cas : seule une borne RELATIVE a la
    # serie l'attrape.
    query = _forecast_query(max_observed_ratio=4.0)
    for metric in ("cost_usd", "dbu_quantity", "query_count", "queue_time_p95_ms"):
        assert f"MAX({metric}) AS {metric}_max" in query
        assert f"b.{metric}_max * 4.0 AS max_plausible_value" in query
    assert "predicted_value <= max_plausible_value" in query


def test_the_upper_bound_is_clipped_to_the_same_ceiling() -> None:
    # Le filtre sur `predicted_value` laisse passer une valeur projetee
    # plausible assortie d'un intervalle de plusieurs ordres de grandeur
    # au-dessus, et l'exposition AGREGE `upper_bound` sur tout le parc pour
    # tracer sa bande : une seule borne aberrante y ecrase la courbe du realise,
    # y compris avec la combinaison en quadrature de l'exposition (un terme tres
    # superieur aux autres domine la racine). Ecrete et non filtre -- la ligne,
    # elle, est plausible.
    query = _forecast_query()
    assert (
        "CASE WHEN upper_bound > max_plausible_value"
        " THEN max_plausible_value ELSE upper_bound END AS upper_bound" in query
    )
    # La borne BASSE n'est pas ecretee : `global_floor` la tient a 0 par le bas,
    # et elle reste sous `predicted_value`, deja plafonnee par le `WHERE`.
    assert "ELSE lower_bound END" not in query


def test_the_clipped_upper_bound_never_fabricates_a_missing_bound() -> None:
    # `LEAST(upper_bound, max_plausible_value)` IGNORE les NULL et renverrait le
    # plafond la ou le modele n'a rendu aucune borne : `CASE` preserve le NULL
    # (`NULL > plafond` vaut NULL, donc la branche `ELSE`), meme convention que
    # `_coerce_forecast_row`.
    assert "LEAST(" not in _forecast_query()


def test_the_percentage_metric_keeps_its_absolute_ceiling() -> None:
    # Un taux d'utilisation qui passe de 8 % a 90 % est invraisemblable pour un
    # modele, pas impossible dans les faits : la borne relative l'ecarterait a
    # tort. 100 est la seule valeur que la metrique ne peut pas depasser, et
    # c'est deja `global_cap`.
    query = _forecast_query()
    assert "100 AS max_plausible_value" in query
    assert "cpu_util_p95_pct_max" not in query


def test_null_predictions_are_not_published() -> None:
    # Une serie degeneree rend des lignes avec `predicted_value` NULL, sans
    # erreur : 224 mesurees en dev sur le seul `queue_time_p95_ms`. Les publier
    # revient a annoncer une prevision qui n'existe pas.
    assert "WHERE predicted_value IS NOT NULL" in _forecast_query()


def test_forecasts_are_clamped_to_business_valid_ranges() -> None:
    # cout/DBU/query_count/queue_time : jamais negatifs (global_floor=0).
    # cpu_util_p95_pct : pourcentage, jamais negatif NI au-dela de 100
    # (global_floor=0, global_cap=100).
    query = _forecast_query()
    assert '{"global_floor": 0}' in query
    assert '{"global_floor": 0, "global_cap": 100}' in query


def test_object_key_groups_by_cloud_provider_workspace_and_cluster_job_or_warehouse() -> None:
    # `ai_forecast` group_col n'accepte qu'UNE colonne : cle composite
    # (cloud_provider, workspace_id, cluster_id/job_id/dlt_pipeline_id/warehouse_id)
    # concatenee avant l'appel.
    query = _forecast_query()
    assert "concat_ws('::', cloud_provider, workspace_id, cluster_id)" in query
    assert "concat_ws('::', cloud_provider, workspace_id, job_id)" in query
    assert "concat_ws('::', cloud_provider, workspace_id, dlt_pipeline_id)" in query
    assert "concat_ws('::', cloud_provider, workspace_id, warehouse_id)" in query
    assert "AS object_key" in query
    assert query.count("group_col => 'object_key'") == _FORECAST_PASSES


def test_object_key_is_split_back_into_cloud_provider_workspace_and_object_id() -> None:
    # ai_forecast ne renvoie que la cle de groupe composite en sortie : il faut
    # la re-eclater pour retrouver les colonnes d'identite d'origine.
    query = _forecast_query()
    assert "split(f.object_key, '::')[0] AS cloud_provider" in query
    assert "split(f.object_key, '::')[1] AS workspace_id" in query
    assert "split(f.object_key, '::')[2] AS object_id" in query


def test_pipeline_has_no_efficiency_or_cpu_forecast_pass() -> None:
    # Aucune table d'efficacite au grain pipeline (hors scope) : seules cost_usd
    # et dbu_quantity sont projetees pour PIPELINE, jamais cpu_util_p95_pct.
    query = _forecast_query()
    # cpu_util_p95_pct n'est projete qu'UNE fois, au grain CLUSTER (une passe
    # ai_forecast, une metrique unpivotee).
    assert query.count("value_col => 'cpu_util_p95_pct'") == 1
    assert query.count("'cpu_util_p95_pct' AS metric_name") == 1
    # Les deux blocs PIPELINE ne referencent aucune metrique d'efficacite.
    pipeline_blocks = query.split("'PIPELINE' AS object_type")
    assert len(pipeline_blocks) == 3  # 2 blocs -> le split produit 3 fragments
    for fragment in pipeline_blocks[1:]:
        block = fragment.split("FROM pipeline_cost_and_dbu_forecast f")[0]
        assert "cpu_util" not in block


def test_pipeline_cost_and_dbu_unpivoted_read_the_pipeline_cte() -> None:
    query = _forecast_query()
    # Les deux blocs PIPELINE lisent la CTE pipeline_cost_and_dbu_forecast.
    assert query.count("FROM pipeline_cost_and_dbu_forecast f") == 2
    assert query.count("'PIPELINE' AS object_type") == 2


def test_output_is_unpivoted_one_row_per_metric_with_object_type_per_source() -> None:
    query = _forecast_query()
    assert "'cost_usd' AS metric_name" in query
    assert "'dbu_quantity' AS metric_name" in query
    assert "'cpu_util_p95_pct' AS metric_name" in query
    assert "'query_count' AS metric_name" in query
    assert "'queue_time_p95_ms' AS metric_name" in query
    assert "'CLUSTER' AS object_type" in query
    assert "'JOB' AS object_type" in query
    assert "'PIPELINE' AS object_type" in query
    assert "'WAREHOUSE' AS object_type" in query
    assert "'ai_forecast' AS method" in query
    # 11 blocs SELECT (cluster cost/dbu/cpu=3, job cost/dbu=2, pipeline
    # cost/dbu=2, warehouse cost/dbu/query/queue=4) -> 10 UNION ALL. Les deux
    # metriques de performance de requetes viennent de deux CTE distinctes.
    assert query.count("UNION ALL") == 10
    assert query.count("FROM warehouse_query_count_forecast f") == 1
    assert query.count("FROM warehouse_queue_time_forecast f") == 1


def test_final_select_exposes_predicted_value_and_bounds() -> None:
    query = _forecast_query()
    assert "predicted_value" in query
    assert "lower_bound" in query
    assert "upper_bound" in query
    assert "horizon_date" in query


# ---------------------------------------------------------------------------
# _coerce_forecast_row — l'API Statement Execution (format JSON_ARRAY)
# renvoie TOUTES les valeurs comme des chaines, y compris DATE/DOUBLE.
# ---------------------------------------------------------------------------


def test_coerce_forecast_row_parses_date_and_doubles() -> None:
    row = [
        "azure", "2978268189007815", "CLUSTER", "0425-145023-jptyise4", "cost_usd",
        "2026-09-08", "12.5", "10.1", "14.9", "ai_forecast",
    ]
    result = _coerce_forecast_row(row)
    assert result == (
        "azure", "2978268189007815", "CLUSTER", "0425-145023-jptyise4", "cost_usd",
        date(2026, 9, 8), 12.5, 10.1, 14.9, "ai_forecast",
    )


def test_coerce_forecast_row_preserves_null_bounds() -> None:
    # Un NULL source (ex. borne d'intervalle non calculable) reste None, jamais
    # une valeur fabriquee.
    row = [
        "aws", "1781037120728603", "WAREHOUSE", "a3b6ba2ae6a22781", "query_count",
        "2026-09-01", None, None, None, "ai_forecast",
    ]
    result = _coerce_forecast_row(row)
    assert result == (
        "aws", "1781037120728603", "WAREHOUSE", "a3b6ba2ae6a22781", "query_count",
        date(2026, 9, 1), None, None, None, "ai_forecast",
    )
