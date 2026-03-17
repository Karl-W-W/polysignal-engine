# DGX Spark workload optimization for an autonomous AI trading agent

**The DGX Spark's 128GB unified memory can host a complete trading agent stack — a 70B LLM, an 8B reasoning model, embedding models, and XGBoost — simultaneously within ~65GB, leaving ample headroom.** The critical constraint is not memory but the **273 GB/s bandwidth**, which caps large-model decode at ~4–5 tok/s for 70B models. This shapes every architectural decision: use smaller, faster models for latency-sensitive tasks, and reserve the 70B model for deep analysis during market lulls. The unified memory architecture eliminates GPU↔CPU transfer overhead, making DGX Spark uniquely suited for multi-model workloads that would choke on discrete GPU VRAM limits.

---

## 1. vLLM vs Ollama: Ollama for stability, vLLM for throughput

Both engines deliver nearly identical single-stream decode for Llama 3.3 70B on DGX Spark — approximately **3.7–4.4 tok/s** — because the 273 GB/s bandwidth is the binding constraint, not the serving framework. The choice between them hinges on your concurrency needs and tolerance for setup complexity.

**Ollama works out-of-the-box** on DGX Spark and remains the only fully stable option without custom compilation. Official benchmarks show Llama 3.1 70B (q4_K_M) at **1,911 tok/s prefill / 4.4 tok/s decode**, with the newer GPT-OSS 120B (MXFP4) hitting **41 tok/s decode** thanks to hardware-accelerated mixed-precision. Ollama natively handles multiple concurrent models via `OLLAMA_MAX_LOADED_MODELS=3`, automatically managing load/unload based on available memory. It exposes a full OpenAI-compatible API at `/v1/chat/completions` and supports up to `OLLAMA_NUM_PARALLEL=8` concurrent request slots per model.

**vLLM requires a custom build** — prebuilt binaries lack sm_121 (GB10) kernel support. Three paths exist: NVIDIA's official container (`nvcr.io/nvidia/vllm:26.02-py3`), the community Docker image (`avarok/vllm-dgx-spark:v11`), or the one-command source build from `eelbaz/dgx-spark-vllm-setup` (~20–30 min compile). Once running, vLLM's advantage is dramatic under concurrent load: at **4 concurrent users**, prefill throughput scales to **9,616 tok/s** (3× single-user) via continuous batching and PagedAttention. Red Hat benchmarks on comparable hardware show vLLM delivering **3.7–4.3× aggregate throughput** over Ollama. vLLM also supports NVFP4 quantization natively (hardware-accelerated on Blackwell, <1% accuracy loss vs FP8) and FP8 KV caches for memory efficiency.

**Recommended configuration for each:**

```bash
# Ollama — production config for trading agent
export OLLAMA_MAX_LOADED_MODELS=3
export OLLAMA_NUM_PARALLEL=4
export OLLAMA_KEEP_ALIVE=30m
export OLLAMA_FLASH_ATTENTION=1
ollama serve &

# vLLM — DGX Spark launch (community image)
docker run -d --gpus all --ipc=host -p 8000:8000 \
  -e VLLM_FLASHINFER_MOE_BACKEND=latency \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  avarok/vllm-dgx-spark:v11 \
  serve nvidia/Llama-3.3-70B-Instruct-NVFP4 \
  --quantization modelopt_fp4 --kv-cache-dtype fp8 \
  --max-model-len 4096 --gpu-memory-utilization 0.45
```

