# Revue T002b — la neutralisation serverless porte sur le chiffre, plus sur la catégorie

**Date** : 2026-09-10 · **Branche** : `spike/serverless_cluster` (aucune branche créée, aucun
switch — consigne utilisateur) · **Base** : `develop`
**Task** : **T002b**, amendement de T002 (domaine `backend`) — conséquence directe de **T001i**
(commit `a8d0db9`), annoncée dans son rapport §4 comme « à re-mesurer et arbitrer avant T003 ».
**Package** : `packages/dcm-backend` · **Mode** : `--commit`, revue du diff **staged**

**Verdict**: **PASS**

**8 fichiers, +454 / −56** (`git diff --cached --numstat`). Dont **4 fichiers de code**
(**+175 / −47**) tous dans `packages/dcm-backend`, et 4 de spécification (+279 / −9) — dont ce
rapport, qui pèse à lui seul 224 des 454 lignes ajoutées. Aucun fichier pipeline, commons,
frontend ou d'infrastructure. Sur les 175 lignes de code ajoutées, **94 sont du test** et une
grande part du reste est de la docstring : le changement de production tient en **une conjonction
SQL**.

---

## 1. Pourquoi ce commit existe

T001i a supprimé à la source les faux chiffres que T002 neutralisait côté API. La justification
écrite dans `_serverless_void_savings_sql` — « 69 lignes `OPEN` portent 27 104,73 $, soit 57,3 %
de chaque dollar que la page promet » — est devenue fausse le jour même.

Et le module énonce lui-même le critère qui tranche. Il conserve `RELIABILITY` parce que
« les supprimer retirerait un conseil sans retirer un faux chiffre ». Or c'était devenu
**exactement** la situation des règles queue time et spill : conseil réel, 0 $. La neutralisation
retirait donc, par sa propre règle, ce qu'elle n'aurait pas dû retirer.

**Mesuré avant de changer une ligne** — c'est l'inversion de cet ordre qui avait produit
l'attribution fausse corrigée par T001i :

| catégorie | statut | lignes | $ |
|---|---|---:|---:|
| `RIGHTSIZING` (34 queue time + 35 spill) | `OPEN` | **69** | **0,00** |
| `RELIABILITY` (déjà conservées) | `OPEN` | 337 | 0,00 |
| `RIGHTSIZING` (`Warehouse surdimensionné`) | `RESOLVED` | 517 | 90 828,91 |
| `FINOPS` (`Auto-stop manquant`) | `RESOLVED` | 7 | 2 531,03 |
| `RELIABILITY` | `RESOLVED` | 11 | 0,00 |

Mesure faite avec la **sémantique exacte du prédicat** (`bool_and(is_serverless)` au
`MAX(as_of_date)` de `warehouse_utilization_rolling`, LEFT JOIN sur les 3 clés), pas avec un
`DISTINCT` approchant. C'est ce qui a permis de trancher un écart : les specs annonçaient **160**
lignes `RELIABILITY` conservées, le code **337**. C'est le code qui avait raison ; les 3
occurrences de 160 sont corrigées dans ce diff.

**Le texte du conseil a été lu, pas supposé.** Les deux actions concernées sont
`Augmenter max_clusters (scaling)` et `Tuner les requêtes ou upsize cible`. Aucune ne mentionne
quoi que ce soit d'exclusif au classique : un warehouse SQL serverless a bien une taille et une
plage de scaling. Le conseil est applicable tel quel.

## 2. Ce qui change

```python
f"AND UPPER({reco}.category) IN ({categories}) "
f"AND COALESCE({reco}.estimated_savings_usd, 0) > 0"
```

Une conjonction ajoutée, et la fonction devient conforme à son propre nom : elle s'appelle
`_serverless_void_savings_sql`, « l'économie est nulle ». **Une ligne qui ne chiffre rien n'a pas
d'économie nulle à retirer.**

Trois décisions dans cette seule ligne :

- **La catégorie est gardée en pré-filtre.** Le chiffre seul supprimerait une règle
  `RELIABILITY` le jour où l'une d'elles se met à chiffrer quelque chose. Les deux conditions
  sont nécessaires, et la docstring le dit.
- **`> 0` et non `IS NOT NULL`.** Un chiffre de `0` exact ne promet rien : il doit rester visible
  comme un `NULL`. La population `RESOLVED` retirée compte **490** lignes à chiffre non-nul, dont
  **3** valant exactement `0` — d'où **487** et non 490. J'avais d'abord écrit 490 dans trois
  docstrings et un commentaire de test ; la réconciliation les a corrigés. Ce détail a été mesuré,
  pas arrondi.
- **Les montants négatifs ne sont délibérément pas attrapés.** Un `estimated_savings_usd` négatif
  serait un défaut du builder ; le masquer masquerait le défaut. Il y en a **0** aujourd'hui.

