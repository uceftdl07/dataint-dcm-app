# Diagnostic deploiement - Administration et Unity Catalog

Date: 2026-05-28

## Contexte

Deux symptomes sont visibles sur le deploiement:

- La page `/admin` affiche `Administration access required` puis `Failed to fetch`, et l'entree `Administration` n'apparait pas toujours dans le menu.
- Le navigateur bloque des appels vers `https://api.dcm.alzp.tgscloud.net/api/v1/unity-catalog/query`.

Mise a jour 2026-05-28 13:14:

- Les tests publics confirment que le backend repond, mais que les preflights CORS ne retournent pas de statut OK.
- Les profils AWS SSO existent deja en local (`dcm-owner`, `alzp-owner`, `dcm-sso`) et pointent vers l'Identity Center `https://identitycenter.amazonaws.com/ssoins-6804389aa94c0d0f` en `eu-west-1`.
- Les tokens SSO locaux sont expires; il faut relancer `aws sso login --profile dcm-sso` avant d'inspecter API Gateway.

Mise a jour 2026-05-28 13:20 apres login SSO:

- Compte AWS inspecte: `551656632516`, role `AWSReservedSSO_ALZP-WL-Owner_440b4efcd7ec8b41`.
- API Gateway inspectee: `dcm-api-jwt`, id `h4b8ee6xja`, region `eu-central-1`, endpoint execute-api desactive, custom domain utilise.
- La config CORS API Gateway autorise bien `https://dcm.alzp.tgscloud.net`, `authorization`, `content-type`, et `GET,POST,OPTIONS`.
- Le probleme vient de la route/integration `OPTIONS /api/v1/{proxy+}`.

## Constats verifies

### 1. Le backend et Unity Catalog repondent

Test direct depuis la machine:

```bash
curl -i https://api.dcm.alzp.tgscloud.net/api/v1/health/live
curl -i -X POST https://api.dcm.alzp.tgscloud.net/api/v1/unity-catalog/query \
  -H 'Origin: https://dcm.alzp.tgscloud.net' \
  -H 'Content-Type: application/json' \
  --data '{"catalogName":"it","schemaName":"ba_data_connect_monitoring__a","tableName":"curated_activity_runs","limit":1,"offset":0}'
```

Resultat observe:

- `/api/v1/health/live` retourne `200`.
- `POST /api/v1/unity-catalog/query` retourne `200` avec une ligne de `curated_activity_runs`.

Conclusion: la route backend existe, le chemin API public arrive bien jusqu'a FastAPI, et la connexion Databricks/Unity Catalog fonctionne au moins pour cette requete.

### 2. Les preflights CORS echouent

Tests directs:

```bash
curl -i -X OPTIONS https://api.dcm.alzp.tgscloud.net/api/v1/auth/me \
  -H 'Origin: https://dcm.alzp.tgscloud.net' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'

curl -i -X OPTIONS https://api.dcm.alzp.tgscloud.net/api/v1/unity-catalog/query \
  -H 'Origin: https://dcm.alzp.tgscloud.net' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type'
```

Resultat observe:

- `OPTIONS /api/v1/auth/me` retourne `401 Missing bearer token`.
- `OPTIONS /api/v1/unity-catalog/query` retourne `405 Method Not Allowed`.
- Le navigateur confirme: `Response to preflight request doesn't pass access control check: It does not have HTTP ok status.`
- Test refait a 13:13: `/auth/me` retourne toujours `401`, `/unity-catalog/query` retourne toujours `405`.

Conclusion: le probleme navigateur est lie au preflight CORS. Le navigateur bloque l'appel avant le vrai `GET`/`POST`, d'ou `Failed to fetch`.

Cause AWS confirmee:

```text
Route: OPTIONS /api/v1/{proxy+}
RouteId: 625zy9b
Target: integrations/ii1f4ic
Integration ii1f4ic: HTTP_PROXY avec IntegrationMethod = GET
```

Donc API Gateway route bien le preflight `OPTIONS`, mais l'integration appelle l'ALB/backend en `GET`.

Effets observes:

- `OPTIONS /api/v1/auth/me` devient equivalent a un `GET /api/v1/auth/me` sans Bearer, donc `401`.
- `OPTIONS /api/v1/unity-catalog/query` devient equivalent a un `GET /api/v1/unity-catalog/query`, alors que l'endpoint backend est `POST`, donc `405`.

Comparaison avec des routes qui fonctionnent:

- `OPTIONS /api/v1/activities` retourne `200 OK`.
- `OPTIONS /api/v1/pipelines` retourne `200 OK`.
- `OPTIONS /api/v1/dashboard/summary` retourne `200 OK`.
- Leur integration utilise `IntegrationMethod = OPTIONS`, par exemple `3kih897`.

### 3. Le menu Administration depend du role `super_admin`

Dans le frontend:

- `packages/dcm-frontend/src/components/Sidebar.tsx` filtre les entrees `requiresAdmin` avec `user?.role === 'super_admin'`.
- `packages/dcm-frontend/src/components/RequireAdmin.tsx` bloque si `user?.role !== 'super_admin'`.

Dans le backend:

- `packages/dcm-backend/app/api/routes/admin_users.py` protege `GET /admin/users` avec `require_role("super_admin")`.

Conclusion: un utilisateur avec role `admin` ne verra pas le menu et ne passera pas le guard. Il faut verifier si le besoin fonctionnel est `admin` ou seulement `super_admin`, puis aligner frontend, backend et donnees `dcm_app_users`.

### 4. Risque de securite sur `unity-catalog/query`

Le `POST /api/v1/unity-catalog/query` a repondu `200` sans token Bearer lors du test direct.

Conclusion: soit l'API Gateway ne protege pas cette route, soit le backend ne force pas `get_current_user` sur les routes Unity Catalog. A verifier rapidement, car cet endpoint expose des requetes SELECT contraintes sur Unity Catalog.

Verification code:

- `packages/dcm-backend/app/api/routes/unity_catalog.py` ne declare pas `Depends(get_current_user)` ni `Depends(get_allowed_lz_ids)` sur les endpoints Unity Catalog.
- Le test direct sans `Authorization` retourne encore `200` a 13:14.

Verification AWS:

- Il n'existe pas de route dediee `ANY /api/v1/unity-catalog/{proxy+}`.
- Il n'existe pas de route dediee `ANY /api/v1/admin/{proxy+}`.
- Il n'existe pas de route dediee `ANY /api/v1/auth/{proxy+}`.
- Ces chemins passent donc par `$default`, dont `AuthorizationType = NONE`.

Conclusion securite: `/api/v1/unity-catalog/query` est public aujourd'hui au niveau API Gateway et au niveau FastAPI.

### 5. AWS SSO local

Le profil `dcm-admin` n'existe pas dans `~/.aws/config`, d'ou l'erreur initiale `The config profile (dcm-admin) could not be found`.

Profils existants:

```bash
aws configure list-profiles
# dcm-owner
# alzp-owner
# dcm-sso
```

Configuration observee:

```ini
[profile dcm-sso]
sso_session = dcm
sso_account_id = 551656632516
sso_role_name = ALZP-WL-Owner

[sso-session dcm]
sso_start_url = https://identitycenter.amazonaws.com/ssoins-6804389aa94c0d0f
sso_region = eu-west-1
sso_registration_scopes = sso:account:access
```

Commande recommandee:

```bash
aws sso login --profile dcm-sso
export AWS_PROFILE=dcm-sso
```

Si un alias `dcm-admin` est vraiment voulu:

```bash
aws configure set sso_session dcm --profile dcm-admin
aws configure set sso_account_id 551656632516 --profile dcm-admin
aws configure set sso_role_name ALZP-WL-Owner --profile dcm-admin
aws configure set region eu-central-1 --profile dcm-admin
```

Ne pas utiliser `aws configure sso --sso-start-url ... --sso-region ...`: cette commande est un assistant interactif et la CLI locale rejette ces options.

## Hypothese principale

La configuration API Gateway/CORS gere mal les `OPTIONS`:

- les preflights sont forwards vers le backend ou remappes vers la methode cible;
- ils reviennent en `401`/`405` au lieu de `200` ou `204`;
- les vrais appels peuvent fonctionner en curl, mais le navigateur les bloque.

Le screenshot API Gateway montre aussi peu de routes visibles (`ANY /`, `GET /health`, `ANY /activities`). Il faut confirmer que les routes proxy couvrent bien `/api/v1/*` et que les `OPTIONS` sont sans authorizer.

## Checks AWS proposes

Apres login SSO AWS CLI:

```bash
aws sts get-caller-identity --profile dcm-sso --region eu-central-1
aws apigatewayv2 get-api --api-id h4b8ee6xja --region eu-central-1
aws apigatewayv2 get-routes --api-id h4b8ee6xja --region eu-central-1
aws apigatewayv2 get-cors-configuration --api-id h4b8ee6xja --region eu-central-1
```

