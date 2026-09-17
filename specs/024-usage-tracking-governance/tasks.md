# Tasks — Tracking d'usage : Usage des tables UC & Gouvernance

**Spec** : [spec.md](spec.md) · **Plan** : [plan.md](plan.md) · **Contrat API** : [contracts/uc-usage-api.md](contracts/uc-usage-api.md)
**Work type** : feature · **Priorité** : P1
**Stories Jira** : 1 · **Branche** : `dataeng/024-usage-tracking-governance` (**unique**)

> ⚠️ Écart assumé à la convention DCM 1-domaine-1-ticket-1-branche : les **3 tasks
> partagent une seule Story Jira et une seule branche**. Voir `intake.json`
> (`ticket_plan.note`) et la section Complexity Tracking de `plan.md`. Le dispatch doit
> créer **1 Epic + 1 Story**, pas trois.

> La branche est livrée en **squash-and-merge** : les commits individuels ne survivent pas
> au merge, et l'arbre final est le seul enregistrement. Les trois sub-specs portent donc
> le détail de **toutes** les étapes livrées, dans l'ordre chronologique, y compris celles
> qui n'étaient pas planifiées au départ. C'est là qu'il faut lire, pas dans `git log`.

## Tasks

- [x] T001 DataEng pipeline gold usage — histogramme de latence et tables éphémères → [stories/T001-gold-usage-pipeline.md](stories/T001-gold-usage-pipeline.md)
- [x] T002 Backend endpoints /api/v1/uc-usage sur les 8 tables gold usage → [stories/T002-uc-usage-api.md](stories/T002-uc-usage-api.md)
- [x] T003 Frontend pages Usage des tables UC et Gouvernance & Recommandations → [stories/T003-uc-usage-pages.md](stories/T003-uc-usage-pages.md)

## Ordre d'exécution

Séquentiel strict, une seule task ouverte à la fois :

| Ordre | Task | Démarre quand |
|-------|------|---------------|
| 1 | T001 DataEng | branche cut depuis `origin/develop` à jour |
| 2 | T002 Backend | T001 étape 1 cochée **et** table gold rafraîchie |
| 3 | T003 Frontend | T002 cochée |

⚠️ **Ordre de déploiement**, distinct de l'ordre d'implémentation : rejouer le pipeline
`gold_dbx_usage` **avant** de livrer le backend, dans chaque environnement. Les colonnes de
cycle de vie n'existent dans les tables gold qu'après un rejeu, et une colonne absente
remonterait en 500 brut sur les 18 routes de grain table. Détail dans les Notes de
[T002](stories/T002-uc-usage-api.md).

## Historique de livraison

Les 3 tasks ont été livrées en **16 étapes** sur la branche, dont 8 n'étaient passées par
aucune task : ce sont les corrections demandées par l'utilisateur après la première
livraison des 2 pages, plus deux amendements de spec et deux correctifs de suivi. Chaque
étape est décrite dans le sub-spec de sa task, sous son propre titre `## Étape n`.

Trois de ces commits touchent **deux packages** (`42af104`, `8b8b001`, `ba40300`) : leur
moitié backend est une étape de T002, leur moitié frontend une étape de T003. Un même
commit apparaît donc dans deux sub-specs, chacun ne décrivant que sa part.

| Étape | Task | Commit | Objet |
|-------|------|--------|-------|
| 1 | T001 étape 1 | `107b7af` | histogramme de latence en gold pour un P95 de période |
| 2 | T002 étape 1 | `116d38b` | les 12 endpoints d'origine |
| 3 | T003 étape 1 | `8a84f57` | les 2 pages |
| 4 | T002 étape 2 · T003 étape 2 | `42af104` | graphiques, exploration, filtres de colonne |
| 5 | T002 étape 3 · T003 étape 3 | `8b8b001` | corriger les chiffres affichés |
| 6 | T003 étape 4 | `4320d49` | rendre visibles les hausses de coût |
| 7 | T002 étape 4 · T003 étape 5 | `ba40300` | aligner « Cost by table » sur les 2 autres tableaux |
| 8 | T003 étape 6 | `05c2f59` | faire remplir sa carte au tableau sur un grand écran |
| 9 | T003 étape 7 | `f8b204a` | demander un périmètre avant d'afficher la gouvernance |
| 10 | doc | `53e293f` | amender FR-017 — les endpoints snapshot attendent aussi Appliquer |
| 11 | doc | `1316d2d` | amender FR-001 — le bloc « Points d'attention » a été retiré |
| 12 | T002 étape 5 | `5ccdaf2` | `include_deleted` sur 18 routes |
| 13 | T003 étape 8 | `2ae1c52` | case « Include deleted tables » et marqueur de suppression |
| 14 | doc | `87a64ad` | rétro-documenter les 8 commits livrés hors task |
| 15 | T002 étape 6 | *(squash)* | sortir l'anti-appartenance du `OR` des recommandations |
| 16 | T001 étape 2 | *(squash)* | écarter les tables éphémères du catalogue et des faits |

⚠️ Les hashes ci-dessus **ne seront plus résolvables après le squash-and-merge** : ils sont
conservés comme trace de la chronologie, pas comme références utilisables. Les deux
dernières étapes n'en ont pas — elles font partie du squash.

L'étape 16 a été **élargie en cours de route**, sur review du subagent
`dp-data-databricks-engineer` : écarter les éphémères du seul registre les aurait rendues
visibles comme des tables **vivantes** dans les pages d'usage, l'exclusion en aval lisant la
présence d'une ligne `is_deleted` au registre et non l'absence de ligne. Le périmètre couvre
donc les 5 tables gold porteuses de la clé de table, sans changement backend.

## Rapports de review

Chaque étape a été revue par `/speckit.dcm.review --commit` avant son commit : le hook
pre-commit refuse le commit sans stamp, donc l'absence de revue n'est pas possible. Les
rapports intermédiaires n'ont pas été conservés — ils étaient nommés d'après un compteur de
reviews plutôt que d'après une task, et **trois d'entre eux n'avaient jamais été versionnés**
(étapes 4, 5 et 6). Les rapporter dans les sub-specs valait mieux que garder treize fichiers
qu'aucun lecteur ne recoupe : **le verdict et les findings encore ouverts de chaque étape
sont dans la section `## Revues` de sa task**.

Ce qui reste ouvert à ce jour, en un coup d'œil :

| Task | Reste ouvert |
|------|--------------|
| T001 | garde-fou volumétrique / trace persistée de l'audit des éphémères — déclaré en Out of scope |
| T002 | `table_lifecycle()` appelée par requête sur `uc_usage_exploration.py` ; l'ordre de déploiement |
| T003 | `uc-usage-attention-panel.tsx` et ses 3 dépendances sont du code mort depuis le retrait du bloc « Points d'attention » : à supprimer ou à assumer, choix non tranché |

## Gates avant PR

La PR portant les 3 tasks, les gates des **trois** packages doivent être verts, pas seulement
ceux de la dernière étape :

```bash
(cd packages/dcm-databricks-pipeline && uv run ruff check . && uv run pytest tests/ -q)
(cd packages/dcm-backend && uv run ruff check . && uv run mypy . && uv run pytest tests/ -q)
(cd packages/dcm-frontend && npm run lint && npx tsc --noEmit && npm run test && npm run build)
```

Puis `/speckit.dcm.review --commit` avant chaque `git commit` (stamp pre-commit obligatoire).
