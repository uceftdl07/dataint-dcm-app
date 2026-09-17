# T005 — Largeurs de colonne fixes et redimensionnables

**Domain**: frontend
**Package**: packages/dcm-frontend
**Branch**: `frontend/023-colonnes-et-filtres`
**Jira**: not dispatched (dispatch non exécuté sur cette feature)
**Depends on**: rien (aucune dépendance serveur — peut avancer pendant la vérification dev de T001/T002)
**Work type**: feature

## Description

Répond à la deuxième demande : « une taille fixe pour les colonnes avec possibilité pour
l'utilisateur d'augmenter ou de diminuer la taille ».

`ComputeDataTableColumn` n'a aujourd'hui que `align` et `className` : aucune largeur, donc la
géométrie de chaque tableau dépend du contenu de la page affichée et **change quand on tourne
la page**. Cette task ajoute une largeur déclarée par colonne, la rend effective par
`table-layout: fixed` + `<colgroup>`, et donne à l'utilisateur une poignée de
redimensionnement bornée, persistée et réinitialisable.

Périmètre : les **11 tableaux** pilotés par `ComputeDataTable`, soit **109 colonnes**, sur
les 5 pages arbitrées par le demandeur.

| Page | Tableaux | Colonnes |
|---|---|---|
| `ComputeClusters` | overview, cost, efficiency, governance | 9 + 8 + 18 + 6 |
| `ComputeSqlWarehouses` | overview, cost, query-performance, slow-queries | 7 + 7 + 9 + 9 |
| `LakeflowJobs` | jobs | 17 |
| `LakeflowJobDetail` | runs | 12 |
| `recommendations-table` | recommandations | 7 |

## Files to create/modify

- UPDATE `packages/dcm-frontend/src/components/domain/compute/compute-data-table.tsx`
- CREATE `packages/dcm-frontend/src/components/domain/compute/compute-column-resizer.tsx`
- CREATE `packages/dcm-frontend/src/hooks/useColumnWidths.ts`
- UPDATE `packages/dcm-frontend/src/pages/ComputeClusters.tsx`
- UPDATE `packages/dcm-frontend/src/pages/ComputeSqlWarehouses.tsx`
- UPDATE `packages/dcm-frontend/src/pages/LakeflowJobs.tsx`
- UPDATE `packages/dcm-frontend/src/pages/LakeflowJobDetail.tsx`
- UPDATE `packages/dcm-frontend/src/components/domain/compute/recommendations-table.tsx`
- CREATE `packages/dcm-frontend/src/components/domain/compute/__tests__/compute-data-table.test.tsx`
- CREATE `packages/dcm-frontend/src/hooks/__tests__/useColumnWidths.test.ts`

## Sub-tasks

- [x] **Tests d'abord** : `<colgroup>` rend une largeur par colonne ; glisser la poignée
      change la largeur **sans** déclencher le tri de la colonne ; la largeur est bornée par
      `minWidth`/`maxWidth` ; `←`/`→` déplacent de 16 px, `Home` réinitialise la colonne ;
      la valeur est relue de `localStorage` au remontage ; une clé de colonne inconnue est
      ignorée ; une valeur non numérique ou hors bornes est **écartée** au profit de la
      largeur déclarée ; `localStorage` indisponible ne fait pas échouer le rendu ; deux
      `tableId` différents ne partagent pas leurs largeurs.
- [x] `ComputeDataTableColumn<T>` : `width?: number`, `minWidth?: number`,
      `maxWidth?: number`, `resizable?: boolean` (défaut `true`).
- [x] Constantes `DEFAULT_COLUMN_WIDTH`, `MIN_COLUMN_WIDTH`, `MAX_COLUMN_WIDTH` — la valeur
      par défaut ne sert que de garde-fou : les 109 colonnes déclarent leur largeur.
- [x] Prop `tableId: string` **requis** sur `ComputeDataTable`. Requis et non optionnel :
      une valeur par défaut ferait silencieusement partager les largeurs entre la vue
      d'ensemble et l'onglet Coût. Dériver la clé de la route ou de la liste des ids de
      colonnes casse dès qu'une colonne est ajoutée.
- [x] `table-layout: fixed` + `<colgroup>` alimenté par les largeurs effectives. Conserver
      `minWidthClassName` : c'est lui qui garantit le défilement horizontal quand la somme
      des largeurs dépasse le conteneur.
- [x] `truncate` + `title` sur les cellules texte — contrepartie obligatoire de
      `table-layout: fixed`, sinon une valeur longue devient illisible sans recours.
- [x] `compute-column-resizer.tsx` : `role="separator"`, `aria-orientation="vertical"`,
      `aria-label` nommant la colonne, `tabIndex={0}`. `onPointerDown` capture le pointeur et
      **`stopPropagation`** — sans quoi un glissement déclenche le tri de la colonne.
      `onPointerMove` met à jour la largeur, `onPointerUp` persiste. Clavier :
      `ArrowLeft`/`ArrowRight` ±16 px, `Home` réinitialise.
