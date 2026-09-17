---
description: "DCM specify — scope intake (Q1–Q7) then spec.md + intake artefacts"
tools:
  - bash
---

# DCM Specify — intake de scope, puis spec

Point d'entrée DCM d'une feature. Deux phases : l'**intake** (questions à l'utilisateur),
puis l'écriture de `spec.md`. **Ne jamais écrire `spec.md` avant la fin de la phase 1.**

```bash
spec-kit-dcm-workflow/scripts/dcm-model-pref.sh --step specify   # préférence, pas un lock
```

## User Input

$ARGUMENTS

Le texte après la commande est la description de la feature — il sert de résumé (Q7).

| Flag | Effet |
|------|-------|
| `--intake-only` | phase 1 seule : écrit `.specify/pending-intake.json` puis rend la main. C'est ce que lance le hook `before_specify` avant le `/{speckit}specify` natif, et c'est aussi le re-intake manuel |
| `--reuse-intake` | saute les questions et reprend l'intake existant — **opt-in explicite**, jamais déduit |

Appelé **par le hook `before_specify`** (donc avec `--intake-only`) : le `/{speckit}specify`
natif écrit `spec.md` juste après toi. Arrête-toi à la fin de la phase 1 — sinon tu crées
un deuxième dossier `specs/NNN-*`.

---

## Phase 1 — Intake (bloquant : rien d'écrit dans `specs/` avant la fin)

Lire `.specify/extensions/dcm/dcm-config.yml` → `packages`, `scope_presets`,
`work_types`.

### Re-run : chaque invocation est un intake neuf

Sans `--reuse-intake`, un intake existant (`.specify/pending-intake.json` ou
`specs/*/intake.json`) **ne se réutilise pas**. Afficher les valeurs précédentes pour
information, puis reposer Q1 :

```
Intake précédent trouvé :
  Work type : {old_work_type}
  Domaines  : {old_domains}

Tu peux refaire le choix ci-dessous.
```

Même quand l'utilisateur ne veut changer que le work type : reposer **tout** Q1–Q7, les
autres réponses ne restent pas valides par défaut. Puis **écraser** le pending.

Si le dossier feature existe déjà (mise à jour, pas nouvelle spec), demander avant
d'écrire : `oui — écraser intake/domain-scope/spec` ou `non — nouvelle feature`.

### Règles de questionnement

- **Une question à la fois**, attendre la réponse avant la suivante.
- Outil **AskQuestion**, avec `allow_multiple: true` pour les multi-sélections.
- Si AskQuestion est indisponible : afficher les options numérotées et **s'arrêter
  jusqu'à réponse**. Ne jamais inférer — un intake que l'utilisateur n'a pas donné
  pilote la spec, les Stories Jira et les branches.
- **Confirmer** (`OK` / `Rechanger`) après Q1, Q2, Q5 et la résolution de Q6.

### Q1 — Work type (choix unique)

```
Quel type de ticket ?

○ feature    — nouvelle capacité métier
○ technique  — refacto / perf / infra
○ dette      — rembourser dette technique
○ hotfix     — correction prod urgente (max 3 tasks)
○ fixture    — données de test, mocks, fixtures JSON
```

### Q2 — Domaines (multi-sélection directe)

```
Quels domaines concernés ? (plusieurs choix possibles)

☐ Frontend  — packages/dcm-frontend
☐ Backend   — packages/dcm-backend, dcm-commons
☐ DataEng   — collectors, pipeline, lambda
☐ DevOps    — CI/CD, infra
☐ QA        — fixtures, tests transverses
```

Raccourcis optionnels (remplissent les cases) : `frontend_only` → `["frontend"]`,
`backend_only`, `dataeng_only`, `fullstack` → `["frontend","backend"]`,
`full_platform` → `+ dataeng`. `selection_mode` = `"preset"` si raccourci, sinon
`"manual"`. Confirmer avec le tableau ✅/❌ des 5 domaines.

