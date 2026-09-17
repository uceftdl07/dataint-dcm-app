"""Tests de `pipelines.gold_dbx_usage.table_daily` (regles de derivation).

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`) :
`build_table_daily` construit un unique `spark.sql(...)`, verifie ici via le
texte SQL genere (`FakeSpark`).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from pipelines.gold_dbx_usage.ephemeral_tables import (
    EPHEMERAL_KEYS_CTE_NAME,
    not_ephemeral_predicate,
)
from pipelines.gold_dbx_usage.table_daily import build_table_daily
from tests.conftest import strip_sql_comments


def _table_daily_query(fakes: SimpleNamespace, lower_bound: date | None) -> str:
    sentinel = fakes.DataFrame("table_daily_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_table_daily(
        spark,
        lineage_table="it.sch.curated_dbx_access_table_lineage",
        access_audit_table="it.sch.curated_dbx_access_audit",
        query_history_table="it.sch.curated_dbx_query_history",
        billing_usage_table="it.sch.curated_dbx_billing_usage",
        billing_list_prices_table="it.sch.curated_dbx_billing_list_prices",
        uc_tables_table="it.sch.curated_dbx_uc_tables",
        table_operations_table="it.sch.curated_dbx_uc_table_operations",
        lower_bound=lower_bound,
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0]


def test_table_daily_full_run_has_no_lower_bound_filter(fakes: SimpleNamespace) -> None:
    query = _table_daily_query(fakes, lower_bound=None)
    assert "event_date >= DATE" not in query
    assert "usage_date >= DATE" not in query
    assert "period_start >= DATE" not in query


def test_table_daily_incremental_run_filters_all_source_windows(
    fakes: SimpleNamespace,
) -> None:
    query = _table_daily_query(fakes, lower_bound=date(2026, 8, 14))
    assert "AND event_date >= DATE '2026-08-14'" in query
    assert "AND to_date(start_time) >= DATE '2026-08-14'" in query
    assert "AND usage_date >= DATE '2026-08-14'" in query
    assert "AND period_start >= DATE '2026-08-14'" in query


def test_table_daily_unions_query_non_query_and_audit_reads(
    fakes: SimpleNamespace,
) -> None:
    query = _table_daily_query(fakes, lower_bound=None)
    assert "FROM query_reads" in query
    assert "FROM non_query_reads" in query
    assert "FROM audit_reads" in query
    assert query.count("UNION ALL") >= 2


def test_table_daily_flags_unknown_data_product_via_left_join_uc_tables(
    fakes: SimpleNamespace,
) -> None:
    query = _table_daily_query(fakes, lower_bound=None)
    assert "LEFT JOIN it.sch.curated_dbx_uc_tables uc" in query
    assert "(uc.table_catalog IS NULL) AS unknown_data_product" in query


def test_table_daily_separates_a_missing_object_from_an_invisible_one(
    fakes: SimpleNamespace,
) -> None:
    """`unknown_data_product` confond deux situations opposees.

    Le registre vient de `system.information_schema.tables`, filtree par privilege
    et OBJET PAR OBJET : « absent du registre » peut vouloir dire « n'existe pas »
    comme « le pipeline n'a pas le droit de le voir ». Le second cas est de loin le
    plus frequent.
    """
    query = _table_daily_query(fakes, lower_bound=None)
    assert "END AS catalog_resolution_status" in query
    assert "THEN 'RESOLVED'" in query
    assert "THEN 'NOT_VISIBLE_TO_PIPELINE'" in query
    assert "ELSE 'NEVER_RESOLVED'" in query


def test_table_daily_existence_is_proven_by_a_successful_access(
    fakes: SimpleNamespace,
) -> None:
    """Toute ligne de lineage prouve l'existence, un `getTable` seulement si `200`.

    C'est le seul discriminant fiable : la visibilite du CATALOGUE n'en est pas un,
    le filtrage par privilege de `information_schema.tables` s'appliquant objet par
    objet.
    """
    query = strip_sql_comments(_table_daily_query(fakes, lower_bound=None))
    # Trois branches lineage-derivees (query_reads, non_query_reads, query_writes).
    assert query.count("TRUE AS existence_proven") == 3
    assert "response['status_code'] = '200' AS existence_proven" in query
    # Un seul acces reussi suffit : les echecs des autres branches ne retirent pas
    # la preuve (OR logique, pas AND).
    assert "MAX(existence_proven) AS existence_proven" in query


def test_table_daily_resolution_status_is_stable_across_window_widths(
    fakes: SimpleNamespace,
) -> None:
    """La fenetre du statut porte sur l'OBJET-JOUR, `period_start` inclus.

    Sans lui, le statut d'un jour dependrait de la largeur de la fenetre
    incrementale recalculee : un meme jour reecrit changerait de valeur sans
    qu'aucune donnee amont n'ait bouge.
    """
    query = _table_daily_query(fakes, lower_bound=None)
    partition = (
        "PARTITION BY a.cloud_provider, a.period_start,\n"
        "                             a.catalog, a.schema, a.table_name"
    )
    assert partition in query


def test_table_daily_cost_attribution_is_equal_parts_fallback_and_documented(
    fakes: SimpleNamespace,
) -> None:
    query = _table_daily_query(fakes, lower_bound=None)
    assert "'equal_parts_fallback'" in query
    assert "n_tables" in query
    # La methode ne doit PAS etre reaffirmee en dur a l'agregation : le litteral en
    # dur ecrasait la valeur des branches et annoncait une attribution meme sur un
    # groupe dont aucune ligne n'avait de cout.
    aggregated_cte = query.split("aggregated AS (")[1]
    assert "MAX(cost_attribution_method) AS cost_attribution_method" in aggregated_cte
    assert "'equal_parts_fallback'" not in aggregated_cte


def test_table_daily_serverless_job_bucket_cannot_double_count_a_billing_row(
    fakes: SimpleNamespace,
) -> None:
    """Les trois seaux doivent partitionner `billing_usage`, pas le recouvrir.

    Le seau serverless est le seul a se rattacher par `job_id` -- une cle que portent
    AUSSI les lignes de facture d'un job sur cluster, deja prises par `cluster_usage`.
    Sans l'exigence d'absence de cluster et de warehouse, ces lignes entreraient dans
    deux seaux et leur cout serait compte deux fois.
    """
    query = strip_sql_comments(_table_daily_query(fakes, lower_bound=None))
    job_cte = query.split("serverless_job_usage AS (")[1].split("billing_buckets AS (")[0]
    assert "usage_metadata.cluster_id IS NULL" in job_cte
    assert "usage_metadata.warehouse_id IS NULL" in job_cte
    assert "usage_metadata.job_id IS NOT NULL" in job_cte
    assert "usage_metadata.job_id AS cost_bucket_id" in job_cte
    # Et symetriquement : les deux autres seaux ne regardent pas `job_id`.
    compute_ctes = query.split("cluster_usage AS (")[1].split("serverless_job_usage AS (")[0]
    assert "job_id" not in compute_ctes


def test_table_daily_serverless_bridge_uses_the_key_query_history_actually_carries(
    fakes: SimpleNamespace,
) -> None:
    """Le pont serverless passe par `query_source.job_info.job_id`, cote requete.

    `compute.warehouse_id` n'est renseigne que pour un SQL warehouse et
    `compute.cluster_id` pour aucun statement : sans ce second pont, tout ce qui n'est
    pas warehouse resterait sans cout alors que sa facture existe. Le compute dedie
    prime sur le job, pour ne pas imputer a la facture serverless d'un job un statement
    que son warehouse facture deja.

    Le `CASE` qui NOMME le seau doit suivre le `COALESCE` qui l'IDENTIFIE terme par
    terme : desynchroniser les deux ferait joindre un identifiant sous l'etiquette d'un
    autre seau, donc chercher sa facture au mauvais endroit.
    """
    query = strip_sql_comments(_table_daily_query(fakes, lower_bound=None))
    history_cte = query.split("query_history_filtered AS (")[1].split("cluster_usage AS (")[0]
    assert (
        "COALESCE(\n                compute.cluster_id, compute.warehouse_id, "
        "query_source.job_info.job_id\n            ) AS cost_bucket_id" in history_cte
    )
    bucket_order = ("cluster_prorata", "warehouse_prorata", "serverless_job_prorata")
    source_order = ("compute.cluster_id", "compute.warehouse_id", "query_source.job_info.job_id")
    case_body = history_cte.split("CASE")[1].split("END AS cost_basis")[0]
    for label, source in zip(bucket_order, source_order, strict=True):
        assert f"WHEN {source} IS NOT NULL" in case_body
        assert f"'{label}'" in case_body
    positions = [case_body.index(f"'{label}'") for label in bucket_order]
    assert positions == sorted(positions)
    assert [case_body.index(f"WHEN {s} IS NOT NULL") for s in source_order] == sorted(
        case_body.index(f"WHEN {s} IS NOT NULL") for s in source_order
    )


def test_table_daily_cost_join_discriminates_on_the_bucket_kind(
    fakes: SimpleNamespace,
) -> None:
    """`cost_basis` appartient a la cle de jointure, pas seulement `cost_bucket_id`.

    Les identifiants de job, de cluster et de warehouse viennent d'espaces distincts,
    mais rien ne garantit qu'ils ne collident jamais. Joindre sur le seul
    `cost_bucket_id` rattacherait alors un statement a la facture d'un autre seau.
    """
    query = strip_sql_comments(_table_daily_query(fakes, lower_bound=None))
    cost_cte = query.split("query_cost AS (")[1].split("query_reads AS (")[0]
    for alias in ("cdc", "cdd"):
        assert f"{alias}.cost_basis = qh.cost_basis" in cost_cte
        assert f"{alias}.cost_bucket_id = qh.cost_bucket_id" in cost_cte
    # Le grain du cout et celui du denominateur doivent etre le meme, sinon le prorata
    # divise par la duree d'une autre population.
    grain = "GROUP BY cloud_provider, workspace_id, cost_basis, cost_bucket_id, period_start"
    for cte in ("bucket_daily_cost AS (", "bucket_daily_duration AS ("):
        assert grain in query.split(cte)[1].split("),")[0]


def test_table_daily_cost_basis_is_only_asserted_where_a_cost_exists(
    fakes: SimpleNamespace,
) -> None:
    """La base annoncee suit le COUT, pas le rattachement.

    Un statement rattache a un seau dont la facture manque garde son `cost_bucket_id`
    mais n'a pas de cout : annoncer sa base decrirait un calcul qui n'a pas eu lieu.
    Les branches sans requete du tout n'en annoncent aucune non plus.
    """
    query = _table_daily_query(fakes, lower_bound=None)
    reads_cte = query.split("query_reads AS (")[1].split("non_query_reads AS (")[0]
    assert (
        "CASE WHEN qc.query_cost_usd IS NULL THEN CAST(NULL AS STRING)\n"
        "                 ELSE qc.cost_basis END AS cost_basis" in reads_cte
    )
    for branch, end in (
        ("non_query_reads AS (", "audit_reads AS ("),
        ("audit_reads AS (", "query_write_volumes AS ("),
        ("query_writes AS (", "all_reads AS ("),
    ):
        body = query.split(branch)[1].split(end)[0]
        assert "CAST(NULL AS STRING) AS cost_basis" in body


def test_table_daily_mixed_cost_bases_are_named_not_silently_picked(
    fakes: SimpleNamespace,
) -> None:
    """Un groupe qui additionne deux seaux le DIT, au lieu d'en designer un.

    Un warehouse et un job serverless peuvent lire la meme table le meme jour. Les
    deux bases ne mesurent pas la meme grandeur -- la facture d'un job couvre son code
    non-SQL -- donc un `MAX()` seul ferait passer un total mixte pour un total d'une
    seule base, au hasard de l'ordre alphabetique.
    """
    query = strip_sql_comments(_table_daily_query(fakes, lower_bound=None))
    aggregated_cte = query.split("aggregated AS (")[1]
    assert (
        "CASE WHEN COUNT(DISTINCT cost_basis) > 1 THEN 'mixed'\n"
        "                 ELSE MAX(cost_basis) END AS cost_basis" in aggregated_cte
    )
    assert "a.cost_basis" in query.split("FROM aggregated a")[0]


def test_table_daily_no_source_lz_id_or_subscription_account_id() -> None:
    import inspect

    from pipelines.gold_dbx_usage import table_daily

    source = inspect.getsource(table_daily)
    assert "source_lz_id" not in source
    assert "subscription_or_account_id" not in source


def test_table_daily_grain_columns_present_in_select(fakes: SimpleNamespace) -> None:
    query = _table_daily_query(fakes, lower_bound=None)
    for column in ("cloud_provider", "catalog", "schema", "table_name", "consumer_id"):
        assert f"a.{column}" in query
    assert "a.period_start" in query
    assert "usage_date" in query  # alias historique conserve


def test_table_daily_read_branches_discriminate_on_statement_id_not_entity_type(
    fakes: SimpleNamespace,
) -> None:
    """Le critere de joignabilite a `query_history` est `statement_id`, pas `entity_type`.

    `DBSQL_QUERY` ne couvre qu'une part marginale du lineage, tandis que la majorite
    des lignes portent un `statement_id` joignable -- `entity_type` NULL et `JOB`
    compris. Router le volume sur `entity_type` enverrait donc l'essentiel des
    lectures MESURABLES vers `non_query_reads`, qui les publie sans volume.
    """
    query = _table_daily_query(fakes, lower_bound=None)
    assert "WHERE entity_type = 'DBSQL_QUERY'" not in query
    assert "entity_type IS DISTINCT FROM 'DBSQL_QUERY'" not in query
    assert "entity_type = 'QUERY'" not in query
    lineage_cte = query.split("query_lineage AS (")[1].split("query_table_counts AS (")[0]
    assert "WHERE statement_id IS NOT NULL" in lineage_cte
    non_query_cte = query.split("non_query_reads AS (")[1].split("audit_reads AS (")[0]
    # Partition EXHAUSTIVE et NULL-safe par construction : `IS NULL`/`IS NOT NULL`
    # sur la meme colonne, la ou `= 'X'` / `IS DISTINCT FROM 'X'` exigeait un helper
    # dedie pour ne pas perdre les lignes a `entity_type` NULL.
    assert "WHERE statement_id IS NULL" in non_query_cte


def test_table_daily_volume_population_is_not_gated_on_billing_attachment(
    fakes: SimpleNamespace,
) -> None:
    """Le VOLUME ne depend d'aucun rattachement a la facturation, seul le COUT en depend.

    Un `WHERE cluster_id IS NOT NULL OR warehouse_id IS NOT NULL` dans
    `query_history_filtered` ecarterait pres de la moitie des statements alors qu'ils
    portent bien leur `read_rows`/`read_bytes`. Le seau n'est projete que comme porte
    du prorata de facturation, et le denominateur seul exclut les statements sans seau.
    """
    query = _table_daily_query(fakes, lower_bound=None)
    history_cte = query.split("query_history_filtered AS (")[1].split("cluster_usage AS (")[0]
    assert "WHERE 1 = 1" in history_cte
    assert "cost_bucket_id IS NOT NULL" not in history_cte
    assert "AS cost_bucket_id" in history_cte
    duration_cte = query.split("bucket_daily_duration AS (")[1].split("query_cost AS (")[0]
    assert "WHERE cost_bucket_id IS NOT NULL" in duration_cte


def test_table_daily_incremental_filter_never_leaks_through_an_or(
    fakes: SimpleNamespace,
) -> None:
    """Un `WHERE a OR b` precedant le filtre de fenetre le ferait fuir.

    `A OR B AND date >= ...` se parse `A OR (B AND date >= ...)` : la fenetre ne
    filtre alors qu'une branche du `OR`. Assertion structurelle plutot que
    textuelle -- aucun `OR` ne doit se trouver dans un `WHERE` suivi du filtre.
    """
    query = _table_daily_query(fakes, lower_bound=date(2026, 8, 14))
    date_filter = "AND to_date(start_time) >= DATE '2026-08-14'"
    assert date_filter in query
    for before in query.split(date_filter)[:-1]:
        where_clause = before.rsplit("WHERE ", 1)[1]
        assert " OR " not in where_clause, where_clause


def test_table_daily_query_table_counts_counts_full_table_name(
    fakes: SimpleNamespace,
) -> None:
    """Le denominateur compte le nom qualifie : `COUNT(DISTINCT` a 3 colonnes ecarte
    tout tuple contenant un NULL."""
    query = _table_daily_query(fakes, lower_bound=None)
    assert "COUNT(DISTINCT source_table_full_name) AS n_tables" in query


def test_table_daily_query_lineage_joins_include_workspace_id(
    fakes: SimpleNamespace,
) -> None:
    """`workspace_id` fait partie de la cle de jointure : il est present des deux
    cotes, et l'omettre croiserait les statements de workspaces differents."""
    query = _table_daily_query(fakes, lower_bound=None)
    assert "qc.workspace_id = ql.workspace_id" in query
    assert "qtc.workspace_id = ql.workspace_id" in query


