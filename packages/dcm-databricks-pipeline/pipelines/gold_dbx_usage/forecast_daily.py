"""Agregation gold `gold_dbx_usage_forecast_daily` (socle predictif, T004).

Projection des 4 metriques d'adoption/FinOps par data product via
`ai_forecast` (fonction SQL native Databricks, table-valued) sur l'historique
deja materialise de `gold_dbx_usage_table_popularity_daily` -- alimente
l'anticipation d'adoption/declin et de budget (cf. `usage_datamapping.md`
§4.2). Une seule table source (contrairement a
`pipelines.gold_dbx_compute.forecast` qui projette 9 combinaisons sur 5
tables clusters/jobs/warehouses) : un seul appel `ai_forecast` multi-metrique
suffit ici.

`ai_forecast` est table-valued (`SELECT * FROM ai_forecast(...)`, jamais un
scalaire) : PySpark n'a pas d'API DataFrame dediee, l'appel passe entierement
par du SQL. `group_col` de `ai_forecast` n'accepte qu'UNE seule colonne : les
2 colonnes d'identite (`cloud_provider`, `table_full_name`) sont donc
concatenees en une cle composite (`object_key`) avant l'appel, puis
re-eclatees apres (cf. `_split_object_key_columns`).

L'historique d'entrainement est DENSIFIE sur le calendrier de la fenetre (cf.
`_dense_observed_sql`) : `gold_dbx_usage_table_popularity_daily` n'a une ligne
que les jours ou la table est lue, alors que les 4 metriques projetees sont
additives (un jour sans lecture vaut 0 requete, 0 consommateur, 0 $, 0 octet).
Sans densification, le modele ajuste le niveau sur les seuls jours ACTIFS et la
projection - lue en aval comme une valeur par jour calendaire - est surevaluee
du rapport jours_calendaires / jours_actifs. `frequency => 'D'` fixe le pas de
sortie au jour plutot que de le laisser inferer d'une serie a trous.

`ai_forecast` ne leve AUCUNE erreur sur une serie degeneree : elle rend des
`predicted_value` NULL, ou ajuste un modele explosif sur une serie a
decrochement et projette plusieurs ordres de grandeur au-dessus du reel. Trois
garde-fous, chacun couvrant ce que les autres laissent passer : la fenetre
exclut le jour en cours (`_observed_window`), les series trop courtes ne sont
pas projetees (`min_observed_days`, superieur a l'horizon), et la requete ne
publie ni les valeurs NULL ni celles qui depassent `max_observed_ratio` fois
le maximum journalier observe de LEUR PROPRE serie. Ce dernier plafond ECRETE
en plus la borne haute de l'intervalle de confiance (cf.
`_CLIPPED_UPPER_BOUND`) : une valeur projetee plausible peut porter un
intervalle qui ne l'est pas.

`ai_forecast` exige un Pro/Serverless SQL Warehouse (doc officielle
Databricks) -- pas du SQL Spark standard executable sur n'importe quel
compute, incompatible avec l'environnement serverless generique d'une tache
`python_wheel_task`. `render_forecast_query` reste une fonction PURE
(construit le texte SQL, ne l'execute pas).

`write_usage_forecast` execute l'ECRITURE COMPLETE (calcul + MERGE/CREATE)
directement sur `warehouse_id`, sans jamais faire transiter les lignes du
resultat par le driver Python (contrairement a une premiere version qui
rappatriait les lignes via l'API Statement Execution puis les reinjectait en
DataFrame via `spark.createDataFrame` : au grain reel constate en dev
(~530k data products actifs x 4 metriques x horizon), ceci construit un
unique message protobuf `LocalRelation` (Spark Connect) qui depasse la
limite de taille gRPC et se corrompt en transit
-- `InvalidProtocolBufferException`/`InvalidWireTypeException`, reproduit 2
fois independamment de la taille du SQL Warehouse). Le calcul ET l'ecriture
Delta (MERGE INTO / CREATE TABLE AS SELECT) se font desormais entierement
cote SQL Warehouse -- `spark` (job cluster generique) ne sert plus qu'a
verifier l'existence de la table cible (`tableExists`, metadonnee legere) et
a attacher les commentaires de table/colonnes (`spark.sql`, cf.
`pipelines.common.writers._apply_table_comments`, reutilise tel quel).
"""

