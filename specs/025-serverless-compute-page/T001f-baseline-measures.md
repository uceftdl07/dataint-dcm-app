# T001f — mesures de référence prises AVANT l'implémentation

Mesuré le **2026-09-10**, profil OAuth `dcm-dev`, warehouse `DCM-metrics`, directement sur
`system.lakeflow.pipeline_update_timeline`. Chaque affirmation de la story a été **re-mesurée**
plutôt que reprise.

## 1. Forme réelle de la source — les chiffres de la story sont périmés d'un facteur 10

| Mesure | Story | Mesuré 2026-09-10 |
|---|---:|---:|
| lignes source | 43 464 | **421 849** |
| updates distincts | 41 817 | **412 038** |
| lignes / update | 1,04 | **1,02** |
| pipelines distincts | — | **13 210** |
| workspaces | — | **61** |
| couverture | — | **2025-09-08 → 2026-09-10** |

Le **ratio** de la story est confirmé, ses **volumes** non : la source a été mesurée à un autre
moment. La couverture s'arrête à ~1 an glissant — c'est la rétention des tables système, donc
l'ingestion T001f ne pourra **jamais** remonter avant `today - 365 j`, quelle que soit la fenêtre
demandée. À dire dans le `table_comment`, sinon un graphe « historique DLT » paraîtra tronqué sans
raison.

## 2. La requête d'agrégation imposée est sûre — prouvé, pas supposé

La story impose `MAX(compute.type)` et `MAX(result_state)` par update. Un `MAX` sur une colonne
qui aurait plusieurs valeurs distinctes dans le groupe choisirait silencieusement la plus grande
alphabétiquement — `'FAILED'` battrait `'COMPLETED'`, ou l'inverse selon les libellés. Mesuré sur
les 412 038 updates :

| Contrôle | Résultat |
|---|---:|
| updates avec **> 1** `compute.type` distinct | **0** |
| updates avec **> 1** `result_state` distinct | **0** |
| updates multi-lignes | 9 677 (**2,35 %**), max **12** lignes |
| `duration_sec` négative | **0** |
| `duration_sec` NULL | **0** |
| `duration_sec` = 0 | 248 (0,06 %) |

Les deux `MAX` sont donc des **choix dans un singleton**, pas des arbitrages. Ils sont sûrs, et un
test doit verrouiller ce constat parce qu'il tient à la donnée, pas à la syntaxe.

## 3. L'agrégation fait disparaître le NULL de `result_state` — argument mesuré

`result_state` est NULL sur **9 811 lignes / 421 849 (2,33 %)** — les tranches non terminales, ce
que la story annonce. Mais au grain `update_id`, **0 update sur 412 038** n'a pas de
`result_state`. Le taux d'échec ligne à ligne est donc faux d'un biais qui **s'annule
complètement** par l'agrégation. C'est la meilleure justification de la requête imposée, et elle
est chiffrée.

`compute.type` est NULL sur **0,00 %** des lignes. À comparer à `job_run_timeline`, dont la colonne
`compute_ids` — c'est son nom, pas `compute[]` — est vide ou NULL sur **97,0 %** des lignes
(6 465 894 / 6 668 570, mesuré le 2026-09-10) et **ne peut donc jamais servir de discriminant
serverless**. Le **88,5 %** que le spike publiait (`proposition.md:283`) n'est reproductible sur
aucun périmètre : 94–95 % sur toute fenêtre de 1 à 90 jours, et **95,3 % aws contre 59,3 % azure**
en curated — le taux **dépend du cloud**, ce qui suffit à disqualifier tout chiffre global sur une
page bi-cloud. Pour les pipelines, ce discriminant existe et il est fiable.

## 4. Le comparatif serverless / classique du bloc 3 — chiffres de référence

Par `compute_type` × `result_state`, au grain update. Les 6 lignes somment à **412 038**, soit
exactement le total : c'est une partition.