def test_table_daily_query_lineage_uses_dedicated_statement_id_column(
    fakes: SimpleNamespace,
) -> None:
    """`entity_id` (UUID v4) n'est pas `query_history.statement_id` (ULID) : les deux
    espaces d'identifiants sont disjoints, donc la jointure doit passer par la
    colonne dediee `statement_id` du lineage."""
    query = _table_daily_query(fakes, lower_bound=None)
    assert "entity_id AS statement_id" not in query
    # Assertion portee sur l'usage de la colonne comme cle de jointure, pas sur un
    # ordre de projection : figer la liste de colonnes de `query_lineage` ferait
    # echouer ce test a chaque evolution de la CTE, defaut absent ou non.
    assert "qc.statement_id = ql.statement_id" in query
    assert "qtc.statement_id = ql.statement_id" in query


def test_table_daily_price_join_deduplicates_via_qualify(fakes: SimpleNamespace) -> None:
    """Des intervalles de prix chevauchants multiplieraient le cout sans dedup."""
    query = _table_daily_query(fakes, lower_bound=None)
    assert "QUALIFY ROW_NUMBER() OVER (" in query
    assert "u.usage_quantity * lp.effective_price AS line_cost_usd" in query


def test_table_daily_cost_path_has_no_masking_coalesce_zero(
    fakes: SimpleNamespace,
) -> None:
    """Aucun `COALESCE(..., 0)` sur le chemin du cout : il transformerait une
    jointure cassee en un faux zero indistinguable d'un cout nul mesure."""
    query = _table_daily_query(fakes, lower_bound=None)
    assert "COALESCE(lp.effective_price, 0)" not in query
    assert "COALESCE(cdc.cost_usd, 0)" not in query


