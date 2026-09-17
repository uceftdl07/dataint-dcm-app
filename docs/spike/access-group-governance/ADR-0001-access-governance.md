# ADR 0001 — Gouvernance des accès DCM : modèle « projet » + groupe Entra unique

- **Statut :** **Accepté** — arbitrage final Design Authority, go V2
- **Date :** 2026-08-18
- **Date de validation :** 2026-08-21 (Design Authority)
- **Branche spike :** `spike/access_groupe_strategy`
- **Décideurs :** Lead Dev DCM, Design Authority
- **Contexte technique :** `docs/spike/access-group-governance/` (spike complet : README V1/V2, ddl.sql, prototype)

---

## Contexte et problème

L'autorisation DCM est aujourd'hui **plate et globale** :

- un **rôle global unique** par utilisateur (`viewer` … `super_admin`, cf. `packages/dcm-backend/app/auth/role_permissions.py`) ;
- l'accès aux Landing Zones via une **liste plate** `dcm_user_lz_access` filtrée en SQL sur `source_lz_id` ;
- `admin` / `super_admin` = **toutes les LZ**, sans restriction ;
- **aucune** notion de projet/équipe, **aucun** scope au niveau workspace Databricks, administration **globale**.

Ce modèle ne passe pas à l'échelle dès que plusieurs équipes veulent auto-gérer leur périmètre. Deux questions à trancher :

1. **Quel modèle d'autorisation ?** (plat vs scopé par projet)
2. **Quel rôle donner à Microsoft Entra ID ?** (source d'autorisation miroir vs simple gate d'authentification)

## Décisions

### D1 — Adopter un modèle d'autorisation « projet »

Un **projet** regroupe des utilisateurs (rôle **scopé projet** `viewer`/`admin`) et un périmètre **LZ et/ou workspace Databricks**. Un utilisateur peut appartenir à plusieurs projets. `super_admin` (platform_admin) reste au-dessus des projets. Administration à **deux étages** : platform_admin (valide créations et extensions de périmètre) vs project admin (gère membres/rôles de son seul projet).

Décisions verrouillées du spike : scope LZ **ET** workspace DBX, chevauchement de LZ autorisé, création et extension validées par platform_admin, 2 rôles projet (`viewer`/`admin`).

### D2 — Entra ID = **groupe unique** `DCM-Users` (gate d'authentification uniquement)

L'**authentification** repose sur un **seul** groupe Entra `DCM-Users` (droit d'ouvrir DCM). Toute l'**autorisation** (projets, rôles, périmètres) vit **exclusivement dans les tables DCM**, seule source de vérité. La colonne `dcm_projects.entra_group_id` est conservée **nullable** (toujours NULL) comme point d'extension vers un modèle « 1 groupe Entra par projet » sans migration de schéma.

## Options envisagées

Constat de départ commun aux deux options : **la table DCM est la source de vérité** de
l'appartenance. Un groupe Entra n'apporte de valeur que si **un système extérieur à DCM le
consomme**. Or DCM ne fait que *monitorer* — il n'accorde aucun droit dans Databricks ni
ailleurs. À ce jour : **aucun consommateur externe** de l'appartenance par projet.

| Critère | V1 — groupe par projet | **V2 — groupe unique** *(retenu)* |
|--------|------------------------|--------------------|
| Rôle d'Entra | Auth **+** miroir d'autorisation | Auth **uniquement** |
| Nb de groupes Entra | 1 / projet (croît avec les projets) | 1 (constant) |
| Privilège Graph `Group.Create` + membership | Requis (sensible, validation sécu lourde) | Aucun |
| Provisioning à la création de projet | Créer groupe + mapper `entra_group_id` | Rien |
| Job de réconciliation de drift | Requis (event-driven + batch + circuit-breakers) | Sans objet |
| Risque de divergence Entra ↔ DCM | Réel (drift à gérer) | Nul par construction |
| Surface d'attaque / secrets | + (identité DCM avec droits d'écriture Graph) | − |
| Complexité de build & run | Élevée | Faible |
| Latence d'octroi d'accès | Dépend du provisioning Graph | Immédiate (écriture table) |
| Overage de claims `groups` dans le JWT | Possible si user dans beaucoup de projets | Non (1 seul groupe) |
| Access reviews / entitlement mgmt Entra par périmètre | ✅ Natif | ❌ (à faire dans DCM) |
| Provisioning SCIM vers d'autres outils | ✅ Possible | ❌ |
| Conditional Access différencié par projet | ✅ Possible | ❌ (CA global seulement) |
| Break-glass / audit hors application | ✅ Via Entra | Dans DCM (`dcm_audit_log`) |
| Effort d'implémentation | Modèle projet **+** provisioning **+** réconciliation | Modèle projet **seul** |

