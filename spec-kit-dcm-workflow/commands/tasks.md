---
description: "tasks.md + stories from spec (no questions); --consolidate, --add"
tools:
  - bash
---

# DCM Tasks — `tasks.md` + sub-specs depuis la spec

Hook `before_tasks`. Génère `tasks.md` et un sub-spec `stories/T00X-*.md` par task,
**depuis la spec** — pas de questions interactives.

```bash
spec-kit-dcm-workflow/scripts/dcm-model-pref.sh --step tasks   # préférence, pas un lock
```

## User Input

$ARGUMENTS

| Flag | Effet |
|------|-------|
| *(aucun)* | régénère `tasks.md` + `stories/` depuis la spec courante |
| `--append` | ajoute les nouveaux T00X à la suite, sans écraser l'existant |
| `--consolidate` | ramène `tasks.md` à **1 task par domaine** (voir plus bas) |
| `--add` | ajoute une task **après un dispatch** — sub-spec + Story Jira + branche pour elle seule |
| `--spec <feature-dir>` | cible explicite ; sinon le dossier `specs/` le plus récent |

`--consolidate` et `--add` sont mutuellement exclusifs et ne régénèrent rien d'autre.

---

## Génération (mode par défaut)

### Étape 1 — Dossier feature (bloquant)

```bash
./spec-kit-dcm-workflow/scripts/dcm-precheck.sh --gate tasks
.specify/scripts/bash/check-prerequisites.sh --json --paths-only
```

Exit **2** = le scope n'a jamais été persisté (`FEATURE_DIR/intake.json` absent) :
**s'arrêter** et renvoyer l'utilisateur vers `/speckit.dcm.specify --intake-only`. Pas de
tasks depuis une spec non scopée.

### Étape 2 — Charger le scope (aucune question)

Lire en silence `FEATURE_DIR/intake.json` (**`ticket_plan`**, `task_dispatch_mode`,
domaines, packages), `domain-scope.json`, et `spec.md` (Domain Scope, Ticket Plan, User
Stories, Work Breakdown).

Défauts si un champ manque :

- `task_dispatch_mode` ← `intake.task_dispatch_mode` → `dcm-config task_dispatch.mode` → `one_per_domain`
- `expected_story_count` / `ticket_domains` ← `intake.ticket_plan`, sinon dérivés du Work Breakdown

Guides **non bloquants** — une ligne chacun, puis continuer : `plan.md` absent alors que
`work_types.{work_type}.requires_plan` est vrai ; `spec.md` contient encore des
`[NEEDS CLARIFICATION]`. Ne pas AskQuestion, ne pas abandonner.

Récap informatif (feature, work type, tickets → domaines, mode), puis générer.

### Étape 3 — `tasks.md` existant

Par défaut : régénérer depuis la spec courante (écraser `tasks.md`, rafraîchir les stories
des T00X listés). Conserver les fichiers story des ids encore présents, créer les
manquants, ne pas laisser de story requise orpheline. Avec `--append` : ajouter à la
suite avec les ids suivants, sans écraser.

### Étape 4 — Règles de génération

```
FEATURE_DIR: {path}                Work type: {work_type}
Domaines in-scope (lecture): {list}
Domaines AVEC TICKET (= ceux qui reçoivent des tasks): {ticket_plan.ticket_domains}
Stories attendues: {expected_story_count}     Mode: {task_dispatch_mode}
```

- Les T00X se dérivent des **User Stories / Work Breakdown / Ticket Plan de `spec.md`**,
  pas d'un échange en chat.
- Créer **exactement** `expected_story_count` task(s), sauf en mode `granular`.
- Créer des tasks **uniquement** pour les domaines de `ticket_plan.ticket_domains` :
  pas de task Backend ou DataEng si le domaine n'a pas de ticket. Un manque identifié
  en Q6 se documente dans les hypothèses du sub-spec, il ne devient pas un ticket.