def test_table_daily_unknown_identity_never_defaults_to_service_principal(
    fakes: SimpleNamespace,
) -> None:
    """Une identite absente ressort `UNKNOWN`, jamais `SERVICE_PRINCIPAL`.

    L'identite d'une lecture de requete est composee : `executed_by` de
    `query.history`, avec repli sur `created_by` du lineage. Deux absences sont donc
    a couvrir -- le SQL NULL, et le litteral `'System-User'` de `created_by`, qui
    faute de `@` serait etiquete `SERVICE_PRINCIPAL`.
    """
    query = _table_daily_query(fakes, lower_bound=None)
    identity = "COALESCE(qc.executed_by, ql.lineage_created_by)"
    assert f"WHEN {identity} IS NULL THEN 'UNKNOWN'" in query
    assert f"WHEN {identity} IN ('unknown', 'System-User') THEN 'UNKNOWN'" in query
    assert "COALESCE(entity_type, 'UNKNOWN') AS consumer_type" in query


def test_table_daily_audit_reads_unknown_identity_never_defaults_to_service_principal(
    fakes: SimpleNamespace,
) -> None:
    """Meme regle dans `audit_reads`, qui a sa propre expression d'identite.

    `access.audit` encode l'absence d'identite par la chaine litterale `'unknown'`
    autant que par un SQL NULL : les deux doivent mener a `UNKNOWN`, sinon une
    identite absente ressort `SERVICE_PRINCIPAL`."""
    query = _table_daily_query(fakes, lower_bound=None)
    assert "NULLIF(user_identity.email, 'unknown')" in query
    assert "WHEN user_identity.email IS NULL OR user_identity.email = 'unknown'" in query


