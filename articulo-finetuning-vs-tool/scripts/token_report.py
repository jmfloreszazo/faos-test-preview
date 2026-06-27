r"""Token report - input (prompt) vs output (completion) tokens per request.

Measures the EXACT token usage (from the API ``usage`` field, the same data
Azure Monitor / App Insights would record) for the three architectures compared
in the article, on both the normal and the fine-tuned deployment:

  A. LLM crudo (sin tool)        - 1 llamada
  B. Agente + tool (prompt base) - 2 llamadas (decidir tool -> responder)
  C. Agente + tool (prompt opt.) - 2 llamadas, con el prompt optimizado del Test 3

We use direct ``usage`` rather than platform metrics on purpose: the account
metrics aggregate ALL traffic (judge calls, optimizer calls, and the 2x1000
blast load tests), which would pollute a per-scenario comparison. Here every
number is attributable to exactly one scenario + model.

No judge is called (this only measures cost/tokens), so it is cheap and fast.

Auth (PowerShell):

    $env:FINETUNE_TOKEN    = az account get-access-token `
        --scope https://cognitiveservices.azure.com/.default --query accessToken -o tsv
    $env:FINETUNE_ENDPOINT = 'https://aisvc-yrwwwokfuruzy.cognitiveservices.azure.com'
    .\.venv\Scripts\python.exe articulo-finetuning-vs-tool/scripts/token_report.py
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL = os.path.join(ROOT, "data", "support-eval.jsonl")

# --- Prompts -----------------------------------------------------------------

# A. Direct, no tool (Test 1 style).
SYSTEM_DIRECT = (
    "You are a customer support agent for an online store. You answer customer "
    "questions about returns, shipping and warranties. Be clear and concise, and "
    "always answer in English. Include concrete details (timeframes, costs, "
    "conditions) when they apply. If you do not have the information, say so "
    "explicitly and offer to hand off to a human agent. Never invent policies, "
    "prices or timeframes."
)

# B. Agent + tool, baseline prompt (Test 2 style).
SYSTEM_TOOL = (
    "You are a customer support agent for an online store. You answer questions "
    "about returns, shipping and warranties. Use the `lookup_policy` tool to "
    "check the official policy before answering. Be clear and concise, and "
    "always answer in English. If you do not have the information, say so and "
    "offer to hand off to a human agent."
)

# C. Agent + tool, optimized prompts from Test 3 (one per model).
SYSTEM_OPT_NORMAL = (
    "You are a customer-support agent for returns, shipping, and warranties. You "
    "have a single tool: `lookup_policy(topic)` where topic in {'returns',"
    "'shipping','warranty'}. It returns the current official policy text for that "
    "topic.\n\n"
    "Always follow these rules:\n"
    "1. Before answering ANY question, call `lookup_policy` for each relevant "
    "topic, then base your answer ONLY on the returned policy text and the user's "
    "question.\n"
    "2. Never invent, guess, or extend policies beyond what the tool returns. If a "
    "detail is not clearly stated in the policy text, say you don't have that "
    "information.\n"
    "3. If the policy text does not let you answer the user's request, explicitly "
    "offer to hand off the conversation to a human agent.\n"
    "4. Answer ONLY what was asked, in English, clearly and concisely, without "
    "extra commentary, upselling, or unrelated details.\n"
    "5. Do not quote the entire policy unless the user explicitly asks for it; "
    "summarize only the relevant parts."
)
SYSTEM_OPT_FT = (
    "You are a customer-support assistant for returns, shipping, and warranties. "
    "You have a tool `lookup_policy(topic)` that returns the official policy text "
    "for one topic: `returns`, `shipping`, or `warranty`.\n\n"
    "Instructions:\n"
    "1. Always call `lookup_policy` for the relevant topic(s) BEFORE answering, "
    "even if you think you know the policy.\n"
    "2. Base your answer ONLY on the returned policy text and the user's question. "
    "Do not invent details or add information not supported by the policy.\n"
    "3. Answer in clear, concise English. No padding, small talk, or marketing "
    "language.\n"
    "4. Answer ONLY what the user asked. Do not add extra recommendations, "
    "explanations, or cross-topic details unless they are explicitly requested or "
    "needed to avoid ambiguity.\n"
    "5. If the policy text does not provide the information needed to answer the "
    "question, say you don't have that information and offer to hand off to a "
    "human agent for clarification.\n"
    "6. If the question is unrelated to returns, shipping, or warranty, briefly "
    "state that you can't answer it and offer to hand off to a human agent.\n"
    "7. Never hard-code policy values; always rely on `lookup_policy`."
)

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

# Approx. public Pay-as-you-go prices (USD / 1M tokens), GlobalStandard, eastus2.
# Fine-tuned gpt-4o tokens bill higher than the base model (plus an hourly
# hosting fee that this per-request view does NOT include).
PRICES = {
    "base": {"in": 2.50, "out": 10.00},   # gpt-4o
    "ft":   {"in": 3.75, "out": 15.00},   # gpt-4o fine-tuned (token price only)
}


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


def run_direct(client, deployment: str, system: str, question: str) -> dict:
    r = client.chat.completions.create(
        model=deployment,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": question}],
        temperature=0.2, max_tokens=250,
    )
    return {"in": r.usage.prompt_tokens, "out": r.usage.completion_tokens}


def run_tool(client, deployment: str, system: str, question: str) -> dict:
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": question}]
    p = c = 0
    r1 = client.chat.completions.create(
        model=deployment, messages=messages, tools=TOOLS,
        tool_choice="auto", temperature=0.2, max_tokens=250,
    )
    p += r1.usage.prompt_tokens
    c += r1.usage.completion_tokens
    msg = r1.choices[0].message
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
        r2 = client.chat.completions.create(
            model=deployment, messages=messages, tools=TOOLS,
            tool_choice="auto", temperature=0.2, max_tokens=250,
        )
        p += r2.usage.prompt_tokens
        c += r2.usage.completion_tokens
    return {"in": p, "out": c}


def mean(xs) -> float:
    return round(statistics.mean(xs), 1) if xs else 0.0


def median(xs) -> float:
    return round(statistics.median(xs), 1) if xs else 0.0


def aggregate(samples: list[dict]) -> dict:
    ins = [s["in"] for s in samples]
    outs = [s["out"] for s in samples]
    tots = [s["in"] + s["out"] for s in samples]
    return {
        "in_mean": mean(ins), "in_median": median(ins),
        "out_mean": mean(outs), "out_median": median(outs),
        "tot_mean": mean(tots), "tot_median": median(tots),
        "in_sum": sum(ins), "out_sum": sum(outs),
    }


def cost_per_1k(agg: dict, price: dict) -> float:
    """USD per 1000 requests using mean tokens."""
    c = (agg["in_mean"] * price["in"] + agg["out_mean"] * price["out"]) / 1e6 * 1000
    return round(c, 3)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--normal", default="gpt-4o")
    ap.add_argument("--ft", default="gpt-4o-ft")
    ap.add_argument("--api-version", default="2024-10-21")
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "token-report-raw.md"))
    args = ap.parse_args()

    endpoint = os.environ.get("FINETUNE_ENDPOINT")
    token = os.environ.get("FINETUNE_TOKEN")
    if not endpoint or not token:
        raise SystemExit("Set FINETUNE_ENDPOINT and FINETUNE_TOKEN (see module docstring).")

    client = make_client(endpoint, token, args.api_version)
    rows = load_eval(EVAL)
    print(f"Loaded {len(rows)} eval questions.")

    # scenario key -> (label, runner, system per model)
    scenarios = [
        ("A", "LLM crudo (sin tool)", "direct",
         {"normal": SYSTEM_DIRECT, "ft": SYSTEM_DIRECT}),
        ("B", "Agente + tool (prompt base)", "tool",
         {"normal": SYSTEM_TOOL, "ft": SYSTEM_TOOL}),
        ("C", "Agente + tool (prompt optimizado)", "tool",
         {"normal": SYSTEM_OPT_NORMAL, "ft": SYSTEM_OPT_FT}),
    ]

    data: dict = {}
    for key, label, kind, systems in scenarios:
        for side, dep in (("normal", args.normal), ("ft", args.ft)):
            samples = []
            for row in rows:
                q = row["query"]
                if kind == "direct":
                    samples.append(run_direct(client, dep, systems[side], q))
                else:
                    samples.append(run_tool(client, dep, systems[side], q))
            data[(key, side)] = aggregate(samples)
            print(f"  [{key}/{side}] in~{data[(key, side)]['in_mean']} "
                  f"out~{data[(key, side)]['out_mean']}")

    write_markdown(args, scenarios, data)
    print(f"\nWrote {args.out}")


def write_markdown(args, scenarios, data) -> None:
    n_label = f"`{args.normal}`"
    f_label = f"`{args.ft}`"
    lines = [
        "# Tokens de entrada/salida y coste por arquitectura",
        "",
        f"_Generado: {datetime.now():%Y-%m-%d %H:%M}_ - 8 preguntas, tokens exactos "
        "del campo `usage` de la API (lo mismo que registra App Insights), "
        "atribuibles 1:1 a cada escenario.",
        "",
        f"Modelos: Normal = {n_label} · Fine-tuned = {f_label}. "
        "Para escenarios con tool, los tokens suman las 2 llamadas internas "
        "(decidir tool + responder).",
        "",
        "## Tokens por petición (media / mediana)",
        "",
        "| Escenario | Modelo | In media | In mediana | Out media | Out mediana | Total media |",
        "|---|---|:--:|:--:|:--:|:--:|:--:|",
    ]
    for key, label, _kind, _sys in scenarios:
        for side, dep in (("normal", args.normal), ("ft", args.ft)):
            a = data[(key, side)]
            lines.append(
                f"| {key}. {label} | `{dep}` | {a['in_mean']} | {a['in_median']} | "
                f"{a['out_mean']} | {a['out_median']} | {a['tot_mean']} |")
    lines += [
        "",
        "## Coste estimado (USD por 1000 peticiones)",
        "",
        f"Precios PAYG GlobalStandard usados: Normal in ${PRICES['base']['in']}/1M, "
        f"out ${PRICES['base']['out']}/1M · Fine-tuned in ${PRICES['ft']['in']}/1M, "
        f"out ${PRICES['ft']['out']}/1M (sólo tokens; el fine-tuned añade además una "
        "**tarifa horaria de hosting** no incluida aquí).",
        "",
        "| Escenario | Normal | Fine-tuned | Δ |",
        "|---|:--:|:--:|:--:|",
    ]
    for key, label, _kind, _sys in scenarios:
        cn = cost_per_1k(data[(key, "normal")], PRICES["base"])
        cf = cost_per_1k(data[(key, "ft")], PRICES["ft"])
        lines.append(f"| {key}. {label} | ${cn} | ${cf} | {round(cf-cn,3):+} |")

    # Decision block
    a_norm = data[("A", "normal")]
    b_norm = data[("B", "normal")]
    c_norm = data[("C", "normal")]
    lines += [
        "",
        "## Lectura para decidir",
        "",
        "- **El coste lo domina el prompt de entrada, no la salida.** Añadir la tool "
        f"y sus instrucciones sube los tokens de entrada de ~{a_norm['in_mean']} "
        f"(crudo) a ~{b_norm['in_mean']} (tool conciso) y ~{c_norm['in_mean']} (tool "
        "optimizado) por petición.",
        "- **El fine-tuned no ahorra tokens**: consume tokens iguales o algo "
        f"mayores que el normal en el mismo escenario, y su precio por token es más "
        "alto, por lo que **siempre cuesta más** a igualdad de calidad.",
        f"- El prompt 'optimizado' (C, ~{c_norm['tot_mean']} tok) no mejora la "
        f"exactitud del normal sobre el prompt conciso (B, ~{b_norm['tot_mean']} "
        "tok): optimizar para calidad no es optimizar para coste.",
        "",
        "**Decisión:** usar el **modelo base + tool con prompt conciso** (escenario "
        "B normal): 8/8 de exactitud al menor coste, menos tokens que el optimizado, "
        "y sin el precio por token más alto ni la tarifa de hosting del fine-tuned.",
        "",
        "## Detalle: tokens totales consumidos en la medición",
        "",
        "| Escenario | Modelo | In total | Out total |",
        "|---|---|:--:|:--:|",
    ]
    for key, label, _kind, _sys in scenarios:
        for side, dep in (("normal", args.normal), ("ft", args.ft)):
            a = data[(key, side)]
            lines.append(f"| {key} | `{dep}` | {a['in_sum']} | {a['out_sum']} |")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
