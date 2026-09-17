# Review report — T001e : `gold_dbx_compute_serverless_governance`

**Date** : 2026-09-10 · **Branche** : `spike/serverless_cluster` · **Base** : `develop`
**Task** : T001e (spec 025) — snapshot de gouvernance de la dépense serverless au grain
`(cloud_provider, workspace_id, serverless_surface)`
**Diff** : 7 fichiers, **+1 221 / −0** — 2 créés, 5 modifiés
**Implémentation** : déléguée à `dp-data-databricks-engineer` (domaine `dataeng`), relue ici,
**gates rejoués de ma main**, puis **déployée, exécutée deux fois et validée sur la table écrite**

## Gates — rejoués indépendamment, pas repris du rapport du subagent

| Gate | Résultat |
|---|---|
| `.venv/bin/python -m pytest -q` | ✅ **846 passed** (821 avant → **+25**, **0 retiré**) |
| `ruff check` sur les 6 fichiers Python touchés | ✅ **All checks passed!** |
| `mypy` sur les 3 fichiers de `pipelines/` touchés | ✅ **Success: no issues found in 3 source files** |
| `databricks bundle validate -t dev_local -p dcm-dev` | ✅ **Validation OK!** |

Arbitrage inchangé pour toute la spec : la dette préexistante du paquet (269 `ruff`, 10 `mypy`,
concentrés sur 3 modules DLT historiques et `forecast.py`, **aucun touché ici**) rend les gates
globaux aveugles ; la mesure qui compte est fichier par fichier sur le diff, et elle est verte.

## Validation sur donnée réelle — la table écrite, pas la requête

Exigence de l'utilisateur : *« pour la partie data à la fin d'une tâche déploie, teste et valide
la donnée »*. Faite **complètement** cette fois, y compris la moitié qui manquait à T001d au
moment de son premier rapport.

`databricks bundle deploy -t dev_local -p dcm-dev` → *Deployment complete!*
Puis **deux** runs one-off `databricks jobs submit` de la seule tâche `serverless_governance`
(`950980246657069` puis `481381739115826`, SUCCESS en ~1 min chacun). Le one-off contourne
`max_concurrent_runs: 1` sans rien annuler — route déjà éprouvée en T001d — et son payload est
**extrait de la spec de tâche réellement déployée**, pas retranscrit à la main.

### 1. Les 7 contrôles de la baseline §6, sur la table écrite

Bornes **lues dans la table** et non supposées (`window_start` / `window_end`), discipline adoptée
après le quasi-piège de conflation de fenêtre de T001d : `window_start` = **2026-06-12** (valeur
unique), `window_end` = **2026-09-09** (valeur unique), **1 316 lignes**. C'est exactement la
fenêtre de référence de la baseline, les chiffres sont donc directement comparables.

| # | Contrôle | Attendu (baseline §6) | Table écrite | ✅ |
|---|---|---|---|---|
| 1 | coût par cloud | 767 022,09 / 269 200,25 / **1 036 222,34** | **767 022,09 / 269 200,25 / 1 036 222,34** | ✅ au centime |
| 2 | couverture policy bi-cloud | 13,4 % | **13,4 %** | ✅ |
| 2b | `SQL_WAREHOUSE` policy, 2 clouds | 0,0 %, 0 policy | **aws 0,0 % / 0 · azure 0,0 % / 0** (372 051,29 + 86 154,39 $) | ✅ |
| 3 | couverture identité bi-cloud | 97,8 % | **97,8 %** (orphelins **22 464,37 $**) | ✅ |
| 3b | `NETWORKING` / `LAKEBASE` | 0,0 % ; 5,5 aws / 0,1 azure | **0,0 / 0,0** ; **5,5 aws / 0,1 azure** | ✅ |
| 4 | tags owner / cost center | 3,1 % / 19,6 % | **3,1 % / 19,6 %** | ✅ |
| 5 | surfaces par cloud | aws 12 / azure 11, `OTHER` absente azure | **aws 12 / azure 11**, `OTHER` = 6,56 $ **aws seul** | ✅ |
| 6 | clés de merge NULL | 0 | **0 / 0 / 0**, plus 0 `window_end` NULL et 0 `identity_source_mix` NULL | ✅ |
| 7 | partition par cloud | somme des surfaces = total | écart max **0,000000** | ✅ |

Contrôle bonus de la baseline, vérifié sur la donnée écrite : **90 lignes coûtent 0 $** et **0
d'entre elles** porte un pourcentage non NULL. La décision `NULLIF(cost_usd, 0)` n'est donc pas
cosmétique — sans elle, 6,8 % des lignes afficheraient « 0 % couvert » sur des surfaces qui n'ont
rien coûté (SKU `GENIE_FREE_USAGE`, DBU gratuits).