- Format de ligne — c'est ce que le parseur lit, pas une convention de style :
  `- [ ] T001 Frontend description → [stories/T001-….md](stories/T001-….md)`
  Domaines reconnus : `frontend`, `backend`, `dataeng`, `devops`, `qa`. Sinon → `misc`.
- **Un sub-spec par task**, obligatoire : `FEATURE_DIR/stories/T00X-{slug}.md` depuis
  `templates/story-spec.template.md`. `tasks.md` est un index ; le détail vit dans
  `stories/`.
- Mode `one_per_domain` : **1 task maximum par domaine avec ticket** — le reste du travail
  descend dans la checklist Sub-tasks du sub-spec. Mode `granular` : une task par User
  Story / ligne de Work Breakdown.
- Multi-domaine ou multi-dev en parallèle → créer `FEATURE_DIR/merge-strategy.md`.
- Pattern de branche dans les sub-specs : `{domain}/{spec_num}-{slug}`.

### Étape 5 — Valider le fichier écrit (bloquant)

`dcm-parse-tasks.sh` est le **seul** lecteur de `tasks.md` pour dispatch / implement /
sync-status. Le lancer juste après l'écriture : une divergence trouvée ici coûte une
édition, trouvée au dispatch elle coûte un mauvais nom de branche.

```bash
spec-kit-dcm-workflow/scripts/dcm-parse-tasks.sh --spec {FEATURE_DIR}
```

| Exit | Sens | Action |
|------|------|--------|
| 0 | toutes les lignes parsées | vérifier que le compte égale `expected_story_count`, continuer |
| **2** | aucune ligne conforme | **corriger `tasks.md`** (format ci-dessus) et relancer — ne pas le passer à dispatch |
| 3 | `dcm-config.yml` illisible | s'arrêter, réparer la config |

Lire les warnings sur stderr : une task qui tombe sur `domain=misc` n'a pas de préfixe de
domaine dans son titre, et sa branche serait `misc/…`. Corriger le titre, ne pas accepter
le fallback.

### Étape 6 — Suite

```
📍 tasks prêtes — tasks.md + {N} sub-spec(s) (parser exit 0)

  Epic Jira + Stories + branches (depuis develop à jour) :
    → /speckit.dcm.dispatch          (--branches-only pour les branches seules)
  Coder :
    → /{speckit}implement T001
  Trop de tasks sur un même domaine :
    → /speckit.dcm.tasks --consolidate
```

---

## `--consolidate` — 1 task par domaine

À utiliser quand la génération a produit trop de tickets (ex. T002–T007 tous Frontend).
Modèle d'équipe DCM : **1 task + 1 sub-spec + 1 branche `{domain}/{spec_num}-{slug}` par
domaine**. Les sous-étapes (tests, utils, correctifs) sont une **checklist dans le
sub-spec**, pas des T00X séparés.

Ajouter `--dry-run` pour ne voir que le plan.

### 1 — Compter par domaine avec le parseur

La colonne `domain` du parseur est celle que dispatch utilisera : compter à la main ici,
c'est consolider sur un autre regroupement que celui qui recevra les branches.

```bash
spec-kit-dcm-workflow/scripts/dcm-parse-tasks.sh --spec {spec-name} \
  | awk -F'\t' '{print $3}' | sort | uniq -c
```

Exit **2** = aucune ligne conforme : il n'y a rien à consolider, le fichier doit d'abord
être remis au format ci-dessus. Ne pas le réécrire à l'aveugle.

Afficher le tableau `Domaine | Tasks | IDs | Cible DCM` + le mode de config.

### 2 — Demander (obligatoire si > 1 task sur un domaine)

```
Tu as {N} tasks {Domaine}. DCM recommande 1 ticket par domaine.

○ Oui — consolider (1 par domaine)
○ Non — garder les tasks détaillées (granular, plusieurs branches)
○ Annuler
```

**Non** → s'arrêter, l'utilisateur garde son `tasks.md`.

### 3 — Fusionner