Verifier:

- une route proxy couvre `/api/v1/{proxy+}` ou `$default`;
- `OPTIONS /{proxy+}` ou `OPTIONS /api/v1/{proxy+}` retourne directement `204/200`;
- aucun authorizer n'est attache aux routes `OPTIONS`;
- les headers `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` ne sont pas supprimes avant FastAPI si le backend doit gerer CORS;
- les methodes autorisees incluent au minimum `GET,POST,PATCH,PUT,DELETE,OPTIONS`;
- les headers autorises incluent `authorization,content-type`.
- le stage deploye correspond bien au dernier changement (`aws apigatewayv2 get-stages --api-id h4b8ee6xja --region eu-central-1`).

Depuis le screenshot AWS Console, la region de l'API Gateway est `eu-central-1` et l'API id visible est `h4b8ee6xja`; c'est cette region qu'il faut utiliser pour inspecter/deployer l'API, meme si la region SSO Identity Center est `eu-west-1`.

Commandes AWS utiles pour reproduire le constat:

```bash
aws apigatewayv2 get-route \
  --api-id h4b8ee6xja \
  --route-id 625zy9b \
  --profile dcm-sso \
  --region eu-central-1

aws apigatewayv2 get-integration \
  --api-id h4b8ee6xja \
  --integration-id ii1f4ic \
  --profile dcm-sso \
  --region eu-central-1

aws apigatewayv2 get-integration \
  --api-id h4b8ee6xja \
  --integration-id 3kih897 \
  --profile dcm-sso \
  --region eu-central-1
```

## Corrections proposees

### Priorite 1 - Corriger le preflight CORS

Option recommandee cote API Gateway:

- Corriger la route `OPTIONS /api/v1/{proxy+}` sans authorizer pour utiliser une integration `OPTIONS`, pas `GET`.
- Retourner `204` ou `200`.
- Retourner les headers:
  - `Access-Control-Allow-Origin: https://dcm.alzp.tgscloud.net`
  - `Access-Control-Allow-Methods: GET,POST,PATCH,PUT,DELETE,OPTIONS`
  - `Access-Control-Allow-Headers: authorization,content-type`
  - `Access-Control-Max-Age: 300`

Correction AWS minimale probable:

```bash
aws apigatewayv2 update-route \
  --api-id h4b8ee6xja \
  --route-id 625zy9b \
  --target integrations/3kih897 \
  --profile dcm-sso \
  --region eu-central-1
```

Pourquoi: `3kih897` est deja une integration `HTTP_PROXY` vers le meme ALB avec `IntegrationMethod = OPTIONS`, et elle retourne `200 OK` sur les routes testees.

Apres correction, re-tester:

```bash
curl -i -X OPTIONS https://api.dcm.alzp.tgscloud.net/api/v1/auth/me \
  -H 'Origin: https://dcm.alzp.tgscloud.net' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'

curl -i -X OPTIONS https://api.dcm.alzp.tgscloud.net/api/v1/unity-catalog/query \
  -H 'Origin: https://dcm.alzp.tgscloud.net' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type'
```

Alternative:

- Laisser FastAPI `CORSMiddleware` gerer CORS, mais dans ce cas API Gateway doit forwarder les vrais `OPTIONS` et les headers `Access-Control-Request-*` sans les transformer.

Option recommandee cote backend si API Gateway forwarde les `OPTIONS` vers FastAPI:

- Ajouter une gestion explicite des preflights avant les routes protegees, car `OPTIONS /api/v1/auth/me` tombe actuellement sur l'auth et retourne `401`.
- Ajouter une route ou un middleware qui retourne `204` pour `OPTIONS` avec les headers CORS attendus.

### Priorite 2 - Verifier l'utilisateur DCM

Une fois CORS corrige, appeler avec un token Bearer valide:

```bash
curl -i https://api.dcm.alzp.tgscloud.net/api/v1/auth/me \
  -H "Authorization: Bearer <access-token>"
```

Verifier que la reponse contient:

- l'email attendu;
- `is_active: true`;
- `role: super_admin` si le code actuel reste tel quel.

Si le besoin est d'ouvrir l'Administration aux `admin`, modifier ensemble:

- `Sidebar.tsx`;
- `RequireAdmin.tsx`;
- les routes backend qui utilisent `require_role("super_admin")`.