**The verdict:** Start with **Ollama** for rapid iteration and multi-model convenience. Migrate latency-critical endpoints to **vLLM** once you need concurrent batching or plan to scale. For maximum single-stream performance, consider **TensorRT-LLM** (NVIDIA's highest-optimized path, with NVFP4/MXFP4 native support). For the specific use case of a trading agent that sends intermittent queries rather than sustaining high concurrency, Ollama is the pragmatic choice.

---

## 2. LoRA fine-tuning with 472 samples is viable — with guardrails

**Fine-tuning with ~472 samples works, and LoRA actually outperforms full fine-tuning at this scale.** NVIDIA's own documentation targets "100–1,000 prompt-sample pairs" for LoRA/QLoRA, and research consistently shows PEFT methods prevent overfitting better than full fine-tuning below 1,000 examples. The QLoRA paper demonstrated that 9K high-quality samples outperformed 450K lower-quality ones, and the LIMA paper showed strong results with just 1,000. Quality dominates quantity.

The primary risk is **overfitting and catastrophic forgetting**. Sebastian Raschka observed performance degradation even at 2 epochs with 1K samples. For 472 samples, aggressive regularization is non-negotiable:

| Hyperparameter | Recommended value | Rationale |
|---|---|---|
| LoRA rank (r) | **8** | Lower rank limits capacity, reduces overfitting |
| LoRA alpha | **16** (2×r) | Standard scaling convention |
| Dropout | **0.1** | Critical for small datasets |
| Learning rate | **2e-4** | Unsloth default; reduce to 5e-5 if validation loss spikes |
| Epochs | **1–2** (max 3) | More epochs → memorization at this scale |
| Batch size | **1** per device, gradient accumulation **16** | Noise from small batches helps regularization |
| Weight decay | **0.05** | AdamW regularization |
| Max gradient norm | **0.3** | Prevents exploding gradients |
| Target modules | All linear layers | `q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj` |

**Data augmentation should be your first step.** Use a stronger model (GPT-4, Claude, or the base instruct model itself) to generate 2–3 paraphrases per training example, plus alternate valid responses. NeurIPS 2024 research from Scale AI found this most beneficial in low-resource settings. Target **1,000–2,000 augmented samples** total, then manually review ~10–20% for quality. LLM-based paraphrasing outperforms traditional augmentation in 56% of tested cases.

**DGX Spark fine-tuning is remarkably fast.** NVIDIA benchmarks show QLoRA on Llama 3.3 70B at **5,079 tok/s** and LoRA on Llama 3.1 8B at **53,658 tok/s**. For 472 samples averaging 512 tokens each, expect **5–15 minutes total** for a 70B QLoRA run and **under 5 minutes** for an 8B model. This enables rapid experimentation.

Three tools are officially supported on DGX Spark, all requiring Docker due to ARM64/sm_121 compatibility:

- **Unsloth** (recommended): NVIDIA-partnered, 2× faster training, dedicated DGX Spark Dockerfile. Supports models up to 200B. Build via `wget -O Dockerfile "https://raw.githubusercontent.com/unslothai/notebooks/main/Dockerfile_DGX_Spark"` then `docker build -t unsloth-dgx .`
- **HuggingFace PEFT + TRL**: Fully supported via NVIDIA's PyTorch container (`nvcr.io/nvidia/pytorch:25.09-py3`). Standard `pip install transformers peft datasets trl bitsandbytes` inside the container.
- **NVIDIA NeMo**: Official playbook at `build.nvidia.com/spark/nemo-fine-tune`. Native FP8 precision optimizations for Blackwell.

QLoRA memory for 70B on DGX Spark: **~46–60GB** (4-bit weights ~35GB + optimizer states + KV cache + gradients), fitting comfortably within 128GB and leaving room for inference workloads alongside training.

---

## 3. XGBoost GPU runs on ARM64, but CPU may win for small financial datasets

**XGBoost v3.1.3+ ships pre-built ARM64 CUDA wheels on PyPI**, making installation trivial: `pip install xgboost`. The GPU tree method (`device="cuda"`, `tree_method="hist"`) works identically on aarch64 and x86_64. For DGX Spark's sm_121 architecture, XGBoost's standard CUDA kernels will JIT-compile from PTX at first run — unlike LLM frameworks, XGBoost doesn't use architecture-specific tensor core instructions.

However, **GPU acceleration provides minimal benefit for typical financial datasets (10K–100K rows)**. The overhead of GPU kernel launches exceeds the compute benefit at these scales:

| Dataset size | Features | Typical GPU speedup | Recommendation |
|---|---|---|---|
| ~10K rows | 30–100 | **~1× (no speedup)** | Use CPU |
| ~50K–100K rows | 100+ | **~1.5–2×** | GPU marginal; CPU competitive |
| ~500K+ rows | 100+ | **~4–8×** | GPU clearly wins |
| ~10M+ rows | 100+ | **~10–22×** | GPU essential |

DGX Spark's unified memory does provide one unique advantage: **zero CPU↔GPU transfer overhead**. On discrete GPUs, the PCIe data transfer is often the bottleneck for small datasets. With NVLink-C2C unified memory, this penalty disappears, potentially lowering the crossover point where GPU becomes beneficial.

**For a trading agent, the best strategy is CPU XGBoost with all 20 ARM cores for training/inference on market data, reserving the GPU for LLM workloads.** GPU XGBoost becomes valuable for hyperparameter search (hundreds of cross-validation folds) even on smaller datasets.

```python
import xgboost as xgb

# CPU — optimal for financial datasets <500K rows
clf = xgb.XGBClassifier(
    tree_method="hist", device="cpu", nthread=20,
    max_depth=8, learning_rate=0.1, n_estimators=500
)

# GPU — use for hyperparameter tuning or large datasets
clf_gpu = xgb.XGBClassifier(
    tree_method="hist", device="cuda",
    max_depth=8, learning_rate=0.1, n_estimators=500
)
```

**RAPIDS cuML also supports ARM64** (`pip install cuml-cu12`) with 50+ GPU-accelerated ML algorithms including random forest and scikit-learn acceleration. The `python -m cuml.accel your_script.py` command provides zero-code-change sklearn acceleration. Potential CUDA 13.0 vs 12.x linking issues may require RAPIDS nightly builds.

---

## 4. Embedding models: Qwen3-Embedding-0.6B is the sweet spot for a trading stack

The **Qwen3-Embedding** family leads MTEB benchmarks (the 8B variant scores **70.58**, #1 on multilingual MTEB as of June 2025) and supports Matryoshka Representation Learning for flexible dimensionality (32–4,096). For a trading agent on DGX Spark, the **0.6B variant** offers the best quality-per-GB: ~1.5GB VRAM for near-state-of-the-art embeddings, leaving memory for everything else.

A critical finding from the **FinMTEB benchmark** (EMNLP 2025): general-purpose embedding models are **poor predictors of financial task performance**. Domain-specific models like **Fin-E5** and **BGE Base Financial Matryoshka** significantly outperform general models on financial retrieval, clustering, and classification. For a trading agent, consider fine-tuning BGE-base on your financial corpus — the Matryoshka approach allows dimension reduction at inference time without retraining.

**Serving framework options** on DGX Spark:

- **Ollama** (simplest): `ollama pull qwen3-embedding` then call `/api/embed`. Supports batching. No continuous batching or high-concurrency optimization.
- **vLLM** (production): Supports `--task embed` for decoder-only embedding models. Confirmed working on DGX Spark with Qwen3-Embedding-8B via the community container. OpenAI-compatible `/v1/embeddings` endpoint.
- **TEI (Text Embeddings Inference)**: **Not supported on ARM64** — open GitHub issues #769 and #657 confirm no ARM64 GPU Docker images. Avoid until HuggingFace adds support.
- **sentence-transformers**: Works for simpler deployments via Python directly.

**Estimated throughput on DGX Spark** (embedding is prefill-only, no autoregressive generation):

| Model | VRAM | Throughput (batched) | Latency/query |
|---|---|---|---|
| nomic-embed-text (137M) | ~0.3 GB | 500–1,000 embed/s | <5ms |
| BGE-M3 (568M) | ~3.4 GB | 100–300 embed/s | 15–40ms |
| Qwen3-Embedding-0.6B | ~1.5 GB | 50–150 embed/s | 20–60ms |
| Qwen3-Embedding-8B (FP16) | ~18 GB | 10–40 embed/s | 50–200ms |

**Recommended financial RAG embedding stack**: Qwen3-Embedding-0.6B (general) + BGE Base Financial Matryoshka (finance-specific) = **~2GB total**, leaving 126GB for LLMs and infrastructure.

---

## 5. Real-time financial analysis: DGX Spark fits intraday trading, not HFT

**LLM-based trading agents are actively deployed on hardware like DGX Spark, but exclusively for intraday-to-position trading horizons.** No LLM can operate at HFT microsecond scales. The sweet spot for LLM trading agents is the **30-minute to multi-day decision cycle**, where the 15–60 seconds for a full multi-agent analysis pipeline is acceptable.

Achievable latencies on DGX Spark:

- **Headline sentiment classification** (FinBERT, 110M): **<10ms** — suitable for real-time news screening
- **Sentiment with LLM** (Llama 8B NVFP4, 50 tokens in / 20 out): **~70ms total**
- **Article summarization** (Llama 70B FP4, 2K tokens in / 256 out): **~8 seconds**
- **Full multi-agent analysis** (4 analyst agents + decision agent, 14B model): **15–60 seconds**

The dominant architecture pattern is the **multi-agent trading system**, exemplified by TradingAgents (UCLA/MIT) and FinRobot (AI4Finance Foundation). These run parallel analyst agents — fundamental, sentiment, news, and technical — whose outputs feed a structured debate between bull/bear researchers, culminating in a trader agent's decision filtered through risk management. This architecture maps naturally to DGX Spark's multi-model capability: a fast 8B model handles real-time screening while a 70B model conducts deeper analysis.

**The hybrid LLM + ML approach consistently outperforms either alone.** FinGPT excels at sentiment classification (F1: 87.6%, headline accuracy: 95.5%) but struggles with complex financial reasoning (QA exact match: 28.5% vs GPT-4's 76%). The optimal architecture combines FinBERT/FinGPT for structured classification, a general 70B model for reasoning, XGBoost for price prediction, and an RL agent (A2C, PPO) for trade execution — with LLM-generated sentiment scores as additional features in the XGBoost/RL feature space.

Key open-source frameworks to build on: **FinGPT** (18.8K GitHub stars, financial LLMs), **FinRL** (14.2K stars, RL trading), **FinRobot** (6.4K stars, agent platform with Chain-of-Thought financial reasoning), and **TradingAgents** (multi-agent LangGraph framework with explicit Ollama support via `llm_provider: "ollama"`).

---

## 6. Multi-model serving: a 128GB memory budget that actually works

DGX Spark's unified memory is simultaneously its greatest advantage and its most dangerous trap. The 128GB pool is shared between CPU and GPU with no hardware partitioning — meaning **GPU OOM manifests as a full system freeze** (SSH hangs, no clean error, hard reboot required), not a recoverable CUDA error. Memory management discipline is essential.

**Concrete memory budget for a trading agent stack:**

| Component | Memory allocation |
|---|---|
| Llama 3.3 70B (NVFP4/INT4) | ~38 GB |
| KV cache for 70B (4K context, 2 parallel slots) | ~2.5 GB |
| Llama 8B reasoning model (INT4) | ~5 GB |
| KV cache for 8B | ~0.5 GB |
| Qwen3-Embedding-0.6B | ~1.5 GB |
| BGE Financial Matryoshka | ~0.5 GB |
| XGBoost + feature pipeline | ~1 GB |
| Vector DB + Redis | ~2 GB |
| CUDA runtime + framework overhead | ~5 GB |
| OS + Docker + system services | ~9 GB |
| **Total allocated** | **~65 GB** |
| **Safety buffer** | **~63 GB** |

This budget is conservative. The key rules: always set vLLM's `--gpu-memory-utilization` to **0.45 or lower per instance** (NVIDIA officially warns against the default ~1.0 on UMA systems), and ensure the sum across all vLLM instances stays **≤0.70**. Flush buffer caches before launching the stack (`sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'`). Monitor with `free -h`, not `nvidia-smi` (which shows "N/A" for memory on unified memory systems).

**MIG is not supported on DGX Spark** — NVIDIA confirmed this has no firmware path to enablement. Use application-level memory management instead: Ollama's built-in multi-model scheduler or separate vLLM instances with controlled memory fractions behind an Nginx gateway.

A practical Docker Compose stack for the full trading agent:

```yaml
version: "3.8"
services:
  ollama:
    image: ollama/ollama:latest
    runtime: nvidia
    environment:
      - OLLAMA_MAX_LOADED_MODELS=3
      - OLLAMA_NUM_PARALLEL=4
      - OLLAMA_KEEP_ALIVE=30m
      - OLLAMA_FLASH_ATTENTION=1
    volumes:
      - ollama_data:/root/.ollama
    ports:
      - "11434:11434"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]

  trading-agent:
    build: ./agent
    depends_on: [ollama, vectordb, redis]
    environment:
      - OLLAMA_BASE_URL=http://ollama:11434
      - MAIN_MODEL=llama3.3:70b-instruct-q4_K_M
      - FAST_MODEL=llama3.1:8b-instruct-q4_K_M
      - EMBED_MODEL=qwen3-embedding
    ports:
      - "8000:8000"

  vectordb:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: trading_knowledge
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

volumes:
  ollama_data:
  pgdata:
  redis_data:
```

## Conclusion

The DGX Spark can host an entire autonomous trading agent — from embedding and retrieval through reasoning to trade signal generation — on a single **$4,699 device drawing ~240W**. The architectural key is **model tiering**: FinBERT (<10ms) for real-time headline screening, an 8B model (~70ms) for fast sentiment and routing, and the 70B model (~8s for article analysis) for deep financial reasoning, all coexisting in 128GB unified memory with ~60GB to spare.

Three insights emerge that aren't obvious from spec sheets. First, the **273 GB/s bandwidth bottleneck makes model selection more important than framework selection** — switching from Ollama to vLLM gains little at batch-size-1, but dropping from 70B to a high-quality 14B model can 4× your decode speed. Second, **472 training samples are enough for LoRA fine-tuning** if you augment to ~1K–2K samples and use aggressive regularization (r=8, dropout=0.1, 1–2 epochs), with training completing in under 15 minutes on DGX Spark. Third, **CPU XGBoost with 20 ARM cores will likely outperform GPU XGBoost** on financial datasets under 500K rows, so reserve GPU compute for LLM inference where it matters most. The unified memory architecture means these workloads coexist without the VRAM fragmentation that plagues discrete GPU setups.