| compute_type | result_state | updates | p50 | p95 | moyenne | max |
|---|---|---:|---:|---:|---:|---:|
| `SERVERLESS_COMPUTE` | COMPLETED | 258 603 | **82 s** | 514 s | 209,1 s | 123,30 h |
| `SERVERLESS_COMPUTE` | FAILED | 78 731 | 164 s | 568 s | 271,8 s | 161,64 h |
| `SERVERLESS_COMPUTE` | CANCELED | 2 343 | 75 s | 779,9 s | 1 597,4 s | 166,02 h |
| `CLASSIC_COMPUTE` | COMPLETED | 63 503 | **695 s** | 2 932,8 s | 1 047,2 s | 7,11 h |
| `CLASSIC_COMPUTE` | FAILED | 8 313 | 402 s | 1 212 s | 1 219,5 s | 448,15 h |
| `CLASSIC_COMPUTE` | CANCELED | 545 | 262 s | **90 385,6 s** | 23 436,1 s | 269,87 h |

Trois conclusions, dont deux que la story ne porte pas :

**4.1 Le serverless est nettement plus rapide, à `COMPLETED` comparable** : p50 **82 s** contre
**695 s**, soit **8,5×**. Sur la moyenne l'écart tombe à 5,0× et sur p95 à 5,7× — d'où
l'obligation de publier un **percentile**, pas une moyenne.

**4.2 Mais le serverless échoue DEUX FOIS PLUS** : `FAILED` vaut **23,2 %** des updates
serverless (78 731 / 339 677) contre **11,5 %** des updates classiques (8 313 / 72 361). Une page
qui montrerait la seule durée dirait « migrez tout en serverless » en cachant ça. Le bloc 3 doit
porter les deux mesures côte à côte. (À nuancer honnêtement : un update qui échoue est réessayé,
donc un petit nombre de pipelines en boucle d'échec peut peser lourd dans le compte — le ratio
reste vrai, sa cause n'est pas établie ici.)

**4.3 Toute statistique de durée doit filtrer `result_state = 'COMPLETED'`.** La queue longue vit
dans `CANCELED` : `CLASSIC_COMPUTE / CANCELED` a un p95 de **90 385,6 s (25 h)** et une moyenne de
**6,5 h**, contre 695 s de médiane pour un classique terminé. Mélanger les états ferait dominer la
moyenne par des updates abandonnés. Le maximum absolu de 448,15 h est un `CLASSIC_COMPUTE /
FAILED`, pas un traitement normal.

## 5. Contrôles que l'implémentation devra reproduire

1. lignes source **421 849** → updates **412 038** (le `COUNT(*)` de la source surestime les
   updates de **2,4 %** ; ne jamais compter la source)
2. `compute_type` ∈ {`SERVERLESS_COMPUTE`, `CLASSIC_COMPUTE`}, **0 NULL**, **0 update ambigu**
3. `result_state` ∈ {`COMPLETED`, `FAILED`, `CANCELED`}, **0 update sans état** après agrégation
4. `duration_sec` : 0 négative, 0 NULL, 248 à zéro
5. la somme des 6 couples `(compute_type, result_state)` = **412 038** (partition)
6. p50 des `COMPLETED` : serverless **82 s**, classique **695 s**
7. taux d'échec : serverless **23,2 %**, classique **11,5 %** — **mais lire le §7 avant de publier
   ce chiffre**

---

# Addendum du 2026-09-10 — mesures prises AVANT l'implémentation, second passage

Le premier passage ci-dessus a été pris sur les colonnes que la story nomme. Le `DESCRIBE` de la
source en expose **16**, dont deux que ni la story ni le §1 ne mentionnent et qui changent le
livrable. Volumes re-mesurés quelques heures plus tard : **422 143 lignes / 412 328 updates** contre
421 849 / 412 038 au premier passage — la source est vivante, l'écart de 294 lignes est de
l'alimentation normale, pas une contradiction. Les ratios sont identiques (surestimation **2,38 %**
contre 2,4 %).

## 6. La forme réelle de la source interdit d'agréger à l'ingestion

`IngestionSpec` ne connaît que `select_columns` (projection) et `row_filter` — **rien qui agrège**.
`ingest.py` s'annonce « Fidele source (no transform, no join) » et « Le corps est generique : la spec
porte toute la difference entre tables ». Y ajouter un `GROUP BY` obligerait à l'écrire **deux
fois** : `read_native_source` construit un DataFrame (AWS), `build_azure_query` une chaîne SQL
(Azure).

