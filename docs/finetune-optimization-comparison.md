# Comparativa de optimización: modelo base vs fine-tuned (los 3 casos)

_Generado: 2026-06-26_ — 8 preguntas de [support-eval.jsonl](../src/support-agent/data/support-eval.jsonl), evaluadores `relevance` + `task_adherence` (escala 0–1) ejecutados por el Foundry Agent Optimizer.

## Los escenarios

| # | Escenario | Modelo / deployment | Prompt | Tool `lookup_policy` | Llamadas |
|---|---|---|---|:--:|:--:|
| 0 | Base **sin optimizar** | `gpt-4.1-mini` | genérico (8 líneas) | sí | 2 |
| 1 | **Base optimizado** (producción actual) | `gpt-4.1-mini` | optimizado (~900 tok) | sí | 2 |
| 2 | Fine-tuned **sin optimizar** | `support-sft-ft` | genérico (8 líneas) | no | 1 |
| 3 | **Fine-tuned optimizado** (caso extremo) | `support-sft-ft` | optimizado (84 líneas) | no | 1 |

## Resultados de calidad (score del optimizer)

| Escenario | Score | Δ vs su baseline | Candidato |
|---|:--:|:--:|---|
| 0 · base sin optimizar | 0.78 | — | baseline |
| 1 · **base optimizado** | **0.98** | **+0.20** | `cand_1465ed93e173446195e3b81bb2a399e5` |
| 2 · fine-tuned sin optimizar | 0.94 | — | baseline |
| 3 · **fine-tuned optimizado** | **0.95** | +0.01 | `cand_b7295a7d22c648f7bd457b0603fa6cf5` |

Fuente: [optimize-runs/summary.csv](../optimize-runs/summary.csv) (run 1, base) y [optimize-runs/ft-optimize-notool-2.log](../optimize-runs/ft-optimize-notool-2.log) (fine-tuned).

## ¿Llegamos al 100%?

**No exactamente, pero muy cerca.** El techo práctico de este set es ~0.95–0.98:

- El mejor resultado es **0.98** (base optimizado), no 1.00.
- El fine-tuned se queda en **0.95** tras optimizar.
- El 2–5% que falta no es "error" real: viene de que el evaluador `relevance` penaliza variaciones de redacción y de que la pregunta de envío internacional es deliberadamente ambigua (la respuesta correcta es derivar a un humano, lo que el juez no siempre puntúa como 5/5).

Para acercarse más al 100% habría que (a) ampliar el dataset de evaluación, (b) subir `max_iterations`, o (c) relajar/ajustar los evaluadores — con rendimientos decrecientes.

## La conclusión importante

**El fine-tuning casi elimina la necesidad de ingeniería de prompts.**

- El modelo fine-tuned **sin optimizar** (prompt genérico de 8 líneas, sin tool) ya saca **0.94** — casi igual que el `gpt-4.1-mini` fuertemente optimizado (0.98) y muy por encima del `gpt-4.1-mini` sin optimizar (0.78).
- Optimizar el fine-tuned solo lo sube de 0.94 → 0.95: el conocimiento ya está "horneado" en los pesos, así que el prompt aporta poco.
- En el modelo base, en cambio, la optimización es **crítica**: pasa de 0.78 → 0.98 (+0.20). Sin el prompt largo + tool, el modelo no conoce las políticas.

```
gpt-4.1-mini :  0.78 ──(optimización +0.20)──► 0.98   ← el prompt hace casi todo el trabajo
fine-tuned   :  0.94 ──(optimización +0.01)──► 0.95   ← los pesos ya hacen el trabajo
```

## Qué generó el optimizer para el fine-tuned

El candidato ganador ([instructions.md](../src/support-agent/.agent_configs/cand_b7295a7d22c648f7bd457b0603fa6cf5/instructions.md), 84 líneas) básicamente **re-inyecta las políticas como conocimiento por defecto** en el prompt (envío estándar 3–5 días, exprés $9.99 / 24–48 h, no inventar envío internacional → derivar a humano). Es decir, el optimizer compensa los pocos casos límite repitiendo en el prompt lo que el fine-tuning ya sabe — de ahí la mejora marginal.

## Coste y velocidad

Para el detalle de tokens, latencia y coste por petición, ver [finetune-cost-latency.md](finetune-cost-latency.md). Resumen:

| | Base optimizado (caso 1) | Fine-tuned (casos 2–3) |
|---|:--:|:--:|
| Tokens/pregunta | ~2872 | ~144 |
| Latencia | 2.52 s | 1.17 s |
| Calidad | 0.98 | 0.95 |

**Lectura final:** el fine-tuned da el ~97% de la calidad del base optimizado con **20× menos tokens** y **la mitad de latencia**. La contrapartida es el **hosting del deployment fine-tuned (~$1.70/h)** y el mayor precio por token de gpt-4o; a alto volumen compensa, a bajo volumen no.

## Notas de reproducción

- Config de optimización del fine-tuned: [src/support-agent/eval-ft.yaml](../src/support-agent/eval-ft.yaml) (usa baseline sin tool [.agent_configs/baseline-ft](../src/support-agent/.agent_configs/baseline-ft)).
- El deployment `support-sft-ft` se escaló de 1 → **50K TPM** para que el optimizer no sufriera throttling (con 1K TPM las respuestas concurrentes volvían vacías y el optimizer fallaba con `Response string cannot be empty`).
- `agent.yaml` quedó apuntando al candidato fine-tuned optimizado (`OPTIMIZATION_CANDIDATE_ID=cand_b7295a7d22c648f7bd457b0603fa6cf5`).
