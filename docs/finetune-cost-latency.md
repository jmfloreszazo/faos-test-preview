# Comparativa de coste y latencia: agente optimizado vs fine-tuned

_Generado: 2026-06-26 18:10_ — 8 preguntas de [data/support-eval.jsonl](src/support-agent/data/support-eval.jsonl).

## Qué se compara

| | Agente optimizado (actual) | Modelo fine-tuned |
|---|---|---|
| Deployment | `gpt-4.1-mini` | `support-sft-ft` |
| Modelo | gpt-4.1-mini (base, "inferior") | gpt-4o-2024-08-06 fine-tuneado |
| System prompt | largo (instrucciones optimizadas) | corto |
| Herramienta `lookup_policy` | sí | no (conocimiento en los pesos) |
| Llamadas al modelo por pregunta | **2** (decidir tool + responder) | **1** |

## Tokens y latencia (media por pregunta)

| Métrica | Optimizado | Fine-tuned | Δ |
|---|:--:|:--:|:--:|
| Tokens input | 2807.75 | 98.75 | -96.5% |
| Tokens output | 64.38 | 45.25 | -29.7% |
| Tokens total | 2872.12 | 144 | -95.0% |
| Latencia (s) | 2.52 | 1.17 | -53.6% |

## Coste estimado

Precios de lista usados (USD / 1M tokens; editables con flags `--*-price-*`):

| Modelo | Input | Output |
|---|--:|--:|
| `gpt-4.1-mini` | $0.4 | $1.6 |
| `support-sft-ft` (fine-tuned) | $3.75 | $15.0 |

| Coste por 1.000 peticiones | Optimizado | Fine-tuned | Δ |
|---|:--:|:--:|:--:|
| Solo tokens (USD) | $1.226 | $1.049 | -14.4% |

> ⚠️ El deployment fine-tuned **también factura hosting ~$1.7/hora** esté o no en uso (SKU Standard regional), mientras que `gpt-4.1-mini` GlobalStandard es pago por uso puro. A bajo volumen el hosting domina el coste del fine-tuned; a alto volumen pesan más los tokens.

### Lectura

- **Tokens:** el fine-tuned usa menos tokens por pregunta (144 vs 2872.12) porque no carga el prompt largo ni hace la doble llamada del tool.
- **Latencia:** el más rápido es **fine-tuned** (1.17 s vs 2.52 s de media).
- **Coste por token:** el más barato en tokens es **fine-tuned**. Aun así, el precio por token del gpt-4o fine-tuned es mayor que el de gpt-4.1-mini, así que el ahorro en número de tokens puede no compensar el mayor precio unitario + hosting.

## Detalle por pregunta

| # | Pregunta | Opt in | Opt out | Opt s | FT in | FT out | FT s |
|--:|---|--:|--:|--:|--:|--:|--:|
| 1 | How many days do I have to return a product? | 2806 | 48 | 3.188 | 100 | 32 | 0.935 |
| 2 | How long does standard shipping take? | 2809 | 56 | 3.257 | 96 | 40 | 1.069 |
| 3 | Does express shipping have an extra cost? | 2811 | 57 | 2.262 | 97 | 38 | 1.268 |
| 4 | What warranty do the products have? | 2793 | 72 | 2.293 | 96 | 32 | 1.162 |
| 5 | I want to return something but I don't have the receipt, can I? | 2814 | 76 | 2.012 | 104 | 65 | 1.343 |
| 6 | Do you ship internationally? | 2805 | 83 | 2.44 | 94 | 69 | 1.381 |
| 7 | My product broke after 6 months, is it covered? | 2803 | 71 | 2.362 | 101 | 50 | 1.165 |
| 8 | How much does express shipping cost and how long does it take? | 2821 | 52 | 2.351 | 102 | 36 | 1.038 |

