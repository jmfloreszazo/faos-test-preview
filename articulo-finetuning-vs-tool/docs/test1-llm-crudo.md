# Comparativa: modelo base vs fine-tuneado

_Generado: 2026-06-27 09:27_ — dataset de evaluación: 8 preguntas con `ground_truth` ([data/support-eval.jsonl](src/support-agent/data/support-eval.jsonl)).

| Rol | Deployment |
|---|---|
| Modelo base | `gpt-4o` |
| Modelo fine-tuneado | `gpt-4o-ft` |
| Juez (evaluador) | `gpt-4o` |

Mismo `system` para ambos candidatos (sin acceso a la herramienta `lookup_policy`): se mide cuánto conocimiento de las políticas tiene el modelo **en sus pesos**. El modelo fine-tuneado aprendió las políticas durante el SFT; el base no las conoce.

## Resultado agregado (1-5)

| Métrica | Base | Fine-tuned | Δ |
|---|:--:|:--:|:--:|
| Relevancia (factual) | 1.62 | 4.5 | +2.88 |
| Adherencia a la tarea | 3.5 | 4.38 | +0.88 |
| **Global** | **2.56** | **4.44** | **+1.88** |
| Respuestas correctas (rel ≥ 4) | 0/8 | 6/8 | +6 |

Mejora relativa global del fine-tuned sobre el base: **+73.4%**.

## Detalle por pregunta

### 1. How many days do I have to return a product?

**Ground truth:** You have 30 days from purchase to return a product, with receipt and in its original packaging.

**Base (`gpt-4o`)** — rel 2, adh 4  ·  _The AI incorrectly states the return period starts from the delivery date instead of the purchase date. It adheres to task expectations but provides inaccurate information._  
> Our return policy allows you to return a product within 30 days of the delivery date. The item must be in its original condition, with all tags and packaging intact. If you need further assistance, feel free to ask!

**Fine-tuned (`gpt-4o-ft`)** — rel 5, adh 5  ·  _The AI answer is factually correct and concise, matching the reference details exactly._  
> You have 30 days from the date of purchase to return a product. The return must include the receipt and the product should be in its original packaging.

### 2. How long does standard shipping take?

**Ground truth:** Standard shipping takes 3 to 5 business days.

**Base (`gpt-4o`)** — rel 1, adh 3  ·  _The AI provided incorrect shipping timeframes (5-7 days instead of 3-5 days). It also added unnecessary details about processing time, which were not in the reference._  
> Standard shipping typically takes **5-7 business days** from the date your order is processed and shipped. Processing usually takes **1-2 business days**. If you need more specific information about your order, let me know!

**Fine-tuned (`gpt-4o-ft`)** — rel 3, adh 2  ·  _The AI answer correctly states the standard shipping timeframe but introduces information about express shipping, which is not in the reference and deviates from expected task adherence._  
> Standard shipping takes 3 to 5 business days. If you need faster delivery, express shipping is available within 24 to 48 hours but has an additional cost of $9.99.

### 3. Does express shipping have an extra cost?

**Ground truth:** Yes, express shipping (24-48 h) costs an additional $9.99.

**Base (`gpt-4o`)** — rel 2, adh 3  ·  _The AI answer is vague and does not provide the specific cost of $9.99 as stated in the reference. It also unnecessarily complicates the response instead of being concise._  
> Yes, express shipping typically has an extra cost. The exact amount depends on the destination and the size/weight of your order. If you'd like specific pricing, please provide your location and the items you're ordering, or I can connect you with a human agent for more details.

**Fine-tuned (`gpt-4o-ft`)** — rel 5, adh 5  ·  _The AI correctly states the cost and timeframe for express shipping and provides additional relevant information about standard shipping, which aligns with the expected support behavior._  
> Yes, express shipping has an extra cost of $9.99. It delivers your order within 24 to 48 hours. Standard shipping takes 3 to 5 business days and does not have this additional cost.

### 4. What warranty do the products have?

**Ground truth:** All products include a 2-year warranty against manufacturing defects.

**Base (`gpt-4o`)** — rel 1, adh 4  ·  _The AI provided incorrect warranty information, deviating from the reference's clear 2-year warranty. It adhered to task behavior by offering further assistance and a handoff option._  
> Our products typically come with a standard one-year manufacturer’s warranty, which covers defects in materials or workmanship. However, warranty terms can vary depending on the specific product and brand. 

If you'd like detailed information about the warranty for a particular item, please provide the product name or model number, and I can assist further. If I don’t have the information you need, I can connect you with a human agent for more assistance.