- [x] `useColumnWidths.ts` : clé `dcm.table-widths.<tableId>`, valeur
      `{ [columnId]: number }`. Les 3 règles de lecture de
      [data-model.md](../data-model.md) §4. `try/catch` autour de chaque accès
      `localStorage` (mode privé, quota dépassé).
- [x] Bouton « Réinitialiser les largeurs » dans la zone `toolbar`, **affiché seulement**
      quand au moins une largeur diverge de la déclaration : un bouton toujours visible qui
      ne fait rien la plupart du temps est du bruit.
- [x] Déclarer une largeur sur les **109 colonnes** des 11 tableaux, ajustée au contenu réel
      de chacune (un `Δ %` n'a pas besoin de la largeur d'un nom de job).
- [x] Marquer `resizable: false` sur les colonnes d'action et de lien (`action`, `actions`,
      `open`) — rien à élargir.
- [ ] Vérifier visuellement les 11 tableaux : aucune colonne ne doit être tronquée au point
      de rendre sa valeur indéchiffrable à sa largeur par défaut ([research.md](../research.md) R8).
- [x] Gates : `npm run test`, `npx tsc --noEmit`, `npm run build`.

## Acceptance Criteria

- [x] **FR-006** : chacune des 109 colonnes a une largeur fixe déclarée, redimensionnable à
      la souris **et** au clavier, bornée, persistée et réinitialisable.
- [x] Redimensionner ne déclenche jamais le tri de la colonne.
- [x] Les largeurs survivent à un rechargement de page.
- [x] Deux tableaux de la même page **ne partagent pas** leurs largeurs (preuve que
      `tableId` sépare les clés).
- [x] Une largeur persistée invalide (non numérique, hors bornes) ou orpheline (colonne
      disparue) est ignorée sans casser le rendu ; `localStorage` indisponible non plus.
- [ ] Aucune colonne illisible à sa largeur par défaut sur les 11 tableaux.
- [x] La poignée est atteignable au `Tab`, annoncée comme `separator` avec le nom de sa
      colonne (P16).
- [x] Aucune donnée métier ni identifiant dans `localStorage` — seulement des largeurs en
      pixels (P7/P8).
- [x] Gates verts, aucune régression sur les 5 pages.

## Reste à faire — vérification navigateur

Les deux points non cochés ci-dessus sont les seuls : ils demandent un œil sur l'IHM, pas un
test. Ils sont mis en commun avec les 6 vérifications manuelles de
[quickstart.md](../quickstart.md) §5ter (T003/T005/T006), à passer en une session sur le dev.

## Ajout après revue navigateur — masquer le débordement, valeur complète au survol

Vu dans le navigateur : à largeur devenue fixe, un contenu plus large **sortait** de sa colonne
et recouvrait la voisine. Angle mort de la story ci-dessus, qui borne les largeurs sans dire ce
qu'il advient de ce qui ne rentre pas.

- [x] `overflow-hidden` sur chaque cellule de corps : dernier rempart, la largeur étant fixe.
- [x] Une enveloppe de contenu qui coupe le texte en points de suspension et pose un `title`
      avec la valeur complète — lu **après rendu** sur le DOM, la plupart des cellules rendant
      un composant dont le texte n'est pas dans `props.children`.
- [x] `title` aussi sur le libellé d'en-tête : coupé, il rend la colonne muette.
- [x] `truncate` sur **chaque ligne** des 5 cellules empilées (warehouse, cluster, workspace ×2,
      objet de recommandation) : les points de suspension d'un conteneur ne s'appliquent pas à
      ses enfants de type bloc.
- [x] Retirer les deux bornes en dur (`max-w-[240px]`, `max-w-xs`) qui contredisent une colonne
      redimensionnable, remplacées par `min-w-0`.
- [x] 4 tests, dont le remplacement du test qui figeait l'ancien comportement
      (`compute-data-table.test.tsx` → 18/18). Gates : tsc 101 (delta 0), lint 61 (delta 0),
      vitest 4 échecs pré-existants / 318 passés, build ✓.
- [ ] Confirmer à l'œil que la coupe reste lisible sur les 11 tableaux — même passe navigateur
      que les deux points ci-dessus.

Le titre de recommandation garde ses deux lignes (`line-clamp-2` + `whitespace-normal`) :
l'enveloppe impose un `nowrap` qui s'hérite, il faut le déclarer localement.

## Écarts par rapport à la déclaration de la story

- Les largeurs ne sont pas des littéraux par colonne : une échelle nommée
  `COLUMN_WIDTH` (`src/components/domain/compute/compute-column-widths.ts`, fichier non
  déclaré dans la liste ci-dessus) porte les 12 sortes de contenu des 109 colonnes. Un
  `width: 108` répété cinquante fois ne dit pas si deux colonnes partagent leur largeur par
  intention ou par hasard.
- Les tests sont **co-localisés** (`src/hooks/useColumnWidths.test.ts`,
  `src/components/domain/compute/compute-data-table.test.tsx`) et non sous `__tests__/`,
  comme le reste du paquet.
- `resizable: false` sur **3** colonnes d'action et non sur `action`/`actions`/`open` : c'est
  le décompte réel des colonnes purement gestuelles des 11 tableaux.