### 2. Cinq contrôles de l'inventaire de policies — que seule la table écrite permet

Le subagent avait validé l'inventaire sur la requête générée ; sur la **table**, il faut en plus
que le `array<struct>` survive à la sérialisation Delta et que son ordre soit stable.

| Contrôle | Résultat |
|---|---|
| policies distinctes reconstruites par explosion de l'inventaire | **49 aws / 20 azure** = les 69 du §1 de la baseline |
| distinctes bi-cloud | **69** → **aucun recoupement entre clouds**, ce que la baseline affirmait sans le prouver |
| tri décroissant effectif sur les lignes à ≥ 2 policies | **0 mal triée** sur 37 |
| `budget_policy_count` = `size(budget_policy_inventory)` | **0 écart** ; max 11 ; **0** ligne à `count = 0` avec inventaire non NULL |
| **somme des coûts de l'inventaire = `cost_usd_with_budget_policy`** | **0 ligne incohérente sur 1 316** |

Le dernier est le plus fort et il n'était **pas** dans le plan du subagent : il prouve que
l'inventaire et le numérateur de couverture sont calculés sur **les mêmes lignes de facturation**.
Un inventaire bâti sur un périmètre légèrement différent du numérateur passerait tous les autres
contrôles.

`identity_source_mix` prend des valeurs plausibles et lisibles : `RUN_AS` (731 lignes), `OWNED_BY`
(241), `NONE` (234), `CREATED_BY` (55), puis des ensembles mixtes en minorité
(`CREATED_BY+NONE+RUN_AS` 22…). Les 234 lignes à `NONE` seul sont les surfaces intégralement
orphelines — cohérent avec `NETWORKING` à 0,0 % de couverture d'identité.

### 3. Idempotence — le second run prouve ce que le premier ne peut pas

| Version Delta | Opération | out | insérées | mises à jour | **supprimées** |
|---|---|---:|---:|---:|---:|
| v0 (07:46) | `CREATE TABLE AS SELECT` | 1 316 | — | — | — |
| v21 (07:50) | **`MERGE`** | 1 316 | **0** | 1 316 | **0** |

La cible n'existait pas : le premier run la **crée** (ce que le rapport d'implémentation
annonçait), le second passe en MERGE. **0 insertion** (le grain est stable), **0 suppression** —
le `absent_row_delete_guard` du gabarit snapshot n'a rien supprimé à tort, le délai de grâce de
7 jours n'étant pas atteint et aucune ligne n'ayant disparu du recalcul.

Comparaison v0 vs v21 sur les **10 colonnes mesurées**, jointure sur les 3 clés de merge :

| lignes appariées | orphelines v0 | orphelines v21 | colonnes divergentes |
|---:|---:|---:|---:|
| **1 316** | **0** | **0** | **0** — coût, 4 numérateurs, `identity_source_mix`, `budget_policy_count`, **`budget_policy_inventory`**, `window_start`, `window_end` |

Idempotence parfaite, **struct d'inventaire compris**. Seul `_generated_at` bouge, ce qui est son
rôle et explique les 1 316 lignes « mises à jour » sans aucun changement de valeur.

## Revue de code

Le builder réutilise **8 helpers** de `sql_helpers.py` sans en réécrire un seul (`serverless_scope_predicate`,
`serverless_surface_case_expr`, `serverless_object_id_expr`, `SERVERLESS_OBJECT_ID_SENTINEL`,
`identity_principal_expr`, `identity_source_expr`, `tag_present_sql`, `lower_bound_predicate`) :
aucune divergence de périmètre possible avec les tables T001d, et c'est ce que le contrôle 7 —
égalité au centime avec `serverless_cost_daily` — mesure réellement.

Trois choix de conception sont justes et non évidents :

- **`priced` n'agrège pas.** C'est l'objet du §5.2 de la baseline : au grain jour-objet, des
  lignes sans identité fusionnent avec des lignes qui en portent une, et le groupe entier hérite
  d'un principal — 98,54 $ d'orphelins d'`AI_ENDPOINT` disparaissent ainsi. Une table de
  gouvernance bâtie sur la table quotidienne **sous-estimerait structurellement** les orphelins.
  Trois tests verrouillent l'absence de `GROUP BY` dans les CTE amont.
- **`policy_grain` avant `policy_inventory`.** Un `collect_list` appliqué directement à `priced`
  rendrait une entrée par ligne de facturation. `COUNT(*)` sur `policy_grain` **est** le
  `COUNT(DISTINCT budget_policy_id)`.