### Q3 — Packages

Si **DataEng** est coché : sous-question obligatoire (`allow_multiple: true`) sur les
packages DataEng de `dcm-config.yml`. Frontend / Backend seuls : packages auto-remplis
depuis le registre, pas de question sauf chemin custom.

### Q4 — Priorité (choix unique) : `P0` (prod down) · `P1` · `P2` · `P3`

### Q5 — Ticket plan (bloquant — pilote spec + dispatch)

**Le nombre de tickets = nombre de Stories Jira = nombre de branches filles = nombre de
sub-specs.**

```
Combien de tickets (Stories) pour cet Epic ?

○ 1 ticket   — un seul domaine (je précise lequel)
○ N tickets  — 1 par domaine coché en Q2 (recommandé multi-dev)
○ custom     — je choisis quels domaines reçoivent un ticket (multi-select)
```

Modes : `single_domain` | `one_per_domain` | `custom`. Récapituler **toujours**, en
nommant les domaines in-scope **sans** ticket — ils sortent de la spec, des tasks et du
dispatch :

```
Plan tickets :
  Stories Jira prévues : {count}
  Domaines avec ticket : {ticket_domains}
  Domaines in-scope SANS ticket : {domains - ticket_domains} → hors spec/tasks/dispatch
```

### Q6 — Vérification code (bloquant — après Q5)

Ordre imposé : choix utilisateur (Q2 + Q5) → **recherches réelles** → tableau de preuves
→ **puis** les choix. Chaque ligne du tableau est un résultat de `rg`/lecture **avec son
chemin**, ou « non trouvé après recherche ». Ne jamais inventer une route ou un fichier :
si la recherche n'a pas tourné, écrire `⚠️ recherche non effectuée`. La conclusion se
dérive du tableau.

Extraire les mots-clés du résumé, puis chercher au minimum, côté API et côté UI :

```bash
rg -l "{keywords}" packages/dcm-backend/app/api/routes/ --glob "*.py"
rg "router\.(get|post)|Query\(" packages/dcm-backend/app/api/routes/{hit}.py
rg -l "{keywords}" packages/dcm-frontend/src/ --glob "*.{ts,tsx}"
```

**Message 1 — constats seuls** (pas encore de boutons) :

```
🔍 Vérification code — "{summary}"  (étape 1/2)

Ton choix actuel : {expected_story_count} ticket(s) → {ticket_domains}

| # | Vérification | Résultat | Preuve (fichier) |
|---|--------------|----------|------------------|
| 1 | API qui expose la donnée | ✅ trouvé | `clusters.py` → GET `/api/v1/compute` |
| 2 | Champ nécessaire dans la réponse | ✅ trouvé | `types/api.ts` → `ComputeState` |
| 3 | Filtre / param côté serveur | ❌ absent | pas de `Query("inactive")` |
| 4 | Filtre équivalent côté front | ✅ trouvé | `useClustersPageData.ts` → `stateFilter` |
| 5 | Page / widget existant | à préciser | `Clusters.tsx` existe ; widget = nouveau |
```

Arbre de décision à appliquer sur ces lignes :

| #1 donnée API | #3 filtre serveur | #4 filtre client | Conclusion |
|---------------|-------------------|------------------|------------|
| ✅ | ✅ | — | backend prêt — le domaine du ticket suffit |
| ✅ | ❌ | ✅ | filtrage côté UI possible |
| ✅ | ❌ | ❌ | données brutes seulement → mock ou ticket backend |
| ❌ | — | — | rien côté API → ticket backend ou mock total |

Si le ticket plan inclut déjà Backend : tableau informatif, pas de flow de gap.

**Message 2 — les choix seuls**, une fois le tableau acquis :

