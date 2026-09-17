# Guide visuel — Onboarding LZ DCM

Guide interactif pour onboarder une **Landing Zone cliente** dans Data Connect Monitoring.

## Ouvrir le guide

**Dans l’application DCM** (recommandé) :

```text
http://localhost:4000/guide/lz-onboarding
```

Bouton **Guide** (header) → **LZ onboarding guide**.

**Fichier HTML standalone** (hors app, option dev) :

```bash
cd packages/dcm-agent/docs/onboarding-guide && python3 -m http.server 8765
```

## Contenu

| Fichier | Sujet |
|---------|--------|
| [index.html](./index.html) | Guide interactif (checklist, schémas, parcours) |
| [00-architecture.md](./00-architecture.md) | Où tourne le collector (Core vs LZ) |
| [01-install-agent.md](./01-install-agent.md) | Installation `@dp-dcm-lz-client` |
| [02-phases-checklist.md](./02-phases-checklist.md) | 7 phases — qui fait quoi |
| [03-phase-5-2-deploy.md](./03-phase-5-2-deploy.md) | Déployer le code collector (étape la plus confuse) |
| [04-network-egress.md](./04-network-egress.md) | Prérequis firewall — flux HTTPS à ouvrir (Entra, Apigee, ECR) |
| [assets/](./assets/) | Screenshots (à compléter par l’équipe) |

## Public

- Équipe LZ / Cloud Ops — première onboarding
- Collègue DevOps — reprise de travail

Complète le [GUIDE-UTILISATEUR.md](../GUIDE-UTILISATEUR.md) (référence texte) et le handoff DevOps dans `BA-Data-Connect-Monitoring-infra/DCM-client-LZ-onboarding-handoff.md`.

**Doc équipe (repo `docs/`) :** [docs/07-lz-onboarding/README.md](../../../../docs/07-lz-onboarding/README.md) — schéma archi, push/pull ECR, checklist nouvelle LZ.

## Captures d’écran

Voir [assets/README.md](./assets/README.md) pour la liste des PNG à ajouter.