def test_table_daily_last_used_at_populated_by_all_three_branches(
    fakes: SimpleNamespace,
) -> None:
    """Les trois branches de lecture alimentent `last_used_at`, pas seulement l'audit."""
    query = _table_daily_query(fakes, lower_bound=None)
    assert "COALESCE(qc.start_time, ql.lineage_event_time) AS last_used_at_ts" in query
    assert query.count("event_time AS last_used_at_ts") == 2  # non_query + audit
    assert "NULL AS last_used_at_ts" not in query


def test_table_daily_audit_reads_period_start_uses_event_time(
    fakes: SimpleNamespace,
) -> None:
    """`period_start` derive de `to_date(event_time)`, pas de la colonne de
    partitionnement `event_date`, qui datte l'ingestion et non l'acces."""
    query = _table_daily_query(fakes, lower_bound=None)
    assert query.count("to_date(event_time) AS period_start") == 2  # lineage + audit


def test_table_daily_query_lineage_is_aggregated_not_projected(
    fakes: SimpleNamespace,
) -> None:
    """`query_lineage` doit AGREGER au grain (statement, table source).

    La source porte plusieurs lignes par couple (statement, source) : fan-out des
    cibles (target_table_full_name est dans ACCESS_TABLE_LINEAGE_MERGE_KEYS),
    `event_id` repetable, et expansion de vue (`direct_access` false). Une simple
    projection multipliait request_count / rows_read / data_read_bytes /
    duration_seconds / estimated_cost_usd par ce nombre de lignes.
    """
    query = _table_daily_query(fakes, lower_bound=None)
    lineage_cte = query.split("query_lineage AS (")[1].split("query_table_counts AS (")[0]
    assert "GROUP BY" in lineage_cte
    assert "statement_id, source_table_full_name" in lineage_cte
    # `period_start` NE DOIT PAS etre dans le groupe : deux evenements de lineage du
    # meme statement encadrant minuit laisseraient un doublon residuel.
    assert "MIN(period_start) AS lineage_period_start" in lineage_cte
    assert "COALESCE(qc.period_start, ql.lineage_period_start) AS period_start" in query