from __future__ import annotations

import time
from datetime import date
from typing import TYPE_CHECKING, Any

from pipelines.common.writers import _apply_table_comments

if TYPE_CHECKING:
    from collections.abc import Mapping

    from databricks.sdk.service.sql import ExternalLink
    from pyspark.sql import SparkSession

# Separateur de la cle composite `object_key` (cf. docstring module). `::` :
# jamais present dans un `cloud_provider`/`table_full_name` reel, ET sans
# signification speciale en regex (contrairement a `||`, une alternation) --
# `split()` (regex Java) peut donc le reutiliser tel quel, sans echappement.
_OBJECT_KEY_SEPARATOR = "::"

# Bornes metier passees a `ai_forecast` (`parameters` JSON, cf. reference
# `databricks-ai-functions/3-ai-forecast.md`) : aucune des 4 metriques
# projetees ne peut etre negative (nombre de requetes, consommateurs
# distincts, cout, octets lus).
_NON_NEGATIVE_FORECAST_PARAMETERS = '{"global_floor": 0}'

# Ecretage de la borne HAUTE au plafond de plausibilite (cf.
# `max_observed_ratio`). Le filtre sur `predicted_value` ne suffit pas :
# `ai_forecast` peut rendre une valeur projetee plausible assortie d'un
# intervalle de confiance de plusieurs ordres de grandeur au-dessus, et
# l'exposition SOMME `upper_bound` sur tout le parc pour tracer son enveloppe --
# une seule borne aberrante y ecrase la courbe du realise.
#
# ECRETE, pas filtre : la ligne est plausible, c'est son intervalle qui ne l'est
# pas ; la supprimer couterait de la couverture pour un defaut qui ne touche pas
# la valeur projetee. `CASE` et non `LEAST` : `LEAST` IGNORE les NULL et
# renverrait le plafond la ou le modele n'a rendu aucune borne, fabriquant une
# valeur -- ici `NULL > plafond` vaut NULL, la branche `ELSE` preserve le NULL.
# La borne BASSE n'a besoin de rien : `global_floor` la tient a 0 par le bas, et
# elle reste sous `predicted_value`, deja plafonnee par le `WHERE`.
_CLIPPED_UPPER_BOUND = (
    "CASE WHEN upper_bound > max_plausible_value"
    " THEN max_plausible_value ELSE upper_bound END AS upper_bound"
)

# Les 4 metriques projetees, dans l'ordre de `value_col`. Toutes ADDITIVES sur
# la journee : un jour sans lecture vaut 0, ce qui rend la densification de
# l'historique legitime pour les quatre (cf. `_dense_observed_sql`).
_FORECAST_METRICS = (
    "request_count",
    "distinct_consumers",
    "estimated_cost_usd",
    "data_read_bytes",
)

# Cle composite de groupe (cf. docstring module), expression SQL reutilisee a
# l'identique dans les trois sous-requetes de `_dense_observed_sql` : les
# `GROUP BY`/`JOIN` portent sur cette expression, jamais sur un alias, pour ne
# pas dependre de la resolution d'alias lateral.
_OBJECT_KEY_EXPR = f"concat_ws('{_OBJECT_KEY_SEPARATOR}', cloud_provider, table_full_name)"

# Delai entre deux verifications de statut d'un statement en cours :
# `ai_forecast` (ajustement de modele) depasse souvent le `wait_timeout` max
# de l'API Statement Execution (50s) -- on poll donc jusqu'a l'etat terminal.
_STATEMENT_POLL_INTERVAL_SECONDS = 2.0


