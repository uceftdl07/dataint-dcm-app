# Revue T001i — le chiffre d'une recommandation doit suivre la règle affichée

**Date** : 2026-09-10 · **Branche** : `spike/serverless_cluster` (aucune branche créée, aucun
switch — consigne utilisateur) · **Base** : `develop`
**Task** : T001 (domaine `dataeng`), sous-tâche **T001i** — défaut **découvert en validant la
donnée de T002**, pas un item du spike, et pas le défaut que T002 annonçait.
**Package** : `packages/dcm-databricks-pipeline` · **Mode** : `--commit`, revue du diff **staged**
**Implémentation** : déléguée au subagent `dp-data-databricks-engineer` (délégation bloquante
imposée par CLAUDE.md pour le domaine `dataeng`), puis revue, contre-mesurée et **corrigée** ici.

**Verdict**: **PASS**

**7 fichiers, +647 / −22.** Dont **2 fichiers de code** (+169 / −9) :
`pipelines/gold_dbx_compute/recommendations.py` et
`tests/gold_dbx_compute/test_recommendations.py`. Les 5 autres sont de la spécification —
ce rapport (+305), `tasks.md` (+9), et **3 fichiers dont le contenu est la correction d'une
attribution fausse que j'avais écrite moi-même** (`stories/T001.md`, `stories/T002.md`,
`review-report-T002.md`) — §3.

Le rapport code / test est de 1 pour 1,15. Le changement de production tient en **6 expressions
SQL**, mais chacune est un arbitrage qui ne se lit pas dans le SQL : c'est pour ça que
l'essentiel du diff de production est de la docstring, et l'essentiel du diff de test est du
verrou de non-régression **dans les deux sens** (§2.3).

---

## 1. Gates

`dcm-review.sh` ne déclare pour ce paquet que **`ruff check .` + `pytest`** (pas de `mypy` :
`dcm-verify` dérive le module du `pyproject.toml` et ce paquet n'a pas de config `mypy`
dédiée). `mypy` et `ruff format` ont été lancés **en plus**, à la main, pour ne pas laisser
d'angle mort.

Comme en T001f / T001g / T002, la mesure qui décide est **double** : par fichier sur le diff, et
par **comparaison de compteurs** avec l'état HEAD. Ici HEAD a été obtenu par
`git stash push` des **deux** fichiers puis relance des **mêmes commandes, aux mêmes chemins
relatifs, dans le même venv** — donc exactement **une** variable change entre les deux colonnes.

| Gate | HEAD | avec T001i | Lecture |
|------|---:|---:|---|
| `ruff check` — 2 fichiers touchés | **All checks passed** | **All checks passed** | 0 erreur introduite |
| `ruff check .` — paquet | 269 | **269** | dette pré-existante, **strictement** inchangée. Le fichier fautif (`tests/test_dlt_workflow.py`) n'est pas dans le diff |
| `ruff format --diff` — `recommendations.py` | 3 lignes | **3 lignes** | 0 dette de format ajoutée |
| `ruff format --diff` — `test_recommendations.py` | 12 lignes | **12 lignes** | idem |
| `mypy pipelines` | 142 err / 7 fich. / **74** src | **142 / 7 / 74** | identique. `recommendations.py` n'est dans **aucun** des 7 |
| `mypy` — 2 fichiers touchés | 1 err | **1 err** | même erreur, même ligne : `test_recommendations.py:46` `no-any-return`, sur le helper partagé `_recommendations_query`, **strictement identique à HEAD** (vérifié par `git show`) |
| `pytest tests -q` — paquet | **879 passés, 0 échec** | **883 passés, 0 échec** | **+4 cas** |
| `pytest tests/gold_dbx_compute -q` | **543 passés** | **547 passés** | **+4 cas** |
| `databricks bundle validate -t dev_local -p dcm-dev` | — | **Validation OK!** | cible `dev_local`, jamais `prod` |

`ruff check .` et `mypy pipelines` restent **rouges en absolu**. Ce n'est pas un PASS déguisé :
le verdict porte sur *« ce diff n'ajoute rien »*, ce qui est mesuré ligne à ligne ci-dessus, et
la dette antérieure reste arbitrée dans `tasks.md`. L'AC « Gates du paquet verts » de T001
**reste décochée** — elle ne peut pas l'être par ce commit.

### 1.1 Falsifiabilité des tests neufs — vérifiée, et pas sur parole

