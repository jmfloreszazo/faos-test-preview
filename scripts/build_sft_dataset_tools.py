"""Build a tool-aware SFT dataset from the blast CSV traces.

Unlike ``build_sft_dataset.py`` (which only emits direct system/user/assistant
answers), this builder teaches the model BOTH skills, so the resulting
fine-tuned model works in the real agent (with the ``lookup_policy`` tool) AND
as a raw LLM (no tools):

  1. Tool trajectory (for the agent-with-tool scenario):
        system(can call lookup_policy) -> user
        -> assistant(tool_call lookup_policy{topic})
        -> tool(EXACT lookup_policy output)
        -> assistant(final answer)
     plus the ``tools`` schema on the example.

  2. Direct trajectory (for the raw-LLM scenario):
        system -> user -> assistant(final answer)

The tool-role content is the GROUND-TRUTH text returned by ``lookup_policy`` in
src/support-agent/main.py (never hallucinated). The final answer is the real
captured answer from the blast traces.

Usage:
    python scripts/build_sft_dataset_tools.py
    python scripts/build_sft_dataset_tools.py --val-split 0.1 --seed 42
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

# Exact policy text returned by lookup_policy() in src/support-agent/main.py.
POLICIES = {
    "returns": (
        "We accept returns within 30 days of purchase, "
        "with receipt and in the original packaging."
    ),
    "shipping": (
        "Standard shipping takes 3 to 5 business days. Express shipping "
        "(24-48 h) has an additional cost of $9.99."
    ),
    "warranty": (
        "All products include a 2-year warranty against manufacturing "
        "defects."
    ),
}
FALLBACK = (
    "I don't have information about that topic. Let me hand you over to a human agent."
)

# Tool schema, matching .agent_configs/baseline/tools.json.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_policy",
            "description": "Return the company policy for a given topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Topic to look up: returns, shipping or warranty.",
                    }
                },
                "required": ["topic"],
            },
        },
    }
]

# System prompt for the DIRECT (no-tool) examples.
SYSTEM_DIRECT = (
    "You are a customer support agent for an online store. You answer customer "
    "questions about returns, shipping and warranties. Be clear and concise, and "
    "always answer in English. Include concrete details (timeframes, costs, "
    "conditions) when they apply. If you do not have the information, say so "
    "explicitly and offer to hand off to a human agent. Never invent policies, "
    "prices or timeframes."
)

# System prompt for the TOOL examples (instructs tool use).
SYSTEM_TOOL = (
    "You are a customer support agent for an online store. You answer questions "
    "about returns, shipping and warranties. Use the `lookup_policy` tool to "
    "check the official policy before answering. Be clear and concise, and "
    "always answer in English. If you do not have the information, say so and "
    "offer to hand off to a human agent."
)

# Keyword signatures for topic classification (answer first, then question).
TOPIC_KEYWORDS = {
    "returns": ["return", "refund", "receipt", "30 day", "money back", "exchange"],
    "shipping": ["shipping", "ship", "delivery", "deliver", "express", "standard",
                 "business day", "$9.99", "9.99", "24-48", "24 to 48"],
    "warranty": ["warranty", "warranties", "covered", "cover ", "defect", "broke",
                 "broken", "stopped working", "guarantee", "2-year", "two year",
                 "2 year"],
}


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def classify(question: str, answer: str) -> str | None:
    """Return 'returns' | 'shipping' | 'warranty', or None if undetermined."""
    a = normalize(answer)
    q = normalize(question)
    scores: dict[str, int] = {}
    for topic, kws in TOPIC_KEYWORDS.items():
        score = sum(2 for kw in kws if kw in a) + sum(1 for kw in kws if kw in q)
        scores[topic] = score
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


def load_pairs(paths: list[str]) -> list[dict]:
    seen: set[str] = set()
    pairs: list[dict] = []
    for path in sorted(paths):
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
    return pairs


def direct_example(pair: dict) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_DIRECT},
            {"role": "user", "content": pair["question"]},
            {"role": "assistant", "content": pair["answer"]},
        ]
    }


def tool_example(pair: dict, topic: str) -> dict:
    call_id = "call_" + re.sub(r"[^a-z0-9]", "", normalize(pair["question"]))[:16].ljust(8, "0")
    tool_output = POLICIES.get(topic, FALLBACK)
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_TOOL},
            {"role": "user", "content": pair["question"]},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": "lookup_policy",
                            "arguments": json.dumps({"topic": topic}),
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": call_id, "content": tool_output},
            {"role": "assistant", "content": pair["answer"]},
        ],
        "tools": TOOLS,
    }


def write_jsonl(path: str, examples: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for ex in examples:
            fh.write(json.dumps(ex, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--val-split", type=float, default=0.1)
    ap.add_argument("--max", type=int, default=0, help="Cap unique questions (0 = no cap).")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    paths = glob.glob(CSV_GLOB)
    if not paths:
        raise SystemExit(f"No CSVs found at {CSV_GLOB}")

    pairs = load_pairs(paths)
    if not pairs:
        raise SystemExit("No clean rows found.")

    random.seed(args.seed)
    random.shuffle(pairs)
    if args.max and len(pairs) > args.max:
        pairs = pairs[: args.max]

    # Build mixed examples: one tool trajectory + one direct trajectory per pair.
    examples: list[dict] = []
    n_tool = 0
    n_direct = 0
    n_unclassified = 0
    for pair in pairs:
        topic = classify(pair["question"], pair["answer"])
        examples.append(direct_example(pair))
        n_direct += 1
        if topic is not None:
            examples.append(tool_example(pair, topic))
            n_tool += 1
        else:
            n_unclassified += 1

    random.shuffle(examples)

    n_val = max(1, int(len(examples) * args.val_split)) if args.val_split > 0 else 0
    val = examples[:n_val]
    train = examples[n_val:]

    os.makedirs(OUT_DIR, exist_ok=True)
    all_path = os.path.join(OUT_DIR, "support-sft-tools.jsonl")
    train_path = os.path.join(OUT_DIR, "support-sft-tools.train.jsonl")
    val_path = os.path.join(OUT_DIR, "support-sft-tools.val.jsonl")

    write_jsonl(all_path, examples)
    write_jsonl(train_path, train)
    if n_val:
        write_jsonl(val_path, val)

    print("================= TOOL-AWARE SFT DATASET =================")
    print(f"Unique questions      : {len(pairs)}")
    print(f"  Direct examples     : {n_direct}")
    print(f"  Tool examples       : {n_tool}")
    print(f"  Unclassified (no tool example): {n_unclassified}")
    print(f"Total examples        : {len(examples)}")
    print(f"  Training            : {len(train)}  -> {os.path.relpath(train_path, ROOT)}")
    if n_val:
        print(f"  Validation          : {len(val)}  -> {os.path.relpath(val_path, ROOT)}")
    print("\nFormat: Azure OpenAI chat JSONL with function-calling (tools + tool_calls).")
    print("Ready to fine-tune gpt-4o-2024-08-06 with tool support.")


if __name__ == "__main__":
    main()
