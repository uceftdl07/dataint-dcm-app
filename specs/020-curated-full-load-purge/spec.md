# technique : Purge générique des tables curated full-load

**Feature Branch**: `020-curated-full-load-purge` — branches filles `{domain}/020-{slug}`
**Work Type**: technique
**Priority**: P2
**Created**: 2026-09-02

**Input**: Une partie des tables curated est alimentée depuis des sources qui sont des photos de l'état courant, et non des logs d'événements : la source ne contient que ce qui existe au moment de la lecture, sans trace de suppression. L'écriture curated se faisant en upsert seul, une entrée retirée de la source y reste indéfiniment. Le curated dérive donc silencieusement de la source qu'il reflète, et l'écart ne fait que croître. Exemple le plus visible : `curated_dbx_uc_tables` et `curated_dbx_uc_table_tags` (← `system.information_schema.*`), où une table droppée ou un tag retiré survit à sa suppression — et où `gold_dbx_usage_table_governance` compte donc des objets inexistants dans `is_orphan`/`is_unused`. Le même mécanisme touche les autres référentiels full load du socle (`curated_dbx_compute_node_types`, `curated_dbx_billing_list_prices`), sans impact métier constaté à ce stade. Il faut un mécanisme de purge générique, activable table par table selon le besoin réel, et piloté indépendamment de l'ingestion : à sa propre fréquence, et sur son propre chemin d'exécution pour qu'une lecture source partielle ou en échec ne puisse jamais déclencher de suppression.

## Clarifications

### Session 2026-09-02

