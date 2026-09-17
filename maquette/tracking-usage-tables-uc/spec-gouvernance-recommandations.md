# Spec — Gouvernance & Recommandations

> Statut : DRAFT — issu du spike challengé. Fusion de l'ancienne page "Gouvernance & FinOps" (partie Gouvernance uniquement, le FinOps a été déplacé dans Usage des tables UC) et de l'ancienne page "Recommandations".
> Page accessible depuis le menu **Databricks** (plus de section "Tracking d'usage" séparée). La fraîcheur (dernière écriture) est désormais affichée sur la page **Usage des tables UC** (onglet Par table) et n'apparaît plus ici, pour éviter la duplication d'un même indicateur entre deux pages avec des angles différents (état vs action).
> Deux onglets : **Gouvernance** (registre + cycle de vie) / **Recommandations** (socle réactif).
> Persona cible : GOV, OWN, DE, FIN (selon `personas` de la recommandation).

## ⚠️ Vérification du périmètre réel (mapping feature 019)

Périmètre confronté au code livré dans `packages/dcm-databricks-pipeline/pipelines/gold_dbx_usage/`.

- **✅ `gold_dbx_usage_recommendations` est implémentée et déployée** (`recommendations.py`, tâche `gold_usage_recommendations` du job `dcm_gold_dbx_usage`). L'onglet Recommandations a donc une source complète : `recommendation_id`, `cloud_provider`, `object_type`, `object_id`, `object_name`, `category`, `mode`, `title`, `detail`, `recommended_action`, `estimated_savings_usd`, `severity`, `personas`, `status`, `first_seen_date`, `last_seen_date`.
- **⚠️ `object_type` vaut `DATA_PRODUCT` ou `CONSUMER`, pas `TABLE`.** Tout mapping ou filtre écrit contre `TABLE` ne renverra rien.
- **⚠️ `status` n'a que deux valeurs : `OPEN` et `RESOLVED`.** Il n'existe **aucun mécanisme d'acquittement** dans le pipeline : `ACK` n'est ni produit ni préservé, et un `UPDATE` posé par l'application serait écrasé au run suivant (le `MERGE` réécrit `status` depuis les règles). FR8 suppose donc soit une évolution du pipeline, soit une table d'acquittement portée par l'application, jointe à la lecture.
- **⚠️ Deux vocabulaires de sévérité sur la même page** : `recommendations.severity` vaut `HIGH`/`MEDIUM`/`LOW` (majuscules) alors que `table_governance.severity` vaut `high`/`medium`/`low` (minuscules). Les deux onglets ne peuvent pas partager le même composant de badge sans normalisation explicite.
- **⚠️ `estimated_savings_usd` n'est renseigné que pour la règle LIFECYCLE "inutilisé"** (dernier coût journalier connu de la table) ; `NULL` pour FRESHNESS, GOVERNANCE, RELIABILITY et FINOPS. Un KPI "gain estimé total" ne couvre donc qu'une catégorie sur cinq — à libeller comme tel.
- **Cycle de vie réel** : une ligne passée `RESOLVED` est **figée** — plus jamais réécrite, aucun `DELETE`. Si l'anomalie se redéclenche, une NOUVELLE ligne est insérée avec un nouveau `recommendation_id` et un nouveau `first_seen_date`, à côté de l'ancienne. L'onglet doit filtrer sur `status = 'OPEN'` et non dédoublonner par `(object_id, category)`, sinon l'historique résolu remonte.
- **Règles réellement codées** (5 catégories, `mode` toujours `REACTIVE`) : LIFECYCLE MEDIUM (`is_unused AND NOT is_critical`), LIFECYCLE HIGH (`is_critical AND is_unused`, contradiction lineage), FRESHNESS HIGH (`is_stale_but_consumed`), GOVERNANCE LOW (`is_orphan`), GOVERNANCE MEDIUM (`is_data_product AND classification IS NULL`), RELIABILITY HIGH (`failure_rate_pct > 5`), FINOPS MEDIUM (`consumer_daily.estimated_cost_usd > 1`, seule règle au grain `CONSUMER`). **Au plus une ligne GOVERNANCE par objet** (ordre de priorité orphelin > classification).
- **⚠️ Les règles RELIABILITY et FINOPS n'évaluent que le DERNIER JOUR connu** de `query_performance_daily`/`consumer_daily`, pas la période sélectionnée : le filtre de période ne peut pas les recalculer.
- **⚠️ Un exemple `object_type = CONSUMER` existe déjà en données réelles** (règle FINOPS) : FR9 n'a plus besoin de données de démo fabriquées.
- **✅ Confirmé (non un gap)** : cette page ne nécessite pas non plus de grain `workspace_id`. Les filtres Workspace et LZ ajoutés dans une itération précédente du bandeau ont été retirés — le module se pilote entièrement via période + catalogue/schéma/table(s), cohérent avec le grain réel de `gold_dbx_usage_table_catalog`/`gold_dbx_usage_table_governance` (`cloud_provider, catalog, schema, table_name`).
- **⚠️ Le filtre catalogue/schéma/table(s) n'est pas applicable directement à `recommendations`** : la table ne porte ni `catalog` ni `schema`, seulement `object_id`. Pour un `object_type = DATA_PRODUCT`, `object_id` = `table_full_name` (filtrable par préfixe ou jointure sur `table_catalog`) ; pour un `object_type = CONSUMER`, `object_id` = `consumer_id`, sans rattachement à un catalogue — ces lignes sortent du filtre par construction. Décision UI à prendre : les masquer, ou les afficher hors périmètre filtré.
- L'onglet **Gouvernance** repose sur `gold_dbx_usage_table_governance` — son champ `recommended_action` est un **mot-clé court** (`archiver` / `documenter` / `surveiller` / NULL), pas la phrase riche utilisée dans le mockup ("Proposer dépréciation / suppression…"). La colonne "Statut" du registre doit dériver son badge de ce mot-clé + `severity`, pas d'un texte généré. Les phrases riches, elles, existent dans `recommendations.title`/`detail`/`recommended_action`.
- Les seuils de gouvernance sont **déjà codés en dur** dans le pipeline, pas paramétrables actuellement : `is_unused` = jamais lue OU inactive >90 jours ; `is_critical` = `downstream_fanout >= 5` ; `is_stale_but_consumed` = écriture >24h ET lecture <7 jours. Ça répond à FR6 (le seuil 90j est confirmé, mais **non paramétrable** — nuance à ajouter).
- `last_operation` n'a que **3 valeurs possibles** dans l'implémentation actuelle : `createTable`, `deleteTable`, `updateTables`. Les valeurs `MERGE`/`WRITE`/`OPTIMIZE`/`VACUUM` utilisées dans le mockup ne sont **pas** couvertes — `system.access.audit` ne semble pas capturer ces opérations d'écriture au sens large pour l'instant, seulement la création/suppression/mise à jour de métadonnées.
- `owner` en registre reste le tag UC `owner` (pivot de `curated_dbx_uc_table_tags`), pas `table_owner` natif comme supposé en FR7 — à corriger : la table `table_catalog` documente bien un champ `owner` alimenté par le tag, cohérent avec "pas de dépendance à un tag" **infirmé** : le champ dépend bel et bien du tag `owner`, qui n'est pas renseigné aujourd'hui (tables non taguées, cf. discussion antérieure) → `owner` sera donc `NULL` pour la quasi-totalité des tables tant que le tagging n'est pas fait.
- Colonnes réelles : `catalog`/`schema` (pas `table_catalog`/`table_schema`), `estimated_cost_usd` (pas `cost_usd`).
- Le périmètre courant inclut toutes les tables visibles dans Unity Catalog, y compris les tables techniques, curated, staging et internes DCM : aucun filtre `is_data_product` n'est appliqué aujourd'hui. L'attribut `is_data_product` reste conservé dans `table_catalog` pour permettre plus tard de distinguer une table data product d'une simple table, via un filtre ou une segmentation dédiée.

