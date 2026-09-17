"""Tests de `pipelines.gold_dbx_usage.table_catalog` (regles de derivation).

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`) :
`build_table_catalog` construit un unique `spark.sql(...)`, verifie ici via
le texte SQL genere (`FakeSpark`), meme pattern que `test_table_popularity_daily.py`.
"""

from __future__ import annotations

from types import SimpleNamespace

from pipelines.gold_dbx_usage.sql_helpers import EPHEMERAL_TABLE_MAX_LIFETIME_SECONDS
from pipelines.gold_dbx_usage.table_catalog import build_table_catalog


def _lifecycle_case(query: str) -> str:
    """Corps du `CASE` qui derive `lifecycle_state`, sans son indentation."""
    return query.split("WHEN present_in_referential")[1].split("END AS lifecycle_state")[0]


def _deleted_only_cte(query: str) -> str:
    """Corps de la CTE `deleted_only`, bornee sur la suivante.

    Borne sur `socle AS (` et non sur `),` : le corps porte des parentheses, dans son
    commentaire comme dans son predicat de duree de vie.
    """
    return query.split("deleted_only AS (")[1].split("socle AS (")[0]


def _without_sql_comments(sql: str) -> str:
    """Le SQL seul, lignes de commentaire `--` retirees.

    Les commentaires de ce builder nomment les formes a NE PAS ecrire (`NOT (...)`) :
    une assertion d'ABSENCE portee sur le texte brut tomberait sur la prose au lieu du
    predicat, et passerait ou echouerait pour la mauvaise raison.
    """
    return "\n".join(line.split("--")[0] for line in sql.splitlines())


