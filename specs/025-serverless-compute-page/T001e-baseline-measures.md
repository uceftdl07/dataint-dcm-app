# T001e — mesures de référence prises AVANT l'implémentation

Mesuré le **2026-09-10**, profil OAuth `dcm-dev`, warehouse `DCM-metrics`, catalogue
`it.ba_data_connect_monitoring__d`. Toutes les requêtes sont générées en important **les vraies
expressions du code** (`serverless_scope_predicate()`, `serverless_surface_case_expr()`,
`identity_principal_expr()`, `tag_present_sql()` avec `OWNER_TAG_KEYS` / `COST_CENTER_TAG_KEYS`),
jamais retranscrites à la main — une première tentative de retranscription s'est trompée sur
4 produits du périmètre sur 10 et rendait 356 085,53 $ au lieu de 380 638,71 $.

**Chaque chiffre porte son cloud et sa fenêtre.** C'est la contrainte imposée par les trois
conflations de fenêtre déjà rencontrées dans cette spec (§10.1, §10.4, contrôle `OTHER` de
T001d).

## 0. Fenêtre à utiliser : 90 jours, pas 31, pas l'historique

Tranché par la convention en place et non par préférence :
`GOVERNANCE_ACTIVITY_WINDOW_DAYS = max(ROLLING_WINDOWS)` = **90 jours**, et
`cluster_governance` — la table sœur, même nature de snapshot — borne son périmètre avec cette
constante. `CLUSTER_GOVERNANCE_SPEC` porte `watermark_column=None`, `initial_mode="full"` et
`absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD`. T001e doit reprendre exactement ce
gabarit.

Ce que le choix de fenêtre change, mesuré sur le même périmètre serverless — c'est l'illustration
la plus nette du piège :

| Fenêtre | Coût bi-cloud | $ sans propriétaire | % sans propriétaire | Couverture policy |
|---|---:|---:|---:|---:|
| 31 j (2026-08-10 → 2026-09-09) | 380 638,71 $ | 8 704,20 $ | **2,29 %** | 12,54 % |
| **90 j (2026-06-12 → 2026-09-09)** | **1 036 222,34 $** | ≈ 22 800 $ | **2,2 %** | **13,4 %** |
| historique (2023-08-26 → 2026-09-09) | 3 687 894,38 $ | 266 421,06 $ | **7,22 %** | 9,98 % |

La part d'orphelins est **plus de 3× supérieure sur l'historique** : l'attribution d'identité
s'est nettement améliorée récemment. Publier 2,2 % comme « le » taux d'orphelins serait donc
juste pour un snapshot à 90 jours et faux comme constat général.

## 1. Référence T001e — 90 jours, par cloud

Périmètre : 1 036 222,34 $ (aws 767 022,09 + azure 269 200,25).

| Mesure | bi-cloud | aws | azure |
|---|---:|---:|---:|
| coût | **1 036 222,34 $** | 767 022,09 $ | 269 200,25 $ |
| `has_owner_tag` (`OWNER_TAG_KEYS`) | **3,1 %** | 4,0 % | **0,6 %** |
| `has_cost_center_tag` (`COST_CENTER_TAG_KEYS`) | **19,6 %** | 11,5 % | 42,8 % |
| couverture `budget_policy_id` | **13,4 %** | 7,6 % | 29,8 % |
| couverture identité | **97,8 %** | 97,9 % | 97,6 % |
| policies distinctes | 69 | 49 | 20 |

## 2. Référence T001e — 90 jours, par surface

