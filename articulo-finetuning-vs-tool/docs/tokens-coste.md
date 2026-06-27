# Tokens de entrada/salida, coste y valor por arquitectura

_Generado: 2026-06-27 — 8 preguntas del set de evaluación. Tokens **exactos** del
campo `usage` de la API (lo mismo que registra Application Insights), atribuibles
1:1 a cada escenario. Sin contaminación de las llamadas del juez/optimizador ni
de los blast tests de carga._

Modelos: **Normal** = `gpt-4o` · **Fine-tuned** = `gpt-4o-ft`. En los escenarios
con tool, los tokens suman las **2 llamadas internas** (decidir tool + responder).

| Escenario | Descripción | Llamadas |
|---|---|:--:|
| **A** | LLM crudo, sin tool | 1 |
| **B** | Agente + tool `lookup_policy`, prompt conciso | 2 |
| **C** | Agente + tool, prompt "optimizado" (Test 3) | 2 |

---

## 1. Tokens por petición (media / mediana)

| Escenario | Modelo | In media | In mediana | Out media | Out mediana | **Total media** |
|---|---|:--:|:--:|:--:|:--:|:--:|
| A. LLM crudo | `gpt-4o` | 98.8 | 98.5 | 74.1 | 70.0 | **172.9** |
| A. LLM crudo | `gpt-4o-ft` | 98.8 | 98.5 | 48.1 | 39.5 | **146.9** |
| B. Tool (prompt conciso) | `gpt-4o` | 313.8 | 313.5 | 40.0 | 35.5 | **353.8** |
| B. Tool (prompt conciso) | `gpt-4o-ft` | 313.8 | 313.5 | 61.6 | 56.5 | **375.4** |
| C. Tool (prompt optimizado) | `gpt-4o` | 573.8 | 573.5 | 40.1 | 36.5 | **613.9** |
| C. Tool (prompt optimizado) | `gpt-4o-ft` | 647.8 | 647.5 | 44.2 | 42.0 | **692.0** |

**Observaciones sobre los tokens:**
- **El coste lo domina la ENTRADA, no la salida.** El prompt + esquema de la tool
  + el texto de la política inflan el input: ~99 (crudo) → ~314 (tool conciso) →
  ~574-648 (tool optimizado). La salida casi no se mueve (~40-74).
- **El fine-tuned responde más corto** en crudo (out 48 vs 74): aprendió
  respuestas escuetas. Pero ese ahorro de salida es pequeño frente al peso del
  input y su precio por token más alto.
- **El prompt "optimizado" (C) consume ~70-90 % más input que el conciso (B)** sin
  mejorar la exactitud (ver §3): optimizar *para calidad* no es optimizar *para
  coste*.

---

## 2. Coste estimado (USD por 1.000 peticiones)

Precios PAYG GlobalStandard (eastus2): Normal in **$2.50**/1M, out **$10.00**/1M ·
Fine-tuned in **$3.75**/1M, out **$15.00**/1M. _Sólo tokens; el fine-tuned añade
además una **tarifa horaria de hosting** del modelo afinado, no incluida aquí, que
se paga **aunque no haya tráfico**._

| Escenario | Normal | Fine-tuned | Δ (FT − Normal) |
|---|:--:|:--:|:--:|
| A. LLM crudo | $0.988 | $1.092 | +0.104 |
| B. Tool (prompt conciso) | **$1.185** | $2.101 | +0.916 |
| C. Tool (prompt optimizado) | $1.835 | $3.092 | +1.257 |

---

## 3. Calidad vs coste — la tabla de decisión

Calidad global = media de relevancia y adherencia (1-5) y nº de respuestas
correctas (rel ≥ 4) de los Tests 1/2/3 ([RESUMEN-final.md](RESUMEN-final.md)).

