# T003 — Page SQL Warehouses par plage, nom et ordre alignés

**Domain**: frontend
**Package**: packages/dcm-frontend
**Branch**: `frontend/023-colonnes-et-filtres`
**Jira**: not dispatched (dispatch non exécuté sur cette feature)
**Depends on**: T002 (bloc `window`, `warehouse_name`, `cost_usd_prev_window`)
**Work type**: feature

## Description

Répond aux trois éléments de la première demande : filtre par période (1, 7, 30, 90 jours),
inversion de l'ordre Warehouse/Workspace, et affichage du **nom** du warehouse plutôt que de
son id.

Le sélecteur de plage réutilise **le même patron que `ComputeClusters.tsx`** (constante
`ROLLING_WINDOWS` l. 79-84, groupe de chips l. 865-892, libellé de période couverte
l. 888-891), pour que les deux pages compute se comportent identiquement — c'est
explicitement ce que la demande réclame (« comme les clusters »).

Le sélecteur de dates libre de l'en-tête **disparaît** de cette page : les vues de liste ne
l'honorent plus après T002, et laisser un contrôle sans effet est pire que de l'enlever.
Il reste actif sur l'onglet Requêtes lentes, qui garde le grain quotidien.
→ Voir « Écarts assumés » §1 : le contrôle est *route-scoped*, il n'a pas pu être retiré.

## Files to create/modify

- UPDATE `packages/dcm-frontend/src/pages/ComputeSqlWarehouses.tsx`
- UPDATE `packages/dcm-frontend/src/hooks/useComputeWarehousesQueries.ts`
- UPDATE `packages/dcm-frontend/src/hooks/query-keys.ts` *(non prévu — voir Notes)*
- UPDATE `packages/dcm-frontend/src/api/dcmApiClient.ts` *(non prévu — voir Notes)*
- UPDATE `packages/dcm-frontend/src/lib/compute/field-descriptions.ts` *(non prévu — voir Notes)*
- UPDATE `packages/dcm-frontend/src/types/api.ts`
- UPDATE `packages/dcm-frontend/src/test/fixtures/compute-warehouses.ts`
- UPDATE `packages/dcm-frontend/src/pages/ComputeSqlWarehouses.test.tsx`
  *(les tests de ce paquet sont colocalisés, pas dans un `__tests__/`)*

## Sub-tasks

- [x] **Tests d'abord** : les 4 chips sont rendues ; cliquer sur une chip envoie
      `window_days` dans la requête ; la plage survit à un changement d'onglet ; la période
      couverte affiche `from_date → to_date` **de la réponse** et non un calcul depuis
      `today` ; `from_date` à `null` affiche un état « aucune donnée » et non `Invalid Date` ;
      l'ordre des colonnes de la vue d'ensemble est Workspace puis Warehouse ; l'onglet
      Performance affiche un nom ; `cost_usd_prev_window` à `null` rend `—` et non `$0`.
      → 8 tests ajoutés, `ComputeSqlWarehouses.test.tsx` passe **16/16**.
- [x] `types/api.ts` : type `ComputeWarehouseWindowDays = 1 | 7 | 30 | 90`, bloc `window` sur
      les 3 réponses, `warehouse_name` sur `ComputeWarehouseQueryPerformanceItem`,
      `cost_usd_prev_window` remplaçant `cost_usd_prev_day` sur `ComputeWarehouseCostItem`.
      → alias sur les types clusters plutôt que deux unions jumelles libres de diverger ;
      `window_start`/`as_of_date` ajoutés ; scission `*Snapshot` (voir Écarts §2).
- [x] `useComputeWarehousesQueries.ts` : `window_days` en paramètre et **dans la clé de
      cache** React Query — sans quoi changer de plage rendrait la réponse de la plage
      précédente. → via un `ComputeWarehousesWindowQueryParams` + normaliseur dédié dans
      `query-keys.ts`, câblé sur les 3 clés d'un coup.
- [x] `ComputeSqlWarehouses.tsx` : `ROLLING_WINDOWS` + `useState<…WindowDays>(1)`, groupe de
      chips `role="group" aria-label="Rolling window"` avec les classes de `ComputeClusters`
      (`rounded-full border border-border bg-muted/30 p-0.5`). → markup identique au
      caractère près ; groupe masqué sur Requêtes lentes ; changer de plage remet les 3
      paginations à la page 1 (une autre plage est une autre population).
- [x] Vue d'ensemble : **inverser** les deux premières colonnes — `id: 'workspace'`
      passe avant `id: 'warehouse'`. Tri par défaut (`sort: 'cost'`) et colonnes triables
      inchangés : l'ordre d'affichage est indépendant de la clé de tri.
- [x] Onglet Performance : `<WarehouseCell name={row.warehouse_name} id={row.warehouse_id} />`
      — le `name={null}` littéral a disparu, y compris dans les deux titres de drawer.
