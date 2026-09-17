# Démarrer avec spec-kit + l'extension DCM

Installation depuis zéro, 15 minutes, une fois par machine.
Référence du flow et des commandes : [GUIDE.md](./GUIDE.md), qui fait foi.

## 1. Choisir son hôte — l'un **ou** l'autre

Un dépôt ne porte qu'une intégration (`specify integration switch <clé>` pour changer).

| | **Claude Code** | **GitHub Copilot** (VS Code) |
|---|---|---|
| `specify init` | `--integration claude` | `--integration copilot` |
| Commandes de base | **`/speckit-plan`** (skills) | **`/speckit.plan`** (prompt files) |
| MCP | `.mcp.json` (`mcpServers`) | `.vscode/mcp.json` (`servers` + `inputs`) |
| Gate `git commit` | hook agent **+** `.git/hooks/pre-commit` | `.git/hooks/pre-commit` seulement |

Le tiret côté Claude n'est pas un bug : un nom de skill ne peut pas contenir de point
(`--integration-options="--skills"` aligne Copilot dessus). Les commandes **DCM**, elles, sont
des fichiers → `/speckit.dcm.*` partout, et `install.sh` les génère pour les deux hôtes.

## 2. Installer

Rien de tout ça n'arrive par `git pull` : `.specify/`, `.claude/`, `CLAUDE.md`,
`.github/agents|prompts/`, `.agents/skills/`, `.vscode/` sont **gitignorés**.
Prérequis : `python3` ≥ 3.9, `bash` 3.2, `git`, [uv](https://docs.astral.sh/uv/). Pas de `yq`.

```bash
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git
specify --version                     # → 0.11.6, version de référence de l'équipe

git clone git@github.com:TotalEnergiesCode/dataint-dcm-app.git && cd dataint-dcm-app

# UNE SEULE ligne, celle de votre hôte — sinon aucune commande de base
specify init --here --integration claude --ignore-agent-tools
specify init --here --integration copilot

git diff .github/copilot-instructions.md    # 🔴 voir ci-dessous

./spec-kit-dcm-workflow/scripts/install.sh  # extension DCM, skills, subagent, hook de commit
```

Puis **redémarrer la session** Claude Code (les hooks sont lus au démarrage) ou
`Developer: Reload Window` sous VS Code.

Trois pièges, tous rencontrés :

- **`Agent Detection Error` / `claude not found`** → `--ignore-agent-tools`. Le flag ne saute
  que la détection du binaire, absente via l'extension IDE ; le scaffold est identique.
- **`.github/copilot-instructions.md` est suivi par git** et chaque `init` réécrit son bloc
  `SPECKIT`, ce qui casse la ligne « Plan actif ». `git checkout --` dessus si le diff le montre.
- **`install.sh` installe l'extension DCM, pas spec-kit** : sans `init`, vous aurez les 9
  `/speckit.dcm.*` et aucune commande de base, sans aucun message d'erreur.

> État du dépôt : intégration installée = **`claude`**. Sous Copilot :
> `specify integration switch copilot` — c'est local, ces répertoires sont gitignorés.

## 3. MCP Jira / GitHub

Le serveur Jira doit s'appeler exactement **`atlassian`** (valeur de `mcp_server` dans la
config) : les noms d'outils MCP en dérivent. Transport `/v1/mcp`.

- **Claude Code** — `.mcp.json`, déjà versionné avec `atlassian`. Pas de serveur `github`, donc
  `publish-pr` n'ouvre pas de PR via MCP en l'état ; template dans `claude-code/`.
- **Copilot** — `.vscode/mcp.json`, gitignoré, à créer par poste (schéma `servers` + `inputs`).

## 4. Vérifier

```bash
specify extension list                            # → DCM Team Workflow (v2.9.2) ✓
ls -l .git/hooks/pre-commit                       # → présent, exécutable
./spec-kit-dcm-workflow/scripts/dcm-selftest.sh   # → OK, 0 failed
ls -d .claude/skills/speckit-plan                 # Claude Code — sinon § 2
ls .github/prompts/speckit.plan.prompt.md         # Copilot     — sinon § 2
```

Version périmée dans `extension list` = le sync a recopié sans réenregistrer → `install.sh`.

## 5. Lancer

Depuis `develop` à jour, dans le chat :

```
/speckit.dcm.specify "afficher le nom du workspace dans le header"
```

L'intake pose le scope, puis écrit `specs/NNN-slug/spec.md` + `intake.json`. Aucune branche
créée. La suite (`plan` → `tasks` → `dispatch` → `implement` → `review --commit` →
`publish-pr` → `sync-status`) : [GUIDE.md](./GUIDE.md). À retenir dès maintenant : **`git commit`
est refusé sans `/speckit.dcm.review --commit`**.

## 6. Après un `git pull`

`sync-dcm-extension.sh` regénère les artefacts (`install.sh` si la version a bougé), puis
redémarrer la session. Votre `dcm-config.yml` est préservé.

## 7. Dépannage

| Symptôme | Cause |
|----------|-------|
| commande de base inconnue, mais `/speckit.dcm.*` marche | `init` non lancé pour cet hôte → § 2 |
| `/speckit.dcm.*` inconnu | session / fenêtre non redémarrée, ou `install.sh` non lancé |
| commandes DCM absentes du chat Copilot | mode Agent désactivé ou prompt files interdits |
| MCP Jira introuvable | serveur mal nommé, ou `.vscode/mcp.json` absent → § 3 |
| `git commit` refusé après une review | le diff *staged* a changé → relancer `--commit` |
| `git commit` passe sans review | `.git/hooks/pre-commit` absent → § 6 |
| subagent `dataeng` non résolu | plugin APM `…/data-integration` absent pour cet hôte → GUIDE.md § 4 |
| un gate ne fait pas ce que la doc dit | `dcm-selftest.sh` |

Aussi : [CONTRACTS.md](./CONTRACTS.md) (schémas JSON) ·
[USAGE-AND-TOKENS.md](./USAGE-AND-TOKENS.md) (tokens) · `commands/*.md` (comportement exact).
