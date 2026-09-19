# Choosing a model

**Catalog and price check: September 18, 2026.** These are starting recommendations, not a classroom benchmark. Compare the same lesson and sources on your own hardware. Measure factual errors, source fidelity, answer quality, editing time, latency, and total cost including retries.

Claw-ED uses the model you select. Task, tier, and vision overrides apply when configured. Generation retries keep the selected model; they no longer rotate automatically into cloud alternatives. Existing saved selections are preserved on upgrade, including an existing `openrouter_vision_model` value. Clear that optional setting to use your main OpenRouter model for images; `OLLAMA_VISION_MODEL` is the equivalent explicit local override. Failed or unsupported image checks omit the image rather than approve it.

## Local Ollama: start with the hardware you have

Local inference has no per-token provider charge. Hardware, electricity, and your time still cost something. Model downloads need internet; optional web search, images, and integrations remain separate network features. A `:cloud` model runs remotely even when selected through Ollama.

| Starting point | Ollama model ID | Suggested use |
| --- | --- | --- |
| 8 GB laptop, short context | `qwen3.5:4b` | Small drafts, rewriting, and a first local trial |
| 16 GB laptop | `qwen3.5:9b` | General drafting; the default for a new local configuration |
| 16–24 GB | `gemma4:12b` | Alternative for document and image-informed drafting |
| 24–32 GB | `gpt-oss:20b` | Text reasoning and tool use; compare against Qwen on the same task |
| 32 GB or more | `qwen3.8:27b` | A current larger local option for harder drafting and reasoning |

Memory ranges above are conservative starting estimates, not guarantees. Leave room for your OS and the context cache; start with short excerpts. For example, Ollama lists Qwen 3.5 4B/9B downloads at 3.4/6.6 GB and Qwen 3.8 27B at 18 GB. Download size is smaller than total runtime memory. Check the exact quantization, model license, and installed Ollama support before downloading.

Sources: [Qwen 3.5 library](https://ollama.com/library/qwen3.5), [Gemma 4 12B](https://ollama.com/library/gemma4:12b), [GPT-OSS 20B](https://ollama.com/library/gpt-oss:20b), [Qwen 3.8 27B](https://ollama.com/library/qwen3.8:27b). These families provide open weights; verify each model's license for your use rather than assuming every downloadable model has the same terms.

```bash
ollama pull qwen3.5:9b
clawed config set-model ollama --model qwen3.5:9b
```

Your Ollama endpoint must be local, normally `http://localhost:11434`. If you previously configured Ollama Cloud, change the endpoint in settings before treating a session as local.

## Cheap hosted options through OpenRouter

Start with **GPT-OSS 20B for a low-cost trial**, then compare **Gemma 4 31B** if the draft needs improvement. **Qwen 3.8 Flash** is another inexpensive current option. These recommendations are based on availability, capabilities, and advertised price, not a claim that one produces the best lessons.

| Model ID | Input / 1M tokens | Output / 1M tokens |
| --- | ---: | ---: |
| `openai/gpt-oss-20b` | $0.03 | $0.13 |
| `google/gemma-4-31b-it` | $0.09 | $0.34 |
| `qwen/qwen3.8-flash` | $0.15 | $0.47 |
| `qwen/qwen3.8-27b:free` | $0 | $0 |
| `google/gemma-4-31b-it:free` | $0 | $0 |

Prices are the advertised catalog rates at the check date; hosting routes, availability, fees, caching, and quotas can change. Free endpoints have limits and may be unavailable when needed. Hosted open-weight models still send your selected content to OpenRouter and the serving provider. Check their routing and data policies before using school material. [Live OpenRouter catalog](https://openrouter.ai/api/v1/models), [pricing and models](https://openrouter.ai/models).

Configure an OpenRouter API key in settings, then:

```bash
clawed config set-model openrouter --model openai/gpt-oss-20b
```

Ollama Cloud is another hosted option. Its plans have usage limits; Claw-ED does not promise unlimited lessons or a fixed cost per lesson. Check [current Ollama plans](https://ollama.com/pricing).

## Premium choices: GPT-6 Astra and Claude Fable 5.1

Use these deliberately for difficult unit design, complex source comparison, or a second review pass. A stronger model still needs the actual sources and teacher review.

| Provider | Direct API ID | OpenRouter ID | Standard input / output per 1M tokens |
| --- | --- | --- | --- |
| OpenAI | `gpt-6-astra` | `openai/gpt-6-astra` | $10 / $50 |
| Anthropic | `claude-fable-5-1` | `anthropic/claude-fable-5.1` | $10 / $50 |

Astra supports a 1.05M-token context and requires the Responses API for native tool calls; Claw-ED's OpenAI adapter uses that path. Fable 5.1 has a 1M-token context and always-on adaptive thinking; the adapter preserves its native content across tool turns. The adapters omit unsupported sampling parameters. Account access, retention rules, and rate limits still apply. Fable's documented 30-day retention requirement deserves particular attention before submitting school content. Sources: [OpenAI model specification](https://developers.openai.com/api/docs/models/gpt-6-astra), [Astra migration guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra), [Fable specification](https://platform.claude.com/docs/en/models/fable-5-1/overview), [Fable migration and retention requirements](https://platform.claude.com/docs/en/models/fable-5-1/migration-guide).

```bash
clawed config set-model openai --model gpt-6-astra
# Or:
clawed config set-model anthropic --model claude-fable-5-1
```

For a less expensive direct Anthropic option, [Claude Sonnet 5](https://platform.claude.com/docs/en/models/sonnet-5/overview) (`claude-sonnet-5`) is listed at $2 input / $10 output per million tokens. It is included in the model picker. API billing is separate from consumer chat subscriptions.

## What has been verified

Model identifiers and advertised prices were checked against official catalogs. Automated tests exercise request formatting, tool routing, selected-model preservation, and recovery with synthetic responses. No paid live-model comparison was performed for this release. Do not read this guide as a pedagogical quality ranking. See [the evaluation protocol](EVALUATION.md) before promoting a model to your daily workflow.