def _observed_window(observed_lower_bound: date) -> str:
    """Predicat de la fenetre d'entrainement, identique partout.

    La borne HAUTE (`period_start < current_date()`) exclut le jour en cours :
    `table_popularity_daily` le contient des la premiere execution de la
    journee, mais partiellement (mesure en dev : ~1,5 M requetes a mi-journee
    contre ~5,5 M sur une journee pleine). Sans cette borne, le modele lit ce
    creux artificiel comme un effondrement reel, et l'horizon s'ancre sur un
    jour incomplet -- la prevision ne commence alors que DEMAIN, laissant
    aujourd'hui sans aucune valeur ni observee ni predite.
    """
    return (
        f"period_start >= DATE '{observed_lower_bound.isoformat()}'"
        " AND period_start < current_date()"
    )


def _split_object_key_columns(alias: str) -> str:
    """Fragment SQL : re-eclate `object_key` (`{alias}.object_key`) en 2 colonnes.

    Inverse de `concat_ws('::', cloud_provider, table_full_name)` --
    `ai_forecast` ne renvoie que la cle de groupe composite en sortie (cf.
    docstring module), jamais les colonnes d'origine qui la composent.
    """
    parts = f"split({alias}.object_key, '{_OBJECT_KEY_SEPARATOR}')"
    return f"{parts}[0] AS cloud_provider, {parts}[1] AS object_id"


def _exclude_deleted_tables(table_catalog_table: str) -> str:
    """Fragment SQL : anti-jointure ecartant les tables supprimees au catalogue.

    Filtre en ENTREE, applique aux trois sous-requetes de l'historique densifie :
    une table supprimee ne doit peser ni sur l'eligibilite, ni sur le calendrier,
    ni sur les valeurs d'entrainement. L'ecarter en sortie la laisserait consommer
    du compute `ai_forecast` et deformer la densification.

    `LEFT ANTI JOIN` et non `NOT IN`/`NOT EXISTS` : ne publie aucune colonne du
    cote droit, donc les references non qualifiees des sous-requetes
    (`cloud_provider`, `period_start`, les 4 metriques) restent non ambigues.
    """
    return f"""LEFT ANTI JOIN (
                        SELECT cloud_provider, table_full_name
                        FROM {table_catalog_table}
                        WHERE is_deleted
                    ) deleted
                      ON deleted.cloud_provider = p.cloud_provider
                     AND deleted.table_full_name = p.table_full_name"""


def _dense_observed_sql(
    *,
    table_popularity_daily_table: str,
    table_catalog_table: str,
    observed_lower_bound: date,
    min_observed_days: int,
) -> str:
    """Fragment SQL : historique d'entrainement densifie, argument de `observed =>`.

    Une ligne par (data product eligible x jour de la fenetre), les jours sans
    lecture a 0 (cf. docstring module). Trois sous-requetes sur la meme table,
    toutes trois amputees des tables supprimees (cf. `_exclude_deleted_tables`) :

      - `eligible` : les data products ayant au moins `min_observed_days` jours
        d'activite REELLE dans la fenetre. Filtre l'extrapolation depuis un
        point isole, et borne le volume (le produit cartesien ci-dessous porte
        sur ce seul perimetre).
      - `calendar` : les jours DISTINCTS presents dans la fenetre, plutot qu'un
        `sequence()` de dates fabriquees. Deux proprietes utiles : la borne
        haute est le dernier jour reellement charge (jamais un jour que la
        source n'a pas encore livre, qui serait densifie a 0 et tirerait la
        prevision vers le bas), et le calendrier reste dense des lors qu'au
        moins une table du parc est lue chaque jour.
      - `daily` : les valeurs observees, jointes en LEFT JOIN sur la grille.
    """
    window = _observed_window(observed_lower_bound)
    exclusion = _exclude_deleted_tables(table_catalog_table)
    coalesced = ",\n                    ".join(
        f"COALESCE(daily.{metric}, 0) AS {metric}" for metric in _FORECAST_METRICS
    )
    metric_columns = ", ".join(_FORECAST_METRICS)
    return f"""
                SELECT
                    eligible.object_key,
                    calendar.period_start,
                    {coalesced}
                FROM (
                    SELECT {_OBJECT_KEY_EXPR} AS object_key
                    FROM {table_popularity_daily_table} p
                    {exclusion}
                    WHERE {window}
                    GROUP BY {_OBJECT_KEY_EXPR}
                    HAVING COUNT(DISTINCT period_start) >= {min_observed_days}
                ) eligible
                CROSS JOIN (
                    SELECT DISTINCT period_start
                    FROM {table_popularity_daily_table} p
                    {exclusion}
                    WHERE {window}
                ) calendar
                LEFT JOIN (
                    SELECT {_OBJECT_KEY_EXPR} AS object_key, period_start, {metric_columns}
                    FROM {table_popularity_daily_table} p
                    {exclusion}
                    WHERE {window}
                ) daily
                  ON daily.object_key = eligible.object_key
                 AND daily.period_start = calendar.period_start"""


