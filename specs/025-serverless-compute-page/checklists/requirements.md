# Requirements Quality Checklist — 025-serverless-compute-page

Validation de la spec avant `plan`. Cocher au fur et à mesure.

## Complétude

- [x] Work type (`feature`), priorité (P2), domaines et Ticket Plan renseignés
- [x] `## Prerequisites` présente et non-`TODO` (bloquant `before_plan`, gate vérifié exit 0)
- [x] Une User Story par domaine avec ticket (dataeng, backend, frontend)
- [x] Work Breakdown : une ligne par ticket (T001–T003), mode `one_per_domain`
- [x] Out of scope explicite (attribution fine SQL, cold start, notebooks via `query.history`,
      attribution NETWORKING, page par surface, CPU/mémoire/idle serverless, DevOps/QA)
- [x] Les 4 correctifs de l'existant sont dans la spec, pas seulement la page neuve
      (FR-001 à FR-005) — c'est la moitié de la valeur du lot

## Testabilité

- [x] Chaque FR est vérifiable (table / colonne / endpoint / bloc d'IHM nommés)
- [x] SC mesurables sur données réelles : comptages à 0 (SC-001, SC-004, SC-005, SC-007,
      SC-010), égalités de sommes (SC-002), cardinalités (SC-003, SC-008, SC-009),
      montants de référence (SC-006), percentiles reconstruits (SC-011)
- [x] Independent Test défini par story
- [x] Les valeurs de référence sont **datées** (2026-09-09) et le jeu de contrôles à rejouer
      est nommé (« Contrôles de non-régression » du spike, reprise dans `stories/T001.md`)
- [x] Restriction `cloud_provider = 'aws'` posée pour tout contrôle comparé au spike

## Cohérence

- [x] Anti-double-comptage `serverless_cost_daily` ↔ tables compute existantes explicité
      (FR-017), avec la somme des surfaces déclarée légitime
- [x] Ordre de livraison inter-domaines posé (DataEng → Backend → Frontend) **et**
      intra-DataEng (correctif warehouse en premier)
- [x] Grain tranché et justifié : `serverless_surface` **dans** le grain, `workspace_id`
      conservé (`AI_ENDPOINT` non unique), objet et non exécution
- [x] Contrainte du merge null-safe `<=>` propagée partout où une clé est produite
      (FR-007, FR-008, FR-009) — sentinelle `'_NO_OBJECT'`, `ELSE 'OTHER'`, `identity_source`
- [x] Aucun chiffre d'économie promis là où la mesure ne le porte pas
      (`performance_target` FR-021/FR-028, DLT serverless vs classic = corrélation)
- [x] Invariant « pas de faux signal » repris : un champ non applicable est `null`/absent,
      jamais `0` (FR-001, FR-013, FR-023, FR-030)

## Clarifications

- [x] `[NEEDS CLARIFICATION]` : **0 en attente** (max 3 autorisés)
- [x] 8 décisions de design verrouillées — section « Décisions verrouillées » (session
      2026-09-10, toutes adossées à une mesure du spike) : structure option A puis C ciblé,
      11 surfaces avec `GENIE` séparé, sentinelle `'_NO_OBJECT'` obligatoire,
      identité en `COALESCE` + `identity_source`, `usage_policy_id` écarté comme alias,
      agrégation des tables périodisées à l'heure, aucune économie chiffrée sur
      `performance_target`, `serverless_surface` dans le grain
- [x] Dépendance externe non résolue **assumée** et non transformée en question ouverte :
      `system.billing.attributed_usage` vide → limitation acceptée, hors scope
      (Prerequisites + Out of scope)
- [x] Écart mesuré vs spike documenté au lieu d'être lissé : le spike est mono-cloud (AWS),
      DCM est bi-cloud — Assumptions, tableau AWS/Azure du 2026-09-10
