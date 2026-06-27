r"""Test 3 - Optimize the SAME agent on both models and watch it evolve.

We take the tool-enabled support agent and, starting from a deliberately
*weak* baseline system prompt, run an iterative prompt-optimization loop driven
by an optimizer model (gpt-5.1). On every iteration the optimizer sees the
current prompt plus the per-question results (answer, judge scores, whether the
``lookup_policy`` tool was called) and proposes an improved system prompt. We
re-evaluate, keep the best candidate, and repeat.

We do this independently for the NORMAL base deployment and the FINE-TUNED
deployment, so we can compare *how each evolves* from the same weak baseline:

  baseline (weak prompt)  --optimize-->  best prompt

The judge (gpt-4o) scores relevance + task_adherence (1-5) against the ground
truth, exactly like Test 1 / Test 2, so all three tests are comparable.

This runs entirely against the inference endpoint (chat.completions); it does
NOT depend on the hosted agent runtime, so it is robust to the runtime 404.

Auth (PowerShell):

    $env:FINETUNE_TOKEN    = (az account get-access-token `
        --scope https://cognitiveservices.azure.com/.default --query accessToken -o tsv)
    $env:FINETUNE_ENDPOINT = 'https://aisvc-yrwwwokfuruzy.cognitiveservices.azure.com'
    .\.venv\Scripts\python.exe scripts/optimize_compare.py `
        --normal gpt-4o --ft gpt-4o-ft --judge gpt-4o --optimizer gpt-5.1 `
        --iterations 3 --out docs/test3-optimizacion.md
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL = os.path.join(ROOT, "src", "support-agent", "data", "support-eval.jsonl")

# Deliberately weak starting prompt: no tool guidance, no conciseness rule,
# no language rule, no fallback behaviour. Plenty of room to improve.
WEAK_SYSTEM = "You are a support bot. Answer the customer's question."

# Exact policy text returned by lookup_policy() in src/support-agent/main.py.
POLICIES = {
    "returns": "We accept returns within 30 days of purchase, with receipt and in the original packaging.",
    "shipping": "Standard shipping takes 3 to 5 business days. Express shipping (24-48 h) has an additional cost of $9.99.",
    "warranty": "All products include a 2-year warranty against manufacturing defects.",
}
POLICY_FALLBACK = "I don't have information about that topic. Let me hand you over to a human agent."

TOOLS = [{
    "type": "function",
    "function": {
        "name": "lookup_policy",
        "description": "Return the company policy for a given topic.",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string",
                          "description": "Topic to look up: returns, shipping or warranty."},
            },
            "required": ["topic"],
        },
    },
}]

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

OPTIMIZER_SYSTEM = (
    "You are a prompt optimizer for a customer-support agent. The agent answers "
    "questions about returns, shipping and warranties, and has access to a tool "
    "`lookup_policy(topic)` that returns the official policy text for the topics "
    "'returns', 'shipping' or 'warranty'. You are given the agent's CURRENT system "
    "prompt and a report of how it performed on a set of questions (each with the "
    "ground truth, the agent's answer, judge scores for relevance and "
    "task_adherence on a 1-5 scale, and whether the agent called the tool).\n\n"
    "Rewrite the system prompt to maximize relevance and task_adherence. The ideal "
    "agent: always uses `lookup_policy` before answering, replies in English, is "
    "clear and concise (no padding), answers ONLY what was asked, and when it has "
    "no information offers to hand off to a human agent. Do not hard-code the "
    "policy values into the prompt (the tool provides them). Keep the prompt short "
    "and instructional.\n\n"
    "Respond ONLY with compact JSON: {\"system_prompt\": \"<the new prompt>\"}."
)


def lookup_policy(topic: str) -> str:
    return POLICIES.get((topic or "").lower().strip(), POLICY_FALLBACK)


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
    return AzureOpenAI(azure_endpoint=endpoint, azure_ad_token=token,
                       api_version=api_version)


def run_agent(client, deployment: str, system_prompt: str, question: str) -> dict:
    """Run the tool-enabled agent flow with a given system prompt."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]
    p_tok = c_tok = 0
    tool_called = False
    topics: list[str] = []

    r1 = client.chat.completions.create(
        model=deployment, messages=messages, tools=TOOLS,
        tool_choice="auto", temperature=0.2, max_tokens=250,
    )
    p_tok += r1.usage.prompt_tokens
    c_tok += r1.usage.completion_tokens
    msg = r1.choices[0].message
    answer = (msg.content or "").strip()

    if msg.tool_calls:
        tool_called = True
        messages.append({
            "role": "assistant", "content": msg.content,
            "tool_calls": [{
                "id": tc.id, "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            } for tc in msg.tool_calls],
        })
        for tc in msg.tool_calls:
            try:
                topic = json.loads(tc.function.arguments).get("topic", "")
            except json.JSONDecodeError:
                topic = ""
            topics.append(topic)
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": lookup_policy(topic)})
        r2 = client.chat.completions.create(
            model=deployment, messages=messages, tools=TOOLS,
            tool_choice="auto", temperature=0.2, max_tokens=250,
        )
        p_tok += r2.usage.prompt_tokens
        c_tok += r2.usage.completion_tokens
        answer = (r2.choices[0].message.content or "").strip()

    return {
        "answer": answer, "tool_called": tool_called, "topics": topics,
        "total": p_tok + c_tok,
    }


def judge(client, deployment: str, question: str, ground_truth: str, answer: str) -> dict:
    user = (
        f"Question:\n{question}\n\n"
        f"Reference (ground truth):\n{ground_truth}\n\n"
        f"AI answer:\n{answer}"
    )
    resp = client.chat.completions.create(
        model=deployment,
        messages=[{"role": "system", "content": JUDGE_SYSTEM},
                  {"role": "user", "content": user}],
        max_tokens=200, temperature=0.0,
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


def optimizer_complete(client, deployment: str, report: str) -> str:
    """Ask the optimizer model for a new system prompt. Robust to gpt-5.x param
    differences (no temperature, max_completion_tokens)."""
    messages = [
        {"role": "system", "content": OPTIMIZER_SYSTEM},
        {"role": "user", "content": report},
    ]
    kwargs_variants = [
        {"max_completion_tokens": 600, "response_format": {"type": "json_object"}},
        {"max_tokens": 600, "temperature": 0.7, "response_format": {"type": "json_object"}},
        {"max_completion_tokens": 600},
    ]
    last_err = None
    for kw in kwargs_variants:
        try:
            resp = client.chat.completions.create(model=deployment, messages=messages, **kw)
            raw = (resp.choices[0].message.content or "").strip()
            try:
                data = json.loads(raw)
                sp = str(data.get("system_prompt", "")).strip()
            except json.JSONDecodeError:
                sp = raw
            if sp:
                return sp
        except Exception as exc:  # noqa: BLE001 - probe param compatibility
            last_err = exc
    raise RuntimeError(f"optimizer call failed: {last_err}")


def avg(nums) -> float:
    return round(statistics.mean(nums), 3) if nums else 0.0


def evaluate(client, deployment: str, judge_dep: str, system_prompt: str,
             rows: list[dict]) -> dict:
    """Run the agent + judge over the eval set; return per-question + aggregates."""
    per = []
    for row in rows:
        q, gt = row["query"], row["ground_truth"]
        out = run_agent(client, deployment, system_prompt, q)
        j = judge(client, judge_dep, q, gt, out["answer"])
        per.append({"q": q, "gt": gt, **out, **j})
    rel = [p["relevance"] for p in per]
    adh = [p["task_adherence"] for p in per]
    tool = sum(1 for p in per if p["tool_called"])
    passed = sum(1 for v in rel if v >= 4)
    combined = round((avg(rel) + avg(adh)) / 2, 3)
    return {
        "system_prompt": system_prompt, "per": per,
        "relevance": avg(rel), "adherence": avg(adh), "combined": combined,
        "passed": passed, "tool": tool, "n": len(per),
        "tokens": avg([p["total"] for p in per]),
    }


def build_report(ev: dict) -> str:
    lines = [f"CURRENT SYSTEM PROMPT:\n{ev['system_prompt']}\n",
             f"Aggregate: relevance={ev['relevance']}/5 adherence={ev['adherence']}/5 "
             f"tool_called={ev['tool']}/{ev['n']} correct(rel>=4)={ev['passed']}/{ev['n']}\n",
             "Per-question results:"]
    for i, p in enumerate(ev["per"], 1):
        lines.append(
            f"{i}. Q: {p['q']}\n   ground_truth: {p['gt']}\n"
            f"   tool_called: {p['tool_called']} topics: {p['topics']}\n"
            f"   answer: {p['answer']}\n"
            f"   scores: relevance={p['relevance']} task_adherence={p['task_adherence']} "
            f"({p['reason']})")
    return "\n".join(lines)


def optimize_model(client, deployment: str, judge_dep: str, optimizer_dep: str,
                   rows: list[dict], iterations: int, label: str) -> dict:
    print(f"\n=== Optimizing {label} ({deployment}) ===")
    baseline = evaluate(client, deployment, judge_dep, WEAK_SYSTEM, rows)
    print(f"  baseline: combined={baseline['combined']} rel={baseline['relevance']} "
          f"adh={baseline['adherence']} pass={baseline['passed']}/{baseline['n']} "
          f"tool={baseline['tool']}/{baseline['n']}")
    history = [{"iter": 0, **{k: baseline[k] for k in
               ("relevance", "adherence", "combined", "passed", "tool", "tokens")}}]
    best = baseline
    for it in range(1, iterations + 1):
        report = build_report(best)
        try:
            candidate_prompt = optimizer_complete(client, optimizer_dep, report)
        except Exception as exc:  # noqa: BLE001
            print(f"  iter {it}: optimizer error -> {exc}; stopping.")
            break
        ev = evaluate(client, deployment, judge_dep, candidate_prompt, rows)
        improved = ev["combined"] > best["combined"]
        print(f"  iter {it}: combined={ev['combined']} rel={ev['relevance']} "
              f"adh={ev['adherence']} pass={ev['passed']}/{ev['n']} "
              f"tool={ev['tool']}/{ev['n']} {'(new best)' if improved else ''}")
        history.append({"iter": it, **{k: ev[k] for k in
                       ("relevance", "adherence", "combined", "passed", "tool", "tokens")}})
        if improved:
            best = ev
    return {"label": label, "deployment": deployment, "baseline": baseline,
            "best": best, "history": history}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--normal", default="gpt-4o")
    ap.add_argument("--ft", default="gpt-4o-ft")
    ap.add_argument("--judge", default="gpt-4o")
    ap.add_argument("--optimizer", default="gpt-5.1")
    ap.add_argument("--iterations", type=int, default=3)
    ap.add_argument("--api-version", default="2024-10-21")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "test3-optimizacion.md"))
    args = ap.parse_args()

    endpoint = os.environ.get("FINETUNE_ENDPOINT")
    token = os.environ.get("FINETUNE_TOKEN")
    if not endpoint or not token:
        raise SystemExit("Set FINETUNE_ENDPOINT and FINETUNE_TOKEN (see module docstring).")

    client = make_client(endpoint, token, args.api_version)
    rows = load_eval(EVAL)
    print(f"Loaded {len(rows)} eval questions.")

    normal = optimize_model(client, args.normal, args.judge, args.optimizer,
                            rows, args.iterations, "Normal")
    ft = optimize_model(client, args.ft, args.judge, args.optimizer,
                        rows, args.iterations, "Fine-tuned")

    write_markdown(args, normal, ft)
    print(f"\nWrote {args.out}")


def _evo_table(res: dict) -> list[str]:
    lines = ["| Iter | Relevancia | Adherencia | Combinada | Correctas | Tool |",
             "|:--:|:--:|:--:|:--:|:--:|:--:|"]
    n = res["baseline"]["n"]
    for h in res["history"]:
        tag = " (baseline)" if h["iter"] == 0 else ""
        lines.append(
            f"| {h['iter']}{tag} | {h['relevance']} | {h['adherence']} | "
            f"{h['combined']} | {h['passed']}/{n} | {h['tool']}/{n} |")
    return lines


def write_markdown(args, normal: dict, ft: dict) -> None:
    def delta(res: dict, key: str) -> str:
        d = round(res["best"][key] - res["baseline"][key], 3)
        return f"{d:+}"

    n = normal["baseline"]["n"]
    lines = [
        "# Test 3 - Optimizacion del mismo agente: normal vs fine-tuned",
        "",
        f"_Generado: {datetime.now():%Y-%m-%d %H:%M}_ - dataset: {n} preguntas "
        "([data/support-eval.jsonl](src/support-agent/data/support-eval.jsonl)).",
        "",
        f"Optimizador: `{args.optimizer}` · Juez: `{args.judge}` · "
        f"Iteraciones: {args.iterations}.",
        "",
        "Ambos agentes parten del **mismo prompt debil** y se optimizan con el "
        "mismo modelo optimizador y el mismo dataset. El optimizador reescribe el "
        "system prompt iteracion a iteracion buscando maximizar relevancia + "
        "adherencia; nos quedamos con el mejor candidato. Asi vemos *como "
        "evoluciona* cada version del modelo desde la misma base.",
        "",
        f"**Prompt debil de partida:** `{WEAK_SYSTEM}`",
        "",
        "## Resumen: baseline -> optimizado",
        "",
        "| Modelo | Combinada base | Combinada opt | Δ | Correctas base | Correctas opt |",
        "|---|:--:|:--:|:--:|:--:|:--:|",
        f"| Normal (`{normal['deployment']}`) | {normal['baseline']['combined']} | "
        f"{normal['best']['combined']} | {delta(normal,'combined')} | "
        f"{normal['baseline']['passed']}/{n} | {normal['best']['passed']}/{n} |",
        f"| Fine-tuned (`{ft['deployment']}`) | {ft['baseline']['combined']} | "
        f"{ft['best']['combined']} | {delta(ft,'combined')} | "
        f"{ft['baseline']['passed']}/{n} | {ft['best']['passed']}/{n} |",
        "",
        "## Evolucion - Normal",
        "",
        *_evo_table(normal),
        "",
        "## Evolucion - Fine-tuned",
        "",
        *_evo_table(ft),
        "",
        "## Prompts optimizados",
        "",
        f"**Normal (`{normal['deployment']}`):**",
        "",
        "```text",
        normal["best"]["system_prompt"],
        "```",
        "",
        f"**Fine-tuned (`{ft['deployment']}`):**",
        "",
        "```text",
        ft["best"]["system_prompt"],
        "```",
        "",
        "## Detalle final por pregunta (prompt optimizado)",
        "",
    ]

    for i in range(n):
        pn = normal["best"]["per"][i]
        pf = ft["best"]["per"][i]
        lines += [
            f"### {i+1}. {pn['q']}",
            "",
            f"**Ground truth:** {pn['gt']}",
            "",
            f"**Normal** - rel {pn['relevance']}, adh {pn['task_adherence']} · "
            f"tool={'si' if pn['tool_called'] else 'no'} · {pn['total']} tok  ·  "
            f"_{pn['reason']}_  ",
            f"> {pn['answer']}",
            "",
            f"**Fine-tuned** - rel {pf['relevance']}, adh {pf['task_adherence']} · "
            f"tool={'si' if pf['tool_called'] else 'no'} · {pf['total']} tok  ·  "
            f"_{pf['reason']}_  ",
            f"> {pf['answer']}",
            "",
        ]

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
