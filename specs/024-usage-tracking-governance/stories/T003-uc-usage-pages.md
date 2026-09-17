# T003 — Frontend : pages Usage des tables UC et Gouvernance & Recommandations

**Domain**: frontend
**Package**: `packages/dcm-frontend`
**Branch**: `dataeng/024-usage-tracking-governance` ⚠️ **branche unique partagée** avec T001
et T002 — ne pas créer `frontend/024-…` que le parseur dérive du titre
**Jira**: `DCINT-334` (1 seule Story pour les 3 tasks)
**Depends on**: **T002** — démarre quand T002 est cochée
**Work type**: feature

## Description

Deux pages sous le menu **Databricks**, consommant les endpoints `/api/v1/uc-usage` :

1. **Usage des tables UC** — section Vue d'ensemble (6 KPI, 3 tendances +7j, 1 carte Volume
   écrit observée) puis 3 vues en tabbar : Par table (défaut, avec drill-down), Par
   consommateur, FinOps.
2. **Gouvernance & Recommandations** — 2 onglets : registre des tables, cartes de
   recommandations filtrables par catégorie.

Filtres catalogue/schéma/table(s) communs. **Aucune requête de données au chargement**,
datée ou non : le bandeau de période global reste affiché, mais rien ne part avant un clic
sur **Appliquer**, hormis `/filters/options` qui peuple le sélecteur de périmètre.

La task a été livrée en **8 étapes** : les 2 pages, puis une seconde vague fonctionnelle
(graphiques, exploration, filtres de colonne), puis cinq corrections issues de retours
utilisateur sur ce qui était affiché, et enfin `include_deleted` côté UI. Les étapes 3, 5 et
6 sont la moitié frontend de commits qui touchent aussi le backend — l'autre moitié est dans
[T002](T002-uc-usage-api.md).

---

## Étape 1 — Les deux pages (`8a84f57`)

- `UsageTablesUc.tsx` — Vue d'ensemble, tabbar 3 vues, filtres communs, bouton **Appliquer**,
  drill-down top 5 consommateurs par **drawer** (le dépôt n'a pas de ligne dépliable ;
  pattern `compute-cluster-drawer.tsx`)
- `UsageGovernance.tsx` — registre + cartes de recommandations
- `useUcUsageQueries.ts` — hooks TanStack, `enabled` conditionné à un état local
  `appliedPeriod` (`null` au premier rendu) ; pattern déjà présent dans
  `useComputeClustersQueries.ts`
- `ucUsageQueryKeys` — normalisation des params (tableaux triés puis joints)
- `lib/uc-usage/severity.ts` — normalisation de casse (FR-015) : `table_governance` écrit en
  minuscules et `recommendations` en majuscules ; `getCheckEffectPillClass()` n'est **pas**
  modifié, la normalisation se fait en amont
- Permission `page:unity-catalog` (pas `page:databricks`) : ces pages sont réservées au scope
  non restreint, comme l'explorateur de tables brutes (FR-021)

## Étape 2 — Graphiques, exploration et filtres de colonne (`42af104`, part frontend)

Seconde vague fonctionnelle demandée après la première livraison : time chart, heatmap,
scatter, tiroir de détail d'entité, filtres par colonne, écran d'accueil « Your analysis
starts here ». **41 fichiers frontend** sur les 54 du commit ; les 13 autres sont les 5
services backend de [T002 étape 2](T002-uc-usage-api.md).

Ce commit a aussi **retiré le bloc « Points d'attention »** de la page d'usage, sur demande
utilisateur — retrait resté non consigné dans `spec.md` jusqu'à l'amendement FR-001 du
2026-09-15 (`1316d2d`). `GET /attention` reste livré côté backend, sans consommateur.

⚠️ Ce travail est parti **hors task**, sans critères écrits d'avance, et « Diff stays
reviewable » n'a **pas** été tenu : 54 fichiers, ~7 900 lignes ajoutées en un commit. À
découper si un travail de cette taille se reproduit. Le SHA `7490304`, cité par le rapport de
review de l'amendement FR-001, est la version **pré-réécriture** de ce commit ; elle n'est
plus dans l'historique.