| Proposition à l'utilisateur | `resolution` persistée |
|-----------------------------|------------------------|
| C'est bon — l'API suffit | `backend_ready` |
| {Domaine} seul avec mock / filtre côté UI | `frontend_only_with_mock` |
| Ajouter un ticket Backend (Epic à 2 Stories) | `add_backend_ticket` → **re-jouer Q5** |
| Reporter | `deferred` |
| Annuler | recommencer l'intake |

Confirmer la résolution avant d'écrire l'intake.

### Q7 — Résumé en une phrase (si absent de `$ARGUMENTS`)

### Sortie de la phase 1 — `.specify/pending-intake.json`

```json
{
  "work_type": "feature",
  "domains": ["frontend", "backend"],
  "ticket_plan": {
    "mode": "single_domain",
    "ticket_domains": ["frontend"],
    "expected_story_count": 1
  },
  "dependency_gaps": [
    {
      "need": "API filtre clusters inactive",
      "required_domain": "backend",
      "ticket_planned": false,
      "resolution": "frontend_only_with_mock",
      "evidence": "packages/dcm-backend/app/api/routes/clusters.py — no inactive filter",
      "spec_note": "GET /compute + filtre client state=inactive ; fixture MSW pour les tests"
    }
  ],
  "packages": ["packages/dcm-frontend"],
  "priority": "P2",
  "preset": "frontend_only",
  "selection_mode": "preset",
  "summary": "Add widget inactive cluster on dashboard",
  "created_at": "ISO8601"
}
```

Aucun gap → `"dependency_gaps": []`. Afficher le récap (work type, mode, domaines ✅/❌,
**tickets Jira** → domaines, gaps, packages, priorité), puis :

- `--intake-only` → **stop ici**, la main revient à l'appelant.
- sinon → attendre la confirmation utilisateur, puis phase 2.

---

## Phase 2 — Écrire la spec

```bash
./spec-kit-dcm-workflow/scripts/dcm-precheck.sh --gate specify
```

Exit **2** = pas d'intake frais (fichier absent, `work_type` vide, ou résidu d'un specify
précédent). **S'arrêter** et rendre le message du gate : la phase 1 n'a pas abouti, ou le
pending est celui d'une autre feature. Ne pas écrire `spec.md` depuis une demande non
scopée.

### 2.1 — Dossier feature

Nom court (2–4 mots, kebab-case) depuis le résumé → `SPECIFY_FEATURE_DIRECTORY` sous
`specs/` (`NNN` séquentiel ou timestamp selon `.specify/init-options.json`) → `mkdir -p`.

**Tracking tokens — début d'étape** (dès que `FEATURE_DIR` existe ; ignoré en
`--intake-only`, le tracking se fait au passage phase 2 complet) :

```bash
spec-kit-dcm-workflow/scripts/dcm-step-start.sh \
  --feature-dir "$FEATURE_DIR" --step specify
```

### 2.2 — Artefacts d'intake

```bash
cp .specify/pending-intake.json "$SPECIFY_FEATURE_DIRECTORY/intake.json"
```

Générer `domain-scope.json` : `work_type`, `domains` (les 5 clés en booléens),
`packages`, `priority`.

**Puis supprimer `.specify/pending-intake.json`.** Ce n'est pas cosmétique : un pending
oublié garde `--gate specify` vert pour toutes les features suivantes, et la spec d'après
héritait silencieusement du scope de celle-ci. Le gate refuse désormais un pending
byte-identique à un `intake.json` déjà persisté — donc l'oubli se voit, mais au prix d'un
blocage.

### 2.3 — spec.md depuis le template DCM

`.specify/extensions/dcm/templates/spec.md` → `FEATURE_DIR/spec.md` (jamais le
spec-template générique de speckit). Le template couvre les 5 work types : **supprimer les
blocs `[work_type: …]` qui ne concernent pas le work type retenu**, marqueur compris, puis
remplir :

