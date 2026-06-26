"""Build a Supervised Fine-Tuning (SFT) dataset from the blast CSV traces.

Reads the question/answer pairs captured by ``scripts/blast_agent.ps1`` and
emits Azure OpenAI chat-format JSONL ready to upload as fine-tuning training
data:

    {"messages": [
        {"role": "system",    "content": "<persona>"},
        {"role": "user",      "content": "<customer question>"},
        {"role": "assistant", "content": "<support answer>"}
    ]}

Only clean rows are kept (Status == ok AND a non-empty Answer), so the
throttled/empty rows from the first run are dropped automatically. Questions
are de-duplicated (first good answer wins) and the set is shuffled and split
into train / validation files.

Usage:
    python scripts/build_sft_dataset.py
    python scripts/build_sft_dataset.py --val-split 0.1 --max 0 --seed 42
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import random
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_GLOB = os.path.join(ROOT, "optimize-runs", "blast-*.csv")
OUT_DIR = os.path.join(ROOT, "src", "support-agent", "data")

# System prompt baked into every SFT example. Derived from the agent's baseline
# persona (.agent_configs/baseline/instructions.md) but without the mandatory
# tool-call instruction, because these examples train the model to answer the
# policy directly (the captured traces contain the final answer, not the tool
# call arguments).
SYSTEM_PROMPT = (
    "You are a customer support agent for an online store. You answer customer "
    "questions about returns, shipping and warranties. Be clear and concise, and "
    "always answer in English. Include concrete details (timeframes, costs, "
    "conditions) when they apply. If you do not have the information, say so "
    "explicitly and offer to hand off to a human agent. Never invent policies, "
    "prices or timeframes."
)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def load_pairs(paths: list[str]) -> list[dict]:
    """Return de-duplicated [{question, answer}] from all CSVs (clean rows only)."""
    seen: set[str] = set()
    pairs: list[dict] = []
    kept_per_file: dict[str, int] = {}
    for path in sorted(paths):
        kept = 0
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                status = (row.get("Status") or "").strip().lower()
                question = (row.get("Question") or "").strip()
                answer = (row.get("Answer") or "").strip()
                if status != "ok" or not question or not answer:
                    continue
                key = normalize(question)
                if key in seen:
                    continue
                seen.add(key)
                pairs.append({"question": question, "answer": answer})
                kept += 1
        kept_per_file[os.path.basename(path)] = kept
    for name, count in kept_per_file.items():
        print(f"  {name}: {count} unique clean pairs")
    return pairs


def to_example(pair: dict) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": pair["question"]},
            {"role": "assistant", "content": pair["answer"]},
        ]
    }


def write_jsonl(path: str, examples: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for ex in examples:
            fh.write(json.dumps(ex, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--val-split", type=float, default=0.1,
                    help="Fraction held out for validation (default 0.1).")
    ap.add_argument("--max", type=int, default=0,
                    help="Cap the total number of examples (0 = no cap).")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    paths = glob.glob(CSV_GLOB)
    if not paths:
        raise SystemExit(f"No CSVs found at {CSV_GLOB}")

    print("Reading CSV traces:")
    pairs = load_pairs(paths)
    if not pairs:
        raise SystemExit("No clean (Status=ok, non-empty Answer) rows found.")

    random.seed(args.seed)
    random.shuffle(pairs)
    if args.max and len(pairs) > args.max:
        pairs = pairs[: args.max]

    n_val = max(1, int(len(pairs) * args.val_split)) if args.val_split > 0 else 0
    val_pairs = pairs[:n_val]
    train_pairs = pairs[n_val:]

    os.makedirs(OUT_DIR, exist_ok=True)
    all_path = os.path.join(OUT_DIR, "support-sft.jsonl")
    train_path = os.path.join(OUT_DIR, "support-sft.train.jsonl")
    val_path = os.path.join(OUT_DIR, "support-sft.val.jsonl")

    write_jsonl(all_path, [to_example(p) for p in pairs])
    write_jsonl(train_path, [to_example(p) for p in train_pairs])
    if n_val:
        write_jsonl(val_path, [to_example(p) for p in val_pairs])

    print("\n======================= SFT DATASET =======================")
    print(f"Total clean examples : {len(pairs)}")
    print(f"  Training           : {len(train_pairs)}  -> {os.path.relpath(train_path, ROOT)}")
    if n_val:
        print(f"  Validation         : {len(val_pairs)}  -> {os.path.relpath(val_path, ROOT)}")
    print(f"  Combined           : {len(pairs)}  -> {os.path.relpath(all_path, ROOT)}")
    print("\nFormat: Azure OpenAI chat JSONL (system/user/assistant). Ready to upload as")
    print("fine-tuning training data for gpt-4.1-mini.")


if __name__ == "__main__":
    main()
