# Alerting Module DCM - Operational Description

Source Confluence: https://tdf.atlassian.net/wiki/spaces/TDF/pages/4816175578/Alerting+Module+DCM+Operational+Description

Ce document décrit le fonctionnement du module d'alerting DCM du point de vue utilisateur. Il couvre les canaux de notification supportés, la configuration des alertes et les flux opérationnels de notification.

## 1. Vue d'ensemble

Le module d'alerting DCM est déclenché automatiquement lorsque le système d'anomalies détecte un incident. Il permet d'envoyer des notifications via 3 canaux :

| Canal | Service | Format | Use case |
| --- | --- | --- | --- |
| **Email** | MailJet API | Template HTML | Notification d'équipe, audit trail, destinataires multiples |
| **Teams** | Incoming Webhook | Adaptive Card | Alerte temps réel dans un channel Teams dédié |
| **Jira** | REST API Jira | Issue DCINT | Création automatique d'un ticket d'incident pour suivi |

## 2. Configuration utilisateur

L'utilisateur configure le module d'alerting depuis 2 endroits dans l'application DCM :

### 2.1 Notification Settings (référentiel des canaux)

Page de configuration accessible depuis le menu paramètres DCM. Permet de créer et gérer les canaux de notification réutilisables :

* Créer un canal **Email** : nom + liste de destinataires
* Créer un canal **Teams** : nom + webhook URL du channel Microsoft Teams (stocké en Key Vault)
* Créer un canal **Jira** : nom + clé du projet Jira + type d'issue
* Activer/désactiver un canal
* Supprimer un canal (désactive automatiquement les alert_configs associés)

### 2.2 Alert Config Dialog (association règle ↔ canal)

Dialog accessible depuis la page Anomaly Rules ou lors de la création d'une règle custom. Permet d'associer une règle d'anomalie à un ou plusieurs canaux de notification :

* Sélection de la règle d'anomalie cible
* Choix des canaux : email | teams | jira (multi-sélection possible)
* Activation/désactivation par configuration

## 3. Flux de notification

1. Le pipeline Databricks détecte une anomalie et crée un rapport (status=active)
2. Le pipeline appelle `POST /internal/anomaly-reports` avec le `report_id` (JWT M2M)
3. L'Alerting Service charge les `alert_configs` actifs liés à la règle de l'incident
4. Pour chaque config active, l'Alerting Service envoie une notification vers le canal configuré
5. L'Alerting Service met à jour `anomaly_reports.alert_sent_at`
6. Si canal Jira : l'URL du ticket créé est stockée dans `anomaly_reports.jira_ticket_url`

## 4. Contenu des notifications par canal

### Email (MailJet template HTML)

| Champ | Valeur |
| --- | --- |
| Sujet | `[{severity}] Anomalie DCM : {rule_name} / {lz_id}` |
| Corps | Template HTML anomaly_alert - sévérité, règle, LZ, valeur métrique, seuil, lien vers rapport DCM |
| From | dcm-alerts@company.com (via MailJet) |
| To | Liste destinataires configurée dans le canal |

### Teams (Adaptive Card)

| Champ | Valeur |
| --- | --- |
| Titre | Anomalie DCM détectée |
| Sévérité | Badge coloré selon low/medium/high/critical |
| Corps | Règle d'anomalie, LZ concernée, valeur observée vs seuil, start_date |
| Action | Bouton "Voir le rapport" -> lien vers la page Anomaly Reports DCM |

### Jira (création issue DCINT)

| Champ Jira | Valeur |
| --- | --- |
| Projet | DCINT (configurable par canal) |
| Type | Bug (configurable par canal) |
| Titre | `[DCM Anomalie] {rule_name} - {lz_id}` |
| Priorité | Mapping sévérité -> Priorité Jira (low->Low, medium->Medium, high->High, critical->Highest) |
| Description | Rapport complet : règle, LZ, valeur, seuil, start_date, logs |
| Labels | dcm-anomaly, {domain}, {severity} |

## 5. Activation MailJet - prérequis PO

**Action requise :** Le PO doit activer un compte MailJet et générer une clé API. La clé API doit être stockée dans Azure Key Vault sous le nom `dcm-mailjet-api-key`. La vérification du domaine d'envoi est requise côté MailJet avant la mise en production.

## 6. Roadmap alerting

| Tâche | Responsable | Statut |
| --- | --- | --- |
| Activation compte MailJet | PO | Planned |
| Module envoi notification - template HTML email | Data | Planned |
| Extension notification email (API MailJet) | Data | Planned |
| Extension notification webhook Teams | Data | Planned |
| Référentiel notification_channels (API + UI) | Full Stack | Planned |
| Menu de configuration webhook Teams | Full Stack | Planned |
| Intégration Jira via REST API | Full Stack | Planned |
