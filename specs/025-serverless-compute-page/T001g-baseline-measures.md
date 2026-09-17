# T001g — mesures de référence prises AVANT l'implémentation

> ## 🚫 Périmètre de ce document après la décision du 2026-09-10
>
> Le volet **forecast** de T001g est **sorti du périmètre de la spec 025** — décision utilisateur du
> **2026-09-10**, prise après que ces mesures ont été faites et **avant** toute ligne de code. Rien
> n'a été implémenté, rien n'est à défaire.
>
> | Sections | Statut |
> |---|---|
> | §1, §2, §3, §4.1, §4.2, §5.1 à §5.6 | 🚫 **hors périmètre** — conservées, pas exécutées |
> | **§4.3 et §5.7** (`compute_kind_case_expr`) | ✅ **dans le périmètre**, c'est ce qui reste de T001g |
> | **§6** | ✅ mesures prises juste avant l'arrêt, conservées pour la spec de durcissement |
>
> **Ces mesures ne sont pas devenues sans valeur en devenant hors périmètre** — au contraire, c'est
> leur seul contenu réutilisable qui justifie de les garder : elles portent sur le mécanisme
> `ai_forecast` **déjà en production** sur 4 grains, et elles établissent qu'il publie **23,4 % de
> lignes NULL** et jusqu'à **2,49 × 10³⁸⁹ $** *sans lever la moindre erreur*. Le durcissement de
> `forecast.py` est donc à ouvrir comme **spec distincte**, et le §6 chiffre ce qu'il coûterait —
> ce n'est pas du nettoyage gratuit, d'où le refus de l'improviser ici.

Mesuré le **2026-09-10**, profil OAuth `dcm-dev`, warehouse `DCM-metrics`. Particularité de cette
task : `ai_forecast` a été **exécuté pour de vrai** sur la table
`gold_dbx_compute_serverless_cost_daily` écrite par T001d, avec la signature exacte du code
(`forecast.py` l. 229-250) — pas simulé, pas raisonné. Les chiffres ci-dessous sont ce que le
mécanisme rend réellement.

Fenêtre d'entraînement : 30 jours (`period_start >= current_date() - 30`), horizon
`2026-09-17` (= `today + FORECAST_HORIZON_DAYS`, 7 j), `prediction_interval_width => 0.95`,
`parameters => '{"global_floor": 0}'`.

Recoupement gratuit : le coût observé de la fenêtre vaut **368 058,50 $**, exactement la valeur
`window_days = 30` de `serverless_cost_rolling` validée le même jour. Les deux chemins concordent.

## 1. Le grain doit être la SURFACE, pas l'objet — mesuré

`serverless_cost_daily` a pour grain `(cloud, workspace, surface, object_id, jour)`. Le nom
`object_type = 'SERVERLESS_SURFACE'` imposé par la story implique que l'**objet du forecast est la
surface**, donc que `object_id` doit être **agrégé et disparaître**. Ce n'est pas qu'une question
de nommage — c'est la différence entre une série exploitable et une série dégénérée :

| Grain candidat | séries | à 1 point | < 7 points | points médians |
|---|---:|---:|---:|---:|
| `(cloud, workspace, surface)` | 1 117 | 107 (**9,6 %**) | 357 (32,0 %) | **16** |
| `(cloud, workspace, surface, object_id)` | 12 768 | 6 312 (**49,4 %**) | 9 020 (70,6 %) | **2** |

Au grain objet, **une série sur deux n'a qu'un seul point**. C'est exactement la raison pour
laquelle `forecast.py` exclut déjà les clusters `JOB`/`PIPELINE` du grain `CLUSTER`
(« la très grande majorité n'a qu'1 seul jour d'historique réel […] ce qui produit une série
dégénérée pour `ai_forecast` »). La même cause produirait le même effet ici.

