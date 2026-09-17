# Installation de l’agent DCM

## Prérequis outils

| Outil | Commande |
|-------|----------|
| GitHub CLI | `gh --version` |
| APM | `apm --version` |
| Azure CLI | `az --version` |
| jq (recommandé) | `jq --version` |

## Installer l’agent (Mac / Linux)

```bash
git clone git@github.com:TotalEnergiesCode/dataint-dcm-app.git
cd dataint-dcm-app
git checkout develop
chmod +x packages/dcm-agent/install.sh
./packages/dcm-agent/install.sh --global
```

## Windows

```powershell
cd dataint-dcm-app
git pull
.\packages\dcm-agent\install.ps1 -Global
```

## Vérifier dans Copilot

1. Recharger VS Code
2. Ouvrir Copilot Chat
3. Taper `@` → choisir **`dp-dcm-lz-client`**

![Copilot agent list](./assets/01-copilot-agent-list.png)

> Si l’image manque : capture Copilot avec `@dp-dcm-lz-client` visible.

## Connexion Azure avant session

```bash
az logout
az login --tenant "329e91b0-e21f-48fb-a071-456717ecc28e" \
  --scope "https://api-aad.pf-identity.iasp.tgscloud.net/.default"
```

Choisir la **subscription de la LZ que tu onboardes** (ex. novadatahub → `sub-iasp-lz-novadatahub`, DataSquad → `sub-iasp-lz-DataSquad`). Pas la subscription DCM Core.

![Subscription picker](./assets/03-az-login-subscription.png)

## Invoquer l’agent

```
@dp-dcm-lz-client Azure : sub-iasp-lz-novadatahub, env=m, subscription_id=77180ab7-ad22-4e7e-aa0b-e2f909e6d0fa, prenom.nom@totalenergies.com
```

![Invoke agent](./assets/02-copilot-invoke.png)
