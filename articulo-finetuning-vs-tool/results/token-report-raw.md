# Tokens de entrada/salida y coste por arquitectura

_Generado: 2026-06-27 11:57_ - 8 preguntas, tokens exactos del campo `usage` de la API (lo mismo que registra App Insights), atribuibles 1:1 a cada escenario.

Modelos: Normal = `gpt-4o` · Fine-tuned = `gpt-4o-ft`. Para escenarios con tool, los tokens suman las 2 llamadas internas (decidir tool + responder).

## Tokens por petición (media / mediana)

| Escenario | Modelo | In media | In mediana | Out media | Out mediana | Total media |
|---|---|:--:|:--:|:--:|:--:|:--:|
| A. LLM crudo (sin tool) | `gpt-4o` | 98.8 | 98.5 | 76.2 | 70.0 | 175 |
| A. LLM crudo (sin tool) | `gpt-4o-ft` | 98.8 | 98.5 | 47.5 | 44.5 | 146.2 |
| B. Agente + tool (prompt base) | `gpt-4o` | 313.8 | 313.5 | 41.2 | 39.0 | 355 |
| B. Agente + tool (prompt base) | `gpt-4o-ft` | 313.8 | 313.5 | 61.6 | 56.5 | 375.4 |
| C. Agente + tool (prompt optimizado) | `gpt-4o` | 573.8 | 573.5 | 38.8 | 36.5 | 612.5 |
| C. Agente + tool (prompt optimizado) | `gpt-4o-ft` | 647.8 | 647.5 | 50.5 | 51.5 | 698.2 |

## Latencia por petición (wall-clock, ms)

Medida extremo a extremo desde el cliente (lo que percibe el usuario). Las métricas de plataforma (`NormalizedTimeToFirstToken`, `TokensPerSecond`) vuelven vacías en esta cuenta porque las llamadas son no-streaming, así que medimos el tiempo de pared real por petición. En los escenarios con tool, **`1ª llamada`** es el tiempo hasta decidir la tool (el *lag* del primer turno) y **`total`** suma las 2 llamadas (decidir tool + responder).

| Escenario | Modelo | Llamadas | 1ª llamada (med) | Total media | Total mediana |
|---|---|:--:|:--:|:--:|:--:|
| A. LLM crudo (sin tool) | `gpt-4o` | 1 | 1440 | 1542 | 1440 |
| A. LLM crudo (sin tool) | `gpt-4o-ft` | 1 | 1039 | 1091 | 1039 |
| B. Agente + tool (prompt base) | `gpt-4o` | 2 | 743 | 1689 | 1611 |
| B. Agente + tool (prompt base) | `gpt-4o-ft` | 2 | 583 | 1726 | 1752 |
| C. Agente + tool (prompt optimizado) | `gpt-4o` | 2 | 509 | 1487 | 1606 |
| C. Agente + tool (prompt optimizado) | `gpt-4o-ft` | 2 | 580 | 1540 | 1541 |

## Coste estimado (USD por 1000 peticiones)

Precios PAYG GlobalStandard usados: Normal in $2.5/1M, out $10.0/1M · Fine-tuned in $3.75/1M, out $15.0/1M (sólo tokens; el fine-tuned añade además una **tarifa horaria de hosting** no incluida aquí).

| Escenario | Normal | Fine-tuned | Δ |
|---|:--:|:--:|:--:|
| A. LLM crudo (sin tool) | $1.009 | $1.083 | +0.074 |
| B. Agente + tool (prompt base) | $1.197 | $2.101 | +0.904 |
| C. Agente + tool (prompt optimizado) | $1.823 | $3.187 | +1.364 |

## Lectura para decidir

- **El coste lo domina el prompt de entrada, no la salida.** Añadir la tool y sus instrucciones sube los tokens de entrada de ~98.8 (crudo) a ~313.8 (tool conciso) y ~573.8 (tool optimizado) por petición.
- **El fine-tuned no ahorra tokens**: consume tokens iguales o algo mayores que el normal en el mismo escenario, y su precio por token es más alto, por lo que **siempre cuesta más** a igualdad de calidad.
- El prompt 'optimizado' (C, ~612.5 tok) no mejora la exactitud del normal sobre el prompt conciso (B, ~355 tok): optimizar para calidad no es optimizar para coste.

**Decisión:** usar el **modelo base + tool con prompt conciso** (escenario B normal): 8/8 de exactitud al menor coste, menos tokens que el optimizado, y sin el precio por token más alto ni la tarifa de hosting del fine-tuned.

## Detalle: tokens totales consumidos en la medición

| Escenario | Modelo | In total | Out total |
|---|---|:--:|:--:|
| A | `gpt-4o` | 790 | 610 |
| A | `gpt-4o-ft` | 790 | 380 |
| B | `gpt-4o` | 2510 | 330 |
| B | `gpt-4o-ft` | 2510 | 493 |
| C | `gpt-4o` | 4590 | 310 |
| C | `gpt-4o-ft` | 5182 | 404 |
