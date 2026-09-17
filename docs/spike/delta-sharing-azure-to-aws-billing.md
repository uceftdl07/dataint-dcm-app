# Spike — Delta Sharing Azure → AWS : system.billing.usage

> Source : [Confluence TDF/4782981210](https://tdf.atlassian.net/wiki/spaces/TDF/pages/4782981210/) · 2026-07-21

---

## Contexte & objectif

Centraliser `system.billing.usage` (Databricks Azure) dans le workspace **Databricks AWS** pour analyse conso/coût multi-cloud.

Voie initiale : **Delta Sharing UC → UC** (sans copie, sans pipeline custom). **Résultat : bloqué.**

---

## Pourquoi Delta Sharing échoue

`system.*` non partageables nativement → workaround Azure : **vue matérialisée** dans :

```
catalog_badsdataeng_dev.sandbox-azure-sys-billing.usage
```

Un Delta Share a été créé sur ce schéma (avec la team DAP). Mais le **firewall ADLS Gen2** rejette les accès depuis le réseau AWS :

- Métadonnées du share visibles côté AWS ✓
- Lecture des données (accès storage) rejetée ✗ — les IP/réseaux AWS Compute ne sont pas allowlistables sur le storage Azure

> Delta Sharing open protocol = accès direct au storage depuis AWS = **impossible** dans cette config réseau.

---

## Solution retenue — SP OAuth M2M + Azure SQL Warehouse

Déplacer la lecture vers le **plan compute Azure** (SQL Warehouse), qui a déjà accès au storage via le firewall.

```
AWS Databricks workspace
  │  SQL query (OAuth M2M — HTTPS 443)
  ▼
Azure SQL Warehouse ──── réseau intra-Azure (firewall OK) ────▶ ADLS Gen2
  │
  │  résultats (lignes uniquement — AWS ne touche jamais au storage)
  ▼
AWS Databricks workspace → table Delta locale AWS
```

**Pourquoi ça passe le firewall :**
- ADLS Gen2 ↔ SQL Warehouse : 100 % intra-Azure
- AWS ↔ SQL Warehouse : HTTPS uniquement (pas d'accès storage)
- Auth : Service Principal OAuth M2M (pas de secret user)

---

## Prérequis

| Élément | Détail | Owner |
|---|---|---|
| Workspace Azure Databricks | Réutiliser `3059738143768593` (dev) / `1294448047628701` (prod) ou LZ dédiée | DAP / Cloud |
| Service Principal Entra ID | Création + secret, OAuth M2M | DAP / IAM |
| Permissions UC | `USE CATALOG`, `USE SCHEMA`, `SELECT` sur `usage` | Data Eng / DAP |
| Accès `system.billing` | System read activé + grant | Admin metastore Azure |
| Azure SQL Warehouse | Warehouse dédié + `CAN USE` pour le SP | DAP |
| Réseau | Endpoint warehouse HTTPS 443 joignable depuis AWS | Network / DAP |
| Côté AWS | Secret SP (secret scope Databricks), job de copie | Data Eng |

---

## Options d'implémentation AWS (classées par priorité POC)

### Option A — JDBC / Spark connector *(recommandée pour POC)*

PySpark job AWS → lit via driver JDBC `databricks` (auth SP OAuth) → écrit Delta table locale.

```python
df = (spark.read
    .format("jdbc")
    .option("url", "jdbc:databricks://<azure-host>:443/default")
    .option("dbtable", "catalog_badsdataeng_dev.`sandbox-azure-sys-billing`.usage")
    .option("driver", "com.databricks.client.jdbc.Driver")
    .option("AuthMech", "11")
    .option("Auth_Flow", "1")               # OAuth M2M
    .option("OAuth2ClientId",     dbutils.secrets.get("scope", "sp-client-id"))
    .option("OAuth2ClientSecret", dbutils.secrets.get("scope", "sp-client-secret"))
    .option("OAuth2TokenEndpoint", "https://login.microsoftonline.com/<tenant>/oauth2/token")
    .load())

df.write.format("delta").mode("overwrite").saveAsTable("billing.azure_usage")
```

### Option B — Python `databricks-sql-connector` *(alternative légère)*

Script Python, requête incrémentale sur `usage_date`, écriture Delta. Moins de config que JDBC.

### Option C — Lakehouse Federation *(industrialisation)*

`CONNECTION` vers le SQL Warehouse Azure + `FOREIGN CATALOG` → SQL natif depuis AWS, aucun code custom.
À valider : auth SP + règles firewall sur l'endpoint warehouse avec DAP.

---

## Points ouverts

- [ ] SP peut-il s'authentifier sur le SQL Warehouse Azure **depuis un réseau AWS** (firewall endpoint warehouse) ?
- [ ] Requête `usage` : full scan vs **incrémentale** sur `usage_date` / `usage_end_time` (volume / coût)
- [ ] Fréquence de refresh de la vue matérialisée Azure vs fréquence pull AWS
- [ ] Latence / SLA acceptables pour les billing data AWS
- [ ] Stockage du secret SP côté AWS : Databricks secret scope vs **Secrets Manager** (DCM standard)
- [ ] Lakehouse Federation : compatibilité auth SP + réseau à confirmer DAP

---

## Conclusion & prochaine étape

Delta Sharing direct **bloqué** (firewall ADLS Gen2 cross-cloud).

Workaround retenu : **SP OAuth M2M → Azure SQL Warehouse** (lecture 100 % intra-Azure) → AWS reçoit uniquement les lignes résultats.

**Next step** : POC Option A (JDBC) + validation permissions SP + règles réseau avec DAP.
