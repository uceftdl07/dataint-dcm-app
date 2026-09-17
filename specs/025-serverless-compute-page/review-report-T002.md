# Revue T002 — backend : 8 routes serverless, neutralisation warehouse, schémas partagés

**Date** : 2026-09-10 · **Branche** : `spike/serverless_cluster` (aucune branche créée, aucun
switch — consigne utilisateur) · **Base** : `develop` · **Packages** : `packages/dcm-backend` +
`packages/dcm-commons` · **Task** : T002 (spec 025) · **Mode** : `--commit`, revue du diff
**staged**

**Verdict**: **PASS**

14 fichiers, **+4 771 / −103**. 12 fichiers de code répartis sur **deux** paquets
(`dcm-backend`, `dcm-commons`), 1 fichier de spécification, et **1 correction hors périmètre
assumée et nommée** (`tests/test_connection.py`, 1 ligne + commentaire, §2.6). Aucun fichier
frontend, aucun fichier pipeline, aucune infrastructure.

Le gros du diff est un module neuf de **1 918 lignes** (`compute_metrics_serverless.py`) et
**+77 tests** (699 → 776 dans le paquet). Le rapport code / test est volontairement bas : ce
module lit une table gold construite dans la même spec, et rien dans le SQL ne dit pourquoi il est
écrit comme ça.

---

## 1. Gates

Le verdict de `dcm-review.sh` (`--report /tmp/t002-gates.md`, tenu **hors** du dépôt car le script
**écrase** sa cible) est **FAIL** sur les trois gates, et il est **inexploitable tel quel** : il
mesure des paquets entiers porteurs d'une dette antérieure, et il n'a aucune notion de baseline.
La mesure qui décide est donc double, comme en T001f/T001g : **par fichier** sur le diff, et **par
comparaison de compteurs** avec un worktree détaché sur HEAD (`9bd149d`).

### 1.1 `packages/dcm-backend`

| Gate | HEAD (worktree détaché) | avec T002 | Lecture |
|------|---:|---:|---|
| `ruff check` — 11 fichiers touchés | **All checks passed** | **All checks passed** | 0 erreur introduite |
| `ruff check .` — paquet | 208 | **208** | dette pré-existante, strictement inchangée |
| `ruff check app/` | 124 | **124** | idem |
| `mypy app` | 74 err / 31 fich. / **89** src | **74 / 31 / 90** | +1 fichier analysé, **+0 erreur** |
| `pytest -q` | **699 passés, 0 échec** | **776 passés, 0 échec** | **+77 cas** |

### 1.2 `packages/dcm-commons`

| Gate | HEAD (worktree détaché) | avec T002 | Lecture |
|------|---:|---:|---|
| `ruff check` — 2 fichiers touchés | 13 (11 `D101` + 2 `TC003`) | **13, les mêmes** | pré-existant, §1.3 |
| `ruff check .` — paquet | 312 | **312** | ramené au baseline, pas toléré : §2.5 |
| `mypy dcm_commons` | 3 err / 2 fich. / 27 src | **3 / 2 / 27** | identique |
| `pytest -q` | 144 passés | **144 passés** | vert |

