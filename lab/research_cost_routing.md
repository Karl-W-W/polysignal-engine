# OpenClaw model routing cuts costs by 80–95%

**Routing heartbeats and simple tasks to cheaper models — or running them locally — eliminates the single largest source of wasted spend in OpenClaw deployments.** Community audits consistently find that **90% of total token spend is overhead** (heartbeats, context re-injection, system prompts), not productive work. By combining tiered model routing, prompt caching, and isolated heartbeat sessions, users report dropping from $300–600/month to under $20/month. This report lays out exact pricing, tooling, and configuration to achieve those savings.

---

## The heartbeat problem: 2–3 million tokens per day doing nothing

OpenClaw's heartbeat mechanism — a periodic agent turn that checks for pending tasks — is the dominant cost driver for idle agents. By default, each heartbeat sends the **full main-session context** (chat history, AGENTS.md, SOUL.md, MEMORY.md, tool schemas) to the LLM. Unoptimized heartbeats consume **170K–210K tokens per run**, and with the default 30-minute interval, that adds up to **2–3 million tokens per day** just for background monitoring.

At Sonnet 4.6 pricing ($3/$15 per MTok input/output), heartbeats alone cost **$1–3/day**. At Opus 4.6 rates ($5/$25 per MTok), it reaches **$5/day or ~$150/month**. One user reported burning $50 in a single day after configuring 5-minute email checks. The math is brutal: 38 calls/day × 12K tokens × $15/MTok (Opus input) = **$6.84/day** just for heartbeats.

The fix is straightforward. Setting `isolatedSession: true` and `lightContext: true` in the heartbeat configuration collapses each heartbeat to **2K–5K tokens** by injecting only HEARTBEAT.md instead of the full bootstrap. Combined with routing heartbeats to Haiku 4.5 ($1/$5 per MTok), daily heartbeat cost drops to roughly **$0.15/day** — a **45× reduction**.

---

## Current Anthropic pricing and where the savings stack

The three Claude tiers relevant to OpenClaw routing have clean, predictable pricing as of March 2026:

| Model | Input / MTok | Output / MTok | Batch Input | Batch Output |
|-------|-------------|--------------|-------------|--------------|
| **Claude Opus 4.6** | $5.00 | $25.00 | $2.50 | $12.50 |
| **Claude Sonnet 4.6** | $3.00 | $15.00 | $1.50 | $7.50 |
| **Claude Haiku 4.5** | $1.00 | $5.00 | $0.50 | $2.50 |

Notably, Opus 4.6 and Sonnet 4.6 (released February 2026) retained the same pricing as their 4.5 predecessors while removing the long-context surcharge — the full **1M-token context window** now costs the same as standard rates. The Batch API provides a flat **50% discount** across all models with no minimum volume.

**Prompt caching** is the most impactful single optimization for OpenClaw. Since heartbeats and conversation turns re-send identical system prompts, cache reads replace full input processing at **90% off**:

| Model | Standard Input | Cache Read (hit) | Cache Write (5m) | Cache Write (1h) |
|-------|---------------|-----------------|-------------------|-------------------|
| Opus 4.6 | $5.00/MTok | **$0.50/MTok** | $6.25/MTok | $10.00/MTok |
| Sonnet 4.6 | $3.00/MTok | **$0.30/MTok** | $3.75/MTok | $6.00/MTok |
| Haiku 4.5 | $1.00/MTok | **$0.10/MTok** | $1.25/MTok | $2.00/MTok |

Cache reads break even after just **2 hits** on either TTL tier, and the discounts **stack with Batch API pricing**. This means Batch + cache read for Sonnet 4.6 drops input cost to **$0.15/MTok** — a 95% reduction from the standard $3.00 rate. For the 5-minute TTL, each cache hit refreshes the TTL at no extra cost, so frequent heartbeats actually keep the cache warm. The 1-hour extended TTL (requiring the `extended-cache-ttl-2025-04-11` beta header) costs 2× base input to write but enables the openclaw-token-optimizer's strategy of setting heartbeat intervals to 55 minutes to stay within the TTL window.

