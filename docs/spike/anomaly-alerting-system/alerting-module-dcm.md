# Alerting Module DCM

Source Confluence: https://tdf.atlassian.net/wiki/spaces/TDF/pages/4816797974/Alerting+Module+DCM

Cette section regroupe toute la documentation du module d'alerting de la plateforme Data Connect Monitoring (DCM). Le module permet d'envoyer des notifications (email, Teams, Jira) lorsqu'une anomalie est détectée par le système d'anomalies DCM.

## Contenu de cette section

| Page | Description |
| --- | --- |
| [Operational Description](alerting-module-dcm-operational-description.md) | Description fonctionnelle du module - canaux supportés, flux de notification, configuration utilisateur |
| [Technical Architecture](alerting-module-dcm-technical-architecture.md) | Architecture technique - Alerting Service, intégrations MailJet/Teams/Jira, sécurité secrets |
| [Design](alerting-module-dcm-design.md) | Design détaillé - fan-out pattern, templates de notification, UI configuration |
| [Data Model](alerting-module-dcm-data-model.md) | Modèle de données - tables notification_channels et alert_configs |

## Canaux supportés

| Canal | Service | Statut |
| --- | --- | --- |
| Email | MailJet API | In Progress |
| Teams | Incoming Webhook (Adaptive Card) | In Progress |
| Jira | REST API Jira (MCP Atlassian) | In Progress |

## Liens rapides

* [Architecture & Design (Solution) - page parente](https://tdf.atlassian.net/wiki/spaces/TDF/pages/4623761505)
* [Anomaly System DCM - documentation liée](https://tdf.atlassian.net/wiki/spaces/TDF/pages/4816011742)