def test_table_daily_query_reads_degrades_instead_of_dropping_uncosted_reads(
    fakes: SimpleNamespace,
) -> None:
    """Une lecture tracee sans cout joignable doit FIGURER sans cout, pas disparaitre.

    Un `statement_id` present dans le lineage n'a pas toujours sa contrepartie dans
    la fenetre curated de `query_history`, et le cout demande en plus un seau de
    facturation rattachable. En INNER JOIN, ces lectures sortiraient de la table sans
    etre reprises ailleurs -- `non_query_reads` est le complement strict sur
    `statement_id IS NULL`.
    """
    query = _table_daily_query(fakes, lower_bound=None)
    reads_cte = query.split("query_reads AS (")[1].split("non_query_reads AS (")[0]
    assert "LEFT JOIN query_cost qc" in reads_cte
    # LEFT aussi sur le denominateur : `NULL = NULL` etant faux, un INNER y perdrait
    # la meme population que le LEFT ci-dessus preserve.
    assert "LEFT JOIN query_table_counts qtc" in reads_cte
    assert "JOIN query_cost qc" not in reads_cte.replace("LEFT JOIN query_cost qc", "")
    # Repli sur les colonnes du lineage, seule information disponible sans la requete.
    assert "qc.executed_by, ql.lineage_created_by, ql.lineage_entity_id, 'unknown'" in reads_cte
    # Pas de methode d'attribution annoncee sur une ligne sans cout calcule.
    assert "CASE WHEN qc.statement_id IS NULL THEN CAST(NULL AS STRING)" in reads_cte


