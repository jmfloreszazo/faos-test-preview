# Comparativa: modelo base vs fine-tuneado

_Generado: 2026-06-26 18:07_ — dataset de evaluación: 8 preguntas con `ground_truth` ([data/support-eval.jsonl](src/support-agent/data/support-eval.jsonl)).

| Rol | Deployment |
|---|---|
| Modelo base | `gpt-4.1-mini` |
| Modelo fine-tuneado | `support-sft-ft` |
| Juez (evaluador) | `gpt-4o` |

Mismo `system` para ambos candidatos (sin acceso a la herramienta `lookup_policy`): se mide cuánto conocimiento de las políticas tiene el modelo **en sus pesos**. El modelo fine-tuneado aprendió las políticas durante el SFT; el base no las conoce.

## Resultado agregado (1-5)

| Métrica | Base | Fine-tuned | Δ |
|---|:--:|:--:|:--:|
| Relevancia (factual) | 1.62 | 4.62 | +3.0 |
| Adherencia a la tarea | 3.75 | 4.38 | +0.63 |
| **Global** | **2.69** | **4.5** | **+1.81** |
| Respuestas correctas (rel ≥ 4) | 0/8 | 7/8 | +7 |

Mejora relativa global del fine-tuned sobre el base: **+67.3%**.

## Detalle por pregunta

### 1. How many days do I have to return a product?

**Ground truth:** You have 30 days from purchase to return a product, with receipt and in its original packaging.

**Base (`gpt-4.1-mini`)** — rel 2, adh 4  ·  _The AI incorrectly states '30 days of delivery' instead of '30 days from purchase,' but it adheres to the task format and tone._  
> Our standard return policy allows you to return a product within 30 days of delivery. The item must be in its original condition and packaging. If you need more specific information about your order or product, please let me know!

**Fine-tuned (`support-sft-ft`)** — rel 5, adh 5  ·  _The AI answer is factually correct and concise, matching the reference details exactly._  
> You have 30 days from the date of purchase to return a product. The return must include the receipt and the product should be in its original packaging.

### 2. How long does standard shipping take?

**Ground truth:** Standard shipping takes 3 to 5 business days.

**Base (`gpt-4.1-mini`)** — rel 1, adh 4  ·  _The AI provided an incorrect timeframe for standard shipping, but the response was otherwise concise and professional._  
> Standard shipping typically takes 5-7 business days. If you need more specific information based on your location or order, please let me know!

**Fine-tuned (`support-sft-ft`)** — rel 5, adh 3  ·  _The AI correctly states the standard shipping timeframe but adds unnecessary information about express shipping, which is not in the reference._  
> Standard shipping takes 3 to 5 business days. If you need faster delivery, express shipping is available within 24 to 48 hours but has an additional cost of $9.99.

### 3. Does express shipping have an extra cost?

**Ground truth:** Yes, express shipping (24-48 h) costs an additional $9.99.

**Base (`gpt-4.1-mini`)** — rel 2, adh 3  ·  _The AI answer is vague and does not provide the specific cost of $9.99 mentioned in the reference. It also unnecessarily complicates the response instead of being concise._  
> Yes, express shipping typically has an extra cost compared to standard shipping. The exact additional fee depends on the size, weight of the package, and the destination. For precise pricing, please provide your shipping address and the items you wish to purchase, or I can connect you with a human agent to assist further.

**Fine-tuned (`support-sft-ft`)** — rel 5, adh 4  ·  _The AI correctly states the cost and timeframe for express shipping but includes unnecessary information about standard shipping, which was not asked._  
> Yes, express shipping has an extra cost of $9.99. Standard shipping takes 3 to 5 business days, while express shipping delivers within 24 to 48 hours.

### 4. What warranty do the products have?

**Ground truth:** All products include a 2-year warranty against manufacturing defects.

**Base (`gpt-4.1-mini`)** — rel 1, adh 4  ·  _The AI provided incorrect warranty information, stating a one-year warranty instead of the correct two-year warranty. However, it adhered to the task by being concise and offering further assistance._  
> Our products typically come with a one-year limited warranty covering manufacturing defects. However, warranty terms can vary depending on the specific product category. If you provide the product name or category, I can give you more detailed information.

