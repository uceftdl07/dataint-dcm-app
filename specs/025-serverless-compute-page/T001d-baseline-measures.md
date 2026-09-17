# T001d — mesures de référence, prises **avant** l'implémentation

**Date** : 2026-09-10 · **Environnement** : `dev_local`, catalogue `it`, schéma
`ba_data_connect_monitoring__d` · **Accès** : Statements API, profil OAuth `dcm-dev`,
warehouse `DCM-metrics`

But : disposer d'une référence indépendante pour **vérifier** le rapport
d'implémentation de T001d au lieu de le croire. Sur T001c, la revue a trouvé 7 affirmations
fausses dans le brief d'origine ; ces mesures-ci sont prises par une main différente de celle
qui écrit le code.

Le prédicat de périmètre utilisé est exactement celui de la story :

```sql
product_features.is_serverless = true
OR billing_origin_product IN ('GENIE','MODEL_SERVING','VECTOR_SEARCH','LAKEBASE',
                              'NETWORKING','AI_FUNCTIONS','AI_GATEWAY','LAKEFLOW_CONNECT',
                              'SUPERVISOR_AGENT','AGENT_EVALUATION')
```

**Preuve que ce prédicat est bien celui du spike** : il rend un total Azure de
**103 966,54 $** sur la fenêtre 2026-08-10 → 2026-09-09, là où la story annonce
« Azure ajoute ≈ 103 967 $/30 j de serverless ». Exact au dollar.

Coût calculé par jointure sur `curated_dbx_billing_list_prices`
(`cloud_provider`, `sku_name`, `price_start_time <= usage_date < price_end_time`,
`pricing.effective_list.default`) — `curated_dbx_billing_usage` **ne porte aucune colonne de
coût**.

## SC-003 — surfaces distinctes du `CASE`, fenêtre 2026-08-10 → 2026-09-09

**12 valeurs distinctes**, `OTHER` non vide. ✅ conforme à la story.

| `serverless_surface` | AWS lignes | AWS $ | Azure lignes | Azure $ |
|---|---:|---:|---:|---:|
| `AI_ENDPOINT` | 210 459 | 12 524,79 | 42 633 | 5 040,23 |
| `APP` | 18 728 | 11 106,35 | 23 447 | 11 648,01 |
| `DLT_PIPELINE` | 50 929 | 7 682,46 | 183 109 | 12 091,77 |
| `GENIE` | 97 973 | **14 870,36** | 30 120 | 3 527,12 |
| `JOB` | 282 745 | 58 806,64 | 218 674 | 29 598,31 |
| `LAKEBASE` | 101 409 | 4 240,97 | 45 294 | 2 034,25 |
| `MV_ST_REFRESH` | 29 576 | 1 940,28 | 14 239 | 438,53 |
| `NETWORKING` | 933 070 | 2 217,94 | 154 117 | 301,02 |
| `NOTEBOOK` | 46 856 | 20 684,43 | 11 892 | 5 250,43 |
| `OTHER` | 36 020 | **4,82** | — | **absent** |
| `PLATFORM_AUTO` | 152 751 | 8 217,63 | 74 315 | 2 954,96 |
| `SQL_WAREHOUSE` | 44 683 | 134 375,51 | 15 138 | 31 081,90 |

- `OTHER` = **4,82 $, AWS uniquement** — exactement la valeur annoncée. C'est le témoin qui
  rend visible l'apparition d'un produit Databricks nouveau ; il doit rester ≤ ~10 $ par cloud.
- **`GENIE` (14 870,36 $ AWS) pèse plus qu'`AI_ENDPOINT` entier (12 524,79 $ AWS)** : la raison
  de les garder séparés tient. La story cite 15 850 $ et 12 733 $ — l'ordre de grandeur et
  surtout **la relation** sont confirmés, les valeurs exactes diffèrent de ~6 % et ~2 %
  (probablement une variante de fenêtre ou de jointure prix côté spike).

## SC-004 — sentinelle `_NO_OBJECT`, même fenêtre

| Périmètre | `_NO_OBJECT` $ | total $ | part |
|---|---:|---:|---:|
| **AWS seul** | **26 281,05** | 276 672,18 | **9,50 %** |
| Azure seul | 7 144,52 | 103 966,54 | 6,87 % |
| **bi-cloud** | **33 425,57** | 380 638,72 | **8,78 %** |

