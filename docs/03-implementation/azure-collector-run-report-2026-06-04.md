# Rapport de collecte — `dcm-azure-collector` (Data Squad LZ)

**Date du run :** 2026-06-04 ~12:14 UTC  
**Commande :** `set -a && . ./.env && set +a && .venv/bin/dcm-azure-collector` (1 cycle observé)  
**Log brut :** `/tmp/dcm-collector-run.log` (reproductible avec la même commande + `tee`)

**Périmètre**

| Paramètre | Valeur |
|-----------|--------|
| Landing zone | `sub-iasp-lz-DataSquad` |
| Subscription | `05ea2e78-8e32-4407-8b27-27ba621fa084` |
| Identity locale | `DefaultAzureCredential` → `EnvironmentCredential` / `ClientSecretCredential` (`AZURE_CLIENT_ID` Builder SPN) |
| Collecteurs activés | **8/8** (défaut config) |
| Lookback ADF | **24 h** |
| Ingestion | Apigee dev → **6/6 payloads HTTP 202** |

---

## 1. Synthèse exécutive (validation équipe Data)

| Verdict global | Détail |
|----------------|--------|
| **Collecteur fonctionnel** | 6 domaines ont produit des données et ont été ingérés via Apigee. |
| **Pas de blocage RBAC majeur** sur subscription (ADF, Databricks, Policy, DB list, SCIM). |
| **2 écarts à traiter** | FinOps (`cost`) : **429 rate limit** — pas permission. Sécurité : **0 alerte** — données, pas erreur API. |
| **Key Vault local** | **403** sur secrets — **non bloquant** (secrets déjà dans `.env`). |

**Recommandation courte :** valider le pipeline ingestion → DLT pour les 6 domaines envoyés ; ouvrir ticket Azure Cost Management (429) ou espacer les appels ; confirmer avec l’équipe Sécurité si 0 alerte Defender est attendu sur cette subscription.

---

## 2. Matrice par collecteur

Légende **classification** :

- **OK** — données collectées et envoyées Apigee
- **VIDE** — API OK, 0 enregistrement (données absentes ou filtre métier)
- **ÉCHEC** — collecteur en erreur, rien envoyé
- **WARN** — fonctionne mais avec avertissement infra

| # | Collecteur | Domaine UC | Métriques | Durée | Apigee | Classification | Cause probable |
|---|------------|------------|-----------|-------|--------|----------------|----------------|
| 1 | `datafactory` | `curated_pipeline_metrics` | **3** | 1,1 s | 202 | **OK** | 2 factories, 3 pipeline runs sur 24 h |
| 2 | `activity_runs` | `curated_activity_runs` | **4** | 1,5 s | 202 | **OK** | Activités liées aux runs ADF (faible volume) |
| 3 | `databricks` | `curated_compute_metrics` | **69** | 1,5 s | 202 | **OK** | 2 workspaces, clusters listés |
| 4 | `users` | `curated_user_metrics` | **176** | 4,4 s | 202 | **OK** | SCIM : dbw-dsde-d-03 (114), dbw-dsde-p-03 (62) |
| 5 | `cost_management` | `curated_cost_metrics` | **0** | 13,3 s | — | **ÉCHEC** | HTTP **429** Cost Management (3 tentatives) |
| 6 | `databases` | `curated_database_metrics` | **1** | 1,6 s | 202 | **OK** (partiel) | 1 ressource DB dans la sub (PostgreSQL typique) |
| 7 | `security_center` | `curated_security_alerts` | **0** | 0,5 s | — | **VIDE** | `total_alerts=0` — API Defender OK |
| 8 | `standard_checks` | `curated_standard_checks` | **334** | 0,9 s | 202 | **OK** | Policy non-conformes (`non_compliant_only`) |

**Total enregistrements collectés :** 587  
**Total envoyés à l’ingestion :** 587 (6 payloads ; cost + security exclus)

---

## 3. Détail des données collectées (par domaine)

### 3.1 Pipeline (`datafactory`)

- **API :** `factories.list` + `pipeline_runs.query_by_factory` (fenêtre 24 h)
- **Résultat :** `factory_count=2`, `metric_count=3`
- **Interprétation :** accès ADF **OK**. Volume faible = peu de runs sur 24 h (normal dev), pas un problème de permissions.
- **Table UC :** `curated_pipeline_metrics` — champs `factory_name`, `resource_group`, `run_id`, `pipeline_name` alimentés.

### 3.2 Activity runs (`activity_runs`)

