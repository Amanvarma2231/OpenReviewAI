# OpenReview AI — Models & Licenses Reference

## 1. Open-Source Software vs. Open-Weight Models

In contemporary AI engineering, it is essential to distinguish between **Open-Source Software (OSS)** and **Open-Weight Models**:

- **Open-Source Software (OSI-Approved):** Software distributed under licenses approved by the Open Source Initiative (OSI), such as MIT, Apache 2.0, BSD, or GPL. These licenses grant unrestricted rights to study, modify, compile, distribute, and commercialize the source code.
- **Open-Weight Models:** Deep learning neural network weights published for public download. While many open-weight models allow commercial use, their custom licenses frequently incorporate restrictions (e.g., prohibition of using model outputs to train competing models, usage caps above a certain number of monthly active users, or acceptable use policies). **They are not strictly OSI-approved open-source software unless explicitly licensed under Apache 2.0 or MIT.**

OpenReview AI runs exclusively with **locally hosted, open-weight models** through Ollama and adheres strictly to each model family's specific license terms.

---

## 2. Supported Model Families & License Audit

| Model Family | Variant Name | Parameter Size | Download Size | License Type | Commercial Use | License Reference |
|:---|:---|:---|:---|:---|:---|:---|
| **Qwen 2.5** | `qwen2.5:0.5b` | 0.5 Billion | ~397 MB | **Apache 2.0** | ✅ Permitted | [Alibaba Qwen License](https://github.com/QwenLM/Qwen2.5/blob/main/LICENSE) |
| **Qwen 2.5 Coder** | `qwen2.5-coder:1.5b` | 1.5 Billion | ~980 MB | **Apache 2.0** | ✅ Permitted | [Alibaba Qwen License](https://github.com/QwenLM/Qwen2.5-Coder/blob/main/LICENSE) |
| **Qwen 2.5 Coder** | `qwen2.5-coder:3b` | 3.0 Billion | ~1.9 GB | **Qwen Research License** | ✅ Permitted (<100M MAU) | [Qwen Terms of Use](https://huggingface.co/Qwen/Qwen2.5-Coder-3B) |
| **DeepSeek Coder** | `deepseek-coder:1.3b` | 1.3 Billion | ~776 MB | **DeepSeek License** | ✅ Permitted | [DeepSeek Coder License](https://github.com/deepseek-ai/DeepSeek-Coder/blob/main/LICENSE-MODEL) |
| **DeepSeek Coder** | `deepseek-coder:6.7b` | 6.7 Billion | ~3.8 GB | **DeepSeek License** | ✅ Permitted | [DeepSeek Coder License](https://github.com/deepseek-ai/DeepSeek-Coder/blob/main/LICENSE-MODEL) |
| **Gemma 2** | `gemma2:2b` | 2.6 Billion | ~1.6 GB | **Gemma Terms of Use** | ✅ Permitted (Responsible AI) | [Google Gemma License](https://ai.google.dev/gemma/terms) |
| **Mistral** | `mistral:7b` | 7.2 Billion | ~4.1 GB | **Apache 2.0** | ✅ Permitted | [Mistral AI Apache 2.0](https://github.com/mistralai/mistral-src/blob/main/LICENSE) |

> [!NOTE]
> **Clarification on "Bonsai":**  
> "Bonsai" does not refer to an industry-standard open-weight foundation model. In OpenReview AI, all model names are strictly configurable via the UI or `WorkflowConfig(generator_model=...)`. Users can supply any custom Ollama model tag or quantized GGUF model present in their local runtime.

---

## 3. Hardware Requirements & Recommended Profiles (16 GB RAM)

OpenReview AI is optimized for developer machines with **16 GB of unified RAM**:

### Recommended Local Pairings:

1. **Ultra-Lightweight / Low Memory Profile (Total VRAM/RAM < 2 GB):**
   - **Agent A (Generator):** `qwen2.5:0.5b` (397 MB)
   - **Agent B (Reviewer):** `deepseek-coder:1.3b` (776 MB)
   - **Agent C (Validator):** Deterministic AST & Subprocess sandbox (0 MB VRAM)
   - *Best for machines running background IDEs, browser tabs, and multiple services.*

2. **Balanced Code Engineering Profile (Total VRAM/RAM ~ 3.5 GB):**
   - **Agent A (Generator):** `qwen2.5-coder:1.5b` (980 MB)
   - **Agent B (Reviewer):** `deepseek-coder:1.3b` (776 MB)
   - *Provides excellent syntax accuracy and edge case detection with fast token generation.*

3. **High-Accuracy Profile (Total VRAM/RAM ~ 6 GB):**
   - **Agent A (Generator):** `qwen2.5-coder:3b` (1.9 GB)
   - **Agent B (Reviewer):** `deepseek-coder:6.7b` or `qwen2.5-coder:1.5b`
   - *Recommended when running on discrete GPUs (NVIDIA RTX 3060/4060 with 6GB–8GB VRAM).*

4. **Zero-GPU / Offline Profile (Total RAM < 100 MB):**
   - **Agent A & B:** `⚡ Smart Simulator` (`mock` provider)
   - *Instant evaluation of multi-agent loops, AST verification, subprocess testing, diff generation, and report persistence without downloading model weights.*

---

## 4. Sequential Inference & Memory Protection

To ensure smooth operation on 16 GB machines without triggering Windows Out-Of-Memory (OOM) paging or system freezes:
- OpenReview AI executes agent inference **sequentially** rather than concurrently. Agent A finishes drafting before Agent B evaluates, and Agent B completes before Agent C arbitrates.
- Model context window is constrained to 4096 tokens by default.
- Temperature is locked to 0.2 to avoid degenerative token loops.
- Ollama automatically swaps model weights out of memory when idle.