Et surtout, agréger dans une ingestion **incrémentale** corrompt la donnée. `DEFAULT_LOOKBACK_DAYS
= 3` (`pipelines/common/incremental.py:29`) :

| Contrôle | Mesuré |
|---|---:|
| updates chevauchant ≥ 2 jours calendaires | **427** (0,104 %) |
| dont multi-lignes | **184**, portant **3 065,2 h** de durée cumulée |
| updates étalés sur **≥ 4 jours** (donc au-delà du lookback de 3 j) | **40** |
| étalement maximum d'un update | **19 jours** |

Pour ces updates, un agrégat calculé sur la fenêtre de lecture reçoit un `MIN(period_start_time)`
**tronqué**, et le MERGE sur `update_id` écrase une ligne correcte par une ligne plus courte. Ce
sont exactement les updates longs, ceux dont la durée porte l'information d'une page d'efficience.

Troisième argument, indépendant : **le backend ne lit aucune table `curated_*`**
(`grep -roE 'curated_dbx_[a-z_]+|gold_dbx_[a-z_]+' packages/dcm-backend/app` → **0** contre ~30
`gold_*`). Faire consommer une table curated directement par T002 serait la première entorse au
découpage en couches de l'application.

**Décision** : ingestion **fidèle** au grain horaire, calquée sur ses deux jumelles
(`watermark_column = "period_start_time"`, pas de partitionnement faute de colonne DATE native), et
agrégation au grain `update_id` dans un **builder gold**. FR-015 demandait « jamais une ligne par
tranche » dans ce que la page consomme : c'est respecté, la table est simplement dans la couche où
vivent les transformations.

## 7. ⚠️ Le « le serverless échoue deux fois plus » du §4.2 est un artefact de comptage des retries

Le §4.2 posait la réserve honnête : « *un update qui échoue est réessayé, donc un petit nombre de
pipelines en boucle d'échec peut peser lourd dans le compte — le ratio reste vrai, sa cause n'est
pas établie ici* ». La colonne **`request_id`** de la source l'établit : sa description officielle
est « *Helps to understand how many times an update had to be retried/restarted* ». **412 328 updates
pour 347 668 `request_id` distincts** (ratio **1,186**, **0 NULL**).

| Taux d'échec | par `update_id` | **par `request_id`** (≥ 1 tentative en échec) | updates | requests |
|---|---:|---:|---:|---:|
| `SERVERLESS_COMPUTE` | **23,16 %** | **7,37 %** | 339 941 | 280 164 |
| `CLASSIC_COMPUTE` | **11,52 %** | **5,77 %** | 72 387 | 67 504 |
| **ratio serverless / classique** | **2,01×** | **1,28×** | | |

La colonne « par update » **reproduit le §4.2 exactement** (23,2 / 11,5) : ce n'était pas une erreur
de mesure, c'était une erreur de **dénominateur**. Une fois les tentatives d'un même
`request_id` regroupées, l'écart tombe de 2,01× à **1,28×**. Le mécanisme est visible en clair dans
la source : `RETRY_ON_FAILURE` est un `trigger_type` à part entière et vaut **63 155 updates
(15,3 %)**.

> **Deux réserves ajoutées le 2026-09-10 après revérification — lire le §10.6 avant de publier quoi
> que ce soit de ce tableau.** (1) La colonne « par `request_id` » ci-dessus compte une requête en
> échec dès qu'**une** tentative a échoué ; en retenant l'état de la **dernière** tentative — la
> définition que sert le builder gold, car une requête qui réussit à la reprise n'est pas un échec —
> elle vaut **7,03 % / 5,19 %** (ratio 1,35×). Les deux chiffres sont exacts, ils répondent à deux
> questions. (2) Ce tableau porte sur l'**historique complet** : sur 30 jours, **le rapport
> s'inverse**. Le §7 corrigeait le dénominateur ; il lui manquait la fenêtre, qui décide du *sens*.

Et la concentration achève l'argument : sur **87 070** updates `FAILED`, **57 045 — soit 65,5 % —
viennent des 10 pires pipelines**, sur 2 126 pipelines ayant au moins un échec. Un taux d'échec
global publié sans cette réserve présenterait le comportement de **dix pipelines** comme une
propriété de la plateforme.