def render_forecast_query(
    *,
    table_popularity_daily_table: str,
    table_catalog_table: str,
    observed_lower_bound: date,
    horizon_date: date,
    horizon_days: int,
    prediction_interval_width: float = 0.95,
    min_observed_days: int = 3,
    max_observed_ratio: float = 10.0,
) -> str:
    """Construit le texte SQL de `gold_dbx_usage_forecast_daily` (pur, non execute).

    Fonction PURE (aucun acces reseau/compute) : separee de
    `build_usage_forecast` pour rester testable par simple assertion de
    texte (cf. `test_forecast_daily.py`), independamment du mecanisme
    d'execution (`ai_forecast` doit tourner sur un SQL Warehouse, cf.
    docstring module).

    Args:
        table_popularity_daily_table: nom qualifie de
            `gold_dbx_usage_table_popularity_daily` (historique source des 4
            metriques).
        table_catalog_table: nom qualifie de `gold_dbx_usage_table_catalog` --
            SEULE table portant l'etat de cycle de vie (cf.
            `_exclude_deleted_tables`) : `table_popularity_daily` est une table
            de fait, un MERGE incremental y figerait `is_deleted` sur tout
            l'historique anterieur.
        observed_lower_bound: borne basse (`period_start >=`) appliquee AVANT
            l'appel `ai_forecast` -- calculee par l'appelant (`today -
            FORECAST_OBSERVED_LOOKBACK_DAYS`, cf. `pipelines.gold_dbx_usage.specs`).
            Double effet, par construction (un seul filtre, pas deux
            mecanismes separes) : (1) borne l'historique d'entrainement a une
            fenetre fixe ; (2) un data product dont TOUTES les lignes sont
            anterieures a cette borne n'a plus aucune ligne dans `observed`
            -> `ai_forecast` ne produit aucune prevision pour lui (evite un
            volume de lignes de "prevision" disproportionne pour un data
            product sans activite recente, meme raisonnement que
            `pipelines.gold_dbx_compute.forecast`).
        horizon_date: plafond ABSOLU passe a `horizon` de `ai_forecast` --
            calcule par l'appelant (`today + FORECAST_HORIZON_DAYS`).
        horizon_days: nombre de jours projetes REELLEMENT conserves, compte a
            partir du dernier jour observe (`FORECAST_HORIZON_DAYS`). Les deux
            bornes ne sont pas redondantes : `ai_forecast` projette du jour
            suivant la derniere observation jusqu'a `horizon`, donc le nombre
            de jours produits varie avec la fraicheur de la source (une source
            en retard de 2 jours produit 2 jours de "prevision" deja passes, et
            9 lignes la ou la table en annonce 7). Le filtre relatif au dernier
            jour observe rend ce nombre constant.
        prediction_interval_width: largeur de l'intervalle de confiance
            (0-1, defaut 0.95 = defaut natif `ai_forecast`).
        min_observed_days: jours d'activite reelle minimum pour etre projete
            (cf. `specs.FORECAST_MIN_OBSERVED_DAYS` et `_dense_observed_sql`).
        max_observed_ratio: plafond de PLAUSIBILITE, relatif a la serie (cf.
            `specs.FORECAST_MAX_OBSERVED_RATIO`). Une prevision superieure a
            `max_observed_ratio x` le maximum journalier observe de SA PROPRE
            serie n'est pas publiee : `ai_forecast` ne leve aucune erreur sur
            une serie a decrochement et peut ajuster un modele explosif
            (mesure en dev : 2,9 x 10^15 requetes/jour projetees pour un parc
            qui en observe 5,5 x 10^6). Un plafond scalaire (`global_cap`) est
            aveugle a ce cas -- une petite serie explose vers une valeur
            absurde mais inferieure au plafond global ; seule une borne
            relative a la serie l'attrape. Le meme plafond ECRETE
            `upper_bound` (cf. `_CLIPPED_UPPER_BOUND`), qu'`ai_forecast` peut
            rendre plusieurs ordres de grandeur au-dessus d'une
            `predicted_value` pourtant plausible.

    Returns:
        Le texte SQL complet (une ligne par
        `(cloud_provider, object_type, object_id, metric_name, horizon_date)`,
        object_type toujours 'DATA_PRODUCT').

    Grain : `(cloud_provider, object_type, object_id, metric_name,
    horizon_date)`. Source : `gold_dbx_usage_table_popularity_daily`
    uniquement (jamais les tables curated directement).

    Un seul appel `ai_forecast` multi-metrique (`value_col => array(...)`,
    PAS une chaine separee par virgules -- une chaine `'a,b'` est lue comme UN
    seul nom de colonne litteral, jamais comme deux colonnes) sur les 4
    metriques `request_count`/`distinct_consumers`/`estimated_cost_usd`/
    `data_read_bytes`, groupe par `object_key` (cf.
    `_split_object_key_columns`) : une serie temporelle independante par data
    product, sur l'historique densifie de `_dense_observed_sql`. Le resultat
    (colonnes `<metrique>_forecast`/`_lower`/`_upper`) est ensuite depivote
    (`UNION ALL`) en une ligne par metrique.
    """
    observed = _dense_observed_sql(
        table_popularity_daily_table=table_popularity_daily_table,
        table_catalog_table=table_catalog_table,
        observed_lower_bound=observed_lower_bound,
        min_observed_days=min_observed_days,
    )
    window = _observed_window(observed_lower_bound)
    last_observed_day = (
        f"(SELECT MAX(period_start) FROM {table_popularity_daily_table}"
        f" WHERE {window})"
    )
    observed_maximums = ",\n            ".join(
        f"MAX({metric}) AS {metric}_max" for metric in _FORECAST_METRICS
    )
    unpivoted = "\n\n        UNION ALL\n\n".join(
        f"""        SELECT
            {_split_object_key_columns("f")},
            'DATA_PRODUCT' AS object_type,
            f.period_start AS horizon_date,
            '{metric}' AS metric_name,
            f.{metric}_forecast AS predicted_value,
            f.{metric}_lower AS lower_bound,
            f.{metric}_upper AS upper_bound,
            b.{metric}_max * {max_observed_ratio} AS max_plausible_value
        FROM popularity_forecast f
        JOIN observed_bounds b ON b.object_key = f.object_key"""
        for metric in _FORECAST_METRICS
    )
    return f"""
    WITH observed_bounds AS (
        SELECT
            {_OBJECT_KEY_EXPR} AS object_key,
            {observed_maximums}
        FROM {table_popularity_daily_table}
        WHERE {window}
        GROUP BY {_OBJECT_KEY_EXPR}
    ),
    popularity_forecast AS (
        SELECT * FROM ai_forecast(
            observed => TABLE({observed}
            ),
            horizon => DATE '{horizon_date.isoformat()}',
            time_col => 'period_start',
            value_col => array(
                'request_count', 'distinct_consumers', 'estimated_cost_usd', 'data_read_bytes'
            ),
            group_col => 'object_key',
            frequency => 'D',
            prediction_interval_width => {prediction_interval_width},
            parameters => '{_NON_NEGATIVE_FORECAST_PARAMETERS}'
        )
        WHERE period_start <= date_add({last_observed_day}, {horizon_days})
    ),
    unpivoted AS (
{unpivoted}
    )
    SELECT
        cloud_provider,
        object_type,
        object_id,
        metric_name,
        horizon_date,
        predicted_value,
        lower_bound,
        {_CLIPPED_UPPER_BOUND},
        'ai_forecast' AS method
    FROM unpivoted
    WHERE predicted_value IS NOT NULL
      AND predicted_value <= max_plausible_value
    """