**Fine-tuned (`support-sft-ft`)** — rel 5, adh 5  ·  _The AI answer correctly states the 2-year warranty against manufacturing defects and is concise and professional._  
> All products come with a 2-year warranty that covers manufacturing defects. If you encounter any such defects within this period, the warranty applies.

### 5. I want to return something but I don't have the receipt, can I?

**Ground truth:** Returns require the receipt and the original packaging within 30 days.

**Base (`gpt-4.1-mini`)** — rel 2, adh 4  ·  _The AI answer is factually incorrect as the reference states returns require a receipt, but it offers to connect to a human agent, adhering to task guidelines._  
> Returns without a receipt depend on our store policy. Typically, we may offer store credit or exchanges without a receipt, but a full refund usually requires proof of purchase. To assist you accurately, could you please provide the item details or order number? If you prefer, I can connect you with a human agent for further help.

**Fine-tuned (`support-sft-ft`)** — rel 5, adh 5  ·  _The AI accurately states the return policy and offers to connect to a human agent for further assistance, aligning with the reference._  
> You can return items within 30 days of purchase, but a receipt is required along with the item being in its original packaging. Since you don't have the receipt, it appears that the return may not be accepted under the current policy. If you need further assistance, I can connect you to a human agent.

### 6. Do you ship internationally?

**Ground truth:** I don't have information about that topic; it's best to hand off to a human agent.

**Base (`gpt-4.1-mini`)** — rel 1, adh 2  ·  _The AI provided an incorrect answer instead of handing off to a human as instructed in the reference._  
> Yes, we do offer international shipping. Shipping costs and delivery times vary depending on the destination country. If you provide your location, I can give you more specific information.

**Fine-tuned (`support-sft-ft`)** — rel 2, adh 4  ·  _The AI answer includes irrelevant shipping details not in the reference and partially invents information. However, it correctly offers to hand off to a human agent._  
> The information provided does not specify whether the store ships internationally. It only mentions standard shipping times (3 to 5 business days) and express shipping (24 to 48 hours with an additional cost of $9.99).   Would you like me to connect you to a human agent for more details on international shipping?

### 7. My product broke after 6 months, is it covered?

**Ground truth:** Yes, the 2-year warranty covers manufacturing defects.

**Base (`gpt-4.1-mini`)** — rel 2, adh 4  ·  _The AI answer is vague and does not confirm the 2-year warranty stated in the reference. It does offer to connect to a human, which aligns with task adherence._  
> Whether your product is covered after 6 months depends on the warranty terms specific to that item. Most products come with a manufacturer's warranty that typically ranges from 6 months to 1 year or more. Please check the warranty information that came with your product or on our website.

If you provide me with the product name or order details, I can look up the exact warranty coverage for you. Alternatively, I can connect you with a human agent to assist further.

**Fine-tuned (`support-sft-ft`)** — rel 5, adh 5  ·  _The AI correctly states the 2-year warranty and addresses the question about coverage after 6 months. It also offers assistance, adhering to expected support behavior._  
> Yes, your product is covered under the warranty since it broke after 6 months. The store provides a 2-year warranty against manufacturing defects. If the issue is due to a manufacturing defect, you can make a warranty claim within this period. Let me know if you need help with the next steps for the warranty claim.

### 8. How much does express shipping cost and how long does it take?

**Ground truth:** Express shipping takes 24-48 h and costs an additional $9.99.

**Base (`gpt-4.1-mini`)** — rel 2, adh 5  ·  _The AI fails to provide the correct cost and timeframe but appropriately offers to hand off to a human._  
> I don't have the exact details on express shipping costs and delivery times for your order. To get accurate information, I can connect you with a human agent who can assist you further. Would you like me to do that?

**Fine-tuned (`support-sft-ft`)** — rel 5, adh 4  ·  _The AI answer is accurate and provides the correct cost and timeframe for express shipping. However, it includes unnecessary information about standard shipping, which was not asked for._  
> Express shipping costs $9.99 and takes 24 to 48 hours for delivery. Standard shipping, by comparison, takes 3 to 5 business days.