| cloud | surface | coût | owner_tag | cc_tag | policy | identité |
|---|---|---:|---:|---:|---:|---:|
| aws | `SQL_WAREHOUSE` | 372 051,29 | 0,3 % | 6,4 % | **0,0 %** | 100 % |
| aws | `JOB` | 159 889,00 | 18,4 % | 34,9 % | 19,6 % | 100 % |
| aws | `NOTEBOOK` | 61 599,21 | 0,0 % | 12,3 % | 23,5 % | 100 % |
| aws | `APP` | 41 689,21 | 0,0 % | 1,1 % | 4,6 % | 100 % |
| aws | `AI_ENDPOINT` | 35 424,43 | 0,0 % | 0,0 % | 2,7 % | 99,6 % |
| aws | `GENIE` | 30 511,14 | 0,0 % | 0,0 % | **0,0 %** | 100 % |
| aws | `PLATFORM_AUTO` | 25 337,79 | 0,0 % | 0,0 % | 0,1 % | 100 % |
| aws | `DLT_PIPELINE` | 18 390,33 | 0,0 % | 0,0 % | **43,3 %** | 100 % |
| aws | `LAKEBASE` | 12 780,30 | 0,0 % | 0,5 % | 7,9 % | **5,5 %** |
| aws | `MV_ST_REFRESH` | 5 637,99 | 0,0 % | 8,3 % | 8,8 % | 100 % |
| aws | `NETWORKING` | 3 704,84 | 0,0 % | 0,0 % | 0,0 % | **0,0 %** |
| aws | `OTHER` | 6,56 | 0,0 % | 0,0 % | 0,0 % | 0,3 % |
| azure | `SQL_WAREHOUSE` | 86 154,39 | 1,4 % | 42,7 % | **0,0 %** | 100 % |
| azure | `JOB` | 73 746,24 | 0,1 % | 69,8 % | **67,2 %** | 100 % |
| azure | `APP` | 30 768,93 | 0,0 % | 23,8 % | 22,9 % | 100 % |
| azure | `DLT_PIPELINE` | 27 514,84 | 0,0 % | 17,5 % | 37,0 % | 100 % |
| azure | `AI_ENDPOINT` | 15 642,26 | 0,0 % | 39,9 % | 32,3 % | 96,8 % |
| azure | `NOTEBOOK` | 12 733,65 | 0,6 % | 40,5 % | 40,9 % | 100 % |
| azure | `PLATFORM_AUTO` | 10 245,13 | 2,4 % | 0,6 % | 0,4 % | 100 % |
| azure | `LAKEBASE` | 5 265,96 | 0,0 % | 53,6 % | 53,6 % | **0,1 %** |
| azure | `GENIE` | 5 141,37 | 0,0 % | 1,0 % | 0,0 % | 100 % |
| azure | `MV_ST_REFRESH` | 1 219,66 | 0,0 % | 38,8 % | 37,0 % | 100 % |
| azure | `NETWORKING` | 767,83 | 0,3 % | 0,0 % | 0,0 % | **0,0 %** |

Le levier de gouvernance le plus lourd est là, et il n'est pas dans la story :
**`SQL_WAREHOUSE` pèse 458 205,68 $ sur 90 jours (44 % du serverless) avec 0,0 % de couverture
`budget_policy_id` sur les deux clouds**, et 0 policy distincte. Aucune autre surface ne combine
ce poids et cette absence.

## 3. Les repères de la story sont mono-cloud — corrections

| Story | Mesuré | Diagnostic |
|---|---|---|
| couverture policy **8,4 %** « du serverless global » | **13,4 %** bi-cloud / 7,6 % aws, 90 j | mono-cloud aws, fenêtre non déclarée |
| **21 %** jobs | aws **19,6 %**, azure **67,2 %** | aws seul ; l'écart entre clouds est le fait marquant, pas la moyenne |
| **26 %** notebooks | aws **23,5 %**, azure 40,9 % | idem |
| **0,3 %** SQL | `SQL_WAREHOUSE` **0,0 %**, `MV_ST_REFRESH` 8,8 % / 37,0 % | **conflation de deux surfaces** : le produit `SQL` en porte deux, que T001d sépare précisément |
| identité **100 % partout sauf `LAKEBASE` (5 %) et `NETWORKING` (0 %)** | `LAKEBASE` 5,5 % aws / 0,1 % azure, `NETWORKING` 0,0 % — mais `AI_ENDPOINT` **99,6 % / 96,8 %** et `OTHER` 0,3 % | les deux exceptions citées sont exactes ; « 100 % partout ailleurs » ne l'est pas |
| $ sans propriétaire **5 875 $ (2,06 %)** | 8 704,20 $ (2,29 %) sur 31 j bi-cloud ; 266 421,06 $ (7,22 %) sur l'historique | aucune combinaison ne rend 5 875 $ ; à remplacer par une valeur datée et sourcée |
| « presque uniquement NETWORKING (100 % orphelin) et LAKEBASE (**81 %**) » | `LAKEBASE` est orphelin à **96,9 %** sur 31 j, et un **troisième** contributeur existe : `AI_ENDPOINT` 98,54 $ | composition à réénoncer |

## 4. Le piège des tags : la couverture booléenne est un faux signal

Mesuré sur la fenêtre de référence de 31 jours, par clé de tag :

- **azure : `Environment` est présent sur 103 966,54 $ / 103 966,54 $, soit 100,0 % de la
  dépense.** Une étiquette plateforme obligatoire, donc « part de $ portant au moins un tag » =
  **0,00 % de non-tagué** sur azure. Une matrice de couverture qui publie ça dit à FinOps qu'il
  n'y a rien à faire sur azure.
- **aws : 151 409,66 $ sur 1 318 975 lignes n'ont aucun tag** — 54,73 %. Il n'existe pas
  d'équivalent azure de l'étiquette obligatoire.