### Ce que V1 apporte réellement

Les seuls avantages **exclusifs** de V1 sont les 3 usages *gouvernance Entra* : access reviews
par périmètre, provisioning SCIM sortant, Conditional Access par projet. Ces trois usages n'ont
de sens que si **l'IAM groupe l'impose** ou si **DCM doit piloter des accès ailleurs**. Tant que
ce n'est pas le cas, V1 paie un coût (privilège Graph sensible, job de drift, latence,
complexité) pour un miroir **que personne ne consomme**.

### Ce que V2 gagne

V2 supprime d'un coup : le privilège `Group.Create`, le provisioning Graph, toute la
réconciliation, les circuit-breakers de suppression en masse, et le risque de drift. Une seule
source de vérité, un onboarding qui réutilise l'auto-provisioning `pending` existant. Moins de
code, moins de surface d'attaque, mise en œuvre plus rapide.

### Couche d'autorisation identique

Point clé : `get_allowed_scope` et `is_project_admin`
([project_scope_prototype.py](./project_scope_prototype.py)) **ne dépendent pas** du modèle
Entra — ils lisent les tables DCM. Le choix V1/V2 n'affecte **que** la couche de provisioning,
pas la logique d'autorisation. Le risque de « mauvais choix » est donc **faible et réversible**.

## Décision retenue : V2 (D2)

**Validée en Design Authority le 2026-08-21.** À ce jour **aucun système externe ne consomme l'appartenance par projet** (DCM ne fait que *monitorer*, il n'octroie aucun droit ailleurs). Un miroir Entra par projet serait donc du poids mort payé au prix d'un privilège Graph sensible, d'un job de drift et d'un risque de divergence.

> V1 = Entra source d'autorisation (miroir) → puissant mais coûteux et utile seulement si un
> système externe le consomme. **V2 = Entra simple gate d'auth, DCM seule autorité
> d'autorisation → plus simple, plus sûr, réversible. Recommandé.**

## Conséquences

**Positives**

- Suppression du privilège Graph `Group.Create` → surface d'attaque et charge de validation sécu réduites.
- Suppression de tout le job de réconciliation / circuit-breakers → moins de code, moins de run.
- Source de vérité unique → **pas de drift** possible ; octroi d'accès immédiat (écriture table).
- Onboarding réutilise l'auto-provisioning `pending` existant (`_load_dcm_user`).

**Négatives / à assumer**

- Pas d'access reviews Entra, de SCIM sortant ni de Conditional Access **par projet** (gouvernance déportée dans DCM : `dcm_audit_log`, `platform_role`, `project_members`).
- Migration des utilisateurs « plats » existants vers des projets par défaut à prévoir.
- Rétrocompat `role_permissions` / matrice frontend `role-access.ts` avec `platform_role` + rôle projet.

## Déclencheurs de bascule vers V1

Rouvrir cette décision **uniquement si** l'un de ces besoins se confirme :

1. l'IAM groupe **exige** des access reviews Entra par périmètre (conformité) ;
2. DCM doit **provisionner des accès réels** ailleurs (Databricks SCIM, …) ;
3. besoin de **Conditional Access différencié par projet**.

La bascule est **additive** (activer provisioning + réconciliation V1) grâce à `entra_group_id` nullable, sans refonte du modèle « projet ».

## Références

- Spike V1 : [README.md](./README.md)
- Spike V2 (retenu) : [README-v2-single-entra-group.md](./README-v2-single-entra-group.md)
- Schéma Delta prototype : [ddl.sql](./ddl.sql)
- Prototype d'autorisation : [project_scope_prototype.py](./project_scope_prototype.py)
