---
name: dcm-uc-validator
description: >-
  Connect to Databricks Unity Catalog (dev/prod via packages/dcm-backend/.env),
  explore tables with read-only SQL, and validate that DCM UI pages or HTML
  maquettes reference tables/columns that exist in UC. Use for data-existence
  checks — not pixel UX (see dcm-maquette-ux for layout).
compatibility: packages/dcm-backend/.env, our_catalogs_spn.py, maquette/, packages/dcm-frontend/
metadata:
  author: DCM Squad
  domain: data,unity-catalog,validation
  agents: [cursor, copilot, claude]
---

# DCM Unity Catalog Validator

Team skill (comme `dcm-python`) — **pas** un agent installable `@dp-dcm-*`.

Canonical : `spec-kit-dcm-workflow/skills/dcm-uc-validator/SKILL.md`  
Après sync : `.agents/skills/`, `.claude/skills/` (copies locales).

CLI : `packages/dcm-backend/scripts/uc_explorer.py`  
(run with `packages/dcm-backend/.venv/bin/python` — needs `python-dotenv` / databricks deps)

Auth : même flux que le backend (`app/db/connection.py`) — charge `packages/dcm-backend/.env`.  
Si `DCM_ENTRA_TENANT_ID` est set → token Azure AD (client credentials) ; sinon SPN Databricks / PAT.

## Quand charger

- Les données d’une **page** ou **maquette** existent-elles dans Unity Catalog ?
- Explorer / décrire / sampler / query UC (dev ou prod)
- Avant de dire qu’un écran est « branché » sur gold/curated
- Avec `dcm-maquette-ux` si layout **et** données doivent être vérifiés

## Env

| Flag | Schema |
|------|--------|
| `--env dev` | `ba_data_connect_monitoring__d` |
| `--env prod` | `ba_data_connect_monitoring__p` — **requires** `--allow-prod` |

Catalog défaut : `it`. Auth : token → profile → SPN/Entra. **Ne jamais afficher de secrets.**

## Contrat interactif

1. **dev ou prod ?** (prod = demander confirmation explicite)
2. **explore** ou **validate-interface** ?
3. Si validate : **interface existante** ou **maquette** ? (chemins)

## CLI

Préférer `ping` / `tables` / `describe` / `sample` / `check-tables`.  
`query` libre = dernier recours, toujours avec `LIMIT ≤ 100`.

```bash
packages/dcm-backend/.venv/bin/python packages/dcm-backend/scripts/uc_explorer.py --env dev ping
packages/dcm-backend/.venv/bin/python packages/dcm-backend/scripts/uc_explorer.py tables --env dev --like 'curated_*'
packages/dcm-backend/.venv/bin/python packages/dcm-backend/scripts/uc_explorer.py describe gold_data_product_usage --env dev
packages/dcm-backend/.venv/bin/python packages/dcm-backend/scripts/uc_explorer.py sample dim_landing_zone --limit 5 --env dev
packages/dcm-backend/.venv/bin/python packages/dcm-backend/scripts/uc_explorer.py query \
  "SELECT lz_id FROM dim_landing_zone LIMIT 10" --env dev
packages/dcm-backend/.venv/bin/python packages/dcm-backend/scripts/uc_explorer.py check-tables dim_landing_zone --env dev
# prod (opt-in):
packages/dcm-backend/.venv/bin/python packages/dcm-backend/scripts/uc_explorer.py tables --env prod --allow-prod
```

Garde-fous SQL (CLI) :
- SELECT/WITH → `LIMIT` obligatoire, max **100**
- `COUNT(*)` / agrégats / `CROSS JOIN` → refusés sauf `--allow-expensive`
- `--env prod` → refusés sauf `--allow-prod`

## Validate-interface

1. Résoudre fichiers (page TSX, API, ou `maquette/*.html`)
2. `extract-refs` + inventaire KPIs / colonnes
3. Mapper labels → tables UC — **UNMAPPED** si flou
4. `check-tables` + `describe` (+ `sample`) — **pas** de full scan
5. Rapport matrice PASS / GAP / UNMAPPED

## Do / Don't

```text
DO  Demander dev vs prod avant de conclure
DO  Préférer sample / check-tables / describe
DO  Toujours LIMIT ≤ 100 sur query
DON'T SELECT * sans LIMIT / COUNT(*) full table sans --allow-expensive
DON'T --env prod sans --allow-prod
DON'T Livrer ça comme agent @dp-dcm-* / packages/dcm-agent/install
DON'T DDL/DML (our_catalogs_spn.py = autre outil)
DON'T Dump secrets
DON'T Confondre gaps UX (dcm-maquette-ux) et données UC manquantes
```

## Phrases déclencheurs

- « valide vs Unity Catalog »
- « ces données existent dans UC ? »
- « check tables UC pour la maquette / la page »
- « explore Unity Catalog dev/prod »
- `dcm-uc-validator`

## Exemples de prompts

Voir aussi `README.md` dans ce dossier.

### Page existante

```text
follow dcm-uc-validator
validate-interface — page existante
env: dev
page: packages/dcm-frontend/src/pages/ComputeClusters.tsx
Vérifie que les tables/colonnes utilisées existent dans UC et qu'il y a des données (PASS/GAP/UNMAPPED).
```

### Maquette

```text
follow dcm-uc-validator
validate-interface — maquette
env: dev
maquette: docs/maquette/maquette_overview.html
Mappe les KPIs/colonnes affichées vers les tables UC et dis-moi PASS/GAP/UNMAPPED.
```