def test_table_daily_write_volumes_come_from_query_history_target_side(
    fakes: SimpleNamespace,
) -> None:
    """Le volume ecrit vient de `query_history.written_rows`/`written_bytes`.

    Il s'attribue a la table CIBLE, via le cote `target_*` du lineage : le rattacher
    a `source_table_full_name` imputerait le volume ecrit dans `gold` a la table
    `silver` lue."""
    query = _table_daily_query(fakes, lower_bound=None)
    assert "target_table_catalog AS catalog" in query
    assert "target_table_schema AS schema" in query
    assert "target_table_name AS table_name" in query
    assert "qw.written_rows / NULLIF(wtc.n_targets, 0) AS rows_written" in query
    assert "qw.written_bytes / NULLIF(wtc.n_targets, 0) AS data_written_bytes" in query
    assert "SELECT * FROM query_writes" in query


def test_table_daily_write_volume_never_fabricates_zero(fakes: SimpleNamespace) -> None:
    """Une ecriture dont le statement n'est pas joignable est NON MESUREE : `0`
    l'affirmerait a tort comme « aucune ligne ecrite »."""
    query = _table_daily_query(fakes, lower_bound=None)
    assert "0 AS rows_written" not in query
    assert "0 AS data_written_bytes" not in query
    assert query.count("CAST(NULL AS DOUBLE) AS rows_written") == 3  # query/non_query/audit
    assert query.count("CAST(NULL AS DOUBLE) AS data_written_bytes") == 3


def test_table_daily_write_branch_does_not_double_count_the_statement(
    fakes: SimpleNamespace,
) -> None:
    """La branche d'ecriture partage le `statement_id` avec `query_reads` : compter
    a nouveau la requete, sa duree ou son cout casserait `SUM(parts) = cout requete`."""
    query = _table_daily_query(fakes, lower_bound=None)
    writes_cte = query.split("query_writes AS (")[1].split("all_reads AS (")[0]
    assert "0 AS request_count" in writes_cte
    assert "CAST(NULL AS DOUBLE) AS estimated_cost_usd" in writes_cte
    assert "CAST(NULL AS DOUBLE) AS duration_seconds" in writes_cte
    assert "0 AS failed_access_count" in writes_cte


