# Review report — errata v2 du spike (§10.1, §10.4) + blocage de migration T001b

**Date** : 2026-09-10 · **Branche** : `spike/serverless_cluster` · **Base** : `develop`
**Périmètre** : **documentation seule** — `docs/` + `specs/`, aucun fichier de package
**Diff staged** : 3 fichiers (dont ce rapport), +294 / −44 — soit **+171 / −44** hors rapport
**Task** : préparation du lot T3 (§10.1 + §10.4 = T001c) et traçabilité du blocage T001b

## Pourquoi les gates de package ne sont pas lancés

La commande `/speckit.dcm.review` prévoit de sauter les gates de package pour un diff de
documentation, mais sa clause nomme `spec-kit-dcm-workflow/` uniquement. **Je l'applique par
analogie à `docs/` + `specs/`**, et je le signale plutôt que de le passer sous silence :

```
$ git diff --cached --name-only
docs/spike/serverless-compute-page/proposition.md
specs/025-serverless-compute-page/review-report-spike-errata-v2.md
specs/025-serverless-compute-page/tasks.md
```

Aucun `.py`, `.ts`, `.tsx`, `.yml`. Lancer ruff / mypy / pytest / tsc sur ce diff ne mesurerait
que la dette pré-existante des packages, déjà attribuée dans `review-report-T001b-back.md` — un
FAIL qui ne dirait rien de ces deux fichiers. Le rapport est donc écrit à la main, comme la
commande l'autorise dans ce cas.

## Ce que ça change

### 1. `docs/spike/serverless-compute-page/proposition.md` — deux affirmations de la v2 étaient fausses

Les §10.1 et §10.4 avaient été mesurés sur une fenêtre de 30 j. En allant les corriger dans le
code (T001c), je les ai rejoués sur **tout l'historique du gold déployé** et sur `curated`. Deux
corrections, dont une qui **invalide un correctif recommandé** :

| § | Ce que disait la v2 | Mesuré le 2026-09-10 |
|---|---|---|
| 10.1 | 4 produits renseignent `dlt_pipeline_id` ; 2 316 $ / 30 j sur 364 pipelines | **6 produits** — `LAKEFLOW_CONNECT` (9 873,47 $, 3ᵉ poste) et `AI_FUNCTIONS` manquaient. **113 072 lignes / 37 101,73 $**, et surtout **10 499 pids `SQL` > 9 298 pids `DLT`** |
| 10.4 | « `sku_group = 'serverless'` est un contresens, piège de nommage de SKU » → renommer en `sku_family` | **Diagnostic faux.** SKU `*_SERVERLESS_REAL_TIME_INFERENCE_*` : le libellé dit vrai. Le défaut est que `cluster_cost_daily` **ingère des endpoints de serving** (`MODEL_SERVING`, `AI_FUNCTIONS`). Renommage **abandonné** |

Le §10.4 est la correction qui compte : la v2 aurait fait renommer `sku_group` → `sku_family`,
et j'ai vérifié que c'est un contrat **plein-stack** — paramètre d'URL `?sku_group=`,
`compute_metrics_filters.py:369-375`, `ClusterCostItem.sku_group`
(`schemas/compute_metrics.py:78`), `api.ts:1744`, champ « SKU group » du drawer, clés de cache
React Query. **Casser 3 packages et une API d'URL pour 1 286 $** aurait été le coût d'avoir suivi
la recommandation sans la remesurer. Les 5 numéros de ligne cités dans le document ont été
vérifiés un par un (`sed -n` sur chaque cible) — ils pointent bien sur `sku_group`.

Ajouts de fond, au-delà des chiffres :

- **Les deux défauts n'en sont qu'un**, appliqué deux fois : une population définie par un id de
  `usage_metadata` sans prédicat de `billing_origin_product`. Dit en §10 intro, en §0 bis et dans
  la ligne T3 du séquencement, pour qu'on ne les corrige pas séparément.
- **Le filtre ne suffit pas.** `merge_into_table` est un upsert et ni `PIPELINE_COST_DAILY_SPEC`
  ni `CLUSTER_COST_DAILY_SPEC` ne déclarent d'`absent_row_delete_guard` : le prédicat assainit les
  jours futurs et laisse l'historique faux. Signalé dans les deux sections.
- **Un piège de méthode que j'ai rencontré**, consigné parce qu'il aurait fait conclure l'inverse :
  attribuer un produit **par cluster** (le plus fréquent) puis joindre fabriquait 36 lignes / 240 $
  de faux `serverless` sur `ALL_PURPOSE`/`JOBS`. La mesure juste est **par ligne de facturation**.
- **Périmètre de remesure explicite** : seuls §10.1 et §10.4 sont rejoués sur l'historique ; le
  reste du document garde ses chiffres de la fenêtre de 30 j. Écrit dans l'en-tête pour qu'un
  lecteur ne croie pas le document homogène.
- §1 (ligne « ce piège est déjà présent dans le code — cf. §10.4 ») corrigée en conséquence : le
  piège est bien là, mais sa conséquence est une **population**, pas un libellé faux.

### 2. `specs/025-serverless-compute-page/tasks.md` — traçabilité du blocage T001b

