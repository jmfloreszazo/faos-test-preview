"""Print failure details/events for a fine-tuning job."""
import os
import sys
from openai import AzureOpenAI

endpoint = os.environ.get("FINETUNE_ENDPOINT", "https://aisvc-yrwwwokfuruzy.services.ai.azure.com")
token = os.environ["FINETUNE_TOKEN"]
job_id = sys.argv[1] if len(sys.argv) > 1 else "ftjob-b09608e20da04458b3924a387aa9a4ab"

c = AzureOpenAI(azure_endpoint=endpoint, azure_ad_token=token, api_version="2024-10-21")

for job in c.fine_tuning.jobs.list(limit=10).data:
    if job.id == job_id:
        print("status:", job.status)
        print("error :", getattr(job, "error", None))
        print("hyper :", getattr(job, "hyperparameters", None))
        break

print("--- events ---")
try:
    for ev in c.fine_tuning.jobs.list_events(job_id, limit=20).data:
        print(f"[{ev.level}] {ev.message}")
except Exception as e:  # noqa: BLE001
    print("events failed:", e)
