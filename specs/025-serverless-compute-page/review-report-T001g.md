# Revue T001g — robustesse `compute_kind_case_expr` + sortie de périmètre du volet forecast

**Date** : 2026-09-10 · **Branche** : `spike/serverless_cluster` (aucune branche créée, aucun
switch — consigne utilisateur) · **Base** : `develop` · **Package** :
`packages/dcm-databricks-pipeline` · **Task** : T001g (spec 025), **réduite à son volet §10.2 / T9**
· **Mode** : `--commit`, revue du diff **staged**

**Verdict**: **PASS**

8 fichiers, **+381 / −66**. **2 fichiers de code** (`sql_helpers.py`, `test_sql_helpers.py`), 6
fichiers de spécification. Aucun fichier hors périmètre : ni frontend, ni backend, ni
infrastructure, et **aucun builder gold touché**.

Ce commit fait deux choses de nature différente, et c'est volontaire : il **implémente** ce qui
reste de T001g, et il **acte la sortie de périmètre** du volet forecast décidée par l'utilisateur
le 2026-09-10. Les deux tiennent dans un même diff parce que la seconde est la raison pour laquelle
la première est si petite — les séparer obligerait à lire l'une sans l'autre.

---

## 1. Gates

Le verdict global de `dcm-review.sh` est **FAIL**, et il est **inexploitable tel quel**, pour la
même raison qu'en T001f : il mesure le package entier, qui porte une dette antérieure sur les
modules DLT historiques et `sqs_to_volume_drain.py`. Les deux échecs qu'il nomme —
`tests/test_dlt_workflow.py:251` (ANN001) et `pipelines/sqs_to_volume_drain.py:46` (mypy) — sont
dans des fichiers **absents du diff**. La mesure qui décide est donc double : par fichier sur le
diff, et par comparaison de compteurs globaux avec HEAD.

| Gate | Portée | Résultat |
|------|--------|----------|
| `ruff check` | les 2 fichiers `.py` du diff | **All checks passed** |
| `ruff format --check` | les 2 mêmes | **2 files already formatted** |
| `mypy` | les 2 mêmes | **Success: no issues found in 2 source files** |
| `pytest` | `tests/gold_dbx_compute` | **543 passed** en 0,20 s (dont **5 cas neufs**) |
| `ruff check` | package entier, HEAD (`9bd149d`) vs arbre | **269 → 269** |
| `mypy` | package entier, HEAD vs arbre | **218 erreurs / 28 fichiers → 218 / 28**, sur **141 → 141** fichiers |
| `databricks bundle validate -t dev_local -p dcm-dev` | bundle | **Validation OK!** |

Compteurs globaux **strictement inchangés**, sur le même nombre de fichiers analysés : les 2
fichiers touchés étaient déjà propres et le restent. Contrairement à T001f, **`ruff format` n'a
aucun fichier rouge dans ce diff** — la dette de formatage des 6 fichiers signalée en T001f reste
entière et hors périmètre, aucun de ces 6 fichiers n'est ici.

## 2. Revue de skills (`dcm-python`, `dcm-testing`, `dcm-verify`, `dp-data-databricks-cyber`)

Aucun **🔴 blocker**, aucun 🟡 restant.

### Secrets et contrôles — PASS

Balayage du diff staged sur `dapi…`, `DATABRICKS_TOKEN`, `client_secret`, clés privées, `dbfs:/`,
`dbutils.fs`, `--no-verify` : **0 correspondance**. Le diff est du texte SQL et des assertions, sans
I/O ni accès workspace. Les deux requêtes de validation sont passées par le profil OAuth `dcm-dev` ;
le profil `[DEFAULT]`, porteur d'un PAT interdit, n'a pas été utilisé — et `bundle validate` a été
lancé avec `-p dcm-dev` explicite, précisément parce que l'oubli avait fait échouer la commande en
T001f. Aucun gate contourné.

Seules données réelles introduites : un `workspace_id` et un `sku_name` de facturation, déjà
consignés au §4.3 de la baseline. Aucune donnée personnelle.

### Un défaut trouvé et corrigé dans le livrable du subagent