## Étape 3 — Cartes de tendance sur la période (`8b8b001`, part frontend)

`uc-usage-trend-cards.tsx` lisait le **dernier jour** au lieu de la période, contrairement au
reste du bloc Vue d'ensemble. Corrigé en chiffre de période, avec une **moyenne/jour** pour les
couples consommateur-table — les sommer compterait trente fois le même lecteur — et le libellé
« Distinct consumers » renommé **« Consumer-table pairs »** : la série somme les consommateurs
*par table* (185 687) quand le KPI « Consumers » de la même page compte les têtes (2 256).
Les trois autres défauts du même commit sont côté service ([T002 étape 3](T002-uc-usage-api.md)).

## Étape 4 — Rendre visibles les hausses de coût (`4320d49`)

`--tdf-orange` n'est déclaré par **aucun thème** : la déclaration `background` était invalide
et les barres de hausse n'avaient aucun fond, alors que les baisses en `--tdf-teal` peignaient
normalement. Une hausse de coût était littéralement invisible. Remplacé par `--warning`.

Trois corrections d'échelle sont venues avec :

- les négatifs sont ancrés par `right: 50%` sur la ligne du zéro, ce qui permet un minimum de
  4 px sans déborder du mauvais côté ;
- l'échelle se cale sur le **pic de la période**, plus sur un plancher arbitraire à 1 $ ;
- un clic sur une table l'**exclut de l'échelle** et redéploie les autres barres, la ligne
  restant en place avec ses chiffres — le top 10 vient du backend et ne se relance pas.

Et un garde-fou : `design-tokens.test.ts` échoue si un composant référence une custom property
CSS non déclarée. **Le garde-fou vaut plus que le correctif** — un token inexistant ne
produisait aucune erreur, ni au build ni au test. C'est le seul défaut de la branche
qu'aucun gate ne pouvait attraper.

## Étape 5 — Aligner « Cost by table » sur les deux autres tableaux (`ba40300`, part frontend)

Le tableau était figé sur « coût décroissant », sans en-tête cliquable ni entonnoir, et il
**ignorait la boîte de recherche de la page** — laquelle reste pourtant affichée dans l'onglet
FinOps, ce qui laissait croire à un résultat filtré. Deux tableaux voisins de la même page,
deux comportements.

Câblage identique à « By table » et « By consumer », en réutilisant `lib/uc-usage/column-filters.ts`
plutôt qu'en dupliquant la logique. Le côté serveur est [T002 étape 4](T002-uc-usage-api.md).

## Étape 6 — Faire remplir sa carte au tableau sur un grand écran (`05c2f59`)

Les trois tableaux de la page ne totalisent pas la même largeur déclarée : « By table »
1855 px sur 11 colonnes, « By consumer » 1530 px sur 10, « Cost by table » **1130 px sur 6**.
`ComputeDataTable` posait `style={{ width: totalWidth }}`, qui écrase le `w-full` de
`ui/table` : sur une zone de contenu de ~1500 px, « By table » remplit et défile, alors que
« Cost by table » s'arrête ~370 px avant le bord de sa carte. Même incohérence entre tableaux
voisins que l'étape 5, sur la géométrie cette fois.

Le composant est partagé par **14 tableaux**, donc la correction est **opt-in** : prop
`stretchColumnId`, `totalWidth` devient un plancher (`width: 100%` + `minWidth: totalWidth`),
et la colonne désignée part du `<colgroup>` sans largeur — sous `table-layout: fixed`, la seule
colonne `auto` prend ce qui reste. Les 13 autres tableaux gardent leur géométrie à l'octet.

## Étape 7 — Demander un périmètre avant d'afficher l'état de gouvernance (`f8b204a`)

`UsageGovernance` démarrait avec `filters = {}` et aucune condition d'application : KPI,
graphiques et registre partaient **au montage**, et la page s'ouvrait sur « All catalogs and
schemas ». `UsageTablesUc` fait l'inverse depuis l'étape 1. Deux pages voisines, deux entrées
opposées, et un balayage de tous les catalogues déclenché sans que personne ne l'ait demandé.