Sans elle, 4 tests verts ne prouvent rien. Mesuré en remettant **le seul fichier de production**
à HEAD (`git stash push -- pipelines/gold_dbx_compute/recommendations.py`), tests inchangés :

```
FAILED test_rule_payload_follows_the_active_rule_not_the_existing_identity
FAILED test_estimated_savings_never_inherited_when_a_candidate_exists_today
FAILED test_resolved_rows_retain_their_last_known_savings
3 failed, 36 passed
```

Puis `git stash pop`, et **547 passés**. Le fichier restauré a été comparé octet à octet à une
copie prise avant l'expérience : identique.

**Le 4e test passe des deux côtés, et c'est voulu** :
`test_join_keys_and_object_name_still_inherit_from_the_existing_state` verrouille ce qui **ne
doit pas** changer (les 5 clés de jointure et `object_name` gardent leur `COALESCE`). Il ne peut
donc pas échouer avant. Le rapport du subagent le disait de lui-même au lieu de le compter parmi
les 3 — c'est la bonne pratique et je la relève plutôt que de la corriger.

## 2. Revue de skills (`dcm-python`, `dcm-testing`, `dcm-verify`)

Aucun **🔴 blocker**.

### 2.1 Secrets et contrôles — PASS

Balayage du diff complet sur `dapi[0-9a-f]`, `DATABRICKS_TOKEN`, `client_secret`, `password`,
clés privées PEM, `dbfs:/`, `dbutils.fs` : **aucune correspondance**. Aucun `.env`, aucun
credential, aucune valeur de secret.

Aucun contrôle contourné : pas de `--no-verify`, pas de stamp écrit à la main. Toutes les
requêtes de mesure et le run de validation sont passés par le profil **OAuth `dcm-dev`
explicite** — le profil `[DEFAULT]` de `~/.databrickscfg`, qui porte un **PAT interdit par les
règles TTE**, n'a jamais été utilisé. Déploiement sur `dev_local` uniquement.

### 2.2 Correctness — le défaut, et pourquoi il était invérifiable de l'extérieur

Trois faits du fichier, chacun légitime seul, produisent la fuite quand on les compose :

1. `QUALIFY ROW_NUMBER() OVER (PARTITION BY cloud_provider, workspace_id, object_type, object_id
   ORDER BY rule_priority) = 1` ne garde **qu'une règle par objet** ;
2. `recommendation_id = sha2(concat_ws('||', workspace_id, object_type, object_id, category,
   first_seen_date))` — l'identité porte la **catégorie**, pas la règle ;
3. le `FULL OUTER JOIN` de `merged` joint sur `(cloud_provider, workspace_id, object_type,
   object_id, **category**)`.

Donc **la règle active peut changer sous une identité stable**. Les six colonnes de payload
étaient récupérées en `COALESCE(c.x, ex.x)` : dès que la règle du jour déclare NULL là où celle
de la veille avait un chiffre, **le chiffre de la veille remonte sous le libellé du jour**.

Le fait publié affirmait alors « spill mémoire détecté » en portant les dollars d'un
rightsizing, avec un `recommendation_id`, un `title`, un `first_seen_date` et un `last_seen_date`
tous **cohérents entre eux**. C'est ce qui rend ce défaut plus grave que sa taille : il ne
produit aucune incohérence détectable dans la ligne servie. Il ne se voit qu'en comparant la
ligne à la règle qui l'a produite — ce que seule une lecture du SQL, ou un time travel, permet.

**Le correctif ne durcit pas, il aligne.** Les six colonnes passent à la forme **déjà utilisée
par `status` et `last_seen_date` dans le même CTE** :

```sql
CASE WHEN c.object_id IS NOT NULL THEN c.title ELSE ex.title END AS title
```

`c.object_id IS NOT NULL` est le test « un candidat existe aujourd'hui » — le même que celui qui
décide déjà `OPEN` vs `RESOLVED` deux lignes plus haut. Le payload et le statut ne peuvent plus
désigner deux jours différents.

