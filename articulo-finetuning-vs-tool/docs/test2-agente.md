# Test 2 - Mismo agente con tool `lookup_policy`: normal vs fine-tuned

_Generado: 2026-06-27 09:30_ - dataset: 8 preguntas ([data/support-eval.jsonl](src/support-agent/data/support-eval.jsonl)).

| Rol | Deployment |
|---|---|
| Agente normal | `gpt-4o` |
| Agente fine-tuned | `gpt-4o-ft` |
| Juez | `gpt-4o` |

Ambos agentes usan el **mismo** system prompt y la **misma** tool `lookup_policy` (flujo de 2 llamadas: decidir tool -> responder con la politica). La tool inyecta la politica correcta, asi que ambos deberian acertar; lo interesante es el comportamiento de tool-calling, los tokens y la latencia.

## Resultado agregado

| Metrica | Normal | Fine-tuned | Δ |
|---|:--:|:--:|:--:|
| Relevancia (1-5) | 5 | 4.38 | -0.62 |
| Adherencia (1-5) | 5 | 4.38 | -0.62 |
| Correctas (rel ≥ 4) | 8/8 | 6/8 | -2 |
| Veces que llamo a la tool | 8/8 | 8/8 | +0 |
| Tokens medios / pregunta | 358.12 | 375.25 | +17.1 |
| Latencia media (s) | 2.01 | 2.41 | +0.4 |

## Detalle por pregunta

### 1. How many days do I have to return a product?

**Ground truth:** You have 30 days from purchase to return a product, with receipt and in its original packaging.

**Normal (`gpt-4o`)** - rel 5, adh 5 · tool=si (returns) · 360 tok · 2.794s  ·  _The AI answer is factually correct, concise, and matches the reference information exactly._  
> You have 30 days from the date of purchase to return a product, as long as you have the receipt and the item is in its original packaging.

**Fine-tuned (`gpt-4o-ft`)** - rel 5, adh 5 · tool=si (returns) · 360 tok · 5.605s  ·  _The AI answer is factually correct and concise, matching the reference details exactly._  
> You have 30 days from the date of purchase to return a product. The return must include a receipt and the product should be in its original packaging.

### 2. How long does standard shipping take?

**Ground truth:** Standard shipping takes 3 to 5 business days.

**Normal (`gpt-4o`)** - rel 5, adh 5 · tool=si (shipping) · 353 tok · 1.47s  ·  _The AI answer is factually correct, concise, and adheres to the expected support agent behavior._  
> Standard shipping takes 3 to 5 business days. Let me know if you have any other questions!

**Fine-tuned (`gpt-4o-ft`)** - rel 3, adh 2 · tool=si (shipping) · 370 tok · 1.89s  ·  _The AI answer correctly states the standard shipping timeframe but adds information about express shipping, which is not in the reference. This makes it less relevant and not fully task-adherent._  
> Standard shipping takes 3 to 5 business days. If you need faster delivery, express shipping is available within 24 to 48 hours for an additional cost of $9.99.

### 3. Does express shipping have an extra cost?

**Ground truth:** Yes, express shipping (24-48 h) costs an additional $9.99.

**Normal (`gpt-4o`)** - rel 5, adh 5 · tool=si (shipping) · 348 tok · 1.616s  ·  _The AI answer correctly states the additional cost of $9.99 for express shipping and is concise, adhering to the expected support agent behavior._  
> Yes, express shipping has an additional cost of $9.99.

**Fine-tuned (`gpt-4o-ft`)** - rel 5, adh 5 · tool=si (shipping) · 374 tok · 1.728s  ·  _The AI answer correctly states the extra cost of $9.99 and the 24-48 hour timeframe for express shipping, aligning with the reference. It is concise and adheres to the expected support agent behavior._  
> Yes, express shipping has an extra cost of $9.99. It offers faster delivery within 24 to 48 hours compared to standard shipping, which takes 3 to 5 business days.

### 4. What warranty do the products have?

**Ground truth:** All products include a 2-year warranty against manufacturing defects.

**Normal (`gpt-4o`)** - rel 5, adh 5 · tool=si (warranty) · 341 tok · 2.76s  ·  _The AI answer correctly states the 2-year warranty against manufacturing defects and maintains a concise, professional tone._  
> All products come with a 2-year warranty that covers manufacturing defects. Let me know if you have any further questions!