- **`measured_window` groupe par cloud.** Les deux clouds sont deux flux de collecte au retard
  distinct (3 à 8 jours) ; un `MAX(usage_date)` global masquerait le retard de l'un derrière
  l'avance de l'autre.

Campagne de mutation du subagent : **25 mutations, 25 tuées**, chacune une erreur plausible et non
un sabotage. Deux points de méthode que je retiens comme acquis de la spec : les assertions
négatives passent par un `_code_only()` qui retire les commentaires SQL (la requête générée *cite*
les constructions interdites, un `"X" not in query` serait satisfait par le commentaire qui
explique pourquoi X est faux) ; et deux mutations ont été **renforcées après un premier passage
trop facile**, dont une qui échouait sur un `NameError` et aurait compté un kill pour la mauvaise
raison.

## Ce que le subagent a corrigé de ma baseline — et il a raison

La baseline §0 annonçait **≈ 22 800 $** de dollars sans propriétaire sur 90 jours. La mesure donne
**22 464,37 $** (15 931,23 aws + 6 533,14 azure), confirmé ici sur la table écrite. Mon chiffre
était reconstruit **depuis un pourcentage déjà arrondi** (2,2 % × 1 036 222,34 = 22 797), alors que
22 464,37 / 1 036 222,34 = 2,168 % arrondit bien à 2,2 %. Le commentaire Unity Catalog porte la
valeur mesurée et sa répartition par cloud, pas la mienne. C'est la bonne décision : un
commentaire de colonne publié est lu comme une mesure.

Aucune des trois décisions du §5 de la baseline ne s'est révélée fausse à la mesure.

## Findings

| Niveau | Constat |
|---|---|
| 🟡 risk | **`run_as` absent du job**, donc exécution sous l'identité de qui déploie. Pré-existant, **transverse aux 8 jobs** du bundle, déjà signalé en T001d, non bloquant en `dev` mais **bloquant avant tout déploiement prod**. Demande un nom de service principal : décision utilisateur, pas un arbitrage d'implémentation. |
| 🟡 risk | Le contrôle 7 est annoncé « chemin de calcul indépendant » : à nuancer. Il emploie **la même jointure de prix** que `serverless_cost_daily`. Il prouve donc que le `CASE` de surface **partitionne** (ça, c'est indépendant — grain et agrégation différents) mais **pas** la jointure de prix elle-même, qu'aucun chemin disponible ne recoupe. À ne pas citer comme preuve du prix. |
| 🟢 note | `SQL_WAREHOUSE` = **458 205,68 $ sur 90 j (44 % du serverless), 0,0 % de couverture policy et 0 politique distincte sur les deux clouds**. C'est le levier FinOps le plus lourd de la page et il est **absent de la story** ; il est publié dans le commentaire de `budget_policy_coverage_pct` et dans la docstring, donc lisible sans relire cette revue. |
| 🟢 note | `OWNER_TAG_KEYS` couvre 3,1 % du serverless. Non touchée à dessein : la constante est partagée avec `cluster_governance` et y ajouter une graphie changerait des chiffres de conformité **déjà publiés**. Les candidats sont mesurés et nommés dans le commentaire (aws `CreatorEmail` 3,7 %, `CreateBy` 3,2 % — injectés par Databricks ; azure `AppOwner` 5,3 %, `CyberContact` 5,3 % — tags TTE délibérés). Arbitrage à porter séparément. |
| 🟢 note | `_surface_list_sql` reste dupliqué dans `serverless_cost_daily.py` (relevé en revue T001d). Non factorisé : ce builder n'en a pas besoin et toucher T001d dépasserait la task. |

## Checklist

| Point | Verdict |
|---|---|
| Aucun secret / credential | ✅ 0 correspondance sur le diff |
| PAT / DBFS / secret en clair | ✅ aucun — profil OAuth `dcm-dev`, wheel sur Workspace files |
| Périmètre ⊆ spec 025 / package `dataeng` | ✅ 7 fichiers, tous dans `packages/dcm-databricks-pipeline` |
| Tests pour tout changement de comportement | ✅ +25 tests, 25/25 mutations tuées |
| Critères d'acceptation couverts | ✅ les 7 contrôles de la baseline §6, sur la table écrite |
| Small PR | ✅ +1 221, un seul livrable |
| Données déployées, testées, validées | ✅ 2 runs, 17 contrôles, idempotence prouvée |
| `--no-verify` | non |
| Branche | ✅ `spike/serverless_cluster`, aucune branche créée |

**Verdict**: **PASS**
