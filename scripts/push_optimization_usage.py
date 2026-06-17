"""Capture the token usage of an Agent Optimizer run and push it to Application Insights.

Why this exists
---------------
The optimization runs in a Foundry-managed control-plane job, so it does NOT flow through
your hosted-agent container and therefore produces NO OpenTelemetry traces in Application
Insights (unlike runtime invocations). The token consumption, however, IS measured by Azure
Monitor platform metrics on the AI Services account, broken down per model deployment.

This script:
  1. Reads the per-deployment token counts (ProcessedPromptTokens / GeneratedTokens) from
     Azure Monitor for the time window of an optimization job.
  2. Computes an estimated cost using configurable per-1M-token prices.
  3. Emits a tagged ``customEvent`` named ``AgentOptimizationUsage`` to Application Insights,
     so you can query and do cost math later with KQL (see the README).

Because in this demo the ``gpt-5.1`` deployment is used ONLY by the optimizer (the "writer"),
its token total is 100% attributable to optimization. ``gpt-4.1-mini`` is the evaluator
("judge") that scores the dataset many times.

Usage
-----
    python scripts/push_optimization_usage.py \
        --job-id opt_xxx \
        --start 2026-06-17T12:28:00Z \
        --end   2026-06-17T12:45:00Z \
        --best-score 0.80

Auth: uses DefaultAzureCredential (az login). Reads APPLICATIONINSIGHTS_CONNECTION_STRING,
AZURE_SUBSCRIPTION_ID, and the AI Services account/resource-group from the environment or CLI.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys

from azure.monitor.opentelemetry import configure_azure_monitor
from azure.monitor.events.extension import track_event

# --- Per-1M-token prices (USD). EDIT to match your contract / region list price. --------
# These are placeholders so the cost column is non-zero; override with --price-* flags.
DEFAULT_PRICES = {
    # deployment-name: (input_per_1M, output_per_1M)
    "gpt-5.1": (1.25, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
}

OPTIMIZER_DEPLOYMENT = "gpt-5.1"      # the "writer" — exclusive to optimization
EVAL_DEPLOYMENT = "gpt-4.1-mini"      # the "judge" — runs the dataset


def _parse_iso(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def _sum_tokens_by_deployment(resource_id, start_iso, end_iso):
    """Return {deployment: {"prompt": int, "generated": int}} for the window.

    Uses the Azure CLI (``az monitor metrics list``) to read the per-deployment token
    counters. The CLI is used instead of the SDK because it is stable across SDK major
    versions and is already authenticated via ``az login``.
    """
    cmd = [
        "az", "monitor", "metrics", "list",
        "--resource", resource_id,
        "--metric", "ProcessedPromptTokens", "GeneratedTokens",
        "--start-time", start_iso,
        "--end-time", end_iso,
        "--interval", "PT1M",
        "--aggregation", "Total",
        "--filter", "ModelDeploymentName eq '*'",
        "-o", "json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    if result.returncode != 0:
        raise RuntimeError(f"az monitor metrics list failed: {result.stderr.strip()}")
    payload = json.loads(result.stdout)

    totals: dict[str, dict[str, float]] = {}
    for metric in payload.get("value", []):
        key = "prompt" if metric["name"]["value"] == "ProcessedPromptTokens" else "generated"
        for series in metric.get("timeseries", []):
            deployment = "unknown"
            for md in series.get("metadatavalues", []):
                deployment = md["value"]
            bucket = totals.setdefault(deployment, {"prompt": 0.0, "generated": 0.0})
            for point in series.get("data", []):
                if point.get("total"):
                    bucket[key] += point["total"]
    return totals


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True, help="Optimization job id (opt_...). Used as a tag.")
    parser.add_argument("--start", required=True, help="Job window start (ISO8601, e.g. 2026-06-17T12:28:00Z).")
    parser.add_argument("--end", required=True, help="Job window end (ISO8601).")
    parser.add_argument("--best-score", type=float, default=None, help="Best score reported by the job.")
    parser.add_argument("--subscription", default=os.environ.get("AZURE_SUBSCRIPTION_ID"))
    parser.add_argument("--resource-group", default="rg-support-demo-en")
    parser.add_argument("--account", default="aisvc-yrwwwokfuruzy", help="AI Services account name.")
    parser.add_argument("--optimizer-deployment", default=OPTIMIZER_DEPLOYMENT)
    parser.add_argument("--eval-deployment", default=EVAL_DEPLOYMENT)
    parser.add_argument("--connection-string", default=os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"))
    args = parser.parse_args()

    if not args.connection_string:
        print("ERROR: APPLICATIONINSIGHTS_CONNECTION_STRING is not set (env or --connection-string).", file=sys.stderr)
        return 2
    if not args.subscription:
        print("ERROR: subscription is not set (AZURE_SUBSCRIPTION_ID or --subscription).", file=sys.stderr)
        return 2

    resource_id = (
        f"/subscriptions/{args.subscription}/resourceGroups/{args.resource_group}"
        f"/providers/Microsoft.CognitiveServices/accounts/{args.account}"
    )
    totals = _sum_tokens_by_deployment(resource_id, args.start, args.end)

    if not totals:
        print("WARNING: no token metrics found for that window. Nothing to emit.", file=sys.stderr)
        return 1

    # Configure the Application Insights exporter once.
    configure_azure_monitor(connection_string=args.connection_string)

    grand_total_cost = 0.0
    print(f"\nOptimization job {args.job_id}  window {args.start} -> {args.end}")
    print(f"{'deployment':<16}{'role':<11}{'prompt':>10}{'generated':>11}{'cost_usd':>12}")
    print("-" * 60)

    for deployment, counts in sorted(totals.items()):
        prompt = int(counts["prompt"])
        generated = int(counts["generated"])
        price_in, price_out = DEFAULT_PRICES.get(deployment, (0.0, 0.0))
        cost = prompt / 1_000_000 * price_in + generated / 1_000_000 * price_out
        grand_total_cost += cost

        if deployment == args.optimizer_deployment:
            role = "optimizer"
        elif deployment == args.eval_deployment:
            role = "evaluator"
        else:
            role = "other"

        # One tagged customEvent per deployment. Everything lands in customDimensions
        # (numeric values are stored as strings -> use toint()/toreal() in KQL).
        track_event(
            "AgentOptimizationUsage",
            {
                "job_id": args.job_id,
                "deployment": deployment,
                "role": role,
                "purpose": "optimization",
                "window_start": args.start,
                "window_end": args.end,
                "prompt_tokens": str(prompt),
                "generated_tokens": str(generated),
                "total_tokens": str(prompt + generated),
                "est_cost_usd": f"{cost:.6f}",
                "best_score": "" if args.best_score is None else str(args.best_score),
            },
        )
        print(f"{deployment:<16}{role:<11}{prompt:>10}{generated:>11}{cost:>12.4f}")

    print("-" * 60)
    print(f"{'TOTAL':<37}{grand_total_cost:>23.4f} USD")
    print("\nFlushing telemetry to Application Insights...")

    # Ensure the buffered telemetry is exported before the process exits.
    from opentelemetry import trace

    provider = trace.get_tracer_provider()
    if hasattr(provider, "force_flush"):
        provider.force_flush()
    print("Done. Query the customEvents table in ~2-5 min (see README for KQL).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
