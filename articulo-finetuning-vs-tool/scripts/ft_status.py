"""Quick status check for the tool-aware fine-tuning job."""
import os
import sys
from openai import AzureOpenAI

endpoint = os.environ.get("FINETUNE_ENDPOINT", "https://aisvc-yrwwwokfuruzy.services.ai.azure.com")
token = os.environ["FINETUNE_TOKEN"]
job_id = sys.argv[1] if len(sys.argv) > 1 else "ftjob-b09608e20da04458b3924a387aa9a4ab"

c = AzureOpenAI(azure_endpoint=endpoint, azure_ad_token=token, api_version="2024-10-21")

try:
    j = c.fine_tuning.jobs.retrieve(job_id)
    print("status        :", j.status)
    print("fine_tuned    :", j.fine_tuned_model)
    print("trained_tokens:", j.trained_tokens)
    print("error         :", getattr(j, "error", None))
except Exception as e:  # noqa: BLE001
    print("retrieve failed:", e)
    print("--- listing recent jobs ---")
    for job in c.fine_tuning.jobs.list(limit=5).data:
        print(job.id, job.status, job.fine_tuned_model)
