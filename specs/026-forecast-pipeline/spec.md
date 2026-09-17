# feature : Pipeline de prévision (forecast) `gold_dbx_compute` / `gold_dbx_usage`

**Feature Branch**: `026-forecast-pipeline` — branche fille git existante : `dataeng/026-forecast-guards`
**Work Type**: feature
**Priority**: P2
**Created**: 2026-09-14

**Input**: Documenter rétroactivement le pipeline de prévision (forecast) de la consommation Databricks — chaîne de production complète : sélection et densification de l'historique, appel du moteur `ai_forecast`, détermination de l'horizon, écriture des tables `gold_dbx_compute_forecast_daily` / `gold_dbx_usage_forecast_daily`, cycle de vie entre deux exécutions. Spec écrite après coup pour tracer un travail déjà implémenté sur la branche `dataeng/026-forecast-guards` (commit #270 et suivants).

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

La prévision répond à une question unique : à activité comparable à celle des deux dernières
semaines, quelle consommation journalière attendre d'un objet Databricks (cluster, job, pipeline,
warehouse, table Unity Catalog), et dans quelle fourchette ? Le pipeline produit cette réponse pour
deux domaines : **Compute** (coût, DBU, CPU, requêtes, file d'attente — 11 combinaisons type
d'objet/métrique) et **Usage** (requêtes, consommateurs distincts, coût estimé, octets lus, par table
Unity Catalog).

**Chaîne de production** :

```
tables gold *_daily          observed                 ai_forecast              table forecast
(historique agrégé)   →  (fenêtre + éligibilité   →  (un modèle par    →   (futur reconstruit
                            + grille journalière)       objet)                à chaque run)
```

1. **La source est toujours la couche gold**, jamais le brut : le coût prévu et le coût observé
   ailleurs dans DCM partagent la même définition.
2. **L'historique d'entraînement (`observed`) est construit** à partir des tables `*_daily` : unicité
   du couple (objet, jour), condition d'éligibilité, distinction métriques additives / de distribution,
   densification à 0 des jours calendaires manquants (additives uniquement).
3. **`ai_forecast`** (fonction SQL native Databricks, table-valued) ajuste un modèle par objet
   (`group_col`) et projette les jours suivants au pas journalier (`frequency => 'D'`), avec un
   intervalle de prédiction à 0,95 et des bornes métier (`global_floor`/`global_cap`, plafond relatif
   ×10 du maximum observé de la série) empêchant une projection publiée sans rapport avec l'activité
   réelle.
4. **L'horizon est ancré sur la fraîcheur propre à chaque source** : chaque passe (6 tables source
   compute + 1 table usage) plafonne sa projection sur son propre dernier jour observé + 7 jours, pour
   que les totaux restent comparables entre types d'objets malgré des fraîcheurs différentes.
5. **Le résultat est écrit en Delta** selon un cycle de vie fixe entre deux exécutions : le futur est
   reconstruit à chaque run (les lignes futures obsolètes sont supprimées), le passé est conservé
   (traçabilité prévision vs réalisé) ; un résultat de calcul vide désactive la suppression pour ne pas
   vider la table sur incident.

Ce ticket couvre la construction du pipeline (étapes 1 à 5, `packages/dcm-databricks-pipeline`). La
restitution par l'API et l'interface (étape suivante de la chaîne) est déjà implémentée sur cette
branche mais hors périmètre de ce ticket — cf. Out of scope.

## Dependency Analysis

| Besoin | Domaine requis | Preuve (fichier) | Résolution |
|--------|----------------|-------------------|------------|
| Restitution API du forecast (lecture des tables gold, agrégation par périmètre) | backend | `packages/dcm-backend/app/api/services/compute_metrics_forecast.py` — déjà modifié sur cette branche | `deferred` — déjà implémenté, pas de Story séparée pour ce ticket rétroactif |
| Widget UI de la courbe de prévision (bande de confiance, distinction réalisé/projeté) | frontend | `packages/dcm-frontend/src/components/domain/compute/forecast-widget.tsx` — déjà modifié sur cette branche | `deferred` — déjà implémenté, pas de Story séparée pour ce ticket rétroactif |

## Prerequisites