- [x] Onglet Coût : en-tête `Δ vs prev day` → **`Δ vs prev window`**, champ lu
      `cost_usd_prev_window`, avec le coût de la fenêtre précédente en sous-ligne.
- [~] Retirer le sélecteur de dates libre de l'en-tête pour les 3 onglets concernés ; le
      conserver pour Requêtes lentes. → **impossible tel quel**, voir Écarts §1 : c'est la
      légende de plage *de la page* qui a été retirée des 3 onglets.
- [x] Mettre à jour le commentaire l. 240 (« Search, filters, sort and paging all happen
      server-side… ») pour mentionner la fenêtre.
- [x] Gates : `npm run test`, `npx tsc --noEmit`, `npm run build` — voir « Gates mesurés ».

## Écarts assumés

1. **Le sélecteur de dates de l'en-tête reste affiché.** Il est *route-scoped* :
   `showsGlobalHeaderTimePresets` ([routes.ts](../../../packages/dcm-frontend/src/lib/databricks/routes.ts))
   le rend vrai pour toute route `/databricks/*` sauf `/databricks/overview`. Or l'onglet est
   un état de page, pas une route, et l'onglet Requêtes lentes **de cette même route** a
   toujours besoin de la période libre — le contrôle ne peut donc pas être masqué par onglet.
   `ComputeClusters` (spec 022) n'a pas fait autrement : il a seulement cessé de *revendiquer*
   la plage. Fait ici de même — la description de page ne mentionne plus la période libre sur
   les 3 onglets à fenêtre, et la garde sur Requêtes lentes. Le retirer réellement demande de
   rendre `showsGlobalHeaderTimePresets` sensible à l'onglet : hors périmètre de T003.
   **Levé depuis** — voir la suite en fin de story : le contrôle a été retiré *par route* et
   non par onglet, et l'onglet Requêtes lentes porte désormais sa propre plage.
2. **Scission de type pour `/warehouses/{id}`.** La story demandait de remplacer
   `cost_usd_prev_day` par `cost_usd_prev_window` sur `ComputeWarehouseCostItem` — mais ce
   même type sert de `ComputeWarehouseDetailResponse.cost`, que le backend remplit par un
   `SELECT *` sur `warehouse_cost_daily` : ce endpoint porte bien un jour et sa comparaison
   jour/jour. Renommer le champ y aurait été un mensonge de type. Vérifié par grep qu'aucun
   consommateur UI ne lit `cost_usd_prev_day` et que le drawer ne lit que des champs communs
   aux deux formes, puis introduit `ComputeWarehouseCostSnapshot` et
   `ComputeWarehouseQueryPerformanceSnapshot` (`Omit<…> & {…}`) pour le détail quotidien.
3. **Libellé de fenêtre vide.** Les clusters rendent `'—'` ; l'AC demande un état
   « aucune donnée » qui ne soit pas `Invalid Date`. Retenu : `'no data over this range'`,
   explicite. Aucun `Date` n'est construit à partir d'une borne nulle, donc `Invalid Date` est
   structurellement impossible — le test le vérifie par assertion négative.
