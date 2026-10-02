import json
from datetime import datetime
from google.cloud import storage

BUCKET_NAME = "mcp_tracking_private"
GCS_PROJECT = "dm-agents-private"

def save_json_to_gcs(data, prefix):

    client = storage.Client(project = GCS_PROJECT)
    bucket = client.bucket(BUCKET_NAME)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    blob_name = f"{prefix}/data_{timestamp}.json"

    blob = bucket.blob(blob_name)

    json_data = json.dumps(data, ensure_ascii=False)

    blob.upload_from_string(
        json_data,
        content_type="application/json"
    )

    return f"gs://{BUCKET_NAME}/{blob_name}"