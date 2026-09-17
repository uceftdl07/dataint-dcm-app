# Alerting Module DCM - Data Model

Source Confluence: https://tdf.atlassian.net/wiki/spaces/TDF/pages/4816208345/Alerting+Module+DCM+Data+Model

Ce document décrit le modèle de données du module d'alerting DCM. Il partage les tables `notification_channels` et `alert_configs` avec le système d'anomalies. Ces tables sont stockées dans Unity Catalog sous `it.ba_data_connect_monitoring__a`.

## 1. Tables du module d'alerting

Le module d'alerting utilise 2 tables Delta dédiées, en relation avec les tables du système d'anomalies :

| Table | Rôle | Propriétaire |
| --- | --- | --- |
| `notification_channels` | Référentiel des canaux de notification configurés (email, teams, jira) | Module Alerting |
| `alert_configs` | Association anomaly_rule <-> notification_channel (détermine quoi alerter sur quoi) | Module Alerting |
| `anomaly_reports` | Utilisé en lecture pour charger le rapport lors du dispatch + UPDATE alert_sent_at et jira_ticket_url | Système Anomalies |

## 2. Table : notification_channels

| Colonne | Type | Nullable | Description |
| --- | --- | --- | --- |
| **id** (PK) | STRING (UUID) | NOT NULL | Identifiant unique du canal |
| name | STRING | NOT NULL | Nom lisible (ex: "Canal Teams DataOps", "Email DBA Team") |
| channel_type | STRING ENUM | NOT NULL | `email` \| `teams` \| `jira` |
| config_json | STRING (JSON) | NOT NULL | Configuration du canal - référence au secret Key Vault (jamais le secret en clair) |
| is_active | BOOLEAN | NOT NULL DEFAULT true | Désactiver sans supprimer (les alert_configs associés sont ignorés) |
| created_by | STRING | NULL | OID Entra ID de l'utilisateur créateur |
| created_at | TIMESTAMP | NOT NULL | Date de création |

### Structure config_json par channel_type

| Type | Schéma config_json | Exemple |
| --- | --- | --- |
| email | `{"secret_name": str, "recipients": [str]}` | `{"secret_name": "dcm-mailjet-api-key", "recipients": ["team@totalenergies.com"]}` |
| teams | `{"secret_name": str}` | `{"secret_name": "dcm-teams-webhook-dataops"}` |
| jira | `{"project_key": str, "issue_type": str, "secret_name": str}` | `{"project_key": "DCINT", "issue_type": "Bug", "secret_name": "dcm-jira-api-token"}` |

## 3. Table : alert_configs

| Colonne | Type | Nullable | Description |
| --- | --- | --- | --- |
| **id** (PK) | STRING (UUID) | NOT NULL | Identifiant unique |
| rule_id (FK) | STRING (UUID) | NOT NULL | Référence vers `anomaly_rules.id` |
| channel_id (FK) | STRING (UUID) | NOT NULL | Référence vers `notification_channels.id` |
| is_active | BOOLEAN | NOT NULL DEFAULT true | Active/désactive cette config d'alerte spécifiquement |
| `resend_frequency` | STRING | NULL | immediate_only \| daily \| weekly \| monthly - cadence de rappel tant que l'incident est actif |
| `last_reminder_sent_at` | TIMESTAMP | NULL | horodatage du dernier rappel envoyé (dédoublonnage du job de renvoi) |
| created_by | STRING | NULL | OID Entra ID créateur |
| created_at | TIMESTAMP | NOT NULL | Date de création |

**Cardinalité :** Une règle peut avoir plusieurs alert_configs (ex: email + teams + jira en même temps). Un même canal peut être utilisé par plusieurs règles. Relation N:N entre anomaly_rules et notification_channels via alert_configs.

## 4. Champs alerting dans anomaly_reports

Les champs suivants de la table `anomaly_reports` sont gérés par le module d'alerting :

| Colonne | Type | Description | Mis à jour par |
| --- | --- | --- | --- |
| jira_ticket_url | STRING | URL du ticket Jira créé (DCINT-XXXX) - null si pas de canal Jira configuré | Alerting Service après création issue Jira |
| alert_sent_at | TIMESTAMP | Horodatage de la dernière notification envoyée avec succès | Alerting Service après fan-out |
| `resolution_sent_at` | TIMESTAMP | NULL | horodatage d'envoi de la notification de résolution |

## 5. DDL SQL (Unity Catalog)

```sql
-- notification_channels
CREATE TABLE IF NOT EXISTS it.ba_data_connect_monitoring__a.notification_channels (
  id STRING NOT NULL,
  name STRING NOT NULL,
  channel_type STRING NOT NULL,  -- email | teams | jira
  config_json STRING NOT NULL,   -- JSON ref. secret KV, jamais secret en clair
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_by STRING,
  created_at TIMESTAMP NOT NULL,
  CONSTRAINT pk_notification_channels PRIMARY KEY (id),
  CONSTRAINT chk_channel_type CHECK (channel_type IN ('email', 'teams', 'jira'))
) USING DELTA
COMMENT 'Référentiel des canaux de notification DCM - alerting module';

-- alert_configs
CREATE TABLE IF NOT EXISTS it.ba_data_connect_monitoring__a.alert_configs (
  id STRING NOT NULL,
  rule_id STRING NOT NULL,      -- FK -> anomaly_rules
  channel_id STRING NOT NULL,   -- FK -> notification_channels
  is_active BOOLEAN NOT NULL DEFAULT true,
  resend_frequency STRING,
  last_reminder_sent_at TIMESTAMP,
  created_by STRING,
  created_at TIMESTAMP NOT NULL,
  CONSTRAINT pk_alert_configs PRIMARY KEY (id),
  CONSTRAINT fk_alert_configs_rule
    FOREIGN KEY (rule_id) REFERENCES it.ba_data_connect_monitoring__a.anomaly_rules(id),
  CONSTRAINT fk_alert_configs_channel
    FOREIGN KEY (channel_id) REFERENCES it.ba_data_connect_monitoring__a.notification_channels(id),
  CONSTRAINT uq_alert_config UNIQUE (rule_id, channel_id)
) USING DELTA
COMMENT 'Association règle anomalie <-> canal notification - alerting module';
```

## 6. Secrets Azure Key Vault - nomenclature

**Règle de nommage :** Tous les secrets liés au module d'alerting suivent le préfixe `dcm-` dans Azure Key Vault. L'accès se fait via Managed Identity de l'App Service backend (pas de credentials en dur).

| Secret | Nom Key Vault | Type |
| --- | --- | --- |
| API Key MailJet | `dcm-mailjet-api-key` | STRING |
| Secret MailJet (Public/Private) | `dcm-mailjet-secret-key` | STRING |
| Webhook Teams (1 secret par canal) | `dcm-teams-webhook-{canal-name}` | STRING (URL) |
| Token API Jira | `dcm-jira-api-token` | STRING |
| Email expéditeur | `dcm-mailjet-sender-email` | STRING |
