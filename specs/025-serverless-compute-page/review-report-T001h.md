# Review report — T001h (suppression des lignes gold orphelines)

**Date** : 2026-09-10 · **Branche** : `spike/serverless_cluster` · **Base** : `develop`
**Task** : T001 (domaine `dataeng`), sous-tâche **T001h** — dette découverte en implémentant
T001a, pas un item du spike. Ferme **SC-013**.
**Package** : `packages/dcm-databricks-pipeline` · **Diff staged** : 8 fichiers, +413 / −23
**Implémentation** : déléguée au subagent `dp-data-databricks-engineer` (délégation bloquante
imposée par CLAUDE.md pour le domaine `dataeng`), puis revue et contre-mesurée ici.

## Gates

| Gate | Statut | Lecture |
|---|---|---|
| **pytest** | ✅ **PASS** — 744 tests (731 avant T001h, +13) | le gate fonctionne depuis le correctif d'outillage du commit précédent ; c'était un FAIL de bruit auparavant |
| **ruff** (fichiers touchés) | ✅ **All checks passed** sur les 8 | — |
| **ruff** (dépôt) | ⚠️ FAIL, 269 erreurs — **inchangé vs HEAD**. Le fichier incriminé, `tests/test_dlt_workflow.py`, n'est pas dans le diff | dette préexistante, cf. arbitrage `tasks.md` |
| **mypy** (fichiers de prod touchés) | ✅ **Success: no issues found in 4 source files** | le code livré est type-clean en mode `strict` |
| **mypy** (package) | ⚠️ FAIL, 142 erreurs dans 7 fichiers, **aucun dans le diff** | dette préexistante, rendue visible par le commit précédent |
| **format** | ✅ **0 régression** sur les 8 fichiers, prouvée fichier par fichier (HEAD vs worktree) | voir ci-dessous — 3 régressions trouvées et **corrigées** |

**J'ai trouvé 3 régressions de format que le rapport du subagent ne signalait pas**, et c'est un
écart instructif : il avait vérifié que les fichiers étaient *déjà* non formatés au HEAD (vrai),
ce qui répond à une question plus faible que celle qui compte — *mon changement ajoute-t-il du
code non formaté ?* (oui : `entrypoint.py` +11 lignes de diff de format, `test_specs.py` +20,
`test_entrypoint.py` +10). Corrigé en repliant les 4 expressions concernées **à la main**,
sans reformater le reste des fichiers : les 8 sont revenus exactement au niveau du HEAD.

## Le mécanisme livré, et pourquoi il est meilleur que ce que je demandais

Je demandais de « câbler la borne dans `entrypoint.py` ». Le mécanisme retenu va plus loin et
c'est ce qui justifie de l'accepter tel quel : le champ de spec ne porte plus le prédicat
complet mais **seulement le garde-fou volumétrique**, renommé `absent_row_delete_guard` pour ne
pas mentir sur son contenu. Le prédicat réel sort d'un unique point de passage,
`GoldAggregationSpec.resolve_absent_row_delete_predicate(window_floor=…)`, qui **dérive** la
borne de `watermark_column` — un champ préexistant qui *définit* le fait que la table est une
série temporelle.

Conséquence : **un auteur de spec ne peut plus oublier la borne, parce qu'il ne peut pas
l'écrire.** Le seul texte qu'il contrôle est un opérande de conjonction, et une conjonction ne
peut que restreindre la portée du DELETE, jamais l'élargir. C'est exactement le critère que
j'avais posé (« le mécanisme doit rendre impossible d'activer la suppression sur une `*_daily`
sans borne »), satisfait par construction du type plutôt que par vigilance.

Les trois cas, et le mode de défaillance :

| `watermark_column` | `window_floor` | Prédicat | Justification |
|---|---|---|---|
| `None` (snapshot rolling / governance) | — | garde-fou seul | la source est le référentiel complet de l'état courant |
| présent | présent | `t.<wm> >= DATE '<floor>' AND (<garde>)` | borné à la fenêtre recalculée |
| présent | `None` (full refresh sur source vide) | **`None`** → aucune clause DELETE | pas de borne, pas de suppression |

Le troisième cas est le bon choix. J'aurais accepté une exception, mais faire échouer un run
gold entier pour une raison **non destructive** est pire ; un WARNING explicite
(« suppression des lignes absentes DESACTIVEE pour ce run ») rend la dégradation visible sans
la rendre bloquante.

