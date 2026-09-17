# DCM Agent — Data Connect Monitoring

Agent **`dp-dcm-lz-client`** — onboarding LZ DCM.

Source : `packages/dcm-agent/` dans **dataint-dcm-app**.

---

## Installation (GitHub Copilot)

Repo déjà cloné :

**Windows**
```powershell
cd C:\chemin\vers\dataint-dcm-app
git pull
.\packages\dcm-agent\install.ps1 -Global
```

**Mac / Linux**
```bash
cd dataint-dcm-app
git pull
bash packages/dcm-agent/install.sh --global
```

Recharge la fenêtre VS Code → chat Copilot → `@dp-dcm-lz-client`

---

## Réinstaller

```bash
cd dataint-dcm-app
git pull
bash packages/dcm-agent/install.sh --global
```

Windows : `.\packages\dcm-agent\install.ps1 -Global`

---

## Usage

```
@dp-dcm-lz-client Onboarder une nouvelle LZ dans DCM
```

| Guide | Usage |
|-------|--------|
| **[Guide visuel dans l’app DCM](/guide/lz-onboarding)** | Parcours phases, checklist — `localhost:4000/guide/lz-onboarding` |
| [Guide HTML standalone](docs/onboarding-guide/index.html) | Copie hors app (option dev) |
| [GUIDE-UTILISATEUR.md](docs/GUIDE-UTILISATEUR.md) | Référence texte complète |
