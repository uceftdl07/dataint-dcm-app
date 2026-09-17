"""Tests de `pipelines.gold_dbx_usage.forecast_daily` (socle predictif, data products).

`render_forecast_query`/`render_forecast_write_sql` sont des fonctions PURES
(construisent le texte SQL, ne l'executent jamais) : les assertions portent
directement sur ce texte, sans double `FakeSpark` (`ai_forecast` et
l'ecriture Delta s'executent via l'API Statement Execution contre un SQL
Warehouse, jamais via `spark.sql`, cf. docstring module `forecast_daily.py`).
"""

from __future__ import annotations

from datetime import date

from pipelines.gold_dbx_usage.forecast_daily import (
    render_forecast_query,
    render_forecast_write_sql,
)

_TABLE_POPULARITY_DAILY_TABLE = "it.sch.gold_dbx_usage_table_popularity_daily"
_TABLE_CATALOG_TABLE = "it.sch.gold_dbx_usage_table_catalog"
_TARGET_TABLE = "it.sch.gold_dbx_usage_forecast_daily"
_MERGE_KEYS = ("cloud_provider", "object_type", "object_id", "metric_name", "horizon_date")


def _forecast_query(
    *,
    observed_lower_bound: date = date(2026, 8, 24),
    horizon_date: date = date(2026, 9, 14),
    horizon_days: int = 7,
    prediction_interval_width: float = 0.95,
    min_observed_days: int = 3,
    max_observed_ratio: float = 10.0,
) -> str:
    return render_forecast_query(
        table_popularity_daily_table=_TABLE_POPULARITY_DAILY_TABLE,
        table_catalog_table=_TABLE_CATALOG_TABLE,
        observed_lower_bound=observed_lower_bound,
        horizon_date=horizon_date,
        horizon_days=horizon_days,
        prediction_interval_width=prediction_interval_width,
        min_observed_days=min_observed_days,
        max_observed_ratio=max_observed_ratio,
    )


def test_calls_ai_forecast_as_a_table_valued_function_once() -> None:
    # `ai_forecast` est table-valued : jamais un scalaire, toujours
    # `SELECT * FROM ai_forecast(...)`. Une seule source (contrairement au
    # compute qui a 5 passes sur 5 tables) -> un seul appel suffit.
    query = _forecast_query()
    assert query.count("FROM ai_forecast(") == 1


def test_all_four_metrics_are_forecast_together_in_one_multi_metric_call() -> None:
    # Les 4 metriques viennent de la MEME table source (table_popularity_daily) :
    # un seul appel ai_forecast multi-metriques (value_col => array(...), PAS
    # une chaine separee par virgule -- meme raison que
    # `gold_dbx_compute.forecast` : `'a,b'` est lue comme UN seul nom de
    # colonne litteral, jamais comme deux colonnes).
    query = _forecast_query()
    assert (
        "value_col => array(\n                'request_count', 'distinct_consumers', "
        "'estimated_cost_usd', 'data_read_bytes'\n            )"
        in query
    )


def test_horizon_date_and_prediction_interval_width_are_passed_through() -> None:
    query = _forecast_query(horizon_date=date(2026, 9, 21), prediction_interval_width=0.8)
    assert "horizon => DATE '2026-09-21'" in query
    assert "prediction_interval_width => 0.8" in query


def test_observed_is_bounded_by_lower_bound() -> None:
    # Sans cette borne, ai_forecast fitte sur la totalite de l'historique
    # disponible et produit une ligne par jour depuis le jour APRES la
    # derniere donnee reelle jusqu'a l'horizon : pour un data product sans
    # activite recente, ceci genere un volume de lignes de "prevision"
    # disproportionne. Le meme filtre a le double effet de bornage
    # d'entrainement ET d'eligibilite (aucune ligne dans la fenetre -> data
    # product absent de `observed` -> aucune prevision produite pour lui).
    # La borne est repetee sur chacune des sous-requetes de l'historique
    # densifie (eligibilite, calendrier, valeurs), sur le dernier jour observe
    # et sur les maximums observes par serie : une seule fenetre, jamais deux
    # perimetres differents.
    query = _forecast_query(observed_lower_bound=date(2026, 8, 1))
    assert query.count("period_start >= DATE '2026-08-01'") == 5