| Escenario · Modelo | Calidad (1-5) | Correctas | Total tok | $/1k | Veredicto |
|---|:--:|:--:|:--:|:--:|---|
| A · Normal | 2.56 | 0/8 | 172.9 | $0.988 | ❌ Barato pero inventa políticas |
| A · Fine-tuned | 4.44 | 6/8 | 146.9 | $1.092 | ✅ Mejor opción **sin** tool |
| **B · Normal** | **5.00** | **8/8** | **353.8** | **$1.185** | ⭐ **Mejor valor global** |
| B · Fine-tuned | 4.38 | 6/8 | 375.4 | $2.101 | ❌ Peor calidad y ~2× coste |
| C · Normal | 5.00 | 8/8 | 613.9 | $1.835 | ➖ 8/8 pero +55 % coste vs B |
| C · Fine-tuned | 5.00 | 8/8 | 692.0 | $3.092 | ❌ Máxima calidad, máximo coste |

**Lecturas clave:**
- **El ganador es `gpt-4o` + tool con prompt conciso (B · Normal): 8/8 al menor
  coste de todas las opciones de máxima calidad.**
- El prompt "optimizado" (C) **no mejora** la exactitud del modelo normal sobre el
  prompt conciso (B), y sólo añade tokens de entrada → más caro por el mismo 8/8.
- El **fine-tuning no compensa cuando hay tool**: misma o peor calidad, más
  tokens, precio por token más alto y, encima, tarifa de hosting fija.
- El fine-tuning **sólo gana en el escenario sin tool** (A): si por algún motivo
  no puedes añadir una tool/RAG, `gpt-4o-ft` es la vía más barata a buena calidad.

---

## 4. Proyección de coste mensual (sólo tokens)

Coste de tokens según volumen, para las cuatro opciones con calidad aceptable:

| Opción | 10k req/mes | 100k req/mes | 1M req/mes |
|---|:--:|:--:|:--:|
| A · FT (sin tool) | $10.9 | $109 | $1.092 |
| **B · Normal (tool conciso)** | **$11.9** | **$119** | **$1.185** |
| C · Normal (tool optimizado) | $18.4 | $184 | $1.835 |
| C · FT (tool optimizado) | $30.9 | $309 | $3.092 |

> ⚠️ Las filas de fine-tuned (`gpt-4o-ft`) suman además la **tarifa horaria de
> hosting** del modelo afinado, constante e independiente del tráfico. A volumen
> bajo/medio esa cuota fija suele **dominar** el coste y agranda aún más la
> diferencia frente al modelo base.

---

## 5. Detalle: tokens totales consumidos en la medición (8 preguntas)

| Escenario | Modelo | In total | Out total |
|---|---|:--:|:--:|
| A | `gpt-4o` | 790 | 593 |
| A | `gpt-4o-ft` | 790 | 385 |
| B | `gpt-4o` | 2.510 | 320 |
| B | `gpt-4o-ft` | 2.510 | 493 |
| C | `gpt-4o` | 4.590 | 321 |
| C | `gpt-4o-ft` | 5.182 | 354 |

---

## Cómo reproducir

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:FINETUNE_TOKEN    = az account get-access-token --scope "https://cognitiveservices.azure.com/.default" --query accessToken -o tsv
$env:FINETUNE_ENDPOINT = "https://aisvc-yrwwwokfuruzy.cognitiveservices.azure.com"
.\.venv\Scripts\python.exe articulo-finetuning-vs-tool/scripts/token_report.py --normal gpt-4o --ft gpt-4o-ft
```

> Los tokens se leen del campo `usage` de cada respuesta de la API. Se eligió esta
> fuente en vez de las métricas de plataforma (`InputTokens`/`OutputTokens` de
> Azure Monitor) porque éstas **agregan todo el tráfico de la cuenta** (juez,
> optimizador y los blast tests de 1.000 llamadas), lo que impediría atribuir el
> consumo a cada escenario. El `usage` da la cifra exacta por petición.
