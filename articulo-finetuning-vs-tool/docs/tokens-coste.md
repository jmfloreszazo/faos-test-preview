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
Fine-tuned in **$3.75**/1M, out **$15.00**/1M. _Esta tabla es **sólo tokens**; las
cuotas fijas (hosting del fine-tuned y RAG de Azure AI Search) se analizan en los
§4 y §5, que calculan el coste total (TCO)._

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

> ⚠️ **Matiz del Test 4 (prompt-stuffing).** Existe una **tercera estrategia de
> conocimiento** además de "tool/RAG" y "fine-tuning": **incrustar el conocimiento
> directamente en el system prompt**. Cuando optimizamos el prompt del modelo base
> *sin tool* ([test4-llm-crudo-optimizado.md](test4-llm-crudo-optimizado.md)), el
> optimizador metió las políticas reales (30 días, $9.99, garantía 2 años) dentro
> del prompt y el `gpt-4o` base pasó de **0/8 → 8/8**. No "inventó" nada: el
> conocimiento estaba *inline*. Funciona **sólo si el conocimiento es pequeño y
> estable** (cabe en el prompt y casi no cambia). Coste: +tokens de entrada en
> *cada* petición, pero **cero infra fija** (ni hosting FT ni RAG). Si el
> conocimiento es grande o cambia a menudo, esta vía no escala → vuelves a RAG.

---

## 3.5. Latencia (lag) por arquitectura — medición wall-clock

Las métricas de plataforma de latencia (`NormalizedTimeToFirstToken`,
`TokensPerSecond`) **vuelven vacías** en esta cuenta porque las llamadas son
no-streaming. Por eso medimos el **tiempo de pared real por petición** desde el
cliente (lo que percibe el usuario), igual que hicimos con los tokens.

| Escenario · Modelo | Llamadas | 1ª llamada (med, ms) | Total media (ms) | Total mediana (ms) |
|---|:--:|:--:|:--:|:--:|
| A · Normal (sin tool) | 1 | 1.440 | 1.542 | 1.440 |
| A · Fine-tuned (sin tool) | 1 | 1.039 | 1.091 | **1.039** |
| B · Normal (tool conciso) | 2 | 743 | 1.689 | 1.611 |
| B · Fine-tuned (tool conciso) | 2 | 583 | 1.726 | 1.752 |
| C · Normal (tool optimizado) | 2 | 509 | 1.487 | 1.606 |
| C · Fine-tuned (tool optimizado) | 2 | 580 | 1.540 | 1.541 |

**Lecturas clave de latencia:**
- **El nº de llamadas es el factor estructural.** Sin tool = **1 round-trip**; con
  tool/RAG = **2 round-trips secuenciales** (decidir tool → recibir resultado →
  responder). La `1ª llamada` de los escenarios con tool (≈500-740 ms) es sólo el
  *lag* de decidir la tool: el usuario **aún no tiene respuesta** hasta completar
  la 2ª llamada.
- **El fine-tuned sin tool es el más rápido (≈1.039 ms)**: 1 sola llamada y
  respuestas más cortas. Es el único punto donde el FT gana claramente al base.
- **En producción el tool/RAG es aún más lento de lo que se ve aquí**: nuestra
  `lookup_policy` es un diccionario local (~0 ms). Un **Azure AI Search real añade
  la latencia de recuperación** (típicamente +50-300 ms, más si usas semantic
  ranker o agentic retrieval) **encima** de las 2 llamadas al modelo.
- **Resumen de lag:** `1 llamada (FT sin tool / prompt-stuffing)` < `2 llamadas
  (tool, dict local)` < `2 llamadas + recuperación (RAG real)`.

> 💡 **La latencia equilibra la decisión.** Por calidad+coste gana B·Normal
> (base+RAG), pero si tu requisito es **latencia mínima** y el conocimiento es
> pequeño/estable, una sola llamada (FT sin tool, o el prompt-stuffing del Test 4)
> evita el segundo round-trip y la recuperación del RAG.

---

## 4. Coste de infraestructura FIJA — el RAG cuesta dinero, pero el FT cuesta mucho más

El escenario "con tool" no es gratis: en producción ese conocimiento sale de un
**RAG real (Azure AI Search)**, que tiene una **cuota fija mensual** independiente
del tráfico. Pero el fine-tuned también arrastra una cuota fija: el **hosting del
deployment afinado**. Comparando las dos cuotas fijas (precios públicos, eastus2):

| Componente fijo | Para qué arquitectura | Coste fijo / mes |
|---|---|:--:|
| Azure AI Search **Basic** (15 GB, 15 índices) | RAG (B·Normal, C·Normal) | **$73.73** |
| Azure AI Search **Standard S1** (prod, SLA) | RAG (alternativa con SLA) | $245.28 |
| **Hosting fine-tuned** ($1.70/h × 730 h) | FT desplegado (A·FT, B·FT, C·FT) | **≈ $1.241** |
| Embeddings de consulta (`text-embedding-3-small`, $0.022/1M) | RAG | ≈ $0.7 @ 100k consultas (despreciable) |
| Semantic ranker (opcional) | RAG | 1k/mes gratis, luego $1 / 1k consultas |

> 💡 **El RAG cuesta dinero, sí — pero la cuota fija del fine-tuned (~$1.241/mes)
> es ~17× la de un Azure AI Search Basic (~$73.73/mes).** Incluso con S1 de
> producción ($245/mes), el RAG sigue siendo ~5× más barato en coste fijo.
> _(El tier **Developer** de fine-tuning no cobra hosting, pero no tiene SLA y el
> deployment puede eliminarse: válido para dev/pruebas, no para producción.)_

---

## 5. Coste total mensual (TCO = fijo + tokens) por volumen

Sumando la cuota fija de infraestructura (RAG Basic $73.73 / hosting FT $1.241) y
el coste variable de tokens (§2):

| Arquitectura | Fijo/mes | 10k req/mes | 100k req/mes | 1M req/mes |
|---|:--:|:--:|:--:|:--:|
| A · FT sin RAG | $1.241 | $1.252 | $1.350 | $2.333 |
| **B · Normal + RAG (tool conciso)** | **$73.73** | **$85.6** | **$192.2** | **$1.258,7** |
| C · Normal + RAG (tool optimizado) | $73.73 | $92.1 | $257.2 | $1.908,7 |
| C · FT + RAG (lo peor de ambos) | $1.314,7 | $1.345,6 | $1.623,9 | $4.406,7 |

- **`gpt-4o` base + RAG (B·Normal) es el más barato en TODOS los volúmenes**, no
  sólo en tokens: arranca en ~$86/mes a 10k req y sólo iguala al FT-sin-RAG cerca
  de **1M req/mes** (y aún ahí gana: $1.259 vs $2.333).
- El fine-tuned **sin RAG** (A·FT) parecía la salida "barata si no puedes usar
  RAG", pero su **hosting fijo de ~$1.241/mes lo hace caro** desde la primera
  petición: a 10k req cuesta **~15×** más que B·Normal.
- Combinar FT **y** RAG (C·FT) acumula las dos cuotas fijas: la opción más cara.

**Conclusión reforzada:** aunque el RAG no es gratis, su coste fijo es pequeño
frente al hosting del modelo afinado. La arquitectura **base + RAG + prompt
conciso (B·Normal)** gana en calidad (8/8) **y** en coste total a cualquier escala.
El fine-tuning sólo tendría sentido económico sin RAG, a volumen muy alto y
usando el tier Developer (sin SLA) — un nicho muy estrecho.

---

## 6. Detalle: tokens totales consumidos en la medición (8 preguntas)

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