def test_table_daily_write_lineage_deduplicates_target_fan_in(
    fakes: SimpleNamespace,
) -> None:
    """Une requete lisant N tables et ecrivant 1 cible produit N lignes de lineage
    portant la MEME cible : sans agregation, `written_rows` serait compte N fois."""
    query = _table_daily_query(fakes, lower_bound=None)
    writes_cte = query.split("lineage_table_writes AS (")[1].split("query_lineage AS (")[0]
    assert "GROUP BY" in writes_cte
    assert "statement_id IS NOT NULL" in writes_cte
    # `PATH` n'a pas de nom qualifie en trois parties : rien a agreger au grain gold.
    assert "'PATH'" not in writes_cte
    assert "'MATERIALIZED_VIEW'" in writes_cte


def test_table_daily_lineage_grain_reads_native_columns_not_a_parsed_string(
    fakes: SimpleNamespace,
) -> None:
    """Le lineage publie `source_table_catalog`/`_schema`/`_name` en natif.

    Reconstituer le grain par `split(source_table_full_name, '\\\\.')` ajoute une
    facon d'avoir tort -- identifiant quote contenant un `.`, valeur non conforme en
    3 parties -- sans rien apporter. Le cote CIBLE (`lineage_table_writes`) lit les
    memes colonnes natives : les deux cotes d'un meme builder restent symetriques.
    """
    query = strip_sql_comments(_table_daily_query(fakes, lower_bound=None))
    reads_cte = query.split("lineage_table_reads AS (")[1].split("lineage_table_writes AS (")[0]
    assert "split(source_table_full_name" not in reads_cte
    assert "source_table_catalog AS catalog" in reads_cte
    assert "source_table_schema AS schema" in reads_cte
    assert "source_table_name AS table_name" in reads_cte


def test_table_daily_read_lineage_covers_every_named_uc_object(
    fakes: SimpleNamespace,
) -> None:
    """Un `source_type = 'TABLE'` rendrait la table aveugle aux vues.

    Vues, vues materialisees, streaming tables et metric views sont des objets lus,
    et des statements ne lisent QUE de tels objets : les restreindre ne deplacerait
    pas leur cout, il le perdrait. `table_popularity_daily` lisant CETTE table,
    aucune vue n'y apparaitrait non plus, quel que soit son propre filtre.
    """
    query = strip_sql_comments(_table_daily_query(fakes, lower_bound=None))
    reads_cte = query.split("lineage_table_reads AS (")[1].split("lineage_table_writes AS (")[0]
    assert "source_type = 'TABLE'" not in reads_cte
    for object_type in ("'TABLE'", "'VIEW'", "'MATERIALIZED_VIEW'", "'STREAMING_TABLE'"):
        assert object_type in reads_cte
    # `PATH` n'a pas de nom qualifie en trois parties : rien a agreger au grain gold.
    assert "'PATH'" not in reads_cte


def test_table_daily_read_lineage_keeps_indirect_view_expansion_reads(
    fakes: SimpleNamespace,
) -> None:
    """Pas de filtre `direct_access`.

    Une requete sur une vue `v` au-dessus de `t` produit une ligne directe sur `v` et
    une ligne INDIRECTE sur `t`, une part notable des lignes de lineage. Filtrer les
    acces indirects ferait perdre a `t` des lectures qu'elle a bien subies ; le prix
    a payer est le partage du cout entre `v` et `t`, documente dans le contrat de
    `estimated_cost_usd`."""
    query = strip_sql_comments(_table_daily_query(fakes, lower_bound=None))
    assert "direct_access" not in query


def test_table_daily_audit_grain_parses_out_of_bounds_safely(
    fakes: SimpleNamespace,
) -> None:
    """La branche audit, elle, DOIT parser : `request_params` ne porte le nom
    qualifie que concatene, il n'y a pas de colonne native a lire.

    Elle reste donc exposee a une valeur non conforme, et c'est l'indexation qui
    decide du mode d'echec : `arr[i]` leve `INVALID_ARRAY_INDEX` en mode ANSI et fait
    perdre TOUT le run gold, la ou `get(arr, i)` rend NULL sur la seule ligne
    concernee.
    """
    query = _table_daily_query(fakes, lower_bound=None)
    audit_cte = query.split("audit_reads AS (")[1].split("query_write_volumes AS (")[0]
    assert "get(split(COALESCE(request_params['full_name_arg']" in audit_cte
    assert "'\\\\.'), 0) AS catalog" in audit_cte
    assert "'\\\\.'), 2) AS table_name" in audit_cte


