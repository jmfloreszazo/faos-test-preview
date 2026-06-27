r"""Test 2 - Same agent (with the ``lookup_policy`` tool) on two models.

Runs the SAME agent tool-flow on both the normal base deployment and the
fine-tuned deployment, on every question in ``data/support-eval.jsonl``:

  system (SYSTEM_TOOL, instructs tool use) + tool ``lookup_policy``
    call 1: model decides -> (optionally) requests lookup_policy{topic}
    we execute lookup_policy locally (ground-truth policy text)
    call 2: model answers grounded on the tool output

For each model and question we record: whether the tool was called, the topic,
prompt/completion tokens (summed across the internal calls), wall-clock latency,
and the final answer. A judge model scores each answer (relevance +
task_adherence, 1-5) against the ground truth. Results are aggregated and
written as Markdown.

Because the tool injects the correct policy, BOTH models should answer
correctly; the interesting deltas are tool-calling behaviour, tokens and
latency (the fine-tuned model learned the policies AND the tool, so it can be
more efficient / consistent).

Auth: FINETUNE_TOKEN (scope https://cognitiveservices.azure.com/.default) and
FINETUNE_ENDPOINT (inference endpoint). Example (PowerShell):

    $env:FINETUNE_TOKEN    = (az account get-access-token `
        --scope https://cognitiveservices.azure.com/.default --query accessToken -o tsv)
    $env:FINETUNE_ENDPOINT = 'https://aisvc-yrwwwokfuruzy.cognitiveservices.azure.com'
    .\.venv\Scripts\python.exe scripts/compare_agents_tool.py `
        --normal gpt-4o --ft gpt-4o-ft --judge gpt-4o --out docs/test2-agente.md
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL = os.path.join(ROOT, "src", "support-agent", "data", "support-eval.jsonl")

# System prompt that instructs the agent to use the lookup_policy tool
# (matches SYSTEM_TOOL in build_sft_dataset_tools.py).
SYSTEM_TOOL = (
    "You are a customer support agent for an online store. You answer questions "
    "about returns, shipping and warranties. Use the `lookup_policy` tool to "
    "check the official policy before answering. Be clear and concise, and "
    "always answer in English. If you do not have the information, say so and "
    "offer to hand off to a human agent."
)

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


def run_agent(client, deployment: str, question: str) -> dict:
    """Run the tool-enabled agent flow; return answer + tool usage + cost."""
    messages = [
        {"role": "system", "content": SYSTEM_TOOL},
        {"role": "user", "content": question},
    ]
    p_tok = c_tok = 0
    tool_called = False
    topics: list[str] = []
    t0 = time.perf_counter()

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

    elapsed = time.perf_counter() - t0
    return {
        "answer": answer, "tool_called": tool_called, "topics": topics,
        "prompt": p_tok, "completion": c_tok, "total": p_tok + c_tok,
        "seconds": round(elapsed, 3),
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


def avg(nums) -> float:
    return round(statistics.mean(nums), 2) if nums else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--normal", default="gpt-4o")
    ap.add_argument("--ft", default="gpt-4o-ft")
    ap.add_argument("--judge", default="gpt-4o")
    ap.add_argument("--api-version", default="2024-10-21")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "test2-agente.md"))
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
        rn = run_agent(client, args.normal, q)
        rf = run_agent(client, args.ft, q)
        jn = judge(client, args.judge, q, gt, rn["answer"])
        jf = judge(client, args.judge, q, gt, rf["answer"])
        results.append({"q": q, "gt": gt, "normal": rn, "ft": rf,
                        "jn": jn, "jf": jf})

    write_markdown(args, results)
    print(f"\nWrote {args.out}")


def write_markdown(args, results) -> None:
    n = len(results)

    def col(side: str, key: str) -> list[float]:
        return [r[side][key] for r in results]

    def jcol(side: str, axis: str) -> list[float]:
        return [r[side][axis] for r in results]

    norm_rel, ft_rel = jcol("jn", "relevance"), jcol("jf", "relevance")
    norm_adh, ft_adh = jcol("jn", "task_adherence"), jcol("jf", "task_adherence")
    norm_pass = sum(1 for v in norm_rel if v >= 4)
    ft_pass = sum(1 for v in ft_rel if v >= 4)
    norm_tool = sum(1 for r in results if r["normal"]["tool_called"])
    ft_tool = sum(1 for r in results if r["ft"]["tool_called"])

    lines = [
        "# Test 2 - Mismo agente con tool `lookup_policy`: normal vs fine-tuned",
        "",
        f"_Generado: {datetime.now():%Y-%m-%d %H:%M}_ - dataset: {n} preguntas "
        "([data/support-eval.jsonl](src/support-agent/data/support-eval.jsonl)).",
        "",
        "| Rol | Deployment |",
        "|---|---|",
        f"| Agente normal | `{args.normal}` |",
        f"| Agente fine-tuned | `{args.ft}` |",
        f"| Juez | `{args.judge}` |",
        "",
        "Ambos agentes usan el **mismo** system prompt y la **misma** tool "
        "`lookup_policy` (flujo de 2 llamadas: decidir tool -> responder con la "
        "politica). La tool inyecta la politica correcta, asi que ambos deberian "
        "acertar; lo interesante es el comportamiento de tool-calling, los tokens "
        "y la latencia.",
        "",
        "## Resultado agregado",
        "",
        "| Metrica | Normal | Fine-tuned | Δ |",
        "|---|:--:|:--:|:--:|",
        f"| Relevancia (1-5) | {avg(norm_rel)} | {avg(ft_rel)} | {round(avg(ft_rel)-avg(norm_rel),2):+} |",
        f"| Adherencia (1-5) | {avg(norm_adh)} | {avg(ft_adh)} | {round(avg(ft_adh)-avg(norm_adh),2):+} |",
        f"| Correctas (rel ≥ 4) | {norm_pass}/{n} | {ft_pass}/{n} | {ft_pass-norm_pass:+} |",
        f"| Veces que llamo a la tool | {norm_tool}/{n} | {ft_tool}/{n} | {ft_tool-norm_tool:+} |",
        f"| Tokens medios / pregunta | {avg(col('normal','total'))} | {avg(col('ft','total'))} | {round(avg(col('ft','total'))-avg(col('normal','total')),1):+} |",
        f"| Latencia media (s) | {avg(col('normal','seconds'))} | {avg(col('ft','seconds'))} | {round(avg(col('ft','seconds'))-avg(col('normal','seconds')),2):+} |",
        "",
        "## Detalle por pregunta",
        "",
    ]

    for i, r in enumerate(results, 1):
        rn, rf, jn, jf = r["normal"], r["ft"], r["jn"], r["jf"]
        lines += [
            f"### {i}. {r['q']}",
            "",
            f"**Ground truth:** {r['gt']}",
            "",
            f"**Normal (`{args.normal}`)** - rel {jn['relevance']}, adh "
            f"{jn['task_adherence']} · tool={'si' if rn['tool_called'] else 'no'}"
            f"{(' ('+', '.join(t for t in rn['topics'] if t)+')') if rn['topics'] else ''}"
            f" · {rn['total']} tok · {rn['seconds']}s  ·  _{jn['reason']}_  ",
            f"> {rn['answer']}",
            "",
            f"**Fine-tuned (`{args.ft}`)** - rel {jf['relevance']}, adh "
            f"{jf['task_adherence']} · tool={'si' if rf['tool_called'] else 'no'}"
            f"{(' ('+', '.join(t for t in rf['topics'] if t)+')') if rf['topics'] else ''}"
            f" · {rf['total']} tok · {rf['seconds']}s  ·  _{jf['reason']}_  ",
            f"> {rf['answer']}",
            "",
        ]

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