**Conséquence pour l'implémentation** : la table gold doit porter `request_id` et `trigger_type`,
et le commentaire Unity Catalog du taux d'échec doit dire lequel des deux dénominateurs il emploie.
Publier « 23,2 % » sans cela est un chiffre juste qui répond à la mauvaise question.

## 8. Trois colonnes de plus, mesurées

| Colonne | Couverture | Valeurs |
|---|---|---|
| `trigger_type` × `update_type` | 8 couples | `JOB_TASK/REFRESH` 290 320 · **`RETRY_ON_FAILURE/REFRESH` 63 155** · `DBSQL_REQUEST/REFRESH` 25 538 · `JOB_TASK/FULL_REFRESH` 17 969 · `USER_ACTION/REFRESH` 6 899 · `USER_ACTION/FULL_REFRESH` 3 853 · `USER_ACTION/VALIDATE` 1 580 · `SCHEMA_CHANGE/REFRESH` 748 |
| `trigger_details.job_task.performance_target` | **NULL sur 50,2 %** (207 055 / 412 328) | `PERFORMANCE_OPTIMIZED` 180 993 · `STANDARD` 24 280 |
| `run_as_user_name` | **99,1 %** non NULL | **186** valeurs distinctes |

`performance_target` existe donc **aussi** ici, mais à moitié seulement — à ne pas substituer à la
source de T002 sans dire cette couverture. `run_as_user_name` à 99,1 % est un signal de propriété
d'une qualité très supérieure aux 3,1 % de `OWNER_TAG_KEYS` sur la dépense serverless (T001e), mais
les deux ne sont **pas** comparables : population différente (updates DLT contre lignes de
facturation serverless) et grain différent. À ne pas invoquer comme argument dans l'arbitrage
`OWNER_TAG_KEYS`.

## 9. Contrôles que l'implémentation devra reproduire — liste révisée

Les 7 du §5 restent, avec le n°7 requalifié, plus :

8. `422 143` lignes source → `412 328` updates ; **0** update à > 1 `compute.type` distinct, **0** à
   > 1 `result_state` distinct (les deux `MAX` sont des choix dans un singleton)
9. les 6 couples `(compute_type, result_state)` somment à **412 328** : SERVERLESS
   COMPLETED 258 865 / FAILED 78 733 / CANCELED 2 343 ; CLASSIC COMPLETED 63 505 / FAILED 8 337 /
   CANCELED 545
10. `request_id` : **0 NULL**, **347 668** distincts, ratio update/request **1,186**
11. taux d'échec **par `request_id`** : serverless **7,37 %**, classique **5,77 %**

---

## 10. Structure fine de la source — quatre faits qui fixent la règle d'agrégation, et un qui inverse une conclusion

Mesuré le 2026-09-10, troisième passage (`/tmp/val_t001f_state.sql`), sur **412 350 updates /
422 167 lignes**. Le §2 établissait déjà que les deux `MAX` sont des choix dans un singleton ; ce
qui suit le **précise** et ne le contredit pas. Écarts de volume (412 038 → 412 350) = quelques
heures d'alimentation.

### 10.1 L'état terminal est sur exactement une ligne — démontré, pas observé

| Mesure | Valeur |
|---|---:|
| lignes totales | 422 167 |
| updates | 412 350 |
| lignes à `result_state IS NULL` | **9 817** |
| updates dont **toutes** les lignes sont NULL | **0** |
| updates à > 1 `result_state` non-NULL | **0** |
| répartition des lignes brutes | `COMPLETED` 322 387 · `FAILED` 87 075 · NULL 9 817 · `CANCELED` 2 888 |

L'identité **422 167 = 412 350 + 9 817** n'est pas une coïncidence, et elle se démontre : chaque
update a **au moins** une ligne non-NULL (ligne 4 du tableau), donc les lignes non-NULL sont ≥
412 350 ; or elles valent 422 167 − 9 817 = **412 350 exactement**. Donc **chaque update porte
exactement une ligne non-NULL**, et les lignes excédentaires sont *précisément* les tranches
intermédiaires à NULL.

