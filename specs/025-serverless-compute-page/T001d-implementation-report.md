# Rapport d'implémentation — T001d (dépense serverless : `serverless_cost_daily` + `serverless_cost_rolling`)

Périmètre livré : les deux tables gold qui rendent visible la dépense serverless,
soit **380 638,71 $ sur la fenêtre de référence** (2026-08-10..2026-09-09, 31 j,
catalogue `it` / schéma `ba_data_connect_monitoring__d` en dev, mesure du
2026-09-10, bi-cloud) — AWS 276 672,18 $, Azure 103 966,54 $, réparties sur
12 surfaces.

Rien n'est déployé, aucun job n'est lancé, aucun commit n'est fait (revue
`/speckit.dcm.review --commit` propriétaire du commit). Le travail est dans le
worktree, non stagé.

---

## Deux décisions à trancher avant déploiement (elles ne se voient qu'ici)

### 1. `run_as` absent du bundle — bloquant avant un déploiement **prod**, pas avant dev

`resources/job_dcm_gold_dbx_compute.yml` (que je modifie pour y ajouter mes deux
tâches) ne porte **aucun `run_as`**, et `databricks.yml` n'en porte pas non plus
sur la cible `prod` (`mode: production`, `root_path` sous
`/Workspace/Users/${workspace.current_user.userName}/`). Le job tourne donc sous
l'identité **humaine** qui déploie, y compris en prod.

C'est **préexistant et transverse au bundle** (8 jobs, ~20 tâches sur ce job
seul) : mes deux tâches n'introduisent pas le défaut, elles l'**héritent**. Je ne
l'ai pas corrigé parce que la correction exige une information que je n'ai pas et
qu'un sous-agent ne peut pas demander : **quel service principal**. Ne pas
l'inventer est la règle.

- Ce que ça ne bloque pas : le déploiement `dev` que tu prévois.
- Ce que ça bloque : un déploiement **prod**. La règle TTE est `run_as` service
  principal en prod ; un déploiement prod fait vivre le défaut.
- Remédiation : `run_as.service_principal_name: <SP>` sur la cible `prod` de
  `databricks.yml` (ou sur le job), plus les grants UC de moindre privilège du SP
  sur `it.ba_data_connect_monitoring__p`. À trancher au niveau **bundle**, pas
  dans T001d — sinon 2 tâches sur 20 tournent sous une identité différente des
  18 autres du même job, ce qui est pire que l'état actuel.

### 2. SC-011 n'est pas validable tel qu'il est écrit (deux fois)

Détail mesuré en §5. En résumé :

- ses percentiles (p50 0,125 / p95 1,49 / p99 14,88) sont des chiffres **AWS
  seuls**. En bi-cloud, ce que la table produit, ils valent **0,1261 / 1,0446 /
  9,1436**. La table est juste ; c'est le critère qui est mono-cloud sans le dire.
- son critère de bucket overflow est **insatisfiable par une table quotidienne** :
  au grain run-JOUR le maximum mesuré est 1 137,99 $, sous la dernière borne
  (1 310,72 $), donc l'overflow est **vide** — et c'est le comportement voulu.
  Seule une exécution **entière** re-sommée à cheval sur minuit atteint
  1 345,12 $, et l'histogramme ne peut pas la voir.

