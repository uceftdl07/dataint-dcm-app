# Revue T001f — `curated_dbx_lakeflow_pipeline_update_timeline` + `gold_dbx_compute_pipeline_update_stats`

**Date** : 2026-09-10 · **Branche** : `spike/serverless_cluster` (aucune branche créée, aucun
switch — consigne utilisateur) · **Base** : `develop` · **Package** : `packages/dcm-databricks-pipeline`
· **Task** : T001f (spec 025) · **Mode** : `--commit`, revue du diff **staged**

**Verdict**: **PASS**

17 fichiers, **+2 357 / −59**. 9 fichiers de code et de configuration dans
`packages/dcm-databricks-pipeline`, 8 fichiers de spécification et de documentation. Aucun fichier
hors périmètre : ni frontend, ni backend, ni infrastructure.

---

## 1. Gates

Le verdict global de `dcm-review.sh` est **FAIL**, et il est **inexploitable tel quel** : il mesure
le package entier, qui porte une dette antérieure sur trois modules DLT historiques et
`sqs_to_volume_drain.py`. Les deux échecs qu'il nomme —
`tests/test_dlt_workflow.py:251` (ANN001) et `pipelines/sqs_to_volume_drain.py:46` (mypy) — sont
dans des fichiers **absents du diff**. La mesure qui décide est donc double : par fichier sur le
diff, et par comparaison de compteurs globaux avec HEAD.

| Gate | Portée | Résultat |
|------|--------|----------|
| `ruff check` | les 8 fichiers `.py` du diff | **All checks passed** |
| `ruff format --check` | les 8 mêmes | 6 fichiers à reformater — **les 6 échouent déjà sur HEAD** (vérifié deux fois, en extrayant les copies HEAD via `git show HEAD:./…` et en les recontrôlant isolément) ; les **2 fichiers créés sont clean** |
| `mypy` | les 8 mêmes | **1 erreur, pré-existante** : `tests/gold_dbx_compute/test_entrypoint.py:452`, ligne **identique octet pour octet sur HEAD** (`git show HEAD:…` le confirme, et le diff du fichier est en +95 insertions toutes situées après la ligne 452) |
| `mypy` | package entier, erreurs localisées dans les 8 fichiers du diff | **exactement cette même erreur**, aucune autre — donc aucun effet de bord inter-fichiers |
| `ruff check` | package entier, **HEAD vs arbre courant** | **269 → 269** |
| `mypy` | package entier, **HEAD vs arbre courant** | **218 erreurs / 28 fichiers → 218 erreurs / 28 fichiers**, sur **139 → 141** fichiers analysés |
| `pytest` | package entier | **874 passed** en 0,33 s |
| `databricks bundle validate -t dev_local -p dcm-dev` | bundle | **Validation OK!** |

La comparaison HEAD a été faite dans un `git worktree` jeté ensuite, en réutilisant le venv du
package : compteurs **strictement égaux** alors que deux fichiers de plus sont analysés. La
régression est donc nulle, et c'est mesuré, pas argumenté.

`ruff format` reste rouge sur 6 fichiers. Ce n'est pas corrigé **volontairement** : reformater
`specs.py` et `entrypoint.py` en entier noierait le diff de T001f dans plusieurs centaines de
lignes de réindentation sans rapport, contre la consigne « small PR » du GUIDE. La dette est
identifiée, antérieure, et à traiter dans un commit de formatage dédié.

## 2. Revue de skills (`dcm-python`, `dcm-testing`, `dcm-verify`, `dp-data-databricks-cyber`)

Aucun **🔴 blocker**.

### Secrets et contrôles — PASS

Balayage du diff staged sur `dapi…`, `DATABRICKS_TOKEN`, `client_secret`, `azure_client_secret`,
clés privées, `dbfs:/`, `dbutils.fs` : **une seule correspondance**, et c'est la ligne de la
checklist cyber du rapport d'implémentation qui écrit « aucun `dbfs:/` ». Les deux YAML ne portent
que des clés de tâches et des paramètres non sensibles ; le payload one-off de `jobs submit` utilisé
pour le premier run vit dans `/tmp` et référence le secret scope par **noms de clés**, jamais par
valeurs. Toutes les mesures SQL sont passées par le profil OAuth `dcm-dev` — le profil `[DEFAULT]`,
qui porte un PAT interdit, n'a **jamais** été utilisé, et c'est d'ailleurs lui qui a fait échouer un
`bundle validate` sans `-p` avant que je le corrige. Aucun `--no-verify`, aucun test désactivé,
aucun gate contourné.