def _fetch_external_link_rows(link: ExternalLink) -> list[list[Any]]:
    """Telecharge et parse un chunk `EXTERNAL_LINKS` (cf. `_execute_statement`).

    L'URL pre-signee (`link.external_link`) sert directement le contenu du
    chunk (ici un tableau JSON, `format=Format.JSON_ARRAY`) : simple GET HTTP,
    sans authentification Databricks (le lien porte sa propre credential
    temporaire, cf. doc `ExternalLink.external_link`). `link.http_headers`
    est vide dans ce cas (pas de cle de dechiffrement a transmettre) mais
    transmis par prudence si jamais present.
    """
    import requests

    resp = requests.get(link.external_link, headers=link.http_headers or {}, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _execute_statement(warehouse_id: str, query: str, profile: str | None) -> list[list[Any]]:
    """Execute `query` sur un SQL Warehouse et renvoie les lignes brutes.

    Identique a `pipelines.gold_dbx_compute.forecast._execute_statement`
    (duplique plutot que partage entre domaines gold, cf. research.md R6) :
    `ai_forecast` exige un Pro/Serverless SQL Warehouse (doc officielle
    Databricks) -- incompatible avec l'environnement serverless generique du
    job (cf. docstring module). Poll jusqu'a l'etat terminal : le
    `wait_timeout` max de l'API (50s) est souvent insuffisant pour
    l'ajustement de modele `ai_forecast`. `profile` est `None` sur cluster
    (authentification native au contexte du job) ou le profil CLI de debug
    local.

    `disposition=EXTERNAL_LINKS` (pas `INLINE`) : le volume reel (parc data
    products, 4 metriques par passe) peut depasser la limite de 25 MiB de
    `INLINE` ; `EXTERNAL_LINKS` n'a pas de limite de taille comparable
    (chaque chunk est telecharge separement via une URL pre-signee, cf.
    `_fetch_external_link_rows`).
    """
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.sql import Disposition, Format, StatementState

    workspace = WorkspaceClient(profile=profile) if profile else WorkspaceClient()
    response = workspace.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=query,
        wait_timeout="50s",
        format=Format.JSON_ARRAY,
        disposition=Disposition.EXTERNAL_LINKS,
    )
    statement_id = response.statement_id
    while response.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(_STATEMENT_POLL_INTERVAL_SECONDS)
        response = workspace.statement_execution.get_statement(statement_id)
    if response.status.state != StatementState.SUCCEEDED:
        error = response.status.error
        message = error.message if error else str(response.status.state)
        raise RuntimeError(f"ai_forecast statement {response.status.state} : {message}")
    if response.result is None or not response.result.external_links:
        return []
    rows: list[list[Any]] = []
    links = list(response.result.external_links)
    seen_chunk_indexes = {link.chunk_index for link in links}
    while links:
        link = links.pop(0)
        rows.extend(_fetch_external_link_rows(link))
        next_index = link.next_chunk_index
        if next_index is not None and next_index not in seen_chunk_indexes:
            seen_chunk_indexes.add(next_index)
            chunk = workspace.statement_execution.get_statement_result_chunk_n(
                statement_id, next_index
            )
            links.extend(chunk.external_links or [])
    return rows


