# DGX Spark Maximization — What the Hardware Can Actually Do
# Source: KWW research (Session 26, 2026-03-16)
# For Loop: Read this, extract actionable items to LEARNINGS_TO_TASKS.md

## Our Hardware: GB10 Grace Blackwell Superchip

- **GPU**: 1 PFLOP FP4 sparse, 250 TFLOP FP8
- **Memory**: 128GB unified LPDDR5X (CPU + GPU share same physical RAM)
- **Bandwidth**: 273 GB/s (bottleneck for LLM decode)
- **CPU**: 20-core ARM Grace
- **NVMe**: 4TB
- **Current utilization**: ~5% (we're barely using this machine)

## Real Benchmarks (Not Marketing)

### Ollama (what we run)
| Model | Quant | Prefill tok/s | Decode tok/s |
|-------|-------|--------------|-------------|
| GPT-OSS 20B | MXFP4 | 3,224 | 58.27 |
| GPT-OSS 120B | MXFP4 | 1,169 | 41.14 |
| Llama 3.1 8B | Q4_K_M | 7,614 | 38.02 |
| DeepSeek-R1 14B | Q4_K_M | 5,919 | 19.99 |
| Qwen3 32B | Q4_K_M | 705 | 9.41 |
| Llama 3.1 70B | Q4_K_M | 1,911 | 4.42 |

### Key Insight: Batching
- Llama 3.1 8B at batch=32: **368 tok/s** total (18x improvement over batch=1)
- DGX Spark excels as inference SERVER, not single-user chat
- DeepSeek-R1 14B at FP8 batch=8: 83.5 tok/s decode

### MoE is the Sweet Spot
GPT-OSS 120B at 41-55 tok/s because only ~20B active params per token. This is surprisingly usable for interactive work.

## Memory Budget (What Fits)

After OS overhead: ~120GB available for models.

| Quantization | Max Dense Model | Example |
|-------------|----------------|---------|
| FP16 (2B/param) | ~55B | Llama 70B won't fit |
| FP8 (1B/param) | ~110B | Llama 70B fits with 48GB left for KV |
| FP4/Q4 (0.5B/param) | ~200B | Llama 70B @ Q4 = 35GB, 83GB free |

**Two DGX Sparks (256GB via 200GbE)**: Qwen3 235B, Llama 405B confirmed.

## What We Should Actually Run

### Tier 1: Replace Ollama with TensorRT-LLM (2-5x faster)
```bash
docker pull nvcr.io/nvidia/tensorrt-llm/release:1.2.0rc6
# Simple serve:
trtllm-serve --model meta-llama/Llama-3.1-8B-Instruct
```
- Exploits Blackwell's native FP4 tensor cores
- Official DGX Spark containers exist

### Tier 2: Multi-Model Serving (~60GB Combined Budget)
Run simultaneously:
- GPT-OSS 20B (~11GB) — Loop's primary model for tasks
- Qwen3-Coder 30B (~17GB) — code generation
- Embedding model for MoltBook intelligence

**Don't** try to run GPT-OSS 120B alongside another large model (performance collapses).

### Tier 3: Fine-Tuning (Already Possible)
Confirmed working on DGX Spark:
- Full fine-tune: Llama 3.2 3B @ BF16 (82K tok/s)
- LoRA: Llama 3.1 8B @ BF16 (53K tok/s)
- **QLoRA: Llama 3.3 70B @ FP4 (5K tok/s)** ← this is our opportunity
- Unsloth has official DGX Spark Docker image

### Tier 4: PyTorch via NGC Container
pip wheel doesn't support Blackwell sm_121. Must use NGC:
```bash
docker pull nvcr.io/nvidia/pytorch:25.03-py3
docker run --gpus all -it --rm \
  -v /opt/loop:/opt/loop \
  --ipc=host \
  nvcr.io/nvidia/pytorch:25.03-py3 bash
```
**Needs NGC API Key** from https://ngc.nvidia.com/

## Bandwidth vs Capacity Tradeoff

The DGX Spark's 273 GB/s is:
- 3.7x less than RTX 4090 (1,008 GB/s)
- 7.5x less than A100 (2,039 GB/s)

This means single-user decode is SLOW for large models. But:
- Prefill is FAST (tensor cores dominate)
- Batched inference is EFFICIENT (shared model weights, parallel KV)
- **Capacity wins**: We can run models no consumer GPU can even load

### Optimal Pairing (Future)
EXO Labs showed: DGX Spark for prefill + Mac for decode = **2.8x speedup**.
NVLink-C2C between CPU and GPU = ~600 GB/s bidirectional.

## Practical Limitations

- **Thermal**: Some units throttle. Ours runs at 28-48°C (good). Keep firmware updated.
- **ARM64**: Some x86 wheels unavailable. Prefer NGC containers over building from source.
- **Context length**: 32K context drops speed ~30% from 16K (growing KV cache).
- **No MIG**: Single GPU, can't partition. Multiple containers share via CUDA time-sharing.
- **mmap double memory**: HuggingFace Transformers uses mmap which wastes unified memory. Disable mmap or use specialized loading.

## Our Action Items

1. **Install TensorRT-LLM** for GPT-OSS 20B/120B (2-5x faster than Ollama)
2. **NGC API Key** needed from NVIDIA (human task)
3. **Try QLoRA fine-tuning** of prediction model on our labeled data
4. **Multi-model serving**: Run cheap model for heartbeats + expensive for tasks
5. **Disable swap** (16GB active, only 137MB used — wastes NVMe bandwidth)