L'exemption de `RELIABILITY` devient une **conséquence de la règle** au lieu d'une exception
tenue à la main — ce qui est le meilleur signe que le prédicat est au bon endroit.

**Ce qui reste neutralisé, et pourquoi la fonction n'est pas simplement supprimée** : la route de
liste peut être interrogée avec `status = 'RESOLVED'`, et les lignes serverless résolues portent
toujours l'argent d'avant le correctif — **487 lignes / 93 359,94 $**. Le `_existing_state_cte` du
builder ne lit que `OPEN`/`ACK`, donc **aucun run de pipeline ne les réécrira jamais**. Sans ce
prédicat, un filtre sur `RESOLVED` ré-exposerait 93 359,94 $ de faux.

## 3. Gates

Mesure à **une seule variable** : `git stash push` des fichiers touchés, puis relance des **mêmes
commandes, aux mêmes chemins relatifs, dans le même venv**. HEAD = `a8d0db9`.

| Gate | HEAD | avec T002b | Lecture |
|------|---:|---:|---|
| `ruff check` — 4 fichiers touchés | **All checks passed** | **All checks passed** | 0 erreur introduite |
| `ruff check .` — paquet | 208 | **208** | dette pré-existante, strictement inchangée |
| `ruff check app/` | 124 | **124** | idem |
| `ruff format --diff` — `compute_metrics_common.py` | 6 lignes | **6** | 0 dette de format ajoutée |
| `ruff format --diff` — `compute_metrics_recommendations.py` | 11 | **11** | idem |
| `ruff format --diff` — `compute_metrics_warehouses.py` | 14 | **14** | idem |
| `ruff format --diff` — `test_compute_metrics_services.py` | 68 | **68** | idem |
| `mypy app` | 74 err / 31 fich. / 90 src | **74 / 31 / 90** | identique |
| `pytest -q` — paquet | **776 passés, 0 échec** | **778 passés, 0 échec** | **+2 cas** |
| `pytest tests/test_compute_metrics_services.py` | 90 passés | **92 passés** | **+2** |

`ruff check .` et `mypy app` restent rouges en absolu : dette antérieure arbitrée dans
`tasks.md`. Le verdict porte sur « ce diff n'ajoute rien », mesuré ligne à ligne ci-dessus.

### 3.1 Falsifiabilité — vérifiée

Prédicat remis à sa forme d'avant (la conjonction retirée), tests inchangés :

```
FAILED test_a_serverless_rightsizing_row_that_prices_nothing_stays_visible
FAILED test_the_summary_stops_withholding_a_row_that_promises_nothing
2 failed, 90 passed
```

Puis restauration → **92 passés**, fichier comparé octet à octet à une copie prise avant
l'expérience.

### 3.2 Une mesure invalide, trouvée et refaite — deuxième fois de la spec

`uv run ruff check $F`, avec `F` contenant les trois chemins, a rendu **« Found 1 error »**. J'ai
d'abord lu ça comme une erreur introduite par mon diff. En sortant le message complet :

```
E902 No such file or directory (os error 2)
--> app/…common.py app/…recommendations.py tests/…services.py:1:1
```

Le shell est **zsh**, qui **ne fait pas de word-splitting** sur une expansion non quotée : ruff a
reçu les trois chemins comme **un seul**. L'erreur ne portait sur aucun fichier réel. La même
boucle avait donc aussi invalidé la mesure `ruff format --diff`, qui n'itérait qu'une fois sur un
chemin inexistant — et son « 0 » aurait été lu comme « aucune dette de format ».

C'est la même leçon que le `_head_compute_metrics.py` du §1.3 de T002 : **une mesure peut être
invalidée par l'outil, pas par le code**, et le signal est toujours une incohérence avec un autre
compteur — ici, `Found 1 error` sur trois fichiers alors qu'aucun diagnostic n'était listé.
Refaite avec des arguments littéraux, fichier par fichier : le tableau du §3 est la mesure valide.

## 4. Revue de skills (`dcm-python`, `dcm-testing`, `dcm-verify`)

Aucun **🔴 blocker**.

### 4.1 Secrets et contrôles — PASS

Balayage du diff complet sur `dapi[0-9a-f]`, `DATABRICKS_TOKEN`, `client_secret`, `password`, clés
privées PEM, `dbfs:/`, `dbutils.fs` : **aucune correspondance**. Aucun contrôle contourné, pas de
`--no-verify`, pas de stamp écrit à la main. Toutes les requêtes de mesure sont passées par le
profil **OAuth `dcm-dev`** explicite — le profil `[DEFAULT]`, porteur d'un **PAT interdit par les
règles TTE**, n'a jamais été utilisé.

### 4.2 Tests

| Fichier | HEAD | arbre |
|---|---:|---:|
| `tests/test_compute_metrics_services.py` | 90 | **92** |
| paquet | 776 | **778** |

Les 2 tests neufs, et ce qu'ils ajoutent :

