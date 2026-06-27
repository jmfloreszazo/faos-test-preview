# Fine-tuning vs Tool: comparativa de un agente de soporte

Bundle autocontenido del experimento para el artículo. Compara el **mismo
modelo base `gpt-4o`** en versión normal y fine-tuned, con y sin tool, y su
optimización de prompt. Mismo dataset (8 preguntas) y mismo juez (`gpt-4o`).

## Empieza por aquí
- [docs/RESUMEN-final.md](docs/RESUMEN-final.md) — resumen consolidado, lectura global y recomendación.
- [docs/tokens-coste.md](docs/tokens-coste.md) — tokens de entrada/salida, coste y la **tabla de decisión** calidad-vs-coste.

## Las tres pruebas
| Test | Documento | Script | Idea |
|---|---|---|---|
| 1 | [docs/test1-llm-crudo.md](docs/test1-llm-crudo.md) | [scripts/compare_models.py](scripts/compare_models.py) | LLM crudo sin tool: ¿qué sabe en los pesos? |
| 2 | [docs/test2-agente.md](docs/test2-agente.md) | [scripts/compare_agents_tool.py](scripts/compare_agents_tool.py) | Mismo agente con tool `lookup_policy` |
| 3 | [docs/test3-optimizacion.md](docs/test3-optimizacion.md) | [scripts/optimize_compare.py](scripts/optimize_compare.py) | Optimización de prompt de ambos modelos |
| Coste | [docs/tokens-coste.md](docs/tokens-coste.md) | [scripts/token_report.py](scripts/token_report.py) | Tokens in/out, $/1k y proyección mensual |

## Resultado en una línea
```
Sin tool   (Test 1):  fine-tuning IMPRESCINDIBLE    2.56 -> 4.44  (+73%)
Con tool   (Test 2):  fine-tuning aporta poco/resta  normal 8/8 vs FT 6/8
Optimizado (Test 3):  ambos llegan al techo          5.0 / 8-8
Coste      (tokens):  base + tool conciso = mejor valor  $1.185/1k @ 8/8
```

## Decisión (calidad + coste)
Ganador: **`gpt-4o` base + tool `lookup_policy` con prompt conciso** — 8/8 de
exactitud al menor coste ($1.185/1k), sin tarifa de hosting y sin re-entrenar al
cambiar una política. El fine-tuning sólo gana si **no** puedes usar tool/RAG.

## Contenido de la carpeta
- `docs/` — los 4 documentos de resultados (Markdown con tablas).
- `scripts/` — código del experimento:
  - `build_sft_dataset_tools.py` — genera el dataset SFT tool-aware.
  - `run_finetune.py` — lanza/gestiona el fine-tuning.
  - `ft_status.py`, `ft_events.py` — seguimiento del job de fine-tuning.
  - `compare_models.py` (Test 1), `compare_agents_tool.py` (Test 2), `optimize_compare.py` (Test 3).
  - `token_report.py` — mide tokens in/out por petición y coste por arquitectura.
- `data/` — dataset de evaluación (`support-eval.jsonl`) y datasets SFT con tool.
- `results/` — logs crudos de las ejecuciones.
- `infra/` — IaC y configuración del agente usados para reproducir el entorno
  (`main.bicep`, `resources.bicep`, `azure.yaml`, `agent.yaml`).

## Cómo reproducir (PowerShell)
```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:FINETUNE_TOKEN    = az account get-access-token --scope "https://cognitiveservices.azure.com/.default" --query accessToken -o tsv
$env:FINETUNE_ENDPOINT = "https://aisvc-yrwwwokfuruzy.cognitiveservices.azure.com"

# Test 1 — LLM crudo
python scripts/compare_models.py --base gpt-4o --ft gpt-4o-ft --judge gpt-4o --out docs/test1-llm-crudo.md
# Test 2 — Agente con tool
python scripts/compare_agents_tool.py --normal gpt-4o --ft gpt-4o-ft --judge gpt-4o --out docs/test2-agente.md
# Test 3 — Optimización
python scripts/optimize_compare.py --normal gpt-4o --ft gpt-4o-ft --judge gpt-4o --optimizer gpt-5.1 --iterations 3 --out docs/test3-optimizacion.md
# Tokens / coste
python articulo-finetuning-vs-tool/scripts/token_report.py --normal gpt-4o --ft gpt-4o-ft
```

> Nota: las rutas internas de los scripts apuntan al dataset original en
> `src/support-agent/data/`. Esta carpeta es una copia para el artículo; los
> scripts se ejecutan desde la raíz del repositorio.