Pas de `mypy` déclaré sur `dcm-commons` par `dcm-review.sh` (`dcm-verify` : le module dérive du
`pyproject.toml`, et ce paquet n'a pas de config `mypy`). Lancé quand même à la main, pour ne pas
laisser un angle mort sur 437 lignes de modèles neufs.

### 1.3 Une mesure per-file que j'ai dû refaire — et pourquoi c'est la bonne leçon

Premier essai de baseline sur les 2 fichiers `commons` : j'ai écrit la version HEAD dans
`dcm_commons/schemas/_head_compute_metrics.py` et lancé `ruff` dessus. Résultat : **2 erreurs**
contre 13 dans l'arbre, soit un faux « +11 `D101` introduits par T002 » — en contradiction directe
avec un compteur global inchangé à 312, ce qui est le signal qui a fait rouvrir la mesure.

La cause est le **nom du fichier** : un module préfixé `_` est privé, donc `D101`
(« missing docstring in **public** class ») ne s'y déclenche pas. J'avais changé deux variables au
lieu d'une. Refaite dans un worktree détaché, **au même chemin relatif** : HEAD donne
**11 `D101` + 2 `TC003`**, exactement l'arbre. Les 13 erreurs sont **intégralement
pré-existantes**, sur des classes `Cluster*`/`Warehouse*` antérieures (lignes 304-668), et le bloc
serverless que j'ai écrit est propre.

Même précaution pour le backend : `ruff`/`mypy`/`pytest` de HEAD ont été lancés **avec le cwd dans
le worktree**, sinon l'install éditable résoudrait le paquet du projet principal et la comparaison
ne mesurerait rien.

## 2. Revue de skills (`dcm-python`, `dcm-testing`, `dcm-verify`)

Aucun **🔴 blocker**. 2 🟡, tous deux **pré-existants et non introduits par ce diff** (§2.4, §2.7).

### 2.1 Secrets et contrôles — PASS

Balayage du diff staged sur `dapi…`, `DATABRICKS_TOKEN`, `client_secret`, `password=`, `api_key=`,
clés privées, `dbfs:/`, `Bearer …` : **une seule correspondance**, et c'est le **nom** de la
variable `DCM_DATABRICKS_SPN_CLIENT_SECRET` dans ma propre note cyber de `stories/T002.md`
(§2.7). **Aucune valeur** de secret, nulle part.

Aucun gate contourné : pas de `--no-verify`, pas de stamp écrit à la main, profil `[DEFAULT]`
(porteur d'un PAT interdit) jamais utilisé — toutes les vérifications live sont passées par le
profil OAuth `dcm-dev` explicite.

### 2.2 Correctness — les trois décisions que le SQL ne peut pas énoncer sur lui-même

**`run_count` est `None`, jamais `0`.** Gold laisse le champ NULL sur **11 des 12 surfaces** et ne
porte aucun zéro. `_optional_int` préserve donc `None`, et le point qui rend les appelants sûrs est
mesuré par un test dédié : `_optional_int(None)` est **falsy exactement comme `0`**, donc un
`if runs:` reste correct et un coût par run reste muet sur un objet non mesuré au lieu de diviser
par zéro. Une route qui répondrait `run_count: 0` inventerait une mesure.

**Les 12 surfaces sont dupliquées depuis le builder gold, et la duplication est gardée par un
test, pas par un commentaire.** Le backend ne peut pas importer le paquet pipeline : c'est la seule
attache entre l'enum et `serverless_surface_case_expr`. Une surface ajoutée là-bas et pas ici
resterait injoignable par l'API et ses lignes gold atterriraient nulle part. Comparaison en
**ensemble** (les deux ordres de déclaration diffèrent et aucun des deux ne signifie quoi que ce
soit), plus la vérification que le bucket de graphe `OTHER_SURFACES` n'est **pas** la surface
`OTHER` — les confondre additionnerait deux séries derrière une seule légende.

**Un histogramme reconstruit depuis un `GROUP BY` clairsemé décale ses étiquettes.** C'est le
défaut le plus dangereux du lot parce qu'il **rend parfaitement** : un `GROUP BY pos` saute les
buckets vides, et une reconstruction en ordre d'arrivée présenterait le compte 0,04–0,08 $ comme
celui de 0–0,01 $. `_histogram_buckets` **lit** la table de positions au lieu de l'itérer, donc une
position hors bornes ne peut pas ajouter un 20e bucket ; les 19 buckets et le dernier non borné
(`to_usd = None` — des runs au-dessus de 1 310,72 $ existent) sont testés, gap inclus.

**Un trou réel fermé en écrivant les tests, et il n'était pas théorique.** `surface` est un `enum`
alimenté par une `option_table` : ses `choices` étaient **vides**, donc rien n'était validé, et
`column_filter=surface:SQL_WAREHOUSSE` arrivait jusqu'à la requête comme valeur liée — pour revenir
en **page vide parfaitement rendue**. Une table qui a l'air filtrée mais ne l'est pas comme demandé
est exactement le mode de panne que la docstring du module interdit. Fermé par un ensemble de
valeurs **clos** sur la spec (`allowed`) + `case="upper"`, vérifié dans `_build`, et sur **les deux
orthographes du même prédicat** (`surface=` et `column_filter=surface:…`) — sans quoi elles
pourraient diverger sur ce qu'est une surface valide. La contradiction
`surface=JOB&column_filter=surface:APP` est un **422** et non un arbitrage : trancher afficherait
une table qui ne correspond à aucune des deux demandes.

**Le sentinelle ne sort pas.** `_NO_OBJECT` est une clé de merge nécessaire dans gold
(`merge_into_table` joint en `<=>` null-safe, un NULL y fusionnerait des lignes) ; servi à l'IHM il
donnerait un lien profond qui 404. `_strip_sentinel` le remplace par `null`, et la route de détail
le refuse **sans toucher l'entrepôt** — vérifié par assertion sur l'absence d'appel.

### 2.3 Tests — PASS, et falsifiables

| Fichier | HEAD | arbre |
|---|---:|---:|
| `tests/test_compute_metrics_routes.py` | 111 | **165** |
| `tests/test_compute_metrics_services.py` | 83 | **90** |
| `tests/test_compute_metrics_serverless.py` | — | **16** (neuf) |
| `tests/test_compute_metrics_filters.py` | 40 | 40 (inventaire mis à jour, pas de cas neuf) |

**Le manque le plus sérieux du premier jet était l'absence de tests *de route*** — les 8 routes
n'étaient couvertes qu'au niveau service et par des appels HTTP manuels en dev. `dcm-testing` est
explicite sur les deux points : « New backend endpoint → `tests/test_{domain}.py` + `mock_db` », et
« *Manual test OK* for new API » est listé comme anti-pattern. Comblé : `TestServerlessRoutes` et
`TestServerlessDeclaredContract`, aux fixtures du fichier (`client` + `mock_db`), couvrent les
formes de payload vide, le 404 du détail (hors périmètre **et** sentinelle), le 422 sur `surface`
manquant ou inconnu, le périmètre projet (`workspace_id IN`, `1 = 0` sans workspace), le soft-fail
à 200 des 6 agrégats et la **ré-émission** sur le détail. Les 2 vues serverless sont ajoutées au
test paramétré `test_unknown_column_is_422_on_every_list_route` (**11 → 13** routes).

**Un critère d'acceptation était faux, et l'écrire l'a montré.** « Les chemins statiques
`/serverless/*` ne sont pas avalés par `/serverless/objects/{object_id}` » avait été formulé
« sinon 404 ». C'est faux : cette route **exige** `surface`, donc un chemin avalé répondrait
**422 — `surface` field required** sur une requête qui ne porte aucun `surface`. Le test assère 200
et **nomme la signature dans sa docstring**, pour qu'un mainteneur voyant un 422 aille lire l'ordre
de déclaration des routes plutôt que sa query string. Un test qui attend le mauvais code d'échec ne
protège de rien.

**Contrôle de contrat, seule forme possible ici.** Le module n'a **aucun `response_model=`** (0
occurrence sur 37 routes) : les modèles `dcm-commons` sont documentaires et dérivent donc en
silence. `TestServerlessDeclaredContract` rejoue les routes et appelle `Model.model_validate()` sur
les payloads, **dans les deux modes** (live-vide et soft-fail), et vérifie qu'aucune clé n'est
servie sans être déclarée — en tenant compte des alias. C'est le précédent de
`test_job_cost_row_columns_all_exist_on_the_declared_contract`, appliqué au bloc serverless.

**Trois tests sont tombés au premier lancement, et les trois fois j'avais tort, pas le code** :
`serverless_share` est un objet à `pct: null` sur le chemin live (pas `null`), `totals` est un dict
à zéros (pas `null`), et `/serverless/governance` ne déclare **aucun** `window_days` — donc
`window_days=5` y est un paramètre surnuméraire ignoré, 200 et pas 422. Les trois assertions ont
été alignées sur le comportement **mesuré**, et le troisième test renommé
`test_governance_declares_no_window_and_binds_none` : il vérifie maintenant que `window_days`
n'apparaît pas dans le SQL et que `30` n'est pas lié.

### 2.4 🟡 Le soft-fail `except Exception` — anti-pattern de skill, gardé comme convention

`compute_metrics_serverless.py` contient **10 `except Exception`** qui retournent un payload vide.
`dcm-python` l'interdit. Gardé quand même, et c'est un choix, pas un oubli : la famille
`app/api/services/compute_metrics_*.py` en compte **41 au total**, dont **31 déjà sur HEAD**
(clusters 7, jobs 6, pipelines 6, warehouses 6, filtres 2, recommandations 2, commun 1,
forecast 1) — c'est la convention du module. Introduire des routes qui remontent l'erreur alors que
leurs voisines rendent 200 vide ferait diverger la page selon l'onglet.

Le coût est réel et doit être écrit : **une réponse tout-à-zéro doit être diagnostiquée, pas
acceptée**, car elle peut vouloir dire « table gold absente » autant que « périmètre vide ». Deux
atténuations dans ce diff : le contrôle de contrat vérifie que les deux formes vides servent le
**même jeu de clés** (§2.5), et **la route de détail, elle, ré-émet** — c'est l'exception
délibérée, testée par `pytest.raises(Exception, match="connection reset")`, parce qu'un 404 sur une
panne d'entrepôt dirait au client « cet objet n'existe pas », ce qui est faux.

### 2.5 Une dérive de contrat trouvée, et corrigée du bon côté

Les deux chemins « rien à afficher » ne sont **pas** le même code : la requête live sur un
périmètre vide rend des lignes-de-rien, une table absente tombe sur un littéral écrit à la main.
En écrivant le test, l'écart était réel — `serverless_share`, `governance_period`, `totals`,
`cost_per_run` et `dlt_comparison` sont `null` dans le fallback et des objets sur le chemin live,
alors que les modèles `dcm-commons` (tous neufs dans ce diff : **0 `class Serverless` sur HEAD**,
vérifié) les déclaraient **non optionnels**.

La correction est allée dans les **modèles**, pas dans le fallback, et la raison se mesure : une
table gold en retard ne doit pas se présenter comme « 0 $ » ou « 0 % de couverture », qui sont des
affirmations. `PeriodRange.model_validate({"from": None, "to": None})` **lève** — d'où
`OptionalPeriodRange`. Un modèle à `serverless_share` non optionnel **rejette**
`{"serverless_share": None}` — vérifié avant de changer quoi que ce soit. Sans ça, `api.ts` (T003)
aurait typé non-nullable un champ nul le jour d'un retard d'ingestion, et le front aurait planté
sur `.pct`. `ServerlessGovernanceTotals` est ajouté pour la même raison : le pied de tableau de
l'onglet gouvernance n'était déclaré nulle part, T003 l'aurait inventé.

Les **8 erreurs `ruff`** que le bloc serverless ajoutait au passage (D101×3, D205×3, D209, RUF002)
sont **corrigées et non tolérées** : 312 → 320 → 312.

### 2.6 La correction hors périmètre — assumée, pas glissée

`tests/test_connection.py::test_connect_timeout_has_actionable_message` échouait **avant** ce
commit. Ce n'est pas une régression, et la cause exacte a été trouvée plutôt que contournée :
`app/config/__init__.py:14` appelle `load_dotenv(_ENV_FILE, override=True)` **à l'import**, donc
`DCM_DATABRICKS_HTTP_PATH` est déjà dans `os.environ` quand le test construit son `Settings(...)` ;
le test n'énonçant pas `databricks_http_path`, la valeur d'environnement l'emportait et
`resolved_http_path` court-circuitait avant `databricks_warehouse_id`.

Le worktree HEAD passait ce test — **parce qu'il n'a pas de `.env`**, pas parce que le code y était
meilleur. C'est précisément le genre de conclusion qu'une comparaison à deux variables produit, et
la même erreur qu'au §1.3.

Corrigé en **1 ligne** (`databricks_http_path=""` explicite : le test asserte sur ce champ, il doit
le déclarer). Deux raisons de l'inclure ici plutôt que de le documenter en rouge : `dcm-verify`
règle 3 interdit d'annoncer un gate vert quand `pytest` est rouge au niveau paquet, et la cause n'a
**aucun** rapport avec T002 — la laisser aurait fait porter à la revue T003 un échec déjà expliqué.

**Vérifié non masquant** : en retirant `http_path` du message d'erreur de `connection.py`, le test
**retombe en échec**. Il vérifie donc toujours ce pour quoi il a été écrit ; `connection.py` a été
restauré et l'arbre est propre sur ce fichier. Le `F841` et les 2 erreurs `mypy` de
`test_connection.py` restent inchangés, simplement décalés de 7 lignes.

### 2.7 Findings pré-existants signalés, hors périmètre de correction

```
packages/dcm-backend/.env: 🟡 risk: pre-existant — DCM_DATABRICKS_SPN_CLIENT_SECRET est defini (longueur 40), donc le pool applicatif s'authentifie par secret de service principal, ce que la regle TTE interdit (WIF / identite managee attendus). C'est la raison pour laquelle toutes les verifications live de T002 passent par un shim OAuth et non par le pool. A traiter hors T002, a ne pas laisser tomber
packages/dcm-backend/app/api/services/compute_metrics_serverless.py: 🟡 risk: 10 `except Exception` rendant un payload vide — anti-pattern `dcm-python`, garde par coherence avec les 29 routes de liste existantes (§2.4). Consequence a retenir : une reponse tout-a-zero se diagnostique, elle ne s'accepte pas
packages/dcm-backend: 🟢 note: `ruff check .` compte 208 erreurs pre-existantes (124 dans `app/`), et `ruff format --check` est rouge sur 60 des 90 fichiers de `app/` — `pyproject.toml` declare line-length = 100 mais le paquet n'a jamais ete formate. Ne pas reformater ici : le churn noierait la revue
packages/dcm-commons/dcm_commons/schemas/compute_metrics.py: 🟢 note: 11 D101 + 2 TC003 pre-existants sur des classes Cluster*/Warehouse* anterieures ; le bloc serverless est propre
packages/dcm-backend/app/api/routes/compute_metrics.py: 🟢 note: 0 `response_model=` sur 37 routes — les modeles dcm-commons sont documentaires et derivent en silence ; c'est ce que TestServerlessDeclaredContract compense, et c'est la moitie du contrat que T003 doit refleter dans api.ts
packages/dcm-backend/tests/test_compute_metrics_routes.py: 🟢 note: plusieurs tests asserent des sous-chaines du SQL emis (`workspace_id IN`, absence de `window_days`). `dcm-testing` le decourage en general ; retenu ici parce que la propriete verifiee *est* le SQL (application du perimetre, absence de fenetre sur une table journaliere) et parce que c'est la convention deja etablie du fichier
specs/025-serverless-compute-page: 🟢 note: le piege `# type:` — une ligne de commentaire commencant ainsi est lue par mypy comme un type comment et rapporte `Invalid syntax` sur le fichier entier, en masquant toutes ses autres erreurs, alors qu'`ast.parse` l'accepte et que pytest l'importe. Coute un aller-retour, consigne inscrite dans le commentaire lui-meme
```

**Total** : 0 🔴 · 2 🟡 (les deux pré-existants, aucun introduit) · 5 🟢.

### 2.8 Critères d'acceptation — couverts, et deux corrigés

18 critères cochés, **1 marqué 🚫 non applicable** (le volet forecast, sorti du périmètre par
décision utilisateur le 2026-09-10, tracé et non supprimé). Deux critères ont été **réécrits parce
qu'ils étaient invérifiables ou faux**, ce qui compte davantage que ceux qui passent du premier
coup :

- le critère « réponses warehouse d'un warehouse serverless : aucun `estimated_savings_usd`,
  `utilization_status`, `rightsizing_reco`, `idle_pct` chiffré » portait sur des champs **qu'aucune
  route warehouse ne sert**. Remplacé par ce qui est vérifiable : `/recommendations` ne rend
  **aucune** ligne `RIGHTSIZING`/`FINOPS` sur un warehouse serverless, conserve ses **337** lignes
  `RELIABILITY` avec `is_serverless = true`, et `/warehouses/overview` expose `is_serverless` à
  **trois** valeurs ;
- le contrôle de non-régression forecast attendait **422** sur `object_type=SERVERLESS_SURFACE`.
  Faux : la route ne valide pas `object_type` contre une liste, elle le passe en prédicat SQL et
  rend **200 avec `items: []`**. C'est bien la preuve que la route n'a pas été touchée, mais elle
  s'énonce « 200 vide ».

Les chiffres du premier critère ont également été **corrigés après mesure** post-ingestion :
**13,38 %** de part serverless globale contre **34,65 %** sur la seule surface JOB (les valeurs
d'origine, 8,4 % / 21 %, datent d'avant le premier run), part calculée en **dollars et non en DBU**
(les DBU de deux SKU ne s'additionnent pas), et **251 ids pour 265 couples** sur `AI_ENDPOINT`.

### 2.9 Périmètre et taille du diff

`git diff --cached --name-only` : 10 fichiers `dcm-backend`, 2 `dcm-commons`, 1
`specs/025-serverless-compute-page/`, 1 correction nommée hors périmètre. Aucun refactoring
opportuniste, aucun fichier frontend, aucun builder gold.

**Le diff n'est pas petit** (+4 771), et c'est le point à ne pas maquiller. Il est mono-task et
non fractionnable utilement : les 8 routes partagent un module de service, les schémas sans les
routes ne se valident pas, et les tests de contrat ont besoin des deux. Découper donnerait des
commits dont aucun ne passe ses propres gates. Ce qui reste hors de ce commit est réellement
séparé : le garde-fou du builder gold (domaine `dataeng`) et `api.ts` (T003).

## 3. Déploiement, test, validation de la donnée

Exigence utilisateur : *« pour la partie data à la fin d'une tâche déploie test et valide la
donnée »*. T002 est **du backend, pas de la data** : il ne construit aucune table, ne modifie aucun
builder gold et ne déploie aucun bundle. Il n'y a donc **rien à déployer ni à revalider côté
donnée** dans ce commit — le prétendre serait une validation décorative.

Ce qui a été validé sur la donnée vivante, c'est **ce que les routes lisent** : chaque route neuve
a été appelée en dev (200, formes de réponse, 404, 422) et ses chiffres réconciliés avec des
requêtes directes sur les tables gold — profil OAuth `dcm-dev`, warehouse `DCM-metrics`, **et non
le pool applicatif** pour la raison cyber du §2.7. Ce sont ces mesures qui ont corrigé les
critères du §2.8, ce qui est le meilleur argument pour les avoir faites.

## 4. Ce qui vient ensuite, et pourquoi ce n'est pas dans ce commit

**Suite immédiate**, dans l'ordre : corriger dans `pipelines/gold_dbx_compute/recommendations.py`
la source des 69 lignes neutralisées / 27 104,73 $, domaine **`dataeng`** → délégation bloquante +
déploiement + run + validation de la donnée ; puis **T003** (frontend — `api.ts` doit refléter les
schémas, **nullabilité neuve incluse** et `ServerlessGovernanceTotals`).

> ### ⚠️ Diagnostic corrigé le 2026-09-10 — ce paragraphe désignait la mauvaise ligne
>
> Il annonçait « **le garde-fou serverless manquant sur la règle `utilization_status = 'OVER'`**
> (une ligne) ». Mesuré avant d'écrire le correctif : cette règle est **déjà inerte** en
> serverless — `utilization_status` est NULL sur les **1 935** lignes serverless de
> `warehouse_utilization_rolling` depuis T001a, donc `= 'OVER'` ne peut pas être vrai, la règle
> s'auto-désactive comme sa docstring l'annonce, et ses **517** lignes serverless sont toutes
> `RESOLVED`. La ligne recommandée ici n'aurait **rien** changé.
>
> Le vrai défaut est ailleurs et vaut plus cher : le CTE `merged` récupérait six colonnes de
> payload en `COALESCE(c.x, ex.x)` alors que sa clé de jointure est la **catégorie**, pas la
> règle. À `recommendation_id` constant, la valeur de la règle de la veille remontait donc sous
> le **libellé de la règle du jour**. Corrigé et validé : **72 lignes / 27 116,40 $** sur **deux**
> catégories, cf. `review-report-T001i.md`.
>
> **Conséquence pour ce commit-ci** : le faux chiffre ayant disparu à la source, la
> neutralisation API de `RIGHTSIZING` sur warehouse serverless retire maintenant un conseil réel
> (queue time, spill) **sans** retirer de dollar — exactement le motif que
> `_serverless_void_savings_sql` invoque pour **conserver** `RELIABILITY`. Sa docstring, qui
> justifie la neutralisation par « 27 104,73 $, soit 57,3 % de chaque dollar », est également
> périmée. À re-mesurer et arbitrer **avant T003**.

## 5. Suite de la revue — la case cochée

Le code de T002 est commité en **`70b6bce`** sous ce verdict. Ce rapport couvre en outre le
commit qui suit, dont le diff est **une ligne** : `tasks.md`, `- [ ] T002` → `- [x] T002`, relu
via `dcm-parse-tasks.sh` (`pending=2 in_progress=0 completed=1`, 0 avertissement) et non à la
main. Il n'ouvre aucun gate de paquet et ne touche aucun code.

**T001 reste non cochée**, et ce n'est pas un oubli : il lui manque la migration de grain de
T001b, refusée par le classifieur (`DROP`/`RENAME`), donc une décision utilisateur — pas du code.

## 6. Décisions utilisateur en attente — rappelées une fois, sans les re-plaider

Quatre décisions restent celles de l'utilisateur, inchangées et **non bloquantes pour ce commit** :
la purge de `pipeline_cost_daily` (113 085 lignes / 37 100,15 $), la migration de grain de T001b
(`DROP`/`RENAME` refusés par le classifieur — `RENAME` recommandé, et c'est pourquoi T001 reste
non cochée), l'absence de `run_as` dans le bundle (bloquant avant tout déploiement `prod`, il faut
un nom de service principal), et la couverture de **3,10 %** de `OWNER_TAG_KEYS` sur la dépense
serverless.