- **Small branches / small PRs** : le travail documenté ici est déjà mergé sur la branche
  `dataeng/026-forecast-guards` (packages/dcm-databricks-pipeline uniquement pour ce ticket) — aucune
  branche fille supplémentaire n'est requise pour l'implémentation, seulement pour un correctif
  ultérieur éventuel.
- Intake + domain scope confirmés (`intake.json` / `domain-scope.json`).
- Dépendances de Dependency Analysis (backend, frontend) reportées : code déjà en place sur cette
  branche, documentées pour mémoire, hors ticket.
- Pas de `[NEEDS CLARIFICATION]` restant : le comportement est déjà implémenté et testé
  (`test_forecast.py`, `test_forecast_daily.py`), cette spec en fait le constat.

## User stories

### User Story 1 — Pipeline de prévision compute/usage de bout en bout (Priority: P1)

En tant qu'utilisateur de DCM consultant une courbe de prévision (coût, DBU, CPU, requêtes, file
d'attente, popularité des tables), je dois disposer d'une table de prévision à jour à chaque
exécution du pipeline gold, produite à partir de l'historique réellement observé de chaque objet, sur
un horizon ancré à la fraîcheur de sa propre source, et fiable : elle ne doit ni surévaluer la dépense
d'un objet trop récent pour avoir un historique exploitable, ni afficher une valeur explosée par un
décrochement d'activité, ni mélanger deux jours en un seul point.