1. 🟡 → corrigé — `tests/gold_dbx_compute/test_sql_helpers.py` : une assertion
   `all(value.startswith("'") and value.endswith("'") …)` **vraie par construction**, immédiatement
   après l'égalité `produced == ["'CLASSIC'", "'SERVERLESS'"]` qui l'implique entièrement. Une
   assertion qui ne peut pas échouer seule n'assure rien et donne une fausse impression de
   couverture. C'est **exactement** le défaut corrigé en T001f (l'assertion `!=` entre un tuple de 5
   et un tuple de 4) : le laisser passer ici aurait été appliquer deux standards. Supprimée, et
   remplacée par le commentaire qui manquait — pourquoi la ligne `NULL` qui suit est gardée alors
   que l'égalité la recouvre en partie (elle énonce l'invariant plutôt que de le déduire, et couvre
   un NULL placé là où la regex ne regarde pas).

### Correctness — ce que ce diff verrouille, et ce qu'il ne verrouille pas

Le point qui justifie la task : `compute_kind_case_expr` est le discriminant d'une **clé de merge**
de `job_cluster_cost_daily`/`_rolling` et `pipeline_cost_daily`/`_rolling`, **déjà en production**,
et il n'avait **aucun test direct** — 0 occurrence de `compute_kind` dans les 265 lignes de
`test_sql_helpers.py`.

La recommandation d'origine de la story — basculer sur le champ officiel
`product_features.is_serverless` — a été **inversée sur mesure** (§4.3 de la baseline), et le mode
de panne évité n'est pas une erreur mais une **absence d'erreur** : écrite avec un `ELSE`
(discipline T001d), la bascule ne produirait pas une clé NULL repérable mais **une ligne serverless
étiquetée `CLASSIC` en silence**. `merge_into_table` fusionne sur `<=>` null-safe : rien ne serait
levé. Le garde-fou ne pouvait donc être qu'un test, et un test **dont le message porte la mesure**.

**Nuance relevée et corrigée dans le rapport, à ne pas surestimer.** Le subagent a signalé
lui-même, et j'ai vérifié, que 4 tests de builder (`test_job_cluster_cost_daily.py`,
`test_pipeline_cost.py`) tombaient **déjà** sur cette mutation. « Aucun test direct » est exact ;
« rien ne l'attraperait » aurait été faux, et le rapport aurait été trompeur en le laissant
entendre. L'apport réel des tests neufs n'est donc **pas la détection** mais la **trace de
l'arbitrage** : le SQL généré montre le `CASE`, il ne peut pas dire qu'un autre champ a été essayé,
mesuré, puis écarté. C'est aussi ce que fait l'ajout de 14 lignes à la docstring du helper.

**Trade-off assumé** : le test d'égalité de chaîne entière fait aussi échouer une réécriture
*sémantiquement équivalente* (`CASE WHEN cluster_id IS NULL THEN 'SERVERLESS' ELSE 'CLASSIC' END`).
Retenu délibérément — sur une clé de merge en production, « équivalent » n'est pas « identique » et
doit passer par une décision explicite. Le coût est réel et nommé : la clause « à re-vérifier si
Databricks facture un cluster DLT classique sans `cluster_id` » de la docstring impliquera de
toucher 4 tests, pas 1.

### Tests — PASS, et falsifiables

4 fonctions / **5 cas** ajoutés (une paramétrée ×2), 16 → 21 tests dans le fichier, 543 dans
`tests/gold_dbx_compute`.

Le choix de conception qui méritait un arbitrage est **comment tester une expression SQL sans
Spark sans écrire un faux test**. Trois formes possibles, une seule honnête : rejouer la donnée est
impossible (helpers purs) ; évaluer le `CASE` en Python réimplémenterait la sémantique que le test
prétend vérifier, donc se validerait lui-même ; asserter la **structure du SQL rendu** et porter la
mesure dans le message d'échec est la seule qui dise ce qu'elle vérifie. C'est la forme retenue, et
la table de vérité est pour cette raison exprimée en `(fragment de branche, valeur rendue)` et non
en `(cluster_id, compute_kind)`.

**Falsifiabilité vérifiée indépendamment** (un test de non-régression qui ne peut pas échouer ne
vaut rien) : mutation du helper vers `product_features.is_serverless`, suite lancée, état restauré
et re-comparé. **5 des tests neufs tombent** — plus les 4 tests de builder mentionnés ci-dessus, soit
9 au total — et le message rendu au mainteneur cite bien la date, le workspace, le `sku_name`, le
`is_serverless` NULL et la conséquence (« elle aurait etiquete CLASSIC une ligne serverless, en
silence »).

### Critères d'acceptation du sub-spec — couverts

Le critère T001g (§10.2) de `stories/T001.md` est couvert et coché, avec son bilan de vérification.
Le critère T001g (forecast) est **marqué 🚫 non applicable** et non pas silencieusement supprimé.