Il faut donc **amender SC-011** (percentiles bi-cloud + overflow attendu vide,
avec le contrôle « s'il se remplit, re-borner la queue ») avant de valider la
story. Ce n'est pas une objection de forme : validé tel quel, le critère fait
échouer une table correcte, ou fait accepter un re-bornage inutile.

---

## 1. Ce qui change, fichier par fichier

| Fichier | Δ |
|---|---|
| `pipelines/gold_dbx_compute/sql_helpers.py` | +290 |
| `pipelines/gold_dbx_compute/serverless_cost_daily.py` | **nouveau**, 523 l. |
| `pipelines/gold_dbx_compute/serverless_cost_rolling.py` | **nouveau**, 311 l. |
| `pipelines/gold_dbx_compute/specs.py` | +443 |
| `pipelines/gold_dbx_compute/entrypoint.py` | +19 |
| `resources/job_dcm_gold_dbx_compute.yml` | +42 |
| `tests/gold_dbx_compute/test_serverless_cost.py` | **nouveau**, 557 l. |
| `tests/gold_dbx_compute/test_sql_helpers.py` | +192 / −2 |
| `tests/gold_dbx_compute/test_entrypoint.py` | +83 |
| `tests/gold_dbx_compute/test_specs.py` | +61 / −3 |

### `sql_helpers.py` — 5 helpers partagés, aucune SQL recopiée dans un builder

`serverless_scope_predicate`, `serverless_surface_case_expr`,
`serverless_object_id_expr`, `identity_principal_expr`, `identity_source_expr`,
plus `HISTOGRAM_COST_PER_RUN_EDGES` / `SERVERLESS_SURFACES` /
`SERVERLESS_OBJECT_ID_SENTINEL` / `SERVERLESS_SCOPE_PRODUCTS`.

Le serverless ne porte **ni `cluster_id`, ni `cluster_source`, ni ligne dans
`curated_dbx_compute_clusters`** : tous les rollups basés cluster l'ignorent par
construction, la facturation est la seule source où il existe. D'où ces helpers,
partagés par les deux tables (et par le snapshot de gouvernance T001e à venir)
plutôt que recopiés.

Trois points portants :

- **Périmètre = liste blanche.** `product_features.is_serverless = true` seul
  perdrait **44 423,98 $ sur 380 638,71 $ (11,7 %)** : GENIE 18 397,47 $,
  AI_ENDPOINT 17 420,85 $, LAKEBASE 6 081,87 $, NETWORKING 2 518,97 $,
  LAKEFLOW_CONNECT 4,82 $ — des services managés, sans cluster à provisionner,
  donc rien à marquer serverless.
- **`ELSE 'OTHER'` est un dispositif de visibilité.** Contrôle à rejouer : `OTHER`
  doit rester ≤ ~10 $ par cloud. Mesuré : **4,82 $ AWS** (uniquement
  `LAKEFLOW_CONNECT`, 36 020 lignes) et **0 $ Azure**.
- **Sentinelle `_NO_OBJECT`** plutôt que NULL, parce que `merge_into_table`
  fusionne sur `<=>` **null-safe** : une clé NULL ne lève pas, elle fond un
  workspace entier en une ligne. En lignes, la sentinelle en porte **plus de la
  moitié** (1 531 218 contre 1 286 959 avec clé) pour **8,78 % du coût**
  (33 425,57 $ ; AWS 26 281,05 $ / 9,50 %, Azure 7 144,52 $ / 6,87 %).

### `serverless_cost_daily.py` — rollup billing-direct, grain `(cloud, workspace, surface, object, jour)`

109 748 lignes de grain sur la fenêtre de référence. Points non déductibles du
code :

- **`cost_usd` couvre 4 unités d'usage** (DBU 377 536,01 · GB 2 268,41 ·
  HOUR 250,56 · DSU 583,73) alors que `dbu_quantity` ne compte **que** les lignes
  DBU. NETWORKING facture **0 DBU pour 2 518,97 $** : un `SUM(usage_quantity)`
  global additionnerait des gigaoctets à des DBU.
- **Comparaison J-1 par self-join exact, jamais `LAG`.** `LAG` sur une partition
  ordonnée par date renvoie la ligne *précédente présente*, pas la veille : un
  objet inactif 3 jours serait comparé à J-4 et son `cost_delta_pct` serait faux
  sans que rien ne lève. Le self-join est égalisé sur **les deux** clés dérivées
  (`serverless_surface` **et** `object_id`).
