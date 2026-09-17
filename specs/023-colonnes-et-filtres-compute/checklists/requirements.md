# Checklist qualité — spec 023 colonnes et filtres compute

## Complétude

- [x] Un work type unique retenu (`feature`), blocs des autres work types élagués.
- [x] Domain Scope aligné sur `intake.json` (dataeng ✅, backend ✅, frontend ✅, devops ❌, qa ❌).
- [x] Ticket Plan cohérent : `expected_story_count = 3` = 3 domaines = 3 branches filles.
- [x] `## Prerequisites` non vide (gate `before_plan`).
- [x] Aucun `[NEEDS CLARIFICATION]` restant : les 2 arbitrages bloquants ont été posés au
      demandeur, le 3e (client vs serveur) était tranché par le code.
- [x] Dependency Analysis : chaque ligne porte une preuve avec son chemin de fichier.
- [x] Out of scope explicite : 7 pages à `<TableHead>` manuel, 4 pages à accordéons,
      réordonnancement/masquage de colonnes, filtres multi-valeurs, export.
- [x] Le périmètre « toutes les colonnes de tous les modules » est **chiffré** : 5 pages,
      11 tableaux, 109 colonnes, 88 filtrables — pas une formule vague.

## Testabilité

- [x] Chaque User story a un `Independent Test` exécutable sans les autres.
- [x] Acceptance Scenarios en Given/When/Then, sur un comportement observable.
- [x] Cas dégradés couverts : warehouse absent du curated, warehouse renommé en cours de
      fenêtre, fenêtre sans donnée, `cost_usd_prev_window` nul, clé de colonne inconnue,
      contradiction entre paramètre historique et `column_filter`, largeur persistée
      invalide ou orpheline, `localStorage` indisponible, liste de valeurs tronquée.
- [x] Critères de succès mesurables sur le catalogue de dev (SC-001 à SC-005), avec les
      requêtes de contrôle écrites dans `quickstart.md`.
- [x] Les contrôles qui pourraient être vides sont marqués « non joué » et non « vert »
      (quickstart §4.5).

## Non-régression

- [x] L'onglet Requêtes lentes est déclaré inchangé, avec test à l'appui.
- [x] `/warehouses/{id}` et `/warehouses/{id}/cost-trend` déclarés inchangés.
- [x] Les paramètres d'API historiques sont **conservés** (P15) ; les 2 ruptures assumées
      sont nommées et justifiées.
- [x] La descente des helpers de fenêtre dans `_common` ne doit rien changer côté clusters :
      critère d'acceptation explicite de T002.
- [x] Les 7 pages hors périmètre gardent leurs largeurs automatiques et leurs filtres.

## Sécurité

- [x] Injection SQL traitée comme le risque principal de T004 : allowlist par vue comme
      seule source d'expressions, valeurs en paramètres liés, patron déjà en place
      (`_OVERVIEW_SORT_COLUMNS`).
- [x] Aucun PAT, aucun secret, aucun DBFS ; déploiement pipeline sous OAuth.
- [x] La divergence PAT en lecture seule héritée de 022 est reconduite **explicitement** en
      `quickstart.md` §6.1, avec ce qui manque pour la refermer — pas passée sous silence.
- [x] `localStorage` ne reçoit que des largeurs en pixels : aucune donnée métier.

## Honnêteté des mesures

- [x] Le ~80 % de lignes anonymes est mesuré, avec la requête et la cause structurelle.
- [x] Il est signalé que la mesure porte sur `utilization_rolling` et non sur le couple
      exact concerné, et un contrôle de dev (§4.3) est prévu pour la refaire sur le bon
      couple — avec la consigne de rouvrir R1 si le chiffre ne tient pas.
- [x] T001 précise que les tables d'utilisation ne sont lues par **aucun** endpoint, donc
      qu'elles sont incluses par cohérence et non par nécessité.
