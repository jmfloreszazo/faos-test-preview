# Comparativa LLM normal vs fine-tuned — Resumen final

_Generado: 2026-06-27 — proyecto `proj-v2`, cuenta `aisvc-yrwwwokfuruzy`, región `eastus2`._

Experimento de reconstrucción limpia para una comparación **justa**: misma base
`gpt-4o` para las dos variantes, y el modelo fine-tuned también aprendió a usar
la tool `lookup_policy`. Sobre el mismo dataset de 8 preguntas
([data/support-eval.jsonl](src/support-agent/data/support-eval.jsonl)) y con el
mismo juez (`gpt-4o`) ejecutamos tres pruebas.

| Modelo | Qué es |
|---|---|
| `gpt-4o` | Base normal (gpt-4o 2024-11-20, GlobalStandard) |
| `gpt-4o-ft` | Fine-tuned desde gpt-4o-2024-08-06 con 1411 ejemplos (706 directos + 705 con tool) |
| `gpt-5.1` | Optimizador del Test 3 |

---

## Test 1 — LLM crudo, sin tool ([test1-llm-crudo.md](docs/test1-llm-crudo.md))

Pregunta directa al modelo, sin acceso a `lookup_policy`. Mide qué sabe el modelo
en sus pesos.

| Métrica | Normal | Fine-tuned | Δ |
|---|:--:|:--:|:--:|
| Relevancia | 1.62 | 4.50 | +2.88 |
| Adherencia | 3.50 | 4.38 | +0.88 |
| Global | 2.56 | 4.44 | **+73%** |
| Correctas (rel≥4) | 0/8 | 6/8 | +6 |

**Conclusión:** sin la tool, el modelo normal se inventa las políticas; el
fine-tuned las tiene memorizadas. Aquí el fine-tuning es decisivo.

---

## Test 2 — Mismo agente con tool `lookup_policy` ([test2-agente.md](docs/test2-agente.md))

Flujo de agente: ambos modelos pueden llamar a la tool, que inyecta la política
correcta. Mide comportamiento de tool-calling, coste y latencia.

| Métrica | Normal | Fine-tuned | Δ |
|---|:--:|:--:|:--:|
| Correctas (rel≥4) | 8/8 | 6/8 | −2 |
| Relevancia | 5.00 | 4.38 | −0.62 |
| Llama a la tool | 8/8 | 8/8 | = |
| Tokens medios | 358 | 375 | +17 |
| Latencia media | 2.01 s | 2.41 s | +0.4 s |

**Conclusión:** con la tool se iguala el terreno. El modelo normal es
ligeramente mejor (más conciso); la verborrea aprendida del fine-tuned penaliza
un poco y consume más tokens y latencia. **Si hay tool, el fine-tuning aporta
poco y hasta resta.**

---

## Test 3 — Optimización del agente ([test3-optimizacion.md](docs/test3-optimizacion.md))

Partiendo del **mismo prompt débil**, `gpt-5.1` reescribe el system prompt
iterativamente (3 iteraciones) para cada modelo. Mide cuánto evoluciona cada uno.

| Modelo | Combinada base | Combinada opt | Δ | Correctas base → opt |
|---|:--:|:--:|:--:|:--:|
| Normal (`gpt-4o`) | 4.31 | 5.00 | +0.69 | 6/8 → 8/8 |
| Fine-tuned (`gpt-4o-ft`) | 4.25 | 5.00 | +0.75 | 6/8 → 8/8 |

**Conclusión:** con la tool disponible, una sola iteración de optimización lleva
a ambos modelos al techo (5.0/5.0, 8/8). La optimización del prompt cierra
rápidamente la diferencia entre normal y fine-tuned.

---

## Coste — tokens de entrada/salida ([tokens-coste.md](tokens-coste.md))

Tokens exactos del campo `usage` de la API (lo mismo que registra App Insights),
medidos por petición en cada arquitectura. El coste lo domina la **entrada**
(prompt + esquema de tool + política), no la salida.

| Escenario · Modelo | Calidad (1-5) | Correctas | Total tok/pet | $/1k pet | Veredicto |
|---|:--:|:--:|:--:|:--:|---|
| A · Normal (sin tool) | 2.56 | 0/8 | 172.9 | $0.988 | ❌ inventa políticas |
| A · Fine-tuned (sin tool) | 4.44 | 6/8 | 146.9 | $1.092 | ✅ mejor opción **sin** tool |
| **B · Normal (tool conciso)** | **5.00** | **8/8** | **353.8** | **$1.185** | ⭐ **mejor valor** |
| B · Fine-tuned (tool) | 4.38 | 6/8 | 375.4 | $2.101 | ❌ peor y ~2× coste |
| C · Normal (tool optimizado) | 5.00 | 8/8 | 613.9 | $1.835 | ➖ 8/8 pero +55 % coste |
| C · Fine-tuned (tool optimizado) | 5.00 | 8/8 | 692.0 | $3.092 | ❌ el más caro |

- El **prompt "optimizado" (C) no mejora** la exactitud del modelo normal sobre el
  prompt-tool conciso (B), y sólo añade tokens de entrada → más caro por el mismo 8/8.
- El **fine-tuned nunca ahorra**: tokens iguales o mayores, precio por token más
  alto y, encima, **tarifa horaria de hosting** fija (se paga sin tráfico).

---

## Lectura global

```
Sin tool   (Test 1):  fine-tuning IMPRESCINDIBLE   (2.56 → 4.44, +73%)
Con tool   (Test 2):  fine-tuning aporta poco/resta (normal 8/8 vs FT 6/8)
Optimizado (Test 3):  ambos llegan al techo         (5.0 / 8-8)
```

- **El conocimiento no se puede "promptear" si no está disponible.** Sin la tool,
  el modelo normal nunca acierta por mucho que mejores el prompt; el fine-tuning
  es la única vía para meter las políticas en el modelo.
- **Si tienes una tool/RAG fiable, el fine-tuning de conocimiento no compensa:**
  añade coste (tokens, latencia) y un estilo más verboso sin mejorar la exactitud.
- **La optimización de prompt es barata y muy efectiva** cuando el modelo tiene
  acceso a la información correcta: lleva a ambos al máximo en una iteración.

**Recomendación:** para este caso de soporte con políticas que cambian, la
arquitectura ganadora es **modelo base `gpt-4o` + tool `lookup_policy` con prompt
conciso (escenario B)**: 8/8 de exactitud al **menor coste** de todas las opciones
de máxima calidad ($1.185/1k), sin tarifa de hosting y sin re-entrenar cuando
cambia una política. El prompt "optimizado" (C) no añade exactitud sobre el
conciso y sólo encarece; el fine-tuned sólo merece la pena si **no** puedes usar
tool/RAG (escenario A).

---

## Reproducibilidad

| Test | Script |
|---|---|
| 1 — LLM crudo | [scripts/compare_models.py](scripts/compare_models.py) |
| 2 — Agente + tool | [scripts/compare_agents_tool.py](scripts/compare_agents_tool.py) |
| 3 — Optimización | [scripts/optimize_compare.py](scripts/optimize_compare.py) |
| Tokens/coste | [scripts/token_report.py](scripts/token_report.py) |

Auth común (PowerShell):

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:FINETUNE_TOKEN    = az account get-access-token --scope "https://cognitiveservices.azure.com/.default" --query accessToken -o tsv
$env:FINETUNE_ENDPOINT = "https://aisvc-yrwwwokfuruzy.cognitiveservices.azure.com"
```
