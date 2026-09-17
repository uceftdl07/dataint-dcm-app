# Spike — Extraction metadata Cognite : centralisée vs par LZ

> Comparatif d'approche pour collecter les metadata Cognite (`extraction_pipelines`) de plusieurs plateformes et les exposer côté Databricks AWS · 2026-08-17

---

## Contexte & objectif

Collecter les **metadata d'extraction** (API `extraction_pipelines`) de plusieurs plateformes hébergées sur **Cognite Data Fusion (CDF)** et les exposer sous forme de table Delta côté **Databricks AWS**, où vivent les flux d'intégration DCM.

**Contrainte réseau structurante :**

- Cognite vit dans le **vnet Azure**. Joignable **uniquement** depuis Azure.
- Les flux d'intégration DCM sont sur **AWS**. La donnée doit atterrir côté AWS.
- Un environnement **Databricks Azure** a déjà accès réseau à CDF.

> Même forme de problème que le spike [delta-sharing-azure-to-aws-billing](delta-sharing-azure-to-aws-billing.md) : **AWS ne doit jamais toucher le réseau/storage Azure directement**. C'est un composant côté Azure qui fait la lecture, AWS ne reçoit que le résultat via HTTPS.

---

## Option écartée d'emblée — Databricks AWS appelle l'API Cognite en direct

**Impossible** : CDF n'est pas joignable depuis AWS (vnet Azure privé). Nécessiterait une exposition réseau AWS↔Azure = **rejeté sécurité** (même verdict que le firewall ADLS dans le spike billing). Non poursuivi.

Restent 2 options réalistes.

---

## Les 2 options

### Option A — Cognite Functions *(recommandée)*

Script d'extraction packagé comme **Cognite Function**, tourne **dans** CDF (Azure). Lit `extraction_pipelines` en local, construit un `MetricPayload`, pousse en HTTPS sortant → **Apigee**. La chaîne d'ingestion AWS existante prend le relais.

```
CDF (Cognite Function)
  │ lit extraction_pipelines API (intra-CDF)
  │ construit MetricPayload
  ▼ HTTPS 443 + JWT Entra ID
Apigee
  ▼
dcm-lambda-ingestion → SQS → dcm-databricks-pipeline (AWS)
  ▼
table Delta AWS
```

### Option B — Azure Databricks passerelle

Job Databricks sur workspace **Azure** (déjà peer au vnet CDF). Appelle l'API Cognite, transforme, renvoie les **résultats seulement** côté AWS (HTTPS via Apigee ou SQL Warehouse OAuth M2M, comme le spike billing).

```
Azure Databricks (job)
  │ appelle API Cognite (intra-vnet Azure)
  ▼ résultats uniquement — HTTPS 443
Apigee / SQL Warehouse
  ▼
AWS → table Delta
```

---

## Comparatif détaillé

| # | Axe | Option A — Cognite Functions | Option B — Azure Databricks passerelle |
|---|---|---|---|
| 1 | Accès réseau CDF | Natif, intra-CDF. Zéro peering à gérer | OK **si** workspace Azure déjà peer/allowlist vnet CDF |
| 2 | Compute | Serverless CDF, dimensionné auto | Cluster/serverless Databricks |
| 3 | Coût récurrent | ~0 idle, facturé à l'exécution | Cluster tourne pour appeler du REST = Spark surdimensionné |
| 4 | Adéquation charge | Idéal metadata (petit volume, pas Spark) | Justifié si gros volume / transform Spark |
| 5 | Transport vers AWS | HTTPS sortant CDF → Apigee | Egress cross-cloud Azure→AWS ou SQL WH |
| 6 | Accès storage cross-cloud | Aucun | Aucun si résultats-only |
| 7 | Limites techniques | Timeout ~10 min, mémoire cappée, deps à packager | Aucune limite pratique, deps libres |
| 8 | Scheduling | CDF Schedules (cron natif) | Databricks Jobs |
| 9 | Auth Cognite | Identité CDF interne | SP Entra ID + secret Key Vault |
| 10 | Auth vers AWS | JWT Entra ID → Apigee | JWT Entra ID → Apigee (idem) |
| 11 | Observabilité | Dans CDF (moins familier) | Stack Databricks connue |
| 12 | Dépendances infra | 1 function + 1 schedule + 1 credential Apigee | Workspace Azure + peering vnet + SP + Key Vault + job |
| 13 | Multi-plateforme (N projets CDF) | 1 function itère, ou 1/projet | 1 job boucle sur N projets |
| 14 | Effort mise en place | Faible (rien côté réseau) | Moyen (réseau + SP/secret si absents) |
| 15 | Dépendance équipe CDF | Forte (deploy/monitor dans CDF) | Faible (autonome Data Eng) |
| 16 | Fit archi DCM (Scénario 2) | Élevé (= collecteur de plus → Apigee) | Moyen (passerelle dédiée hors pattern) |

