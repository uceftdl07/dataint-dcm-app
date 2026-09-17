# Databricks notebook source
# DBTITLE 1,Configuration
# Lecture SQS -> depot dans le volume d'ingestion DLT
# Mode BATCH intelligent :
#   - Lit tous les messages disponibles par batches de 10
#   - Deduplication par collection_run_id (1 fichier par run_id)
#   - Supprime le message SQS apres ecriture reussie
#   - Rapport par domaine avant depot
# Auth : Instance profile workload/dcm-databricks-jobs

SQS_QUEUE_URL         = dbutils.widgets.get("sqs_queue_url")
INGESTION_VOLUME_PATH = dbutils.widgets.get("ingestion_volume_path").rstrip("/")
BATCH_LIMIT           = int(dbutils.widgets.get("batch_limit"))   # 0 = vide toute la queue
AWS_REGION            = "eu-central-1"

VALID_DOMAINS = {"pipeline", "compute", "cost", "database", "security", "activity_run", "user", "standard_check", "workflow"}

print(f"Queue URL    : {SQS_QUEUE_URL}")
print(f"Volume       : {INGESTION_VOLUME_PATH}")
print(f"Batch limit  : {BATCH_LIMIT if BATCH_LIMIT > 0 else 'illimite (drain)'}")

# COMMAND ----------

# DBTITLE 1,Connexion SQS
# MAGIC %md
# MAGIC ## 1. Connexion SQS

# COMMAND ----------

# DBTITLE 1,SQS Client Init
import boto3, json
from collections import Counter, defaultdict

sqs = boto3.client("sqs", region_name=AWS_REGION)
print("SQS client OK")

# COMMAND ----------

# DBTITLE 1,Lecture intelligente
# MAGIC %md
# MAGIC ## 2. Lecture intelligente — boucle jusqu'a epuisement ou limite atteinte

# COMMAND ----------

# DBTITLE 1,Lecture SQS batch
all_messages = []   # tous les messages bruts collectes
seen_ids     = set()  # deduplication sur MessageId SQS
calls        = 0

print("Lecture SQS en cours...")

while True:
    # Respect de la limite si configuree
    if BATCH_LIMIT > 0 and len(all_messages) >= BATCH_LIMIT:
        print(f"  Limite de {BATCH_LIMIT} messages atteinte — arret.")
        break

    batch_size = 10
    if BATCH_LIMIT > 0:
        batch_size = min(10, BATCH_LIMIT - len(all_messages))

    response = sqs.receive_message(
        QueueUrl=SQS_QUEUE_URL,
        MaxNumberOfMessages=batch_size,
        WaitTimeSeconds=5,          # long polling — evite les appels a vide
        VisibilityTimeout=300,      # 5 min — protege pendant le traitement
        AttributeNames=["All"],
    )
    calls += 1
    batch = response.get("Messages", [])

    if not batch:
        print(f"  Queue vide apres {calls} appel(s).")
        break

    new_count = 0
    for msg in batch:
        if msg["MessageId"] not in seen_ids:
            seen_ids.add(msg["MessageId"])
            all_messages.append(msg)
            new_count += 1

    print(f"  Appel {calls:3d} : {len(batch):2d} recus / {new_count:2d} nouveaux / {len(all_messages):4d} total")

    # Si tous les messages du batch etaient deja vus -> queue epuisee
    if new_count == 0:
        print("  Plus de nouveaux messages — arret.")
        break

print(f"\nTotal messages uniques : {len(all_messages)}")

if not all_messages:
    print("Queue vide — rien a traiter.")
    dbutils.jobs.taskValues.set(key="messages_written", value=0)
    dbutils.jobs.taskValues.set(key="messages_errors",  value=0)
    dbutils.notebook.exit("empty_queue")

# COMMAND ----------

# DBTITLE 1,Parse et deduplication
# MAGIC %md
# MAGIC ## 3. Parse + deduplication par collection_run_id

# COMMAND ----------

# DBTITLE 1,Deduplication par run_id
# On garde uniquement le message le plus recent par collection_run_id
# (SQS peut re-livrer le meme message avec un nouveau MessageId -> dedupe metier)
best_by_run_id = {}   # collection_run_id -> row
invalid_rows   = []