Deux conséquences opérationnelles :

- `MAX(result_state)` est **exact** et suffit : il ignore les NULL et il n'y a qu'une valeur à
  rendre. Inutile d'écrire un `row_number() OVER (ORDER BY period_start_time DESC)` — plus coûteux,
  rien de plus. À commenter dans le code comme vrai **par mesure et non par contrat** : si deux
  états non-NULL coexistaient un jour, le `MAX` trancherait par ordre alphabétique en silence.
- **Le piège du `COUNT(*)` de la curated n'est pas celui qu'on croit.** Comme `FAILED` n'occupe
  qu'une ligne par update, un *taux* d'échec calculé ligne à ligne n'est presque pas faussé
  (87 075/422 167 = 20,6 % contre 87 075/412 350 = 21,1 %). Ce que les 9 817 lignes en trop
  faussent, c'est le **compte d'updates** (+2,4 %) et la **durée**, qui se double-compte. Le §7
  reste le vrai piège de dénominateur ; celui-ci est un piège de volumétrie.

### 10.2 Les deux définitions de durée concordent à la seconde

Sur les **9 683** updates multi-tranches, `MAX(period_end_time) − MIN(period_start_time)` comparé à
la somme des tranches horaires : écart **médian 0,0 s**, **p95 0,0 s**, **0** update au-delà de
60 s. Les tranches **pavent l'intervalle sans trou ni recouvrement**.

Donc la définition horloge est sûre, et c'est celle à retenir — la plus simple à expliquer dans une
IHM. Ce n'était pas acquis : une source à tranches trouées aurait rendu les deux définitions
divergentes, et le choix aurait été un arbitrage métier de plus.

### 10.3 `update_id` est globalement unique — la clé de merge du gold doit en tenir compte

| Décompte distinct | Valeur |
|---|---:|
| `update_id` | **412 350** |
| triplets `(workspace_id, pipeline_id, update_id)` | **412 350** |
| couples `(workspace_id, update_id)` | **412 350** |

`workspace_id` et `pipeline_id` n'ajoutent donc **aucun pouvoir discriminant** à la clé — seulement
un mode de panne. Un MERGE du gold sur le 4-uplet `(cloud_provider, workspace_id, pipeline_id,
update_id)` **insérerait un doublon** au lieu de mettre à jour si le `pipeline_id` associé à un
`update_id` changeait, cassant le grain qui est la raison d'être de la table. Le gold merge donc sur
**`(cloud_provider, update_id)`**, et garde `workspace_id` / `pipeline_id` comme attributs.

La clé de la **curated** reste inchangée (`+ period_start_time`) : elle est au grain horaire, où
`update_id` seul n'est pas unique.

### 10.4 `result_state` peut être NULL en gold, et ce n'est pas une anomalie

`updates_tout_null = 0` **aujourd'hui**, mais un update en cours au moment du snapshot n'aurait que
des lignes NULL. À ne pas inscrire comme invariant, et surtout à ne pas masquer par un
`coalesce(result_state, 'UNKNOWN')` qui fabriquerait un état inexistant : laisser NULL, le dire dans
le `table_comment`, et exclure les NULL du **dénominateur** du taux d'échec.

### 10.5 Contrôles ajoutés (12 à 15)

12. `lignes_curated = updates + lignes_result_state_NULL` (identité du §10.1) — se vérifie à
    l'unité près
13. gold : **1 ligne par update**, `lignes/updates = 1,0000` exactement
14. gold : `update_start_time = MIN(period_start_time)` sur **toutes** les tranches, y compris pour
    les updates qui chevauchent ≥ 2 jours — **le contrôle anti-troncature du §6**, à ne pas déclarer
    vert si le sous-ensemble testé est vide
15. gold : `duration_sec` cohérente avec les **deux** définitions du §10.2 (écart ≤ 1 s)

### 10.6 ⚠️ Le taux d'échec dépend de la FENÊTRE, et sur 30 jours le sens s'inverse

Le §7 corrigeait le **dénominateur** du taux d'échec. Il lui manquait deux choses, trouvées en
revérifiant indépendamment les mesures avant de les inscrire dans des commentaires Unity Catalog.
La seconde annule la conclusion du §4.2 pour la période courante.