- Gate `applied: boolean` — et **pas** `appliedPeriod` : cette page est un snapshot sans période
- `applied && …` sur les 5 hooks (KPI, graphiques des 2 onglets, registre, recommandations) ;
  `useUcUsageGovernanceKpis` reçoit un paramètre `enabled`, il était le seul hook snapshot à ne
  pas en avoir
- Filtre en `requireScope` + `catalogTriggerRef`, comme la page d'usage
- `UcUsageWelcome` gagne `variant` (`'usage'` | `'governance'`)
- Bandeau « Selection changed… » quand le brouillon diverge du périmètre appliqué

Cette étape a laissé `spec.md` en contradiction avec le code : FR-017 décrivait encore des
endpoints snapshot qui partaient au montage. Écart déclaré à l'époque plutôt que corrigé en
silence — la réécriture d'un FR est une décision de spec, tranchée par l'amendement du
2026-09-15 (`53e293f`).

## Étape 8 — Case « Include deleted tables » et marqueur de suppression (`2ae1c52`)

FR-023 côté UI. La case vit dans le **bloc de périmètre**, aux côtés de catalogue / schéma /
tables, sur les 2 pages : c'est là que l'utilisateur décide ce qu'il analyse, et le message
« Select a catalog, a schema or at least one table to start the analysis » y est déjà.
Décochée par défaut, elle part avec le même clic sur **Appliquer** que le reste du périmètre
(FR-017) — rien ne se recharge à la coche.

Une exception assumée : `/filters/options` écoute la case **immédiatement**. Sans cela une
table supprimée ne pourrait jamais être cochée dans le sélecteur, et la case n'aurait aucun
effet atteignable.

Les lignes supprimées sont marquées avec **leur date de suppression** dans les trois tableaux
de grain table et dans le tiroir d'historique : sans la date, une ligne supprimée se lirait
comme une ligne vide plutôt que comme de l'historique.

`include_deleted: filters.includeDeleted || undefined` — le client saute les paramètres
`undefined`, donc l'URL décochée reste **exactement** celle d'avant la spec 027. Le drapeau
entre aussi dans les clés TanStack, sans quoi cocher la case resservirait le cache filtré
autrement. `useConsumerScopeParams()` le **retire** des 2 vues de grain consommateur, qui
n'ont aucune clé table à filtrer.

Pas de primitive `ui/checkbox` dans le dépôt : un `<input type="checkbox">` dans un `<label>`
est le pattern maison, et donne le rôle `checkbox` nommé aux tests.

---

## Files to create/modify

Pages et routage :

- CREATE `src/pages/UsageTablesUc.tsx` + `UsageTablesUc.test.tsx`
- CREATE `src/pages/UsageGovernance.tsx` + `UsageGovernance.test.tsx`
- UPDATE `src/app-routes.ts` — 2 routes lazy
- UPDATE `src/config/navigation.ts` — 2 entrées sous Databricks
- UPDATE `src/config/role-permissions.ts` — 2 mappings `page:unity-catalog`

Données :

- CREATE `src/hooks/useUcUsageQueries.ts` — hooks, `UcUsageFilters` (`includeDeleted` en
  étape 8), `useConsumerScopeParams()`
- UPDATE `src/hooks/query-keys.ts` — `ucUsageQueryKeys`, `normalizeUcUsageScope`, clé
  `filterOptions`
- UPDATE `src/api/dcmApiClient.ts` — fonctions GET du contrat (aucun `fetch` hors ce module)
- UPDATE `src/types/api.ts` — types miroir des réponses, `UcUsageLifecycle` étendu par les 6
  interfaces de grain table

Composants (`src/components/domain/uc-usage/`) :

- CREATE filtres, multi-select, cartes de tendance, panneau top consommateurs, écran d'accueil
  (`uc-usage-welcome.tsx`, prop `variant`), carte de recommandation (étapes 1, 2, 7)
