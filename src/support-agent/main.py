"""Customer support agent — hosted agent in Foundry (responses protocol).

This agent is ready for Agent Optimizer: it reads its configuration
(instructions, model and tool descriptions) from `.agent_configs/baseline/`
through `load_config()`. Thanks to this, the optimizer can try variants
WITHOUT modifying this file.

Hosted Agents preview stack:
  - FoundryChatClient        (agent-framework-foundry)         — bridge to the model
  - Agent                    (agent-framework-core)            — definition + tools
  - ResponsesHostServer      (agent-framework-foundry-hosting) — HTTP host (responses)
"""

import os

from azure.monitor.opentelemetry import configure_azure_monitor
from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from azure.ai.agentserver.optimization import load_config

# Enable Azure Monitor telemetry when the connection string is available.
if os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    configure_azure_monitor()


# --- Tools (function calling) ---------------------------------------------

@tool
def lookup_policy(topic: str) -> str:
    """Return the company policy for a given topic.

    In a real scenario you would query a database or an API. Here we use
    sample data so the example is self-contained.
    """
    policies = {
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
    return policies.get(
        topic.lower().strip(),
        "I don't have information about that topic. Let me hand you over to a human agent.",
    )


def main() -> None:
    # Configuration loaded by the optimizer (or local baseline by default).
    config = load_config()

    project_endpoint = os.environ.get(
        "FOUNDRY_PROJECT_ENDPOINT"
    ) or os.environ["AZURE_AI_PROJECT_ENDPOINT"]

    client = FoundryChatClient(
        project_endpoint=project_endpoint,
        model=config.model or os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    tools = [lookup_policy]

    # Apply the optimized tool descriptions (if any).
    config.apply_tool_descriptions(tools)

    agent = Agent(
        client=client,
        instructions=config.compose_instructions(),
        tools=tools,
        # History is managed by the Hosted Agents platform.
        default_options={"store": False},
    )

    # Exposes POST /responses and GET /readiness for the Foundry runtime.
    ResponsesHostServer(agent).run()


if __name__ == "__main__":
    main()