def render_forecast_write_sql(
    *,
    target_table: str,
    table_exists: bool,
    merge_keys: tuple[str, ...],
    table_popularity_daily_table: str,
    table_catalog_table: str,
    observed_lower_bound: date,
    horizon_date: date,
    horizon_days: int,
    prediction_interval_width: float = 0.95,
    min_observed_days: int = 3,
    max_observed_ratio: float = 10.0,
) -> str:
    """Construit le texte SQL COMPLET d'ecriture (pur, non execute).

    Contrairement a `render_forecast_query` (juste le calcul), ce texte
    ECRIT directement dans `target_table` -- `CREATE TABLE ... AS SELECT`
    (premiere execution) ou `MERGE INTO` (executions suivantes) -- afin que
    ni le calcul ni l'ecriture ne fassent jamais transiter les lignes par le
    driver Python (cf. docstring module).

    Deduplique sur `merge_keys` via `ROW_NUMBER()` (equivalent SQL de
    `DataFrame.dropDuplicates` utilise par `pipelines.common.writers.
    merge_into_table` sur les autres tables gold) : `ai_forecast` ne devrait
    produire qu'une ligne par cle mais un `MERGE INTO` echoue
    (`DELTA_MULTIPLE_SOURCE_ROW_MATCHING_TARGET_ROW`) si plusieurs lignes
    source correspondent a la meme ligne cible, meme garantie que
    `merge_into_table` par securite. Le tri du `ROW_NUMBER()` porte sur
    `predicted_value` : `method` est une constante ('ai_forecast'), donc un tri
    sur cette colonne laisse le choix de la ligne conservee a l'ordre physique
    d'evaluation, non deterministe.

    `WHEN MATCHED THEN UPDATE SET *` / `WHEN NOT MATCHED THEN INSERT *` :
    supporte par Databricks SQL quand les colonnes source/cible portent les
    memes noms (cf. `_FORECAST_COLUMNS`) -- evite d'enumerer chaque colonne.

    `WHEN NOT MATCHED BY SOURCE AND t.horizon_date >= current_date() THEN
    DELETE` purge les previsions futures d'un run precedent que le run courant
    ne produit plus (data product devenu inactif, ou passe sous
    `min_observed_days`) : sans cette clause un MERGE pur upsert les laisse en
    place indefiniment, et l'API les additionne a la prevision courante. Le
    predicat protege l'historique : les horizons deja passes restent en table
    (trace de ce qui avait ete predit), seul le futur est reconstruit a chaque
    run.

    Args:
        target_table: nom qualifie de `gold_dbx_usage_forecast_daily`.
        table_exists: `spark.catalog.tableExists(target_table)` -- calcule
            par l'appelant (verification de metadonnee legere, cote job
            cluster, jamais un scan de donnees).
        merge_keys: cles de merge (grain de la table, cf. `specs.
            FORECAST_DAILY_MERGE_KEYS`).
        table_popularity_daily_table: cf. `render_forecast_query`.
        table_catalog_table: cf. `render_forecast_query`.
        observed_lower_bound: cf. `render_forecast_query`.
        horizon_date: cf. `render_forecast_query`.
        horizon_days: cf. `render_forecast_query`.
        prediction_interval_width: cf. `render_forecast_query`.
        min_observed_days: cf. `render_forecast_query`.
        max_observed_ratio: cf. `render_forecast_query`.

    Returns:
        Le texte SQL complet (`CREATE TABLE ... AS SELECT` ou
        `MERGE INTO ...`), a executer via `_execute_statement` sur le SQL
        Warehouse (jamais sur le job cluster generique, cf. docstring
        module).
    """
    forecast_query = render_forecast_query(
        table_popularity_daily_table=table_popularity_daily_table,
        table_catalog_table=table_catalog_table,
        observed_lower_bound=observed_lower_bound,
        horizon_date=horizon_date,
        horizon_days=horizon_days,
        prediction_interval_width=prediction_interval_width,
        min_observed_days=min_observed_days,
        max_observed_ratio=max_observed_ratio,
    )
    partition_by = ", ".join(merge_keys)
    deduped_query = f"""
    SELECT cloud_provider, object_type, object_id, metric_name, horizon_date,
           predicted_value, lower_bound, upper_bound, method,
           current_timestamp() AS _generated_at
    FROM (
        SELECT *, ROW_NUMBER() OVER (
            PARTITION BY {partition_by} ORDER BY predicted_value DESC NULLS LAST
        ) AS _row_number
        FROM ({forecast_query}) AS forecast
    ) AS deduped
    WHERE _row_number = 1
    """
    if not table_exists:
        return f"CREATE TABLE {target_table} USING DELTA AS {deduped_query}"
    merge_condition = " AND ".join(f"t.{key} = s.{key}" for key in merge_keys)
    return f"""
    MERGE INTO {target_table} AS t
    USING ({deduped_query}) AS s
    ON {merge_condition}
    WHEN MATCHED THEN UPDATE SET *
    WHEN NOT MATCHED THEN INSERT *
    WHEN NOT MATCHED BY SOURCE AND t.horizon_date >= current_date() THEN DELETE
    """


