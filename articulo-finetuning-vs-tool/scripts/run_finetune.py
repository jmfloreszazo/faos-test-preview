"""Validate the SFT dataset and (optionally) launch an Azure OpenAI fine-tuning job.

Two modes
---------
* Default (validate):  pure stdlib, no network. Checks the JSONL meets Azure
  OpenAI supervised fine-tuning requirements and prints token estimates.
      python scripts/run_finetune.py

* Launch (--launch):   uploads the train/validation files and creates the
  fine-tuning job on the Foundry AI Services account. Requires the ``openai``
  SDK and an ``az login`` session. This INCURS COST, so it is opt-in.
      python scripts/run_finetune.py --launch

Config is read from the azd environment (AZURE_AI_PROJECT_ENDPOINT, account)
unless overridden by flags / environment variables.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "src", "support-agent", "data")
TRAIN = os.path.join(DATA_DIR, "support-sft.train.jsonl")
VAL = os.path.join(DATA_DIR, "support-sft.val.jsonl")

VALID_ROLES = {"system", "user", "assistant", "tool"}
MIN_EXAMPLES = 10  # Azure OpenAI minimum for fine-tuning.


def validate_file(path: str) -> tuple[int, int]:
    """Validate one JSONL file. Returns (n_examples, est_total_tokens)."""
    if not os.path.exists(path):
        raise SystemExit(f"Missing dataset file: {path}")
    n = 0
    chars = 0
    errors: list[str] = []
    with open(path, "r", encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"line {i}: invalid JSON ({e})")
                continue
            msgs = obj.get("messages")
            if not isinstance(msgs, list) or not msgs:
                errors.append(f"line {i}: missing/empty 'messages'")
                continue
            roles = [m.get("role") for m in msgs]
            if any(r not in VALID_ROLES for r in roles):
                errors.append(f"line {i}: invalid role in {roles}")
            if roles[-1] != "assistant":
                errors.append(f"line {i}: last message must be 'assistant'")
            if not any(r == "user" for r in roles):
                errors.append(f"line {i}: no 'user' message")
            for m in msgs:
                content = m.get("content")
                # An assistant turn may carry tool_calls instead of content.
                has_tool_calls = bool(m.get("tool_calls"))
                if not (content or "").strip() and not has_tool_calls:
                    errors.append(f"line {i}: empty content for role '{m.get('role')}'")
                chars += len(content or "")
            n += 1
    if errors:
        print(f"  ✗ {os.path.basename(path)}: {len(errors)} problem(s):")
        for e in errors[:10]:
            print(f"      - {e}")
        if len(errors) > 10:
            print(f"      ... and {len(errors) - 10} more")
        raise SystemExit(1)
    est_tokens = chars // 4  # rough heuristic (~4 chars/token)
    print(f"  ✓ {os.path.basename(path)}: {n} examples, ~{est_tokens:,} tokens")
    return n, est_tokens


def do_validate() -> None:
    print("Validating SFT dataset (Azure OpenAI chat format):")
    n_train, t_train = validate_file(TRAIN)
    n_val, t_val = (0, 0)
    if os.path.exists(VAL):
        n_val, t_val = validate_file(VAL)
    print()
    if n_train < MIN_EXAMPLES:
        raise SystemExit(f"Training set has {n_train} examples; Azure requires >= {MIN_EXAMPLES}.")
    print(f"Total: {n_train + n_val} examples, ~{t_train + t_val:,} tokens.")
    print("Result: VALID and ready for fine-tuning.")
    print("\nTo launch the fine-tuning job (incurs cost):")
    print("  python scripts/run_finetune.py --launch")


def do_launch(model: str, api_version: str, suffix: str) -> None:
    try:
        from openai import AzureOpenAI
    except ImportError:
        raise SystemExit("The 'openai' package is required for --launch. Install: "
                         f"{sys.executable} -m pip install openai")
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    # Validate before spending money.
    do_validate()

    endpoint = (os.environ.get("FINETUNE_ENDPOINT")
                or _account_endpoint_from_env())
    if not endpoint:
        raise SystemExit("Set FINETUNE_ENDPOINT to the AI Services account endpoint, "
                         "e.g. https://aisvc-xxxx.services.ai.azure.com")

    direct_token = os.environ.get("FINETUNE_TOKEN")
    if direct_token:
        client = AzureOpenAI(
            azure_endpoint=endpoint,
            azure_ad_token=direct_token,
            api_version=api_version,
        )
    else:
        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
        )
        client = AzureOpenAI(
            azure_endpoint=endpoint,
            azure_ad_token_provider=token_provider,
            api_version=api_version,
        )

    print(f"\nEndpoint: {endpoint}")
    print(f"Model:    {model}")

    # Reuse already-uploaded files if their ids are provided (avoids re-upload
    # and lets us recover from a job-creation timeout without paying twice).
    train_id = os.environ.get("FINETUNE_TRAIN_FILE_ID")
    if train_id:
        print(f"Reusing training file id: {train_id}")
    else:
        print("Uploading training file...")
        with open(TRAIN, "rb") as fh:
            train_id = client.files.create(file=fh, purpose="fine-tune").id
        print(f"  train file id: {train_id}")

    val_id = os.environ.get("FINETUNE_VAL_FILE_ID")
    if val_id:
        print(f"Reusing validation file id: {val_id}")
    elif os.path.exists(VAL):
        print("Uploading validation file...")
        with open(VAL, "rb") as fh:
            val_id = client.files.create(file=fh, purpose="fine-tune").id
        print(f"  validation file id: {val_id}")

    # Azure rejects job creation until the uploaded files are processed.
    for fid in [f for f in (train_id, val_id) if f]:
        _wait_file_processed(client, fid)

    print("Creating fine-tuning job...")
    job = _create_job_with_retry(client, train_id, val_id, model, suffix)
    print(f"\nFine-tuning job created: {job.id}  (status: {job.status})")
    print("Track it with:")
    print(f"  python -c \"from openai import AzureOpenAI; ...\"  or the Foundry portal -> Fine-tuning.")


def _wait_file_processed(client, file_id: str, timeout_s: int = 600) -> None:
    """Poll an uploaded file until Azure reports it processed (or fails)."""
    import time
    from openai import NotFoundError
    deadline = time.time() + timeout_s
    while True:
        try:
            f = client.files.retrieve(file_id)
        except NotFoundError:
            # Just-uploaded files can 404 briefly until they propagate.
            if time.time() > deadline:
                raise SystemExit(f"Timed out: file {file_id} never became retrievable.")
            print(f"  file {file_id}: not yet visible ... waiting")
            time.sleep(10)
            continue
        status = getattr(f, "status", None)
        if status == "processed":
            print(f"  file {file_id}: processed")
            return
        if status in ("error", "failed", "deleted"):
            raise SystemExit(f"File {file_id} did not process (status={status}): "
                             f"{getattr(f, 'status_details', '')}")
        if time.time() > deadline:
            raise SystemExit(f"Timed out waiting for file {file_id} to process "
                             f"(last status={status}).")
        print(f"  file {file_id}: {status} ... waiting")
        time.sleep(10)


def _create_job_with_retry(client, train_id: str, val_id, model: str, suffix: str,
                           attempts: int = 5):
    """Create the fine-tuning job, retrying transient 408/5xx timeouts."""
    import time
    from openai import APIStatusError
    for i in range(1, attempts + 1):
        try:
            return client.fine_tuning.jobs.create(
                training_file=train_id,
                validation_file=val_id,
                model=model,
                suffix=suffix,
            )
        except APIStatusError as e:
            if e.status_code in (408, 409, 429, 500, 502, 503, 504) and i < attempts:
                wait = min(30, 5 * i)
                print(f"  job create failed ({e.status_code}); retry {i}/{attempts - 1} "
                      f"in {wait}s...")
                time.sleep(wait)
                continue
            raise


def _account_endpoint_from_env() -> str | None:
    """Derive the AI Services account endpoint from the azd project endpoint."""
    proj = os.environ.get("AZURE_AI_PROJECT_ENDPOINT", "")
    # https://aisvc-xxxx.services.ai.azure.com/api/projects/proj-xxxx  ->  https://aisvc-xxxx.services.ai.azure.com
    if proj:
        marker = ".services.ai.azure.com"
        i = proj.find(marker)
        if i != -1:
            return proj[: i + len(marker)]
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--launch", action="store_true",
                    help="Upload files and create the fine-tuning job (incurs cost).")
    ap.add_argument("--model", default="gpt-4.1-mini",
                    help="Base model to fine-tune (default gpt-4.1-mini).")
    ap.add_argument("--api-version", default="2024-10-21")
    ap.add_argument("--suffix", default="support-sft",
                    help="Suffix added to the fine-tuned model name.")
    ap.add_argument("--train", default=None, help="Override training JSONL path.")
    ap.add_argument("--val", default=None, help="Override validation JSONL path.")
    args = ap.parse_args()

    global TRAIN, VAL
    if args.train:
        TRAIN = args.train if os.path.isabs(args.train) else os.path.join(ROOT, args.train)
    if args.val:
        VAL = args.val if os.path.isabs(args.val) else os.path.join(ROOT, args.val)

    if args.launch:
        do_launch(args.model, args.api_version, args.suffix)
    else:
        do_validate()


if __name__ == "__main__":
    main()
