"""Helpers SQL partages par les builders `gold_dbx_usage` (fenetre + attribution cout).

Purs helpers de formatage/calcul (aucune dependance Spark), symetrique a
`pipelines.gold_dbx_compute.sql_helpers` (module duplique plutot que partage
entre domaines gold, cf. convention actee dans ce dernier).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date


def sql_string_list(values: tuple[str, ...]) -> str:
    """Formate un tuple de chaines en liste SQL litterale : `'a', 'b'`."""
    return ", ".join(f"'{value}'" for value in values)


def lower_bound_predicate(column: str, lower_bound: date | None) -> str:
    """Predicat `AND col >= DATE '...'` (chaine vide si pas de fenetre).

    `None` => full (tout l'historique curated disponible, 1er run) ; une date
    borne la lecture curated a la fenetre incrementale (runs suivants).
    """
    if lower_bound is None:
        return ""
    return f"AND {column} >= DATE '{lower_bound.isoformat()}'"


# Methode d'attribution du cout/duree d'une requete multi-data-product a chacune
# des tables sources qu'elle lit. `WEIGHTED_BYTES` (prorata de `read_bytes` par
# table source) n'est pas calculable : aucune source ne porte de volume par table
# source -- le lineage n'en a pas, `query.history` l'a au niveau requete. Seul
# `EQUAL_PARTS_FALLBACK` est donc applique. La constante et le flag par ligne
# subsistent pour tracer la methode et permettre la bascule si une telle source
# apparait, sans casser le contrat de colonne.
COST_ATTRIBUTION_WEIGHTED_BYTES = "weighted_bytes"
COST_ATTRIBUTION_EQUAL_PARTS_FALLBACK = "equal_parts_fallback"


# SEAU de facturation dont le prorata de duree tire le cout d'une requete. Axe
# distinct de `COST_ATTRIBUTION_*`, qui decrit le partage d'une requete entre ses
# tables sources : une ligne chiffree porte les deux.
#
# UNE VALEUR PAR SEAU, jamais un libelle commun a plusieurs. Ces valeurs entrent dans
# la CLE DE JOINTURE vers la facturation : c'est le seul discriminant entre des
# identifiants qui viennent d'espaces sans rapport (5,3 millions de clusters factures
# contre 1 828 warehouses, aucune collision observee mais aucune garantie). Deux seaux
# partageant une valeur perdraient cette protection l'un envers l'autre.
#
# Ces bases ne mesurent pas la meme grandeur et ne sont pas additionnables sans le
# dire. Un SQL warehouse n'execute que des requetes : le prorata de duree lui est
# fidele. Un cluster et un job serverless executent aussi du code non-SQL, que le
# prorata sur les seuls statements ignore -- l'integralite de leur facture atterrit
# donc sur leurs requetes SQL. A lire comme « ce que coute la charge qui a touche cette
# table », pas comme le cout de ces requetes.
#
# `COST_BASIS_CLUSTER_PRORATA` ne produit aucune ligne tant que la source ne comble pas
# son bout du pont : `billing_usage.usage_metadata.cluster_id` est bien rempli
# (9 356 230 lignes) mais `query_history.compute.cluster_id` est vide sur la totalite
# des statements -- la table nomme le TYPE du compute (`CLASSIC_COMPUTE`), pas la
# ressource. Le seau est conserve pour que le cout des clusters arrive sans
# redeveloppement si `query.history` se met a publier l'identifiant.
COST_BASIS_WAREHOUSE_PRORATA = "warehouse_prorata"
COST_BASIS_CLUSTER_PRORATA = "cluster_prorata"
COST_BASIS_SERVERLESS_JOB_PRORATA = "serverless_job_prorata"

# Un groupe du grain gold peut melanger des acces chiffres sur plusieurs seaux (un
# warehouse et un job serverless ayant lu la meme table le meme jour). Un `MAX()` en
# designerait un seul, au hasard de l'ordre alphabetique ; ce libelle dit que le
# total agrege additionne des bases differentes.
COST_BASIS_MIXED = "mixed"


# SIGNAL dont `freshness_lag_hours` tire son anciennete. Deux signaux, de valeur de
# preuve INEGALE, et c'est tout l'objet de cette colonne que de dire lequel a servi.
#
# `LINEAGE_WRITE` est la seule preuve d'ecriture du modele : le lineage donne la table
# ecrite, `curated_dbx_query_history.written_rows` donne le nombre de lignes. Bornee par
# la retention du lineage, et muette sur les objets sans contenu propre (une vue n'est
# jamais ecrite).
#
# `TABLE_ALTERED` est le repli qui donne une fraicheur au reste du catalogue. Il apporte
# de la COUVERTURE et non de la precision, et il se trompe dans LES DEUX SENS -- ne jamais
# le lire comme une preuve d'ecriture :
#   trop recent : la doc officielle definit `last_altered` comme l'horodatage auquel la
#     DEFINITION de la relation a ete modifiee « in any way ». Un `SET TBLPROPERTIES` le
#     fait donc bouger sans qu'une seule ligne soit ecrite -> anciennete SOUS-estimee.
#   trop ancien : rien dans cette definition ne promet qu'une ecriture de donnees le fasse
#     bouger, et c'est verifie -- sur les tables dont le lineage atteste une ecriture,
#     `last_altered` est ANTERIEUR a celle-ci dans 44 % des cas, avec un retard median de
#     448 h sur les tables MANAGED -> anciennete SUR-estimee.
# `is_stale_but_consumed` calcule sur ce repli est donc une heuristique et non un constat,
# et c'est `freshness_basis` qui permet au consommateur de le savoir.
FRESHNESS_BASIS_LINEAGE_WRITE = "lineage_write"
FRESHNESS_BASIS_TABLE_ALTERED = "table_altered"


# `entity_type` d'une requete SQL tracee dans `curated_dbx_access_table_lineage`.
# Domaine observe de la colonne : `DBSQL_QUERY`, `JOB`, `NOTEBOOK`, `PIPELINE`,
# `DASHBOARD_V3` et NULL -- ce dernier sur une part importante des lignes, d'ou
# l'interdiction de la filtrer avec un `=`/`!=` simple (cf.
# `non_null_entity_type_predicate`, NULL-safe).
LINEAGE_ENTITY_TYPE_QUERY = "DBSQL_QUERY"

# Valeurs de `source_type`/`target_type` de `system.access.table_lineage` qui
# designent un objet Unity Catalog PORTANT UN NOM QUALIFIE en trois parties.
# Le domaine documente complet est `TABLE`, `PATH`, `VIEW`, `MATERIALIZED_VIEW`,
# `METRIC_VIEW`, `STREAMING_TABLE` : seul `PATH` est exclu ici (un chemin de
# stockage n'a pas de `catalog.schema.table`, donc rien a rapprocher de
# `curated_dbx_uc_tables` ni a agreger au grain de cette table gold).
LINEAGE_NAMED_OBJECT_TYPES = (
    "TABLE",
    "VIEW",
    "MATERIALIZED_VIEW",
    "METRIC_VIEW",
    "STREAMING_TABLE",
)

# Sous-ensemble de `LINEAGE_NAMED_OBJECT_TYPES` dont un `target_type` peut attester une
# ECRITURE : les objets qui portent leur propre contenu. `VIEW` et `METRIC_VIEW` en sont
# exclus -- une vue n'a pas de donnees, sa fraicheur est celle de ses tables
# sous-jacentes, et elle apparait en cible des qu'une lecture la traverse (arete
# « table source -> vue »). Les y inclure daterait une ecriture depuis une lecture.
LINEAGE_WRITTEN_OBJECT_TYPES = (
    "TABLE",
    "MATERIALIZED_VIEW",
    "STREAMING_TABLE",
)

# Libelle explicite pour un `consumer_type` qu'aucune branche ne sait qualifier
# (`entity_type` NULL en amont, par exemple). `consumer_type` est une colonne
# categorique : elle porte toujours une valeur, jamais NULL. Etiqueter ces cas
# `SERVICE_PRINCIPAL` par defaut inventerait un signal.
CONSUMER_TYPE_UNKNOWN = "UNKNOWN"

# Etats de resolution d'un objet accede face au registre `curated_dbx_uc_tables`.
#
# Le booleen `unknown_data_product` confond deux situations opposees pour un produit
# de gouvernance : « cet objet n'appartient a aucun data product » et « le pipeline
# n'a pas le DROIT de le voir ». Le registre vient de
# `system.information_schema.tables`, filtree par privilege OBJET PAR OBJET et non
# catalogue par catalogue : voir un catalogue ne dit rien de ses objets, donc la
# visibilite du catalogue ne peut pas servir de discriminant.
#
# Le discriminant est une PREUVE D'EXISTENCE : un acces reussi atteste que l'objet
# existe, Databricks ne journalisant pas la lecture reussie d'une table inexistante.
# Toute ligne de lineage en est une par construction ; cote audit `getTable`, seul un
# `status_code = '200'` en est une.
CATALOG_RESOLUTION_RESOLVED = "RESOLVED"
CATALOG_RESOLUTION_NOT_VISIBLE = "NOT_VISIBLE_TO_PIPELINE"
CATALOG_RESOLUTION_NEVER_RESOLVED = "NEVER_RESOLVED"

# Etat de cycle de vie d'une table au catalogue, derive par CORROBORATION de deux
# signaux dans `table_catalog` : la presence dans `curated_dbx_uc_tables` (miroir
# purge a chaque full load, donc une absence y est un signal reel et non un reliquat
# de snapshot) et la derniere operation d'audit.
#
# TROIS etats et non deux, parce que l'absence du referentiel NE PROUVE RIEN a elle
# seule : elle vient majoritairement d'un privilege manquant sur le principal
# d'ingestion, meme cause que `CATALOG_RESOLUTION_NOT_VISIBLE`. `UNKNOWN` nomme ce
# « absente sans preuve de suppression » et vaut `is_deleted = false` -- marquer ces
# tables supprimees les retirerait des previsions et des recommandations alors
# qu'elles sont vivantes.
#
# La PRESENCE au referentiel prime sur tout evenement passe : une table recreee
# redevient `ACTIVE` sans code de reversion dedie, meme si son `deleteTable` est
# encore dans la fenetre d'audit.
LIFECYCLE_STATE_ACTIVE = "ACTIVE"
LIFECYCLE_STATE_DELETED = "DELETED"
LIFECYCLE_STATE_UNKNOWN = "UNKNOWN"

# Duree de vie SOUS laquelle une table n'est PAS declaree supprimee : elle n'a jamais
# ete un objet gouverne, seulement un intermediaire d'execution -- une table de staging
# creee, lue et droppee par le meme run de job. Lui fabriquer une ligne de catalogue est
# une erreur de definition, pas un probleme de volume.
#
# En SECONDES : la duree de vie se mesure par difference de deux `unix_timestamp` sur
# les evenements d'audit `createTable` et `deleteTable` (cf. `ephemeral_tables`).
#
# Le seuil separe deux populations, il ne dose pas un compromis : un objet gouverne
# (declare, tague, consomme, sauvegarde) ne vit pas moins d'une heure, un intermediaire
# d'execution ne vit pas plus. Retenu apres mesure de la distribution des durees de vie
# sur la warehouse de dev, qui n'est pas un continuum mais deux paquets separes.
#
# Il gouverne les DEUX sens du filtre, qui doivent rester complementaires (cf.
# `LIVED_LONG_ENOUGH_PREDICATE` et `WAS_EPHEMERAL_PREDICATE` dans `ephemeral_tables`) :
# ne pas ecrire de ligne pour une ephemere, et retirer apres coup celle qu'un run avait
# vue vivante. Le changer deplace les deux frontieres a la fois, ce qui est voulu.
EPHEMERAL_TABLE_MAX_LIFETIME_SECONDS = 3600

# Litteral de `table_lineage.created_by` pour une action declenchee par la
# plateforme sans identite rattachable. A traiter comme une absence d'identite,
# comme le litteral `'unknown'` de `access.audit` : sinon l'absence de `@` le fait
# etiqueter `SERVICE_PRINCIPAL`.
LINEAGE_SYSTEM_IDENTITY = "System-User"

# Sentinelles textuelles signalant une identite ABSENTE (et non un principal
# anonyme) dans les sources de lineage/audit. Le SQL NULL n'est pas le seul
# encodage de l'absence : les deux sources utilisent aussi des litteraux.
CONSUMER_IDENTITY_ABSENT_LITERALS = ("unknown", LINEAGE_SYSTEM_IDENTITY)


def consumer_type_from_identity(identity: str) -> str:
    """Qualifie un `consumer_type` a partir d'une expression d'identite SQL.

    Regle unique et NULL-safe, partagee par les branches qui derivent le type
    depuis une IDENTITE plutot que depuis un `entity_type` de lineage.

    `identity` peut etre une expression composee (un `COALESCE`, par exemple) :
    elle est alors reproduite plusieurs fois dans le `CASE`, sans effet de bord
    puisque aucune fonction non deterministe n'est en jeu.

    Limite connue : `created_by` peut porter un NOM DE GROUPE, indiscernable d'un
    identifiant de principal de service sans source d'identites externe. Un groupe
    ressort donc `SERVICE_PRINCIPAL`.
    """
    absent = ", ".join(f"'{literal}'" for literal in CONSUMER_IDENTITY_ABSENT_LITERALS)
    return (
        f"CASE "
        f"WHEN {identity} IS NULL THEN '{CONSUMER_TYPE_UNKNOWN}' "
        f"WHEN {identity} IN ({absent}) THEN '{CONSUMER_TYPE_UNKNOWN}' "
        f"WHEN {identity} LIKE '%@%' THEN 'USER' "
        f"ELSE 'SERVICE_PRINCIPAL' END"
    )


def non_null_entity_type_predicate(column: str, excluded_value: str) -> str:
    """Predicat NULL-safe `col <> excluded_value`.

    `col != 'X'` rend NULL, donc ecarte la ligne, quand `col` est NULL : deux
    branches censees etre l'exact complement l'une de l'autre (`= 'X'` / `!= 'X'`)
    perdent alors toute ligne a `col` NULL, qu'aucune des deux ne reprend.
    `IS DISTINCT FROM` traite NULL comme une valeur a part entiere, ce qui rend la
    partition exhaustive par construction.
    """
    return f"{column} IS DISTINCT FROM '{excluded_value}'"


def encode_consumer_type_priority(column: str) -> str:
    """Encode `consumer_type` avec un prefixe de priorite pour un `MAX()` deterministe.

    Un `MAX(consumer_type)` brut sur un `UNION ALL` de vocabulaires distincts
    (`USER`/`SERVICE_PRINCIPAL` d'un cote, `JOB`/`NOTEBOOK`/... de l'autre) fait
    gagner la valeur la plus grande ALPHABETIQUEMENT, pas la plus pertinente.
    Priorite retenue : une identite nominative (`USER`) prime sur un principal de
    service, qui prime sur un type d'entite brut du lineage. Le prefixe numerique
    tenant sur un chiffre, il trie lexicalement dans le bon ordre ;
    `decode_consumer_type_priority` le retire apres le `MAX()`.

    Suppose `column` non-NULL : toute branche productrice doit emettre
    `CONSUMER_TYPE_UNKNOWN` plutot qu'un NULL.
    """
    return (
        f"CONCAT(CASE {column} "
        f"WHEN 'USER' THEN '3_' "
        f"WHEN 'SERVICE_PRINCIPAL' THEN '2_' "
        f"ELSE '1_' END, {column})"
    )


def decode_consumer_type_priority(column: str) -> str:
    """Retire le prefixe `N_` ajoute par `encode_consumer_type_priority`."""
    return f"SUBSTRING({column}, 3)"


def split_full_name(column: str) -> tuple[str, str, str]:
    """Genere les 3 expressions SQL (`catalog`, `schema`, `table_name`) d'un nom qualifie.

    Reserve aux sources qui ne portent QUE la chaine concatenee -- en pratique
    `request_params` de `system.access.audit`, ou le nom qualifie arrive dans une
    seule cle de map (ex. `COALESCE(request_params['full_name_arg'],
    request_params['name_arg'])`). `system.access.table_lineage`, lui, publie
    `source_table_catalog` / `source_table_schema` / `source_table_name` (et leurs
    equivalents `target_*`) en colonnes natives : les builders de lineage les
    lisent directement plutot que de reconstituer par parsing ce que la source
    donne deja decompose.

    `get(split(...), i)` et non `split(...)[i]` : l'indexation par crochet leve
    `INVALID_ARRAY_INDEX` en mode ANSI sur une valeur qui n'a pas 3 parties, donc
    fait echouer tout le run au lieu de produire un NULL sur la seule ligne
    concernee. `get` renvoie NULL hors bornes.

    Limite qui subsiste : un identifiant quote contenant un `.` litteral serait mal
    decoupe. Aucun cas observe a ce jour.
    """
    parts = f"split({column}, '\\\\.')"
    return f"get({parts}, 0)", f"get({parts}, 1)", f"get({parts}, 2)"


def equal_parts_share(total: float, n_parts: int) -> float:
    """Part egale de `total` attribuee a une des `n_parts` tables d'une requete.

    Utilise par le controle de reconciliation des tests : `SUM(part) == total` pour
    toute requete multi-data-product. `n_parts <= 0` (aucune table source resolue)
    renvoie `0.0` plutot que de diviser par zero.
    """
    if n_parts <= 0:
        return 0.0
    return total / n_parts