for msg in all_messages:
    raw_body = msg.get("Body", "")
    try:
        payload           = json.loads(raw_body)
        collection_run_id = payload.get("collection_run_id")
        domain            = payload.get("domain", "").lower().strip()
        cloud_provider    = payload.get("cloud_provider", "").lower().strip()
        metric_count      = payload.get("metric_count", len(payload.get("metrics", [])))

        if not collection_run_id:
            raise ValueError("collection_run_id manquant")
        if domain not in VALID_DOMAINS:
            raise ValueError(f"domaine inconnu : '{domain}'")

        # Garder la derniere occurrence (collected_at le plus recent)
        collected_at = payload.get("collected_at", "")
        if collection_run_id not in best_by_run_id or collected_at > best_by_run_id[collection_run_id]["collected_at"]:
            best_by_run_id[collection_run_id] = {
                "sqs_message_id":    msg["MessageId"],
                "receipt_handle":    msg["ReceiptHandle"],
                "collection_run_id": collection_run_id,
                "domain":            domain,
                "cloud_provider":    cloud_provider,
                "metric_count":      metric_count,
                "collected_at":      collected_at,
                "payload":           payload,
            }

    except Exception as e:
        invalid_rows.append({
            "sqs_message_id": msg["MessageId"],
            "error":          str(e),
            "body_preview":   raw_body[:150],
        })

valid_rows = list(best_by_run_id.values())

print(f"Messages bruts     : {len(all_messages)}")
print(f"Run IDs uniques    : {len(valid_rows)}")
print(f"Invalides          : {len(invalid_rows)}")

# COMMAND ----------

# DBTITLE 1,Repartition par domaine
# MAGIC %md
# MAGIC ## 4. Repartition par domaine

# COMMAND ----------

# DBTITLE 1,Comptage par domaine
domain_counts = Counter(r["domain"] for r in valid_rows)
print("Repartition par domaine :")
for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
    total_metrics = sum(r["metric_count"] for r in valid_rows if r["domain"] == domain)
    print(f"  {domain:20s} : {count:4d} messages  /  {total_metrics:6d} metriques")

# Apercu DataFrame
display(spark.createDataFrame([
    {k: v for k, v in r.items() if k not in ("payload", "receipt_handle")}
    for r in valid_rows
]))

# COMMAND ----------

# DBTITLE 1,Depot dans le volume
# MAGIC %md
# MAGIC ## 5. Depot dans le volume

# COMMAND ----------

# DBTITLE 1,Ecriture fichiers volume
try:
    dbutils.fs.ls(INGESTION_VOLUME_PATH)
except Exception:
    dbutils.fs.mkdirs(INGESTION_VOLUME_PATH)
    print(f"Volume cree : {INGESTION_VOLUME_PATH}")

written        = []
skipped        = []   # deja present dans le volume
errors         = []

for r in valid_rows:
    filename  = f"{r['collection_run_id']}.json"
    dest_path = f"{INGESTION_VOLUME_PATH}/{filename}"

    # Idempotence : fichier deja present -> skip mais on delete SQS quand meme
    file_exists = False
    try:
        dbutils.fs.ls(dest_path)
        file_exists = True
    except Exception:
        pass

    if file_exists:
        skipped.append(filename)
        # Supprimer de SQS pour ne pas le re-livrer
        try:
            sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=r["receipt_handle"])
        except Exception:
            pass
        continue

    try:
        with open(dest_path, "w", encoding="utf-8") as f:
            json.dump(r["payload"], f, ensure_ascii=False, indent=2)

        # Supprimer de SQS seulement apres ecriture reussie
        sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=r["receipt_handle"])

        written.append({
            "file":    filename,
            "domain":  r["domain"],
            "cloud":   r["cloud_provider"],
            "metrics": r["metric_count"],
        })

    except Exception as e:
        # Ecriture echouee -> ne pas supprimer de SQS, sera re-livre au prochain run
        errors.append({"file": filename, "error": str(e)})
        print(f"  ERREUR : {filename} -> {e}")

print(f"\nEcrits  : {len(written)}")
print(f"Skippes : {len(skipped)}")
print(f"Erreurs : {len(errors)}")

# COMMAND ----------

# DBTITLE 1,Rapport final
# MAGIC %md
# MAGIC ## 6. Rapport final

# COMMAND ----------

# DBTITLE 1,Rapport et task values
print("=" * 60)
print("RAPPORT BATCH INTELLIGENT SQS -> VOLUME")
print("=" * 60)
print(f"  Appels SQS       : {calls}")
print(f"  Messages lus     : {len(all_messages)}")
print(f"  Run IDs uniques  : {len(valid_rows)}")
print(f"  Invalides        : {len(invalid_rows)}")
print(f"  Ecrits volume    : {len(written)}")
print(f"  Skippes (dedupe) : {len(skipped)}")
print(f"  Erreurs          : {len(errors)}")

if written:
    display(spark.createDataFrame(written))

if invalid_rows:
    print("\nMessages invalides :")
    display(spark.createDataFrame([{"sqs_message_id": r["sqs_message_id"], "error": r["error"]} for r in invalid_rows]))

if errors:
    print("\nErreurs ecriture :")
    display(spark.createDataFrame(errors))

dbutils.jobs.taskValues.set(key="messages_written", value=len(written))
dbutils.jobs.taskValues.set(key="messages_errors",  value=len(errors) + len(invalid_rows))

print("\nPret pour le pipeline DLT.")
print("=" * 60)
