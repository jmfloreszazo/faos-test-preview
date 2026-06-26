"""Cost & latency comparison: optimized base agent vs fine-tuned model.

Two production paths are measured on the same eval questions:

  A) OPTIMIZED AGENT  (what is deployed today)
     - model: gpt-4.1-mini  (base, cheaper/"inferior")
     - long optimized system prompt (winning candidate instructions)
     - tool `lookup_policy` -> TWO model calls per question
       (1: decide the tool call, 2: answer using the tool result)

  B) FINE-TUNED MODEL
     - model: support-sft-ft  (fine-tuned gpt-4o-2024-08-06)
     - short system prompt, NO tool -> ONE model call per question
       (the policies are baked into the weights)

For every question we record prompt_tokens, completion_tokens and wall-clock
latency for each path (path A sums both internal calls), then aggregate and
estimate cost. Output is written as Markdown.

Auth: FINETUNE_TOKEN (scope https://cognitiveservices.azure.com/.default) and
FINETUNE_ENDPOINT (account endpoint). Both paths use chat completions on the
same account, so a single token works.

Prices are LIST-PRICE ESTIMATES (USD per 1M tokens) and can be overridden via
CLI. Fine-tuned deployments also bill hosting per hour (not per token); see the
note in the generated report.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL = os.path.join(ROOT, "src", "support-agent", "data", "support-eval.jsonl")
OPT_INSTRUCTIONS = os.path.join(
    ROOT, "src", "support-agent", ".agent_configs",
    "cand_1465ed93e173446195e3b81bb2a399e5", "instructions.md",
)

FT_SYSTEM_PROMPT = (
    "You are a customer support agent for an online store. You answer customer "
    "questions about returns, shipping and warranties. Be clear and concise, and "
    "always answer in English. Include concrete details (timeframes, costs, "
    "conditions) when they apply. If you do not have the information, say so "
    "explicitly and offer to hand off to a human agent. Never invent policies, "
    "prices or timeframes."
)

# Same policies the hosted agent serves through lookup_policy (see main.py).
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
        "description": "Looks up the company's official policy for a given topic.",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string",
                          "description": "Topic to look up: returns, shipping or warranty."}
            },
            "required": ["topic"],
        },
    },
}]


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


def run_optimized(client, deployment: str, instructions: str, question: str) -> dict:
    """Reproduce the optimized agent: tool-decision call + answer call."""
    messages = [
        {"role": "system", "content": instructions},
        {"role": "user", "content": question},
    ]
    p_tok = c_tok = 0
    t0 = time.perf_counter()

    # Call 1: let the model decide / request the tool.
    r1 = client.chat.completions.create(
        model=deployment, messages=messages, tools=TOOLS,
        tool_choice="auto", temperature=0.2, max_tokens=250,
    )
    p_tok += r1.usage.prompt_tokens
    c_tok += r1.usage.completion_tokens
    msg = r1.choices[0].message

    answer = (msg.content or "").strip()
    if msg.tool_calls:
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
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": lookup_policy(topic)})
        # Call 2: final answer grounded on the tool output.
        r2 = client.chat.completions.create(
            model=deployment, messages=messages, tools=TOOLS,
            tool_choice="auto", temperature=0.2, max_tokens=250,
        )
        p_tok += r2.usage.prompt_tokens
        c_tok += r2.usage.completion_tokens
        answer = (r2.choices[0].message.content or "").strip()

    elapsed = time.perf_counter() - t0
    return {"prompt": p_tok, "completion": c_tok, "total": p_tok + c_tok,
            "seconds": round(elapsed, 3), "answer": answer}


def run_finetuned(client, deployment: str, question: str) -> dict:
    t0 = time.perf_counter()
    r = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": FT_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        temperature=0.2, max_tokens=250,
    )
    elapsed = time.perf_counter() - t0
    return {"prompt": r.usage.prompt_tokens, "completion": r.usage.completion_tokens,
            "total": r.usage.total_tokens, "seconds": round(elapsed, 3),
            "answer": (r.choices[0].message.content or "").strip()}


def avg(nums) -> float:
    return round(statistics.mean(nums), 2) if nums else 0.0


def cost(prompt_tok: float, completion_tok: float, p_in: float, p_out: float) -> float:
    """USD for given token counts at price-per-1M rates."""
    return round(prompt_tok / 1_000_000 * p_in + completion_tok / 1_000_000 * p_out, 6)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--opt-model", default="gpt-4.1-mini")
    ap.add_argument("--ft-model", default="support-sft-ft")
    ap.add_argument("--api-version", default="2024-10-21")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "finetune-cost-latency.md"))
    # List-price estimates (USD / 1M tokens). Override if your rates differ.
    ap.add_argument("--opt-price-in", type=float, default=0.40)
    ap.add_argument("--opt-price-out", type=float, default=1.60)
    ap.add_argument("--ft-price-in", type=float, default=3.75)
    ap.add_argument("--ft-price-out", type=float, default=15.00)
    ap.add_argument("--ft-hosting-per-hour", type=float, default=1.70)
    args = ap.parse_args()

    endpoint = os.environ.get("FINETUNE_ENDPOINT")
    token = os.environ.get("FINETUNE_TOKEN")
    if not endpoint or not token:
        raise SystemExit("Set FINETUNE_ENDPOINT and FINETUNE_TOKEN (see module docstring).")

    with open(OPT_INSTRUCTIONS, encoding="utf-8") as fh:
        instructions = fh.read()

    client = make_client(endpoint, token, args.api_version)
    rows = load_eval(EVAL)
    print(f"Loaded {len(rows)} eval questions.")

    results = []
    for i, row in enumerate(rows, 1):
        q = row["query"]
        print(f"[{i}/{len(rows)}] {q}")
        opt = run_optimized(client, args.opt_model, instructions, q)
        ft = run_finetuned(client, args.ft_model, q)
        results.append({"query": q, "opt": opt, "ft": ft})

    write_markdown(args, results)
    # Console summary.
    def col(m, k): return [r[m][k] for r in results]
    print("\n             input   output   total   sec")
    print(f"  optimized  {avg(col('opt','prompt')):>6}  {avg(col('opt','completion')):>6}  "
          f"{avg(col('opt','total')):>6}  {avg(col('opt','seconds')):>5}")
    print(f"  finetuned  {avg(col('ft','prompt')):>6}  {avg(col('ft','completion')):>6}  "
          f"{avg(col('ft','total')):>6}  {avg(col('ft','seconds')):>5}")
    print(f"\nWrote {args.out}")


def write_markdown(args, results) -> None:
    import datetime
    def col(m, k): return [r[m][k] for r in results]

    n = len(results)
    opt_in, opt_out = avg(col("opt", "prompt")), avg(col("opt", "completion"))
    ft_in, ft_out = avg(col("ft", "prompt")), avg(col("ft", "completion"))
    opt_tot, ft_tot = avg(col("opt", "total")), avg(col("ft", "total"))
    opt_sec, ft_sec = avg(col("opt", "seconds")), avg(col("ft", "seconds"))

    # Cost per 1,000 requests at average usage.
    opt_cost_1k = round(cost(opt_in, opt_out, args.opt_price_in, args.opt_price_out) * 1000, 4)
    ft_cost_1k = round(cost(ft_in, ft_out, args.ft_price_in, args.ft_price_out) * 1000, 4)

    def pct(new, base):
        if not base:
            return "n/a"
        return f"{(new - base) / base * 100:+.1f}%"

    L = []
    L.append("# Comparativa de coste y latencia: agente optimizado vs fine-tuned")
    L.append("")
    L.append(f"_Generado: {datetime.datetime.now():%Y-%m-%d %H:%M}_ — "
             f"{n} preguntas de [data/support-eval.jsonl](src/support-agent/data/support-eval.jsonl).")
    L.append("")
    L.append("## Qué se compara")
    L.append("")
    L.append("| | Agente optimizado (actual) | Modelo fine-tuned |")
    L.append("|---|---|---|")
    L.append(f"| Deployment | `{args.opt_model}` | `{args.ft_model}` |")
    L.append("| Modelo | gpt-4.1-mini (base, \"inferior\") | gpt-4o-2024-08-06 fine-tuneado |")
    L.append("| System prompt | largo (instrucciones optimizadas) | corto |")
    L.append("| Herramienta `lookup_policy` | sí | no (conocimiento en los pesos) |")
    L.append("| Llamadas al modelo por pregunta | **2** (decidir tool + responder) | **1** |")
    L.append("")
    L.append("## Tokens y latencia (media por pregunta)")
    L.append("")
    L.append("| Métrica | Optimizado | Fine-tuned | Δ |")
    L.append("|---|:--:|:--:|:--:|")
    L.append(f"| Tokens input | {opt_in} | {ft_in} | {pct(ft_in, opt_in)} |")
    L.append(f"| Tokens output | {opt_out} | {ft_out} | {pct(ft_out, opt_out)} |")
    L.append(f"| Tokens total | {opt_tot} | {ft_tot} | {pct(ft_tot, opt_tot)} |")
    L.append(f"| Latencia (s) | {opt_sec} | {ft_sec} | {pct(ft_sec, opt_sec)} |")
    L.append("")
    L.append("## Coste estimado")
    L.append("")
    L.append("Precios de lista usados (USD / 1M tokens; editables con flags `--*-price-*`):")
    L.append("")
    L.append("| Modelo | Input | Output |")
    L.append("|---|--:|--:|")
    L.append(f"| `{args.opt_model}` | ${args.opt_price_in} | ${args.opt_price_out} |")
    L.append(f"| `{args.ft_model}` (fine-tuned) | ${args.ft_price_in} | ${args.ft_price_out} |")
    L.append("")
    L.append("| Coste por 1.000 peticiones | Optimizado | Fine-tuned | Δ |")
    L.append("|---|:--:|:--:|:--:|")
    L.append(f"| Solo tokens (USD) | ${opt_cost_1k} | ${ft_cost_1k} | {pct(ft_cost_1k, opt_cost_1k)} |")
    L.append("")
    L.append(f"> ⚠️ El deployment fine-tuned **también factura hosting ~${args.ft_hosting_per_hour}/hora** "
             "esté o no en uso (SKU Standard regional), mientras que `gpt-4.1-mini` GlobalStandard "
             "es pago por uso puro. A bajo volumen el hosting domina el coste del fine-tuned; "
             "a alto volumen pesan más los tokens.")
    L.append("")
    L.append("### Lectura")
    L.append("")
    cheaper = "fine-tuned" if ft_cost_1k < opt_cost_1k else "optimizado"
    faster = "fine-tuned" if ft_sec < opt_sec else "optimizado"
    L.append(f"- **Tokens:** el fine-tuned usa menos tokens por pregunta "
             f"({ft_tot} vs {opt_tot}) porque no carga el prompt largo ni hace la doble llamada del tool.")
    L.append(f"- **Latencia:** el más rápido es **{faster}** "
             f"({min(opt_sec, ft_sec)} s vs {max(opt_sec, ft_sec)} s de media).")
    L.append(f"- **Coste por token:** el más barato en tokens es **{cheaper}**. "
             "Aun así, el precio por token del gpt-4o fine-tuned es mayor que el de gpt-4.1-mini, "
             "así que el ahorro en número de tokens puede no compensar el mayor precio unitario + hosting.")
    L.append("")
    L.append("## Detalle por pregunta")
    L.append("")
    L.append("| # | Pregunta | Opt in | Opt out | Opt s | FT in | FT out | FT s |")
    L.append("|--:|---|--:|--:|--:|--:|--:|--:|")
    for i, r in enumerate(results, 1):
        o, f = r["opt"], r["ft"]
        L.append(f"| {i} | {r['query']} | {o['prompt']} | {o['completion']} | {o['seconds']} "
                 f"| {f['prompt']} | {f['completion']} | {f['seconds']} |")
    L.append("")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