One important constraint: Opus 4.6 and Haiku 4.5 require a **4,096-token minimum** for cache eligibility, while Sonnet models need only 1,024 tokens. OpenClaw's typical 5K–10K-token system prompt clears both thresholds.

---

## Three ClawHub tools for automated routing

The OpenClaw ecosystem offers three distinct approaches to model routing, each with different trade-offs:

**openclaw-token-optimizer** is the most OpenClaw-specific tool. It's a one-shot patcher (not a runtime proxy) that modifies your OpenClaw installation to enable native prompt caching with `cache_control: ephemeral` markers, replaces static tool-schema injection with a lazy-loading `search_available_tools(query)` meta-tool, and includes a `model_router.py` script for complexity-based Haiku→Sonnet→Opus escalation with budget-aware fallback. It claims **50–80% cost reduction**, with context optimization being the biggest contributor. The project is very new (22 ClawHub stars, 6 GitHub commits) and carries risk since it modifies core config files — always back up first.

**ClawRouter by BlockRunAI** is the most mature option with **1,800 GitHub stars**. It performs 100% local routing via a 15-dimension weighted scoring system in under 1ms, classifying requests into four tiers (SIMPLE → MEDIUM → COMPLEX → REASONING) across 41+ models from multiple providers. It routes trivially ("What is 2+2?") to DeepSeek at $0.27/MTok and complex coding to Sonnet at $15/MTok, claiming **78% average savings**. The catch: it requires USDC micropayments on Base/Solana for authentication. The **cgaeking fork** removes the crypto dependency and uses direct provider API keys instead. The **donnfelker/claw-llm-router** variant runs as a local HTTP proxy on port 8401 with your own API keys.

**clawrouter.org** (a separate project) takes a more sophisticated approach with a 5-stage pipeline including a self-learning EMA-based scoring system and optional small-LLM classifier via Ollama. It supports 14 pre-configured models including all current Claude tiers, GPT-4.1, Gemini 2.5, and Llama 4. Its four routing policies (cheap, balanced, best, low_latency) map cleanly to OpenClaw use cases.

---

## OpenClaw's native model override has three entry points

OpenClaw provides built-in model switching without any plugins. The **`session_status(model=X)` tool call** lets the agent programmatically switch models, stored in `sessions.json`. A critical limitation: the switch takes effect on the **next message**, not the current one — by the time the agent reads an instruction to switch, it's already generating on the current model.

The **`/model` chat command** offers instant switching for users (`/model anthropic/claude-sonnet-4-5`), while the **CLI** supports `openclaw model set` for temporary overrides. Model presets in `openclaw.json` enable aliased switching between "cheap," "balanced," and "quality" tiers. The `per-spawn model override` through `sessions_spawn` allows sub-agents to run on different models than the parent session.