def test_the_day_in_progress_is_excluded_from_the_training_window() -> None:
    # `table_popularity_daily` porte le jour en cours des la premiere execution
    # de la journee, mais partiellement. Le modele lirait ce creux artificiel
    # comme un effondrement reel, et l'horizon s'ancrerait sur un jour
    # incomplet : la prevision ne commencerait que DEMAIN, laissant aujourd'hui
    # sans valeur ni observee ni predite.
    query = _forecast_query()
    assert query.count("AND period_start < current_date()") == 5


def test_observed_history_is_densified_with_zeros_on_days_without_reads() -> None:
    # `table_popularity_daily` n'a une ligne qu'un jour ou la table est lue.
    # Les 4 metriques etant additives, un jour sans lecture vaut 0 : sans
    # densification le modele ajuste le niveau sur les seuls jours ACTIFS et la
    # projection, lue en aval comme une valeur par jour calendaire, est
    # surevaluee du rapport jours_calendaires / jours_actifs.
    query = _forecast_query()
    assert "CROSS JOIN (\n                    SELECT DISTINCT period_start" in query
    for metric in (
        "request_count",
        "distinct_consumers",
        "estimated_cost_usd",
        "data_read_bytes",
    ):
        assert f"COALESCE(daily.{metric}, 0) AS {metric}" in query


def test_frequency_is_pinned_to_daily_rather_than_inferred() -> None:
    # `frequency` omis est inferee de la serie observee : sur une serie a trous
    # le pas inferre peut ne pas etre le jour, alors que la table cible est au
    # grain jour.
    assert "frequency => 'D'" in _forecast_query()


def test_data_products_below_min_observed_days_are_not_forecast() -> None:
    # Une table lue 1 ou 2 fois n'a pas de serie temporelle : la projeter
    # extrapole depuis un point isole, sur un volume proportionnel au parc.
    query = _forecast_query(min_observed_days=5)
    assert "HAVING COUNT(DISTINCT period_start) >= 5" in query


def test_horizon_is_capped_relative_to_the_last_observed_day() -> None:
    # `horizon` seul est un plafond absolu : une source en retard de 2 jours
    # produirait 2 jours de "prevision" deja passes et 9 lignes la ou la table
    # en annonce 7. Le plafond relatif au dernier jour observe rend le nombre
    # de jours projetes constant.
    query = _forecast_query(horizon_days=7)
    assert "WHERE period_start <= date_add(" in query
    assert f"SELECT MAX(period_start) FROM {_TABLE_POPULARITY_DAILY_TABLE}" in query
    assert ", 7)" in query


def test_all_four_metrics_are_clamped_to_non_negative() -> None:
    # request_count/distinct_consumers/estimated_cost_usd/data_read_bytes :
    # jamais negatifs (global_floor=0). Pas de plafond SCALAIRE : il serait
    # aveugle aux petites series qui explosent vers une valeur absurde mais
    # inferieure au plafond global (cf. le plafond relatif ci-dessous).
    query = _forecast_query()
    assert '{"global_floor": 0}' in query
    assert "global_cap" not in query


def test_predictions_above_the_observed_maximum_of_their_series_are_not_published() -> None:
    # `ai_forecast` ne leve aucune erreur sur une serie a decrochement : elle
    # ajuste un modele explosif et projette plusieurs ordres de grandeur
    # au-dessus du reel. Seule une borne RELATIVE a la serie l'attrape.
    query = _forecast_query(max_observed_ratio=4.0)
    for metric in (
        "request_count",
        "distinct_consumers",
        "estimated_cost_usd",
        "data_read_bytes",
    ):
        assert f"MAX({metric}) AS {metric}_max" in query
        assert f"b.{metric}_max * 4.0 AS max_plausible_value" in query
    assert "predicted_value <= max_plausible_value" in query