### Deux défauts trouvés et corrigés dans le livrable du subagent

1. 🟡 → corrigé — `pipelines/gold_dbx_compute/specs.py` : le commentaire Unity Catalog de la table
   **contredisait** celui de la colonne `result_state` sur le dénominateur du taux d'échec (l'un
   incluait « les 2,3 % encore sans état terminal », l'autre les excluait). Et ce 2,3 % est un taux
   **ligne** de la curated (9 817 / 422 167) transposé dans une table de grain **update**, où il
   vaut **0 %**. Publier un taux d'un grain dans le commentaire de l'autre grain est précisément le
   piège que cette table existe pour supprimer. Les deux commentaires disent maintenant la même
   chose, et **la donnée déployée valide la correction** : `result_state` NULL = **0** en gold.
2. 🟡 → corrigé — `tests/system_tables/test_specs.py` : une assertion `!=` entre le tuple de clés
   (5 éléments) et un tuple de 4, censée « montrer » le mode de panne. Vraie par construction, donc
   elle n'assure rien, et mypy la signalait (`comparison-overlap`). Supprimée ; le commentaire
   conservé explique pourquoi ne pas la remettre, l'égalité au-dessus couvrant déjà l'intention.

### Correctness — le point qui justifie à lui seul la revue

Le `GROUP BY` du builder est `(cloud_provider, update_id)`, **exactement la clé de merge du gold**.
Ce n'est pas du style : `merge_into_table` applique `dropDuplicates(list(merge_keys))` **avant** le
MERGE (`pipelines/common/writers.py:156`). Une clé de merge non unique au grain source ferait donc
**tomber des lignes en silence**. La version publiée dans `stories/T001.md` avant implémentation
groupait sur un tuple différent : c'était un défaut de perte de données silencieuse, corrigé avant
le premier run et documenté comme tel.

Même raison côté ingestion : la clé de la curated inclut `period_start_time`, sans quoi 9 817 lignes
disparaîtraient dans le `dropDuplicates`. Le test qui verrouille ça est une **égalité exacte** du
tuple, pas une inclusion.

### Tests — PASS

