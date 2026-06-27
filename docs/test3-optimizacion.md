# Test 3 - Optimizacion del mismo agente: normal vs fine-tuned

_Generado: 2026-06-27 10:18_ - dataset: 8 preguntas ([data/support-eval.jsonl](src/support-agent/data/support-eval.jsonl)).

Optimizador: `gpt-5.1` · Juez: `gpt-4o` · Iteraciones: 3.

Ambos agentes parten del **mismo prompt debil** y se optimizan con el mismo modelo optimizador y el mismo dataset. El optimizador reescribe el system prompt iteracion a iteracion buscando maximizar relevancia + adherencia; nos quedamos con el mejor candidato. Asi vemos *como evoluciona* cada version del modelo desde la misma base.

**Prompt debil de partida:** `You are a support bot. Answer the customer's question.`

## Resumen: baseline -> optimizado

| Modelo | Combinada base | Combinada opt | Δ | Correctas base | Correctas opt |
|---|:--:|:--:|:--:|:--:|:--:|
| Normal (`gpt-4o`) | 4.312 | 5.0 | +0.688 | 6/8 | 8/8 |
| Fine-tuned (`gpt-4o-ft`) | 4.25 | 5.0 | +0.75 | 6/8 | 8/8 |

## Evolucion - Normal

| Iter | Relevancia | Adherencia | Combinada | Correctas | Tool |
|:--:|:--:|:--:|:--:|:--:|:--:|
| 0 (baseline) | 4.375 | 4.25 | 4.312 | 6/8 | 8/8 |
| 1 | 5 | 5 | 5.0 | 8/8 | 8/8 |
| 2 | 5 | 5 | 5.0 | 8/8 | 8/8 |
| 3 | 5 | 5 | 5.0 | 8/8 | 8/8 |

## Evolucion - Fine-tuned

| Iter | Relevancia | Adherencia | Combinada | Correctas | Tool |
|:--:|:--:|:--:|:--:|:--:|:--:|
| 0 (baseline) | 4.375 | 4.125 | 4.25 | 6/8 | 8/8 |
| 1 | 5 | 5 | 5.0 | 8/8 | 8/8 |
| 2 | 4.625 | 4.375 | 4.5 | 7/8 | 8/8 |
| 3 | 4.625 | 4.625 | 4.625 | 7/8 | 8/8 |

## Prompts optimizados

**Normal (`gpt-4o`):**

```text
You are a customer-support agent for returns, shipping, and warranties. You have a single tool: `lookup_policy(topic)` where topic ∈ {'returns','shipping','warranty'}. It returns the current official policy text for that topic.

Always follow these rules:
1. Before answering ANY question, call `lookup_policy` for each relevant topic, then base your answer ONLY on the returned policy text and the user’s question.
2. Never invent, guess, or extend policies beyond what the tool returns. If a detail is not clearly stated in the policy text, say you don’t have that information.
3. If the policy text does not let you answer the user’s request, explicitly offer to hand off the conversation to a human agent.
4. Answer ONLY what was asked, in English, clearly and concisely, without extra commentary, upselling, or unrelated details.
5. Do not quote the entire policy unless the user explicitly asks for it; summarize only the relevant parts.
```

**Fine-tuned (`gpt-4o-ft`):**

```text
You are a customer-support assistant for returns, shipping, and warranties. You have a tool `lookup_policy(topic)` that returns the official policy text for one topic: `returns`, `shipping`, or `warranty`.

Instructions:
1. Always call `lookup_policy` for the relevant topic(s) BEFORE answering, even if you think you know the policy.
2. Base your answer ONLY on the returned policy text and the user’s question. Do not invent details or add information not supported by the policy.
3. Answer in clear, concise English. No padding, small talk, or marketing language.
4. Answer ONLY what the user asked. Do not add extra recommendations, explanations, or cross-topic details unless they are explicitly requested or needed to avoid ambiguity.
5. If the policy text does not provide the information needed to answer the question, say you don’t have that information and offer to hand off to a human agent for clarification.
6. If the question is unrelated to returns, shipping, or warranty, briefly state that you can’t answer it and offer to hand off to a human agent.
7. Never hard-code policy values; always rely on `lookup_policy`.
```

## Detalle final por pregunta (prompt optimizado)

### 1. How many days do I have to return a product?

**Ground truth:** You have 30 days from purchase to return a product, with receipt and in its original packaging.

**Normal** - rel 5, adh 5 · tool=si · 626 tok  ·  _The AI answer is factually correct and concise, matching the reference details exactly._  
> You have 30 days from the date of purchase to return a product, provided you have the receipt and the item is in its original packaging.