Le « 26 533 $ (9,3 %) » de SC-004 est donc une mesure **AWS seule** — conforme à
l'avertissement de la story (« le spike est mono-cloud, DCM est bi-cloud »), à ~1 % près.
**Le critère doit être relu bi-cloud à 33 425,57 $ / 8,78 %**, sinon il échouera à tort.
En lignes : 1 531 218 `_NO_OBJECT` contre 1 286 959 avec clé — la sentinelle porte donc **plus
de la moitié des lignes** pour moins d'un dixième du coût, ce qui est cohérent avec
`NETWORKING` (1 087 187 lignes pour 2 518,96 $) et confirme que laisser cette clé à NULL
aurait fusionné une part massive de la table en lignes corrompues.

## Composition d'`OTHER` — vérifiée exhaustivement

Sur la fenêtre, `OTHER` ne contient **que** `LAKEFLOW_CONNECT` : 36 020 lignes, 4,82 $, AWS
uniquement. Aucun autre produit n'échappe au `CASE`. ✅

## Erreur trouvée dans la story, corrigée : `DATA_CLASSIFICATION`

La story affirmait que `DATA_CLASSIFICATION` « n'existe **que sur Azure** : 107,54 $ sur
1 workspace, absent des mesures AWS ». **Faux.** 107,54 $ est le total Azure de la **seule
fenêtre 30 jours** (90 lignes). Sur tout l'historique :

| cloud | lignes | workspaces | première | dernière | $ |
|---|---:|---:|---|---|---:|
| `aws` | 495 | 1 | 2025-11-24 | **2026-01-15** | **113,91** |
| `azure` | 648 | 1 | 2026-02-19 | 2026-09-08 | **582,32** |

Le produit existe **sur les deux clouds** et a simplement **cessé sur AWS en janvier 2026** — une
fenêtre de 30 jours mesurée en septembre ne peut pas le voir. Story corrigée. Ce constat
**renforce** la conception retenue : un produit peut apparaître sur un cloud, s'arrêter, puis
revenir, donc seule une **liste blanche** avec un `ELSE 'OTHER'` non vide et surveillé le rend
visible. Une liste noire l'aurait admis en silence à son retour.

## 2ᵉ erreur trouvée dans la story, corrigée : `budget_policy_id` n'est pas un « alias strict »

La story justifiait le choix de `budget_policy_id` par « alias strict vérifié null-safe sur
2 294 408 lignes ». C'est un **sur-ensemble strict**, pas un alias — et la vraie raison est
plus forte. Mesuré sur les **33 879 602** lignes de l'historique complet :

| Cas | Lignes |
|---|---:|
| `budget_policy_id` renseigné, `usage_policy_id` NULL | **188 744** (toutes entre 2025-02-10 et 2025-09-22) |
| `usage_policy_id` renseigné, `budget_policy_id` NULL | **0** |
| les deux renseignés mais **différents** | **0** |
| `budget_policy_id` non NULL / `usage_policy_id` non NULL | 3 427 925 / 3 239 181 |

`usage_policy_id` est donc la colonne **récente**, apparue vers septembre 2025. Les deux ne se
contredisent jamais, mais retenir `usage_policy_id` perdrait **silencieusement** l'attribution de
policy de 188 744 lignes sur février→septembre 2025. Le choix de la story est le bon ; sa
justification était fausse, et affaiblissait l'argument.

## `object_id` et `workspace_id` dans le grain — confirmé

`AI_ENDPOINT` sur tout l'historique : **932** `endpoint_id` distincts pour **939** couples
`(workspace_id, endpoint_id)`. La story cite 152 / 159 — figures de fenêtre 30 j, mais **la
relation est la même et c'est elle qui porte la décision** : `endpoint_id` n'est **pas**
globalement unique (7 collisions dans les deux mesures), donc `workspace_id` doit rester dans le
grain. ✅

## Reste à recouper dans le rapport de T001d

- que chaque figure publiée précise **cloud et fenêtre** — c'est la confusion exacte qui a fait
  réécrire §10.4 du spike deux fois, et celle des deux erreurs trouvées ci-dessus ;
- les percentiles $/run reconstruits depuis l'histogramme (SC-011 : p50 0,125 $ / p95 1,49 $ /
  p99 14,88 $ sur 98 207 runs) — non mesurés ici, à confronter.