**(a) Deux définitions du taux « par requête » coexistent, et les deux chiffres publiés sont
exacts.** Une requête peut être dite en échec si **au moins une** de ses tentatives a échoué, ou si
sa **dernière** tentative a échoué. Mesuré sur l'historique complet :

| Définition d'un `request_id` en échec | serverless | classique | ratio |
|---|---:|---:|---:|
| **dernière** tentative en échec | **7,03 %** (19 702 / 280 255) | **5,19 %** (3 504 / 67 507) | **1,35×** |
| **au moins une** tentative en échec | 7,37 % (20 660 / 280 255) | 5,77 % (3 896 / 67 507) | 1,28× |

Le builder gold sert la **première** : une requête qui réussit à la reprise n'est pas un échec, et
c'est la question que pose un utilisateur de la page (« mon pipeline a-t-il fini par passer ? »). La
seconde reste calculable depuis `request_id`, mais doit alors être **nommée** — l'écart de 0,3 à
0,6 point n'est pas la partie importante, c'est le fait que deux chiffres également défendables
circulent.

**(b) Sur les 30 derniers jours, le rapport s'inverse.** Fenêtre posée sur `update_end_time`, l'axe
qu'un consommateur filtrera :

| Fenêtre | par `update_id` | par `request_id` (dernière tentative) |
|---|---|---|
| historique complet (367 j) | serverless **23,16 %** > classique 11,52 % | serverless **7,03 %** > classique 5,19 % |
| **30 derniers jours** | classique **27,89 %** (1 751 / 6 278) > serverless **7,20 %** (2 536 / 35 216) | classique **13,29 %** (694 / 5 221) > serverless **2,01 %** (669 / 33 329) |

Le découpage mensuel explique le renversement, et il est franc : le serverless est descendu de
**40,1 %** (2025-09), après un pic à **53,8 %** (2026-01), à **6,6 %** (2026-09) ; le classique est
monté de **7,9 %** (juillet) à **17,5 %** (août) puis **39,0 %** (septembre), sur une population
~10× plus petite (2 349 updates contre 11 490 en serverless). Deux lectures étaient possibles — un
incident concentré sur quelques pipelines, ou une dégradation large. La concentration tranche :
**142 pipelines classiques sur 177 actifs** portent au moins un échec sur la fenêtre, et le top 3 ne
pèse que **30,8 %** des 1 751 échecs. C'est **large**, donc ce n'est pas un artefact.

**Ce qui ne s'inverse pas** : la durée. p50 des `COMPLETED` à 82 s (serverless) contre 694 s
(classique) sur l'historique, **93 s contre 846 s** sur 30 jours — 8,5× puis 9,1×. Le gain de
**latence** est robuste au choix de fenêtre ; l'écart de **fiabilité** ne l'est pas.

**Conséquence pour l'implémentation, et elle est contraignante** : les artefacts de cette feature
instruisaient T002 et T003 de publier « le serverless échoue deux fois plus », ce qui est
**factuellement inversé** sur la fenêtre que la page affiche par défaut. La règle devient :

1. aucun taux d'échec n'est **codé en dur** dans un artefact ou dans le front — il est recalculé
   sur la fenêtre demandée ;
2. le libellé porte **le dénominateur, la définition et la fenêtre**, les trois ;
3. **aucune forme de compute n'est qualifiée de plus fiable que l'autre** : c'est une mesure de
   période, pas une propriété de la plateforme. Le seul écart affirmable sans réserve est la durée.

### 10.7 Contrôles ajoutés (16 et 17)

16. le taux d'échec servi par l'API **change** quand la fenêtre change (contrôle de non-régression
    du point 1 ci-dessus : un taux constant révèle un chiffre codé en dur)
17. `job_run_timeline.compute_ids` : le taux de vide est mesuré **par `cloud_provider`**, jamais
    globalement (95,3 % aws contre 59,3 % azure en curated — cf. §3)

---

# Addendum du 2026-09-10 — mesures APRÈS déploiement : azure change le comparatif