En `full_refresh`, la borne est le `MIN(period_start)` de la **sortie du builder**, pas de la
cible. C'est le détail qui protège l'historique : le gold plus ancien que la couverture curated
réelle n'a pas été recalculé, donc le run ne dit rien de ces jours-là et n'a pas à les
supprimer. Une sortie vide (run dégradé) donne `None` → rien n'est supprimé. Coût assumé et
documenté : une action Spark de plus, limitée au mode full et aux seules specs qui activent la
suppression.

Le piège que j'avais identifié est confirmé dans le code : `partition_predicate` est concaténé
dans le `ON` du MERGE ([writers.py:90-91](../../packages/dcm-databricks-pipeline/pipelines/common/writers.py#L90-L91))
et la couche gold n'en passe **aucun** — donc toute ligne cible hors du lot frais est
`NOT MATCHED BY SOURCE`. Un prédicat non borné sur une `*_daily` aurait effacé l'historique
jusqu'au 2026-07-15 dès le premier run.

## Invariant découvert, absent de mon énoncé

`SNAPSHOT_ABSENT_ROW_GRACE_DAYS` doit rester **strictement inférieur** à
`INCREMENTAL_LOOKBACK_DAYS` (7 < 10). Redémontré indépendamment : une ligne orpheline de
`period_start` P n'est supprimable que si elle est **à la fois** hors grâce et dans la fenêtre,
soit `P + grâce < aujourd'hui ≤ P + fenêtre`. L'intervalle est **vide** dès que
`grâce ≥ fenêtre`, et l'orpheline devient **immortelle** en régime incrémental. Deux constantes
qui vivaient indépendamment sont en réalité couplées ; le couplage est désormais verrouillé par
un test ([test_specs.py:865](../../packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_specs.py#L865)).
Quelqu'un qui monterait la grâce « par prudence » obtiendrait l'effet inverse de celui
recherché — c'est le genre de piège qui ne se voit qu'à l'implémentation.

## Périmètre

- **10 specs `*_rolling`** : invariant revérifié spec par spec, **aucune exclusion**, et sur une
  troisième condition que je n'avais pas énoncée — `watermark_column` **et**
  `incremental_lookback_days` à `None`, sans quoi `NOT MATCHED BY SOURCE` signifierait « hors
  fenêtre » et non « clé disparue ». C'est une meilleure formulation de l'invariant que la
  mienne.
- **`WAREHOUSE_UTILIZATION_DAILY_SPEC`** : seule `*_daily` traitée, avec un commentaire qui dit
  pourquoi elle est légitime (les warehouse-days sont *reconstruits* par sessionisation de
  `warehouse_events`, donc une clé peut disparaître à recalcul constant) et qui interdit
  d'étendre le garde-fou aux autres `*_daily` sans refaire l'analyse.
- 13 tests ajoutés, dont **2 assertions sur la chaîne SQL exacte** incluant la borne. Le
  subagent a vérifié qu'elles **mordent** en sabotant temporairement le résolveur pour qu'il
  rende la garde nue : exactement ces 2 tests échouent. Un test qui n'échoue jamais ne protège
  de rien.

## Validation sur données réelles — contre-mesurée, pas seulement rapportée

Déployé `-t dev_local -p dcm-dev` (jamais `prod`), 2 runs `SUCCESS` du job gold, restreints aux
2 tâches concernées (~4 min de serverless au lieu de ~167 min pour le job complet). J'ai
**rejoué les requêtes moi-même** via la Statements API (`dcm-dev`, warehouse
`fcc5098720414937`) au lieu de me fier au rapport :

| `warehouse_utilization_daily` | avant | après run 1 | après run 2 |
|---|---|---|---|
| `COUNT(*)` | 16 784 | **16 820** ✔ | 16 820 |
| `MIN(period_start)` | 2026-07-15 | **2026-07-15** ✔ | 2026-07-15 |
| `is_serverless IS NULL` | 75 | **32** ✔ | 32 |
| `numTargetRowsDeleted` | **0** (v661, la veille) | **43** (v685) | **0** (v709) |

La v661 du `DESCRIBE HISTORY` est la **preuve directe du défaut** : le MERGE de la veille ne
supprimait rien. La v709 prouve l'idempotence. `16 784 − 43 + 79 = 16 820` : l'arithmétique
ferme. `MIN(period_start)` inchangé : l'historique n'a pas reculé, ce qui était mon critère
d'arrêt.

`warehouse_utilization_rolling` : 2 380 lignes avant/après, 162 NULL, `numTargetRowsDeleted = 0`
aux deux runs. Ce n'est **pas** un échec : la clause DELETE **est** émise, mais
`WHERE _generated_at < date_add(current_date(), -7)` ne sélectionne **0** ligne. Vérifié
`_generated_at` par `_generated_at` : aucune orpheline n'est hors grâce aujourd'hui.

## SC-013 était auto-contradictoire — et c'est le subagent qui l'a montré, pas moi

Le critère exigeait « **0 ligne** à `is_serverless` NULL » **tout en** exigeant le garde-fou de
grâce de 7 jours qui protège précisément les orphelines récentes. **Aucun mécanisme ne peut
satisfaire les deux.** Le subagent a ouvert son rapport sur cette contradiction, mesures en
main, au lieu de la contourner en affaiblissant la grâce ou en lançant un `DELETE` ad hoc — les
deux étaient interdits, et le premier est la protection contre un run dégradé.

SC-013 est donc **reformulé** sur ce qu'il voulait dire : « aucune orpheline ne survit plus de
`grâce + 1` jours », plus le contrôle que le MERGE émet bien une clause DELETE bornée, sans
recul d'historique et idempotente. Ce n'est **pas** un critère assoupli pour épouser un
résultat décevant — SC-001, lui, a été maintenu tel quel et atteint. C'est un critère
**inatteignable par construction**, démontré par la mesure et corrigé comme un défaut de
spécification.

Échéancier de fermeture du résiduel, vérifié par requête : rolling 103 lignes au 09-12, 21 au
09-14, 38 au 09-15 ; daily 19 au 09-14, 13 au 09-17. Les 32 daily ont un `period_start` du
09-05 au 09-09, donc **dans** la fenêtre incrémentale : un run normal les atteindra, sans
nouveau `full_refresh`.

## Findings

```
packages/dcm-databricks-pipeline/resources/job_dcm_gold_dbx_compute.yml:1: 🟡 risk: le `schedule` est PAUSED sur dev_local ET sur dev -> la fermeture du residuel de SC-013 (09-12 au 09-17) demande un run MANUEL, elle ne se fera pas d'elle-meme. C'est le seul point qui peut faire croire a tort que le correctif ne marche pas
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/specs.py:362: 🟡 risk: sur `*_rolling` le residuel est un FLUX, pas un stock — le run du 09-10 a lui-meme cree 204 nouvelles lignes perimees (churn de window_days=1). La peremption passe de permanente a <= 8 jours, elle ne disparait pas. La protection du consommateur reste le filtre de lecture `as_of_date = MAX(as_of_date)`, deja en place cote API et cote moteur de regles
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/entrypoint.py:216: 🟢 note: `_source_watermark_floor` ajoute une action Spark sur le plan du builder, donc une evaluation supplementaire de sa requete. Limitee au mode full (rare, declenche a la main) et aux seules specs qui suppriment — cout assume et documente
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/specs.py:185: 🟢 note: renommage `absent_row_delete_predicate` -> `absent_row_delete_guard` sur la spec, tandis que `writers.py` garde `absent_row_delete_predicate` pour le predicat reel. La distinction est justifiee (la spec ne porte plus qu'un operande) et les 3 appelants sont a jour — verifie par grep, 0 usage orphelin
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_specs.py:826: 🟢 note: 3 regressions de format introduites par le subagent, non signalees par son rapport (il avait verifie « deja non formate au HEAD », question plus faible que « ai-je ajoute du non formate »). Corrigees a la main sur les 4 expressions concernees
```

0 🔴 blocker · 2 🟡 risk · 3 🟢 note

## Verdict

Mécanisme correct, plus sûr que ce que l'énoncé demandait, type-clean, couvert par 13 tests
dont 2 vérifiés mordants, et validé sur données réelles avec l'historique démontré intact et
l'idempotence prouvée par `DESCRIBE HISTORY`. Aucun contrôle affaibli, aucun `DELETE` ad hoc.
Les 3 régressions de format sont corrigées ; les FAIL `ruff`/`mypy` du dépôt sont de la dette
préexistante hors diff, arbitrée dans `tasks.md`. Les 2 🟡 sont des limites **documentées et
chiffrées** du correctif, pas des défauts du code.

**Verdict**: **PASS**