**Fine-tuned (`gpt-4o-ft`)** - rel 5, adh 5 · tool=si (warranty) · 355 tok · 1.975s  ·  _The AI correctly states the 2-year warranty against manufacturing defects and offers appropriate next steps, adhering to the support agent role._  
> The products come with a 2-year warranty that covers manufacturing defects. If you need to make a warranty claim, please let me know, and I can guide you through the next steps.

### 5. I want to return something but I don't have the receipt, can I?

**Ground truth:** Returns require the receipt and the original packaging within 30 days.

**Normal (`gpt-4o`)** - rel 5, adh 5 · tool=si (returns) · 379 tok · 1.755s  ·  _The AI answer correctly states the return policy and adheres to the expected support agent behavior._  
> Returns are accepted within 30 days of purchase, but a receipt is required along with the original packaging. Without a receipt, unfortunately, we cannot process the return. Let me know if you need further assistance!

**Fine-tuned (`gpt-4o-ft`)** - rel 5, adh 5 · tool=si (returns) · 389 tok · 2.188s  ·  _The AI accurately states the return policy and offers to connect to a human agent for further assistance, aligning with the reference._  
> You cannot return the item without a receipt. The store's policy requires a receipt for returns, along with the item being in its original packaging and returned within 30 days of purchase. If you need further assistance, I can connect you to a human agent.

### 6. Do you ship internationally?

**Ground truth:** I don't have information about that topic; it's best to hand off to a human agent.

**Normal (`gpt-4o`)** - rel 5, adh 5 · tool=si (shipping) · 351 tok · 2.066s  ·  _The AI correctly states the lack of information and appropriately offers to hand off to a human agent, aligning with the reference._  
> The shipping policy does not specify whether we ship internationally. Let me hand this off to a human agent for clarification.

**Fine-tuned (`gpt-4o-ft`)** - rel 2, adh 4 · tool=si (shipping) · 385 tok · 2.104s  ·  _The AI provides unrelated shipping details instead of directly stating it lacks information and handing off to a human. However, it does offer to connect to a human, aligning partially with the task._  
> The shipping policy does not specify whether international shipping is available. It only mentions standard shipping taking 3 to 5 business days and express shipping having an additional cost of $9.99.   Would you like me to connect you with a human agent for more details about international shipping?

### 7. My product broke after 6 months, is it covered?

**Ground truth:** Yes, the 2-year warranty covers manufacturing defects.

**Normal (`gpt-4o`)** - rel 5, adh 5 · tool=si (warranty) · 373 tok · 1.954s  ·  _The AI correctly states the 2-year warranty coverage for manufacturing defects and offers assistance, aligning with the reference and expected support behavior._  
> Yes, your product is covered under our 2-year warranty against manufacturing defects. If you believe the issue is due to a defect, you can proceed with a warranty claim. Let me know if you need assistance with the process!

**Fine-tuned (`gpt-4o-ft`)** - rel 5, adh 5 · tool=si (warranty) · 392 tok · 2.234s  ·  _The AI correctly states the 2-year warranty and its coverage of manufacturing defects, and offers assistance, aligning with the reference and expected support behavior._  
> Yes, your product is covered under the warranty since it broke after 6 months. The store provides a 2-year warranty against manufacturing defects. If your product's issue is due to a manufacturing defect, you can make a warranty claim within this period. If you need assistance with the claim process, please let me know.

### 8. How much does express shipping cost and how long does it take?

**Ground truth:** Express shipping takes 24-48 h and costs an additional $9.99.

**Normal (`gpt-4o`)** - rel 5, adh 5 · tool=si (shipping) · 360 tok · 1.664s  ·  _The AI answer is factually correct, concise, and matches the reference exactly._  
> Express shipping costs $9.99 and takes 24 to 48 hours.

**Fine-tuned (`gpt-4o-ft`)** - rel 5, adh 4 · tool=si (shipping) · 377 tok · 1.526s  ·  _The AI answer correctly provides the cost and timeframe for express shipping but includes unnecessary information about standard shipping, which was not asked._  
> Express shipping costs an additional $9.99 and takes 24 to 48 hours. Standard shipping, by comparison, takes 3 to 5 business days.