4. **Trois fichiers hors liste prévue** : `query-keys.ts` (le normaliseur de clé de cache,
   sans quoi la sous-tâche « dans la clé de cache » n'était pas tenable), `dcmApiClient.ts`
   (`window_days` sur les 3 types de params) et `field-descriptions.ts` (6 descriptions de
   champ + 3 de KPI qui décrivaient encore la période libre et les tables `*_daily` — les
   laisser aurait fait mentir les info-bulles).

## Gates mesurés

Jugés **en delta** contre le worktree de référence `/tmp/dcm-baseline` (même commande, même
machine), pas en absolu : la baseline n'est pas verte.

| Gate | Baseline | Après T003 | Delta |
|------|----------|------------|-------|
| `npx tsc --noEmit` | 101 erreurs | 101 erreurs | **0** — mêmes 4 erreurs warehouse, lignes décalées |
| `npm run test` | 4 échecs / 293 (`App`, `Databricks`, `Dashboard` ×2) | 4 échecs / 293, mêmes fichiers | **0** |
| `ComputeSqlWarehouses.test.tsx` | 8/8 | **16/16** | +8 tests |
| `npm run lint` | 61 (39 err, 22 warn) | 61 (39 err, 22 warn) | **0** |
| `npm run build` | ✓ | ✓ | — |

## Acceptance Criteria

- [x] **FR-001** : exactement 4 plages (`Daily`, `Last 7d`, `Last 30d`, `Last 90d`), aucune
      saisie de dates libre **dans le groupe de chips** sur les 3 onglets à fenêtre. Le
      sélecteur de l'en-tête subsiste — Écarts §1.
- [x] **FR-002** : la période couverte affichée provient de `window.from_date` /
      `window.to_date`, jamais d'un calcul depuis `today`. Test : la fixture annonce une
      fenêtre de 7 jours alors que la chip `Daily` est active, et c'est la fixture qui gagne.
- [x] La plage sélectionnée est conservée en changeant d'onglet.
- [x] **FR-005** : Workspace est la 1re colonne de la vue d'ensemble, Warehouse la 2e.
- [x] **FR-004** : les 3 onglets affichent le nom en libellé principal et l'id en secondaire
      monospace ; aucun `name={null}` en dur ne subsiste.
- [x] Un `warehouse_name` absent retombe sur l'id — pas de nom fabriqué (P9) :
      `WarehouseCell` rend `{name || id}`.
- [x] `cost_usd_prev_window` à `null` rend un tiret, pas `$0`.
- [x] L'onglet Requêtes lentes est **inchangé** : mêmes colonnes, même période libre, aucun
      `window_days` envoyé (assertion négative sur `listComputeWarehousesSlowQueries`). *La
      période libre a depuis été remplacée par des chips propres à l'onglet — suite ci-dessous ;
      l'assertion négative sur `window_days` tient toujours.*
- [x] Gates verts au sens delta, aucune régression sur les autres pages.

## Suite après demande utilisateur — retrait du sélecteur de dates de l'en-tête

« Pour les pages cluster, comme les résultats affichés sont toujours les plus récents, les
filtres date du haut n'ont pas d'utilité et peuvent rendre l'utilisateur confus. » L'écart §1
ci-dessus, pris à la racine : le contrôle est retiré **par route**, ce qui ne demandait pas de le
rendre sensible à l'onglet.

Prémisse vérifiée côté serveur avant tout retrait, parce qu'elle n'était vraie que sur une partie
des écrans : inertes (simplement renvoyées dans `period`) sur les 4 tableaux clusters et les 3
onglets warehouses à fenêtre ; **filtrantes** sur `fetch_warehouse_slow_queries`
(`CAST(start_time AS DATE) BETWEEN`), sur le détail et les courbes de tiroir (`_date_where`), sur
les recommandations (`last_seen_date >=`), la prévision (`horizon_date >=`) et lakeflow
(`_resolve_period` renvoie `"custom"` dès que les deux bornes arrivent, écrasant le preset nommé).
D'où deux pages seulement : `/databricks/cluster` et `/databricks/sql-warehouse` — Recommendations
et Workflows gardent leur bloc de dates, qui y filtre pour de vrai.

- [x] `showsGlobalHeaderDateRange` ajouté dans
      [routes.ts](../../../packages/dcm-frontend/src/lib/databricks/routes.ts) et
      `showsGlobalHeaderTimePresets` en dépend : les presets écrivent dans la même plage, seuls
      ils ne filtreraient rien. Le préfixe est comparé segment par segment, pour ne pas capter
      la route plurielle héritée `/databricks/clusters`.
- [x] `Header.tsx` : les deux `<label>` `Start date` / `End date` sous condition.
- [x] Les deux pages calculent leurs bornes elles-mêmes, ancrées sur aujourd'hui
      (`lastNDaysPeriodIso`) — masquer le contrôle en continuant de lire la plage globale aurait
      laissé une page voisine décaler ces écrans sans rien afficher qui l'explique. **365 jours**
      pour les lectures « dernière ligne dans la plage » du détail (un défaut de 30 jours
      masquerait un instantané en retard d'un mois), **90 jours** pour les courbes du tiroir.
- [x] Onglet Requêtes lentes : chips `Last 7d` / `Last 30d` / `Last 90d`, défaut **30 jours**
      (le comportement de l'ancien `defaultDays={30}`), retour page 1 au changement. Pas de chip
      `Daily` : ailleurs elle désigne le dernier instantané et n'est jamais vide, ici une seule
      journée de dates sur une table de statements en retard afficherait « aucune requête lente »
      pour « pas encore de données ».
- [x] Tests : `routes.test.ts` 24 → 31, `Header.test.tsx` 10 → 12,
      `ComputeSqlWarehouses.test.tsx` 17 → 19, `ComputeClusters.test.tsx` 20 → 21. Les bornes
      attendues sont recalculées dans les tests, sans passer par le helper de production.
- [x] Gates en delta contre `/tmp/dcm-baseline` : `tsc` 101 = 101, `lint` 61 = 61, `vitest`
      mêmes 4 échecs pré-existants / 340 passés, `npm run build` ✓. Piège rencontré : `.at(-1)`
      passe en vitest mais casse `tsc` (la `lib` du projet est antérieure à ES2022).
- [ ] Vérification navigateur : bloc de dates absent des 2 pages, présent sur Recommendations et
      Workflows, chips Slow queries fonctionnelles (mutualisée avec les 6 contrôles §5ter).