- **API :** `activity_runs.query_by_pipeline_run` par run ADF
- **Résultat :** `activity_run_collected total=4`
- **Interprétation :** cohérent avec 3 pipeline runs ; lignage activité **OK** mais échantillon minuscule.
- **Table UC :** `curated_activity_runs` — `activity_run_id` synthétisé côté DLT.

### 3.3 Compute Databricks (`databricks`)

- **API :** ARM workspaces `200` + `clusters/list` sur :
  - `adb-3059738143768593.13.azuredatabricks.net`
  - `adb-1294448047628701.1.azuredatabricks.net`
- **Résultat :** `workspace_count=2`, `metric_count=69`
- **Interprétation :** token management + token Databricks **OK**.
- **Limite produit :** pas de `avg_cpu_utilization_pct` / `estimated_hourly_cost_usd` (non implémenté collecteur).

### 3.4 Users Databricks (`users`)

- **API :** SCIM `/api/2.0/preview/scim/v2/Users` — **200** sur les 2 workspaces
- **Résultat :** 176 utilisateurs (114 + 62)
- **Interprétation :** permissions workspace SCIM **OK** pour le SPN Builder.

### 3.5 FinOps (`cost_management`) — ÉCHEC

- **API :** `POST .../Microsoft.CostManagement/query`
- **Erreur :** `HTTP 429 Too Many Requests` (tentatives 1, 2, 3)
- **Classification :** **quota / throttling Azure**, pas `403 Forbidden`
- **Action équipe :**
  - Vérifier que le rôle **Cost Management Reader** est bien assigné (pour exclure un faux 429 masquant un autre souci — peu probable ici).
  - Réduire fréquence collecte cost, backoff plus long, ou fenêtre dédiée (éviter rafales avec autres appels management).
  - Contacter support Azure si 429 persistant hors heures de pointe.

### 3.6 Databases (`databases`)

- **API :** list SQL / PostgreSQL Flexible / MySQL / Cosmos + Azure Monitor
- **Résultat :** `metric_count=1`
- **Interprétation :**
  - **Accès list resources : OK** (sinon warning `database_category_failed` dans les logs — **aucun** sur ce run).
  - **1 seule DB détectée** dans la subscription = **périmètre données**, pas refus RBAC global.
  - Historique local : `monitoring-postgresql` (RG `monitoring`) — métriques Monitor souvent NULL si pas de points sur 15 min.
- **Action :** confirmer avec équipe infra s’il existe d’autres SQL/Cosmos attendus dans cette sub.

### 3.7 Security (`security_center`) — VIDE

- **API :** Defender alerts list — succès
- **Résultat :** `total_alerts=0`, `collected=0`
- **Interprétation :** **pas d’alerte active** à la collecte, pas erreur permission.
- **RBAC attendu :** **Security Reader** (subscription) — semble suffisant si 0 alerte est réel.
- **Action :** valider avec SOC / équipe sécu si dashboard DCM doit afficher des alertes résolues (`include_resolved` désactivé par défaut).

### 3.8 Compliance (`standard_checks`)

- **API :** Policy Insights `list_query_results_for_subscription` (NonCompliant)
- **Résultat :** `total=334`, `scope=non_compliant_only`
- **Interprétation :** accès Policy **OK** ; gouvernance alimentée.

---

## 4. Trace des erreurs et avertissements

| Horodatage (UTC) | Niveau | Événement | Impact | Permissions ? |
|------------------|--------|-----------|--------|---------------|
| 12:14:05 | info | Key Vault `dcm-entra-client-id` → **401** puis token → **403** | Aucun — fallback `.env` | **Oui** — SPN sans `Key Vault Secrets User` sur `azrmkvdsde-dcm` (optionnel en local) |
| 12:14:05 | info | Idem `dcm-entra-client-secret`, `dcm-apigee-api-key` **403** | Aucun | Idem |
| 12:14:16–28 | warning/error | Cost Management **429** ×3 | **Pas de `curated_cost_metrics` ce cycle** | **Non** — throttling |
| 12:14:30 | warning | `collector_empty_payload` security_center | Pas d’envoi domaine security | **Non** — 0 alerte |
| — | — | Aucun `403` sur ADF, Databricks, Policy, DB ARM | — | — |

**Auth Azure subscription :** `ClientSecretCredential.get_token` / `EnvironmentCredential` **succeeded** sur tous les appels métier.