def test_table_daily_unmeasurable_reads_are_null_never_zero(
    fakes: SimpleNamespace,
) -> None:
    """Volume et duree non mesurables ressortent NULL, jamais `0`.

    `non_query_reads` (lineage sans `statement_id`) et `audit_reads` (`getTable`, des
    metadonnees UC sans requete) n'ont acces a aucun volume : un `0` y affirmerait
    « a lu zero ligne en zero seconde pour zero dollar » et diluerait toute moyenne
    calculee en aval. Elles ne doivent pas non plus annoncer de methode
    d'attribution, aucun cout n'ayant ete calcule.
    """
    query = _table_daily_query(fakes, lower_bound=None)
    for zero in ("0 AS rows_read", "0 AS data_read_bytes", "0.0 AS duration_seconds"):
        assert zero not in query
    assert "0.0 AS estimated_cost_usd" not in query
    for cte_name, next_cte in (
        ("non_query_reads AS (", "audit_reads AS ("),
        ("audit_reads AS (", "query_write_volumes AS ("),
    ):
        cte = query.split(cte_name)[1].split(next_cte)[0]
        assert "CAST(NULL AS DOUBLE) AS rows_read" in cte
        assert "CAST(NULL AS DOUBLE) AS data_read_bytes" in cte
        assert "CAST(NULL AS DOUBLE) AS duration_seconds" in cte
        assert "CAST(NULL AS DOUBLE) AS estimated_cost_usd" in cte
        assert "CAST(NULL AS STRING) AS cost_attribution_method" in cte
        assert "'equal_parts_fallback'" not in cte


def test_table_daily_publishes_the_denominator_of_its_partial_sums(
    fakes: SimpleNamespace,
) -> None:
    """`SUM()` ignorant les NULL, un total partiel est indistinguable d'un total.

    Un groupe melangeant des acces chiffres et des acces non mesurables (audit
    `getTable`, lineage sans `statement_id`) rend un `estimated_cost_usd` qui ne porte
    que sur une partie de `request_count`. `costed_request_count` publie sur combien
    d'acces le cout a reellement ete calcule -- sans lui, la sous-estimation est
    invisible pour le consommateur de la table.
    """
    query = _table_daily_query(fakes, lower_bound=None)
    assert (
        "SUM(CASE WHEN estimated_cost_usd IS NOT NULL THEN request_count ELSE 0 END)\n"
        "                AS costed_request_count"
    ) in query
    assert "a.costed_request_count" in query


def test_table_daily_consumer_type_uses_priority_ranked_max(
    fakes: SimpleNamespace,
) -> None:
    """`MAX(consumer_type)` brut gagnerait alphabetiquement : l'encodage priorise
    fait primer une identite nominative sur un type d'entite brut."""
    query = _table_daily_query(fakes, lower_bound=None)
    assert "MAX(consumer_type)" not in query
    assert "MAX(CONCAT(CASE consumer_type" in query
    assert "SUBSTRING(a.consumer_type_ranked, 3) AS consumer_type" in query


def test_table_daily_excludes_the_keys_proven_ephemeral(fakes: SimpleNamespace) -> None:
    """Le filtre est POSE ICI, et pas seulement sur le registre.

    L'exclusion en aval lit la PRESENCE d'une ligne `is_deleted` au registre, jamais
    l'absence de ligne : purger le registre sans retirer les lignes de fait rendrait
    l'ephemere visible comme une table VIVANTE. Ce filtre est la moitie « ne pas ecrire »
    du mecanisme -- l'autre moitie retire le stock deja ecrit (`purge_ephemeral_rows`).
    """
    query = _table_daily_query(fakes, lower_bound=None)
    assert f"WITH {EPHEMERAL_KEYS_CTE_NAME}_referentiel AS (" in query
    assert "it.sch.curated_dbx_uc_table_operations" in query
    assert f"AND {not_ephemeral_predicate('a')}" in query


def test_table_daily_filter_reaches_popularity_and_consumer_daily_by_derivation(
    fakes: SimpleNamespace,
) -> None:
    """Le filtre porte sur l'ALIAS de la projection finale, celle que les deux derivees lisent.

    `table_popularity_daily` prend ses cles de cette table (`FROM daily_agg`) et ne fait
    que l'enrichir par LEFT JOIN ; `consumer_daily` l'agrege par consommateur. Filtrer une
    CTE intermediaire suffirait a l'une et pas a l'autre. Pose sur la projection publiee,
    aucune des deux ne peut voir une cle que celle-ci a refusee.
    """
    query = _table_daily_query(fakes, lower_bound=None)
    final_projection = query.rpartition("FROM aggregated a")[2]
    assert final_projection, "la projection finale a change de forme"
    assert not_ephemeral_predicate("a") in final_projection