def write_usage_forecast(
    spark: SparkSession,
    *,
    warehouse_id: str,
    target_table: str,
    table_popularity_daily_table: str,
    table_catalog_table: str,
    observed_lower_bound: date,
    horizon_date: date,
    horizon_days: int,
    merge_keys: tuple[str, ...],
    prediction_interval_width: float = 0.95,
    min_observed_days: int = 3,
    max_observed_ratio: float = 10.0,
    column_comments: Mapping[str, str] | None = None,
    table_comment: str | None = None,
    profile: str | None = None,
) -> None:
    """Calcule ET ecrit `gold_dbx_usage_forecast_daily` (4 metriques/data product).

    `ai_forecast` exige un Pro/Serverless SQL Warehouse (doc officielle
    Databricks) -- un environnement serverless generique de job
    (`SparkSession.builder.getOrCreate()`) n'en est pas un : le calcul ET
    l'ecriture Delta (`render_forecast_write_sql`) s'executent donc
    entierement cote SQL Warehouse via l'API Statement Execution, jamais via
    `spark.sql`/`merge_into_table` (cf. docstring module -- une premiere
    version rapatriait les lignes vers le driver Python puis les reinjectait
    en DataFrame Spark, ce qui echouait en volume reel).

    Args:
        spark: session Spark du job -- utilisee uniquement pour
            `tableExists` (metadonnee legere) et l'attache des commentaires
            de table/colonnes (`spark.sql`), jamais pour executer
            `ai_forecast` ni l'ecriture Delta elle-meme (cf. ci-dessus).
        warehouse_id: identifiant du SQL Warehouse (Pro/Serverless) contre
            lequel `ai_forecast` et l'ecriture sont executes (`--warehouse_id`
            du job, cf. `entrypoint.py`/`resources/job_dcm_gold_dbx_usage.yml`).
        target_table: nom qualifie de `gold_dbx_usage_forecast_daily`.
        table_popularity_daily_table: cf. `render_forecast_query`.
        table_catalog_table: cf. `render_forecast_query`.
        observed_lower_bound: cf. `render_forecast_query`.
        horizon_date: cf. `render_forecast_query`.
        horizon_days: cf. `render_forecast_query`.
        merge_keys: cf. `render_forecast_write_sql`.
        prediction_interval_width: cf. `render_forecast_query`.
        min_observed_days: cf. `render_forecast_query`.
        max_observed_ratio: cf. `render_forecast_query`.
        column_comments: cf. `pipelines.common.writers._apply_table_comments`.
        table_comment: cf. `pipelines.common.writers._apply_table_comments`.
        profile: `None` sur cluster (authentification native au contexte du
            job) ou profil CLI de debug local.
    """
    table_exists = spark.catalog.tableExists(target_table)
    query = render_forecast_write_sql(
        target_table=target_table,
        table_exists=table_exists,
        merge_keys=merge_keys,
        table_popularity_daily_table=table_popularity_daily_table,
        table_catalog_table=table_catalog_table,
        observed_lower_bound=observed_lower_bound,
        horizon_date=horizon_date,
        horizon_days=horizon_days,
        prediction_interval_width=prediction_interval_width,
        min_observed_days=min_observed_days,
        max_observed_ratio=max_observed_ratio,
    )
    _execute_statement(warehouse_id, query, profile)
    _apply_table_comments(
        spark, target_table, column_comments=column_comments, table_comment=table_comment
    )