- CREATE time chart, heatmap, scatter, `uc-usage-exploration-charts.tsx`,
  `uc-usage-chart-utils.ts`, `uc-usage-detail-drawer.tsx` (étapes 2, 4)
- CREATE `uc-usage-deleted-badge.tsx` — marqueur + date (étape 8)
- UPDATE `src/components/domain/compute/compute-data-table.tsx`,
  `compute-column-resizer.tsx` — redimensionnement partagé (étape 2), prop `stretchColumnId`
  (étape 6) + `compute-data-table.test.tsx`

Helpers (`src/lib/uc-usage/`) :

- CREATE `severity.ts`, `column-filters.ts`, `labels.ts`, `recommendation-copy.ts`,
  `filters.ts`

Tests et fixtures :

- CREATE `src/test/fixtures/uc-usage.ts`, `uc-usage-charts.ts`, `uc-governance-charts.ts`,
  `uc-usage-exploration.ts` (dont `ucUsageDeletedLifecycle`)
- CREATE `src/components/domain/uc-usage/uc-usage-exploration.test.tsx`
- CREATE `src/styles/design-tokens.test.ts` — garde-fou des custom properties (étape 4)

## Acceptance Criteria

### Étape 1 — les deux pages

- [x] **Aucune requête de données émise au chargement**, datée ou non — seul
      `/filters/options` part, pour peupler le sélecteur de périmètre ; l'onglet Réseau le
      prouve (FR-017, amendé le 2026-09-15 : les endpoints snapshot de la page Gouvernance
      attendent eux aussi **Appliquer**)
- [x] Un état explicite invite à choisir un périmètre puis à cliquer **Appliquer** —
      `UcUsageWelcome`, sur les 2 pages
- [x] Tous les libellés d'horizon disent **« +7j »** — `grep -rn "+14j" src/` ne renvoie rien
      (SC-004)
- [x] La carte Volume écrit est présentée comme **observée**, pas prévisionnelle, et n'affiche
      pas `0` quand la valeur est `null`
- [x] Forecast absent ⇒ **tiret**, jamais `0` ni `$0` (SC-005)
- [x] Owner absent ⇒ « **Non renseigné** », jamais une cellule vide (FR-012)
- [x] Drill-down plafonné à **5** consommateurs, triés par coût, sans pagination (FR-004)
- [x] Le switch de vue **ne réinitialise pas** les filtres communs (FR-002)
- [x] Filtre table appliqué à la vue Par consommateur par **intersection** (FR-003)
- [x] Recommandations : `status='OPEN'`, filtre par catégorie (liste fermée à 5), tri
      `severity` desc ; `HIGH`/`MEDIUM`/`LOW` et `high`/`medium`/`low` rendus par le **même**
      badge (FR-013, FR-015)
- [x] Statut du registre dérivé du mot-clé `recommended_action`
      (`archiver`/`documenter`/`surveiller`/`null`), pas d'un texte libre (FR-012)
- [x] Bandeau **sans** filtre Workspace, LZ ni Cloud ; le sélecteur de période reste (FR-010,
      FR-019)
- [x] Sélecteur de type de consommateur **sans** option `GENIE` ; une valeur inconnue est
      affichée telle quelle, jamais masquée
- [x] **Aucun** bouton « Acquitter » sur une recommandation
- [x] Les 4 états sont rendus sans crash : invite à choisir une période, chargement, vide, erreur
- [x] Tooltip sur le coût mentionnant `cost_attribution_method` et `cost_basis` (FR-009)
- [x] Aucune occurrence de `cost_usd`, `table_catalog` ou `table_schema` — seulement
      `estimated_cost_usd`, `catalog`, `schema` (FR-008)

### Étape 2 — graphiques, exploration, filtres de colonne

- [x] Les 2 pages rendent leurs graphiques sur un périmètre appliqué
- [x] Chaque colonne filtrable l'est côté serveur, pas après pagination
- [x] Aucun bloc ne s'affiche **sans périmètre appliqué** — le bloc « Points d'attention » a
      été retiré sur demande utilisateur (FR-001, amendé le 2026-09-15)

### Étape 3 — cartes de tendance