## User Scenarios

- En tant que Gouvernance, je veux voir l'inventaire complet des tables trackées avec leur dernier état (owner, dernière opération, fraîcheur) pour identifier les tables à risque.
- En tant que propriétaire de tables, je veux, depuis la même page que le registre, accéder directement aux recommandations actionnables liées au cycle de vie de mes tables, sans changer de page.
- En tant que Gouvernance, je veux filtrer les recommandations par catégorie pour traiter un type de problème à la fois.

## Functional Requirements

- FR1 — Deux onglets : **Gouvernance** (défaut) et **Recommandations**, filtres communs catalogue/schéma/table(s) partagés entre les deux. Les deux onglets ont une source gold livrée ; le filtre ne s'applique pas de la même façon aux deux (cf. Vérification du périmètre : `recommendations` ne porte ni `catalog` ni `schema`).
- FR2 — L'onglet Gouvernance repose sur le **registre** (état courant, 1 ligne = 1 table) — contrairement à Usage qui est au grain jour × table × consommateur.
- FR3 — Le statut d'une table (OK / Périmée mais lue / Inutilisée / Critique) est dérivé de `recommended_action` (mot-clé) + `severity` en base `governance`, pas recalculé côté frontend. Le badge de statut doit mapper les valeurs réelles (`archiver`/`documenter`/`surveiller`/NULL), pas un texte libre.
- FR4 — L'onglet Recommandations liste les lignes `status = 'OPEN'` de `gold_dbx_usage_recommendations`, triées par `severity` décroissante (`HIGH` > `MEDIUM` > `LOW`, majuscules côté table). Ne pas dédoublonner par `(object_id, category)` : les lignes `RESOLVED` restent en base et une réouverture crée une seconde ligne.
- FR5 — Le filtre catalogue/schéma/table(s) s'applique aux recommandations via `object_id` (= `table_full_name`) pour `object_type = 'DATA_PRODUCT'`, par jointure sur `gold_dbx_usage_table_catalog`. Les lignes `object_type = 'CONSUMER'` n'ont aucun rattachement catalogue — **[NEEDS DECISION PO]** : les masquer quand un filtre table est actif, ou les afficher dans une section "hors périmètre table" ?
- FR6 — ✅ **Partiellement résolu** : le seuil "tables inutilisées" est confirmé à 90 jours dans l'implémentation actuelle — mais il est **codé en dur** (`specs.py::UNUSED_AFTER_DAYS`), pas paramétrable par LZ/catalogue. Idem pour les seuils du rule engine (`USAGE_FAILURE_RATE_PCT_THRESHOLD = 5.0`, `USAGE_HIGH_COST_USD_THRESHOLD = 1.0`). Décision PO restante : faut-il investir dans la paramétrisation, ou les seuils fixes conviennent-ils pour le MVP ?
- FR7 — ⚠️ **Correction** : `owner` provient bien du **tag UC `owner`** (pas de `table_owner` natif comme supposé) — cela signifie qu'`owner` sera `NULL` pour la quasi-totalité des tables tant que le tagging n'est pas en place (cf. décision antérieure de reporter le tagging en V2). Le registre doit donc afficher un état "Non renseigné" explicite plutôt qu'un champ vide, et ne pas laisser croire à une donnée fiable. Conséquence directe : `is_orphan` (aucun des 3 tags) est vrai pour presque tout le parc, donc la règle GOVERNANCE LOW de l'onglet Recommandations va produire un volume massif de lignes — prévoir un tri/pagination, ou masquer cette catégorie par défaut.
- FR8 — [NEEDS DECISION PO] Une action "Acquitter" ne peut PAS écrire `status = 'ACK'` sur la table gold : le pipeline ne connaît que `OPEN`/`RESOLVED` et réécrit `status` à chaque run. L'acquittement suppose donc soit une évolution du pipeline côté data engineering, soit une table d'acquittement portée par l'application et jointe à la lecture. Décision : investir, ou s'en passer pour le MVP ?
- FR9 — ✅ **Résolu** : la règle FINOPS produit des lignes `object_type = 'CONSUMER'` en données réelles (consommateur dont le coût journalier dépasse 1 USD). Aucune donnée de démo à fabriquer.

