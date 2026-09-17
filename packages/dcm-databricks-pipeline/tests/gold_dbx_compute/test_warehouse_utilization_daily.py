"""Tests de `pipelines.gold_dbx_compute.warehouse_utilization_daily`.

Pas de vraie `SparkSession` : `build_warehouse_utilization_daily` construit un
unique `spark.sql(...)`, verifie ici via le texte SQL genere (`FakeSpark`).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from pipelines.gold_dbx_compute.warehouse_utilization_daily import (
    build_warehouse_utilization_daily,
)


def _utilization_query(fakes: SimpleNamespace, lower_bound: date | None) -> tuple[str, object]:
    sentinel = fakes.DataFrame("warehouse_utilization_daily_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_warehouse_utilization_daily(
        spark,
        warehouse_events_table="it.sch.curated_dbx_compute_warehouse_events",
        warehouses_table="it.sch.curated_dbx_compute_warehouses",
        query_history_table="it.sch.curated_dbx_query_history",
        cost_daily_table="it.sch.gold_dbx_compute_warehouse_cost_daily",
        billing_usage_table="it.sch.curated_dbx_billing_usage",
        lower_bound=lower_bound,
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0], result


def test_utilization_daily_full_run_has_no_lower_bound_filter(fakes: SimpleNamespace) -> None:
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert "event_time >= DATE" not in query
    assert "to_date(start_time) >= DATE" not in query
    assert "period_start >= DATE" not in query
    assert "usage_date >= DATE" not in query


def test_utilization_daily_incremental_run_buffers_events_and_query_history_not_output(
    fakes: SimpleNamespace,
) -> None:
    """`event_time` lit 30 jours avant `lower_bound`, `query_history` 1 jour ; sortie non.

    Le tampon `event_time` (`WAREHOUSE_SESSION_LOOKBACK_DAYS`) permet de
    reconstruire une session encore ouverte (warehouse serverless jamais
    arrete) dont le `STARTING` precede la fenetre incrementale. Le tampon
    `query_history` (`WAREHOUSE_QUERY_HISTORY_LOOKBACK_DAYS`) permet de
    conserver une requete demarree la veille de `lower_bound` et se
    terminant dans la fenetre lue, pour que sa portion du 1er jour de la
    fenetre soit comptee dans `active_query_hours`
    (`query_history_by_day` decoupe ensuite la requete par jour calendaire
    traverse). La sortie n'a pas besoin de tampon : elle reste bornee
    exactement a `lower_bound`. La facturation (discriminant serverless) non
    plus : elle est jointe sur le MEME jour que la ligne de sortie.
    """
    query, _ = _utilization_query(fakes, lower_bound=date(2026, 8, 14))
    assert "AND event_time >= DATE '2026-07-15'" in query
    assert "AND to_date(start_time) >= DATE '2026-08-13'" in query
    assert "AND period_start >= DATE '2026-08-14'" in query
    assert "AND usage_date >= DATE '2026-08-14'" in query


def test_utilization_daily_derives_running_hours_from_starting_stopped_sessions(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert "event_type = 'STARTING'" in query
    assert "next_event_type = 'STOPPED'" in query
    assert "SUM(session_hours) AS running_hours" in query


def test_utilization_daily_open_session_capped_at_current_timestamp(
    fakes: SimpleNamespace,
) -> None:
    """Non-regression : une session sans `STOPPED` visible reste "ouverte".

    Un `STARTING` qui n'est suivi d'AUCUN autre evenement dans la fenetre lue
    (le warehouse ne s'est peut-etre jamais arrete depuis, cf.
    `eed997d23b820ef3` dans le sub-spec T003) ne doit pas etre rejete : sa
    fin doit etre bornee a `current_timestamp()` (l'instant du run) au lieu
    d'etre exclue de `running_hours`, quitte a etre corrigee au prochain run
    qui verra le vrai `STOPPED`.
    """
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert "WHEN next_event_type = 'STOPPED' THEN next_event_time" in query
    assert "ELSE current_timestamp()" in query
    assert "next_event_type IS NULL" in query



def test_utilization_daily_dedupes_consecutive_starting_events(
    fakes: SimpleNamespace,
) -> None:
    """Non-regression : seul le PREMIER `STARTING` d'une serie ouvre une session.

    Un warehouse peut enchainer plusieurs `STARTING` sans `STOPPED` entre eux
    (ex. `37125f2e1acc22fd`, 3 `STARTING` d'affilee, cf. sub-spec T003). Sans
    deduplication, ces sessions intermediaires seraient jetees et
    `running_hours` severement sous-estime. Le `LAG` doit exclure tout
    `STARTING` dont le precedent (dans la sous-sequence STARTING/STOPPED)
    est aussi un `STARTING`.
    """
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert "LAG(event_type) OVER (" in query
    assert "AS prev_event_type" in query
    assert "event_type = 'STARTING'" in query
    assert "AND prev_event_type <=> 'STARTING'" in query
    assert "FROM tagged_events" in query


def test_utilization_daily_first_ever_starting_event_is_not_dropped(
    fakes: SimpleNamespace,
) -> None:
    """Non-regression : le tout premier STARTING d'un warehouse doit ouvrir une session.

    Bug confirme en donnee reelle (warehouse `3355bb208bc59ad5`, seule session
    jamais enregistree : STARTING -> STOPPED, aucun evenement precedent) :
    avec `prev_event_type = 'STARTING'` (egalite non null-safe), le premier
    evenement retenu d'un warehouse a `prev_event_type IS NULL` (`LAG` sans
    ligne precedente) ; `NULL = 'STARTING'` vaut NULL (pas FALSE), donc
    `NOT (TRUE AND NULL)` vaut NULL et la ligne est EXCLUE par le WHERE (une
    condition NULL n'est jamais retenue) -- ce warehouse disparaissait
    entierement de la sortie (aucune ligne `daily_running`). L'egalite
    null-safe (`<=>`) traite `NULL <=> 'STARTING'` comme FALSE : la ligne est
    conservee.
    """
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert "AND prev_event_type <=> 'STARTING'" in query
    assert "AND prev_event_type = 'STARTING'" not in query


def test_utilization_daily_dangling_stopped_opens_implicit_midnight_session(
    fakes: SimpleNamespace,
) -> None:
    """Non-regression : un `STOPPED` sans aucun evenement precedent doit compter.

    Bug confirme en donnee reelle (`idle_pct` negatif sur des sessions
    tronquees a la frontiere de retention, cf. sub-spec T003) : un warehouse
    dont la session "on" etait deja en cours quand la lecture de
    `curated_dbx_compute_warehouse_events` a commence n'a, par construction,
    aucun `STARTING` retrouvable -- le premier evenement STARTING/STOPPED
    jamais capture est un `STOPPED` isole (`prev_event_type IS NULL`).
    Avant ce fix, `running_sessions` ne derivait de session QUE depuis un
    `STARTING` : ce `STOPPED` orphelin etait purement et simplement ignore,
    alors que `active_query_hours` (independant, base sur `query_history`)
    reflete l'activite reelle -> `idle_pct` negatif (`running_hours` sous-
    estime, voire absent). On sait avec certitude que le warehouse etait
    deja allume a minuit le jour de ce `STOPPED` (une session ouverte avant
    la fenetre lue l'est forcement restee jusque-la), donc une session
    implicite s'ouvre a minuit de ce jour plutot que d'etre perdue.
    """
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert "implicit_opening_sessions AS (" in query
    assert "CAST(to_date(event_time) AS TIMESTAMP) AS session_start" in query
    assert "event_time AS session_end" in query
    assert "FROM tagged_events" in query
    assert "event_type = 'STOPPED'" in query
    assert "AND prev_event_type IS NULL" in query
    assert "FROM implicit_opening_sessions" in query
    # La session implicite doit s'ajouter aux sessions STARTING -> STOPPED,
    # pas les remplacer.
    assert "UNION ALL" in query


def test_utilization_daily_running_hours_split_across_calendar_days(
    fakes: SimpleNamespace,
) -> None:
    """Non-regression : une session qui chevauche minuit doit etre decoupee.

    L'ancienne formule attribuait la totalite de la duree d'une session
    `STARTING -> STOPPED` au jour de son `STARTING`, meme quand la session
    durait ~22h a cheval sur 2 jours : le 2e jour recevait 0h de
    `running_hours` alors que le warehouse y tournait reellement, faussant
    `idle_pct` jusqu'a -22 537% (bug confirme en run reel T003, cf.
    sub-spec "Fix cible post-livraison"). La nouvelle formule decoupe
    chaque session par jour calendaire traverse via `LATERAL VIEW
    explode(sequence(...))`, en bornant chaque segment aux limites du jour
    (`GREATEST`/`LEAST`).
    """
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert "LATERAL VIEW explode(" in query
    assert "sequence(to_date(rs.session_start), to_date(rs.session_end))" in query
    assert "GREATEST(rs.session_start, CAST(d AS TIMESTAMP))" in query
    assert (
        "LEAST(rs.session_end, CAST(d AS TIMESTAMP) + INTERVAL 1 DAY)" in query
    )
    assert "FROM running_sessions_by_day" in query


def test_utilization_daily_lead_computed_on_starting_stopped_filtered_subsequence(
    fakes: SimpleNamespace,
) -> None:
    """Non-regression : `running_hours` doit utiliser `STARTING`, pas `RUNNING`.

    `STARTING` borne le debut REEL de l'allumage : un warehouse est allume (et
    facture, en classique) des sa mise en route, pas seulement une fois pret a
    servir -- une session `RUNNING -> STOPPED` amputerait chaque cycle de sa
    rampe de demarrage. ATTENTION : la justification historique de ce choix
    ("`RUNNING` n'est presque jamais journalise sur les warehouses serverless")
    est FAUSSE, mesuree a l'inverse le 2026-09-10 (`RUNNING` : 55 886
    evenements / 393 warehouses serverless, `STARTING` : 55 880 / 380) -- ne pas
    la ressusciter pour justifier ce test. Le `LEAD` doit etre calcule sur la
    sous-sequence filtree aux 2 seuls evenements STARTING/STOPPED
    (`running_stopped_events`), pas RUNNING/STOPPED.
    """
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert "WHERE event_type IN ('STARTING', 'STOPPED')" in query
    assert "FROM running_stopped_events" in query
    # Le LEAD ne doit PAS etre calcule directement sur `events_filtered` brut.
    assert "    FROM events_filtered\n    ),\n    running_sessions" not in query


def test_utilization_daily_active_query_hours_split_across_calendar_days(
    fakes: SimpleNamespace,
) -> None:
    """`active_query_hours`/`peak_concurrency` decoupent chaque requete par jour traverse.

    Une requete a cheval sur minuit est d'abord ventilee par jour calendaire
    traverse (`query_history_by_day`, meme principe que
    `running_sessions_by_day`), chaque segment etant borne aux limites du
    jour (`GREATEST`/`LEAST`) avant d'alimenter le balayage (sweep-line) :
    seule la fraction de duree ecoulee dans un jour donne contribue a
    `active_query_hours`/`peak_concurrency` de ce jour-la.
    """
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert "FROM query_history_filtered qhf" in query
    assert "sequence(to_date(qhf.start_time), to_date(qhf.end_time))" in query
    assert "GREATEST(qhf.start_time, CAST(d AS TIMESTAMP)) AS clipped_start" in query
    assert (
        "LEAST(qhf.end_time, CAST(d AS TIMESTAMP) + INTERVAL 1 DAY) AS clipped_end" in query
    )
    assert "FROM query_history_by_day" in query
    assert "clipped_start AS ts, 1 AS delta" in query
    assert "clipped_end AS ts, -1 AS delta" in query


def test_utilization_daily_computes_idle_pct_and_ratio(fakes: SimpleNamespace) -> None:
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert (
        "(e.running_hours - e.active_query_hours) / NULLIF(e.running_hours, 0) * 100"
        in query
    )
    assert "e.active_query_hours / NULLIF(e.running_hours, 0) AS active_to_running_ratio" in query


def test_utilization_daily_active_query_hours_uses_sweep_line_not_hour_buckets(
    fakes: SimpleNamespace,
) -> None:
    """Non-regression : `active_query_hours` doit etre l'union d'intervalles reels.

    L'ancienne formule (`COUNT(DISTINCT date_trunc('HOUR', start_time))`)
    compte des heures calendaires pleines des qu'une seule requete y passe,
    incompatible en unite avec `running_hours` (mesure fine, a la seconde) :
    produisait un `idle_pct` jusqu'a -22 537% sur les warehouses serverless a
    cycles courts (bug confirme en run reel T003, cf. sub-spec "Fix cible
    post-livraison"). La nouvelle formule reutilise le balayage (sweep-line)
    deja construit pour `peak_concurrency` (memes evenements +1/-1), somme les
    segments `[ts, next_ts)` ou `concurrency > 0`, convertis en heures.
    """
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert "COUNT(DISTINCT date_trunc('HOUR', start_time)) AS active_query_hours" not in query
    assert "WHEN concurrency > 0 AND next_ts IS NOT NULL" in query
    assert (
        "THEN (CAST(next_ts AS DOUBLE) - CAST(ts AS DOUBLE)) / 3600.0" in query
    )
    assert "AS active_query_hours" in query
    assert "FROM concurrency_running" in query


def test_utilization_daily_coalesces_null_end_time_to_avoid_corrupting_sweep_line(
    fakes: SimpleNamespace,
) -> None:
    """Non-regression : `end_time` NULL doit etre coalesce, jamais laisse tel quel.

    `curated_dbx_query_history` peut contenir des lignes `end_time IS NULL`
    de facon durable (requete encore RUNNING/QUEUED au moment de l'ingestion,
    ou requete longue dont le `start_time` est sorti du watermark incremental
    avant que sa completion ne soit re-ingeree, cf.
    `system_tables.specs.QUERY_HISTORY_SPEC`). Sans `COALESCE`, un `ts` NULL
    dans `concurrency_events` est trie avant tous les evenements reels du
    jour (NULLS FIRST), ce qui laisse un `+1` orphelin gonfler
    `active_query_hours` a tort -- bug qui reproduit meme en
    `--full-refresh` (vient de `curated_dbx_query_history`, pas de la
    fenetre de lecture de ce builder).
    """
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert "COALESCE(end_time, current_timestamp()) AS end_time" in query


def test_utilization_daily_excludes_stale_null_end_time_rows_instead_of_coalescing(
    fakes: SimpleNamespace,
) -> None:
    """Non-regression : une ligne `end_time` NULL trop ancienne est EXCLUE, pas coalescee.

    Verifie en donnee reelle : un warehouse peut accumuler des centaines de
    lignes `end_time` NULL orphelines (requetes en realite terminees depuis
    longtemps, dont la completion n'a jamais ete re-ingeree a cause du
    watermark `start_time` de `QUERY_HISTORY_SPEC`), la plus ancienne
    remontant a plusieurs semaines. Les coalescer toutes a
    `current_timestamp()` (comme le ferait un `COALESCE` sans garde-fou)
    gonflerait `active_query_hours` de semaines entieres et ferait EMPIRER
    `idle_pct` negatif au lieu de le corriger. Seules les lignes dont le
    `start_time` est recent (`WAREHOUSE_QUERY_STILL_RUNNING_MAX_HOURS`, 24h)
    sont donc coalescees ; les autres sont exclues du balayage.
    """
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert (
        "OR start_time >= current_timestamp() - INTERVAL 24 HOURS"
        in query
    )
    assert "end_time IS NOT NULL" in query


def test_utilization_daily_counts_scale_up_and_scale_down_events(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert "event_type IN ('SCALING_UP', 'SCALED_UP')" in query
    assert "event_type IN ('SCALED_DOWN')" in query


def test_utilization_daily_resolves_warehouse_name_at_last_known_state(
    fakes: SimpleNamespace,
) -> None:
    """`warehouse_name` = etat curated le plus recent du jour agrege (fin de journee).

    Meme regle que `warehouse_cost_daily` : la CTE `warehouses_as_of` joignait
    deja le curated pour `auto_stop_minutes`/`max_clusters`, le nom s'y ajoute
    sans jointure supplementaire. `LEFT JOIN` et non `INNER` : la jointure
    enrichit, elle ne filtre pas -- un warehouse absent du curated garde sa
    ligne avec `warehouse_name` NULL, aucune valeur de repli n'est fabriquee en
    gold (le repli sur l'id est une decision d'affichage).
    """
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert "LEFT JOIN it.sch.curated_dbx_compute_warehouses w" in query
    assert "AND w.change_time < r.period_start + INTERVAL 1 DAY" in query
    assert "ORDER BY w.change_time DESC" in query
    assert "            w.warehouse_name,\n" in query
    # Propage par `enriched` (a cote des autres attributs `wa.*`) puis expose
    # dans le SELECT final, ou les colonnes ne sont plus prefixees.
    assert "            wa.warehouse_name,\n" in query
    assert "        period_start,\n        warehouse_name,\n" in query


def test_utilization_daily_names_warehouse_created_within_the_aggregated_day(
    fakes: SimpleNamespace,
) -> None:
    """Un warehouse dont l'unique `change_time` tombe DANS le jour J est nomme sur J.

    `period_start` est une DATE : `change_time <= period_start` la caste a
    minuit et n'admet donc aucune version d'un warehouse cree en cours de
    journee, qui sortait sans nom -- et, ce nom NULL etant repris par
    `latest_attrs`, se propageait aux 4 fenetres de `utilization_rolling`
    (SC-001 mesure a 90,3 % en w90 avant correction). Ne pas "resserrer" ce
    predicat par mimetisme sur l'ancienne version.
    """
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert "w.change_time < r.period_start + INTERVAL 1 DAY" in query
    assert "w.change_time <= r.period_start" not in query
    # Le tri du QUALIFY est inchange : c'est lui qui retient la version la plus
    # recente de la journee, donc l'etat de FIN de journee -- `auto_stop_minutes`
    # et `max_clusters` suivent la meme borne, par construction de la CTE.
    assert "ORDER BY w.change_time DESC" in query


def test_utilization_daily_has_auto_stop_and_utilization_status_branches(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert "ELSE auto_stop_minutes > 0 END AS has_auto_stop" in query
    assert "WHEN idle_pct > 60.0 THEN 'OVER'" in query
    assert "WHEN peak_concurrency >= max_clusters * 0.8 THEN 'UNDER'" in query
    assert "ELSE 'OPTIMAL'" in query


def test_utilization_daily_estimated_savings_only_when_over(fakes: SimpleNamespace) -> None:
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert "WHEN idle_pct > 60.0 THEN cost_usd * idle_pct / 100" in query
    assert "ELSE NULL\n        END AS estimated_savings_usd" in query


# --- Discriminant serverless (`is_serverless`) et neutralisation ----------------
# Le calcul d'efficience (idle, rightsizing, economies) n'a de sens QUE sur du
# compute classique / pro : en serverless la facturation suit le compute des
# requetes, pas le temps allume. Ces tests verrouillent les deux moities de la
# regle -- ce qui doit etre neutralise, et ce qui doit RESTER servi.

# Champs de diagnostic economique, sans objet en serverless.
_NEUTRALIZED_ON_SERVERLESS = (
    "idle_pct",
    "active_to_running_ratio",
    "auto_stop_minutes",
    "has_auto_stop",
    "utilization_status",
    "rightsizing_reco",
    "estimated_savings_usd",
)
# Metriques d'activite brutes, justes dans les deux mondes : les neutraliser
# viderait la page serverless de toute mesure.
_PRESERVED_ON_SERVERLESS = (
    "running_hours",
    "active_query_hours",
    "peak_concurrency",
    "scale_up_events",
    "scale_down_events",
    "avg_cluster_count",
    "max_cluster_count",
)


def _final_select_without_comments(query: str) -> str:
    """Dernier `SELECT` de la requete, commentaires SQL retires.

    Les assertions ci-dessous inspectent l'EXPRESSION servie pour chaque colonne
    de sortie : un commentaire `--` citant `is_serverless` ne doit pas pouvoir
    faire passer un champ pour neutralise.
    """
    final_select = query[query.rindex("    SELECT\n") :]
    return "\n".join(
        line for line in final_select.splitlines() if not line.lstrip().startswith("--")
    )


def test_utilization_daily_derives_is_serverless_from_billing_then_warehouse_type(
    fakes: SimpleNamespace,
) -> None:
    """`is_serverless` : facturation du jour, a defaut type declare, a defaut faux.

    La forme de compute est resolue au grain JOUR et non par warehouse : 68
    warehouses changent de forme au fil de l'historique (mesure dev 2026-09-10),
    et 63 jours-warehouse melangent les deux formes le meme jour -- replies par
    `MAX` (serverless l'emporte), pour ne jamais afficher une economie non
    encaissable. La cascade est indispensable a la garantie "jamais NULL" : la
    facturation ne couvre que 16 218 des 16 781 jours-warehouse (96,6 %), le type
    declare du warehouse resout les 563 restants.
    """
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert "billing_serverless_by_day AS (" in query
    assert "FROM it.sch.curated_dbx_billing_usage" in query
    assert "usage_metadata.warehouse_id AS warehouse_id" in query
    assert "WHERE usage_metadata.warehouse_id IS NOT NULL" in query
    assert (
        "MAX(CASE WHEN product_features.is_serverless THEN 1 ELSE 0 END) = 1 AS is_serverless"
        in query
    )
    # Cascade : facturation -> type declare -> faux, jamais NULL.
    assert "COALESCE(\n                bs.is_serverless,\n" in query
    assert "wa.warehouse_type = 'SERVERLESS',\n                false\n" in query
    assert "            ) AS is_serverless" in query
    # Le type declare doit etre remonte par `warehouses_as_of` (aucune jointure
    # supplementaire sur le curated).
    assert "            w.warehouse_type\n" in query
    assert "LEFT JOIN billing_serverless_by_day bs" in query
    # Colonne exposee en sortie : c'est elle qui rend lisibles les NULL.
    assert "        warehouse_name,\n        is_serverless,\n" in query


def test_utilization_daily_neutralizes_efficiency_fields_on_serverless(
    fakes: SimpleNamespace,
) -> None:
    """Les 7 champs de diagnostic economique sont a NULL quand `is_serverless`.

    Sans cette garde, la table affichait (mesure dev, 15 j, AWS) un `idle_pct`
    median de 96,3 %, 95,6 % des jours-warehouse au-dela du seuil, 353 des 398
    warehouses serverless marques `OVER` et ~49 100 $ d'`estimated_savings_usd`
    IRREALISABLES -- un chiffre qu'aucune action ne peut encaisser.
    """
    query, _ = _utilization_query(fakes, lower_bound=None)
    # Seul le SELECT final compte : `with_metrics` calcule volontairement les
    # ratios bruts (sans garde) pour les lignes classiques.
    select_final = _final_select_without_comments(query)
    for field in _NEUTRALIZED_ON_SERVERLESS:
        alias = f" AS {field},"
        assert alias in select_final, field
        expression = select_final[: select_final.index(alias)].rsplit(",\n", 1)[-1]
        assert "WHEN is_serverless THEN NULL" in expression, field


def test_utilization_daily_keeps_activity_metrics_on_serverless(
    fakes: SimpleNamespace,
) -> None:
    """Les metriques d'activite restent servies en serverless (elles sont justes).

    Non-regression de la neutralisation elle-meme : elle doit rester chirurgicale.
    `running_hours`, `active_query_hours`, `peak_concurrency` et les compteurs de
    scaling mesurent ce qui s'est passe, pas ce qu'il faudrait redimensionner --
    sans eux la page serverless n'aurait plus aucune mesure a afficher.
    """
    query, _ = _utilization_query(fakes, lower_bound=None)
    select_final = _final_select_without_comments(query)
    for field in _PRESERVED_ON_SERVERLESS:
        assert f"        {field},\n" in select_final, field
        assert f"THEN NULL ELSE {field} END" not in select_final, field


# --- Type de compute declare (`warehouse_type`) ---------------------------------
# `is_serverless` est un booleen : il ne distingue pas PRO de CLASSIC alors que
# les deux sont peuples (mesure account-wide 2026-09-11 : 359 warehouses PRO, 162
# CLASSIC cote curated dev). `warehouse_type` expose le type declare, mais reste
# SUBORDONNE au booleen -- c'est cette subordination que verrouillent les tests
# ci-dessous, pas la simple presence de la colonne.

# Expression exacte servie en sortie. L'ORDRE des branches est la regle metier :
# `is_serverless` d'abord (il est lu sur la facturation, forme reellement
# facturee), le dementi inverse ensuite, le type declare seulement en dernier.
_DAILY_WAREHOUSE_TYPE_EXPRESSION = (
    "        CASE\n"
    "            WHEN is_serverless THEN 'SERVERLESS'\n"
    "            WHEN declared_warehouse_type = 'SERVERLESS' THEN NULL\n"
    "            ELSE declared_warehouse_type\n"
    "        END AS warehouse_type,\n"
)


def test_utilization_daily_exposes_declared_warehouse_type(
    fakes: SimpleNamespace,
) -> None:
    """`warehouse_type` sort du dernier etat connu du jour, sans jointure de plus.

    Le type declare est deja remonte par `warehouses_as_of` (il servait de repli a
    `is_serverless`) : l'exposer ne doit couter AUCUNE jointure supplementaire sur
    `curated_dbx_compute_warehouses`, donc aucun scan de plus. Il est lu sous un
    alias distinct (`declared_warehouse_type`) parce que la valeur declaree et la
    valeur servie ne sont pas la meme chose (cf. test suivant).
    """
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert "            w.warehouse_type\n" in query
    # Une SEULE jointure sur le referentiel, celle de `warehouses_as_of`.
    assert query.count("it.sch.curated_dbx_compute_warehouses") == 1
    assert "wa.warehouse_type AS declared_warehouse_type," in query
    select_final = _final_select_without_comments(query)
    assert " AS warehouse_type,\n" in select_final


def test_utilization_daily_warehouse_type_never_contradicts_is_serverless(
    fakes: SimpleNamespace,
) -> None:
    """Coherence obligatoire : le type declare ne dement JAMAIS `is_serverless`.

    Le backend supprime les economies non encaissables sur le seul
    `is_serverless` : une ligne affichant « PRO » alors qu'`is_serverless` est vrai
    casserait cette suppression. Le cas n'est pas theorique -- mesure en dev le
    2026-09-11 sur les 16 820 jours-warehouse deja ecrits : 3 sont declares PRO
    tout en etant FACTURES en serverless (ils doivent afficher `SERVERLESS`), et 1
    est declare SERVERLESS alors que la facturation du jour dit le contraire (il
    doit afficher NULL : on ne sait pas lequel de PRO/CLASSIC a ete facture, et
    l'inventer serait faux). Ce test echoue si quelqu'un reordonne les branches ou
    sert le type declare brut -- les deux regressions qui reintroduiraient la
    contradiction.
    """
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert _DAILY_WAREHOUSE_TYPE_EXPRESSION in query
    select_final = _final_select_without_comments(query)
    # Jamais servi brut : la garde de coherence n'est pas contournable par un
    # simple passe-plat.
    assert "        declared_warehouse_type AS warehouse_type" not in select_final
    assert "        wa.warehouse_type AS warehouse_type" not in select_final
    # `is_serverless` reste expose a cote : c'est le couple qui est lisible, pas
    # le type seul (cf. la neutralisation des champs d'efficience).
    assert "        is_serverless,\n" in select_final


def test_utilization_daily_warehouse_type_is_not_clamped_to_three_values(
    fakes: SimpleNamespace,
) -> None:
    """Un 4e type declare passe tel quel, il ne disparait pas dans un NULL.

    Le domaine de `curated_dbx_compute_warehouses.warehouse_type` est OUVERT :
    `REAL_TIME` existe deja en dev (1 warehouse au 2026-09-11, sans session dans
    `warehouse_events` donc sans ligne gold aujourd'hui). La derniere branche est
    un `ELSE` sur le type declare et non une liste blanche PRO/CLASSIC : un SKU
    inconnu doit s'afficher, pas etre efface -- et le consommateur (API/IHM) doit
    donc afficher la chaine recue plutot que la valider contre un enum ferme.
    """
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert "ELSE declared_warehouse_type\n" in query
    for clamped in ("'PRO'", "'CLASSIC'", "'REAL_TIME'"):
        assert clamped not in query, clamped


def test_utilization_daily_peak_concurrency_uses_sweep_line_not_self_join(
    fakes: SimpleNamespace,
) -> None:
    """Non-regression : `peak_concurrency` doit etre un balayage (sweep-line).

    Un self-join `q1 JOIN q2 ON chevauchement d'intervalle` est O(n^2) par
    groupe et a timeout en run reel sur dev_local (full-refresh sur 3 ans
    d'historique `query_history`, cf. sub-spec T003 "Fix cible
    post-livraison"). Remplace par : +1/-1 par requete, somme cumulee
    (fenetre triee par instant), MAX par jour.
    """
    query, _ = _utilization_query(fakes, lower_bound=None)
    assert "1 AS delta" in query
    assert "-1 AS delta" in query
    assert "SUM(delta) OVER (" in query
    assert "MAX(concurrency) AS peak_concurrency" in query
    # Aucun self-join par chevauchement d'intervalle ne doit subsister.
    assert "JOIN query_history_filtered q2" not in query