- Q: Quelle fréquence par défaut pour le job de purge (indépendant de l'ingestion) ? → A: Hebdomadaire
- Q: Mécanisme de traçabilité des runs de purge (réel ou dry-run) ? → A: Table d'audit Delta dédiée (en plus du log structuré structlog déjà obligatoire P10)
- Q: Nature du seuil du garde-fou volumétrique (au-delà duquel la purge s'arrête sans supprimer) ? → A: Les deux (absolu + pourcentage), le plus restrictif s'applique
- Q: Le job de purge doit-il être ordonnancé par rapport au job d'ingestion, ou totalement découplé ? → A: Espacement de planning (cron décalé après l'heure habituelle de fin d'ingestion), sans dépendance technique entre les deux jobs
- Q: Quelles tables sont activées pour la purge dès la livraison de ce ticket ? → A: Les 4 tables full-load du socle (`curated_dbx_uc_tables`, `curated_dbx_uc_table_tags`, `curated_dbx_compute_node_types`, `curated_dbx_billing_list_prices`)

## Domain Scope

Depuis `intake.json` — « In scope » = lecture autorisée, « Ticket » = reçoit une Story.

| Domaine | In scope | Ticket Story | Packages |
|---------|----------|--------------|----------|
| Frontend | ❌ | ❌ | — |
| Backend | ❌ | ❌ | — |
| DataEng | ✅ | ✅ | packages/dcm-databricks-pipeline |
| DevOps | ❌ | ❌ | — |
| QA | ❌ | ❌ | — |

## Ticket Plan

| Stories Jira | 1 |
|---|---|
| Mode | single_domain |
| Domaines avec ticket | dataeng |

## Contexte

Le socle d'ingestion `pipelines/system_tables` traite toutes les tables source de la même façon : lecture (native ou cross-tenant Azure), puis `MERGE INTO` idempotent (`pipelines/common/writers.py::build_merge_sql`) — uniquement des `UPDATE`/`INSERT`, jamais de `DELETE`. Pour les tables déclarées en full load dans `IngestionSpec` (`watermark_column=None` : `curated_dbx_uc_tables`, `curated_dbx_uc_table_tags`, `curated_dbx_compute_node_types`, `curated_dbx_billing_list_prices`), la source lue à chaque run est un **snapshot complet de l'état courant**, sans mécanisme de suppression en aval : une ligne absente de la lecture du jour reste en curated pour toujours. L'écart curated/source ne peut que croître avec le temps, et se propage silencieusement en gold (ex. `gold_dbx_usage_table_governance` qui compte des objets Unity Catalog déjà droppés dans ses métriques `is_orphan`/`is_unused`).

L'objectif est d'ajouter un mécanisme de purge **générique et opt-in par table**, distinct du socle d'ingestion existant, **activé dès ce ticket sur les 4 tables full-load du socle** (`curated_dbx_uc_tables`, `curated_dbx_uc_table_tags`, `curated_dbx_compute_node_types`, `curated_dbx_billing_list_prices`) :

- Détection des lignes curated absentes de la dernière lecture source complète (par clé de merge, par cloud), puis suppression.
- Activation explicite table par table (registre déclaratif, à l'image de `IngestionSpec`) — **jamais** appliquée par défaut à une table incrémentale (watermarkée), où elle supprimerait à tort l'historique hors fenêtre de lecture.
- Chemin d'exécution et fréquence **indépendants** de l'ingestion : un job/tâche séparé, planifié **hebdomadairement**, avec un cron **décalé après l'heure habituelle de fin du job d'ingestion** (espacement de planning, aucune dépendance technique entre les deux jobs), pour qu'une lecture source partielle ou en échec côté ingestion ne puisse jamais déclencher une suppression en curated.
- Toute suppression plafonnée (garde-fou volumétrique), tracée dans une table d'audit Delta dédiée (en plus du log structuré structlog déjà obligatoire) et vérifiable en dry-run avant exécution réelle.

Approche retenue : nouveau module `pipelines/common` (registre de purge + logique de suppression `DELETE`/`MERGE WHEN NOT MATCHED BY SOURCE`), déclenché par un job Databricks Asset Bundle dédié (nouveau `resources/job_dcm_*_purge.yml` ou équivalent), lisant le même snapshot source que l'ingestion mais sans jamais écrire dans le même run/tâche que celle-ci.

## Dependency Analysis

| Besoin | Domaine requis | Preuve (fichier) | Résolution |
|--------|----------------|------------------|------------|
| Registre générique des tables full-load | dataeng | `pipelines/system_tables/specs.py` — `IngestionSpec.watermark_column=None` (billing_list_prices, compute_node_types, uc_tables, uc_table_tags) | backend_ready (dataeng seul) |
| Écriture curated = upsert seul, aucun DELETE | dataeng | `pipelines/common/writers.py::build_merge_sql` — MERGE INTO (UPDATE+INSERT) sans DELETE ; `pipelines/gold_dbx_compute/recommendations.py` commente explicitement l'absence de purge | backend_ready (dataeng seul) |
| Mécanisme de purge/soft-delete existant | dataeng | aucune occurrence `DELETE FROM`/`purge` dans `pipelines/` (hors commentaire) | backend_ready (dataeng seul) |
| Job Databricks séparé de l'ingestion | dataeng | `resources/` ne contient que des jobs d'ingestion (`job_dcm_system_tables.yml` et similaires), aucun job de maintenance/purge | backend_ready (dataeng seul) |

## Prerequisites

- **Small branches / small PRs** : découper pour que la branche fille DataEng touche un ensemble restreint de fichiers (registre de purge + job dédié), sans toucher au socle d'ingestion existant.
- Intake + domain scope confirmés (`intake.json` / `domain-scope.json`).
- Aucune dépendance bloquante identifiée en Dependency Analysis (dataeng seul, socle déjà en place).
- `[NEEDS CLARIFICATION]` levés (recommandé avant l'étape `plan` de spec-kit).

## Acceptance Criteria

1. **Given** une table curated activée pour la purge, **When** le job de purge s'exécute après une lecture source complète, **Then** les lignes curated absentes de cette lecture (par clé de merge, par cloud) sont supprimées et celles présentes sont conservées.
2. **Given** une table curated **non** activée pour la purge (par défaut, notamment toute table incrémentale/watermarkée), **When** le job de purge s'exécute, **Then** aucune suppression n'a lieu sur cette table.
3. **Given** une lecture source partielle ou en échec côté ingestion, **When** le job d'ingestion échoue ou ne s'exécute que partiellement, **Then** aucune suppression n'est déclenchée en curated (le job de purge tourne sur son propre chemin d'exécution, à sa propre fréquence hebdomadaire et son propre cron décalé, sans jamais être appelé depuis le job/tâche d'ingestion, ni vérifier son statut).
4. **Given** un run de purge, **When** le nombre de lignes à supprimer dépasse le seuil absolu **ou** le seuil pourcentage configurés pour la table (le plus restrictif des deux s'applique), **Then** la purge s'arrête sans supprimer (garde-fou) et l'anomalie est tracée.
5. **Given** un opérateur souhaitant vérifier l'impact avant exécution, **When** il lance le mode dry-run du job de purge, **Then** le nombre de lignes qui seraient supprimées est restitué sans suppression réelle.
6. **Given** un run de purge exécuté (réel ou dry-run), **When** il se termine, **Then** le résultat (table, nombre de lignes évaluées/supprimées, mode) est inséré dans une table d'audit Delta dédiée, en plus du log structuré structlog.
7. **Given** la livraison de ce ticket, **When** le registre de purge est déployé, **Then** les 4 tables full-load du socle (`curated_dbx_uc_tables`, `curated_dbx_uc_table_tags`, `curated_dbx_compute_node_types`, `curated_dbx_billing_list_prices`) sont activées pour la purge.
8. Gates du package verts (lint → types → tests → build).

## Impact

Aucune modification du socle d'ingestion existant (`pipelines/system_tables`, `pipelines/common/readers.py`, `writers.py::build_merge_sql`, `transforms.py`) : le mécanisme de purge est additif, sur un chemin d'exécution séparé. Impact borné aux tables explicitement activées (opt-in) ; aucune table incrémentale ne peut être configurée pour la purge (garde-fou de conception, à valider en implémentation). Pas de breaking change sur les schémas curated existants — seules des lignes obsolètes sont retirées, jamais de colonnes.

## Out of scope (cet Epic)

Aucun — un seul domaine (DataEng) est in-scope pour cette spec.

## Work Breakdown (preview)

| ID | Domain | Summary | Ticket |
|----|--------|---------|--------|
| T001 | DataEng | Mécanisme de purge générique (registre opt-in, détection des lignes absentes, garde-fou volumétrique, dry-run, traçabilité) + job Databricks dédié, indépendant de l'ingestion — activé sur les 4 tables full-load du socle | ✅ |

## Rollback

Le job de purge est un composant additif et désactivable indépendamment (retrait de la table du registre de purge, ou pause du job dédié) sans impact sur le job d'ingestion existant. En cas de suppression erronée constatée, restauration via Delta Time Travel (`RESTORE TABLE ... TO VERSION AS OF`) sur la table curated concernée, la fenêtre de rétention Delta par défaut permettant un retour arrière rapide.

## Assumptions

- Le mécanisme de purge s'appuie sur une comparaison ensembliste (clé de merge, par cloud) entre la dernière lecture source complète et la table curated — pas de log de suppression disponible côté source.
- Le seuil de garde-fou volumétrique combine une borne absolue (nombre de lignes) et une borne pourcentage (part de la table), configurables par table ; le plus restrictif des deux déclenche l'arrêt. Les valeurs par défaut sont à définir en `plan`.
- Le job de purge peut relire la source (nouvelle lecture dédiée) plutôt que de réutiliser un résultat intermédiaire de l'ingestion, pour garantir l'indépendance des deux chemins d'exécution.
