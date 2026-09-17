# Alerting Module DCM - Technical Architecture

Source Confluence: https://tdf.atlassian.net/wiki/spaces/TDF/pages/4816306514/Alerting+Module+DCM+Technical+Architecture

Ce document décrit l'architecture technique du module d'alerting DCM - composants, flux d'intégration avec MailJet, Teams et Jira, et gestion sécurisée des secrets.

## 1. Composant central : Alerting Service

L'**Alerting Service** est un service Python intégré dans `packages/dcm-backend`. Il est déclenché de deux façons :

| Mode | Déclencheur | Description |
| --- | --- | --- |
| **Instantané** | POST /internal/anomaly-reports (Databricks -> Backend) | Appelé après chaque insertion de rapport d'anomalie par le pipeline Databricks |
| **On-demand** | POST /anomaly-reports/{id}/notify (frontend utilisateur) | L'utilisateur re-déclenche manuellement l'envoi de notifications pour un rapport existant |

## 2. Architecture de l'Alerting Service

```python
# packages/dcm-backend/alerting/
# ├── alerting_service.py     ← orchestrateur principal
# ├── channels/
# │   ├── base.py             ← NotificationChannel ABC
# │   ├── email_channel.py    ← MailJet client
# │   ├── teams_channel.py    ← Teams Webhook client
# │   └── jira_channel.py     ← Jira REST client
# └── templates/
#     └── anomaly_alert.html  ← template email MailJet

class AlertingService:
    async def dispatch(self, report_id: str) -> None:
        report = await self._load_report(report_id)
        configs = await self._load_alert_configs(report.rule_id)
        channels = self._build_channels(configs)
        await asyncio.gather(*[ch.send(report) for ch in channels])
        await self._mark_sent(report_id)
```

## 3. Intégration MailJet

| Élément | Détail |
| --- | --- |
| SDK | `mailjet-rest` (Python) |
| Auth | API Key stockée dans Azure Key Vault -> `dcm-mailjet-api-key` |
| Endpoint | `POST https://api.mailjet.com/v3.1/send` |
| Template | HTML inline - `alerting/templates/anomaly_alert.html` |
| Variables | rule_name, severity, lz_id, metric_value, threshold_value, start_date, report_url |
| From | Adresse d'expéditeur configurée dans MailJet (domaine vérifié) |
| Retry | 3 tentatives avec backoff exponentiel en cas d'erreur 5xx |

## 4. Intégration Teams Webhook

| Élément | Détail |
| --- | --- |
| Méthode | HTTP POST vers l'URL du webhook (Incoming Webhook connecteur Teams) |
| Format | Adaptive Card v1.4 (JSON) |
| Auth | URL du webhook stockée dans Azure Key Vault -> `dcm-teams-webhook-{canal_name}` |
| Contenu | Card avec sévérité (badge coloré), règle, LZ, valeur vs seuil, bouton "Voir rapport" |
| 1 config = 1 webhook | Chaque notification_channel de type teams possède son propre webhook URL |

## 5. Intégration Jira REST API

| Élément | Détail |
| --- | --- |
| Méthode | REST API Jira Cloud (`POST /rest/api/3/issue`) |
| Auth | Token API stocké dans Azure Key Vault -> `dcm-jira-api-token` |
| Projet | Configurable par canal (défaut: DCINT) |
| Priorité | Mapping automatique sévérité -> priorité Jira |
| Post-action | URL du ticket créé stockée dans `anomaly_reports.jira_ticket_url` |
| Idempotence | Vérification avant création : si `jira_ticket_url` déjà renseigné, pas de création dupliquée |

## 6. Sécurité des secrets

**Principe cardinal :** Aucun secret (clé API MailJet, webhook URL, token Jira) n'est stocké en base de données ni dans le code. La table `notification_channels.config_json` ne contient que le _nom_ du secret dans Azure Key Vault. La résolution est faite au runtime par le backend via Managed Identity Azure.

| Secret | Nom Key Vault | Utilisé par |
| --- | --- | --- |
| MailJet API Key | `dcm-mailjet-api-key` | EmailChannel |
| Teams Webhook URL (par canal) | `dcm-teams-webhook-{name}` | TeamsChannel |
| Jira API Token | `dcm-jira-api-token` | JiraChannel |

## 7. Gestion des erreurs

| Scénario | Comportement |
| --- | --- |
| Canal indisponible (5xx) | Retry 3x avec backoff - log erreur structuré - pas de blocage des autres canaux |
| Secret introuvable (Key Vault) | Log erreur critique + skip du canal - alerte opérationnelle |
| Ticket Jira déjà créé | Idempotence : pas de duplication si `jira_ticket_url` déjà présent |
| Fan-out partiel | Les canaux réussis sont traités indépendamment des canaux en erreur (asyncio.gather) |

## 8. Observabilité

* Logs structurés JSON via `structlog` - chaque envoi loggué avec report_id, channel_type, channel_id, success/error
* Métrique `alert_sent_at` dans `anomaly_reports` - permet de monitorer les délais de notification
* Logs d'erreur disponibles dans CloudWatch (ECS Fargate backend)