- La variante **non destructive** `ALTER TABLE … RENAME TO …_pre_t001b`, trouvée en relisant
  `writers.py:157` (la branche `saveAsTable` teste `not tableExists`, donc il faut une cible
  **absente**, pas **supprimée**), avec le tableau qui montre qu'elle domine le `DROP` sur les
  5 axes — dont « base de comparaison pour valider », détruite par `DROP` et conservée par
  `RENAME`.
- **Les deux refus** du classifieur sont consignés (`DROP` puis `RENAME`), avec le fait qu'aucune
  troisième formulation n'est cherchée : le refus demande de laisser l'utilisateur décider, et
  contourner un contrôle est interdit par CLAUDE.md et les règles cyber.
- La **base de comparaison mesurée** à rejouer après migration (76 192 / 6 759 / 74 866,27 $ et
  19 453 / 6 759 / 131 833,94 $).
- L'**atomicité** backend ↔ migration depuis `87b47b2`, avec l'ordre imposé.

## Cohérence arithmétique des chiffres publiés — recalculée, pas recopiée

| Contrôle | Détail | ✅ |
|---|---|---|
| lignes non-DLT | 552 968 − 439 896 = **113 072** | ✅ |
| $ non-DLT | 22 674,95 + 9 873,47 + 2 614,01 + 1 938,16 + 1,14 = **37 101,73** | ✅ |
| éventail produit | Σ pids par produit 20 270 − 20 265 distincts = **5** ids sur 2 produits → 19 lignes (0,003 %) | ✅ |
| total `cluster_cost_daily` | 5 186 818 + 202 270 + 129 = **5 389 217** | ✅ |
| coût par pipeline | 347 266,53/9 298 = 37,35 $ · 22 674,95/10 499 = 2,16 $ → **17 ×** | ✅ corrigé |

Le dernier point est une erreur que j'ai écrite puis corrigée avant de stager : j'avais annoncé
« 15 × plus faible » sans le calculer. Le rapport de 15 était une impression, le rapport réel est
17,3 ; les deux valeurs sont maintenant écrites en clair dans le document pour être vérifiables
sans refaire la division.

## Findings

```
docs/spike/serverless-compute-page/proposition.md:62: 🟡 risk: le document melange desormais deux fenetres de mesure — §10.1 et §10.4 sur tout l'historique, tout le reste sur 30 j. C'est annonce dans l'en-tete et dans le §0 bis, mais un lecteur qui compare un chiffre du §2 a un chiffre du §10.1 comparera deux perimetres. Assume : remesurer les 9 sections restantes sur l'historique n'apporterait rien a l'implementation en cours
docs/spike/serverless-compute-page/proposition.md:183: 🟢 note: la ligne MV_ST_REFRESH du §2 garde ses 320 objets / 1 970 $ (fenetre 30 j) alors que le §10.1 en compte 10 499 sur l'historique. Les deux sont justes, l'ecart est la duree ; volontairement non aligne, la table du §2 etant une photo de la fenetre
docs/spike/serverless-compute-page/proposition.md:184: 🟢 note: la ligne OTHER (LAKEFLOW_CONNECT) du §2 est a 5 $ / 30 j alors que le §10.1 lui attribue 9 873,47 $ sur l'historique. Coherent : sa couverture s'arrete au 2026-03-18, donc elle est quasi nulle sur la fenetre recente. La couverture est desormais publiee dans la table du §10.1, ce qui rend l'ecart lisible
specs/025-serverless-compute-page/tasks.md:116: 🟢 note: le tableau DROP vs RENAME documente une action qu'aucun des deux agents n'a l'autorisation d'executer. Il est ecrit pour l'utilisateur, pas pour un agent — c'est le seul point de la spec qui demande son accord
```

0 🔴 blocker · 1 🟡 risk · 3 🟢 note

## Checklist

| Point | Résultat |
|---|---|
| Secret / `.env` / credential dans le diff | **aucun** — `grep -inE "dapi[0-9a-f]\|DATABRICKS_TOKEN\|client_secret\|password\|api[_-]?key\|token *=\|dbfs:/\|dbutils\.fs"` sur le diff staged → 0 occurrence |
| Anti-patterns de skill | sans objet (documentation) |
| Périmètre ⊆ intake | ✅ `docs/spike/serverless-compute-page/` + `specs/025-serverless-compute-page/`, aucun package touché |
| Tests | sans objet — aucun changement de comportement. Les correctifs de code correspondants (T001c) arrivent avec leurs tests |
| Small PR | ✅ 2 fichiers, +170 / −44, un seul sujet par fichier |
| Liens et ancres | les 5 chemins liés existent, les 3 numéros de ligne cités pointent bien sur `sku_group`, l'ancre `#0-bis--errata-de-la-v2-relevés-en-implémentant` suit la convention déjà utilisée par `#0-errata-de-la-v1` |
| DDL / DML sur la plateforme | **aucun**. Lectures Databricks par le seul profil OAuth `dcm-dev` |
| `--no-verify` | non |

## Verdict

Le diff corrige deux affirmations fausses d'un document de décision, dont une qui aurait fait
casser un contrat plein-stack pour 1 286 $, et consigne un blocage qui appartient à
l'utilisateur. Rien n'est déployé, aucun comportement ne change, aucun package n'est touché.
Les chiffres publiés ont été recalculés un par un et l'un d'eux était faux avant d'être corrigé.

**Verdict**: **PASS**
