# Contract: Registre de purge + CLI du job

Interface interne (pas d'API publique) exposée aux futurs mainteneurs du socle
`pipelines/system_tables` pour activer/désactiver la purge sur une table, et au
job Databricks Asset Bundle qui invoque le point d'entrée wheel task.

## 1. Registre déclaratif — `pipelines/system_tables/purge_specs.py`

```python
from pipelines.system_tables.specs import SPECS

PURGE_ENABLED_KEYS: tuple[str, ...] = (
    "uc_tables",
    "uc_table_tags",
    "compute_node_types",
    "billing_list_prices",
)

DEFAULT_ABSOLUTE_THRESHOLD = 1_000
DEFAULT_PERCENTAGE_THRESHOLD = 0.20

# THRESHOLDS: dict[str, tuple[int, float]] — override optionnel par table,
# retombe sur les défauts ci-dessus si absent.
```

**Contrat** :
- Toute clé de `PURGE_ENABLED_KEYS` **doit** exister dans `specs.SPECS`.
- Toute clé de `PURGE_ENABLED_KEYS` **doit** référencer un `IngestionSpec` avec
  `watermark_column is None` — violé ⇒ `ValueError` explicite au chargement du
  module (import-time), jamais une purge silencieuse sur une table incrémentale.
- Ajouter une table à la purge = ajouter sa clé à `PURGE_ENABLED_KEYS` (+
  éventuellement une entrée dans `THRESHOLDS`) — aucun autre changement de code
  requis, aucune modification du job `dcm_system_tables` existant.

## 2. Point d'entrée wheel task — `dcm-curated-purge`

Même convention que `dcm-system-tables` (`pipelines/system_tables/entrypoint.py`) :
fonction `main(spark, secrets, params: dict[str, str]) -> None`, testable sans
cluster réel.

**`named_parameters` acceptés** (job `job_dcm_curated_purge.yml`) :

| Paramètre | Obligatoire | Description |
|---|---|---|
| `table` | non | Clé de `PURGE_ENABLED_KEYS` à traiter (valeur `{{input}}` d'une itération `for_each`) ; vide ⇒ toutes les tables activées, séquentiellement (debug local) |
| `catalog` / `schema` | oui | Qualification des tables curated (vars bundle, jamais en dur) |
| `collection_run_id` | oui | `{{job.run_id}}` — identifiant du run de purge, distinct du run d'ingestion |
| `collected_at` | oui | `{{job.start_time.iso_datetime}}` |
| `azure_host` / `azure_http_path` / `azure_secret_scope` / `azure_tenant_id_key` / `azure_client_id_key` / `azure_secret_key` | oui si Azure activé | Identiques à `dcm-system-tables` — mêmes secrets réutilisés, jamais en dur (P8) |
| `dry_run` | non (défaut `"false"`) | `"true"` ⇒ calcule et trace en audit sans exécuter de `DELETE` |

**Sortie** : aucune valeur de retour applicative ; effet de bord = suppressions
conditionnelles en curated (sauf dry-run) + une ligne insérée dans
`curated_dbx_purge_audit_log` par (table, cloud) traité. Toute erreur de lecture
source ou d'écriture propage (P4 — fail loud), jamais un `except: pass`.

## 3. Fonction générique — `pipelines/common/purge.py`

```python
def purge_absent_rows(
    spark: SparkSession,
    spec: IngestionSpec,          # réutilisé tel quel, watermark_column doit être None
    *,
    cloud_provider: str,          # "azure" | "aws"
    collection_run_id: str,
    collected_at: str,
    threshold_absolute: int,
    threshold_percentage: float,
    dry_run: bool,
    azure_config: AzureConnectionConfig | None = None,
) -> PurgeAuditRecord:
    ...
```

**Contrat** :
- Relit systématiquement la source (jamais un résultat intermédiaire d'un run
  d'ingestion précédent — garantit l'indépendance des deux chemins d'exécution).
- Calcule `rows_to_delete` (anti-join sur `merge_keys`) **avant** toute tentative
  de suppression.
- N'exécute le `MERGE ... WHEN NOT MATCHED BY SOURCE ... THEN DELETE` que si
  `dry_run is False` **et** `rows_to_delete` respecte les deux seuils.
- Retourne toujours un `PurgeAuditRecord` (même si le garde-fou est déclenché ou
  en dry-run) — l'appelant (`purge_entrypoint.py`) l'insère dans la table
  d'audit avant de passer à la table/cloud suivant.