**Why this priority** : c'est le socle de toute la fonctionnalité de prévision dans DCM — sans un
pipeline produisant des tables `gold_dbx_compute_forecast_daily` / `gold_dbx_usage_forecast_daily`
fiables, l'API et l'interface qui les consomment n'ont rien à restituer, ou restituent des valeurs
sans rapport avec la réalité (mesuré : un facteur ~500 000 sur une série UC en l'absence de garde-fou).

**Independent Test** : exécuter `build_compute_forecast` / `build_usage_forecast_daily` sur un jeu de
données de test couvrant un objet actif en continu, un objet à un seul jour d'activité, un objet à
décrochement brutal, et un objet avec deux lignes source le même jour ; vérifier que la table produite
contient une ligne par (objet, métrique, jour d'horizon) pour les cas éligibles, et aucune ligne pour
les trois situations dégradées.

**Acceptance Scenarios**

1. **Given** un objet avec une activité continue sur la fenêtre d'historique, **When** le pipeline de
   prévision s'exécute, **Then** une ligne de prévision est produite pour chaque jour de l'horizon,
   valorisée (`predicted_value`, `lower_bound`, `upper_bound`) dans `gold_dbx_compute_forecast_daily`
   ou `gold_dbx_usage_forecast_daily`.
2. **Given** un objet avec moins de 3 jours d'activité réelle sur 14 (8 jours pour le domaine usage),
   **When** le forecast est calculé, **Then** aucune ligne de prévision n'est produite pour cet objet
   (pas de ligne à zéro).
3. **Given** une série dont le modèle projette une valeur supérieure à 10 × le maximum journalier
   observé de cette même série, **When** le forecast est calculé, **Then** cette ligne n'est pas
   publiée en table.
4. **Given** un objet avec plusieurs lignes source le même jour (ex. `compute_kind` différent),
   **When** l'historique d'entraînement (`observed`) est construit, **Then** ces lignes sont agrégées
   en une seule valeur par jour (`SUM` pour les métriques additives, `MAX` pour les métriques de
   distribution).
5. **Given** un jour calendaire sans ligne source pour un objet éligible, **When** l'historique est
   densifié, **Then** ce jour est complété à 0 pour une métrique additive, et **laissé absent** pour
   une métrique de distribution.
6. **Given** des sources compute de fraîcheur différente (ex. une table chargée jusqu'à J, une autre
   jusqu'à J-2), **When** l'horizon est déterminé pour chacune, **Then** chaque passe est plafonnée sur
   son propre dernier jour observé + 7 jours, sans jamais produire une prévision pour un jour déjà
   écoulé.
7. **Given** une exécution normale du pipeline, **When** la table de prévision est mise à jour,
   **Then** les lignes dont l'horizon est à venir et que l'exécution courante ne produit plus sont
   supprimées, tandis que les lignes dont l'horizon est déjà écoulé sont conservées (traçabilité
   prévision vs réalisé).
8. **Given** une exécution dont le résultat est vide (warehouse indisponible, source en échec),
   **When** la table de prévision est mise à jour, **Then** les lignes futures existantes ne sont pas
   supprimées (garde-fou anti-vidage).

## Acceptance Criteria

1. Les scénarios 1 à 8 ci-dessus sont couverts par les tests `test_forecast.py` et
   `test_forecast_daily.py` de `packages/dcm-databricks-pipeline`.
2. Gates du package verts (lint → types → tests → build) sur `packages/dcm-databricks-pipeline`.

## Out of scope (cet Epic)

- **Backend** : consommation de `gold_dbx_compute_forecast_daily`/`gold_dbx_usage_forecast_daily` par
  l'API (`compute_metrics_forecast.py`) — déjà implémentée sur cette branche, pas de Story séparée.
- **Frontend** : restitution graphique (`forecast-widget.tsx`) — déjà implémentée sur cette branche,
  pas de Story séparée.

## Work Breakdown (preview)

| ID | Domain | Summary | Ticket |
|----|--------|---------|--------|
| T001 | DataEng | Pipeline de prévision compute/usage : construction de l'historique, appel `ai_forecast`, ancrage de l'horizon, cycle de vie de la table | ✅ |
| — | Backend | Restitution API déjà en place | ❌ hors Epic |
| — | Frontend | Widget UI déjà en place | ❌ hors Epic |

## Requirements & Success Criteria

- **FR-000** : Le pipeline lit l'historique depuis les tables gold `*_daily` (jamais le brut), construit
  pour chaque objet éligible une série d'entraînement (`observed`), appelle `ai_forecast` pour projeter
  les jours suivants, et écrit le résultat dans `gold_dbx_compute_forecast_daily` /
  `gold_dbx_usage_forecast_daily` — une ligne par (objet, métrique, jour d'horizon).
- **FR-001** : Un objet doit présenter au moins 3 jours d'activité réelle sur la fenêtre de 14 jours
  (8 jours pour le domaine usage) pour recevoir une ligne de prévision ; en deçà, aucune ligne n'est
  produite.
- **FR-002** : Une prévision dont la valeur dépasse 10 × le maximum journalier observé de sa propre
  série n'est pas publiée.
- **FR-003** : Plusieurs lignes source pour le même couple (objet, jour) sont agrégées en une seule
  valeur avant d'être fournies au modèle (`SUM` pour les métriques additives, `MAX` pour les métriques
  de distribution).
- **FR-004** : Les jours calendaires sans ligne source sont densifiés à 0 pour les métriques additives
  uniquement ; les métriques de distribution restent creuses sur ces jours.
- **FR-005** : Chaque source compute ancre son horizon de projection sur son propre dernier jour
  observé + 7 jours, indépendamment de la fraîcheur des autres sources.
- **FR-006** : À chaque exécution, les lignes futures obsolètes (horizon à venir, non reproduites par
  le run courant) sont supprimées et les lignes passées (horizon déjà écoulé) sont conservées, pour
  permettre la comparaison ultérieure prévision vs réalisé.
- **FR-007** : Un résultat de calcul vide ne déclenche pas la suppression des lignes de prévision
  futures déjà en table.
- **SC-001** : Sur le jeu de données de test du parc UC, aucune table à décrochement ne produit une
  ligne de prévision au-delà du plafond relatif (0 dépassement observé après application du garde-fou,
  contre le cas mesuré de 5,5 × 10¹⁴ requêtes/jour avant garde-fou).
- **SC-002** : 100 % des objets avec moins de 3 jours d'activité (8 pour l'usage) sont absents de la
  table de prévision plutôt que d'y figurer avec une projection en droite constante.
- **SC-003** : Chaque exécution du pipeline gold produit une table de prévision cohérente avec la
  fraîcheur du jour (aucune ligne au-delà de `dernier jour observé + 7`), sans intervention manuelle.

## Assumptions

- Les seuils numériques (3 jours / 8 jours, plafond ×10, fenêtre 14 jours, horizon 7 jours,
  `prediction_interval_width` 0,95) sont ceux déjà en place dans `specs.py` et ne sont pas remis en
  question par ce ticket rétroactif ; toute évolution de seuil est un ticket distinct.
- Le contrat de sortie des tables gold (`gold_dbx_compute_forecast_daily`,
  `gold_dbx_usage_forecast_daily`) reste inchangé : ce ticket documente le calcul, pas son schéma.