**Fine-tuned (`gpt-4o-ft`)** — rel 5, adh 5  ·  _The AI answer correctly states the 2-year warranty against manufacturing defects and provides additional relevant details in a concise manner._  
> All products come with a 2-year warranty that covers manufacturing defects. If you experience any issues related to manufacturing defects within this period, you can make a warranty claim for repair or replacement.

### 5. I want to return something but I don't have the receipt, can I?

**Ground truth:** Returns require the receipt and the original packaging within 30 days.

**Base (`gpt-4o`)** — rel 2, adh 4  ·  _The AI answer incorrectly suggests returns might be possible without a receipt, which contradicts the reference. However, it adheres to task expectations by offering to connect to a human agent._  
> Our return policy typically requires a receipt or proof of purchase to process a return. If you don't have the receipt, we may still be able to assist you if the purchase can be verified, such as through the payment method used (e.g., credit card or PayPal). 

Please note that without a receipt, refunds may be issued as store credit instead of the original payment method. Additionally, the item must meet our return conditions, such as being in its original packaging and within the return window (usually 30 days from the delivery date, but please check your order confirmation for specifics).

If you're unable to verify the purchase, I recommend contacting our customer service team directly for further assistance. Let me know if you'd like me to connect you with a human agent!

**Fine-tuned (`gpt-4o-ft`)** — rel 5, adh 5  ·  _The AI correctly states the return policy requiring a receipt and offers to connect to a human agent for further assistance, adhering to the task._  
> You can return items within 30 days of purchase, but a receipt is required for the return. Since you don't have the receipt, it appears you would not be able to return the item under the current policy. If you need further assistance, I can connect you with a human agent.

### 6. Do you ship internationally?

**Ground truth:** I don't have information about that topic; it's best to hand off to a human agent.

**Base (`gpt-4o`)** — rel 1, adh 2  ·  _The AI provided an invented answer instead of handing off to a human as instructed in the reference._  
> Yes, we do ship internationally to many countries. Shipping costs and delivery times vary depending on the destination. At checkout, you can enter your shipping address to see the available options, costs, and estimated delivery times for your location. 

If you have a specific country in mind and need more details, let me know, or I can connect you with a human agent for further assistance.

**Fine-tuned (`gpt-4o-ft`)** — rel 3, adh 4  ·  _The AI correctly offers to hand off to a human agent but includes irrelevant shipping details not mentioned in the reference._  
> The policy information provided does not specify whether the store ships internationally. Shipping details only mention a standard shipping time of 3 to 5 business days and an express shipping option that takes 24 to 48 hours with an additional cost of $9.99. For confirmation about international shipping, I can connect you to a human agent who can assist further. Would you like me to do that?

### 7. My product broke after 6 months, is it covered?

**Ground truth:** Yes, the 2-year warranty covers manufacturing defects.

**Base (`gpt-4o`)** — rel 2, adh 4  ·  _The AI answer incorrectly states a 1-year warranty instead of the correct 2-year warranty. It does offer to connect to a human agent, adhering to task expectations._  
> That depends on the warranty policy for the product you purchased. Many products come with a standard 1-year manufacturer warranty, but this can vary. If the product is still within the warranty period and the issue is due to a manufacturing defect, it may be covered.

Please check the warranty details provided with your product or in your order confirmation email. If you're unsure or need further assistance, I can connect you with a human agent to review your specific case. Let me know how you'd like to proceed!

**Fine-tuned (`gpt-4o-ft`)** — rel 5, adh 5  ·  _The AI correctly states the 2-year warranty coverage for manufacturing defects and offers appropriate next steps, adhering to the support agent role._  
> Yes, your product is covered under the 2-year warranty for manufacturing defects since it broke after 6 months. This warranty covers defects in manufacturing within that period. If you want to proceed, you can initiate a warranty claim for repair or replacement. Let me know if you need help with the next steps.

### 8. How much does express shipping cost and how long does it take?

**Ground truth:** Express shipping takes 24-48 h and costs an additional $9.99.

**Base (`gpt-4o`)** — rel 2, adh 4  ·  _The AI answer provides incorrect timeframes and costs, deviating from the reference. However, it offers to connect to a human agent, aligning with task adherence._  
> The cost and delivery time for express shipping depend on your location and the items in your order. Typically, express shipping takes 1-3 business days. 

To get an exact cost, please check the shipping options at checkout or provide your location and order details so we can assist further. If you need more specific information, I can connect you with a human agent. Let me know!

**Fine-tuned (`gpt-4o-ft`)** — rel 5, adh 4  ·  _The AI correctly states the cost and timeframe for express shipping but includes unnecessary information about standard shipping, which was not asked._  
> Express shipping costs $9.99 and takes 24 to 48 hours for delivery. Standard shipping, by comparison, takes 3 to 5 business days.

