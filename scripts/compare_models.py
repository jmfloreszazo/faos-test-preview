r"""Head-to-head evaluation: base model vs fine-tuned model on the support eval set.

For every question in ``data/support-eval.jsonl`` it asks two Azure OpenAI
deployments the same question (same system prompt) and then uses a judge model
to score each answer against the ground truth on two axes (relevance and task
adherence, 1-5). Results are aggregated and written as a Markdown comparison.

Auth: pass an Entra token in FINETUNE_TOKEN (scope
https://cognitiveservices.azure.com/.default) and the account endpoint in
FINETUNE_ENDPOINT. Example (PowerShell):

    $env:FINETUNE_TOKEN    = (az account get-access-token `
        --scope https://cognitiveservices.azure.com/.default --query accessToken -o tsv)
    $env:FINETUNE_ENDPOINT = 'https://aisvc-yrwwwokfuruzy.services.ai.azure.com'
    .\.venv\Scripts\python.exe scripts/compare_models.py

Usage:
    python scripts/compare_models.py [--base gpt-4.1-mini] [--ft support-sft-ft]
        [--judge gpt-4o] [--api-version 2024-10-21] [--out docs/finetune-comparison.md]
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL = os.path.join(ROOT, "src", "support-agent", "data", "support-eval.jsonl")

SYSTEM_PROMPT = (
    "You are a customer support agent for an online store. You answer customer "
    "questions about returns, shipping and warranties. Be clear and concise, and "
    "always answer in English. Include concrete details (timeframes, costs, "
    "conditions) when they apply. If you do not have the information, say so "
    "explicitly and offer to hand off to a human agent. Never invent policies, "
    "prices or timeframes."
)

JUDGE_SYSTEM = (
    "You are a strict evaluator of customer-support answers. Compare the AI answer "
    "to the reference (ground truth). Score two axes from 1 to 5:\n"
    "- relevance: does the answer address the question with the correct facts from "
    "the reference (timeframes, costs, conditions)?\n"
    "- task_adherence: does it behave like the expected support agent (concise, in "
    "English, and when the reference says to hand off to a human, it offers that)?\n"
    "A factually wrong or invented answer must score 1-2 on relevance. "
    "Respond ONLY with compact JSON: "
    '{"relevance": <int>, "task_adherence": <int>, "reason": "<short>"}.'
)


def load_eval(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def make_client(endpoint: str, token: str, api_version: str):
    from openai import AzureOpenAI
    return AzureOpenAI(
        azure_endpoint=endpoint,
        azure_ad_token=token,
        api_version=api_version,
    )


def ask(client, deployment: str, question: str) -> str:
    resp = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        max_tokens=250,
        temperature=0.2,
    )
    return (resp.choices[0].message.content or "").strip()


def judge(client, deployment: str, question: str, ground_truth: str, answer: str) -> dict:
    user = (
        f"Question:\n{question}\n\n"
        f"Reference (ground truth):\n{ground_truth}\n\n"
        f"AI answer:\n{answer}"
    )
    resp = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": user},
        ],
        max_tokens=200,
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    raw = (resp.choices[0].message.content or "{}").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"relevance": 0, "task_adherence": 0, "reason": "unparseable judge output"}
    data["relevance"] = int(data.get("relevance", 0) or 0)
    data["task_adherence"] = int(data.get("task_adherence", 0) or 0)
    data["reason"] = str(data.get("reason", ""))
    return data


def avg(nums: list[float]) -> float:
    return round(statistics.mean(nums), 2) if nums else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="gpt-4.1-mini")
    ap.add_argument("--ft", default="support-sft-ft")
    ap.add_argument("--judge", default="gpt-4o")
    ap.add_argument("--api-version", default="2024-10-21")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "finetune-comparison.md"))
    args = ap.parse_args()

    endpoint = os.environ.get("FINETUNE_ENDPOINT")
    token = os.environ.get("FINETUNE_TOKEN")
    if not endpoint or not token:
        raise SystemExit("Set FINETUNE_ENDPOINT and FINETUNE_TOKEN (see module docstring).")

    client = make_client(endpoint, token, args.api_version)
    rows = load_eval(EVAL)
    print(f"Loaded {len(rows)} eval questions.")

    results = []
    for i, row in enumerate(rows, 1):
        q, gt = row["query"], row["ground_truth"]
        print(f"[{i}/{len(rows)}] {q}")
        base_ans = ask(client, args.base, q)
        ft_ans = ask(client, args.ft, q)
        base_j = judge(client, args.judge, q, gt, base_ans)
        ft_j = judge(client, args.judge, q, gt, ft_ans)
        results.append({
            "query": q, "ground_truth": gt,
            "base_answer": base_ans, "ft_answer": ft_ans,
            "base": base_j, "ft": ft_j,
        })

    # Aggregates.
    def col(model: str, axis: str) -> list[float]:
        return [r[model][axis] for r in results]

    agg = {
        "base_rel": avg(col("base", "relevance")),
        "base_adh": avg(col("base", "task_adherence")),
        "ft_rel": avg(col("ft", "relevance")),
        "ft_adh": avg(col("ft", "task_adherence")),
    }
    agg["base_overall"] = round((agg["base_rel"] + agg["base_adh"]) / 2, 2)
    agg["ft_overall"] = round((agg["ft_rel"] + agg["ft_adh"]) / 2, 2)
    base_pass = sum(1 for r in results if r["base"]["relevance"] >= 4)
    ft_pass = sum(1 for r in results if r["ft"]["relevance"] >= 4)

    write_markdown(args, results, agg, base_pass, ft_pass, len(rows))
    print(f"\nBase overall:       {agg['base_overall']}/5  (relevance {agg['base_rel']}, adherence {agg['base_adh']}, pass {base_pass}/{len(rows)})")
    print(f"Fine-tuned overall: {agg['ft_overall']}/5  (relevance {agg['ft_rel']}, adherence {agg['ft_adh']}, pass {ft_pass}/{len(rows)})")
    print(f"\nWrote {args.out}")


def write_markdown(args, results, agg, base_pass, ft_pass, n) -> None:
    import datetime
    def delta(ft, base):
        d = round(ft - base, 2)
        return f"+{d}" if d >= 0 else f"{d}"

    lines = []
    lines.append("# Comparativa: modelo base vs fine-tuneado")
    lines.append("")
    lines.append(f"_Generado: {datetime.datetime.now():%Y-%m-%d %H:%M}_ — "
                 f"dataset de evaluación: 8 preguntas con `ground_truth` "
                 "([data/support-eval.jsonl](src/support-agent/data/support-eval.jsonl)).")
    lines.append("")
    lines.append("| Rol | Deployment |")
    lines.append("|---|---|")
    lines.append(f"| Modelo base | `{args.base}` |")
    lines.append(f"| Modelo fine-tuneado | `{args.ft}` |")
    lines.append(f"| Juez (evaluador) | `{args.judge}` |")
    lines.append("")
    lines.append("Mismo `system` para ambos candidatos (sin acceso a la herramienta "
                 "`lookup_policy`): se mide cuánto conocimiento de las políticas tiene "
                 "el modelo **en sus pesos**. El modelo fine-tuneado aprendió las "
                 "políticas durante el SFT; el base no las conoce.")
    lines.append("")
    lines.append("## Resultado agregado (1-5)")
    lines.append("")
    lines.append("| Métrica | Base | Fine-tuned | Δ |")
    lines.append("|---|:--:|:--:|:--:|")
    lines.append(f"| Relevancia (factual) | {agg['base_rel']} | {agg['ft_rel']} | {delta(agg['ft_rel'], agg['base_rel'])} |")
    lines.append(f"| Adherencia a la tarea | {agg['base_adh']} | {agg['ft_adh']} | {delta(agg['ft_adh'], agg['base_adh'])} |")
    lines.append(f"| **Global** | **{agg['base_overall']}** | **{agg['ft_overall']}** | **{delta(agg['ft_overall'], agg['base_overall'])}** |")
    lines.append(f"| Respuestas correctas (rel ≥ 4) | {base_pass}/{n} | {ft_pass}/{n} | {delta(ft_pass, base_pass)} |")
    lines.append("")
    if agg["base_overall"]:
        rel_impr = round((agg["ft_overall"] - agg["base_overall"]) / agg["base_overall"] * 100, 1)
        lines.append(f"Mejora relativa global del fine-tuned sobre el base: **{rel_impr:+.1f}%**.")
        lines.append("")
    lines.append("## Detalle por pregunta")
    lines.append("")
    for i, r in enumerate(results, 1):
        lines.append(f"### {i}. {r['query']}")
        lines.append("")
        lines.append(f"**Ground truth:** {r['ground_truth']}")
        lines.append("")
        lines.append(f"**Base (`{args.base}`)** — rel {r['base']['relevance']}, "
                     f"adh {r['base']['task_adherence']}  ·  _{r['base']['reason']}_  ")
        lines.append(f"> {r['base_answer']}")
        lines.append("")
        lines.append(f"**Fine-tuned (`{args.ft}`)** — rel {r['ft']['relevance']}, "
                     f"adh {r['ft']['task_adherence']}  ·  _{r['ft']['reason']}_  ")
        lines.append(f"> {r['ft_answer']}")
        lines.append("")
    out = args.out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
