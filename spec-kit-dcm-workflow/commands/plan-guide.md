---
description: "Validate spec Prerequisites before /{speckit}plan (prerequisite detector)"
tools:
  - bash
---

# DCM Plan Guide — before `/{speckit}plan`

Hook `before_plan`. Le détecteur de prérequis vit dans le gate, pas dans ce fichier :

```bash
PREF=$(spec-kit-dcm-workflow/scripts/dcm-model-pref.sh --step plan 2>/dev/null || true)
[[ -n "$PREF" ]] && echo "DCM model preference — step: plan → $PREF"
./spec-kit-dcm-workflow/scripts/dcm-precheck.sh --gate plan $ARGUMENTS
```

`$ARGUMENTS` accepte `--spec <feature-dir>` ; sans lui le gate prend le dossier
`specs/` le plus récent.

| Sortie | Sens | Suite |
|--------|------|-------|
| **0** | section `## Prerequisites` présente et remplie | enchaîner sur `/{speckit}plan` |
| **2** | section absente, vide, ou pas de `spec.md` | **s'arrêter** et rendre le message du gate à l'utilisateur |

Sur exit 2, ne pas écrire le bloc à la place de l'utilisateur : les cinq templates de
spec en livrent un déjà rempli, donc une section absente ou vide signifie que quelqu'un
l'a retirée — et ce que le plan doit respecter n'est pas devinable. Demander à
l'utilisateur de la compléter, puis relancer le gate.

Rappel à afficher quand le gate passe : découper pour des **PR petites** — chaque
branche fille `{domain}/{spec_num}-{slug}` touche peu de fichiers, la revue humaine
en dépend.
