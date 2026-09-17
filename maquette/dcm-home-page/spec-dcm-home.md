# DCM — Home Page — Spec

**Module** : Home (racine DCM)
**Fichier maquette associé** : `dcm-home.html`
**Statut** : Draft — première itération PO

---

## User Scenarios

### DataOps
En tant que DataOps, en arrivant sur DCM je veux voir immédiatement s'il y a des jobs en échec sur les dernières 24h et des alertes actives, pour savoir si je dois intervenir avant même d'ouvrir un module spécifique.

### Data Engineer
En tant que Data Engineer, je veux voir un aperçu de la santé de mes clusters/warehouses et du volume de tables suivies sur mon périmètre, pour identifier rapidement si je dois aller creuser dans Compute ou Tracking d'usage.

### Data Product Owner
En tant que Data Product Owner, je veux voir le coût global cumulé depuis le début d'année sur les workspaces que je pilote, avec une tendance visuelle, pour suivre la dérive budgétaire sans avoir à ouvrir le module FinOps.

### SysOps
En tant que SysOps, je veux voir en un coup d'œil le nombre d'alertes actives et leur sévérité, ainsi que les modules à venir (Cognite, Azure Data Factory, anomalies ouvertes), pour anticiper le périmètre de supervision futur.

---

## Functional Requirements

### FR1 — Bandeau de bienvenue
- Affiche un message de salutation nominatif à l'utilisateur connecté.
- Affiche l'horodatage de dernière synchronisation des données.
- Affiche un rappel du nombre total d'alertes actives (raccourci vers la section Anomalies de la page).

### FR2 — Cartes modules Databricks (une carte par sous-module)
- **Jobs & Pipelines** : KPI = nombre de jobs en échec sur les dernières 24h glissantes, tous workspaces Databricks confondus. Lien vers le module Jobs & Pipelines.
- **Compute** : KPI = nombre de clusters + SQL Warehouses actifs, tous workspaces confondus. Lien vers le module Compute.
- **Tracking d'usage** : pas de chiffre affiché — un chiffre global n'a pas de sens tant que l'utilisateur n'a pas sélectionné les tables qui le concernent dans le module. La carte affiche à la place un texte de résumé de ce que couvre le module (requêtes, consommateurs, gouvernance, coûts) et invite à aller sélectionner ses tables. Lien vers le module Tracking d'usage.
- Chaque carte affiche en pied de carte la ou les gold tables sources (footnote de traçabilité), conformément à la convention DCM.
- Chaque carte est cliquable dans son intégralité et redirige vers le module correspondant.

### FR3 — Carte FinOps mise en avant (coût & consommation)
- KPI principal = coût global cumulé depuis le 1er janvier de l'année en cours, tous workspaces Databricks confondus.
- Affiche une variation (delta) par rapport à une période de référence. `[NEEDS DECISION PO]` définir la période de référence exacte (N-1 même durée ? mois précédent ?).
- Affiche une courbe d'évolution mensuelle de la consommation sur l'année en cours (graphique en aire/ligne).
- Footnote de traçabilité gold tables (billing_usage, billing_list_prices).
- Lien vers le module FinOps complet.
- `[NEEDS DECISION PO]` : le filtrage par workspace(s) reste disponible dans le module FinOps lui-même ; la home affiche volontairement un chiffre non filtré, à confirmer que c'est le comportement souhaité pour tous les KPIs de la page.

### FR4 — Carte Anomalies & Alertes
- KPI = nombre d'alertes actives, tous modules Databricks confondus.
- Répartition visuelle par sévérité (badges Critical / High / Medium / Low, uniquement les sévérités présentes).
- Lien vers Anomaly Reports.

### FR5 — Section Roadmap (modules à venir)
- Cartes visuellement distinctes (style atténué/pointillé) des modules actifs, non cliquables, avec tag "Bientôt disponible".
- Contenu actuel : Cognite, Azure Data Factory, Nombre d'anomalies ouvertes (compteur consolidé, tous modules).
- Cette section est purement indicative de roadmap ; aucune donnée réelle n'est affichée derrière ces cartes.

### FR6 — Navigation
- La sidebar reflète les modules disponibles et à venir (items "Soon" désactivés, non cliquables) pour cohérence avec la section Roadmap de la home.

---

## Key Entities

| Entité | Description |
|---|---|
| `ModuleKpiSummary` | Résumé KPI d'un sous-module (Jobs & Pipelines, Compute) : valeur, libellé, lien, source(s). Pour Tracking d'usage, pas de valeur chiffrée : un texte de résumé statique du module est affiché à la place (pas d'appel API dédié). |
| `CostSummary` | Coût cumulé YTD + série temporelle mensuelle pour la courbe d'évolution, tous workspaces confondus. |
| `AlertSummary` | Compteur d'alertes actives + répartition par sévérité. |
| `RoadmapItem` | Élément de roadmap affiché en carte "Bientôt disponible" (nom, description, statut). |

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/home/kpis` | Retourne les KPIs Jobs & Pipelines et Compute, tous workspaces confondus. Tracking d'usage n'a pas de KPI chiffré sur la home (texte statique, pas d'appel API). |
| `GET /api/home/cost-summary?from=2026-01-01&to=today` | Retourne le coût cumulé et la série mensuelle pour la courbe d'évolution. |
| `GET /api/home/alerts/active` | Retourne le nombre d'alertes actives et leur répartition par sévérité. |

---

## Checklist

- [ ] Confirmer la table source des runs de jobs (`system.lakeflow.job_run_timeline` ou équivalent) — non présente dans `reference/gold-tables-confirmed.md`.
- [ ] Confirmer la période de référence du delta de coût FinOps (FR3).
- [ ] Confirmer que tous les KPIs de la home restent volontairement non filtrés (pas de sélecteur de périmètre sur cette page — filtrage disponible dans chaque module).
- [ ] Valider la date/portée roadmap de "Nombre d'anomalies ouvertes" avant de la faire passer de carte roadmap à carte active.
- [ ] Revue design avec PO sur la hiérarchie visuelle carte FinOps vs cartes modules (carte pleine largeur vs grille uniforme).