**Apigee :** 6 × `POST .../metrics/ingest` → **202 Accepted**, `sent_failure=0`.

---

## 5. Permissions — besoin d’action ou non

### 5.1 Déjà suffisant (preuve : run OK)

| Rôle / accès | Preuve run |
|--------------|------------|
| **Reader** (subscription) | Databricks workspaces, Policy 334 lignes |
| **Data Factory** (lecture runs) | 3 pipeline + 4 activity runs |
| **Databricks workspace** (clusters + SCIM) | 69 clusters, 176 users |
| **Monitoring Reader** (implicite) | 1 snapshot DB Monitor |
| **Resource Policy Insights Reader** | 334 non-compliant |
| **Apigee + Entra ingestion** | 6 payloads 202 |

### 5.2 À clarifier / demander si besoin produit

| Besoin | Rôle Azure suggéré | Priorité |
|--------|-------------------|----------|
| FinOps stable | **Cost Management Reader** + gestion quota 429 | **P1** |
| Alertes Defender dans DCM | **Security Reader** + alertes actives dans la sub | P2 (données) |
| Secrets depuis KV en local/CI | **Key Vault Secrets User** sur `azrmkvdsde-dcm` | P3 (confort) |
| Plus de DB dans le rapport | Ressources dans la sub ou **Reader** sur autres RGs | P2 (données) |

### 5.3 Pas un problème de collecteur

- Registry 8 collecteurs : **OK**
- Lookback 24 h : **OK** (3 runs vs 0 avec 1 h)
- Sérialisation + Apigee : **OK**
- Échec cost = **plateforme Azure**, pas bug mapping UC

---

## 6. Mapping ingestion → tables Unity Catalog

| Domaine Apigee | Table silver | Statut ce run |
|----------------|--------------|---------------|
| `pipeline` | `curated_pipeline_metrics` | Données attendues DLT |
| `activity_run` | `curated_activity_runs` | Données attendues DLT |
| `compute` | `curated_compute_metrics` | Données attendues DLT |
| `user` | `curated_user_metrics` | Données attendues DLT |
| `database` | `curated_database_metrics` | 1 ligne attendue |
| `standard_check` | `curated_standard_checks` | 334 lignes attendues |
| `cost` | `curated_cost_metrics` | **Trou** ce cycle |
| `security` | `curated_security_alerts` | **Trou** ce cycle (0 alerte) |

**Contrôle post-ingestion (équipe Data) :**

```sql
SELECT domain, COUNT(*) AS n
FROM it.ba_data_connect_monitoring__a.raw_metrics
WHERE source_lz_id = 'sub-iasp-lz-DataSquad'
  AND collected_at >= current_timestamp() - INTERVAL 2 HOUR
GROUP BY domain;
```

---

## 7. Checklist validation avec l’équipe Data

- [ ] Confirmer que les **6 domaines** reçus dans `raw_metrics` / curated sont suffisants pour les dashboards cibles.
- [ ] **FinOps :** accepter mitigation 429 (intervalle, retry) ou escalade Azure.
- [ ] **Sécurité :** confirmer 0 alerte Defender attendu sur `05ea2e78-...`.
- [ ] **Pipeline :** confirmer que 3 runs / 24 h est représentatif ou augmenter lookback / planifier runs test ADF.
- [ ] **DB :** confirmer qu’une seule PostgreSQL `monitoring-postgresql` est le périmètre attendu.
- [ ] **RBAC prod :** aligner le SPN du collecteur (Managed Identity / Builder) avec les rôles §5.2 pour ACI/App Service.

---

## 8. Prochaines étapes techniques

1. Réinstaller le package local pour `--once` : `pip install -e .` dans `packages/dcm-azure-collector` (flag ajouté dans `main.py`).
2. Relancer : `.venv/bin/dcm-azure-collector --once`
3. Après fix 429 : vérifier `curated_cost_metrics` et `gold_cost_summary`.
4. Optionnel : `DCM_LOG_LEVEL=DEBUG` pour détail `sql_servers_found`, `postgresql_servers_found`, etc.

---

## Annexe — commande de reproduction

```bash
cd "/Users/zahramaaziz/Desktop/new squad/dataint-dcm-app/packages/dcm-azure-collector"
set -a && . ./.env && set +a
pip install -e .   # une fois, pour --once
.venv/bin/dcm-azure-collector --once 2>&1 | tee /tmp/dcm-collector-run.log
```

**Durée cycle observée :** ~26 s (12:14:06 → 12:14:32 UTC).
