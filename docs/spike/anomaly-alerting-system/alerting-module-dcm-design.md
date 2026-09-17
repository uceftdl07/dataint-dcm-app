# Alerting Module DCM - Design

Source Confluence: https://tdf.atlassian.net/wiki/spaces/TDF/pages/4816601343/Alerting+Module+DCM+Design

Ce document décrit le design détaillé du module d'alerting DCM - pattern fan-out, templates de notification, et design de l'UI de configuration.

## 1. Pattern Fan-out

L'Alerting Service utilise un pattern fan-out asynchrone : pour un rapport d'anomalie donné, il envoie en parallèle vers tous les canaux configurés pour la règle concernée.

```text
POST /internal/anomaly-reports { report_id, notification_type }
        |
        v
[Alerting Service]
   charge alert_configs actifs pour rule_id
        |
   +----+----+
   |    |    |
   v    v    v
Email Teams Jira   (asyncio.gather - parallele)
   |    |    |
   +----+----+
        |
   UPDATE alert_sent_at (incident) | resolution_sent_at (resolution)
```

## 2. Design de la classe NotificationChannel

```python
from abc import ABC, abstractmethod
from dcm_backend.schemas.anomaly import AnomalyReportSchema

class NotificationChannel(ABC):
    """Base class for all notification channels."""

    @abstractmethod
    async def send(self, report: AnomalyReportSchema, notification_type: str) -> None:
        """Send notification for the given anomaly report.
        notification_type: "incident" (alerte initiale / rappel) | "resolution" (cloture).
        """
        ...

    @abstractmethod
    async def _resolve_secret(self, secret_name: str) -> str:
        """Resolve secret from Azure Key Vault at runtime."""
        ...
```

## 3. Fréquence de renvoi d'alerte

* **Envoi immédiat** - systématique à la création de l'incident (`status = active`).
* **Rappels périodiques** - tant que `status = active`, selon `alert_configs.resend_frequency`.

| Valeur | Comportement |
| --- | --- |
| `immediate_only` | (défaut) aucun rappel, uniquement l'envoi initial |
| `daily` | rappel toutes les 24 h tant que l'incident est actif |
| `weekly` | rappel tous les 7 jours |
| `monthly` | rappel tous les 30 jours |

* **Implémentation** : job Databricks planifié qui scanne les incidents `active`, compare `now - last_reminder_sent_at` à la fréquence, renvoie si dû, puis met à jour `last_reminder_sent_at` (dédoublonnage).
* **Arrêt** : les rappels cessent automatiquement à la résolution de l'incident (voir §4).

## 4. Notification de résolution

* Déclenchée par `POST /internal/anomaly-reports/{id}/resolve` avec `notification_type = "resolution"`.
* Fan-out vers les mêmes canaux que l'alerte initiale.
* Trace : `anomaly_reports.resolution_sent_at`.

| Canal | Rendu résolution |
| --- | --- |
| Email | Template vert "Anomalie résolue" - règle, LZ, durée totale de l'incident, horodatage de résolution |
| Teams | Adaptive Card Good (vert), FactSet avec durée d'incident |
| Jira | Commentaire "Incident résolu par DCM" + transition du ticket vers Done (si le workflow le permet) |

## 5. Envoi manuel de notification

* Endpoint `POST /anomaly-reports/{id}/notify` (JWT user, permission requise).
* Renvoie vers tous les canaux configurés de la règle, ou un canal choisi via un mini-sélecteur.
* Cas d'usage : ré-alerter une astreinte, escalade manuelle. Met à jour `alert_sent_at`.

## 6. Template email - structure HTML