---

## Décision retenue — Option A (Cognite Functions)

Pondération sur critères : **solidité, maintenabilité, peu de dépendances, facilité de mise en place**.

| Critère | Option A | Option B |
|---|---|---|
| Peu de dépendances | ✅✅ Zéro infra à créer | ❌ Workspace + peering + SP + Key Vault |
| Facilité mise en place | ✅ Script + package + schedule | ❌ Chantier réseau si peering absent |
| Solidité | ✅ Peu de pièces mobiles | ⚠️ Plus de composants |
| Maintenabilité | ✅ Un artefact, sortie `MetricPayload` (pattern connu) | ⚠️ Pipeline distribué 2 clouds |

**Pourquoi A :**

- Le **réseau disparaît** comme problème : la function est déjà dans CDF, rien à traverser. B dépend d'un peering vnet Azure↔CDF (plus gros risque projet s'il n'existe pas).
- **Moins de secrets** : identité CDF interne côté Cognite + un seul JWT Apigee. B ajoute un SP + secret Key Vault à roter.
- **Colle au pattern collecteur DCM** : sortie `MetricPayload` → Apigee → Lambda → pipeline. Cognite devient juste **un collecteur de plus** (Scénario 2).

**Condition qui ferait basculer vers B** — choisir A si et seulement si :

1. On peut déployer/planifier une Cognite Function dans le(s) CDF, **et**
2. Une extraction tient en **< 10 min** avec des **deps Python packageables**.

Si un point saute (deploy CDF verrouillé, extraction longue, lib lourde) → **B obligatoire**. Pour de la metadata (petit volume), les deux tiennent → A reste le bon choix.

---

## Prérequis (Option A)

| Élément | Détail | Owner |
|---|---|---|
| Accès deploy Cognite Function | Droit de déployer + planifier dans le(s) CDF | Équipe Cognite / CDF |
| Credential Apigee | Client Entra ID (JWT) pour POST vers Apigee | DCM / IAM |
| Contrat `MetricPayload` | Domaine metadata mappé sur `MetricPayload` (schema_version 1.1) | Data Eng DCM |
| Route Apigee → Lambda | Endpoint d'ingestion existant réutilisé | DCM |
| CDF Schedule | Cron de déclenchement de la function | Équipe Cognite / Data Eng |

---

## Points ouverts

- [ ] Peut-on déployer une Cognite Function dans le(s) CDF (droits / équipe dispo) ?
- [ ] Durée réelle d'une extraction < 10 min (timeout CDF) ?
- [ ] Les N plateformes sont-elles dans le **même tenant CDF** ou des **CDF séparés** ? (décide *centralize* vs *per-LZ*)
- [ ] Deps Python nécessaires packageables dans une Cognite Function ?
- [ ] Peering vnet Azure↔CDF existant (uniquement requis si bascule vers B) ?
- [ ] Mapping metadata `extraction_pipelines` → schéma `MetricPayload` / domaine cible

---

## Conclusion & prochaine étape

Appel direct Databricks AWS → Cognite : **impossible** (réseau/sécurité).

Approche retenue : **Option A — Cognite Function → Apigee → chaîne d'ingestion AWS**. Le minimum de dépendances, pas de chantier réseau, aligné sur le pattern collecteur DCM.

**Next step** : valider les 4 premiers points ouverts, puis POC d'une Cognite Function qui lit `extraction_pipelines` et POST un `MetricPayload` de test vers Apigee.
