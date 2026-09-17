# Agent @dp-dcm-sync-infra

Synchronise les routes API backend (`main.py` **develop**) vers le repo infra (`API_GW_2.tf`).

## Prérequis

- `dataint-dcm-app` (branche **develop**) + **`BA-Data-Connect-Monitoring-infra`** dans le workspace
- `gh` authentifié

## Workflow

```
1. Ajouter le repo infra au workspace (si absent)
2. @dp-dcm-sync-infra  → compare main.py (develop) vs API_GW_2.tf, ajoute routes manquantes
3. Script PR           → commit + push + PR vers develop (1 fichier)
```

## Commandes

```
@dp-dcm-sync-infra sync les routes API manquantes
```

```bash
packages/dcm-agent/scripts/sync-infra-apigw-pr.sh --check
packages/dcm-agent/scripts/sync-infra-apigw-pr.sh
```

## Fichiers

| Fichier | Rôle |
|---------|------|
| `packages/dcm-backend/app/main.py` (develop) | Source routes |
| `BA-Data-Connect-Monitoring-infra/Project/IaC/API_GW_2.tf` | Cible Terraform |
| `.github/agents/dp-dcm-sync-infra.agent.md` | Agent (Copilot / Claude / Cursor) |
| `packages/dcm-agent/scripts/sync-infra-apigw-pr.sh` | Commit + push + PR (base develop) |