def test_the_upper_bound_is_clipped_to_the_same_ceiling() -> None:
    # Le filtre sur `predicted_value` laisse passer une valeur projetee
    # plausible assortie d'un intervalle de plusieurs ordres de grandeur
    # au-dessus, et l'exposition SOMME `upper_bound` sur tout le parc pour
    # tracer son enveloppe : une seule borne aberrante y ecrase la courbe du
    # realise. Ecrete et non filtre -- la ligne, elle, est plausible.
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
    # plafond la ou le modele n'a rendu aucune borne, fabriquant une valeur :
    # `CASE` preserve le NULL (`NULL > plafond` vaut NULL, branche `ELSE`).
    assert "LEAST(" not in _forecast_query()


def test_null_predictions_are_not_published() -> None:
    # Une serie degeneree rend des lignes avec `predicted_value` NULL, sans
    # erreur : les publier revient a annoncer une prevision qui n'existe pas.
    assert "WHERE predicted_value IS NOT NULL" in _forecast_query()


def test_object_key_groups_by_cloud_provider_and_table_full_name() -> None:
    # `ai_forecast` group_col n'accepte qu'UNE colonne : cle composite
    # (cloud_provider, table_full_name) concatenee avant l'appel -- 2 colonnes
    # seulement (pas de workspace_id, contrairement au compute).
    query = _forecast_query()
    assert "concat_ws('::', cloud_provider, table_full_name)" in query
    assert "AS object_key" in query
    assert "group_col => 'object_key'" in query


def test_object_key_is_split_back_into_cloud_provider_and_object_id() -> None:
    # ai_forecast ne renvoie que la cle de groupe composite en sortie : il
    # faut la re-eclater pour retrouver les colonnes d'identite d'origine.
    query = _forecast_query()
    assert "split(f.object_key, '::')[0] AS cloud_provider" in query
    assert "split(f.object_key, '::')[1] AS object_id" in query


def test_output_is_unpivoted_one_row_per_metric_always_data_product() -> None:
    query = _forecast_query()
    assert "'request_count' AS metric_name" in query
    assert "'distinct_consumers' AS metric_name" in query
    assert "'estimated_cost_usd' AS metric_name" in query
    assert "'data_read_bytes' AS metric_name" in query
    assert query.count("'DATA_PRODUCT' AS object_type") == 4
    assert "'ai_forecast' AS method" in query
    # 4 metriques -> 3 UNION ALL.
    assert query.count("UNION ALL") == 3


def test_final_select_exposes_predicted_value_and_bounds() -> None:
    query = _forecast_query()
    assert "predicted_value" in query
    assert "lower_bound" in query
    assert "upper_bound" in query
    assert "horizon_date" in query


def test_deleted_tables_are_excluded_from_the_three_observed_subqueries() -> None:
    """Filtre en ENTREE, sur les trois sous-requetes de l'historique densifie.

    Exclure en sortie laisserait la table supprimee consommer du compute
    `ai_forecast` et peser sur la densification : elle resterait dans le
    calendrier et dans le decompte d'eligibilite. L'anti-jointure porte sur la
    cle (`cloud_provider`, `table_full_name`), celle que `object_id` reconstitue.
    """
    query = _forecast_query()
    observed = query.split("observed => TABLE(")[1].split("horizon =>")[0]
    assert observed.count("LEFT ANTI JOIN (") == 3
    assert observed.count(f"FROM {_TABLE_CATALOG_TABLE}") == 3
    assert observed.count("WHERE is_deleted") == 3
    assert observed.count("ON deleted.cloud_provider = p.cloud_provider") == 3
    assert observed.count("AND deleted.table_full_name = p.table_full_name") == 3


def test_the_deleted_table_exclusion_never_reaches_the_daily_fact_tables() -> None:
    """`is_deleted` ne vit que sur le registre : le lire ailleurs signalerait une
    denormalisation sur une table de fait, dont le MERGE incremental figerait la
    valeur sur tout l'historique anterieur."""
    query = _forecast_query()
    for fragment in query.split("WHERE is_deleted")[:-1]:
        assert fragment.rstrip().endswith(_TABLE_CATALOG_TABLE)


