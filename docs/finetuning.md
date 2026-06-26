# Generación de datos sintéticos, Fine-tuning y Deploy

Pipeline end-to-end para: generar trazas sintéticas desde el agente desplegado →
curar un dataset SFT → lanzar un fine-tuning en Azure → desplegar y probar el
modelo resultante.

> Este documento describe lo realizado sobre el recurso **AI Services / Foundry**
> `aisvc-yrwwwokfuruzy` (proyecto `proj-yrwwwokfuruzy`, RG `rg-support-demo-en`,
> región `eastus2`).

---

## 0. Entorno y requisitos

| Elemento | Valor |
|---|---|
| Subscription | `7a84bc78-1d1e-4294-a7c4-760dc607b5de` |
| Tenant | `f0eff2df-e4c1-4b90-870a-5f6ab6a6604b` |
| Resource Group | `rg-support-demo-en` |
| Región | `eastus2` |
| AI Services | `aisvc-yrwwwokfuruzy` |
| Proyecto | `proj-yrwwwokfuruzy` |
| Endpoint cuenta | `https://aisvc-yrwwwokfuruzy.services.ai.azure.com` |
| Agente desplegado | `support-agent` (v200) |

Prerrequisitos locales (Windows + PowerShell 7):

```pwsh
# El intérprete del venv (python "pelado" NO está en PATH en esta máquina)
.\.venv\Scripts\python.exe --version

# SDK necesario para lanzar el fine-tuning
.\.venv\Scripts\python.exe -m pip install openai

# Sesión de Azure CLI activa
az account show
```

Hay **dos scopes de token** distintos según el endpoint:

| Acción | Scope |
|---|---|
| Invocar el agente (`/responses`) | `https://ai.azure.com/.default` |
| Files / fine-tuning / chat completions | `https://cognitiveservices.azure.com/.default` |

---

## 1. Generar trazas sintéticas (blast al agente)

[scripts/blast_agent.ps1](scripts/blast_agent.ps1) dispara N preguntas de soporte
realistas (devoluciones / envíos / garantías / escalado) contra el endpoint
`/responses` del agente. Cada petición es *stateless*, por lo que paraleliza.

Características clave:

- Banco de ~1500 preguntas únicas (plantillas de intención × productos × periodos).
- `-Throttle` controla la concurrencia. **Mantener ≤ 4**: el modelo base
  `gpt-4.1-mini` tiene capacidad 50 y cada request hace 2 llamadas (decisión de
  tool + respuesta); con concurrencia alta el modelo se satura y devuelve HTTP 200
  pero con cuerpo vacío (sin `message`).
- Reintentos con backoff exponencial + jitter, y detección de respuesta vacía.
- **Auto-refresh del token** al detectar `401` (sin consumir presupuesto de
  reintentos), porque un run largo supera la vida del token (~60-75 min).
- Salida CSV en `optimize-runs/blast-<timestamp>.csv` con columnas
  `Index, Status, Attempts, Seconds, Question, Answer`.

```pwsh
# Ejecución recomendada (throttle bajo + reintentos)
pwsh -File scripts/blast_agent.ps1 -Count 1000 -Throttle 4 -Retries 5
```

Al terminar imprime el resumen (Succeeded / Empty / Errors / Retried) y la
**ventana temporal UTC**, útil para filtrar luego en el portal de Foundry.

> Resultado usado: `blast-20260626-092317.csv` con **700 trazas limpias**
> (ventana `2026-06-26T07:23:17Z` → `2026-06-26T08:51:17Z`).

### Lecciones aprendidas

- **817/1000 vacías** en el primer intento (throttle 10) → saturación del modelo.
  Solución: bajar throttle a 4 + reintento en vacío.
- **298/1000 errores 401** en un run de 88 min → token expirado.
  Solución: refresco de token por worker al detectar 401.

---

## 2. Construir el dataset SFT

[scripts/build_sft_dataset.py](scripts/build_sft_dataset.py) lee los CSV
`optimize-runs/blast-*.csv`, se queda **solo con filas limpias** (`Status == ok`
y `Answer` no vacía), deduplica por pregunta normalizada, baraja (seed 42) y parte
en train / validation en formato chat de Azure OpenAI.

