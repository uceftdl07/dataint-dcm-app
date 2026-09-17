# DCM - Clarification App Registrations, Groups, Roles et Permissions

Ce document clarifie quoi faire apres le retour de Yahia sur les permissions via App Registration, claims token et Microsoft Graph.

## 1. Ce que le code fait aujourd'hui

Le frontend utilise MSAL.

Dans `packages/dcm-frontend/.env` :

```env
VITE_AZURE_CLIENT_ID=ef49b2f7-6dea-4181-ac06-788033b361db
VITE_AZURE_TENANT_ID=329e91b0-e21f-48fb-a071-456717ecc28e
VITE_AZURE_SCOPE=api://15817864-589d-4a33-ada4-ec40fa309a7b/access_as_user
VITE_REDIRECT_URI=http://localhost:4000/
VITE_ENABLE_AUTH=true
```

Donc il y a bien deux App Registrations :

| App Registration | Role | ID dans le repo |
| --- | --- | --- |
| Frontend SPA | Login utilisateur dans le navigateur | `ef49b2f7-6dea-4181-ac06-788033b361db` |
| Backend API | Resource/API qui expose le scope `access_as_user` | `15817864-589d-4a33-ada4-ec40fa309a7b` |

Le frontend lit actuellement les permissions dans `accounts[0].idTokenClaims`, donc dans l'ID token recu par la SPA.

Fichier concerne :

```text
packages/dcm-frontend/src/contexts/PermissionsContext.tsx
```

Le code cherche deja ces claims :

```ts
clouds / cloud_providers / cloudProviders / providers / dcm_clouds
landing_zones / landingZones / source_lz_ids / sourceLzIds / lz_ids / dcm_landing_zones
environments / envs / dcm_environments
kpis / kpi_permissions / kpiPermissions / permissions / roles / dcm_kpis
```

Mais dans ton token actuel, les logs montrent :

```text
cloudClaims: {}
landingZoneClaims: {}
environmentClaims: {}
kpiClaims: {}
```

Conclusion : l'authentification marche, mais aucune permission DCM n'est encore emise dans le token.

## 2. Ce que Yahia propose

Yahia propose le pattern Microsoft standard :

1. Mettre les `groups` et/ou `roles` dans le token.
2. L'application lit ces claims.
3. L'application applique son modele d'autorisation.
4. Microsoft Graph est utilise seulement en fallback si les groupes ne rentrent pas dans le token.

Cas normal :

```json
{
  "groups": ["<group-object-id-1>", "<group-object-id-2>"],
  "roles": ["DCM.Reader"]
}
```

Cas avec trop de groupes :

```json
{
  "hasgroups": true
}
```

ou :

```json
{
  "_claim_names": {
    "groups": "src1"
  }
}
```

Dans ce cas, il faut appeler Microsoft Graph pour recuperer les groupes.

## 3. Ce qu'il faut comprendre

`groups` ne donne pas directement les Landing Zones.

Un group ID dit seulement :

```text
L'utilisateur est membre du groupe Entra ID X.
```

Il faut encore un mapping DCM :

```text
group object id -> permissions DCM
```

Exemple :

```json
{
  "11111111-1111-1111-1111-111111111111": {
    "clouds": ["azure"],
    "environments": ["prod"],
    "landing_zones": ["lz-analytics-prod"],
    "kpis": ["all"]
  }
}
```

Sans ce mapping, le frontend peut lire les groupes, mais il ne peut pas savoir quelles Landing Zones afficher.

## 4. Quelle App Registration configurer ?

Il y a deux besoins differents.

### A. Pour que le frontend voie les permissions en local

Le code actuel lit `idTokenClaims` cote frontend.

Donc pour ton debug local, il faut que l'ID token contienne `groups` et/ou `roles`.

A configurer sur l'App Registration frontend :

```text
AZR-IASP-LZ-DataSquad-dcm-frontend-dev
Client ID: ef49b2f7-6dea-4181-ac06-788033b361db
```

Dans Azure :

1. App registrations.
2. Ouvrir l'App Registration frontend.
3. Token configuration.
4. Add groups claim.
5. Choisir `Security groups`.
6. Cocher `ID token`.
7. Sauvegarder.

Puis tester une reconnexion. Le log `[DCM permissions] relevant token claims` doit afficher une claim `groups`.

### B. Pour que le backend/API valide les droits en production

L'access token envoye au backend cible le scope :

```text
api://15817864-589d-4a33-ada4-ec40fa309a7b/access_as_user
```

Donc les claims utiles au backend doivent etre presents dans le token emis pour l'App Registration backend/API.

A configurer cote App Registration backend/API si le backend ou un Lambda Authorizer doit lire les groupes/roles :

```text
AWS-ALZP-WL-dcm-api-d
Client ID: 15817864-589d-4a33-ada4-ec40fa309a7b
```

Dans Azure :