- [x] Les cartes portent un chiffre de **période**, comme le reste de la Vue d'ensemble
- [x] Deux libellés distincts pour deux chiffres distincts (paires vs têtes)

### Étape 4 — hausses de coût

- [x] Une hausse de coût est visible (fond peint)
- [x] Une barre négative ne déborde pas du mauvais côté du zéro (minimum 4 px)
- [x] Exclure une table redéploie les autres barres **sans nouvel appel réseau**
- [x] Une custom property CSS non déclarée fait échouer les tests

### Étape 5 — « Cost by table »

- [x] Les en-têtes trient côté serveur, comme les 2 autres tableaux
- [x] La boîte de recherche de la page filtre réellement l'onglet FinOps

### Étape 6 — géométrie du tableau

- [x] « Cost by table » remplit sa carte sur un grand écran
- [x] Le redimensionnement de colonne des 14 tableaux partageant le composant est intact
- [x] Aucun tableau autre que celui visé ne change de rendu (prop opt-in)

### Étape 7 — périmètre obligatoire sur Gouvernance

- [x] Aucun appel réseau avant **Apply** sur la page Gouvernance
- [x] L'accueil « Your analysis starts here » s'affiche à l'arrivée, variante gouvernance
- [x] Après Apply, un changement de brouillon affiche le bandeau au lieu de recharger

### Étape 8 — `include_deleted`

- [x] Cocher la case **ne déclenche aucune** requête d'analyse ; après **Appliquer**,
      `include_deleted=true` part vers `/tables`, `/overview`, `/charts/tables`,
      `/finops/trends`, `/governance/registry`, `/governance/kpis`, `/governance/charts`
- [x] `/consumers` et `/charts/consumers` ne reçoivent **jamais** le drapeau et ne rechargent
      pas quand la case change
- [x] Le sélecteur de tables, lui, obéit à la case sans attendre **Appliquer**, et l'option
      supprimée porte le suffixe `deleted`
- [x] Une ligne supprimée affiche `Deleted <date>` dans les tableaux de grain table ; une
      ligne vivante n'affiche rien
- [x] Le tiroir d'historique rappelle la suppression **sans** changer son titre, qui nomme la
      boîte de dialogue
- [x] Case décochée : la requête est **identique** à celle d'avant la spec 027 (paramètre omis,
      pas `include_deleted=false`)

### Les huit étapes

- [x] Aucun `any` committé ; `lint`, `tsc --noEmit`, `test`, `build` verts — aucune régression
      introduite (3 échecs pré-existants sur `App`, `Dashboard`, `Databricks`, vérifiés
      identiques sur `HEAD` sans ces changements)

## Tests

```bash
cd packages/dcm-frontend
npm run lint && npx tsc --noEmit
npm run test -- src/pages/UsageTablesUc.test.tsx src/pages/UsageGovernance.test.tsx \
  src/components/domain/compute/compute-data-table.test.tsx \
  src/components/domain/uc-usage/uc-usage-exploration.test.tsx \
  src/styles/design-tokens.test.ts
npm run build
```

Mock : `vi.mock('../api/dcmApiClient')`, fixtures dans `src/test/fixtures/uc-usage*.ts`, rendu
via `renderWithProviders` de `src/test/render.tsx`.

## Out of scope

- Persistance des filtres lors de la navigation entre les 2 pages (FR9 du draft, reporté)
- Filtre `GENIE` (chantier DataEng non démarré)
- Action d'acquittement d'une recommandation
- Ligne de tableau dépliable : le dépôt n'en a pas ; pattern **drawer** pour le drill-down
- Modification de `DataProductUsage.tsx` ou de l'ancienne API `data-product-usage`
- Modification de `getCheckEffectPillClass()` dans `lib/domain/governance.ts` — la
  normalisation se fait en amont, dans un helper dédié
- Un libellé français pour la case : toute la copie UI de ces pages est en anglais, donc
  « Include deleted tables » et non « Inclure les tables supprimées » comme le cite le contrat
  027. Écart assumé, consigné dans l'amendement FR-023
- Marquer les lignes de grain recommandation : elles ne portent pas les trois champs de cycle
  de vie
