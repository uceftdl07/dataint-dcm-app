# Proposition - Alimenter la table `users` depuis Azure / Entra ID

## Objectif

Mettre en place un mecanisme simple et fiable pour alimenter la table `users` de l'application avec les utilisateurs autorises a acceder a l'interface, ainsi que leur niveau de droit :

- `admin`
- `super_admin`

L'objectif est d'eviter une gestion manuelle dans l'application et de centraliser les droits d'acces dans Azure / Microsoft Entra ID.

## Point important

Le lien du portail Azure :

`https://portal.azure.com/?feature.msaljs=true#view/Microsoft_AAD_RegisteredApps/ApplicationMenuBlade/~/Owners/appId/ef49b2f7-6dea-4181-ac06-788033b361db`

sert a gerer l'application via l'interface web Azure.

Pour automatiser l'alimentation de la table `users`, il ne faut pas utiliser directement cette page web. Il faut utiliser l'API officielle Microsoft Graph.

## Recommandation

La solution recommandee est d'utiliser deux groupes Microsoft Entra ID :

- `DCM_Admin`
- `DCM_SuperAdmin`

Les utilisateurs sont ajoutes ou retires de ces groupes dans Azure / Entra ID. Ensuite, un script lit les membres de ces groupes via Microsoft Graph et synchronise la table `users`.

Cette approche est preferable aux `Owners` de l'App Registration, car les owners servent plutot a administrer l'application Azure elle-meme. Ils ne representent pas forcement les utilisateurs qui doivent avoir acces a l'interface metier.

## Fonctionnement propose

1. Creer deux groupes Entra ID :
   - `DCM_Admin`
   - `DCM_SuperAdmin`

2. Ajouter les utilisateurs autorises dans les bons groupes.

3. Creer un script Python de synchronisation.

4. Le script appelle Microsoft Graph pour recuperer :
   - les membres du groupe `DCM_Admin`
   - les membres du groupe `DCM_SuperAdmin`

5. Le script fait un `upsert` dans la table `users`.

6. Les utilisateurs qui ne sont plus presents dans les groupes Azure peuvent etre desactives dans l'application.

## Exemple de structure pour la table `users`

Champs possibles :

- `id`
- `email`
- `display_name`
- `azure_object_id`
- `role`
- `is_active`
- `created_at`
- `updated_at`

Exemple de valeurs :

| email | display_name | azure_object_id | role | is_active |
| --- | --- | --- | --- | --- |
| user1@company.com | User One | Azure object id | admin | true |
| user2@company.com | User Two | Azure object id | super_admin | true |

## Logique du script

Pseudo-code :

```python
# 1. Authentification Microsoft Graph
# 2. Recuperer les membres du groupe DCM_Admin
# 3. Recuperer les membres du groupe DCM_SuperAdmin
# 4. Construire la liste des utilisateurs autorises
# 5. Inserer ou mettre a jour chaque utilisateur dans la table users
# 6. Desactiver les utilisateurs qui ne sont plus autorises
```

Exemple de logique metier :

- si un utilisateur est dans `DCM_SuperAdmin`, son role devient `super_admin`
- sinon, s'il est dans `DCM_Admin`, son role devient `admin`
- si un utilisateur n'est dans aucun des deux groupes, il est desactive

## Permissions Microsoft Graph necessaires

Pour que le script puisse lire les groupes et leurs membres, l'application Azure utilisee par le script doit avoir des permissions Microsoft Graph adaptees.

Permissions possibles :

- `Group.Read.All`
- `User.Read.All`
- eventuellement `Directory.Read.All`

Ces permissions doivent generalement etre validees par un administrateur Azure.

## Configuration technique

Le script peut utiliser des variables d'environnement :

```bash
AZURE_TENANT_ID=...
AZURE_CLIENT_ID=...
AZURE_CLIENT_SECRET=...
AZURE_GROUP_ADMIN_ID=...
AZURE_GROUP_SUPER_ADMIN_ID=...
```

Il est preferable d'utiliser les IDs des groupes plutot que leurs noms, car les noms peuvent changer.

## Frequence de synchronisation

Plusieurs options sont possibles :

- lancer le script manuellement quand les droits changent
- lancer le script via un job planifie
- lancer le script pendant le deploiement
- lancer le script regulierement, par exemple toutes les heures ou tous les jours

Pour commencer, un lancement manuel ou un job planifie quotidien peut suffire.

## Points de securite

- Ne jamais stocker le `client_secret` en clair dans le repository.
- Utiliser des variables d'environnement ou un secret manager.
- Donner au script uniquement les permissions necessaires.
- Garder une trace de la date de derniere synchronisation.
- Eviter de supprimer physiquement les utilisateurs : preferer `is_active = false`.

## Alternative : App Roles

Une autre option consiste a definir des App Roles directement sur l'App Registration Azure :

- `Admin`
- `SuperAdmin`

Les utilisateurs ou groupes sont ensuite assignes a ces roles.

Cette approche est plus proche du modele applicatif Azure, mais elle peut etre un peu plus lourde a configurer. Pour un besoin simple de gestion d'acces, les groupes Entra ID restent la solution la plus facile a maintenir.

## Decision proposee

Utiliser les groupes Microsoft Entra ID comme source de verite :

- `DCM_Admin`
- `DCM_SuperAdmin`

Puis creer un script Python qui synchronise ces groupes vers la table `users` via Microsoft Graph.