**Décision : agrégation explicite par `(cloud_provider, workspace_id, serverless_surface,
period_start)` avant l'appel**, `object_key = concat_ws('::', cloud_provider, workspace_id,
serverless_surface)`. Les noms de surface ne contiennent pas `::`, la clé composite est donc
réversible par `_split_object_key_columns` sans changement.

**Et cette agrégation est obligatoire, pas seulement souhaitable.** Sans elle, `ai_forecast` reçoit
plusieurs lignes pour le même `(object_key, period_start)` et **ne lève aucune erreur** — c'est le
bug déjà rencontré et corrigé en T001b (926 jours-job avec deux points au même horodatage,
cf. `tasks.md`). Le test doit donc porter sur l'agrégation elle-même, pas sur le résultat.

## 2. `ai_forecast` sur séries dégénérées : ni erreur, ni refus — du NULL et des explosions

Résultat brut de l'appel au grain surface, sans aucun garde-fou, joint au nombre de points de
chaque série :

| longueur de série | séries | lignes NULL | max prédit | max observé/jour | verdict |
|---|---:|---:|---:|---:|---|
| 1 point | 107 | **2 378** (100 %) | — | 8,77 | **aucune prédiction** |
| 2 points | 57 | 0 | **2,49 × 10³⁸⁹** $ | 15,45 | **explosion** |
| 3 points | 41 | 0 | 2,50 × 10⁵⁰ $ | 73,16 | **explosion** |
| 4 points | 29 | 0 | 1 193 413,08 $ | 193,77 | aberrant |
| 5 points | 35 | 0 | 1,08 × 10¹⁵ $ | 44,03 | **explosion** |
| 6 points | 59 | 0 | 544 537 009,27 $ | 67,15 | aberrant |
| 7 points | 62 | 0 | 10 368,90 $ | 83,38 | aberrant |
| 14 points | 19 | 0 | **62 553 805,89 $** | 469,48 | aberrant |
| 21 points | 24 | 0 | 17 521 709,64 $ | 545,09 | aberrant |
| 25 points | 17 | 0 | 8 905 372,55 $ | 1 382,87 | aberrant |
| 30 points | **319** | 0 | 1 374,74 $ | 18 915,88 | plausible |

Total sans garde-fou : **10 160 lignes, 1 088 séries, 2 380 NULL (23,4 %)**, prédiction maximale
**2,49 × 10³⁸⁹ $** pour une surface qui a dépensé **15,45 $** en 30 jours.

Trois faits à retenir, aucun n'étant intuitif :

1. **Aucune erreur n'est levée.** Une série à 1 point rend des lignes avec `predicted_value` NULL.
   T001g livré sans garde-fou publierait 2 378 lignes NULL par run, silencieusement.
2. **`global_floor: 0` ne borne que par le bas.** Rien ne borne par le haut, et l'ajustement
   exponentiel sur 2 points part à 10³⁸⁹.
3. **29 séries sur 1 117 ne ressortent pas du tout** de l'appel (1 088 en sortie). `ai_forecast`
   en écarte silencieusement ; un contrôle de complétude entrée/sortie est donc nécessaire.

## 3. Un seuil de longueur ne suffit pas — et il est presque gratuit

Ce que coûte chaque seuil minimal de points, en couverture :

| seuil min. de points | séries retenues | % séries | coût observé couvert | **% coût couvert** |
|---:|---:|---:|---:|---:|
| 1 (aucun garde-fou) | 1 117 | 100,0 % | 368 058,50 $ | 100,00 % |
| 2 | 1 010 | 90,4 % | 367 973,43 $ | 99,98 % |
| 4 | 888 | 79,5 % | 367 531,33 $ | 99,86 % |
| **8** | **698** | **62,5 %** | **365 487,53 $** | **99,30 %** |
| 14 | 600 | 53,7 % | 362 225,62 $ | 98,42 % |
| 21 | 497 | 44,5 % | 354 236,71 $ | 96,24 % |
| 30 | 319 | 28,6 % | 297 792,56 $ | 80,91 % |

**Écarter 37,5 % des séries coûte 0,70 % de la couverture en dollars.** Les séries dégénérées ne
portent pas d'argent — c'est l'argument qui rend la décision facile, et il est mesuré. Un seuil de
**8 points** (supérieur à l'horizon de 7 jours : on ne projette pas plus loin qu'on n'observe)
retient 99,30 % du coût et supprime la totalité des NULL du bucket à 1 point ainsi que les
explosions à 2, 3 et 5 points.

**Mais il ne suffit pas.** Le même appel, restreint aux séries de ≥ 8 points :

| Mesure | Valeur |
|---|---:|
| lignes / séries | 5 370 / 698 |
| `predicted_value` NULL **restantes** | **2** |
| prédiction maximale | **62 553 805,89 $** |
| lignes > max journalier observé toutes surfaces (4 165,46 $) | 32 |
| lignes > 10 × ce max global (41 654,60 $) | 18 |
| **lignes > 10 × le max observé de LEUR PROPRE série** | **78 (1,45 %)** |

Un plafond **global** (`global_cap` dans `parameters`, mécanisme déjà utilisé par
`_PERCENTAGE_FORECAST_PARAMETERS` avec `global_cap: 100`) n'attraperait que **18** de ces 78
lignes : il est aveugle aux petites séries qui explosent vers une valeur absurde mais inférieure au
plafond global. La borne pertinente est **relative à la série**.

## 4. Décisions pour T001g

**4.1 Trois garde-fous, pas un.** Chacun couvre ce que les autres laissent passer :

1. **seuil minimal de 8 points** dans la fenêtre d'entraînement (> horizon de 7 j) — supprime le
   bucket NULL et les explosions à 2/3/5 points, coûte 0,70 % de couverture ;
2. **rejet explicite des `predicted_value` NULL** — il en reste **2** même à ≥ 8 points ;
3. **borne haute relative à la série** (prédiction > k × max observé de la série) — seule à
   attraper les 78 lignes aberrantes ; un `global_cap` scalaire n'en voit que 18.

Le facteur k reste à arbitrer ; k = 10 est mesuré ci-dessus et écarte 1,45 % des lignes.

**4.2 Contrôle de complétude entrée/sortie obligatoire.** 29 séries éligibles sur 1 117 ne
ressortent pas de l'appel sans qu'aucune erreur ne soit levée. Le builder doit comparer le nombre
de séries soumises au nombre de séries revenues.

**4.3 §10.2 (T9) : NE PAS basculer sur `product_features.is_serverless`.** La story annonce une
équivalence « parfaite » avec `cluster_id IS NULL` (51 748 / 11 869 lignes, 0 discordance, aucun
`is_serverless` NULL) et recommande la bascule en priorité basse. Re-mesuré sur **tout l'historique
et les deux clouds** — 2 033 499 lignes DLT, 2024-02-13 → 2026-09-09, soit **39×** le périmètre de
la story :

| cloud | lignes | `is_serverless` NULL | discordances | `cluster_id` NULL | `is_serverless` = true |
|---|---:|---:|---:|---:|---:|
| aws | 1 182 457 | **1** | **1** | 686 953 | 686 952 |
| azure | 851 042 | 0 | 0 | 850 514 | 850 514 |

L'équivalence n'est donc **pas** parfaite : il existe **1 discordance**, et c'est le champ
« officiel » qui se trompe.

```
cloud aws · 2026-07-31 · workspace 66097812060322
sku_name      = ENTERPRISE_JOBS_SERVERLESS_COMPUTE_EUROPE_FRANKFURT
cluster_id    = NULL      → l'expression actuelle rend SERVERLESS  ✅
is_serverless = NULL      → le champ proposé ne rend rien          ❌
usage         = 0,0006839 DBU
```

Le nom du SKU dit lui-même `SERVERLESS_COMPUTE`. `cluster_id IS NOT NULL` classe cette ligne
correctement ; `product_features.is_serverless` a un trou de donnée exactement là.

Conséquence de forme, à énoncer parce qu'elle décide de la gravité : écrite avec un `ELSE`
(discipline imposée par T001d — un `CASE` de clé ne doit jamais rendre NULL), la bascule ne
produirait pas une clé de merge NULL mais **une ligne serverless silencieusement étiquetée
`CLASSIC`**. Le montant est négligeable (0,0007 DBU), le mécanisme ne l'est pas : `compute_kind`
est une clé de merge du nouveau grain, et une erreur de classification y est invisible.

**Décision : conserver `cluster_id IS NOT NULL`.** Ajouter l'équivalence comme test de
non-régression, **avec cette exception documentée**, pour qu'un mainteneur futur ne « corrige » pas
l'expression vers le champ officiel en croyant l'améliorer. C'est la troisième fois dans cette spec
que le champ nommément officiel est moins fiable que le proxy structurel — même leçon que
l'errata `11 bis` du spike et que SC-010.

> **✅ Re-mesuré après implémentation, le 2026-09-10** — et le résultat est plus fort que celui du
> tableau ci-dessus, parce que la source a grossi entre-temps :
>
> | cloud | lignes DLT | `is_serverless` NULL | discordances | `cluster_id` NULL | `is_serverless` = true |
> |---|---:|---:|---:|---:|---:|
> | aws | **1 382 663** (+200 206) | **1** | **1** | 686 953 | 686 952 |
> | azure | **851 497** (+455) | 0 | **0** | 850 514 | 850 514 |
>
> **2 234 160 lignes** au total, **+200 661** depuis la mesure de conception, et **toujours 1 seule
> discordance** — le même enregistrement, à l'identique : aws, workspace 66097812060322,
> `ENTERPRISE_JOBS_SERVERLESS_COMPUTE_EUROPE_FRANKFURT`, `cluster_id` NULL, `is_serverless` NULL,
> 2026-07-31, 0,0006839 DBU. Ce n'est donc pas un artefact de fenêtre : la discordance est **stable
> sur 200 661 lignes supplémentaires**, et le trou du champ officiel ne s'est pas rebouché.
>
> Le test de non-régression est en place (`test_sql_helpers.py`, 4 fonctions / 5 cas) et sa
> **falsifiabilité est vérifiée** : la mutation vers `product_features.is_serverless` a été
> appliquée puis annulée, 5 tests neufs tombent, et le message porte la mesure. Le SQL rendu est
> inchangé (AST hors docstrings identique à HEAD) : **aucune donnée ne change**, donc rien à
> redéployer.

## 5. Contrôles que l'implémentation devra reproduire

1. l'agrégation avant `ai_forecast` est explicite : **0** couple `(object_key, period_start)` en
   double dans la série observée
2. **0** ligne publiée avec `predicted_value` NULL
3. **0** ligne publiée avec `predicted_value` > k × max observé de sa propre série
4. séries soumises = séries revenues (complétude entrée/sortie)
5. `object_type = 'SERVERLESS_SURFACE'` et `object_id` ∈ les 12 surfaces de T001d
6. les métriques projetées sont exactement `cost_usd` et `dbu_quantity` → **13** combinaisons
   (object_type, métrique) au total, contre 11 aujourd'hui
7. `compute_kind_case_expr` reste sur `cluster_id IS NOT NULL` ; le test d'équivalence documente
   la ligne aws du 2026-07-31 comme exception connue

---

# 6. Trois mesures prises juste avant l'arrêt — à reprendre par la spec de durcissement

Mesurées le **2026-09-10**, même profil et même warehouse, sur les **4 grains déjà en
production** (`JOB`, `CLUSTER`, `PIPELINE`, `WAREHOUSE`) et non plus sur la seule surface
serverless. Elles répondaient aux deux questions de conception laissées ouvertes au §4.1 (« le
facteur k reste à arbitrer ») et à la question implicite « ces garde-fous sont-ils généralisables
au forecast existant ». Les réponses valent indépendamment du retrait : ce sont des mesures du
mécanisme en place, pas de la fonctionnalité abandonnée.

## 6.1 Le seuil de 8 points ne se généralise pas — il coûte 9× plus cher sur JOB

C'est la mesure la plus importante du §6, parce qu'elle **contredit** la lecture rassurante du §3.
Le « 0,70 % de couverture » y était mesuré sur `SERVERLESS_SURFACE` seulement. Sur les grains
réellement en production :

| grain | séries | p50 des points d'historique | % de $ perdu par un seuil à 8 points |
|---|---:|---:|---:|
| SERVERLESS_SURFACE (§3, pour mémoire) | 1 117 | 16 | **0,70 %** |
| **JOB** | — | **1 jour** | **6,39 %** |
| **CLUSTER** | — | — | **6,26 %** |
| WAREHOUSE | — | — | 3,33 % |
| PIPELINE | — | — | 3,20 % |

**Le grain JOB a une médiane d'un seul jour d'historique.** Un seuil à 8 points y retirerait
**6,39 % des dollars projetés** — soit **9× le coût** mesuré sur la surface serverless. Le §3
concluait « la décision est facile parce qu'elle est presque gratuite » : cette conclusion est
vraie sur `SERVERLESS_SURFACE` et **fausse sur JOB et CLUSTER**. Durcir le forecast existant est
donc un **arbitrage de couverture**, pas un correctif de qualité — et c'est précisément le genre
de décision qu'on n'improvise pas en fin de task. Le retrait du périmètre est, sur ce point,
la bonne issue.

## 6.2 k = 10 est défendable sur la distribution, et le rapport est le bon indicateur

Le §4.1 laissait k « à arbitrer ». Distribution du rapport `predicted_value / max observé de la
propre série`, mesurée sur les séries de ≥ 8 points :

| percentile | rapport (dbu) | rapport (cost) |
|---|---:|---:|
| p50 | 0,38 | 0,40 |
| **p90** | **0,88** | 0,88 |
| p99 | 4,50 | **43,06** |
| max | **563 068** | 449 956 |

**Le p90 à 0,88 est le fait qui tranche** : une prédiction légitime est *inférieure* au maximum
déjà observé de sa série — 9 séries sur 10 le vérifient. Le rapport n'est donc pas un indicateur
bruité qu'on seuille arbitrairement : il est concentré sous 1, et sa queue est un signal franc.

Sensibilité de k, en lignes et séries écartées sur 10 740 lignes / 698 séries :

| k | lignes écartées | % | séries touchées |
|---:|---:|---:|---:|
| 3 | 184 | 1,71 % | 42 |
| 5 | 133 | 1,24 % | 33 |
| **10** | **96** | **0,89 %** | **25** |
| 20 | 80 | 0,74 % | 20 |

Le passage de k = 3 à k = 20 ne fait varier le rejet que de 1,71 % à 0,74 % : **le résultat est
insensible au choix exact de k**, ce qui est l'argument le plus solide en faveur d'un k rond.
k = 10 écarte 0,89 % des lignes, dont le maximum à 563 068 × le max de sa série.

## 6.3 Une borne *strictement* relative rejetterait de la poussière flottante

Défaut du garde-fou n°3 du §4.1, trouvé en le mesurant plutôt qu'en le raisonnant : **1 015
lignes** proviennent de séries dont le maximum observé est **0**. Pour elles, `k × max = 0`, donc
toute prédiction non nulle est « aberrante » — et **364** le sont formellement. Or la pire de ces
prédictions vaut **0,0 à six décimales** : ce n'est pas une explosion, c'est de la poussière
d'arrondi flottant.

Un plafond purement multiplicatif rejetterait donc 364 lignes inoffensives et masquerait son taux
de rejet réel. Il lui faut un **plancher additif**, et ce plancher doit venir de la donnée, pas
d'un choix : la plus petite valeur non nulle réellement observée est **1 × 10⁻⁶ $** et
**5,2 × 10⁻⁸ DBU**. La borne s'écrit donc `predicted > max(k × série_max, plancher)`.

> **Ce que le §6 change pour la suite.** Si la spec de durcissement est ouverte, elle hérite de
> trois résultats déjà payés : k = 10 est justifié par une distribution (§6.2), la borne relative
> a besoin d'un plancher mesuré (§6.3), et le seuil de longueur **ne peut pas** être appliqué
> uniformément aux 4 grains sans arbitrer 6,39 % des dollars sur JOB (§6.1). Le point §6.1 est
> celui à traiter en premier : il conditionne la forme de tous les autres.