| Section | Règle |
|---------|-------|
| **Domain Scope** | les 5 lignes, ✅/❌ depuis l'intake (lecture) |
| **Ticket Plan** | domaine → ticket oui/non ; total = `expected_story_count` |
| **Dependency Analysis** | constats Q6 + choix utilisateur (`resolution`) |
| **Prerequisites** | **obligatoire** — small branches / small PRs, intake confirmé, deps bloquantes résolues ou reportées. Le hook `before_plan` refuse une section vide |
| **User stories** | **uniquement** pour `ticket_plan.ticket_domains` |
| **Work Breakdown preview** | une ligne par domaine avec ticket (T001, T002…) |
| **Out of scope (this Epic)** | domaines in-scope sans ticket, avec la raison |
| **Input** | le résumé utilisateur |

Écrire `.specify/feature.json` : `{ "feature_directory": "specs/NNN-short-name" }`.

### 2.4 — Checklist qualité

`checklists/requirements.md` (validation speckit standard). Max 3 marqueurs
`[NEEDS CLARIFICATION]` dans la spec.

---

## Phase 3 — Rapport

Récap (dossier, work type, domaines, **tickets Jira** → domaines, gaps, packages,
priorité, fichiers créés) puis la suite :

```
📍 PROCHAINES ÉTAPES

  Scope / type / tickets pas sûrs ?
    → /speckit.dcm.specify --intake-only   (re-intake complet)

  Recommandé avant tasks (rien n'est imposé) :
    1. /{speckit}clarify   — résoudre les [NEEDS CLARIFICATION]
    2. /{speckit}plan      — plan technique (hook before_plan = gate Prerequisites)
    3. /speckit.dcm.tasks — tasks.md + stories/T00X.md depuis la spec, sans questions
                            ({expected_story_count} task(s) attendue(s))

  Sautable pour hotfix / fixture / urgence — l'agent ne bloque pas.

  Jira + git :
    → /speckit.dcm.dispatch   (1 Epic + {expected_story_count} Story(ies) + branches
                               depuis develop à jour ; --jira-only / --branches-only)
  Coder :
    → /{speckit}implement T001
```

## Usage log (tokens / modèle)

**Au début** (dès que `FEATURE_DIR` existe — voir § 2.1) :

```bash
spec-kit-dcm-workflow/scripts/dcm-step-start.sh \
  --feature-dir "$FEATURE_DIR" --step specify
```

**À la fin** de la commande (intake + spec écrits), mesure depuis les logs Claude ou Copilot :

```bash
spec-kit-dcm-workflow/scripts/dcm-track-session.sh \
  --feature-dir "$FEATURE_DIR" --step specify
```

`--intake-only` : pas de tracking ici (pas encore de `FEATURE_DIR`) — le tracking se fait
au passage phase 2 complet ou au `/{speckit}specify` natif qui suit.

Ne **pas** appeler `dcm-render-usage-report.sh` ici — le rapport est généré via
`/speckit.dcm.usage-report` uniquement.

## Troubleshooting

| Problème | Correction |
|----------|------------|
| L'agent a sauté les questions | relancer — la phase 1 est obligatoire, Q1–Q7 à chaque fois |
| Re-run pour changer le work type | reposer Q1–Q7 ; pas de réutilisation silencieuse |
| Mauvais domaines / preset choisi par erreur | `--intake-only` : Q1–Q7 rejouées, pending écrasé |
| Garder l'intake précédent sans questions | `--reuse-intake`, explicitement |
| `--gate specify` exit 2 alors qu'on vient de faire l'intake | le pending est un résidu : le supprimer puis refaire l'intake (message du gate) |
| Spec générique, sans Domain Scope | `templates/spec.md` non utilisé — repartir de lui |
| Blocs `[work_type: …]` d'un autre work type restés dans la spec | les supprimer : le template les liste, l'agent les élague |
| Tasks Backend alors qu'un seul ticket Frontend | `/speckit.dcm.tasks` suit `ticket_domains` — task Backend interdite |