```pwsh
.\.venv\Scripts\python.exe scripts/build_sft_dataset.py --val-split 0.1 --seed 42
```

Salida en `src/support-agent/data/`:

| Fichero | Ejemplos | Tokens aprox. |
|---|---|---|
| [support-sft.train.jsonl](src/support-agent/data/support-sft.train.jsonl) | 636 | ~110.336 |
| [support-sft.val.jsonl](src/support-agent/data/support-sft.val.jsonl) | 70 | ~12.279 |
| [support-sft.jsonl](src/support-agent/data/support-sft.jsonl) (combinado) | 706 | ~122.615 |

Formato de cada línea:

```json
{"messages": [
  {"role": "system",    "content": "<persona de soporte>"},
  {"role": "user",      "content": "<pregunta del cliente>"},
  {"role": "assistant", "content": "<respuesta de soporte>"}
]}
```

El `system` se deriva de la persona baseline del agente pero **sin** la instrucción
obligatoria de llamar al tool, porque estos ejemplos entrenan al modelo a
responder la política directamente.

---

## 3. Validar y lanzar el fine-tuning

[scripts/run_finetune.py](scripts/run_finetune.py) valida el dataset (gratis, sin
red) y, con `--launch`, sube los ficheros y crea el job.

### Validación (sin coste)

```pwsh
.\.venv\Scripts\python.exe scripts/run_finetune.py
```

### Lanzamiento (con coste)

El script soporta autenticación por token directo (vía `FINETUNE_TOKEN`) porque
`DefaultAzureCredential` no siempre encuentra el `az` CLI en el subproceso. También
permite **reutilizar ficheros ya subidos** (`FINETUNE_TRAIN_FILE_ID` /
`FINETUNE_VAL_FILE_ID`) y **espera a que los ficheros estén `processed`** antes de
crear el job, con reintentos ante `408 Timeout`.

```pwsh
$env:FINETUNE_TOKEN    = (az account get-access-token --scope https://cognitiveservices.azure.com/.default --query accessToken -o tsv)
$env:FINETUNE_ENDPOINT = 'https://aisvc-yrwwwokfuruzy.services.ai.azure.com'

.\.venv\Scripts\python.exe scripts/run_finetune.py --launch `
  --model gpt-4o-2024-08-06 --api-version 2024-10-21
```

> ⚠️ **Elección del modelo base — importante.** En `eastus2` `gpt-4.1-mini`
> **no** admite fine-tuning (el POST de creación se cuelga → `408`) y
> `gpt-35-turbo` está **deprecado** para fine-tuning (`400 deprecated`). Los
> modelos base válidos en esta región son:
>
> | Modelo | Versión |
> |---|---|
> | `gpt-4o` | `2024-08-06` |
> | `o4-mini` | `2025-04-16` |
> | ~~`gpt-35-turbo`~~ | deprecado |
>
> Comprobar disponibilidad:
>
> ```pwsh
> az cognitiveservices model list -l eastus2 `
>   --query "[?model.capabilities.fineTune=='true'].{name:model.name, version:model.version}" -o table
> ```

> Job lanzado: **`ftjob-6b3bb3f9f1ff4e6e91d7116a22d63ae1`** sobre
> `gpt-4o-2024-08-06`. Resultado: `succeeded`, **388.251 tokens entrenados**,
> modelo `gpt-4o-2024-08-06.ft-6b3bb3f9f1ff4e6e91d7116a22d63ae1-support-sft`.

---

## 4. Monitorizar el job

[scripts/watch_finetune.ps1](scripts/watch_finetune.ps1) hace polling del job,
refresca el token automáticamente, va imprimiendo los eventos (loss por step) y
sale cuando el job llega a estado terminal.

```pwsh
pwsh -File scripts/watch_finetune.ps1 `
  -JobId ftjob-6b3bb3f9f1ff4e6e91d7116a22d63ae1 -IntervalSec 120
