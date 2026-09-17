"""Tests de `pipelines.gold_dbx_compute.recommendations` (rule engine, clusters + warehouses).

Meme convention que les autres tests `gold_dbx_compute` (cf.
`test_cluster_governance.py`) : pas de vraie `SparkSession`, `FakeSpark`
capture le texte SQL genere par l'unique `spark.sql(...)` et les assertions
portent sur ce texte (formule du hash, preservation de `first_seen_date`,
transition de statut, priorite des regles).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from pipelines.gold_dbx_compute.recommendations import build_compute_recommendations

_TARGET_TABLE = "it.sch.gold_dbx_compute_recommendations"


def _recommendations_query(
    fakes: SimpleNamespace,
    *,
    existing_tables: set[str] | None = None,
    generated_date: date = date(2026, 8, 25),
) -> str:
    sentinel = fakes.DataFrame("recommendations_result")
    spark = fakes.Spark(existing_tables=existing_tables, sql_result=sentinel)
    result = build_compute_recommendations(
        spark,
        cluster_efficiency_rolling_table="it.sch.gold_dbx_compute_cluster_efficiency_rolling",
        cluster_reliability_rolling_table="it.sch.gold_dbx_compute_cluster_reliability_rolling",
        governance_table="it.sch.gold_dbx_compute_cluster_governance",
        cluster_cost_rolling_table="it.sch.gold_dbx_compute_cluster_cost_rolling",
        warehouse_utilization_rolling_table=(
            "it.sch.gold_dbx_compute_warehouse_utilization_rolling"
        ),
        warehouse_query_performance_rolling_table=(
            "it.sch.gold_dbx_compute_warehouse_query_performance_rolling"
        ),
        warehouse_cost_rolling_table="it.sch.gold_dbx_compute_warehouse_cost_rolling",
        recommendations_table=_TARGET_TABLE,
        generated_date=generated_date,
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0]


def test_recommendation_id_hash_uses_first_seen_date_not_run_date(fakes: SimpleNamespace) -> None:
    # Stabilite du hash sur tout le cycle de vie de l'anomalie : `first_seen_date`
    # (pas la date du run) dans la formule, sinon un nouvel id serait genere a
    # chaque run et le MERGE ne matcherait jamais l'existant (cf. docstring module).
    query = _recommendations_query(fakes)
    assert (
        "concat_ws(\n                '||', workspace_id, object_type, object_id, category,\n"
        "                CAST(first_seen_date AS STRING)"
        in query
    )
    assert "sha2(\n            concat_ws(" in query


def test_recommendation_id_hash_includes_workspace_id(fakes: SimpleNamespace) -> None:
    # `object_id` (cluster_id/warehouse_id) n'est pas garanti unique
    # cross-workspace, a la difference de CLUSTER_DAILY_MERGE_KEYS/
    # WAREHOUSE_DAILY_MERGE_KEYS (T002/T003) qui incluent `workspace_id`.
    # `recommendation_id` doit faire de meme pour eviter qu'un `dropDuplicates`
    # au MERGE collapse silencieusement deux objets de workspaces differents.
    query = _recommendations_query(fakes)
    assert "'||', workspace_id, object_type, object_id, category," in query


def test_recommendation_id_stable_across_two_runs_same_day(fakes: SimpleNamespace) -> None:
    # 2 executions du meme jour (ex. retry manuel) generent EXACTEMENT la meme
    # requete (meme formule de hash, memes CTE) : idempotent par construction (P6).
    first_run_query = _recommendations_query(fakes, existing_tables={_TARGET_TABLE})
    second_run_query = _recommendations_query(fakes, existing_tables={_TARGET_TABLE})
    assert first_run_query == second_run_query


def test_first_run_uses_empty_typed_existing_stub_when_target_table_absent(
    fakes: SimpleNamespace,
) -> None:
    # 1er run (table cible pas encore creee) : `existing` ne doit JAMAIS referencer
    # la table cible reelle (elle n'existe pas), sinon `TABLE_OR_VIEW_NOT_FOUND`.
    query = _recommendations_query(fakes, existing_tables=set())
    assert _TARGET_TABLE not in query
    assert "WHERE 1 = 0" in query
    assert "CAST(NULL AS DATE) AS first_seen_date" in query


def test_reads_rolling_tables_filtered_on_window(fakes: SimpleNamespace) -> None:
    # Le rule engine lit les tables `*_rolling` (fenetre 30 j) et non plus le
    # dernier jour des `*_daily` : filtre `WHERE window_days = 30` par source
    # metrique, plus aucun `QUALIFY ... ORDER BY period_start DESC`.
    query = _recommendations_query(fakes)
    assert "FROM it.sch.gold_dbx_compute_cluster_efficiency_rolling" in query
    assert "FROM it.sch.gold_dbx_compute_warehouse_cost_rolling" in query
    assert "WHERE window_days = 30" in query
    assert "ORDER BY period_start DESC" not in query
    # La GOVERNANCE reste sur le snapshot (aucune variante rolling).
    assert "FROM it.sch.gold_dbx_compute_cluster_governance" in query


def test_rolling_ctes_read_only_the_latest_snapshot_not_every_as_of_date(
    fakes: SimpleNamespace,
) -> None:
    """Les 6 CTE `latest_*` ne lisent que le dernier `as_of_date` de la fenetre.

    `WHERE window_days = 30` ne designe pas « le dernier snapshot » :
    `as_of_date` n'est dans aucune cle de merge `*_ROLLING_MERGE_KEYS`, donc une
    ligne dont le run du jour ne produit plus la cle survit avec son ancien
    `as_of_date`. Sans ce filtre, le rule engine notait des objets disparus
    (recos `OPEN` au lieu de `RESOLVED`) et lisait des lignes anterieures a
    `is_serverless` (NULL = lu comme classique, donc gardes serverless
    inoperants). Mesure au moment du correctif sur le workspace dev : 4 recos
    « auto-stop manquant » et 6 recos rightsizing portees par des snapshots
    perimes de 3 a 5 jours (13 459 recos `OPEN` au total, cf. `_latest_rolling_cte`).

    Le `MAX(as_of_date)` doit porter sur TOUTE la table et non sur la fenetre
    lue : meme forme que la garde de la couche API
    (`compute_metrics_common._window_where`), sinon une fenetre a population
    courante vide ressuscite ses lignes perimees et le rule engine juge
    « courant » un autre snapshot que celui affiche a l'utilisateur.
    """
    query = _recommendations_query(fakes)
    assert query.count("AND as_of_date = (SELECT MAX(as_of_date) FROM ") == 6
    for rolling_table in (
        "it.sch.gold_dbx_compute_cluster_efficiency_rolling",
        "it.sch.gold_dbx_compute_cluster_reliability_rolling",
        "it.sch.gold_dbx_compute_cluster_cost_rolling",
        "it.sch.gold_dbx_compute_warehouse_utilization_rolling",
        "it.sch.gold_dbx_compute_warehouse_query_performance_rolling",
        "it.sch.gold_dbx_compute_warehouse_cost_rolling",
    ):
        assert (
            f"SELECT * FROM {rolling_table}\n"
            "        WHERE window_days = 30\n"
            f"          AND as_of_date = (SELECT MAX(as_of_date) FROM {rolling_table})"
        ) in query, rolling_table
    # Sous-requete non filtree sur window_days (un `MAX` par fenetre serait un bug).
    assert "MAX(as_of_date) FROM it.sch.gold_dbx_compute_cluster_cost_rolling)" in query
    assert "MAX(as_of_date) FROM it.sch.gold_dbx_compute_cluster_cost_rolling WHERE" not in query


def test_governance_snapshot_is_read_without_recency_filter(fakes: SimpleNamespace) -> None:
    """`governance` reste lu sans filtre de recence, a la difference des `*_rolling`.

    C'est un snapshot d'etat courant sans fenetre ni `as_of_date` (rien a
    filtrer), et il se purge lui-meme a l'ecriture via
    `CLUSTER_GOVERNANCE_SPEC.absent_row_delete_guard` : lui ajouter un
    filtre de recence n'aurait aucune colonne sur laquelle porter.
    """
    query = _recommendations_query(fakes)
    assert (
        "governance AS (\n        SELECT * FROM it.sch.gold_dbx_compute_cluster_governance\n    )"
    ) in query


def test_existing_run_reads_the_full_target_table_both_object_types(
    fakes: SimpleNamespace,
) -> None:
    # Ce builder gere/ecrit les DEUX types d'objet (CLUSTER et WAREHOUSE) :
    # `existing` ne doit donc PAS filtrer par object_type (contrairement au
    # perimetre cluster-only d'une iteration precedente).
    query = _recommendations_query(fakes, existing_tables={_TARGET_TABLE})
    assert f"SELECT * FROM {_TARGET_TABLE} WHERE status IN ('OPEN', 'ACK')" in query
    assert f"SELECT * FROM {_TARGET_TABLE} WHERE object_type" not in query


def test_existing_run_excludes_resolved_rows_so_reopening_is_a_new_detection(
    fakes: SimpleNamespace,
) -> None:
    # Une ligne RESOLVED ne doit plus etre retrouvee par la jointure
    # sur cle metier de `merged`, sinon sa `first_seen_date` d'origine serait
    # reprise si l'anomalie se redeclenche des mois/annees plus tard - ce qui
    # contredirait le docstring module ("nouvelle detection apres resolution").
    query = _recommendations_query(fakes, existing_tables={_TARGET_TABLE})
    assert "WHERE status IN ('OPEN', 'ACK')" in query


def test_first_seen_date_preserved_from_existing_state(fakes: SimpleNamespace) -> None:
    query = _recommendations_query(fakes, existing_tables={_TARGET_TABLE})
    assert "COALESCE(ex.first_seen_date, DATE '2026-08-25') AS first_seen_date" in query


def test_status_transitions_to_resolved_when_no_longer_a_candidate(fakes: SimpleNamespace) -> None:
    # Une anomalie presente dans `existing` mais absente de `candidates` (plus
    # aucune regle ne se declenche) -> `status = 'RESOLVED'`, `last_seen_date`
    # inchangee (dernier jour ou la condition etait vraie, pas aujourd'hui).
    query = _recommendations_query(fakes, existing_tables={_TARGET_TABLE})
    assert "CASE WHEN c.object_id IS NOT NULL THEN 'OPEN' ELSE 'RESOLVED' END AS status" in query
    assert (
        "CASE\n                WHEN c.object_id IS NOT NULL THEN DATE '2026-08-25'\n"
        "                ELSE ex.last_seen_date\n            END AS last_seen_date" in query
    )
    assert "FULL OUTER JOIN existing ex" in query


def test_rule_payload_follows_the_active_rule_not_the_existing_identity(
    fakes: SimpleNamespace,
) -> None:
    """Non-regression : aucun champ de la regle ne peut etre herite de la veille.

    `merged` joint sur `(cloud_provider, workspace_id, object_type, object_id,
    category)` : la CATEGORIE, pas la regle. Plusieurs regles partagent une
    categorie et le `QUALIFY ... ORDER BY rule_priority` n'en garde qu'une, donc
    la regle active d'une identite change d'un run a l'autre des que la plus
    prioritaire cesse de se declencher. Avec un `COALESCE(c.x, ex.x)`, un champ
    NULL cote candidat retombait sur la valeur de la regle de la VEILLE :
    `title`/`detail`/`recommended_action` du jour et chiffre d'hier sur la meme
    ligne. Mesure en dev au moment du correctif : la mise a NULL de
    `utilization_status` en serverless a desactive la regle RIGHTSIZING de
    priorite 2 au profit des regles queue-time/spill (priorites 3 et 4, qui
    declarent toutes deux `CAST(NULL AS DOUBLE)`), et 64 lignes ont continue
    d'afficher 27 104,74 $ herites de la priorite 2. Le meme mecanisme jouait
    en FINOPS sur 8 lignes / 11,66 $ (`Cluster zombie` relaye par
    `Auto-terminaison manquante`) : 72 lignes / 27 116,40 $ au total, et c'est
    cette seconde categorie qui montre que le defaut est dans `merged` et non
    dans une regle particuliere.

    D'ou le `CASE WHEN c.object_id IS NOT NULL` (meme forme que `status` et
    `last_seen_date`) sur les SIX champs de charge utile : deux pouvaient
    reellement traverser (`estimated_savings_usd`, et `detail` dont le `concat`
    rend NULL des qu'un argument est NULL), les quatre autres sont des litteraux
    non nuls cote candidat et le `CASE` y verrouille l'invariant pour les regles
    futures.
    """
    query = _recommendations_query(fakes, existing_tables={_TARGET_TABLE})
    for column in (
        "title",
        "detail",
        "recommended_action",
        "estimated_savings_usd",
        "severity",
        "personas",
    ):
        assert f"COALESCE(c.{column}, ex.{column})" not in query, column
        assert f"WHEN c.object_id IS NOT NULL THEN c.{column}" in query, column
        assert f"ELSE ex.{column}" in query, column


def test_estimated_savings_never_inherited_when_a_candidate_exists_today(
    fakes: SimpleNamespace,
) -> None:
    """Le `CASE` est bien branche sur la colonne de sortie, et pas ailleurs.

    Ce que le test precedent ne peut pas dire : il cherche les fragments
    `WHEN c.x IS NOT NULL THEN c.x` et `ELSE ex.x` n'importe ou dans la requete,
    donc il resterait vert si l'expression corrigee etait aliasee sur une autre
    colonne. Ici la chaine `END AS estimated_savings_usd` ferme le circuit sur
    la seule colonne dont le defaut a ete MESURE en base (72 lignes,
    27 116,40 $ toutes categories).

    Assertion sur les espaces **normalises** et non sur l'indentation rendue :
    le fichier pipeline est deja rouge a `ruff format --check`, donc un
    reformatage un jour reflowera ce `CASE` sans rien changer a son sens - un
    test qui tomberait la-dessus ne signalerait pas un defaut.
    """
    query = " ".join(_recommendations_query(fakes, existing_tables={_TARGET_TABLE}).split())
    assert (
        "CASE WHEN c.object_id IS NOT NULL THEN c.estimated_savings_usd "
        "ELSE ex.estimated_savings_usd END AS estimated_savings_usd," in query
    )


def test_resolved_rows_retain_their_last_known_savings(fakes: SimpleNamespace) -> None:
    # Symetrique du test precedent : plus aucun candidat aujourd'hui -> la ligne
    # passe `RESOLVED` et GARDE son dernier chiffre connu (c'est la raison d'etre
    # de `ex`), avec `last_seen_date` figee au dernier jour observe. Corriger la
    # fuite ne doit pas vider les lignes resolues.
    query = _recommendations_query(fakes, existing_tables={_TARGET_TABLE})
    assert "ELSE ex.estimated_savings_usd" in query
    assert "CASE WHEN c.object_id IS NOT NULL THEN 'OPEN' ELSE 'RESOLVED' END AS status" in query
    assert "ELSE ex.last_seen_date" in query


def test_join_keys_and_object_name_still_inherit_from_the_existing_state(
    fakes: SimpleNamespace,
) -> None:
    """Le `COALESCE` reste la ou il est correct : cles de jointure et `object_name`.

    Cles de jointure : cote apparie la jointure impose deja `c.x = ex.x`, le
    `COALESCE` ne sert que le cote RESOLVED. `object_name` : propriete de
    l'OBJET (fixe par ces memes cles), pas de la regle - son heritage rattrape
    volontairement un nom que la source du jour n'a pas resolu (cf. la saga
    `object_name` / perimetre `governance` dans la docstring du module) sans
    jamais melanger deux regles. Une « uniformisation » de ces six lignes vers
    le `CASE` de la charge utile ferait donc regresser ce rattrapage.
    """
    query = _recommendations_query(fakes, existing_tables={_TARGET_TABLE})
    for column in ("cloud_provider", "workspace_id", "object_type", "object_id", "category"):
        assert f"COALESCE(c.{column}, ex.{column}) AS {column}" in query, column
    assert "COALESCE(c.object_name, ex.object_name) AS object_name" in query


def test_zombie_cluster_yields_finops_high_severity_rule(fakes: SimpleNamespace) -> None:
    query = _recommendations_query(fakes)
    assert "WHERE e.is_zombie = true" in query
    assert "'FINOPS' AS category, 'HIGH' AS severity" in query
    assert "Cluster zombie" in query


def test_oversized_cluster_yields_rightsizing_medium_severity_rule(
    fakes: SimpleNamespace,
) -> None:
    query = _recommendations_query(fakes)
    assert "WHERE e.utilization_status = 'OVER'" in query
    assert "'RIGHTSIZING' AS category, 'MEDIUM' AS severity" in query


def test_finops_rules_deduplicated_with_zombie_priority_over_missing_auto_termination(
    fakes: SimpleNamespace,
) -> None:
    # Un cluster zombie ET sans auto-terminaison ne doit produire qu'UNE seule
    # ligne FINOPS (meme cle/categorie) : priorite zombie (rule_priority=1)
    # avant auto-terminaison manquante (rule_priority=2), meme convention que
    # `cluster_governance.py` (une action par categorie).
    query = _recommendations_query(fakes)
    zombie_priority_pos = query.index("1 AS rule_priority")
    auto_term_priority_pos = query.index("2 AS rule_priority")
    warehouse_autostop_priority_pos = query.index("3 AS rule_priority")
    assert zombie_priority_pos < auto_term_priority_pos < warehouse_autostop_priority_pos


def test_governance_rules_prioritize_missing_tags_over_dbr_obsolete(
    fakes: SimpleNamespace,
) -> None:
    # Meme ordre de priorite que `cluster_governance.recommended_action` (tag
    # manquant avant DBR obsolete).
    query = _recommendations_query(fakes)
    tag_pos = query.index("AND NOT (has_owner_tag AND has_cost_center_tag)")
    dbr_pos = query.index("AND NOT COALESCE(dbr_is_lts_current, false)")
    assert tag_pos < dbr_pos


def test_dbr_lts_rule_treats_null_as_non_conformant(fakes: SimpleNamespace) -> None:
    # `dbr_is_lts_current` est NULL quand `dbr_version` est NULL
    # (aucune mesure possible). Principe de prudence gouvernance : NULL est
    # traite comme un manquement (`NOT COALESCE(x, false)`), pas exclu
    # silencieusement (`NOT NULL` vaudrait NULL et la ligne serait perdue).
    query = _recommendations_query(fakes)
    assert "AND NOT COALESCE(dbr_is_lts_current, false)" in query


def test_governance_rules_only_target_clusters_where_governance_applies(
    fakes: SimpleNamespace,
) -> None:
    # Les tags et le runtime d'un cluster JOB/PIPELINE sont imposes par la
    # definition du job/pipeline : une reco par execution ephemere n'aurait aucun
    # destinataire (et representait l'essentiel du volume de la table).
    # `COALESCE(..., false)` : la colonne est NULL sur les lignes de governance
    # ecrites avant son introduction.
    query = _recommendations_query(fakes)
    assert query.count("WHERE COALESCE(governance_applies, false)") == 2


def test_recommendations_never_target_pipeline_ephemeral_grain(fakes: SimpleNamespace) -> None:
    # T001d : les pipelines DLT sont projetes (forecast, grain dlt_pipeline_id)
    # mais ne recoivent AUCUNE recommandation — pas de signal rightsizing/
    # reliability au grain pipeline dans le scope. Le rule engine ne lit que les
    # tables cluster (ALL_PURPOSE) + warehouse, jamais pipeline_cost_*.
    query = _recommendations_query(fakes)
    assert "pipeline_cost" not in query
    assert "dlt_pipeline_id" not in query
    assert "'PIPELINE'" not in query


def test_dedup_partition_key_includes_object_type(fakes: SimpleNamespace) -> None:
    # RIGHTSIZING/FINOPS combinent desormais des regles CLUSTER et WAREHOUSE :
    # la cle de dedoublonnage doit inclure object_type (pas seulement
    # object_id), sinon un cluster_id et un warehouse_id identiques (improbable
    # mais possible) se deduperaient a tort l'un l'autre.
    query = _recommendations_query(fakes)
    assert (
        "PARTITION BY cloud_provider, workspace_id, object_type, object_id\n"
        "            ORDER BY rule_priority"
        in query
    )


def test_warehouse_missing_auto_stop_yields_finops_rule(fakes: SimpleNamespace) -> None:
    query = _recommendations_query(fakes)
    assert "AND COALESCE(u.has_auto_stop, false) = false" in query
    assert "Auto-stop manquant" in query
    assert "'WAREHOUSE' AS object_type" in query


def test_warehouse_auto_stop_rule_treats_null_as_non_conformant(fakes: SimpleNamespace) -> None:
    # `has_auto_stop` est NULL sur 87% des warehouse-jours reels
    # (config warehouse non capturee, hors perimetre T004). Principe de
    # prudence FinOps : NULL est traite comme un manquement
    # (`COALESCE(x, false) = false`), pas exclu silencieusement
    # (`NULL = false` vaudrait NULL et la ligne serait perdue).
    query = _recommendations_query(fakes)
    assert "AND COALESCE(u.has_auto_stop, false) = false" in query


def test_warehouse_auto_stop_rule_skips_serverless_warehouses(fakes: SimpleNamespace) -> None:
    """Non-regression : aucune reco "auto-stop manquant" sur un warehouse serverless.

    La table d'utilisation met `has_auto_stop` a NULL en serverless (l'arret y
    est gere par la plateforme) et la regle ci-dessus lit tout NULL comme un
    manquement : sans garde explicite, CHAQUE warehouse serverless recevrait une
    reco FINOPS de severite HIGH sans action possible -- et, cette regle etant
    prioritaire par objet, elle masquerait au passage une vraie reco. Le garde
    porte sur `is_serverless`, pas sur `has_auto_stop IS NULL` : la prudence
    FinOps sur les warehouses classiques a config non capturee doit rester.
    """
    query = _recommendations_query(fakes)
    assert "WHERE COALESCE(u.is_serverless, false) = false" in query


def test_warehouse_oversized_yields_rightsizing_rule(fakes: SimpleNamespace) -> None:
    query = _recommendations_query(fakes)
    assert "WHERE u.utilization_status = 'OVER'" in query
    assert "Warehouse surdimensionne" in query


def test_warehouse_queue_time_threshold_yields_rightsizing_rule(fakes: SimpleNamespace) -> None:
    query = _recommendations_query(fakes)
    assert "WHERE qp.queue_time_p95_ms > 5000" in query
    assert "Augmenter max_clusters (scaling)" in query


def test_warehouse_spill_threshold_yields_rightsizing_rule(fakes: SimpleNamespace) -> None:
    query = _recommendations_query(fakes)
    assert "WHERE qp.spill_query_count > 10" in query
    assert "Tuner les requetes ou upsize cible" in query


def test_warehouse_failure_rate_threshold_yields_reliability_rule(fakes: SimpleNamespace) -> None:
    query = _recommendations_query(fakes)
    assert "WHERE qp.failure_rate_pct > 5.0" in query
    assert "'RELIABILITY' AS category, 'HIGH' AS severity" in query
    assert "Investiguer les requetes en echec" in query


def test_rightsizing_rules_prioritize_cluster_then_warehouse_over_then_queue_then_spill(
    fakes: SimpleNamespace,
) -> None:
    # Priorite RIGHTSIZING (rule_priority) : cluster OVER (1) > warehouse OVER
    # (2) > queue time (3) > spill (4) - au plus une ligne RIGHTSIZING par objet.
    query = _recommendations_query(fakes)
    rightsizing_block_start = query.index("rightsizing_candidates AS")
    finops_block_start = query.index("finops_candidates AS")
    rightsizing_block = query[rightsizing_block_start:finops_block_start]
    assert "1 AS rule_priority" in rightsizing_block
    assert "2 AS rule_priority" in rightsizing_block
    assert "3 AS rule_priority" in rightsizing_block
    assert "4 AS rule_priority" in rightsizing_block


def test_candidates_union_includes_all_four_category_ctes(fakes: SimpleNamespace) -> None:
    query = _recommendations_query(fakes)
    assert "SELECT * FROM rightsizing_candidates" in query
    assert "SELECT * FROM finops_candidates" in query
    assert "SELECT * FROM governance_candidates" in query
    assert "SELECT * FROM reliability_candidates" in query


def test_rightsizing_and_zombie_cluster_object_name_uses_efficiency_rolling_not_governance(
    fakes: SimpleNamespace,
) -> None:
    # object_name doit venir de latest_efficiency (deja porteuse de
    # cluster_name, cf. cluster_efficiency_rolling.py) et non
    # d'une jointure governance annexe : le perimetre de governance
    # (GOVERNANCE_ACTIVITY_WINDOW_DAYS) est plus etroit que celui des tables
    # *_rolling, ce qui produisait un object_name NULL pour tout cluster hors
    # de ce perimetre.
    query = _recommendations_query(fakes)
    assert "e.cluster_id AS object_id, e.cluster_name AS object_name," in query
    assert "g.cluster_name AS object_name" not in query


def test_auto_termination_candidate_object_name_uses_reliability_rolling(
    fakes: SimpleNamespace,
) -> None:
    # Meme correctif que la regle zombie/rightsizing, pour la regle FINOPS
    # auto-terminaison manquante (cluster_name porte par
    # gold_dbx_compute_cluster_reliability_rolling).
    query = _recommendations_query(fakes)
    assert "r.cluster_id AS object_id, r.cluster_name AS object_name," in query


def test_cluster_candidates_no_longer_join_governance_table_directly(
    fakes: SimpleNamespace,
) -> None:
    # Seules les regles GOVERNANCE lisent `governance` (l'ancre elle-meme) :
    # les regles RIGHTSIZING/FINOPS cluster ne doivent plus faire de
    # `LEFT JOIN governance g` annexe.
    query = _recommendations_query(fakes)
    assert "LEFT JOIN governance g" not in query


def test_warehouse_utilization_candidates_object_name_uses_utilization_not_cost(
    fakes: SimpleNamespace,
) -> None:
    # Meme cause racine que le bug CLUSTER, decouverte ensuite
    # sur les warehouses : `latest_warehouse_cost` (source billing) peut ne
    # pas couvrir un warehouse actif en utilisation/auto-stop mais sans
    # activite de cout/DBU sur la fenetre -> object_name doit venir de
    # latest_warehouse_utilization (deja porteuse de warehouse_name), jamais
    # de la jointure wc annexe.
    query = _recommendations_query(fakes)
    assert "u.warehouse_id AS object_id, u.warehouse_name AS object_name," in query
    assert "u.warehouse_id AS object_id, wc.warehouse_name AS object_name," not in query


def test_warehouse_query_performance_candidates_object_name_uses_query_performance_not_cost(
    fakes: SimpleNamespace,
) -> None:
    # Meme correctif, pour les regles adossees a
    # latest_warehouse_query_performance (queue time, spill, failure rate) :
    # object_name doit venir de qp.warehouse_name, jamais de wc.warehouse_name.
    query = _recommendations_query(fakes)
    assert query.count("qp.warehouse_id AS object_id, qp.warehouse_name AS object_name,") == 3
    assert "qp.warehouse_id AS object_id, wc.warehouse_name AS object_name," not in query


def test_warehouse_candidates_no_longer_select_cluster_type(fakes: SimpleNamespace) -> None:
    # cluster_type retire de gold_dbx_compute_recommendations (decision
    # produit) : plus aucune occurrence, ni cote CLUSTER ni cote WAREHOUSE.
    query = _recommendations_query(fakes)
    assert "cluster_type" not in query


def test_object_name_threaded_through_existing_state_stub_and_final_select(
    fakes: SimpleNamespace,
) -> None:
    query = _recommendations_query(fakes, existing_tables=set())
    assert "CAST(NULL AS STRING) AS object_name" in query
    assert (
        "cloud_provider, workspace_id, object_type, object_id, object_name,\n"
        "        category, mode, title, detail, recommended_action, "
        "estimated_savings_usd,"
        in query
    )