A persistent pain point: **stale overrides in `sessions.json`** silently persist and can override agent-configured models. One user's budget agent configured for cheap `gpt-5-nano` got silently pinned to `claude-opus-4-6`, burning premium tokens until they manually edited the session file. There's an open feature request (Issue #23254) for heartbeat-specific model routing with automatic escalation — currently achievable only via the third-party tools described above.

The recommended heartbeat configuration for cost optimization:

```json
{
  "agents": {
    "defaults": {
      "heartbeat": {
        "every": "30m",
        "lightContext": true,
        "isolatedSession": true,
        "model": "anthropic/claude-haiku-4-5",
        "escalateModel": "anthropic/claude-opus-4-6"
      }
    }
  }
}
```

---

## Llama 3.3 70B as a local zero-cost heartbeat engine

For users willing to run a local model, **Llama 3.3 70B eliminates heartbeat API costs entirely**. Its IFEval instruction-following score of **92.1** actually exceeds GPT-4o (84.6) and Claude 3.5 Sonnet (89.3), making it more than capable for trivial tasks like JSON parsing, status checks, and file reads. Its BFCL v2 tool-use score of 77.3 confirms solid function-calling ability. For structured JSON output with grammar-constrained generation (GBNF), it achieves **~100% compliance**.

The practical bottleneck is inference speed on consumer hardware. The NVIDIA DGX Spark, despite its **128GB unified memory** and $4,000 price point, delivers only **2.7–5 tokens/second** for decode due to its 273 GB/s memory bandwidth — barely usable for interactive work but adequate for background heartbeats where latency tolerance is high. An RTX 5090 (32GB) running Q4_K_M quantization achieves **40–50 tokens/second**, while an RTX 4090 requires aggressive 2–3 bit quantization that degrades quality. Via cloud API providers like Groq, Llama 3.3 70B runs at **276–317 tokens/second** at just **$0.10–0.15/MTok** — roughly 7–10× cheaper than Haiku 4.5 via Anthropic.

The comparison with Claude Haiku 4.5 is stark on cost: Llama 3.3 70B via DeepInfra costs **$0.10/MTok input** versus Haiku 4.5's **$1.00/MTok** — a 10× difference. Self-hosting eliminates per-token costs entirely but only makes economic sense above ~400M tokens/month to justify GPU rental, making it ideal specifically for high-frequency, low-complexity tasks like heartbeats.

| Deployment | Speed | Effective Cost | Best For |
|-----------|-------|---------------|----------|
| DGX Spark (local) | 2.7–5 tok/s | $0/token | Background heartbeats |
| RTX 5090 (local) | 40–50 tok/s | $0/token | Interactive + heartbeats |
| Groq API | 317 tok/s | $0.15/MTok blended | Fast, cheap API tasks |
| Claude Haiku 4.5 | Cloud-fast | $1.00/$5.00 MTok | When Anthropic features needed |

---

## Concrete cost modeling: from $600/month to $18/month

Consider a typical active OpenClaw deployment: 48 heartbeats/day, 50 productive interactions/day averaging 20K input tokens and 2K output tokens each.

**Unoptimized baseline (Sonnet 4.6 for everything):**
- Heartbeats: 48 × 200K tokens × $3/MTok = **$28.80/day input**
- Productive work: 50 × 20K × $3/MTok input + 50 × 2K × $15/MTok output = **$4.50/day**
- Total: **~$33/day → ~$1,000/month**

**Optimized with full routing stack:**
- Heartbeats on Haiku 4.5 with `lightContext` + prompt caching: 48 × 5K tokens × $0.10/MTok (cache read) = **$0.024/day**
- Simple tasks (60%) routed to Haiku 4.5 with caching: 30 × 8K × $0.10/MTok + 30 × 1K × $5/MTok = **$0.174/day**
- Complex tasks (40%) on Sonnet 4.6 with caching: 20 × 20K × $0.30/MTok + 20 × 3K × $15/MTok = **$1.02/day**
- Total: **~$1.22/day → ~$37/month**

Substituting Llama 3.3 70B via Groq for heartbeats and simple tasks drops the total further to roughly **$18/month** — a **98% reduction** from the unoptimized baseline.

The key levers, ranked by impact: **(1)** Isolated heartbeat sessions with `lightContext` (eliminates ~170K tokens per heartbeat), **(2)** prompt caching on the system prompt (90% input cost reduction on cache hits), **(3)** model tiering — Haiku or local for simple tasks, Sonnet for productive work, Opus only for complex reasoning, and **(4)** lazy tool loading via openclaw-token-optimizer to avoid injecting 50+ tool schemas on every turn.

---

## Conclusion

The OpenClaw cost optimization landscape has matured rapidly since the project's late-2025 release, but the ecosystem remains young and carries real risks — the ClawHavoc incident in February 2026 exposed **341 malicious skills** on ClawHub, underscoring the need to audit any third-party patcher before installation. The most reliable approach combines OpenClaw's native configuration (`lightContext`, `isolatedSession`, model presets) with Anthropic's prompt caching rather than depending heavily on third-party tools. For users processing hundreds of millions of tokens monthly, routing heartbeats to a local Llama 3.3 70B instance via Ollama or a cheap API provider like Groq is the most economically efficient path — the model's 92.1 IFEval score makes it overqualified for background monitoring tasks. The single highest-impact change remains the simplest: setting `lightContext: true` on heartbeats to collapse per-heartbeat token consumption from 200K to under 5K, which alone delivers a **40× cost reduction** before any model switching is applied.