### Priorite 3 - Securiser Unity Catalog

Verifier si `/api/v1/unity-catalog/*` doit etre public. Si non:

- ajouter `get_current_user` ou `get_allowed_lz_ids` sur les routes Unity Catalog;
- ou configurer l'authorizer API Gateway sur ces routes;
- re-tester qu'un appel sans Bearer retourne `401`.

Correction API Gateway recommandee pour defense en profondeur:

```bash
aws apigatewayv2 create-route \
  --api-id h4b8ee6xja \
  --route-key 'ANY /api/v1/unity-catalog/{proxy+}' \
  --authorization-type JWT \
  --authorizer-id 2klsap \
  --target integrations/7iabqmt \
  --profile dcm-sso \
  --region eu-central-1

aws apigatewayv2 create-route \
  --api-id h4b8ee6xja \
  --route-key 'OPTIONS /api/v1/unity-catalog/{proxy+}' \
  --authorization-type NONE \
  --target integrations/3kih897 \
  --profile dcm-sso \
  --region eu-central-1
```

Correction similaire a envisager pour l'administration:

```bash
aws apigatewayv2 create-route \
  --api-id h4b8ee6xja \
  --route-key 'ANY /api/v1/admin/{proxy+}' \
  --authorization-type JWT \
  --authorizer-id 2klsap \
  --target integrations/7iabqmt \
  --profile dcm-sso \
  --region eu-central-1

aws apigatewayv2 create-route \
  --api-id h4b8ee6xja \
  --route-key 'OPTIONS /api/v1/admin/{proxy+}' \
  --authorization-type NONE \
  --target integrations/3kih897 \
  --profile dcm-sso \
  --region eu-central-1
```

Proposition code backend:

- importer `get_current_user` ou `get_allowed_lz_ids` dans `unity_catalog.py`;
- ajouter une dependance sur les endpoints explorer/schemas/tables/metadata/preview/query;
- conserver les controles SQL existants, mais ne pas les considerer comme une authentification.

### Priorite 4 - Revalider les variables de build

Dans l'environnement GitHub utilise par `dcm-frontend.yml`, verifier:

- `VITE_API_BASE_URL=https://api.dcm.alzp.tgscloud.net`
- `VITE_REDIRECT_URI=https://dcm.alzp.tgscloud.net`
- `VITE_ENABLE_AUTH=true`
- `VITE_AZURE_SCOPE` correspond a l'audience attendue par le backend/API Gateway

Dans l'environnement backend/ECS, verifier:

- `DCM_ENTRA_TENANT_ID`
- `DCM_ENTRA_CLIENT_ID`
- `DCM_CORS_ALLOWED_ORIGINS` ou `DCM_ALLOWED_ORIGINS` contient `https://dcm.alzp.tgscloud.net`

## Changements appliques dans API Gateway

Date: 2026-05-28 13:40

Actions effectuees sur l'API Gateway `h4b8ee6xja` en `eu-central-1` avec le profil `dcm-sso`:

```bash
aws apigatewayv2 update-route \
  --api-id h4b8ee6xja \
  --route-id 625zy9b \
  --target integrations/3kih897 \
  --profile dcm-sso \
  --region eu-central-1

aws apigatewayv2 create-route \
  --api-id h4b8ee6xja \
  --route-key 'ANY /api/v1/auth/{proxy+}' \
  --authorization-type JWT \
  --authorizer-id 2klsap \
  --target integrations/7iabqmt \
  --profile dcm-sso \
  --region eu-central-1

aws apigatewayv2 create-route \
  --api-id h4b8ee6xja \
  --route-key 'OPTIONS /api/v1/auth/{proxy+}' \
  --authorization-type NONE \
  --target integrations/3kih897 \
  --profile dcm-sso \
  --region eu-central-1

aws apigatewayv2 create-route \
  --api-id h4b8ee6xja \
  --route-key 'ANY /api/v1/admin/{proxy+}' \
  --authorization-type JWT \
  --authorizer-id 2klsap \
  --target integrations/7iabqmt \
  --profile dcm-sso \
  --region eu-central-1

aws apigatewayv2 create-route \
  --api-id h4b8ee6xja \
  --route-key 'OPTIONS /api/v1/admin/{proxy+}' \
  --authorization-type NONE \
  --target integrations/3kih897 \
  --profile dcm-sso \
  --region eu-central-1

aws apigatewayv2 create-route \
  --api-id h4b8ee6xja \
  --route-key 'ANY /api/v1/unity-catalog/{proxy+}' \
  --authorization-type JWT \
  --authorizer-id 2klsap \
  --target integrations/7iabqmt \
  --profile dcm-sso \
  --region eu-central-1

aws apigatewayv2 create-route \
  --api-id h4b8ee6xja \
  --route-key 'OPTIONS /api/v1/unity-catalog/{proxy+}' \
  --authorization-type NONE \
  --target integrations/3kih897 \
  --profile dcm-sso \
  --region eu-central-1
```