### Périmètre — PASS

`git diff --cached --name-only` : 2 fichiers dans `packages/dcm-databricks-pipeline`, 6 dans
`specs/025-serverless-compute-page/`. Aucun refactoring opportuniste. Un écart au brief, signalé
par le subagent et **accepté** : il a touché le docstring de module de `test_sql_helpers.py` (2
phrases) alors que je demandais un ajout en fin de fichier — parce que ce docstring affirmait que
« les autres helpers restent vérifiés à travers le SQL généré », ce que l'ajout rendait faux. La
correction est juste ; refuser l'écart aurait laissé une phrase fausse.

## 3. Déploiement, test, validation de la donnée

Exigence utilisateur : *« pour la partie data à la fin d'une tâche déploie test et valide la
donnée »*. Cette task est le cas particulier où **la donnée ne change pas** — et ça se prouve au
lieu de s'affirmer :

| Contrôle | Résultat |
|---|---|
| AST de `sql_helpers.py` **hors docstrings**, HEAD vs arbre | **IDENTIQUE** |
| Expression rendue par `compute_kind_case_expr`, HEAD vs arbre | **égale caractère pour caractère** |
| `databricks bundle validate -t dev_local -p dcm-dev` | **Validation OK!** |

Le SQL produit étant inchangé, un redéploiement suivi d'un run produirait des lignes **identiques** :
il n'y aurait rien à valider, et le prétendre serait une validation décorative. Le bundle est
revalidé quand même, parce que c'est le seul contrôle qui garde un sens ici.

**Ce qui est validé sur la donnée vivante, en revanche, c'est la prémisse du test** — et c'est le
contrôle utile de cette task. Re-mesuré sur `curated_dbx_billing_usage`, profil `dcm-dev`,
warehouse `DCM-metrics` :

| cloud | lignes DLT | `is_serverless` NULL | **discordances** | `cluster_id` NULL | `is_serverless` = true |
|---|---:|---:|---:|---:|---:|
| aws | 1 382 663 | 1 | **1** | 686 953 | 686 952 |
| azure | 851 497 | 0 | **0** | 850 514 | 850 514 |

**2 234 160 lignes**, soit **+200 661** depuis la mesure de conception (2 033 499), et **toujours
une seule discordance** — le même enregistrement, identique champ par champ : aws, workspace
66097812060322, `ENTERPRISE_JOBS_SERVERLESS_COMPUTE_EUROPE_FRANKFURT`, `cluster_id` NULL,
`is_serverless` NULL, 2026-07-31, 0,0006839 DBU.

C'est plus fort que la mesure d'origine : la discordance est **stable sur 200 661 lignes
supplémentaires**, donc ce n'est pas un artefact de fenêtre, et le trou du champ officiel ne s'est
pas rebouché. Le test verrouille un fait qui tient, pas une coïncidence.

## 4. Sortie de périmètre du volet forecast — tracée, pas effacée

Décision utilisateur du 2026-09-10, prise **après** les mesures de faisabilité et **avant** toute
ligne de code : rien n'a été implémenté, rien n'est à défaire. La propagation a été faite à partir
d'un inventaire de références (81 sites sur 6 fichiers), et suit trois règles :

1. **Marquer, jamais supprimer** — chaque énoncé retiré est barré, daté et motivé (🚫 + date +
   raison). Un lecteur futur voit qu'une décision a été prise, pas un trou.
2. **Conserver l'analyse** — les mesures partent dans des blocs `<details>` et dans un §6 neuf de
   `T001g-baseline-measures.md`, parce qu'elles portent sur le mécanisme `ai_forecast` **déjà en
   production sur 4 grains** : elles établissent qu'il publie **23,4 % de lignes NULL** et jusqu'à
   **2,49 × 10³⁸⁹ $** *sans lever d'erreur*. C'est réutilisable indépendamment de cette spec.
3. **Rendre le retrait testable** — dans `stories/T002.md`, le critère
   « `GET /forecast?object_type=SERVERLESS_SURFACE` renvoie des points » n'est pas supprimé mais
   **inversé** : `SERVERLESS_SURFACE` doit rester un `object_type` **inconnu** et rendre **422**.
   C'est ce qui prouve que la route n'a pas été touchée par inadvertance.

Sites propagés : `spec.md` (FR-016, énumération de périmètre, Work Breakdown), `plan.md` (étape 7,
liste des tables modifiées, dépendances, gates P11/P12/P15, arbre de fichiers, diagramme d'ordre,
checklist), `tasks.md` (ligne T001, diagramme, dépendances), `stories/T001.md` (section T001g,
critères, fichiers), `stories/T002.md` (route, fichiers, critère inversé),
`T001g-baseline-measures.md` (en-tête de périmètre + §6).

