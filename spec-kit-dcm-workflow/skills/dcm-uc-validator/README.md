# `dcm-uc-validator`

Skill DCM pour explorer Unity Catalog et valider qu’une **page** ou **maquette** référence des données qui existent dans UC.

Source : `SKILL.md` (charger via sync / `follow dcm-uc-validator`).

## Exemples de prompts

### Explore (tables / sample)

```text
follow dcm-uc-validator
env: dev
explore — ping puis list tables gold_* et sample dim_landing_zone (5 lignes)
```

### Validate-interface — page existante

```text
follow dcm-uc-validator
validate-interface — page existante
env: dev
page: packages/dcm-frontend/src/pages/ComputeClusters.tsx
Vérifie que les tables/colonnes utilisées existent dans UC et qu'il y a des données (PASS/GAP/UNMAPPED).
```

Autres pages utiles : `Dashboard.tsx`, `DataProductUsage.tsx`, `ComputeSqlWarehouses.tsx`, `Costs.tsx`.

### Validate-interface — maquette

```text
follow dcm-uc-validator
validate-interface — maquette
env: dev
maquette: docs/maquette/maquette_overview.html
Mappe les KPIs/colonnes affichées vers les tables UC et dis-moi PASS/GAP/UNMAPPED.
```

Autres maquettes : `docs/maquette/Screen Recording 2026-07-02 at 14.29.37.html`, `maquette/compute-metrics-exposition/`.

### Prod (opt-in)

```text
follow dcm-uc-validator
validate-interface — maquette
env: prod
maquette: docs/maquette/maquette_overview.html
Utilise --allow-prod. Pas de full scan — sample / check-tables seulement.
```

## CLI (rappel)

```bash
packages/dcm-backend/.venv/bin/python packages/dcm-backend/scripts/uc_explorer.py --env dev ping
packages/dcm-backend/.venv/bin/python packages/dcm-backend/scripts/uc_explorer.py sample dim_landing_zone --limit 5 --env dev
```

`--env prod` → `--allow-prod` · `query` → `LIMIT ≤ 100` (agrégats → `--allow-expensive`).