- **1 jour tampon en lecture, exclu de la sortie.** La lecture facturation
  descend à `lower_bound - 1 j` pour que le self-join voie J-1 au bord de la
  fenêtre incrémentale ; la **sortie** reste bornée à `lower_bound`, sinon le jour
  tampon serait écrit avec un coût **partiel** (sa propre veille n'est pas lue).
- **`run_count` NULL et jamais 0 hors surface `JOB`.** `job_run_id` n'existe que
  là. Agrégation à deux niveaux (`runs` par exécution, puis `runs_agg`), sinon
  l'histogramme compterait des *tranches de facturation* et non des exécutions.
  Le `LEFT JOIN` produit NULL ailleurs : un `COALESCE(..., 0)` affirmerait
  « aucune exécution » pour un warehouse, ce qui est faux — la métrique n'y est
  pas définie.
- **`budget_policy_id`, pas `usage_policy_id`** : sur-ensemble **strict**,
  188 744 lignes portent le premier avec le second NULL, **0** l'inverse, **0**
  désaccord quand les deux sont renseignés.
- **Identité : `max_by(identity_source, identity_principal)`**, pas deux `MAX`
  indépendants — sur les 2 405 lignes de grain à plusieurs identités, deux `MAX`
  attribueraient un coût à un principal avec le `source` d'un autre.
- **Noms résolus « as of »** (`change_time < period_start + INTERVAL 1 DAY`) et
  **gatés par surface**. La facturation ne nomme nativement ni les warehouses ni
  les pipelines (0 % de leur coût) ; la cascade finit sur `g.object_id` pour que
  `object_name` ne soit jamais NULL. 0 ligne de grain nommée par les *deux*
  référentiels : le gating est **préventif**, pas correctif.
- **`cost_rank` par `(jour, surface)`** : l'IHM affiche cette liste filtrée par
  surface, un rang toutes surfaces confondues y commencerait à 40. Douze lignes
  du même jour peuvent donc porter `cost_rank = 1`.

### `serverless_cost_rolling.py` — snapshot 1/7/30/90 j

- **Percentiles recalculés** depuis les histogrammes quotidiens fusionnés bucket
  par bucket. Un percentile n'est ni sommable ni moyennable ; une moyenne de p95
  quotidiens n'a aucune signification statistique.
- **Histogramme masqué à la fenêtre courante** avant fusion : la CTE lit
  `2 × window_days` pour calculer la fenêtre précédente, et `collect_list` ignore
  les NULL — sans le masque, les deux fenêtres seraient mélangées.
- **Puis démasqué en NULL quand `run_count IS NULL`** : `aggregate` sur une liste
  vide renvoie **0**, donc l'histogramme fusionné vaudrait 19 zéros et le p50
  serait lu comme 0,005 $ (représentant du premier bucket) pour un objet qui n'a
  rien exécuté.
- **`cost_usd_prev_window` NULL et non 0** (pas d'`ELSE`), et filtre final avec
  `COALESCE(..., 0) <> 0` : sans le COALESCE, `NULL <> 0` vaut NULL et
  **exclurait** l'objet disparu au lieu de le garder à −100 %.
- `latest_attrs` partitionne sur le grain **complet** hors `period_start`,
  **surface incluse** : le nom d'un `dlt_pipeline_id` vu en `MV_ST_REFRESH` n'est
  pas celui du même id vu en `DLT_PIPELINE`.

### `specs.py`, `entrypoint.py`, `resources/…yml`

Registre gelé (`GOLD_SPECS`), dispatch, 22 + 27 commentaires de colonnes.
Arbitrages : **pas** de `absent_row_delete_guard` sur la quotidienne (le
billing-direct ne rétracte jamais une ligne émise),
`SNAPSHOT_ABSENT_ROW_DELETE_GUARD` sur la fenêtre (`as_of_date` n'est pas une clé
de merge, une ligne périmée survivrait telle quelle et passerait pour courante).

Côté job : deux tâches serverless, `environment_key: gold_compute_env`
(serverless partagé, aucun cluster dédié), `max_retries: 0`, et **aucun
`depends_on` sur le chaînage cluster** — le serverless n'a rien à y attendre.
`gold_serverless_cost_rolling` dépend de la seule `gold_serverless_cost_daily`,
sa source unique.

---

## 2. Les tests mordent-ils ? Campagne de sabotage : 29 mutations, 29 détectées

Un test qui ne casse pas quand le code devient faux n'est pas un test. 29
mutations plausibles (celles qu'une relecture distraite laisserait passer), chaque
fois : mutation → `pytest tests/gold_dbx_compute` → restauration → **vérification
SHA-256** du fichier restauré.

Résultat : **29/29 détectées**, chacune par 1 test en échec. Extraits des plus
significatives :

| Mutation | Détectée par |
|---|---|
| `ELSE 'OTHER'` → `ELSE 'PLATFORM_AUTO'` (le coût non classé redevient invisible) | surface jamais NULL |
| branche `ELSE` supprimée (clé de merge NULL) | idem |
| `MV_ST_REFRESH` testé **après** le `SQL_WAREHOUSE` générique | ordre des branches `SQL` |
| 13ᵉ surface déclarée sans branche dans le `CASE` | exhaustivité `SERVERLESS_SURFACES` |
| constante `SERVERLESS_OBJECT_ID_SENTINEL` désynchronisée du littéral SQL | sentinelle |
| tampon J-1 supprimé / borne de sortie alignée sur le tampon | fenêtre incrémentale |
| J-1 par inégalité (équivalent d'un `LAG`) | self-join exact |
| self-join non égalisé sur `object_id` | idem |
| `COALESCE(ra.run_count, 0)` | `run_count` NULL hors `JOB` |
| CTE `runs` non restreinte à la surface `JOB` | idem |
| `lp.cloud` au lieu de `lp.cloud_provider` | jointure de prix |
| `usage_policy_id` au lieu de `budget_policy_id` | colonne de politique |
| `SUM(usage_quantity)` pour `dbu_quantity` | 4 unités d'usage |
| `cost_rank` toutes surfaces confondues | rang par surface |
| deux `MAX` au lieu de `max_by` | paire d'identité |
| `ELSE 0` sur la fenêtre précédente | delta +infini |
| histogramme non masqué à la fenêtre courante | fusion 2× fenêtre |
| percentiles non masqués | p50 lu dans un histogramme vide |
| filtre final sans `COALESCE` | objet disparu exclu |
| commentaire de colonne orphelin | parité colonnes ↔ commentaires |
| clé de merge `object_id` retirée du grain | grain épinglé |
| rolling recâblé sur la facturation | dispatch |

**Deux trous trouvés par la campagne, et bouchés** (c'est l'intérêt de la faire) :

1. **`COUNT(DISTINCT job_run_id)` interdit passait au vert** parce qu'un
   *commentaire* SQL généré cite la construction. Tous les asserts négatifs du
   nouveau fichier de tests passent désormais par un helper `_code_only()` qui
   retire les commentaires `--` : sinon un assert négatif reste vert le jour où le
   code redevient faux mais garde son commentaire.
2. **Retirer `object_id` de `SERVERLESS_COST_DAILY_MERGE_KEYS` ne cassait
   rien** : la parité `set(merge_keys) <= set(colonnes)` reste vraie quand une clé
   *disparaît*. Ajout de `test_serverless_cost_grain_carries_the_surface_and_the_object`
   dans `test_specs.py`, qui **épingle les deux tuples de clés** — le grain est ce
   qui, faux, écrase silencieusement des lignes distinctes.

Fichiers restaurés à l'identique (SHA-256 vérifié à chaque itération et en fin de
campagne) : `sql_helpers.py`, `serverless_cost_daily.py`,
`serverless_cost_rolling.py`, `specs.py`, `entrypoint.py`.

### Style d'assertion

Prédicats testés sur l'**expression entière** (le `WHERE` de périmètre sur ses
2 lignes, le bloc de self-join sur ses 6) plus des assertions **négatives** :
`LAG(` absent, `ELSE 'PLATFORM_AUTO'` absent, `usage_policy_id` absent,
`COALESCE(ra.run_count` absent, `AVG(` / `percentile(` absents,
`THEN d.run_count ELSE 0` absent, aucun identifiant `cloud` nu (regex).

### Nouveaux tests : 49 ajoutés, 0 supprimé (771 → 820)

- `test_serverless_cost.py` : **30** (17 daily, 13 rolling).
- `test_sql_helpers.py` : **+12** (les helpers portent des invariants que le SQL
  généré ne montre pas : exhaustivité des 12 surfaces, **ordre** des branches,
  alignement des deux expressions d'identité, produit admis au périmètre mais non
  classé).
- `test_entrypoint.py` : **+5** (dispatch, absence de toute table de clusters,
  clés au MERGE, garde-fou de suppression).
- `test_specs.py` : **+2** (grain épinglé, documentation des deux clés non
  nullables et des 4 tables à ne pas sommer avec).

---

## 3. Gates

| Gate | Résultat |
|---|---|
| `ruff check` (9 fichiers touchés) | **All checks passed** |
| `ruff format --check` (mes 5 fichiers) | **clean** |
| `mypy --no-incremental` (9 fichiers) | 1 erreur, **préexistante** |
| `pytest` (suite complète) | **820 passed** (HEAD : 771) |
| `pytest tests/gold_dbx_compute` | 486 passed |
| `databricks bundle validate --strict -t dev -p dcm-dev` | **Validation OK** |

### Parité avec HEAD, mesurée des deux côtés

`git archive HEAD packages/dcm-databricks-pipeline` extrait dans `/tmp/headpkg`,
mêmes commandes des deux côtés.

- **Format** : 4 fichiers préexistants restent non formatés (dette hors
  périmètre, non touchée). Nombre de hunks **identique** HEAD / worktree :
  `entrypoint.py` 4/4, `specs.py` 21/21, `test_entrypoint.py` 11/11,
  `test_specs.py` 11/11. Un 22ᵉ hunk était apparu dans `specs.py` — il venait de
  **mon** bloc (`window_start`), il est corrigé : ma contribution n'ajoute aucune
  dérive.
- **mypy** : la seule erreur est
  `tests/gold_dbx_compute/test_entrypoint.py:452` (`CURATED_LAKEFLOW_JOB_RUN_TIMELINE`
  non ré-exporté, T001b). Même numéro de ligne, même contenu qu'à HEAD, et
  **absente de mon diff** (`git diff | grep -c` = 0).
- **pytest** : HEAD = **771 passed**, worktree = **820 passed**.

Note : l'exécution de mypy dans `/tmp/headpkg` remonte 10 erreurs
supplémentaires dans `forecast.py` que l'arbre réel ne remonte pas — la copie
extraite n'a pas de `.venv`, les stubs `databricks-sdk` s'y résolvent
différemment. La comparaison valable est donc « même erreur, même ligne,
contenu inchangé », pas le total brut.

---

## 4. Vérification cyber

Périmètre : SQL générée, YAML de job, accès aux données de mesure.
N.A. : ML, Apps, Vector Search, MCP, Genie côté produit, Lakebase, modèles —
orchestration et agrégation pures.

| Règle | Statut | Preuve | Remédiation |
|---|---|---|---|
| Aucun PAT, aucun `DATABRICKS_TOKEN` | PASS | mesures via profil **OAuth `dcm-dev`** uniquement ; profil `[DEFAULT]` (PAT prohibé) jamais utilisé | — |
| Aucun secret de service principal | PASS | aucun secret dans le diff | — |
| Aucun secret en clair | PASS | aucun littéral de credential ; les deux builders ne prennent que des noms de tables | — |
| Pas de DBFS | PASS | aucune référence `dbfs:/` ni `dbutils.fs` | — |
| Tout en Unity Catalog | PASS | tables qualifiées `catalog.schema.table`, catalog/schema **paramétrés** (`${var.catalog}` / `${var.schema}`), aucun littéral | — |
| Aucune donnée personnelle PROD → NON-PROD | PASS | lecture dev uniquement, aucun transfert inter-environnement | — |
| Aucune action destructive | PASS | aucun DDL, aucun `DROP`, aucun run de job ; MERGE en upsert, suppression uniquement via le garde-fou de grâce sur le snapshot | — |
| `run_as` service principal en prod | **FAIL** | ni `resources/job_dcm_gold_dbx_compute.yml` ni la cible `prod` de `databricks.yml` ne portent `run_as` | **préexistant, transverse au bundle** — cf. décision 1 : bloquant avant un déploiement **prod**, pas avant dev |
| Moindre privilège UC | N.A. (hors périmètre) | aucun `grants:` dans ce bundle aujourd'hui | à traiter avec le `run_as`, au niveau bundle |

**Conseil upstream écarté** : aucun. Aucun `databricks-*` consulté ne proposait
d'authentification par PAT sur ce périmètre ; les mesures sont passées par
`/tmp/dbxq.sh` (API Statements, profil OAuth `dcm-dev`, warehouse `DCM-metrics`).

**Avant déploiement** : un seul bloqueur, et seulement pour la prod — le `run_as`.
Le déploiement `dev` ne rencontre aucun FAIL introduit par T001d.

---

## 5. Ce que la story / le brief disent de faux, ou d'inmesurable

Six points. Les deux premiers sont ceux qui empêchent de valider la story telle
quelle.

1. **SC-011, percentiles mono-cloud non signalés.** Les valeurs citées
   (p50 0,125 / p95 1,49 / p99 14,88) sont **AWS**. Mesuré sur la fenêtre de
   référence : bi-cloud **p50 0,1261 · p95 1,0446 · p99 9,1436** ;
   AWS **0,1245 · 1,4897 · 14,789** (96 576 run-jours) ; Azure
   **p95 0,8226 · p99 2,8651**. La queue est un phénomène **AWS** : un percentile
   serverless cité sans son cloud ne veut rien dire — exactement la confusion qui
   a fait réécrire deux fois le §10.4 du spike. Ma mesure **reproduit** les
   chiffres AWS de la story, ce qui confirme le diagnostic.
2. **SC-011, critère d'overflow insatisfiable au grain quotidien.** Max mesuré
   par run-JOUR : **1 137,99 $** (AWS), sous la dernière borne. L'overflow est
   **vide**, et doit l'être. Seule une exécution **entière** à cheval sur minuit
   atteint **1 345,12 $** — elle entre dans l'histogramme par tranches
   quotidiennes, chacune sous la borne. Le critère doit être reformulé en
   contrôle (« overflow vide ; s'il se remplit, re-borner »), pas en attente de
   remplissage.
3. **SC-004, « 26 533 $ (9,3 %) » est un chiffre AWS.** Bi-cloud :
   **33 425,57 $ / 8,78 %** (AWS 26 281,05 $ / 9,50 %, Azure 7 144,52 $ /
   6,87 %). Déjà relevé par ta mesure indépendante, confirmé.
4. **`run_count` est un compte de RUN-JOURS, pas d'exécutions distinctes.** Une
   exécution à cheval sur minuit compte pour 2 : **339 AWS + 183 Azure = 522** sur
   161 550 exécutions (**0,32 %**), soit **573 run-jours en trop** sur 162 123
   (**0,35 %**). L'écart est marginal mais réel, et le grain quotidien de la
   source ne permet pas de faire mieux sans relire la facturation. La story parle
   d'exécutions sans cette réserve ; elle est désormais dans les docstrings et
   dans les commentaires de colonnes.
5. **`cost_usd` et `dbu_quantity` ne couvrent pas le même périmètre.**
   `cost_usd` agrège **4 unités** (DBU · GB · HOUR · DSU), `dbu_quantity`
   seulement DBU. NETWORKING : **0 DBU pour 2 518,97 $**. Un rapport $/DBU calculé
   naïvement sur ces deux colonnes est faux sur plusieurs surfaces.
6. **`GENIE_FREE_USAGE` fausse le ratio DBU/coût de GENIE.** C'est le **seul** SKU
   sans prix du périmètre (66 688 lignes, 102 105 DBU) : GENIE affiche
   **321 124 DBU pour 18 397,47 $**. Ce n'est pas un défaut de la table (un SKU
   gratuit coûte 0), mais toute lecture « DBU ⇒ coût » sur cette surface est
   trompeuse, et la story ne le dit pas.

Corrections **de mes propres chiffres** en cours de tâche, pour traçabilité : mes
premières mesures étaient sur une fenêtre de 30 j (2026-08-11..2026-09-09) et non
31 j, ce qui donnait des valeurs voisines mais différentes ; tout a été
re-mesuré sur **ta** fenêtre de référence, de sorte que le dépôt ne porte plus
qu'**une seule** fenêtre. Deux chiffres étaient en outre franchement faux et sont
corrigés : « 57 run-jours > 50 $ / 7 488,25 $ » → **117 / 13 520,44 $** ;
« ~1,5 % des run-jours à cheval sur minuit » → **0,32 % des exécutions / 0,35 %
des run-jours** ; et `serverless_compute_id` « 80 valeurs pour 2 701 jobs » →
**175 pour 3 727** (dont 2 510 en portent un).

Tes deux corrections sont intégrées : `DATA_CLASSIFICATION` est documenté comme
**bi-cloud** (aws 495 lignes / 113,91 $ jusqu'au 2026-01-15 ; azure 648 /
582,32 $) et sert désormais d'argument **pour** la liste blanche (« un produit
peut apparaître sur un cloud, cesser, puis revenir ») ; `budget_policy_id` est
documenté comme **sur-ensemble strict** d'`usage_policy_id`, pas comme un alias.

---

## 6. Ce qui n'est pas fait, et pourquoi

- **Déploiement et validation données** : à toi, comme convenu. Rien n'a été
  déployé, aucun job lancé.
- **Commit** : à `/speckit.dcm.review --commit`. Travail laissé non stagé.
- **T001b / T001e / T001g** (`job_cluster_cost_daily`, `serverless_governance`,
  `forecast`) : non touchés, hors T001d.
- **`run_as` et grants UC** : cf. décision 1 — décision de bundle, pas de tâche.
- **Percentiles exacts par exécution entière** (au lieu de run-jour) :
  demanderait une seconde lecture de la facturation au grain `job_run_id` sans
  découpage quotidien. Écart mesuré à 0,32 % ; non fait volontairement, réserve
  documentée dans les deux modules et dans les commentaires de colonnes.