Routes creees:

- `ANY /api/v1/auth/{proxy+}` avec authorizer JWT `2klsap`.
- `OPTIONS /api/v1/auth/{proxy+}` sans authorizer.
- `ANY /api/v1/admin/{proxy+}` avec authorizer JWT `2klsap`.
- `OPTIONS /api/v1/admin/{proxy+}` sans authorizer.
- `ANY /api/v1/unity-catalog/{proxy+}` avec authorizer JWT `2klsap`.
- `OPTIONS /api/v1/unity-catalog/{proxy+}` sans authorizer.

Verification apres changement:

```bash
curl -i -X OPTIONS https://api.dcm.alzp.tgscloud.net/api/v1/auth/me \
  -H 'Origin: https://dcm.alzp.tgscloud.net' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'

curl -i -X OPTIONS https://api.dcm.alzp.tgscloud.net/api/v1/admin/users \
  -H 'Origin: https://dcm.alzp.tgscloud.net' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'

curl -i -X OPTIONS https://api.dcm.alzp.tgscloud.net/api/v1/unity-catalog/query \
  -H 'Origin: https://dcm.alzp.tgscloud.net' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type'
```

Resultats:

- Les trois preflights retournent `HTTP/2 200` avec `Access-Control-Allow-Origin: https://dcm.alzp.tgscloud.net`.
- `POST /api/v1/unity-catalog/query` sans Bearer retourne maintenant `HTTP/2 401 {"message":"Unauthorized"}`.
- `GET /api/v1/auth/me` sans Bearer retourne maintenant `HTTP/2 401 {"message":"Unauthorized"}` depuis API Gateway.
- `GET /api/v1/admin/users` sans Bearer retourne maintenant `HTTP/2 401 {"message":"Unauthorized"}` depuis API Gateway.

## Correction CORS pour les mutations admin

Date: 2026-05-28 13:59

Symptome supplementaire:

- `PATCH /api/v1/admin/users/{user_id}/role` passait en local mais pas sur le domaine deploye.
- Le frontend appelle bien cet endpoint en `PATCH`.
- Le preflight `OPTIONS` retournait `200 OK`, mais sans headers `Access-Control-Allow-*` tant que `PATCH` n'etait pas dans la configuration CORS API Gateway.

Correction appliquee:

```bash
aws apigatewayv2 update-api \
  --api-id h4b8ee6xja \
  --cors-configuration 'AllowOrigins=[http://localhost:3000,https://dcm.alzp.tgscloud.net,http://localhost:4000],AllowMethods=[GET,POST,PUT,PATCH,DELETE,OPTIONS],AllowHeaders=[authorization,content-type],MaxAge=300,AllowCredentials=false' \
  --profile dcm-sso \
  --region eu-central-1
```

Verification:

```bash
curl -i -X OPTIONS https://api.dcm.alzp.tgscloud.net/api/v1/admin/users/b8bca617-c047-45ec-9ebe-61e131ea0f0a/role \
  -H 'Origin: https://dcm.alzp.tgscloud.net' \
  -H 'Access-Control-Request-Method: PATCH' \
  -H 'Access-Control-Request-Headers: authorization,content-type'
```

Resultat apres propagation du stage:

- `HTTP/2 200`
- `Access-Control-Allow-Origin: https://dcm.alzp.tgscloud.net`
- `Access-Control-Allow-Methods: DELETE,GET,OPTIONS,PATCH,POST,PUT`
- `Access-Control-Allow-Headers: authorization,content-type`

## Limites du check actuel

- Les routes API Gateway ont ete corrigees et verifiees par `curl`, mais le parcours navigateur complet avec un token utilisateur reel reste a revalider.
- Le menu `Administration` depend encore du role applicatif retourne par `/api/v1/auth/me`: le role doit etre `super_admin` avec le code actuel.
