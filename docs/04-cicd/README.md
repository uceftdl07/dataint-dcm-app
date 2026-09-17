# CI/CD — GitHub Actions Workflows

Ce dossier documente les workflows GitHub Actions de la repo `dataint-dcm-app`.
Chaque package du dossier `packages/` a son propre workflow, isolé et déclenché
uniquement quand son code (ou ses dépendances internes) change.

## Sommaire

| Workflow | Fichier | App | Cible de déploiement |
|---|---|---|---|
| [dcm-backend](#dcm-backend) | `.github/workflows/dcm-backend.yml` | API FastAPI Python | ECR + ECS Fargate |
| [dcm-frontend](#dcm-frontend) | `.github/workflows/dcm-frontend.yml` | App React/Vite | S3 static + CloudFront |
| [dcm-lambda-ingestion](#dcm-lambda-ingestion) | `.github/workflows/dcm-lambda-ingestion.yml` | Lambda Python | S3 artifact + AWS Lambda |
| [dcm-aws-collector](#dcm-aws-collector) | `.github/workflows/dcm-aws-collector.yml` | Collecteur AWS Python | ECR |
| [dcm-azure-collector](#dcm-azure-collector) | `.github/workflows/dcm-azure-collector.yml` | Collecteur Azure Python | ECR |

---

## Principes communs

### Stratégie de branches & environnements

| Événement | Branche | Action |
|---|---|---|
| `push` (merge) | `main` | test + build + **deploy → `prod`** |
| `push` (merge) | `develop` | test + build + **deploy → `dev`** |
| `pull_request` | n'importe quelle branche cible | test + build (pas de deploy) |
| `push` direct | autre branche (`feature/*`, etc.) | test + build (pas de deploy) |
| `workflow_dispatch` (manuel) | branche choisie dans l'UI | test + build, et deploy → `dev` ou `prod` selon les inputs |

Le job `setup` placé en tête de chaque workflow résout dynamiquement la cible :

```yaml
if workflow_dispatch                  → environment = inputs.environment (dev|prod)
                                        deploy = inputs.deploy
elif push && ref == refs/heads/main   → environment = prod
elif push && ref == refs/heads/develop → environment = dev
else                                  → should_deploy = false
```

### Déclenchement manuel (`workflow_dispatch`)

Tous les workflows peuvent être lancés à la main via l'UI GitHub
(`Actions → choisir le workflow → Run workflow`). Trois choix offerts :

1. **Branch** (champ natif GitHub) — sélectionner la branche / tag à exécuter.
2. **Target environment** (`dev` ou `prod`) — détermine l'environnement
   GitHub à charger (secrets, variables, règles de protection).
3. **Run deploy step** (case à cocher, par défaut `true`) — décocher pour
   ne lancer que **test + build** sans déploiement (utile pour valider
   une branche de feature contre les secrets `dev`/`prod`).

> **Note** : la combinaison `branch=feature/X` + `environment=prod` est
> possible côté workflow, mais sera filtrée par les protections
> d'environnement GitHub : si `prod` a `Deployment branches limited to main`,
> GitHub bloquera le job `deploy` avec un message clair.

L'environnement choisi est passé au job `deploy` via `environment:` GitHub.
Cela permet de définir des **variables et secrets différents par environnement**
dans les settings GitHub (`Settings → Environments`), et d'activer des
règles de protection (reviewers requis sur `prod`, par exemple).

### Déclencheurs
- `push` sur `main` ou `develop` → pipeline complète (test + build + deploy).
- `pull_request` ciblant `main` ou `develop` → test + build seulement.
- Filtrage par `paths:` : un workflow ne se déclenche que si les fichiers de
  son package (ou de `dcm-commons` quand le package en dépend) ont changé.
  Cela évite de rebuilder tout le monde à chaque commit.

### Architecture en 4 jobs
Chaque workflow est découpé en quatre jobs chaînés via `needs:` :

```
┌───────┐    ┌──────┐    ┌───────┐    ┌────────┐
│ setup │ ─> │ test │ ─> │ build │ ─> │ deploy │
└───────┘    └──────┘    └───────┘    └────────┘
   (résout l'env. cible)              (skip si autre branche)
```

- **`setup`** : détermine `deploy_env` (`prod` / `dev` / vide) et
  `should_deploy` (`true` / `false`) en fonction de la branche poussée.
  Ces valeurs sont exposées en `outputs` et consommées par `deploy`.
- **`test`** : qualité du code (ruff, mypy, pytest pour Python ; ESLint + tsc
  pour le frontend). Tourne sur PR comme sur push.
  - `ruff`, `mypy`, `eslint` et `tsc --noEmit` sont **non-bloquants**
    (`continue-on-error: true`) : leurs résultats sont publiés dans le
    **GitHub Step Summary** du run pour traitement ultérieur, mais
    n'arrêtent pas la pipeline.
  - `pytest` reste **bloquant** : un test qui échoue fait tomber le job.
  - **Note frontend** : le script `build` du `package.json` appelle
    uniquement `vite build` (pas `tsc && vite build`), pour que les
    erreurs de type ne bloquent pas non plus le job `build`. Vite/esbuild
    transpile en ignorant les erreurs de type ; la vérification des types
    reste assurée par le step `tsc --noEmit` du job `test` (en rapport).
- **`build`** : produit l'artefact (image Docker en tarball, zip Lambda,
  bundle Vite) et le publie via `actions/upload-artifact`. **Tourne aussi
  sur les branches non déployées**, pour valider que le code compile.
- **`deploy`** : conditionnel à `needs.setup.outputs.should_deploy == 'true'`.
  Consomme l'artefact, l'envoie sur AWS (ECR / S3 / Lambda) et déclenche
  le rollout sur l'environnement cible. Skippé sur les branches autres
  que `main` et `develop`.

> **Pourquoi ce découpage ?** Si la pipeline tombe, on sait immédiatement où :
> un échec dans `build` = problème de compilation/packaging ;
> un échec dans `deploy` = problème d'infra/IAM/rollout AWS.
> Le job `deploy` ne reconstruit jamais — il déploie exactement ce que `build`
> a produit.

### Stack & versions
- **Python 3.12** pour tous les services Python, installé via `uv` (rapide,
  installe dépendances et toolchain).
- **Node.js 20** pour le frontend, avec `npm ci` (lockfile strict).
- **Docker Buildx** + cache GitHub Actions (`type=gha`) pour les images.

### Authentification AWS
Toutes les interactions AWS utilisent **OIDC** via
`aws-actions/configure-aws-credentials@v4`. Aucune clé statique n'est stockée
dans les secrets — seul le rôle IAM est référencé via `secrets.AWS_ROLE_ARN`.

### Variables & secrets requis

Toutes les variables d'infrastructure sont **scopées par environnement GitHub**
(`prod` et `dev`) — chaque environnement pointe vers ses propres ressources
cloud (buckets, ECR repos, ACR, services ECS, fonction Lambda, etc.).

| Type | Nom | Niveau | Usage |
|---|---|---|---|
| Secret | `AWS_ROLE_ARN` | Environnement | Rôle IAM assumé via OIDC (un rôle distinct par env) |
| Secret | `AWS_COLLECTOR_AWS_ROLE_ARN` | Environnement | Rôle IAM optionnel dédié au collecteur AWS; si absent, fallback sur `AWS_ROLE_ARN` |
| Secret | `AWS_FRONTEND_ROLE_ARN` | Environnement | Rôle IAM OIDC dans le compte workload (**dev** `551656632516` / **prod** `884068385310`) pour S3 + CloudFront — **ne pas** utiliser `AWS_ROLE_ARN` (`551656632516`) |
| Secret | `FRONTEND_BUCKET` | Environnement | Bucket S3 servant le frontend |
| Secret | `CLOUDFRONT_DISTRIBUTION_ID` | Environnement | Distribution CloudFront du frontend |
| Secret | `BACKEND_ECR_REPOSITORY` | Environnement | Repo ECR du backend |
| Secret | `BACKEND_ECS_CLUSTER` | Environnement | Cluster ECS du backend |
| Secret | `BACKEND_ECS_SERVICE` | Environnement | Service ECS du backend |
| Secret | `DCM_DATABRICKS_SPN_CLIENT_SECRET_ARN` | Environnement | ARN du secret Secrets Manager → client secret du SPN Databricks |
| Secret | `AZURE_TENANT_ID` | Environnement | Tenant Microsoft Entra ID (frontend SPA et login OIDC Azure) |
| Secret | `APP_ID` | Environnement | App Registration (Client) ID du SPA dcm-frontend — injecté en `VITE_AZURE_CLIENT_ID`; fallback pour le login ACR du collecteur Azure si `AZURE_CLIENT_ID` n'est pas défini |
| Secret | `AZURE_SCOPE` | Environnement | Scope OAuth utilisé pour appeler le backend (ex. `api://<backend-app-id>/access_as_user`) |
| Secret/Variable | `AZURE_CLIENT_ID` | Environnement | Client ID du SP Builder Azure (`AZURE_BUILDER_*`) pour deploy App Service |
| Secret/Variable | `AZURE_SUBSCRIPTION_ID` | Environnement | Subscription Azure LZ (deploy App Service) — optionnel si cible dans `azure-collector-deploy-targets.json` |
| Variable | `AWS_REGION` | Environnement | Région AWS (défaut workflow AWS collector: `eu-central-1`) |
| Variable | `AWS_COLLECTOR_ECR_REGISTRY` | Environnement | Registry ECR central DCM (`551656632516.dkr.ecr.eu-central-1.amazonaws.com`) |
| Variable | `LAMBDA_FUNCTION_NAME` | Environnement | Fonction Lambda d'ingestion |
| Variable | `LAMBDA_LAYER_NAME` | Environnement | Nom de la Lambda Layer qui porte les dépendances Python |
| Variable | `LAMBDA_ARTIFACTS_BUCKET` | Environnement | Bucket S3 pour les zips Lambda (layer + function) |
| Variable | `AWS_COLLECTOR_ECR_REPOSITORY` | Environnement | Repo ECR du collecteur AWS (défaut workflow: `dcm-aws-collector`) |
| Variable | `AZURE_COLLECTOR_ECR_REPOSITORY` | Environnement | Repo ECR du collecteur Azure (défaut workflow: `awsd-dcm-azure-collector`) — **même registry** `551656632516` |
| Variable | `VITE_API_BASE_URL` | Environnement | URL publique du backend dcm-backend |
| Variable | `VITE_REDIRECT_URI` | Environnement | URI de redirection après login Entra ID |
| Variable | `VITE_ENABLE_AUTH` | Environnement | `true`/`false` — active ou bypasse l'authentification |
| Variable | `SQS_QUEUE_URL` | Environnement | URL de la queue SQS d'ingestion |
| Variable | `ENVIRONMENT` | Environnement | Code court d'env (`d` / `p`) — utilisé par le backend |
| Variable | `DCM_ENVIRONMENT` | Environnement | Code long d'env (`development` / `production`) |
| Variable | `DCM_APP_NAME` | Environnement | Nom logique de l'app (`dcm-backend`) |
| Variable | `DCM_DATABRICKS_HOST` | Environnement | Host Databricks sans `https://` |
| Variable | `DCM_DATABRICKS_WAREHOUSE_ID` | Environnement | ID du SQL Warehouse utilisé par le backend |
| Variable | `DCM_DATABRICKS_HTTP_PATH` | Environnement | Override optionnel du HTTP path Warehouse |
| Variable | `DCM_DATABRICKS_CATALOG` | Environnement | Catalogue Unity Catalog (ex. `it`) |
| Variable | `DCM_DATABRICKS_SCHEMA` | Environnement | Schéma Unity Catalog (ex. `ba_data_connect_monitoring__a`) |
| Variable | `DCM_DATABRICKS_SPN_CLIENT_ID` | Environnement | Client ID du SPN Databricks |
| Variable | `DCM_ALLOWED_ORIGINS` | Environnement | Liste JSON des origines CORS autorisées |
| Variable | `POWERTOOLS_SERVICE_NAME` | Environnement | Service name pour Lambda Powertools (ex. `dcm-backend`) |

> **Pourquoi en secrets ?** Ces 5 valeurs (buckets S3, distribution
> CloudFront, repo ECR, cluster/service ECS) exposent des identifiants
> de ressources AWS internes qui ne doivent pas se retrouver en clair
> dans les logs GitHub ni dans le code de la repo. Les **secrets** sont
> masqués automatiquement dans les logs (remplacés par `***`), ce qui
> n'est **pas** le cas des `vars`.

**Configuration GitHub requise** :

1. Créer deux environnements dans `Settings → Environments` :
   - `prod` (avec, idéalement, *Required reviewers* + `Deployment branches` limité à `main`)
   - `dev` (avec `Deployment branches` limité à `develop`)
2. Pour chacun, renseigner le secret `AWS_ROLE_ARN` et toutes les variables
   ci-dessus avec les valeurs propres à l'environnement.

---

## dcm-backend

**Fichier :** `.github/workflows/dcm-backend.yml`
**App :** API FastAPI Python 3.12 (`packages/dcm-backend/`)
**Cible :** image Docker dans ECR, déployée sur ECS Fargate.

### Job `test`
1. Checkout + installation `uv` avec cache.
2. `uv pip install --system -e ".[dev]"` pour installer le package + extras de dev.
3. Quality gates :
   - `ruff check .` (lint)
   - `mypy app` (type check strict)
   - `pytest` (tests unitaires + intégration)

### Job `build`
- Tourne sur **toute branche** (PR comprise) pour valider la construction.
- `docker buildx build` **sans push** vers ECR → produit un tarball
  `/tmp/dcm-backend-image.tar` uploadé comme artefact.
- Cache Docker via `type=gha` (réutilisé entre runs).

### Job `deploy`
- Conditionnel : `needs.setup.outputs.should_deploy == 'true'`.
- Cible l'environnement GitHub résolu par `setup` (`prod` ou `dev`).
- Lit `BACKEND_ECR_REPOSITORY`, `BACKEND_ECS_CLUSTER`, `BACKEND_ECS_SERVICE`
  (en secrets) → ECR repo et service ECS différents selon prod/dev.
- Étapes :
  1. Auth AWS via OIDC → login ECR → `docker load` du tarball →
     push de l'image avec deux tags (`:${{ github.sha }}` et `:latest`).
  2. **Render new task definition** : récupère la révision active de la
     task definition utilisée par le service (`describe-services` →
     `describe-task-definition`), strippe les champs read-only
     (`taskDefinitionArn`, `revision`, `status`, …), puis patche le
     premier container avec :
     - `image` → la nouvelle image ECR taguée par SHA ;
     - `environment[]` → liste construite à partir des `vars` GitHub
       (`DCM_DATABRICKS_*`, `SQS_QUEUE_URL`, `ENVIRONMENT`, etc.) ;
     - `secrets[]` → références aux entrées Secrets Manager via
       `DCM_DATABRICKS_SPN_CLIENT_SECRET_ARN`.
  3. `aws ecs register-task-definition` → enregistre une nouvelle révision.
  4. `aws ecs update-service --task-definition <new-arn> --force-new-deployment`
     → bascule le service sur la nouvelle révision.
  5. `aws ecs wait services-stable` → attend la fin du rollout.

> **Pourquoi register une nouvelle task def ?** Sans ça, modifier des
> variables d'environnement nécessiterait soit de patcher la task
> definition à la main dans la console, soit de redéployer un container
> avec ces valeurs *baked in*. Ce pattern garde la config externe au
> container et **versionnée par la pipeline** : chaque déploiement
> = nouvelle révision = trace complète de ce qui a été déployé.

### Diagramme

```
                ┌─ main    → environment=prod
setup ──────────┼─ develop → environment=dev
                └─ autre   → should_deploy=false
                          │
test ─> build (image .tar artefact)
                          │
deploy (load + push ECR + ECS rollout)   ← skippé si should_deploy=false
```

---

## dcm-frontend

**Fichier :** `.github/workflows/dcm-frontend.yml`
**App :** SPA React + Vite + TypeScript (`packages/dcm-frontend/`)
**Cible :** bucket S3 statique servi via CloudFront.

### Job `test`
1. Setup Node 20 avec cache npm sur `package-lock.json`.
2. `npm ci` (installation strictement reproductible).
3. Quality gates :
   - `npm run lint` → ESLint
   - `npx tsc --noEmit` → vérification TypeScript sans émission

### Job `build`
- Rattaché à un environnement GitHub via `environment:` :
  - `prod` sur `push main`
  - `dev` sur `push develop` ET sur PR / autres branches (fallback non
    sensible pour valider la compilation avec des secrets réalistes).
- Re-checkout + `npm ci`.
- **Injection des secrets MSAL au moment du build** (Vite remplace
  statiquement les `import.meta.env.VITE_*` dans le bundle) :
  - `VITE_AZURE_TENANT_ID`, `VITE_AZURE_CLIENT_ID`, `VITE_AZURE_SCOPE`
    (secrets — service principal Entra ID propre à l'env).
  - `VITE_API_BASE_URL`, `VITE_REDIRECT_URI`, `VITE_ENABLE_AUTH`
    (variables — non sensibles, par environnement).
- `npm run build` → produit `dist/` via Vite (le `tsc` a été retiré
  du script pour ne pas bloquer sur les erreurs de type).
- Upload du dossier `dist/` comme artefact GitHub `dcm-frontend-dist`
  (rétention 7 jours), récupéré ensuite par `deploy`.

> **Pourquoi injecter les secrets dans le build et pas au déploiement ?**
> Les apps SPA Vite n'ont pas de runtime serveur — toutes les variables
> `VITE_*` sont *hardcodées* dans les bundles JS au moment de `vite build`.
> Le bundle d'un environnement n'est donc pas réutilisable sur un autre :
> chaque env a son propre artefact, buildé avec ses propres secrets.

### Job `deploy`
- Download de l'artefact `dcm-frontend-dist`.
- Auth AWS via OIDC avec `AWS_FRONTEND_ROLE_ARN` (compte workload `551656632516` dev / `884068385310` prod).
- Vérifie que le rôle assumé n'est **pas** dans `551656632516` (dcmd).
- Secret `AWS_FRONTEND_ROLE_ARN` dev : `arn:aws:iam::551656632516:role/GithubDeploy` (compte workload, pas `551656632516`).
- Upload S3 en deux passes (stratégie de cache différenciée) :
  - **Assets hashés** (JS/CSS/images) : `Cache-Control: public, max-age=31536000, immutable`.
    Ils ont un hash dans le nom de fichier, on peut les cacher 1 an.
  - **`*.html`** : `Cache-Control: public, max-age=0, must-revalidate`.
    L'`index.html` doit toujours être frais pour pointer vers les bons hash.
- `aws cloudfront create-invalidation --paths "/*"` pour purger le cache CDN.

> **Pourquoi 2 syncs ?** L'`index.html` est l'unique source de vérité qui dit
> à quels assets pointer. S'il est mis en cache long, les utilisateurs
> peuvent charger un HTML qui référence des bundles JS supprimés.

### Diagramme

```
setup → test → build (npm build → artefact dist)
                                ↓
                deploy (S3 sync + CF invalidate)
                target = prod (main) | dev (develop) | skipped (autres)
```

---

## dcm-lambda-ingestion

**Fichier :** `.github/workflows/dcm-lambda-ingestion.yml`
**App :** Fonction Lambda Python 3.12 (`packages/dcm-lambda-ingestion/`)
**Cible :** **2 zips** (layer dépendances + function code) publiés sur S3,
puis nouvelle version de Lambda Layer + mise à jour du code de la fonction.

### Job `test`
- Identique au backend : ruff + mypy (`mypy lambda_ingestion`) + pytest.
- Path filter inclut aussi `packages/dcm-commons/**` car la Lambda en dépend.

### Job `build`
Produit **deux artefacts distincts** : la layer (deps) et le function code.

1. **Layer zip** — `dcm-lambda-ingestion-layer.zip`
   ```bash
   mkdir -p layer/python
   uv pip install \
     --target layer/python \
     --python-platform x86_64-manylinux2014 \
     --python-version 3.12 \
     .
   # On retire le code applicatif : il n'a rien à faire dans la layer.
   rm -rf layer/python/lambda_ingestion layer/python/lambda_ingestion-*.dist-info
   cd layer && zip -r9 ../dcm-lambda-ingestion-layer.zip .
   ```
   - Layout requis par AWS : `python/<site-packages>/...` à la racine du zip.
   - `--python-platform x86_64-manylinux2014` garantit que les wheels
     téléchargées sont compatibles avec le runtime Lambda (Linux x86_64).

2. **Function zip** — `dcm-lambda-ingestion-function.zip`
   ```bash
   mkdir -p function
   cp -r lambda_ingestion function/
   cd function && zip -r9 ../dcm-lambda-ingestion-function.zip .
   ```
   Contient uniquement le code applicatif. Ce zip est petit (kB),
   donc les déploiements de code "cycle court" ne réuploadent plus
   les MB de dépendances.

3. Les deux zips sont uploadés comme artefacts GitHub
   (`dcm-lambda-ingestion-layer-zip` et `dcm-lambda-ingestion-function-zip`,
   rétention 7 jours), récupérés ensuite par `deploy`.

> **Pourquoi splitter ?** Les dépendances changent rarement, le code
> applicatif souvent. Avec une layer, on évite d'embarquer 30+ Mo de
> wheels dans chaque révision de fonction, on reste sous le quota
> de 50 Mo zippé sur l'API `update-function-code`, et la layer est
> partageable entre plusieurs Lambdas si besoin demain.

### Job `deploy`
1. Download des deux artefacts zip (layer + function).
2. Auth AWS via OIDC.
3. Upload des deux zips sur S3, sous des préfixes versionnés par SHA :
   - `s3://$BUCKET/dcm-lambda-ingestion/layer/...-<sha>.zip`
   - `s3://$BUCKET/dcm-lambda-ingestion/function/...-<sha>.zip`
4. **`publish-layer-version`** depuis la source S3 → renvoie un
   `LayerVersionArn` exposé en sortie (`steps.layer.outputs.arn`).
5. **`update-function-code`** depuis le function zip S3 → met à jour
   uniquement le code applicatif (sans toucher à la layer pour l'instant).
6. `wait function-updated` (le code passe par un état `Pending`).
7. **`update-function-configuration --layers <layer-arn>`** → attache la
   nouvelle version de layer à la fonction.
8. `wait function-updated` à nouveau (la config passe aussi par `Pending`).
9. **`publish-version`** → publie une version immuable de la Lambda
   correspondant au couple (code + layer + config) qu'on vient de poser.

> **Pourquoi 2 `wait` ?** AWS impose qu'une fonction soit dans l'état
> `Active`/`Successful` avant d'accepter le prochain appel d'API. Mettre
> à jour le code et la config en deux temps oblige donc à attendre
> entre les deux. C'est l'API qui dicte l'ordre, pas un choix arbitraire.

### Diagramme

```
setup → test → build ─┬─ layer.zip   (deps)
                      └─ function.zip (code)
                                ↓
                deploy:
                  - upload layer.zip + function.zip → S3
                  - publish-layer-version
                  - update-function-code (function.zip)
                  - update-function-configuration --layers <new arn>
                  - publish-version
                target = prod (main) | dev (develop) | skipped (autres)
```

---

## dcm-aws-collector

**Fichier :** `.github/workflows/dcm-aws-collector.yml`
**App :** Tâche ECS Fargate one-shot Python (`packages/dcm-aws-collector/`)
**Cible :** image Docker dans ECR (déclenchement de la tâche fait par EventBridge / Step Functions, hors workflow).

### Job `test`
- ruff + mypy (`mypy aws_collector`) + pytest.
- Inclut `packages/dcm-commons/**` dans le path filter.

### Job `build`
- `docker buildx build` **sans push** vers ECR.
- Output `type=docker,dest=/tmp/dcm-aws-collector-image.tar`.
- Le tarball est uploadé comme artefact GitHub.
- Cette séparation garantit que rien ne touche ECR si le build a un problème
  ou si une étape ultérieure découvre un défaut. Le `deploy` est responsable
  de la publication.

### Job `deploy`
- Download de l'artefact (`.tar`).
- Auth AWS via OIDC, login ECR.
- Vérifie que le repository ECR cible existe et le crée si besoin
  (`ecr:DescribeRepositories` + `ecr:CreateRepository` requis sur le rôle OIDC).
- `docker load` + retag + push vers ECR avec deux tags (`<sha>` et `latest`).

> **Pas d'étape "demarre l'ECS"** : ce collecteur est une tâche
> à la demande, pas un service. Son orchestration (cron, événements) est
> gérée en dehors de la pipeline applicative.

### Diagramme

```
setup → test → build (docker build → tar artefact)
                                ↓
                deploy (docker load → push ECR)
                target = prod (main) | dev (develop) | skipped (autres)
```

---

## dcm-azure-collector

**Fichier :** `.github/workflows/dcm-azure-collector.yml`
**App :** Collecteur Azure Python (`packages/dcm-azure-collector/`)
**Cible :** image Docker dans ECR (même pattern que le collecteur AWS).

Structure identique à `dcm-aws-collector` :
- `test` → ruff + mypy + pytest sur `azure_collector`
- `build` → image Docker en tarball
- `deploy` → push ECR avec tags `<sha>` et `latest`

> Bien que ce collecteur cible Azure (App Service dans chaque LZ), son image est hébergée dans l’**ECR DCM central sur AWS** (même registry que `dcm-aws-collector`, repo `dcm-azure-collector`). L’App Service pull via identifiants registry ECR (user `AWS`).

---

## FAQ — Diagnostiquer un échec

| Job qui échoue | Causes typiques | Où regarder |
|---|---|---|
| `test` (ruff) | Code mal formaté, lint en erreur | logs ruff dans le job |
| `test` (mypy) | Annotation manquante, type incohérent | logs mypy |
| `test` (pytest) | Régression métier, fixture cassée | logs pytest, screenshots si applicable |
| `build` (frontend) | TS broken, import manquant, mémoire dépassée | logs `npm run build` |
| `build` (Docker) | Dockerfile cassé, dep introuvable, cache corrompu | logs `docker buildx` |
| `build` (Lambda) | wheel incompatible Linux, taille zip > 250 Mo | logs `uv pip install` |
| `deploy` ECS | rôle IAM insuffisant, healthcheck échoue → tâche refused | console ECS, CloudWatch Logs |
| `deploy` Lambda | rôle IAM, code package invalide | `aws lambda get-function` |
| `deploy` Frontend | rôle IAM sur le bucket / la distribution | console S3 + CloudFront |

## FAQ — Refaire un déploiement sans recommit

Pour redéployer un commit déjà mergé sans changement de code :

1. Onglet **Actions** dans GitHub.
2. Sélectionner le workflow.
3. Cliquer **Re-run all jobs** sur le run cible (ou seulement le job `deploy`
   si l'image/zip est encore disponible — sinon il faut tout réexécuter car
   les artefacts inter-jobs ont une rétention courte).