Un point **volontairement conservé** dans le périmètre malgré le retrait, avec sa justification
écrite dans `tasks.md` : le point 4 « `forecast_daily` : le résidu est accepté, mesuré et borné »
(≈ 7 800 lignes de prévision construites sur les faux DLT). Ce n'est pas la fonctionnalité, c'est
la **conséquence opérationnelle** du recalcul de `pipeline_cost_daily` sur une table déjà en
production, et il ne demande aucun changement de code — seulement un ordre de relance. Le retirer
laisserait 7 800 lignes fausses sans mention nulle part.

## 5. Ce que le §6 neuf apporte à la suite

Trois mesures prises juste avant l'arrêt, conservées parce qu'elles chiffrent ce que coûterait le
durcissement du forecast **existant** — et la première **contredit** la lecture rassurante du §3 :

- **le seuil de 8 points ne se généralise pas** : il coûte 0,70 % des dollars sur
  `SERVERLESS_SURFACE` mais **6,39 %** au grain JOB (p50 = **1 jour** d'historique) et **6,26 %** au
  grain CLUSTER. Le §3 concluait « la décision est facile parce qu'elle est presque gratuite » :
  vrai sur la surface serverless, **faux sur JOB et CLUSTER**. Durcir est un arbitrage de
  couverture, pas un correctif de qualité — ce qui rend le retrait du périmètre défendable sur le
  fond, et pas seulement par décision ;
- **k = 10 se lit sur une distribution** : p90 du rapport prédiction / max observé = **0,88** (une
  prévision légitime est *inférieure* au max déjà observé), et le rejet varie peu de k=3 à k=20
  (1,71 % → 0,74 %) — donc le résultat est **insensible au choix exact de k**, ce qui est le meilleur
  argument pour un k rond ;
- **une borne strictement relative rejetterait de la poussière** : 364 lignes viennent de séries à
  max observé nul, et leur pire prédiction vaut **0,0 à 6 décimales**. La borne a besoin d'un
  plancher **mesuré** (1 × 10⁻⁶ $, 5,2 × 10⁻⁸ DBU), pas choisi.

## 6. Findings résiduels

```
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_sql_helpers.py: 🟢 note: l'egalite de chaine entiere fait echouer une reecriture semantiquement equivalente du CASE ; volontaire sur une cle de merge en production, mais la clause « a re-verifier si Databricks facture un cluster DLT classique sans cluster_id » de la docstring impliquera de toucher 4 tests
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/sql_helpers.py: 🟢 note: la docstring de `compute_kind_case_expr` fait maintenant 30 lignes pour 4 lignes de code — assume : le rapport est justifie par le fait que le choix est contre-intuitif (proxy structurel prefere au champ officiel) et que c'est la troisieme fois dans cette spec
packages/dcm-databricks-pipeline: 🟢 note: `ruff format` reste rouge sur 6 fichiers du package, tous deja rouges sur HEAD et AUCUN dans ce diff ; dette antérieure, a traiter dans un commit de formatage dedie
specs/025-serverless-compute-page/T001g-baseline-measures.md: 🟢 note: §1 a §4.2 et §5.1 a §5.6 decrivent une implementation qui n'aura pas lieu ; conservees deliberement (elles mesurent le mecanisme en production) et l'en-tete le dit explicitement, mais un lecteur pressé peut les prendre pour du reste-a-faire
specs/025-serverless-compute-page: 🟢 note: T001 reste non cochee — il lui manque la migration de grain de T001b (DROP/RENAME refusé par le classifieur, decision utilisateur), pas du code
```

**Total** : 0 🔴 · 0 🟡 restant (le seul trouvé est corrigé dans ce même diff) · 5 🟢.

## 7. Hors périmètre, rappelé une fois sans le re-plaider

Quatre décisions restent celles de l'utilisateur, inchangées depuis le rapport T001f et **non
bloquantes pour ce commit** : la purge de `pipeline_cost_daily` (113 085 lignes / 37 100,15 $), la
migration de grain de T001b (`DROP`/`RENAME` refusés — `RENAME` recommandé), l'absence de `run_as`
dans le bundle (bloquant avant tout déploiement `prod`, il faut un nom de service principal), et la
couverture de 3,1 % de `OWNER_TAG_KEYS` sur la dépense serverless.
