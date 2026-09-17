# Checklist qualité — spec 022 cluster rolling windows

## Complétude

- [x] Un work type unique retenu (`feature`), blocs des autres work types élagués du template.
- [x] Domain Scope aligné sur `intake.json` (frontend ✅, backend ✅, dataeng ✅, devops ❌, qa ❌).
- [x] Ticket Plan cohérent : `expected_story_count = 3` = 3 lignes ✅ dans Work Breakdown = 3 User stories.
- [x] `## Prerequisites` non vide (gate `before_plan`).
- [x] Aucun `[NEEDS CLARIFICATION]` restant (max toléré : 3).
- [x] Dependency Analysis : chaque ligne porte une preuve avec son chemin de fichier.
- [x] Out of scope explicite (reliability_rolling, warehouses, page Clusters héritée).

## Testabilité

- [x] Chaque User story a un `Independent Test` exécutable sans les deux autres.
- [x] Les Acceptance Scenarios sont en Given/When/Then et portent sur un comportement observable.
- [x] Les cas dégradés sont couverts : pas de fenêtre précédente, `dbu_quantity` nulle,
      `workspace_id` inconnu de la dimension, cluster sans donnée sur la plage.
- [x] Les critères de succès sont mesurables sur le catalogue de dev (SC-001 à SC-004).

## Non-régression

- [x] L'onglet Governance est explicitement déclaré inchangé (FR-007, AC-2).
- [x] Les pages Warehouses et la page `Clusters.tsx` héritée sont hors périmètre.
- [x] La migration des deux tables efficiency est listée en prérequis, avec sa cause
      (changement de type de `active_hours` dans `b102155`).

## Points de vigilance pour le plan

- L'ordre des Stories est contraint : T001 (gold) → T002 (API) → T003 (UI). T002 ne peut
  pas être validée avant que les tables enrichies soient peuplées en dev.
- `uptime_hours_prev_window` doit rester `NULL` (et non `0`) sans fenêtre précédente,
  sinon le front affiche une régression de 100 % inventée.
- Les tendances par cluster restent servies par les tables `*_daily` : une table
  `*_rolling` ne porte qu'un point par fenêtre, elle ne peut pas alimenter une série.