```

Consulta puntual por REST:

```pwsh
$tok = (az account get-access-token --scope https://cognitiveservices.azure.com/.default --query accessToken -o tsv)
$h = @{ Authorization = "Bearer $tok" }
Invoke-RestMethod -Headers $h -Uri "https://aisvc-yrwwwokfuruzy.services.ai.azure.com/openai/fine_tuning/jobs/ftjob-6b3bb3f9f1ff4e6e91d7116a22d63ae1?api-version=2024-10-21" |
  Select-Object id, status, model, fine_tuned_model, trained_tokens
```

---

## 5. Desplegar el modelo fine-tuneado

Los modelos fine-tuneados se despliegan con SKU **`Standard`** (regional; no
`GlobalStandard`). Tiene **coste de hosting por hora** mientras el deployment esté
activo.

```pwsh
az cognitiveservices account deployment create `
  -g rg-support-demo-en -n aisvc-yrwwwokfuruzy `
  --deployment-name support-sft-ft `
  --model-name "gpt-4o-2024-08-06.ft-6b3bb3f9f1ff4e6e91d7116a22d63ae1-support-sft" `
  --model-version 1 --model-format OpenAI `
  --sku-name Standard --sku-capacity 1
```

Esperar a que esté listo:

```pwsh
az cognitiveservices account deployment show `
  -g rg-support-demo-en -n aisvc-yrwwwokfuruzy `
  --deployment-name support-sft-ft `
  --query "properties.provisioningState" -o tsv   # -> Succeeded
```

---

## 6. Probar el modelo desplegado

```pwsh
$tok = (az account get-access-token --scope https://cognitiveservices.azure.com/.default --query accessToken -o tsv)
$h = @{ Authorization = "Bearer $tok"; 'Content-Type' = 'application/json' }
$sys = 'You are a customer support agent for an online store. You answer customer questions about returns, shipping and warranties. Be clear and concise, and always answer in English.'
$body = @{
  messages = @(
    @{ role = 'system'; content = $sys },
    @{ role = 'user';   content = 'How long do I have to return a pair of headphones?' }
  )
  max_tokens = 200; temperature = 0.2
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method POST -Headers $h `
  -Uri "https://aisvc-yrwwwokfuruzy.services.ai.azure.com/openai/deployments/support-sft-ft/chat/completions?api-version=2024-10-21" `
  -Body $body | ForEach-Object { $_.choices[0].message.content }
```

Respuestas del modelo entrenado (coherentes con las políticas):

| Pregunta | Respuesta |
|---|---|
| How long do I have to return a pair of headphones? | 30 días desde la compra, con recibo y embalaje original. |
| My package is late, what shipping options do you offer? | Standard 3-5 días hábiles / Express 24-48h. |
| Is the warranty on a laptop transferable if I sell it? | No transferible; solo comprador original, 2 años por defectos. |

---

## 7. Limpieza (evitar coste de hosting)

Cuando no se use el modelo, borrar el deployment (el modelo fine-tuneado y los
ficheros se conservan):

```pwsh
az cognitiveservices account deployment delete `
  -g rg-support-demo-en -n aisvc-yrwwwokfuruzy `
  --deployment-name support-sft-ft
```

---

## Resumen de artefactos

| Tipo | Identificador |
|---|---|
| Fichero train | `file-f05ae9884836442abfe2595f8321ef28` |
| Fichero val | `file-d462fbc709f94b399baa695414dc481c` |
| Fine-tuning job | `ftjob-6b3bb3f9f1ff4e6e91d7116a22d63ae1` |
| Modelo base | `gpt-4o-2024-08-06` |
| Modelo fine-tuneado | `gpt-4o-2024-08-06.ft-6b3bb3f9f1ff4e6e91d7116a22d63ae1-support-sft` |
| Deployment | `support-sft-ft` (SKU Standard, 1K TPM) |

| Script | Propósito |
|---|---|
| [scripts/blast_agent.ps1](scripts/blast_agent.ps1) | Generar trazas sintéticas desde el agente |
| [scripts/build_sft_dataset.py](scripts/build_sft_dataset.py) | Curar CSV → dataset SFT JSONL |
| [scripts/run_finetune.py](scripts/run_finetune.py) | Validar / lanzar el fine-tuning |
| [scripts/watch_finetune.ps1](scripts/watch_finetune.ps1) | Monitorizar el job hasta completar |