## Key Entities & Data Sources

### Onglet Gouvernance — KPI

| KPI | Table gold source | Colonne(s) | Transformation |
|---|---|---|---|
| Tables inutilisées | `gold_dbx_usage_table_governance` | `is_unused` | `COUNT(is_unused=true)` |
| Périmées mais lues | `gold_dbx_usage_table_governance` | `is_stale_but_consumed` | `COUNT(is_stale_but_consumed=true)` |
| Tables critiques | `gold_dbx_usage_table_governance` | `is_critical` | `COUNT(is_critical=true)` |

### Onglet Gouvernance — Registre des tables

| Colonne UI | Table gold source | Colonne(s) | Transformation |
|---|---|---|---|
| Table (+ type) | `gold_dbx_usage_table_catalog` | `table_full_name` (dérivé), `table_type` | direct |
| Owner | `gold_dbx_usage_table_catalog` | `owner` | tag UC `owner` — ⚠️ sera `NULL` pour la majorité des tables tant que le tagging n'est pas en place (cf. FR7) ; afficher "Non renseigné" plutôt qu'un vide |
| Dernière opération | `gold_dbx_usage_table_catalog` | `last_operation`, `last_operation_at`, `last_operation_by` | ⚠️ vocabulaire réel limité à `createTable` / `deleteTable` / `updateTables` — ne pas afficher MERGE/WRITE/OPTIMIZE comme dans le mockup actuel. ⚠️ `last_operation_at` **n'est PAS un alias de `last_write_at`** : deux colonnes de sources différentes, `last_operation_at` venant de l'audit UC (appels d'API, sans compteur de lignes) et `last_write_at` du lineage qualifié par `written_rows > 0`. Une valeur dans `last_operation_at` ne prouve aucune écriture |
| Fan-out aval | `gold_dbx_usage_table_governance` | `downstream_fanout` | dernier fan-out connu de `gold_dbx_usage_table_popularity_daily`, 0 par défaut |
| Statut | `gold_dbx_usage_table_governance` | `recommended_action` (mot-clé), `severity` | badge dérivé du mot-clé réel : `archiver`→Inutilisée, `documenter`→Orpheline, `surveiller`→Périmée mais consommée, NULL→OK |

### Onglet Recommandations

| Élément UI | Table gold source | Colonne(s) | Transformation |
|---|---|---|---|
| KPI High / Medium / Total ouvertes | `gold_dbx_usage_recommendations` | `severity`, `status` | `COUNT` par `severity` sur `status = 'OPEN'` — valeurs en **majuscules** (`HIGH`/`MEDIUM`/`LOW`) |
| Filtre catégorie (pills) | `gold_dbx_usage_recommendations` | `category` | `LIFECYCLE`, `FRESHNESS`, `GOVERNANCE`, `RELIABILITY`, `FINOPS` — liste fermée, à figer côté UI plutôt qu'un `SELECT DISTINCT` |
| Titre / détail / action recommandée | `gold_dbx_usage_recommendations` | `title`, `detail`, `recommended_action` | direct — `detail` porte déjà les valeurs mesurées, ne pas les recalculer côté UI |
| Gain estimé | `gold_dbx_usage_recommendations` | `estimated_savings_usd` | direct — ⚠️ renseigné uniquement pour LIFECYCLE "inutilisé", `NULL` pour les 4 autres catégories. Un total ne couvre donc qu'une catégorie : le libeller "gain estimé sur les tables inutilisées" |
| Table / consommateur concerné | `gold_dbx_usage_recommendations` | `object_type` (**`DATA_PRODUCT`** ou `CONSUMER`), `object_id`, `object_name` | `object_id` = `table_full_name` (DATA_PRODUCT) ou `consumer_id` (CONSUMER) — le lien de renvoi diffère selon le cas |
| Date de détection / personas | `gold_dbx_usage_recommendations` | `first_seen_date`, `last_seen_date`, `personas` | `personas` est un `ARRAY<STRING>` ⊂ {`OWN`, `FIN`, `GOV`, `DE`, `AN`} |
| Ancienneté de l'anomalie | dérivé | `first_seen_date` | `datediff(current_date(), first_seen_date)` — stable au fil des runs, contrairement à `_generated_at` |

### Filtres communs (aux deux onglets)

| Élément | Table gold source | Colonne(s) |
|---|---|---|
| Catalogue / Schéma / Tables (multi-select) | `gold_dbx_usage_table_catalog` | `catalog`, `schema`, `table_full_name` (dérivé) |
| Jointure Recommandations → filtre table | `gold_dbx_usage_recommendations` × `gold_dbx_usage_table_catalog` | `object_id = table_full_name` sur `object_type = 'DATA_PRODUCT'` uniquement ; les lignes `CONSUMER` n'ont pas de rattachement catalogue (cf. FR5) |

### Convention de période et d'état courant

Le filtre global **Date de début / Date de fin** est présent en haut de la page et est transmis à l'API.

- Les KPI de gouvernance issus de `gold_dbx_usage_table_governance` décrivent un **snapshot d'état courant** : cette table n'a pas de `period_start`. Le filtre de période ne doit donc pas simuler un historique de gouvernance qui n'existe pas.
- `is_unused`, `is_stale_but_consumed`, `is_critical`, `recommended_action` et `severity` sont évalués selon le dernier snapshot gold disponible.
- `gold_dbx_usage_recommendations` est aussi un **snapshot d'état** (pas de `period_start`, recalcul complet à chaque run) : les recommandations ne peuvent être filtrées par période que via leur cycle de vie (`first_seen_date` / `last_seen_date`). Les règles RELIABILITY et FINOPS n'évaluent que le dernier jour connu de leurs sources quotidiennes : le filtre de période ne les recalcule pas.
- Les métriques dérivées de tables daily utilisées pour contextualiser la gouvernance doivent respecter les mêmes règles d'agrégation que la page Usage : sommes pour les métriques additives, ratios pondérés pour les taux et aucun `AVG` naïf de P95.

La note d'information placée au-dessus des filtres doit expliquer ce comportement :

> La période filtre les données d'usage et le cycle de vie des recommandations. Le registre et les statuts de gouvernance affichent le dernier état connu; ils ne représentent pas un historique jour par jour.

## API Endpoints (proposition)

- `GET /api/usage/governance/kpis?catalog=&schema=&tables[]=` → KPI onglet Gouvernance
- `GET /api/usage/governance/registry?catalog=&schema=&tables[]=&sort=` → registre + statut (FR2, FR3)
- `GET /api/usage/recommendations?catalog=&schema=&tables[]=&category=&severity=&object_type=` → onglet Recommandations (FR4, FR5), `status = 'OPEN'` par défaut
- ~~`PATCH /api/usage/recommendations/{id}/status`~~ → **hors périmètre** : `status` est recalculé par le pipeline à chaque run, une écriture applicative serait écrasée (cf. FR8)

## Checklist

- [x] Seuil "inutilisée" confirmé à 90 jours (FR6) — ⚠️ mais codé en dur, décision PO restante sur la paramétrisation
- [ ] `owner` affiché avec état "Non renseigné" explicite plutôt qu'un champ vide (dépend du tag `owner`, pas de `table_owner` natif — FR7 corrigée)
- [ ] Vocabulaire "Dernière opération" corrigé pour ne montrer que `createTable`/`deleteTable`/`updateTables`
- [ ] `last_operation_at` traité comme distinct de `last_write_at` (pas un alias) : ne pas présenter une opération d'audit comme une écriture
- [ ] Statut du registre dérivé du mot-clé réel `recommended_action` (archiver/documenter/surveiller), pas d'un texte libre
- [ ] `object_type = 'DATA_PRODUCT'` (pas `TABLE`) dans tous les filtres et mappings de l'onglet Recommandations
- [ ] Sévérité normalisée entre les deux onglets (`HIGH`/`MEDIUM`/`LOW` dans `recommendations`, `high`/`medium`/`low` dans `table_governance`)
- [ ] KPI "gain estimé" libellé comme ne couvrant que LIFECYCLE inutilisé (`estimated_savings_usd` NULL ailleurs)
- [ ] Liste des recommandations filtrée sur `status = 'OPEN'` sans dédoublonnage par `(object_id, category)`
- [ ] Volume attendu de la catégorie GOVERNANCE anticipé (tagging absent ⇒ `is_orphan` quasi universel) : tri, pagination, ou catégorie repliée par défaut
- [ ] Décision PO FR8 (acquittement) et FR5 (lignes `CONSUMER` face au filtre table)
- [ ] Filtres communs strictement identiques (composant, référentiel) à la page Usage des tables UC
- [ ] Toutes les occurrences `cost_usd`/`table_catalog`/`table_schema` corrigées en `estimated_cost_usd`/`catalog`/`schema`