```html
<!-- anomaly_alert.html - Template MailJet -->
<div style="font-family: Arial, sans-serif; max-width: 600px;">
  <div style="background: {severity_color}; padding: 12px; color: white;">
    <h2>Anomalie DCM - {severity}</h2>
  </div>
  <table>
    <tr><td>Règle</td><td>{rule_name}</td></tr>
    <tr><td>Landing Zone</td><td>{lz_id}</td></tr>
    <tr><td>Valeur observée</td><td>{metric_value}</td></tr>
    <tr><td>Seuil configuré</td><td>{threshold_value}</td></tr>
    <tr><td>Début incident</td><td>{start_date}</td></tr>
  </table>
  <a href="{report_url}">Voir le rapport complet dans DCM</a>
</div>
```

## 7. Template Teams - Adaptive Card JSON

```json
{
  "type": "message",
  "attachments": [{
    "contentType": "application/vnd.microsoft.card.adaptive",
    "content": {
      "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
      "type": "AdaptiveCard",
      "version": "1.4",
      "body": [
        {
          "type": "TextBlock",
          "text": "Anomalie DCM détectée",
          "weight": "Bolder",
          "size": "Medium",
          "color": "Warning"
        },
        {
          "type": "FactSet",
          "facts": [
            {"title": "Règle", "value": "{rule_name}"},
            {"title": "Sévérité", "value": "{severity}"},
            {"title": "Landing Zone", "value": "{lz_id}"},
            {"title": "Valeur", "value": "{metric_value} (seuil: {threshold_value})"},
            {"title": "Début", "value": "{start_date}"}
          ]
        }
      ],
      "actions": [{
        "type": "Action.OpenUrl",
        "title": "Voir le rapport",
        "url": "{report_url}"
      }]
    }
  }]
}
```

## 8. Mapping sévérité -> couleurs et priorités

| Sévérité DCM | Couleur email (hex) | Couleur Teams | Priorité Jira |
| --- | --- | --- | --- |
| low | #17a2b8 (info blue) | Good | Low |
| medium | #ffc107 (warning yellow) | Warning | Medium |
| high | #fd7e14 (orange) | Warning | High |
| critical | #dc3545 (danger red) | Attention | Highest |

## 9. UI - Page Notification Settings

Design de la page de configuration des canaux de notification :

| Composant | Description |
| --- | --- |
| Tableau des canaux | Colonnes : Nom \| Type \| Statut \| Actions (éditer, supprimer, tester) |
| Bouton "Tester" | Envoie une notification test sur le canal sélectionné |
| Formulaire création canal Teams | Champs : Nom (text) + Webhook URL (password masked) + Bouton test avant sauvegarde |
| Formulaire création canal Email | Champs : Nom (text) + Destinataires (multi-input email) |
| Formulaire création canal Jira | Champs : Nom (text) + Clé projet (text) + Type d'issue (select) |
| Validation webhook Teams | Test de connectivité avant sauvegarde (POST de test vers l'URL webhook) |

## 10. Diagramme de séquence complet

Le diagramme de séquence complet est disponible dans `docs/08-anomaly-alerting-system/ANOMALY-ALERTING-SYSTEM-DESIGN.drawio` - Page 3 : Alerting Flow.

```text
Databricks         Backend API         MailJet/Teams/Jira       Unity Catalog
    │                   │                     │                      │
    │──POST /internal/anomaly-reports──▶│     │                      │
    │   {report_id, notification_type, JWT M2M}            │     │                      │
    │                   │──load report──┼─────┼─────────────────────▶│
    │                   │◀──────────────┼─────┼──────────report──────│
    │                   │──load configs─┼─────┼─────────────────────▶│
    │                   │◀──────────────┼─────┼──────────configs──────│
    │                   │               │     │
    │                   │──send email───┼────▶│ (MailJet API)
    │                   │──send teams───┼────▶│ (Webhook POST)
    │                   │──create jira──┼────▶│ (Jira REST API)
    │                   │◀──────────────┼──jira_ticket_url────────────│
    │                   │──update alert_sent_at / resolution_sent_at▶│
    │                   │               │     │
    │◀──────200 OK──────│               │     │
```