Les sections ci-dessus sont toutes mesurées sur `system.lakeflow.pipeline_update_timeline`, donc
**aws uniquement** : la partie azure est ingérée par JDBC cross-tenant et n'était pas mesurable
avant le premier run. Elle l'est maintenant, et elle **retire son objet** au comparatif
serverless / classique sur ce cloud.

### 10.8 La population azure est le double de l'aws, et elle est serverless à 99,97 %

Premier run d'ingestion, fenêtre `INITIAL_BACKFILL_DAYS = 30` (2026-08-11 → 2026-09-10) :

| | lignes curated | updates | pipelines | workspaces | lignes / update |
|---|---:|---:|---:|---:|---:|
| aws | 43 122 | 41 466 | 1 412 | 42 | **1,0399** |
| **azure** | **86 591** | **86 174** | 1 561 | **10** | **1,0048** |
| bi-cloud | 129 713 | 127 640 | — | 52 | 1,0162 |

Trois faits, chacun avec une conséquence directe :

**(a) Azure porte 67,5 % des updates**, sur **10** workspaces contre 42. Tous les ratios des §1 à
§10.7 ne décrivent donc qu'**un tiers** du périmètre que la page affichera. Aucun d'eux n'est faux,
tous sont partiels — c'est ce que dit déjà le commentaire Unity Catalog de `cloud_provider`, et c'est
maintenant chiffré. Accessoirement, azure est à peine périodisée (1,0048 ligne par update contre
1,0399) : le piège du `COUNT(*)` y est réel mais quatre fois plus faible.

**(b) Le comparatif serverless / classique n'a de sens que sur aws.** Répartition des updates :

| | serverless | classique | part classique |
|---|---:|---:|---:|
| aws | 35 193 | **6 273** | 15,1 % |
| azure | 86 151 | **23** | **0,027 %** |

Sur azure il n'y a **pas de population classique** : 23 updates, 6 `request_id`. Le taux d'échec
« classique azure » vaut 82,61 % par update et 33,33 % par requête — sur 6 requêtes, donc il ne veut
rien dire. **Conséquence contraignante pour T002/T003** : la tuile de comparaison doit porter un
**seuil de population minimale** et, en dessous, afficher l'absence de comparaison plutôt qu'un
pourcentage. Le cas azure/classique est le contre-exemple à inscrire dans le test.

**(c) Le taux d'échec serverless est 3× plus élevé sur azure que sur aws.** Par requête, dernière
tentative :

| | serverless | classique |
|---|---:|---:|
| aws | **1,99 %** (664 / 33 311) | **13,31 %** (694 / 5 216) |
| azure | **5,97 %** (5 105 / 85 453) | 33,33 % (2 / 6) — non significatif |
| **bi-cloud** | **4,86 %** (5 769 / 118 764) | **13,33 %** (696 / 5 222) |

Un taux serverless « global » (4,86 %) est donc la moyenne de deux régimes très différents, tirée
vers le haut par azure qui pèse 72 % du dénominateur. **La page doit soit découper par
`cloud_provider`, soit dire explicitement qu'elle agrège deux clouds** — le grain de toutes les
tables gold commence par `cloud_provider`, la donnée est là pour le faire.

Ce que ces mesures **confirment** en revanche : les chiffres aws du §10.6 se reproduisent sur un jeu
de données indépendant (la curated à 30 jours, et non la system table) — 7,18 % contre 7,20 % par
update, 27,91 % contre 27,89 %, 13,31 % contre 13,29 %, 1,99 % contre 2,01 %. L'inversion du sens sur
30 jours est donc établie **deux fois, par deux chemins différents**.

### 10.9 Contrôles ajoutés (18 à 20)

18. la tuile de comparaison serverless / classique applique un **seuil de population minimale** et
    n'affiche aucun pourcentage en dessous (contre-exemple à tester : azure classique, 6 requêtes)
19. tout taux serverless publié est soit **découpé par `cloud_provider`**, soit accompagné de la
    mention qu'il agrège deux clouds aux régimes différents (1,99 % aws contre 5,97 % azure)
20. `SUM(period_count)` du gold = `COUNT(*)` de la curated, **par `cloud_provider`** — contrôle
    d'audit exécuté après le premier run : 43 122 et 86 591, écart 0 des deux côtés