21 tests neufs sur le périmètre T001f (13 sur le builder, 8 sur les specs gold, 5 sur le dispatch,
+83/−1 sur les specs d'ingestion). Le test le plus utile est
`test_job_inputs_match_the_registry_exactly` : le garde-fou de l'entrypoint ne couvrait qu'**un**
sens — une clé en trop lève une erreur, une clé **manquante** est silencieuse (la spec existe, son
test passe, la table n'est jamais ingérée). L'égalité de liste, ordre compris, ferme ce sens-là.

### Critères d'acceptation du sub-spec — couverts

Le critère T001f de `stories/T001.md` est couvert point par point, y compris ses deux exigences non
évidentes : l'agrégation vit **en gold** et non dans l'ingestion (40 updates s'étalent au-delà du
lookback de 3 j, jusqu'à 19 j — un agrégat incrémental tronquerait leur durée), et **aucun taux
d'échec attendu n'est fixé**, seul le recalcul sur la fenêtre demandée l'est. Le critère a été
complété du bilan post-déploiement.

### Périmètre — PASS

`git diff --cached --name-only` : tout est dans `packages/dcm-databricks-pipeline`, dans
`specs/025-serverless-compute-page/` ou dans `docs/spike/serverless-compute-page/`. Aucun refactoring
opportuniste, aucun churn sans rapport.

## 3. Déploiement, exécution, validation de la donnée

Exigence utilisateur : *« pour la partie data à la fin d'une tâche déploie test et valide la
donnée »*. Fait, sur `dev_local`, jamais sur `prod`.

| Étape | Résultat |
|---|---|
| Déploiement du bundle | OK (`dev_local`, profil `dcm-dev`) |
| Ingestion — run `3083401854457` | **SUCCESS** — 19ᵉ table, les deux clouds |
| Gold — run `105088015771793` | **SUCCESS** en 66 s |

**Curated, fidélité au grain source** : 43 122 lignes attendues côté aws, 43 122 obtenues ;
**0 orphelin, 0 divergence, 0 doublon** sur la clé de merge ; **1,0399 ligne par update**, ce qui
prouve que la périodisation est conservée et que l'agrégation n'a pas fui dans l'ingestion.

**Gold, grain exécution** : **1,0000** exactement (127 640 lignes pour 127 640 updates, 0 doublon),
0 orphelin de réconciliation, les deux définitions de durée concordent, 0 divergence sur
`result_state` / `compute_type` / `request_id`, `result_state` NULL = **0**, et l'auto-audit
`SUM(period_count)` gold = `COUNT(*)` curated est **exact par `cloud_provider`** (43 122 et 86 591,
écart 0 des deux côtés). Le contrôle anti-troncature — celui qui a motivé tout le choix de
conception — est **non vide** : **48 updates** chevauchent la borne de fenêtre, étalement maximal
**19,2 h**, **0 troncature**. Il prouve donc réellement quelque chose.

**Un écart apparent, expliqué et non un défaut** : le contrôle G6b donne 16,91 % de requêtes
classiques en échec là où j'annonce 13,31 %. Les deux sont exacts — G6b calcule « au moins une
tentative a échoué », mon chiffre « la dernière tentative a échoué ». Les 3,6 points d'écart sont
l'illustration en vraie donnée du §10.6(a) de la baseline, qui exige justement de nommer la
définition.

## 4. Ce que le run a appris, et qui change une consigne frontend

La partie azure est ingérée par JDBC cross-tenant : elle n'était **pas mesurable** avant ce run.
Elle porte **86 174 updates sur 10 workspaces contre 41 466 aws sur 42** — **67,5 %** du périmètre —
et elle est **serverless à 99,97 %** : **23** updates classiques, 6 `request_id`. Le comparatif
serverless / classique est donc structurellement **aws seulement**, et un « taux d'échec classique
azure » de 33,33 % sortirait de **deux** échecs. Par ailleurs le taux serverless est **3× plus élevé
sur azure** (5,97 % contre 1,99 % par requête), ce qui fait du global bi-cloud (4,86 %) une moyenne
pesée à 72 % par azure.

Propagé, pas seulement constaté : §10.8 et §10.9 de `T001f-baseline-measures.md` (contrôles 18 à
20), **SC-008 et SC-008b** de `spec.md`, la règle 4 et le seuil de population dans `stories/T002.md`,
trois critères d'acceptation neufs dans `stories/T003.md`, deux lignes d'annexe dans
`stories/T001.md`. Bénéfice de contrôle au passage : les chiffres aws du §10.6 se reproduisent sur un
**jeu de données indépendant** (la curated à 30 j, et non la system table) — 7,18 vs 7,20 ; 27,91 vs
27,89 ; 13,31 vs 13,29 ; 1,99 vs 2,01. L'inversion sur 30 jours est établie deux fois, par deux
chemins.

## 5. Findings résiduels

```
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/pipeline_update_stats.py: 🟢 note: la fenêtre de réécriture porte sur `update_end_time` — une correction tardive touchant seulement `update_start_time` d'un update terminé hors fenêtre ne serait pas réécrite ; cas non observé sur cette source, parade non justifiée sans lui
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/specs.py: 🟢 note: le commentaire de `GOLD_SPEC_KEYS` parle de la « liste `inputs` du `for_each` » alors que le job gold utilise des tâches explicites — formulation pré-existante, sans effet
packages/dcm-databricks-pipeline/resources/job_dcm_gold_dbx_compute.yml: 🟢 note: la dépendance ingestion 03:00 → gold 05:00 ne tient qu'à une marge de 2 h, non exprimable en `depends_on` (intra-job) ; documentée dans le YAML, correctif réel hors périmètre T001f
packages/dcm-databricks-pipeline/pipelines/system_tables/specs.py: 🟢 note: `account_id` reste hors des clés de merge, contrairement aux deux tables sœurs ; la table est maintenant peuplée, donc revenir dessus coûte un `CREATE OR REPLACE` — décision prise, défendable (`workspace_id` est unique par compte), pas suspendue
packages/dcm-databricks-pipeline: 🟢 note: `ruff format` rouge sur 6 fichiers, tous déjà rouges sur HEAD ; non corrigé pour ne pas noyer le diff — à traiter dans un commit de formatage dédié
```

**Total** : 0 🔴 · 0 🟡 restant (les 2 trouvés sont corrigés dans ce même diff) · 5 🟢.

## 6. Hors périmètre, signalé une fois

Le job n'a pas de `run_as` et s'exécute donc sous l'identité de qui déploie, y compris en prod.
Pré-existant, transverse aux 8 jobs du bundle, non bloquant sur `dev_local`, **bloquant avant tout
déploiement `prod`** — et il faut un nom de service principal, que je ne peux pas inventer.
T001f n'introduit pas la violation et n'en hérite pas.
