# Anomaly System DCM - Design

Source Confluence: https://tdf.atlassian.net/wiki/spaces/TDF/pages/4816109960/Anomaly+System+DCM+Design

Ce document décrit le design détaillé du système d'anomalies DCM - flux de détection, wireframes des pages frontend, et décisions de design UI/UX.

## 1. Fichier de design (draw.io)

Le fichier draw.io complet est disponible dans le repository : `dataint-dcm-app/docs/08-anomaly-alerting-system/ANOMALY-ALERTING-SYSTEM-DESIGN.drawio`

Il contient 3 pages :

* **Page 1** : Architecture Système (4 couches : Frontend / Backend / Databricks / Unity Catalog)
* **Page 2** : Data Model (tables Delta + relations FK)
* **Page 3** : Alerting Flow (flux détaillé détection -> rapport -> notification fan-out)

## 2. Whiteboard de conception initiale

Le design a été initié lors d'une session de conception sur tableau blanc. Les éléments clés identifiés :

* **DCM (DBX <-> API <-> APP)** : flux central DCM inchangé, le système anomalie vient en surcouche
* **Total Anomaly Rules** dans Unity Catalog : Lineage, WF (Workflows), Compute - 3 catégories de rules company identifiées
* **MCP ?** : question ouverte sur l'utilisation du MCP Atlassian pour la création de tickets Jira (retenu : oui, via API REST Jira)
* **Alerting + Jira** : Teams Webhook + MCP Atlassian API -> Alerting Service centralisé dans le backend
* **Alerting Service** : 2 modes de déclenchement - instantané (check anomaly after insert) et on-demand (report generation)

## 3. Flux de détection - diagramme

```text
[Databricks Workflow] --cron 15min--> [Rule Loader]
                                           |
                              charge anomaly_rules actives
                                           |
                                    [Rule Evaluator]
                                           |
                            lit tables metriques (Delta UCat)
                            applique: metric_value [op] threshold
                                           |
                              +------------+------------+
                           Anomalie                  Pas d'anomalie
                           detectee                        |
                              |                incident actif existant ?
                    incident actif existant ?    +---------+---------+
                    +----------+----------+     Non                 Oui
                   Oui                   Non      |                   |
                    |                     |      Fin        UPDATE end_date = now
              UPDATE end_date       INSERT                   status = finalized
              recalcule duration    INTO anomaly_report      recalcule duration
                                    status = active                 |
                                         |                          |
                                  [Alert Trigger]          [Alert Trigger - resolution]
                                  POST /internal/          POST /internal/anomaly-reports/{id}/resolve
                                  anomaly-reports                    |
                                  JWT M2M Entra ID          notification de resolution (fan-out)
                                         |                          |
                                  [Alerting Service]        UPDATE resolution_sent_at
                                  charge alert_configs actifs
                                  fan-out: email | teams | jira
                                         |
                                  UPDATE alert_sent_at
```

## 4. Pages Frontend

### 4.1 Page Anomaly Rules

| Élément UI | Description |
| --- | --- |
| Tableau des règles | Liste paginée - colonnes : nom, domaine, sévérité, type (company/custom), mode (scheduled/on-demand), statut (actif/inactif) |
| Badge rule_type | company (read-only) / custom (éditable) |
| Bouton "Créer une règle" | Ouvre le formulaire de création de règle custom |
| Toggle activer/désactiver | Switch on/off par règle (custom uniquement) |
| Bouton "Configurer alerting" | Ouvre l'Alert Config Dialog pour associer un canal de notification |

### 4.2 Page Anomaly Reports

| Élément UI | Description |
| --- | --- |
| Tableau des rapports | Liste paginée - colonnes : règle, LZ, sévérité, start_date, end_date, durée, statut |
| Badge statut | active / finalized |
| Filtres | Par LZ, par statut, par règle, par période |
| Détail rapport | Vue détaillée : `metric_value`, `threshold_value`, `logs` JSON, lien Jira |
| Lien Jira | URL vers ticket DCINT créé automatiquement (si alerting Jira activé) |

### 4.3 Alerting - Dialog inline + page dédiée

**Alert Config Dialog (inline)** - accessible pendant la création/édition d'une règle, sans quitter le formulaire :

| Élément UI | Description |
| --- | --- |
| Sélecteur de règle | Pré-rempli avec la règle en cours de création |
| Canal Email | Toggle + sélection d'un channel de type `email` |
| Canal Teams | Toggle + sélection d'un channel de type `teams` |
| Canal Jira | Toggle + sélection d'un channel de type `jira` |
| Fréquence de notification | Select : `daily` \| `weekly` \| `monthly` |

**Page dédiée Alerting** - accessible via le raccourci "Configurer alerting" (§4.1) et depuis le menu :

> **Note de scope** : cette page dédiée est différée et n'entre pas dans le périmètre P2 actuel. Pour cette phase, la gestion de l'alerting passe par l'Alert Config Dialog inline.

| Élément UI | Description |
| --- | --- |
| Tableau des alert_configs | Toutes les associations règle / canaux - tri par règle ou par canal |
| Actions par ligne | Éditer, activer/désactiver, tester, supprimer |
| Édition fréquence de notification | Modification du champ `notify_frequency` par config |

### 4.4 Notification Settings

| Élément UI | Description |
| --- | --- |
| Liste channels | Tableau : nom, type (email/teams/jira), statut actif/inactif |
| Créer channel Teams | Formulaire : nom + webhook URL (stocké dans AWS Secrets Manager) |
| Créer channel Email | Formulaire : nom + liste destinataires |
| Créer channel Jira | Formulaire : nom + projet Jira + issue type |

## 5. Formule de création d'une règle custom

| Champ formulaire | Type | Valeurs possibles |
| --- | --- | --- |
| Nom | text | Libre |
| Description | textarea | Libre |
| Domaine | select | pipeline \| compute \| cost \| standard_check \| storage \| database |
| Indicateur (metric_field) | select dynamique | Chargé selon le domaine sélectionné depuis les métadonnées DCM |
| Opérateur | select | > \| < \| >= \| <= \| = \| ≠ |
| Seuil | number | Décimal |
| Sévérité | select | low \| medium \| high \| critical |
| Mode déclenchement | radio | scheduled (automatique) \| on_demand (manuel) |
| Portée LZ | multi-select | Toutes les LZ de l'utilisateur (null = toutes) |

## 6. Questions ouvertes

* Spike à réaliser : identification des **company rules P1** (métriques cibles, opérateurs, seuils par domaine)
* Déterminer si le chargement des `metric_field` disponibles dans le formulaire custom est statique (liste en dur par domaine) ou dynamique (introspection Unity Catalog)
* Définir la politique de **déduplication** des incidents actifs : UNIQUE (rule_id, lz_id) ou tolérance multi-incidents simultanés par règle ?
