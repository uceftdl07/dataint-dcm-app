# T006 — Combo de filtre dans l'en-tête de colonne

**Domain**: frontend
**Package**: packages/dcm-frontend
**Branch**: `frontend/023-colonnes-et-filtres`
**Jira**: not dispatched (dispatch non exécuté sur cette feature)
**Depends on**: T005 (géométrie de l'en-tête), T004 (`column_filter` + `filter-options`)
**Work type**: feature

## Description

Répond à la troisième demande : « ajouter des filtres par colonne avec des combo bar (liste,
recherche) ». Chaque colonne filtrable reçoit un entonnoir dans son en-tête, qui ouvre une
combo compacte : liste des valeurs du périmètre, champ de recherche, sélection unique.

`components/ui/combobox.tsx` n'est **pas réutilisable en l'état** — palette `slate`/`blue`
codée en dur au lieu des tokens de design, `w-full` + `px-4 py-3`, liste `max-h-60`, taillé
pour un formulaire et non pour un en-tête de tableau. Son **modèle d'interaction** est en
revanche celui à reprendre : champ de recherche, `role="combobox"` + `role="listbox"`,
`ArrowUp`/`ArrowDown`/`Enter`/`Escape`, fermeture au clic extérieur.

**T005 d'abord** : les deux tasks modifient la même cellule d'en-tête, où cohabitent déjà le
bouton de tri. Poser la géométrie puis y greffer l'entonnoir évite de réécrire deux fois le
même bloc et de faire se marcher dessus la poignée, le tri et le filtre.

## Files to create/modify

- UPDATE `packages/dcm-frontend/src/components/domain/compute/compute-data-table.tsx`
- CREATE `packages/dcm-frontend/src/components/domain/compute/compute-column-filter.tsx`
- CREATE `packages/dcm-frontend/src/hooks/useColumnFilterOptions.ts`
- UPDATE `packages/dcm-frontend/src/hooks/useComputeWarehousesQueries.ts`
- UPDATE `packages/dcm-frontend/src/hooks/useComputeClustersQueries.ts`
- UPDATE `packages/dcm-frontend/src/hooks/useLakeflowQueries.ts`
- UPDATE `packages/dcm-frontend/src/pages/ComputeClusters.tsx`
- UPDATE `packages/dcm-frontend/src/pages/ComputeSqlWarehouses.tsx`
- UPDATE `packages/dcm-frontend/src/pages/LakeflowJobs.tsx`
- UPDATE `packages/dcm-frontend/src/pages/LakeflowJobDetail.tsx`
- UPDATE `packages/dcm-frontend/src/components/domain/compute/recommendations-table.tsx`
- UPDATE `packages/dcm-frontend/src/types/api.ts`
- CREATE `packages/dcm-frontend/src/components/domain/compute/__tests__/compute-column-filter.test.tsx`
- UPDATE `packages/dcm-frontend/src/test/fixtures/` (fixture d'options de filtre)

## Sub-tasks

- [x] **Tests d'abord** : l'entonnoir n'apparaît que sur les colonnes filtrables ; il s'ouvre
      au clic et au clavier, se ferme par `Escape` et au clic extérieur ; les flèches
      parcourent la liste, `Enter` sélectionne ; saisir dans le champ de recherche déclenche
      une requête **debouncée** ; sélectionner une valeur remonte le filtre à la page et
      **ramène à la page 1** ; l'entonnoir d'une colonne filtrée est visuellement actif ;
      `truncated: true` affiche « affinez la recherche » ; ouvrir l'entonnoir ne déclenche pas
      le tri ni le redimensionnement ; `kind = "numeric"` liste les seuils du serveur ;
      « effacer tous les filtres » vide tout et revient page 1 ; le `<select>` de taille de la
      barre d'outils et la combo `size` restent synchronisés **dans les deux sens**.
- [x] `ComputeDataTableColumn<T>` : `filterKey?: string` (la clé de l'allowlist serveur ;
      absente = colonne non filtrable). Le composant ne devine **jamais** la clé depuis
      `id` — les deux coïncident souvent mais pas toujours, et une divergence silencieuse
      donnerait un 422 incompréhensible.
- [x] `ComputeDataTable` : props `filters?: Record<string, string>`,
      `onFiltersChange?`, `filterView?: string`. Le composant reste **sans état** sur les
      filtres : la page possède déjà les paramètres de requête et la pagination, dédoubler
      l'état ferait divergerer les deux.
- [x] `compute-column-filter.tsx` : entonnoir + popover ancré à la cellule d'en-tête, largeur
      indépendante de celle de la colonne (une colonne de 80 px doit pouvoir afficher une
      liste lisible). Tokens de design du repo (`border-border`, `bg-popover`,
      `text-foreground`) — pas de `slate`/`blue` en dur.
- [x] Accessibilité : `role="combobox"` + `aria-expanded` sur le déclencheur,
      `role="listbox"`/`option` + `aria-selected` sur la liste, `aria-label` nommant la
      colonne, focus rendu au déclencheur à la fermeture.
- [x] `useColumnFilterOptions.ts` : requête React Query sur `filter-options`, clé incluant
      `view` + `column` + le scope + `window_days` + `q`, `enabled` seulement quand le
      popover est **ouvert** (ne pas charger 88 listes au montage de la page), debounce du
      terme de recherche, `keepPreviousData` pour éviter le clignotement pendant la frappe.
- [x] `stopPropagation` sur l'ouverture : la cellule d'en-tête porte déjà le tri et la
      poignée de T005.
- [x] Hooks de page : sérialiser les filtres en `column_filter` **répétés**, les inclure dans
      la clé de cache, et remettre `page = 1` à chaque changement.
- [x] Lier le `<select>` de taille de la barre d'outils et la combo `size` au **même** état
      de page, dans les deux sens (décision R6).
- [x] Bouton « Effacer tous les filtres » dans la zone `toolbar`, affiché seulement quand au
      moins un filtre est actif, indiquant leur nombre.
- [x] Renseigner `filterKey` sur les **88 colonnes filtrables** des 11 tableaux, en accord
      strict avec [contracts/compute-column-filters.md](../contracts/compute-column-filters.md).
- [x] Gates : `npm run test`, `npx tsc --noEmit`, `npm run build`.

## Acceptance Criteria

- [x] **FR-007** : les 88 colonnes filtrables portent un entonnoir ouvrant une combo liste +
      recherche ; les 21 autres n'en portent pas.
- [ ] Le filtrage est **serveur** : le `total` et la pagination changent, et une ligne située
      au-delà de la première page est ramenée (SC-003 vu de l'IHM). ⏳ SC-003 est **atteint et
      mesuré côté serveur** (T004, ligne 51 → page 3 → `total = 1`) ; ce qui reste est de le
      voir dans le navigateur, avec les 6 contrôles de quickstart §5ter.
- [x] Tout changement de filtre ramène à la page 1.
- [x] Une colonne filtrée est visuellement identifiable sans ouvrir son popover.
- [x] Navigation clavier complète : ouverture, parcours, sélection, `Escape`, retour du focus.
- [x] Ouvrir l'entonnoir ne trie pas la colonne et ne la redimensionne pas.
- [x] Les listes ne sont chargées qu'à l'ouverture du popover — pas 88 requêtes au montage.
- [x] `truncated: true` est rendu explicitement (« affinez la recherche »), l'IHM ne fait pas
      croire à une liste complète.
- [x] Le `<select>` de taille et la combo `size` ne peuvent pas afficher des valeurs
      contradictoires.
- [x] Aucune valeur de filtre fabriquée côté front : les seuils numériques viennent du
      serveur (P9).
- [x] Gates verts, aucune régression sur les 5 pages.

## Reste à faire — vérification navigateur

Un seul critère non coché : voir SC-003 depuis l'IHM. Mutualisé avec les 6 contrôles manuels
de [quickstart.md](../quickstart.md) §5ter, communs à T003, T005 et T006.

## Écarts par rapport à la déclaration de la story

- Le fichier de hooks Lakeflow s'appelle `src/hooks/useLakeflowJobsData.ts` — il n'existe pas
  de `useLakeflowQueries.ts`. Les hooks warehouses/clusters n'ont pas été touchés : la
  sérialisation de `column_filter` est faite une fois pour toutes dans les hooks de liste, via
  `toColumnFilterParam` de `src/lib/compute/column-filters.ts` (fichier non déclaré dans la
  liste ci-dessus, créé par T004).
- Tests **co-localisés** : `src/components/domain/compute/compute-column-filter.test.tsx` et
  la vérification bidirectionnelle dans `src/pages/ComputeSqlWarehouses.test.tsx`, pas sous
  `__tests__/`. Pas de nouvelle fixture : la réponse d'options est construite dans le test,
  elle ne sert qu'à lui.
- Une **quatrième** prop de tableau au-delà des trois déclarées : `filterScope`
  (`{ windowDays?, workflowId? }`). Sans elle, la combo d'un tableau en fenêtre 90 jours
  listerait les valeurs du jour, et celle des runs listerait les statuts de tous les jobs.
- **Chaque page dérive ses paramètres historiques de l'état de filtres**, au lieu de garder un
  état séparé par contrôle de barre d'outils : `warehouse_size`, `utilization_status`,
  `sku_group`, `severity`, `category`, `status`, `min_failure_rate_pct`… sont lus dans le même
  objet que les combos écrivent. C'est la seule construction qui rend impossible un
  `warehouse_size=MEDIUM` accompagné d'un `column_filter=size:LARGE` — que le serveur refuse
  en 422. La synchronisation « dans les deux sens » demandée par R6 n'est donc pas un
  mécanisme de recopie : il n'y a qu'un état.
- Conséquence côté barre d'outils : cinq `<select>` (taille, latence p95, groupe SKU,
  sévérité, catégorie) rendent une `<option>` hors liste quand la valeur active ne figure pas
  dans leur liste codée en dur. La combo propose tout ce qui existe en gold, le `<select>`
  n'en connaît qu'une partie — sans cette option il afficherait « All … » alors qu'un filtre
  est actif.
- Les colonnes dont l'alias serveur attend une **liste** (`status`, `trigger_type` des deux
  pages Lakeflow) demandent une réécriture explicite : quand le paramètre de liste est
  présent, le backend **ignore** le prédicat mono-valeur, ce qui rendrait la combo inopérante.
  Les pages réécrivent donc la liste de statuts à la valeur choisie — et seulement quand elle
  diffère de celle déjà dérivée, sinon un filtre posé sur une autre colonne effacerait une
  sélection multi-statuts.
- `ComputeRecommendationsForecast` et `LakeflowJobs` gardent `category`/`severity`/`status`
  dans l'**URL** (liens partageables) et les recomposent avec les filtres locaux dans l'objet
  unique que voit le tableau.
- Le retour à la page 1 est porté par un `useEffect` sur l'état de filtres de chaque tableau,
  pas par le gestionnaire de changement : c'est ce qui couvre aussi les remises à zéro
  (changement d'onglet, « Effacer tous les filtres »).

## Vérification

- `npx tsc --noEmit` : 101 erreurs, **identique** au worktree de référence sur `HEAD`
  (`/tmp/dcm-baseline`) — delta 0.
- `npx vitest run` : **4 échecs / 315 réussis**, les 4 échecs étant ceux de la référence
  (`App.test.tsx` route paresseuse, `Dashboard` ×2, navigation du widget Databricks).
- `npm run build` : OK.
- `npm run lint` : **61 problèmes, delta 0** — mais seulement après correction. Un `npx eslint`
  fichier par fichier était propre alors que le lint complet donnait **63** : les deux problèmes
  venaient de fichiers **créés** par cette task, donc absents de la baseline et invisibles dans
  un diff. `options` non mémoïsé dans `compute-column-filter.tsx`
  (`react-hooks/exhaustive-deps`) et `_ignored` non utilisé dans `hooks/query-keys.ts` — la
  règle du projet ne reconnaît pas le préfixe `_`, d'où une copie suivie d'un `delete`.
- 109 `id` de colonne, 109 `width`, **88 `filterKey`** recomptés dans les 5 fichiers :
  conforme au récapitulatif de
  [contracts/compute-column-filters.md](../contracts/compute-column-filters.md).