**Fine-tuned** - rel 5, adh 5 · tool=si · 700 tok  ·  _The AI answer is factually correct, concise, and adheres to the expected support agent behavior._  
> You have 30 days from the date of purchase to return a product. The return must include a receipt and the product should be in its original packaging.

### 2. How long does standard shipping take?

**Ground truth:** Standard shipping takes 3 to 5 business days.

**Normal** - rel 5, adh 5 · tool=si · 611 tok  ·  _The AI answer is factually correct and concise, matching the reference exactly._  
> Standard shipping takes 3 to 5 business days.

**Fine-tuned** - rel 5, adh 5 · tool=si · 683 tok  ·  _The AI answer is factually correct and concise, matching the reference exactly._  
> Standard shipping takes 3 to 5 business days.

### 3. Does express shipping have an extra cost?

**Ground truth:** Yes, express shipping (24-48 h) costs an additional $9.99.

**Normal** - rel 5, adh 5 · tool=si · 616 tok  ·  _The AI answer is factually correct and concise, matching the reference details exactly._  
> Yes, express shipping has an additional cost of $9.99.

**Fine-tuned** - rel 5, adh 5 · tool=si · 688 tok  ·  _The AI answer is factually correct and concise, matching the reference details._  
> Yes, express shipping has an extra cost of $9.99.

### 4. What warranty do the products have?

**Ground truth:** All products include a 2-year warranty against manufacturing defects.

**Normal** - rel 5, adh 5 · tool=si · 599 tok  ·  _The AI answer is factually correct and concise, matching the reference exactly._  
> All products come with a 2-year warranty that covers manufacturing defects.

**Fine-tuned** - rel 5, adh 5 · tool=si · 669 tok  ·  _The AI answer is accurate, concise, and matches the reference information._  
> The products have a 2-year warranty against manufacturing defects.

### 5. I want to return something but I don't have the receipt, can I?

**Ground truth:** Returns require the receipt and the original packaging within 30 days.

**Normal** - rel 5, adh 5 · tool=si · 658 tok  ·  _The AI correctly states that a receipt is required and offers to connect to a human agent, adhering to the reference and task requirements._  
> Based on the return policy, a receipt is required to process a return. Since you don't have the receipt, the policy does not specify if exceptions can be made. I recommend contacting a human agent for further assistance. Would you like me to connect you to one?

**Fine-tuned** - rel 5, adh 5 · tool=si · 712 tok  ·  _The AI answer accurately reflects the return policy and is concise, adhering to the expected support agent behavior._  
> You cannot return the item without a receipt. The policy requires a receipt for returns, along with the item being in its original packaging and returned within 30 days of purchase.

### 6. Do you ship internationally?

**Ground truth:** I don't have information about that topic; it's best to hand off to a human agent.

**Normal** - rel 5, adh 5 · tool=si · 627 tok  ·  _The AI correctly states it lacks information and offers to hand off to a human, aligning with the reference._  
> The shipping policy does not specify whether international shipping is available. I recommend connecting with a human agent for clarification. Would you like me to assist with that?

**Fine-tuned** - rel 5, adh 5 · tool=si · 711 tok  ·  _The AI correctly states it lacks information on international shipping and offers to connect to a human agent, aligning with the reference._  
> The policy text does not specify whether international shipping is available. It only provides details about standard and express shipping times and costs.   Would you like me to connect you to a human agent for clarification on international shipping?

### 7. My product broke after 6 months, is it covered?

**Ground truth:** Yes, the 2-year warranty covers manufacturing defects.

**Normal** - rel 5, adh 5 · tool=si · 611 tok  ·  _The AI correctly states that the product is covered under the 2-year warranty for manufacturing defects and adheres to the expected support agent behavior._  
> Yes, your product is covered under the 2-year warranty against manufacturing defects.

**Fine-tuned** - rel 5, adh 5 · tool=si · 701 tok  ·  _The AI correctly states the product is covered under the 2-year warranty for manufacturing defects and provides a concise, relevant response._  
> Yes, your product is covered under the 2-year warranty for manufacturing defects since it broke after 6 months. This warranty covers defects related to manufacturing within that period.

### 8. How much does express shipping cost and how long does it take?

**Ground truth:** Express shipping takes 24-48 h and costs an additional $9.99.

**Normal** - rel 5, adh 5 · tool=si · 630 tok  ·  _The AI answer is factually correct, concise, and matches the reference exactly._  
> Express shipping takes 24 to 48 hours and costs an additional $9.99.

**Fine-tuned** - rel 5, adh 5 · tool=si · 703 tok  ·  _The AI answer is factually correct, concise, and matches the reference exactly._  
> Express shipping costs an additional $9.99 and takes 24 to 48 hours.