def _table_catalog_query(fakes: SimpleNamespace) -> str:
    sentinel = fakes.DataFrame("table_catalog_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_table_catalog(
        spark,
        uc_tables_table="it.sch.curated_dbx_uc_tables",
        uc_table_tags_table="it.sch.curated_dbx_uc_table_tags",
        table_operations_table="it.sch.curated_dbx_uc_table_operations",
        lineage_table="it.sch.curated_dbx_access_table_lineage",
        query_history_table="it.sch.curated_dbx_query_history",
        table_daily_table="it.sch.gold_dbx_usage_table_daily",
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    # Annotation et non `return spark.sql_calls[0]` : `fakes` est un `SimpleNamespace`,
    # donc `spark` est `Any` et le type declare de `FakeSpark.sql_calls` est perdu.
    query: str = spark.sql_calls[0]
    return query


def test_table_catalog_last_operation_and_last_write_at_via_max_by(
    fakes: SimpleNamespace,
) -> None:
    query = _table_catalog_query(fakes)
    assert "MAX_BY(action_name, event_time) AS last_operation" in query
    assert "MAX(event_time) AS last_operation_at" in query
    assert "FROM it.sch.curated_dbx_uc_table_operations" in query
    assert (
        "action_name = 'createTable' AND request_params['catalog_name'] IS NOT NULL "
        "AND request_params['schema_name'] IS NOT NULL AND request_params['name'] IS NOT NULL"
        in query
    )
    assert "action_name != 'createTable' AND request_params['full_name_arg'] IS NOT NULL" in query


def test_table_catalog_full_name_extraction_branches_by_action_name(
    fakes: SimpleNamespace,
) -> None:
    query = _table_catalog_query(fakes)
    # createTable : catalog_name/schema_name/name (jamais full_name_arg, confirme sur donnee reelle)
    assert "THEN request_params['catalog_name']" in query
    assert "THEN request_params['schema_name']" in query
    assert "THEN request_params['name']" in query
    # deleteTable/updateTables : full_name_arg, split via get() (ANSI-safe, pas [i]).
    assert "get(split(request_params['full_name_arg'], '\\\\.'), 0)" in query
    assert "get(split(request_params['full_name_arg'], '\\\\.'), 1)" in query
    assert "get(split(request_params['full_name_arg'], '\\\\.'), 2)" in query


def test_table_catalog_last_operation_by_via_max_by_user_identity(
    fakes: SimpleNamespace,
) -> None:
    query = _table_catalog_query(fakes)
    assert (
        "MAX_BY(COALESCE(user_identity.email, user_identity.subject_name), event_time)"
        in query
    )
    assert "AS last_operation_by" in query


def test_table_catalog_freshness_lag_hours_formula_is_null_safe(
    fakes: SimpleNamespace,
) -> None:
    # Test sur le texte SQL genere (pas d'execution reelle) : on verifie que
    # l'expression est presente, pas le comportement runtime sur NULL (une
    # division/soustraction impliquant un NULL SQL propage naturellement le
    # NULL, jamais une valeur inventee).
    query = _table_catalog_query(fakes)
    assert (
        "(unix_timestamp(current_timestamp())\n"
        "            - unix_timestamp(COALESCE(last_write_at, last_altered_at))) / 3600" in query
    )
    assert "AS freshness_lag_hours" in query


def test_table_catalog_audit_dates_the_last_operation_never_a_write(
    fakes: SimpleNamespace,
) -> None:
    """L'audit date une operation, il ne peut pas prouver une ecriture.

    `system.access.audit` journalise des appels d'API Unity Catalog : ses 3 actions ne
    portent aucun compteur de lignes, et `updateTables` couvre autant un changement de
    metadonnee seule qu'un commit de donnees. Le derive dont il est la source est donc
    `last_operation_at`, sur les 3 actions et sans restriction, jamais `last_write_at`.
    """
    query = _table_catalog_query(fakes)
    # Borne la CTE sur la suivante : son corps contient des parentheses,
    # qu'un split sur ")," couperait au milieu d'un commentaire.
    operations_cte = query.split("last_operation AS (")[1].split("lineage_writes AS (")[0]
    assert "MAX(event_time) AS last_operation_at" in operations_cte
    # Le MAX porte les 3 actions : aucun predicat d'audit ne selectionne d'ecriture,
    # ici comme dans la CTE qui l'alimente.
    assert "action_name = 'updateTables'" not in query
    assert "internal_update_mask" not in query
    # Aucune date d'ecriture ne sort de cette CTE : `last_write_at` vient du lineage.
    assert "audit_write_at" not in query
    assert "lo.last_operation_at" in query


def test_table_catalog_last_write_at_is_the_proven_lineage_write(
    fakes: SimpleNamespace,
) -> None:
    """Une seule preuve d'ecriture, publiee telle quelle.

    Aucun arbitrage avec un second signal : melanger a une ecriture mesuree une date
    dont rien n'atteste qu'une ligne a ete ecrite rendrait la colonne inverifiable, et
    `freshness_basis` mensonger sur les lignes ou l'autre signal l'emporterait.
    """
    query = _table_catalog_query(fakes)
    assert "lw.lineage_write_at AS last_write_at" in query
    assert "GREATEST(" not in query
    assert "COALESCE(lw.lineage_write_at" not in query
    # Cote lineage : la table ECRITE, donc le cote cible, et aucun filtre de fenetre
    # (snapshot recalcule en entier).
    # Borne la CTE sur la suivante : son corps contient des parentheses,
    # qu'un split sur ")," couperait au milieu d'un commentaire.
    lineage_cte = query.split("lineage_writes AS (")[1].split("last_read AS (")[0]
    assert "MAX(l.event_time) AS lineage_write_at" in lineage_cte
    assert "l.target_table_name AS table_name" in lineage_cte
    assert "FROM it.sch.curated_dbx_access_table_lineage l" in lineage_cte
    assert "source_table" not in lineage_cte


def test_table_catalog_lineage_write_requires_rows_written_or_no_query_history(
    fakes: SimpleNamespace,
) -> None:
    """Une cible de lineage n'est pas une ecriture.

    Le cote cible designe le noeud AVAL d'une arete : lire une table a travers une vue
    produit « table source -> vue », dont la cible est la vue. La qualifier demande
    `written_rows > 0` cote query history, et d'exclure les `target_type` sans contenu
    propre. L'absence de query history reste acceptee, sinon les ecritures de PIPELINE
    (jamais journalisees la) et de JOB disparaitraient.
    """
    query = _table_catalog_query(fakes)
    # Borne la CTE sur la suivante : son corps contient des parentheses,
    # qu'un split sur ")," couperait au milieu d'un commentaire.
    lineage_cte = query.split("lineage_writes AS (")[1].split("last_read AS (")[0]
    assert (
        "LEFT JOIN it.sch.curated_dbx_query_history q\n"
        "          ON q.cloud_provider = l.cloud_provider "
        "AND q.statement_id = l.statement_id" in lineage_cte
    )
    assert "(q.written_rows > 0 OR q.statement_id IS NULL)" in lineage_cte
    # Objets porteurs de donnees seulement : une VIEW n'a pas de contenu propre.
    assert "l.target_type IN ('TABLE', 'MATERIALIZED_VIEW', 'STREAMING_TABLE')" in lineage_cte
    assert "'VIEW'" not in lineage_cte
    assert "'METRIC_VIEW'" not in lineage_cte


def test_table_catalog_freshness_basis_follows_the_value_actually_retained(
    fakes: SimpleNamespace,
) -> None:
    """La base annoncee doit designer le signal dont la valeur a ete prise.

    Le `CASE` suit terme par terme le `COALESCE` qui calcule l'anciennete :
    desynchroniser les deux nommerait une base autre que celle qui l'a produite, un
    mensonge invisible puisque les deux colonnes resteraient plausibles.
    """
    query = _table_catalog_query(fakes)
    case_body = query.split("CASE\n            WHEN last_write_at")[1].split(
        "END AS freshness_basis"
    )[0]
    assert "IS NOT NULL THEN 'lineage_write'" in case_body
    # Le repli n'est annonce que s'il a une valeur a offrir : sinon la base reste NULL
    # plutot que d'affirmer un signal absent.
    assert "WHEN last_altered_at IS NOT NULL THEN 'table_altered'" in case_body
    assert "'audit_write'" not in query


def test_table_catalog_is_data_product_via_tag_name_exact_match(fakes: SimpleNamespace) -> None:
    query = _table_catalog_query(fakes)
    assert (
        "MAX(CASE WHEN tag_name = 'data_product' THEN 1 ELSE 0 END) = 1"
        "\n                AS is_data_product" in query
    )
    assert "COALESCE(is_data_product, false) AS is_data_product" in query


def test_table_catalog_pivots_owner_domain_cost_center_classification_tags(
    fakes: SimpleNamespace,
) -> None:
    query = _table_catalog_query(fakes)
    assert "MAX(CASE WHEN tag_name = 'owner' THEN tag_value END) AS owner" in query
    assert "MAX(CASE WHEN tag_name = 'domain' THEN tag_value END) AS domain" in query
    assert "MAX(CASE WHEN tag_name = 'cost_center' THEN tag_value END) AS cost_center" in query
    assert (
        "MAX(CASE WHEN tag_name = 'classification' THEN tag_value END) AS classification"
        in query
    )


def test_table_catalog_table_full_name_via_concat_ws(fakes: SimpleNamespace) -> None:
    query = _table_catalog_query(fakes)
    assert "concat_ws('.', catalog, schema, table_name) AS table_full_name" in query


def test_table_catalog_has_no_source_lz_id_or_subscription_account_id(
    fakes: SimpleNamespace,
) -> None:
    query = _table_catalog_query(fakes)
    assert "source_lz_id" not in query
    assert "subscription_or_account_id" not in query


def test_table_catalog_last_read_at_from_table_daily_via_max_last_used_at(
    fakes: SimpleNamespace,
) -> None:
    query = _table_catalog_query(fakes)
    assert "FROM it.sch.gold_dbx_usage_table_daily" in query
    assert "MAX(last_used_at) AS last_read_at" in query


def test_table_catalog_lifecycle_is_active_when_present_in_the_referential(
    fakes: SimpleNamespace,
) -> None:
    """La presence au referentiel decide seule, et en PREMIER.

    `curated_dbx_uc_tables` est un full load purge : une cle qui y figure existe au
    catalogue au moment du run, quel que soit l'historique d'audit.
    """
    query = _table_catalog_query(fakes)
    assert _lifecycle_case(query).startswith(" THEN 'ACTIVE'")


def test_table_catalog_lifecycle_is_deleted_only_when_corroborated_by_an_audit_event(
    fakes: SimpleNamespace,
) -> None:
    """L'absence du referentiel ne suffit pas : il faut un `deleteTable`.

    Sans cette corroboration, tout defaut de GRANT sur le principal d'ingestion
    marquerait supprimee une table vivante (SC-002).
    """
    query = _table_catalog_query(fakes)
    assert "WHEN last_operation = 'deleteTable' THEN 'DELETED'" in _lifecycle_case(query)
    # `is_deleted` se lit exactement comme « l'etat vaut DELETED » : jamais NULL,
    # donc jamais de `NOT is_deleted` qui filtre silencieusement en aval.
    assert "lifecycle_state = 'DELETED' AS is_deleted" in query
    assert "CASE WHEN lifecycle_state = 'DELETED' THEN last_operation_at END" in query
    assert "AS deleted_at" in query


def test_table_catalog_lifecycle_is_unknown_when_absent_without_proof(
    fakes: SimpleNamespace,
) -> None:
    """Absente du referentiel sans `deleteTable` : etat explicite, pas un booleen.

    Le repli est `UNKNOWN`, donc `is_deleted = false` : une visibilite manquante ne
    doit jamais se lire comme une suppression.
    """
    query = _table_catalog_query(fakes)
    assert "ELSE 'UNKNOWN'" in _lifecycle_case(query)


def test_table_catalog_a_recreated_table_goes_back_to_active(
    fakes: SimpleNamespace,
) -> None:
    """Reversibilite (FR-016) sans code dedie.

    La branche `present_in_referential` precede celle du `deleteTable` dans le meme
    `CASE` : une table recreee sort donc `ACTIVE` meme si son evenement de suppression
    est toujours dans la fenetre d'audit.
    """
    lifecycle_case = _lifecycle_case(_table_catalog_query(fakes))
    assert lifecycle_case.index("'ACTIVE'") < lifecycle_case.index("'DELETED'")


def test_table_catalog_deleted_tables_get_a_row_with_null_registry_columns(
    fakes: SimpleNamespace,
) -> None:
    """Une table supprimee n'a AUCUNE ligne source : il faut la fabriquer.

    Elle a disparu de `curated_dbx_uc_tables` (full load purge) et
    `merge_into_table` ne supprime jamais de ligne cible -- sans ce squelette, une
    table deja connue garderait `is_deleted = false` pour toujours. Ses colonnes de
    registre sont NULL : l'objet n'existe plus au catalogue, les inventer serait pire
    que de les taire.
    """
    query = _table_catalog_query(fakes)
    deleted_cte = _deleted_only_cte(query)
    assert "LEFT ANTI JOIN base b" in deleted_cte
    assert "WHERE lo.last_operation = 'deleteTable'" in deleted_cte
    socle_cte = query.split("socle AS (")[1].split("lineage_writes AS (")[0]
    assert "true AS present_in_referential" in socle_cte
    assert "false AS present_in_referential" in socle_cte
    for column, sql_type in (
        ("table_type", "STRING"),
        ("created_at", "TIMESTAMP"),
        ("created_by", "STRING"),
        ("last_altered_at", "TIMESTAMP"),
    ):
        assert f"CAST(NULL AS {sql_type}) AS {column}" in socle_cte
    # Les tags ne sont pas joints a une cle absente du registre : `is_data_product`
    # doit donc rester le booleen non-NULL du contrat, pas un NULL.
    assert "COALESCE(is_data_product, false) AS is_data_product" in query


def test_table_catalog_an_ephemeral_table_is_not_a_deleted_table(
    fakes: SimpleNamespace,
) -> None:
    """Vivre moins que le seuil n'est pas mourir : c'est n'avoir jamais existe.

    Une table de staging creee, lue et droppee par le meme run de job porte un
    `createTable` et un `deleteTable` : sans ce filtre, le squelette `deleted_only` lui
    fabrique une ligne de registre declaree supprimee pour toujours, le MERGE ne retirant
    jamais de ligne cible. Le registre accumule alors des objets que personne n'a jamais
    gouvernes.
    """
    query = _table_catalog_query(fakes)
    # La naissance vient de l'audit : une table supprimee n'a plus de `created` au
    # referentiel, il n'y a donc rien d'autre a comparer.
    assert (
        "MIN(CASE WHEN action_name = 'createTable' THEN event_time END) AS created_event_at"
        in query
    )
    deleted_cte = _deleted_only_cte(query)
    assert (
        "unix_timestamp(lo.last_operation_at) - unix_timestamp(lo.created_event_at)" in deleted_cte
    )
    # Le seuil du SQL suit la constante : ce test epingle la VALEUR, pas sa provenance
    # -- un litteral recopie passerait tant qu'il vaut la meme chose, et divergerait le
    # jour ou la constante bouge. C'est justement ce jour-la que l'assertion parle.
    assert f">= {EPHEMERAL_TABLE_MAX_LIFETIME_SECONDS}" in deleted_cte


def test_table_catalog_a_deleted_table_of_unknown_age_is_kept(
    fakes: SimpleNamespace,
) -> None:
    """Age inconnu, table gardee : jamais d'exclusion sur un doute.

    Un `createTable` sorti de la fenetre de retention d'audit rend `created_event_at`
    NULL. Ecrit en negatif (`NOT (age < seuil)`), le predicat rendrait NULL sur ces
    lignes et les jetterait en silence -- exactement la vraie suppression, ancienne et
    donc interessante, qu'on voulait garder.
    """
    deleted_sql = _without_sql_comments(_deleted_only_cte(_table_catalog_query(fakes)))
    assert "lo.created_event_at IS NULL" in deleted_sql
    # Forme positive : « garder si la vie a dure ». Un `NOT (...)` ou un `<` inverserait
    # le sort des lignes d'age inconnu sans que le reste du predicat change.
    assert "NOT (" not in deleted_sql
    assert "IS NOT NULL" not in deleted_sql
    assert deleted_sql.index("lo.created_event_at IS NULL") < deleted_sql.index("unix_timestamp")


def test_table_catalog_the_audit_birth_never_reaches_the_published_columns(
    fakes: SimpleNamespace,
) -> None:
    """`created_event_at` est un intermediaire de mesure, pas une colonne du contrat.

    `created_at` reste celui du referentiel. Publier la date de l'audit a sa place
    ferait apparaitre une creation sur des lignes dont toutes les autres colonnes de
    registre sont NULL, et changerait le sens d'une colonne du contrat sans le dire.
    """
    query = _table_catalog_query(fakes)
    projection = query.split("with_lifecycle AS (")[1]
    assert "created_event_at" not in projection
    assert "created_event_at AS created_at" not in query
