import os
import json
from typing import Any
from fastapi import APIRouter, HTTPException
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from datetime import datetime

router = APIRouter()


def get_sqs_queue_url():
    return os.getenv("SQS_QUEUE_URL", "")

def get_raw_in_dir():
    return os.getenv("RAW_IN_DIR", "./raw/in")

def get_aws_region():
    return os.getenv("AWS_REGION", "eu-west-1")

def get_sqs_client():
    return boto3.client("sqs", region_name=get_aws_region())

def ensure_raw_in_dir():
    os.makedirs(get_raw_in_dir(), exist_ok=True)

def save_json_to_raw_in(payload: Any, suffix: str = ""):  # suffix pour différencier les fichiers
    ensure_raw_in_dir()
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%S%f")
    filename = f"payload_{now}{suffix}.json"
    path = os.path.join(get_raw_in_dir(), filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path

from fastapi import Request
from pydantic import BaseModel

# 1. API : push direct dans raw/in
@router.post("/push-to-raw-in", tags=["ingest"])
async def push_to_raw_in(payload: Any):
    """
    Reçoit un JSON et l'écrit directement dans raw/in (bypass SQS).
    """
    try:
        path = save_json_to_raw_in(payload)
        return {"status": "ok", "path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur écriture raw/in: {e}")

# 2. API : push dans SQS
@router.post("/push-to-sqs", tags=["ingest"])
async def push_to_sqs(payload: Any):
    """
    Reçoit un JSON et le publie dans SQS.
    """
    queue_url = get_sqs_queue_url()
    if not queue_url:
        raise HTTPException(status_code=500, detail="SQS_QUEUE_URL non configurée")
    try:
        get_sqs_client().send_message(QueueUrl=queue_url, MessageBody=json.dumps(payload))
        return {"status": "ok", "detail": "Payload publié dans SQS"}
    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=500, detail=f"Erreur SQS: {e}")

@router.post("/sqs-to-raw-in", tags=["ingest"])
def sqs_to_raw_in(max_messages: int = 10):
    """
    Lit les messages SQS et les écrit dans le dossier raw/in (Data Lake).
    """
    queue_url = get_sqs_queue_url()
    if not queue_url:
        raise HTTPException(status_code=500, detail="SQS_QUEUE_URL non configurée")
    try:
        messages = get_sqs_client().receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=2
        ).get("Messages", [])
        if not messages:
            return {"status": "ok", "written": 0, "detail": "Aucun message SQS"}
        written = 0
        for msg in messages:
            body = msg["Body"]
            try:
                payload = json.loads(body)
            except Exception:
                payload = body  # fallback si pas du JSON
            save_json_to_raw_in(payload, suffix=f"_{msg['MessageId']}")
            # Suppression du message SQS après traitement
            get_sqs_client().delete_message(QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"])
            written += 1
        return {"status": "ok", "written": written}
    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=500, detail=f"Erreur SQS: {e}")