def test_write_sql_purge_window_covers_the_whole_horizon_not_only_recomputed_keys() -> None:
    """FR-012 : les previsions d'une table devenue supprimee ne sont plus produites,
    donc plus jamais candidates a une clause restreinte aux cles recalculees.

    Seule une fenetre portant sur l'horizon ENTIER les atteint -- `NOT MATCHED BY
    SOURCE` evalue toutes les lignes cible, et la seule restriction admise est
    temporelle (les horizons deja passes restent, trace de prevision vs reel).
    """
    delete_clause = _write_query(table_exists=True).split("WHEN NOT MATCHED BY SOURCE")[1]
    assert delete_clause.strip() == "AND t.horizon_date >= current_date() THEN DELETE"
    for key in ("cloud_provider", "object_type", "object_id", "metric_name"):
        assert f"t.{key}" not in delete_clause


# ---------------------------------------------------------------------------
# render_forecast_write_sql -- l'ECRITURE complete (calcul + MERGE/CREATE)
# s'execute entierement cote SQL Warehouse, jamais via spark.createDataFrame
# (cf. docstring module -- InvalidProtocolBufferException a fort volume).
# ---------------------------------------------------------------------------


def _write_query(*, table_exists: bool) -> str:
    return render_forecast_write_sql(
        target_table=_TARGET_TABLE,
        table_exists=table_exists,
        merge_keys=_MERGE_KEYS,
        table_popularity_daily_table=_TABLE_POPULARITY_DAILY_TABLE,
        table_catalog_table=_TABLE_CATALOG_TABLE,
        observed_lower_bound=date(2026, 8, 24),
        horizon_date=date(2026, 9, 14),
        horizon_days=7,
    )


def test_write_sql_creates_table_on_first_run() -> None:
    query = _write_query(table_exists=False)
    assert f"CREATE TABLE {_TARGET_TABLE} USING DELTA AS" in query
    assert "MERGE INTO" not in query
    assert "FROM ai_forecast(" in query


def test_write_sql_merges_on_subsequent_runs() -> None:
    query = _write_query(table_exists=True)
    assert f"MERGE INTO {_TARGET_TABLE} AS t" in query
    assert "WHEN MATCHED THEN UPDATE SET *" in query
    assert "WHEN NOT MATCHED THEN INSERT *" in query
    assert "CREATE TABLE" not in query


def test_write_sql_merge_condition_covers_all_merge_keys() -> None:
    query = _write_query(table_exists=True)
    for key in _MERGE_KEYS:
        assert f"t.{key} = s.{key}" in query


def test_write_sql_purges_stale_future_horizons_and_keeps_past_ones() -> None:
    # Un MERGE pur upsert laisse indefiniment les horizons futurs d'un run
    # precedent qui ne sont plus produits (data product devenu inactif) et
    # l'API les additionne a la prevision courante. Le predicat protege
    # l'historique : seuls les horizons futurs sont reconstruits.
    query = _write_query(table_exists=True)
    assert "WHEN NOT MATCHED BY SOURCE AND t.horizon_date >= current_date() THEN DELETE" in query


def test_write_sql_deduplicates_on_merge_keys_before_writing() -> None:
    # Meme garantie que `merge_into_table`/`dropDuplicates` (evite
    # DELTA_MULTIPLE_SOURCE_ROW_MATCHING_TARGET_ROW si ai_forecast produisait
    # plus d'une ligne par cle) -- ici via ROW_NUMBER() cote SQL Warehouse.
    # Le tri porte sur `predicted_value` : `method` est une constante, donc un
    # tri sur cette colonne ne designe aucune ligne de facon deterministe.
    query = _write_query(table_exists=True)
    assert "ROW_NUMBER() OVER (" in query
    assert f"PARTITION BY {', '.join(_MERGE_KEYS)}" in query
    assert "ORDER BY predicted_value DESC NULLS LAST" in query
    assert "WHERE _row_number = 1" in query


def test_write_sql_adds_generated_at_timestamp() -> None:
    query = _write_query(table_exists=True)
    assert "current_timestamp() AS _generated_at" in query


def test_write_sql_never_builds_a_python_side_dataframe() -> None:
    # Regression : l'ancienne architecture rapatriait les lignes vers le
    # driver (`spark.createDataFrame`) -- source du bug InvalidProtocolBuffer
    # a fort volume (~530k data products actifs). Desormais tout le texte SQL
    # (calcul + ecriture) est un seul bloc execute cote warehouse.
    query = _write_query(table_exists=True)
    assert "createDataFrame" not in query