- Un filtre à trois états (actives / supprimées / toutes) : la spec 027 gèle un booléen
- `useUcUsageTopConsumers` accepte le drapeau mais n'a pas encore d'appelant : le drill-down
  top 5 n'est pas monté dans les pages aujourd'hui
- La variante « `w-full` sur le tableau, toutes les colonnes fixes » de l'étape 6 : écartée,
  elle cassait le redimensionnement
- Étendre `stretchColumnId` à « By consumer » (1530 px, même écart en plus petit) : possible,
  non demandé ; « By table » (1855 px) défile déjà, la prop n'y changerait rien

## Revues

| Étape | Rapport | Verdict | Reste ouvert |
|---|---|---|---|
| 1 | review 2026-09-13 | **PASS** (0 🔴, 2 🟡) | `UsageTablesUc.tsx` dépasse 800 lignes — découpage à envisager ; PR volumineuse (40 fichiers, ~4 700 lignes), attendu pour 2 pages neuves |
| 2 | — | rapport **perdu** (jamais versionné) | la revue a eu lieu (stamp exigé par le hook), le rapport était nommé d'après un compteur de reviews. « Diff stays reviewable » non tenu |
| 3 | — | rapport **perdu**, même cause | — |
| 4 | — | rapport **perdu**, même cause | — |
| 5 | review 2026-09-15 | **PASS** | rien |
| 6 | review 2026-09-15 | **PASS** (0 🔴, 1 🟡) | jsdom ne calcule aucune mise en page : les tests verrouillent le **mécanisme**, pas la répartition réelle des pixels. Ni Playwright ni Puppeteer dans le package ; vérification à l'œil sur un comparatif statique. Limite de vérification déclarée, pas un défaut du code |
| 7 | review 2026-09-15 | **PASS** (0 🔴, 1 🟡) | le 🟡 était l'écart avec FR-017 — **résolu** par l'amendement `53e293f` |
| 8 | review 2026-09-16 | **PASS** (0 🔴, 1 🟡) | le libellé anglais, assumé et consigné en Out of scope |

Un 🟡 reste ouvert hors étape, relevé par la revue de l'amendement FR-001 :
`uc-usage-attention-panel.tsx` n'a plus aucun import depuis `7490304`, comme
`useUcUsageAttention`, `getUcUsageAttention` et `ucUsageAttentionFixture` — code mort côté
frontend, qui ne survit que par le mock de non-régression. À supprimer dans un commit dédié, ou
à assumer comme point d'entrée pour un futur usage : le choix reste à trancher, et sort du
périmètre d'un amendement de doc.

## Before PR

- [x] Rebased/merged latest develop before PR
- [x] Tests pass
- [x] No files outside package scope
- [x] Sub-spec checkboxes reviewed
- [x] Jira Story lists **Git branch** name (not a commit SHA)

## Notes

- **Contrat API** : [contracts/uc-usage-api.md](../contracts/uc-usage-api.md). **Entités et
  pièges d'affichage** : [data-model.md](../data-model.md). Contrat `include_deleted` gelé par
  la spec 027 :
  [027 · api-include-deleted.md](../../027-usage-table-deleted-flag/contracts/api-include-deleted.md).
- Composants réutilisés (D8 de [research.md](../research.md)) : `ComputeTabs`,
  `ComputeKpiCard`, `ComputeDataTable`, `ListPagination`, `ComputeEmptyState`, `Skeleton`,
  `recharts` pour les tendances, pattern drawer pour le drill-down.
- ⚠️ L'étape 8 dépend du **rejeu du pipeline `gold_dbx_usage`** avant la livraison du backend,
  dans chaque environnement : sans lui, les trois colonnes de cycle de vie n'existent pas et
  les 18 routes rendent un 500 brut. Contrainte détaillée dans les Notes de
  [T002](T002-uc-usage-api.md).
- Charger la skill `dcm-react` avant de coder, `dcm-verify` avant de cocher la task.
- `packages/dcm-frontend/package-lock.json` reste **hors commit** sur cette branche.