Pour chaque domaine ayant plus d'une task d'implémentation : une seule ligne dans
`tasks.md`, et les anciennes tasks deviennent la section `## Sub-tasks (merged from
T002–T007)` du sub-spec conservé, avec la liste des fichiers touchés.

Règles :

- Supprimer les tasks purement **Setup** (checkout) sauf demande contraire.
- Replier les phases **test-only** dans le sub-spec du domaine parent.
- Renuméroter T001, T002… séquentiellement dans l'ordre Frontend → Backend → DataEng.
- Supprimer les `stories/T00X-*.md` fusionnés (ou les déplacer dans `stories/archive/`).
- Écrire `tasks-consolidated-log.json` avec le mapping `old_id → new_id`.
- **Relancer le parseur** : `dcm-parse-tasks.sh --spec {spec-name}` doit sortir 0. Une
  consolidation qui casse le format ne se verrait qu'au dispatch.

Rendre le tableau avant/après, puis pointer vers `/speckit.dcm.dispatch`.

Déjà dispatché dans Jira ? Consolider `tasks.md` d'abord ; le resume de dispatch saute les
clés existantes — le ménage Jira reste manuel. Pour garder des tasks fines de façon
durable : `task_dispatch.mode: granular` dans `dcm-config.yml`.

---

## `--add` — ajouter une task après le dispatch

Ajoute un T00X à une spec déjà dispatchée, **sans** recréer l'Epic ni les Stories
existantes. Requiert `--spec <feature-dir>`.

### 1 — Charger l'état

`intake.json`, `domain-scope.json`, `dispatch-manifest.json`, `jira-mapping.json`, et les
ids existants **via le parseur** — l'id le plus haut doit être lu comme dispatch le lit :

```bash
spec-kit-dcm-workflow/scripts/dcm-parse-tasks.sh --spec {spec-name} | cut -f1
```

Exit 2 = format cassé : le réparer avant d'ajouter, sinon la nouvelle task sera la seule
que quiconque dispatchera.

### 2 — Demander

Domaine (Frontend / Backend / DataEng / QA / DevOps), package (depuis l'intake, ou nouveau
si le TL valide), description courte, et **raison de l'ajout tardif** (audit). Domaine
hors intake → prévenir : c'est une extension de scope, mettre à jour `intake.json` et la
table Domain Scope de `spec.md`.

### 3 — Écrire

Id suivant `T{NNN}`, **jamais réutilisé**. Ajouter la ligne à `tasks.md`, créer
`stories/T00X-{slug}.md` depuis le template, ajouter une ligne au Work Breakdown de
`spec.md`. Puis vérifier que le parseur sort 0 **et** liste le nouvel id avec le domaine
choisi (pas `misc`) — c'est de là que vient le nom de branche :

```bash
spec-kit-dcm-workflow/scripts/dcm-parse-tasks.sh --spec {spec-name} | grep '^T00X'
```

Journaliser dans `amend-log.json` (`at`, `task_id`, `domain`, `package`, `reason`, `by`) et
mettre à jour `intake.json` (`amended_at`, `amend_count`).

### 4 — Delta de dispatch

```
/speckit.dcm.dispatch --spec {name}
```

En resume : Epic, Stories et branches existants sont sautés, seuls la Story et la branche
du nouveau T00X sont créés. **Jamais de nouvel Epic**, jamais de renumérotation des T00X
existants, un sub-spec obligatoire pour chaque ajout.

---

## Troubleshooting

| Problème | Correction |
|----------|------------|
| Pas d'`intake.json` | `/speckit.dcm.specify` (ou `--intake-only` puis `/{speckit}specify`) |
| Task sans préfixe de domaine | refuser — ajouter Frontend / Backend / DataEng / QA |
| `stories/T00X.md` manquant | à créer avant de terminer : le sub-spec n'est pas optionnel |
| Confirmation interactive du scope voulue | passer par `/speckit.dcm.specify --intake-only`, puis relancer |
| Parseur exit 2 après édition manuelle | format de ligne : `- [ ] T001 Frontend titre → [stories/…](…)` |