- `test_a_serverless_rightsizing_row_that_prices_nothing_stays_visible` — les trois cas dans une
  seule table de faits : `NULL` reste, `0.0` reste, `500.0` part. `NULL` et `0.0` doivent se
  comporter pareil, et le test le dit plutôt que de le laisser déduire du prédicat.
- `test_the_summary_stops_withholding_a_row_that_promises_nothing` — la même règle vue des KPI :
  la ligne non chiffrée compte dans `open_count` et n'est **pas** reportée comme retirée, la
  chiffrée l'est toujours.

Les 5 tests existants de la neutralisation passent **sans modification** : ils seedent tous des
lignes chiffrées, ce qui est exactement la population que le prédicat doit continuer à retirer.
Trois docstrings ont été mises à jour parce qu'elles portaient des chiffres de dev périmés — pas
les assertions.

### 4.3 Findings

- 🟢 **Le bloc `not_applicable` répond désormais `0 / 0,0` sur les KPI ouverts en dev.** C'est la
  réponse juste et non une panne : plus rien d'ouvert n'est retiré. Le bloc reste, parce que c'est
  lui qui rendra lisible le jour où une ligne chiffrée réapparaît, et parce qu'il couvre aussi les
  lignes `RESOLVED` toujours retirées. Écrit dans sa docstring pour qu'un lecteur futur ne le
  prenne pas pour un bug.
- 🟢 **La tuile `open_recommendations` revient de 388 à 419** — mesurée en reproduisant la requête
  de la tuile (INNER JOIN sur les warehouses actifs de la fenêtre 30 j). Les 31 warehouses perdus
  reviennent en portant **0 $** : la tuile compte des warehouses ayant quelque chose à regarder,
  pas des warehouses avec de l'argent sur la table. Le commentaire de 13 lignes qui justifiait le
  419 → 388 est conservé comme historique et complété, pas remplacé.
- 🟢 **3 chiffres de spec périmés corrigés** : 160 → **337** lignes `RELIABILITY` conservées
  (le code disait vrai), et les compteurs de l'AC des KPI.
- 🟢 **Périmètre** : 4 fichiers de code, tous dans `packages/dcm-backend`, tous déjà touchés par
  T002. Aucune refacto hors sujet.

## 5. Validation sur la donnée

Aucun artefact Databricks n'est déployé par ce commit : le changement est un prédicat SQL construit
par le backend. Ce qui est validable, c'est **ce que le prédicat rend**, et il l'a été en
reproduisant sa sémantique exacte (`sw` CTE, LEFT JOIN, `COALESCE`) contre
`gold_dbx_compute_recommendations` en dev — profil OAuth `dcm-dev`, warehouse `DCM-metrics`, et
**non** le pool applicatif, pour la raison cyber du §2.7 de `review-report-T002.md`.

| statut | lignes | retirées **avant** | $ retirés avant | retirées **après** | $ retirés après | redevenues visibles | $ ré-ajoutés |
|---|---:|---:|---:|---:|---:|---:|---:|
| `OPEN` | 213 930 | 69 | **0,00** | **0** | **0,00** | **69** | **0,00** |
| `RESOLVED` | 32 413 | 524 | 93 359,94 | **487** | **93 359,94** | 37 | **0,00** |

**C'est le résultat cherché, et la colonne qui le prouve est la dernière** : 106 lignes de conseil
redeviennent visibles en ré-ajoutant **0,00 $**. Le commit rend de l'information sans rendre un
seul dollar faux — et les 93 359,94 $ de faux restent retirés à l'unité près.

Les deux nombres de la ligne `RESOLVED` disent bien la même chose : **524** est la population de
catégorie, **487** celles qui portent un chiffre au-dessus de zéro. Le compte baisse de 37 sans
que le montant bouge d'un cent, ce qui est la définition même de ce que `> 0` cherche à laisser
passer — et c'est aussi le contrôle qui a fait tomber mon 490 initial.

Tuile `open_recommendations` sur la fenêtre 30 j, mesurée avec la requête de la tuile :
**419 sans garde-fou · 388 avec l'ancien prédicat · 419 avec le nouveau**.

## 6. Ce qui vient ensuite

**T003** (frontend) : `packages/dcm-frontend/src/types/api.ts` doit refléter les schémas
`dcm-commons`, nullabilité neuve incluse et `ServerlessGovernanceTotals`. Rien dans ce commit ne
change une forme de réponse — seulement des valeurs — donc T003 n'a pas de dépendance neuve.

Décisions qui restent à l'utilisateur, inchangées : la purge de `pipeline_cost_daily`, la
migration de table de T001b (qui est pourquoi T001 reste décochée), `run_as` absent du bundle,
`OWNER_TAG_KEYS` à 3,10 % de la dépense serverless, et la ligne `RESOLVED` figée à 1,46 $ de
T001i.
