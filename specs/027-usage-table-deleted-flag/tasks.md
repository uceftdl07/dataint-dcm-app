# Tasks — Marquage des tables supprimées dans le Data Product Usage

**Spec** : [spec.md](spec.md) · **Plan** : [plan.md](plan.md) · **Data model** : [data-model.md](data-model.md) · **Contrats** : [gold-lifecycle-contract.md](contracts/gold-lifecycle-contract.md) · [api-include-deleted.md](contracts/api-include-deleted.md)
**Work type** : feature · **Priorité** : P1
**Stories Jira** : 1 · **Branche** : `dataeng/027-usage-table-deleted-flag`

## Tasks

- [x] T001 DataEng usage table deleted flag → [stories/T001-usage-table-deleted-flag.md](stories/T001-usage-table-deleted-flag.md)

> Titre volontairement calqué sur le slug : le parseur canonique dérive la branche du titre
> (`{domain}/{spec_num}-{slug}`), donc `dataeng/027-usage-table-deleted-flag`. Le détail
> fonctionnel vit dans la sub-spec, pas dans le titre de la task.

## Couverture des user stories

| User story | Priorité | Task | Statut |
|---|---|---|---|
| US1 — signal de suppression en gold | P1 | T001 | dans cette feature |
| US3 — exclusion du forecast | P2 | T001 | dans cette feature |
| US4 — exclusion gouvernance / recommandations | P2 | T001 | dans cette feature |
| US2 — filtre API + toggle UI | P1 | — | **hors périmètre**, porté par la feature 024 |

Un seul domaine (DataEng), un seul package (`packages/dcm-databricks-pipeline`) : la convention DCM 1-domaine-1-ticket-1-branche s'applique sans écart. Le dispatch doit créer **1 Epic + 1 Story**.

Découper US1/US3/US4 en trois Stories a été écarté : elles modifient les mêmes fichiers (`specs.py`, `entrypoint.py`), et US3/US4 sont bloquées par US1 — trois branches parallèles produiraient des conflits pour aucun gain de parallélisme.

## US2 — délégation à la feature 024

Le code à modifier (21 endpoints `/api/v1/uc-usage/*`, pages `UsageTablesUc` et `UsageGovernance`) vit sur la branche `dataeng/024-usage-tracking-governance` et n'existe pas sur `develop` : le modifier depuis 027 garantirait un conflit de fusion frontal (cf. [research.md](research.md) §R7).

Séquence : **027 merge sur `develop`** → la branche 024 se resynchronise (`git merge origin/develop`) → 024 implémente `include_deleted` selon [contracts/api-include-deleted.md](contracts/api-include-deleted.md) avant sa PR. Ordre contraint : 024 ne peut filtrer sur une colonne qui n'existe pas encore.

Point d'accroche déjà présent côté 024 : ses services déclarent `GOLD_TABLE_CATALOG` dans `app/api/services/uc_usage_common.py` — la jointure de filtrage se greffe sur une table déjà lue.

## Ordre d'exécution

Une seule task. Ses étapes internes (détaillées dans la sub-spec) suivent un ordre contraint :

| Bloc | Contenu | Démarre quand |
|---|---|---|
| A | Socle `LIFECYCLE_STATE_*` + `table_catalog` (US1) | branche cut depuis `origin/develop` à jour |
| B | Forecast (US3) | bloc A terminé |
| C | Gouvernance + recommandations (US4) | bloc A terminé — indépendant de B |

B et C sont parallélisables entre eux, mais tous deux bloqués par A : la colonne doit exister avant d'être filtrée.

## Gates avant PR

```bash
cd packages/dcm-databricks-pipeline
uv run ruff check . && uv run ruff format --check .
uv run mypy .
uv run pytest tests/ -q
```

⚠️ Une suite verte ne suffit pas : les tests de ce package portent sur le **texte SQL généré**, pas sur la donnée. La validation dev de [quickstart.md](quickstart.md) §2.1 à §2.7 est **bloquante avant la PR**.

Puis `/speckit.dcm.review --commit` avant `git commit` (stamp pre-commit obligatoire).