1. App registrations.
2. Ouvrir l'App Registration backend/API.
3. Token configuration.
4. Add groups claim.
5. Choisir `Security groups`.
6. Cocher `Access token`.
7. Sauvegarder.

## 5. App roles : quoi creer ?

Ne pas creer un role par user.

Ne pas commencer par creer un role par Landing Zone si le nombre de Landing Zones est grand.

Commencer simple :

```text
DCM.Reader
DCM.Admin
```

Ces roles disent :

```text
L'utilisateur peut acceder a l'application DCM.
```

Ils ne disent pas encore :

```text
L'utilisateur a acces a telle Landing Zone.
```

Pour les Landing Zones, il faut soit :

1. Des groupes Entra ID par perimetre DCM.
2. Un mapping entre ces groupes et les LZ.
3. Ou une API backend `/me/permissions` qui fait ce calcul.

## 6. Decision recommandee pour DCM

Recommendation la plus claire pour ce repo :

1. Utiliser `roles` pour l'acces global a l'application.
2. Utiliser `groups` pour representer les perimetres DCM.
3. Ajouter un mapping `groupId -> permissions DCM`.
4. Lire `groups` depuis le token si present.
5. Appeler Microsoft Graph seulement si le token contient `hasgroups` ou `_claim_names`.

Architecture cible :

```text
User login
  -> ID token contient roles/groups
  -> Frontend lit roles/groups
  -> Frontend mappe groups vers permissions DCM
  -> Header affiche seulement les Landing Zones autorisees
```

Architecture plus robuste a moyen terme :

```text
User login
  -> Frontend recoit access token
  -> Frontend appelle GET /api/v1/me/permissions
  -> Backend lit token + groups/Graph
  -> Backend retourne les permissions DCM normalisees
  -> Frontend affiche les Landing Zones autorisees
```

La deuxieme option est meilleure pour la securite, car le backend reste la source d'autorisation.

## 7. Ce qu'il faut demander maintenant

Message a envoyer a Yahia / responsable :

```text
OK pour le pattern groups/roles dans le token.

J'ai bien deux App Registrations :
- frontend SPA : ef49b2f7-6dea-4181-ac06-788033b361db
- backend API : 15817864-589d-4a33-ada4-ec40fa309a7b

Pour le debug local, le frontend lit aujourd'hui idTokenClaims.
Je vais donc activer les group claims dans l'ID token de l'App Registration frontend.

Pour l'API/backend, il faudra aussi confirmer si les groups doivent etre dans l'access token de l'App Registration backend/API.

Question bloquante :
ou se trouve le mapping officiel entre group object ID Entra ID et permissions DCM ?

Exemple attendu :
group object id -> clouds / environments / source_lz_ids / kpis

Sans ce mapping, je peux lire les groupes, mais je ne peux pas savoir quelles Landing Zones afficher.
```

## 8. Changements code a prevoir

### Court terme frontend

Modifier `PermissionsContext.tsx` pour :

1. Lire la claim `groups`.
2. Detecter `hasgroups` et `_claim_names`.
3. Mapper les group IDs vers les permissions DCM.
4. Garder les logs debug.

Pseudo-code :

```ts
const GROUP_CLAIMS = ['groups'];

const DCM_GROUP_PERMISSIONS = {
  '<group-object-id>': {
    clouds: ['azure'],
    environments: ['prod'],
    landingZones: ['lz-analytics-prod'],
    kpis: ['all'],
  },
};
```

### Moyen terme backend

Ajouter une route :

```http
GET /api/v1/me/permissions
```

Reponse :

```json
{
  "status": "ready",
  "clouds": ["azure"],
  "environments": ["prod"],
  "landing_zones": [
    {
      "source_lz_id": "lz-analytics-prod",
      "cloud_provider": "azure",
      "environment": "prod",
      "label": "Analytics Prod"
    }
  ],
  "kpis": ["all"]
}
```

## 9. Checklist action immediate

1. Azure frontend App Registration : activer `groups` dans ID token.
2. Se deconnecter/reconnecter.
3. Verifier console :

```text
[DCM permissions] relevant token claims
```

4. Confirmer qu'on voit :

```text
groups: [...]
```

5. Recuperer les group object IDs.
6. Demander/definir le mapping group ID vers LZ.
7. Adapter `PermissionsContext.tsx`.
8. Si le token affiche `hasgroups` ou `_claim_names`, prevoir Graph fallback.

## 10. Resume simple

Tu n'es pas censee connaitre les LZ depuis l'App Registration seule.

L'App Registration peut donner :

```text
roles
groups
```

Mais pour connaitre les Landing Zones, il faut :

```text
groups -> mapping DCM -> Landing Zones
```

Donc l'action la plus importante maintenant n'est pas de creer plein de roles.

L'action la plus importante est d'obtenir le mapping officiel :

```text
group object ID Entra ID -> permissions DCM
```