**Ce qui garde son `COALESCE`, et c'est un choix, pas un oubli** : les 5 clés de jointure (une
clé doit être renseignée des deux côtés du FULL OUTER JOIN — un `CASE` y produirait des NULL sur
les lignes qui ne sortent que de `existing`) et `object_name` (libellé de l'objet, pas attribut
de règle : le nom d'un warehouse ne change pas parce que la règle qui le juge a changé). Chacun
porte désormais un commentaire disant pourquoi, et le test du §2.3 les verrouille **en sens
inverse**.

### 2.3 Tests — PASS, et symétriques

| Fichier | HEAD | arbre |
|---|---:|---:|
| `tests/gold_dbx_compute/test_recommendations.py` | 39 | **43** |
| `tests/gold_dbx_compute` | 543 | **547** |
| `tests` (paquet) | 879 | **883** |

Les 4 tests neufs :

- `test_rule_payload_follows_the_active_rule_not_the_existing_identity` — **boucle sur les 6
  colonnes** et vérifie pour chacune l'absence de `COALESCE(c.x, ex.x)` **et** la présence des
  deux branches. Un test par colonne aurait laissé passer une 7e colonne ajoutée plus tard sans
  test ; la boucle rend la liste explicite et relisible.
- `test_estimated_savings_never_inherited_when_a_candidate_exists_today` — ferme le circuit sur
  la **colonne de sortie** : ce que le test précédent ne dit pas, c'est que l'expression est bien
  celle qui alimente `AS estimated_savings_usd`. C'est la colonne qui porte l'argent, donc celle
  où la liaison expression → nom de sortie mérite sa propre assertion.
- `test_resolved_rows_retain_their_last_known_savings` — une ligne sans candidat aujourd'hui
  garde son dernier chiffre connu. Sans ce test, « corriger » en forçant NULL passerait les deux
  premiers.
- `test_join_keys_and_object_name_still_inherit_from_the_existing_state` — verrou **inverse**
  contre une « uniformisation » future qui emporterait les 6 `COALESCE` légitimes.

### 2.4 Deux défauts trouvés dans le diff du subagent, et corrigés ici

Ils sont mineurs en volume et instructifs sur la méthode, donc nommés :

- **La docstring propageait *mon* chiffre, pas la mesure du subagent.** Elle annonçait
  « 64 lignes / 27 104,74 $ » — le chiffre de mon brief, hérité de T002 — alors que sa propre
  mesure donnait **72 / 27 116,40 $**. Un rapport qui contredit son brief et une docstring qui
  répète le brief ne peuvent pas coexister. Réécrite avec le total et **la décomposition en deux
  catégories**, qui est l'argument (§2.5).
- **Le 2e test assérait une indentation exacte** sur une chaîne multi-lignes. Brittle sur un
  fichier **déjà rouge à `ruff format --check`** (12 lignes de diff, pré-existantes) : le premier
  `ruff format` du fichier aurait cassé un test qui ne teste pas le formatage. Réécrit sur du SQL
  **normalisé en espaces** (`" ".join(query.split())`), ce qui asserte la sémantique et pas la
  mise en page.

### 2.5 Deux catégories, pas une — et c'est ce qui décide de la forme du correctif

| catégorie | règle du jour (prio) | relayant (prio) | lignes | $ hérités |
|---|---|---|---:|---:|
| `RIGHTSIZING` | `Spill mémoire` (7) / `Queue time` (6) | `Warehouse surdimensionné` (5) | 64 | 27 104,74 |
| `FINOPS` | `Auto-terminaison manquante` (2) | `Cluster zombie` (1) | 8 | 11,66 |
| **total** | | | **72** | **27 116,40** |

La 2e ligne ne concerne **aucun serverless et aucun warehouse** : ce sont des **clusters**.
Vérifiée par time travel — à v5 et v12, ces 8 `recommendation_id` portaient le titre
`Cluster zombie` avec ces mêmes 11,66 $, et à v20 le titre `Auto-terminaison manquante` avec
toujours ces 11,66 $. C'est la preuve directe que le mécanisme est celui de `merged` et non
celui du serverless — donc qu'un garde-fou local sur une règle aurait laissé le défaut en place
ailleurs. **C'est ce qui justifie de corriger les 6 colonnes plutôt qu'une règle.**

### 2.6 Findings

- 🟡 **1 ligne `RESOLVED` reste figée à 1,46 $** hérités, et le pipeline **ne peut pas** la
  réécrire : `_existing_state_cte` ne lit que `status IN ('OPEN', 'ACK')`, par choix documenté
  (ne pas ressusciter la `first_seen_date` d'une anomalie résolue des mois plus tard). La
  corriger demande un `UPDATE` ciblé **hors pipeline**, c'est-à-dire une écriture destructive sur
  de la donnée existante → **décision utilisateur**, non exécutée. Le subagent a refusé de la
  lancer de lui-même et l'a remontée : c'est le bon comportement. **Enjeu réel : 1,46 $ sur
  96 668,53 $ de `RESOLVED` chiffrés (0,0015 %), et les KPI de la page ne comptent que les
  `OPEN`** — aucun chiffre affiché n'est faux à cause d'elle. Documentée en § Notes de
  `stories/T001.md` pour qu'elle ne passe pas pour une régression du correctif.
- 🟡 **La neutralisation API de T002 est devenue trop large**, en conséquence directe de ce
  commit — développé au §4.
- 🟢 **`detail` était une seconde instance latente du même défaut.** `concat` est
  null-intolerant en Spark, contrairement à `concat_ws` : un seul argument NULL rend tout le
  `detail` NULL, donc éligible à l'héritage. Aucune ligne ne le manifestait au moment du
  correctif ; la même correction la ferme. Trouvé par le subagent, pas par moi.
- 🟢 **La règle `utilization_status = 'OVER'` n'avait pas besoin du garde-fou** que T002
  recommandait — §3.
- 🟢 **Périmètre du diff** : 2 fichiers de code, tous deux dans le paquet du domaine `dataeng`
  de l'intake. Aucun fichier backend, frontend, commons ou d'infrastructure. Aucune refacto hors
  sujet. Petit PR par construction.
- 🟢 **`forecast.py` non touché**, conformément à la sortie de périmètre du volet forecast
  (décision utilisateur du 2026-09-10). Il figure dans les 7 fichiers en erreur `mypy`, à
  l'identique de HEAD.

## 3. L'attribution que ce commit corrige — dans mes propres livrables

T002 et son rapport annonçaient, comme suite immédiate, « **le garde-fou serverless manquant sur
la règle `utilization_status = 'OVER'`, une ligne à ajouter par analogie exacte avec le garde-fou
trois règles plus bas** ». **C'était faux, et sur les deux moitiés de la phrase.**

Mesuré avant d'écrire une ligne de correctif : `utilization_status` est **NULL sur les 1 935
lignes serverless** de `warehouse_utilization_rolling` depuis T001a. Donc `= 'OVER'` ne peut pas
être vrai, la règle **s'auto-désactive** exactement comme sa docstring l'annonce, et ses **517**
lignes serverless sont **toutes `RESOLVED`** (dernière vue le 2026-09-09). Le garde-fou que je
recommandais n'aurait corrigé **rien**, et aurait ajouté une condition morte dans un fichier
déjà dense.

Les lignes `RIGHTSIZING` serverless encore `OPEN` venaient des règles **queue time** et
**spill**, qui lisent `warehouse_query_performance_rolling` — table dont T001a n'annule aucune
colonne, **et à raison** : une file d'attente et un débordement mémoire sont des phénomènes
réels en serverless, qui a une taille et une plage de scaling. Ces règles **calculent 0 $** ;
elles n'étaient pas la source de l'argent.

J'ai donc dit explicitement au subagent de **ne pas** ajouter le garde-fou que j'avais
recommandé pendant plusieurs tasks. Les 3 fichiers de spécification du diff portent cette
correction là où le diagnostic faux était écrit : `stories/T002.md` (l'encadré « Prémisse
corrigée » et l'AC concerné), `review-report-T002.md` (§4), et `stories/T001.md` (la section
T001i neuve, qui documente le mécanisme réel).

Ce n'est pas un détail d'historique : un mainteneur qui aurait lu T002 aurait ajouté une ligne
inutile, constaté que les 69 lignes ne disparaissaient pas, et conclu que la mesure était
mauvaise plutôt que le diagnostic.

## 4. Conséquence pour T002, à traiter avant T003

`_serverless_void_savings_sql` (`app/api/services/compute_metrics_common.py`) neutralise
`RIGHTSIZING` et `FINOPS` sur les warehouses serverless. Sa docstring **justifie** cette
neutralisation par « 69 lignes `OPEN` portent 27 104,73 $, soit 57,3 % de chaque dollar que la
page promet ». **Cet argent n'existe plus à la source.**

Le module énonce lui-même le critère qui tranche : `RELIABILITY` est **délibérément conservée**
parce que « les supprimer retirerait un conseil sans retirer un faux chiffre ». Or c'est
désormais **exactement** la situation des règles queue time et spill : conseil réel, 0 $ faux.
La neutralisation est donc devenue **trop large** par sa propre règle, et sa docstring est
périmée sur le chiffre qui la motive.

À faire ensuite, dans cet ordre : **re-mesurer** l'état post-correctif (combien de lignes
`RIGHTSIZING`/`FINOPS` `OPEN` restent sur warehouse serverless, et combien de dollars — attendu :
0 $), **puis** arbitrer `_SERVERLESS_INAPPLICABLE_CATEGORIES`, le bloc `not_applicable` et la
docstring. Re-mesurer d'abord, changer ensuite : c'est précisément l'inversion de cet ordre qui a
produit l'attribution fausse du §3.

Puis **T003** (frontend — `api.ts` doit refléter les schémas `dcm-commons`, nullabilité neuve
incluse et `ServerlessGovernanceTotals`).

## 5. Déploiement, run et validation de la donnée

Exigence utilisateur : *« pour la partie data, à la fin d'une tâche, déploie, teste et valide la
donnée »*. Elle est satisfaite ici de bout en bout.

| Étape | Preuve |
|---|---|
| Validation du bundle | `databricks bundle validate -t dev_local -p dcm-dev` → **Validation OK!** |
| Déploiement | cible **`dev_local`** (host `dbc-223d60ab-45bd`, catalogue `it`, schéma `ba_data_connect_monitoring__d`). **Jamais `-t prod`** |
| Run | job **961859781275611**, run **1089349890449426**, état **SUCCESS** |
| Portée du run | `--json '{"job_id": …, "only": ["gold_recommendations"]}'` → **25 tâches SKIPPED**, dont `gold_pipeline_cost_rolling` : la contrainte « ne pas relancer ce builder avant la purge » est honorée, et le run ne mesure **qu'une** variable |
| Écriture | Delta **v129 → v130**, opération **MERGE**, **213 930 lignes mises à jour, 0 supprimée** |
| État « avant » | lu par **`VERSION AS OF 129`**, pas reconstruit |

**Ce que la donnée dit :**

| | avant (v129) | après (v130) | Δ |
|---|---:|---:|---:|
| Σ `estimated_savings_usd` des `OPEN` | 47 324,89 $ | **20 208,50 $** | **−27 116,40** |
| lignes `OPEN` portant un chiffre | 263 | **191** | −72 |
| lignes `OPEN` (total) | 213 930 | 213 930 | **0** |
| `RESOLVED` — lignes / chiffrées / $ | 32 413 / 18 803 / 96 668,53 | **identique** | **0** |

Décomposition des 72 lignes : **spill 30 / −24 140,91 $**, **queue time 34 / −2 963,83 $**,
**FINOPS 8 / −11,66 $**.

**Les invariants qui rendent le résultat concluant sont tous à zéro** : aucun changement de
`title`, `detail`, `first_seen_date`, `last_seen_date` ni `status` ; aucune ligne apparue ni
disparue ; **aucun dollar ajouté** ; **aucun dollar déplacé** d'une ligne à une autre. Le
correctif n'a fait que **retirer** de l'argent hérité, sur les seules lignes concernées. Sans ces
zéros, un Δ de −27 116,40 $ serait compatible avec un correctif qui aurait cassé autre chose.

## 6. Décisions qui restent à l'utilisateur

Aucune n'est bloquante pour ce commit ; elles sont listées ici pour ne pas être perdues.

1. **La ligne `RESOLVED` figée à 1,46 $** (§2.6) — demande un `UPDATE` destructif hors pipeline.
2. **La purge de `pipeline_cost_daily`** — 113 085 lignes / 37 100,15 $ de faux DLT, payload prêt.
   Tant qu'elle n'est pas faite, `pipeline_cost_rolling` ne doit pas être relancé.
3. **La migration de table de T001b** — `job_cluster_cost_daily` / `_rolling` doivent être
   absentes ; `DROP` et `RENAME` ont tous deux été refusés par le contrôle de permission
   (`RENAME` recommandé). **C'est pour ça que T001 reste décochée dans `tasks.md`.**
4. **`run_as` absent du bundle** — demande un nom de service principal, bloquant avant tout
   déploiement `prod`.
5. **`OWNER_TAG_KEYS` ne couvre que 3,10 % de la dépense serverless.**