Alors que sur les clés **métier**, azure décroche vite : `AppName` 60,5 %, `BaID`/`AsID` 44,3 %,
`Project` 34,2 %, `AppCode` **12,4 %**. Et côté aws la meilleure clé normalisée est `project` à
**13,8 %**, tout le reste ≤ 12,2 %.

**Conclusion de conception** : ne jamais publier « `custom_tags` non vide ». Réutiliser
`sql_helpers.tag_present_sql` avec `OWNER_TAG_KEYS` / `COST_CENTER_TAG_KEYS`, comme
`cluster_governance` — c'est déjà la réponse du codebase, elle est insensible à la casse et
refuse une valeur vide.

Orthographes multiples réellement mesurées pour une même notion, ce qui fragmente toute métrique
par clé brute : `project` en 3 graphies aws (`PROJECT|Project|project`), `env` en 3
(`ENV|Env|env`), `owner` en 2, `AsID|AsId`, `BaID|BaId`, `Application|application`,
`Source|source`. Le décompte azure `environment` ressort même à **100,9 %** parce que certaines
lignes portent `Environment` **et** `environment`.

## 5. Décisions à prendre, avec la mesure qui les tranche

**5.1 `OWNER_TAG_KEYS = ("owner",)` est quasi aveugle sur le serverless : 3,1 %.**
Candidats mesurés : aws `CreatorEmail` 3,7 % et `CreateBy` 3,2 % — mais ce sont des tags
**injectés par Databricks**, les compter gonflerait une conformité que personne n'a choisie ;
azure `AppOwner` 5,3 % et `CyberContact` 5,3 % — ceux-là sont des tags TTE délibérés, cohérents
avec la famille `x_*` / `Ba*` / `As*`.
**Décision retenue pour T001e : ne pas toucher à la constante.** Elle est partagée avec
`cluster_governance` ; y ajouter une graphie changerait les chiffres de conformité **déjà
publiés** par cette autre table, ce qui sort du périmètre de T001e. La couverture est publiée
telle quelle (3,1 %) avec un commentaire de colonne qui nomme l'angle mort et les candidats.
À arbitrer par l'utilisateur, séparément.

**5.2 T001e lit les LIGNES DE FACTURATION, pas `serverless_cost_daily`.**
Mesuré : le coût sans propriétaire vaut **8 704,20 $** au niveau ligne contre **8 605,66 $** au
grain jour-objet de `serverless_cost_daily`, sur la même fenêtre de 31 jours. L'écart est
**98,54 $** et vaut exactement l'orphelin d'`AI_ENDPOINT` : au grain jour-objet, ses lignes sans
identité fusionnent avec des lignes qui en portent une, et le groupe entier hérite d'un
principal. Une table de gouvernance construite sur le daily **sous-estime** donc structurellement
les orphelins. La source est `curated_dbx_billing_usage` + `curated_dbx_billing_list_prices`,
comme T001d.

**5.3 L'inventaire des budget policies ne peut pas porter de NOM.**
Vérifié : `system.billing` n'expose que `account_prices`, `attributed_usage`, `list_prices`,
`usage` — **aucune table de budget policies**, et le catalogue curated n'en a pas non plus
(`dcm_retention_policies` est sans rapport). L'inventaire se limite donc à
`(policy_id, coût, surfaces couvertes)`. **T003 ne doit pas promettre un nom de policy.**
69 policies distinctes sur 90 jours (49 aws + 20 azure, aucun recoupement).

## 6. Contrôles que l'implémentation devra reproduire

1. coût bi-cloud 90 j = **1 036 222,34 $**, aws 767 022,09, azure 269 200,25
2. couverture policy bi-cloud = **13,4 %**, `SQL_WAREHOUSE` = **0,0 %** sur les deux clouds
3. couverture identité bi-cloud = **97,8 %** ; `NETWORKING` = 0,0 % ; `LAKEBASE` = 5,5 % aws /
   0,1 % azure
4. `has_owner_tag` bi-cloud = **3,1 %** ; `has_cost_center_tag` = **19,6 %**
5. les **12** surfaces de T001d sont toutes présentes côté aws ; azure en a **11** — la seule
   absente est `OTHER`, ce qui est cohérent avec T001d (`OTHER` ne contient sur azure que
   l'ancien `LAKEHOUSE_MONITORING`, désormais classé en `PLATFORM_AUTO`). Une table de
   gouvernance ne doit donc **pas** exiger 12 lignes par cloud
6. aucune clé de merge NULL — `serverless_surface` et `workspace_id` sont des clés de merge et
   `merge_into_table` fusionne sur `<=>` null-safe
7. la somme des surfaces par cloud = le total du cloud (partition, pas recouvrement)
