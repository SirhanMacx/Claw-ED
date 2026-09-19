# Architecture

Claw-ED is a single-teacher Python application. Its useful core is curriculum retrieval, structured `MasterContent`, and compilers for editable teacher DOCX, student DOCX, and PPTX files.

## One runtime

`clawed`, `python -m clawed`, the local dashboard, Telegram, and MCP use the owned Python backend. The previous bundled coding-agent terminal source is removed from the source tree and new distributions. Node.js and Bun are no longer required. `clawed --python` remains a compatibility alias. Start Telegram explicitly with `clawed bot`; the old Node daemon command has been retired.

Natural-language requests use `agent_core.Gateway` and its tool registry and approval policy. `clawed -p "request"` uses that same gateway. Deterministic generation commands call the shared Python teaching services. Provider tool definitions are request-local; concurrent requests cannot change another request's tools.

## Durable generation

`task_queue.db` is the job ledger shared by CLI and dashboard. Atomic database claims assign each job to one worker. Workers heartbeat while processing and report failed, interrupted, cancelled, or done states. Cancellation is cooperative and cannot reverse provider work already performed.

Use the dashboard's Jobs page or `clawed queue submit bundle --topic "Topic" --grade 8 --subject History`, then run `clawed queue worker`. The phased generator saves validated phase responses by job, phase, and a hash of prompt, schema, system prompt, provider, and model. Resume reuses matching phases; changed inputs or model invalidate those checkpoints. `clawed queue recover` marks workers missing for five minutes as interrupted; recovery never silently reruns them. `clawed queue resume ID` is explicit.

Bundle jobs use separate output folders named for the job ID. Successful artifact paths and completed phases remain visible in the dashboard. This ledger covers queued generation; it does not yet checkpoint arbitrary conversational tool loops or promise exactly-once external publishing. Existing approval records remain separate, scoped, expiring, and single-use. Existing databases are preserved rather than destructively migrated into a new store.

## Evidence and review

Retrieved excerpts retain document IDs, origin, available page/slide metadata, complete excerpt text, and hashes in a source manifest. When ingestion did not preserve a page or slide number, that gap is stated explicitly. Downstream phases receive the source text used to write questions and answers.

Bundle outputs include a manifest with quotation checks. A match means text occurs in supplied evidence; it does not prove historical accuracy or pedagogical validity. Unmatched model-generated quotations require teacher verification. Multilingual source text is preserved. Source manifests may contain private source paths and excerpts and should be handled with the same care as the teacher's original materials.

## Provider boundary

Task and tier overrides are opt-in. Otherwise, generation keeps the teacher's selected model. No hard-coded cloud fallback chain changes the model after a failure. Astra native tool calls use OpenAI Responses. Anthropic native thinking and tool blocks are retained across turns; Google tools use Google's compatibility endpoint. OpenRouter and Ollama retain their compatible adapters.

Image screening also keeps the selected model unless a saved `openrouter_vision_model` or `OLLAMA_VISION_MODEL` override is present. It rejects unverified images when vision is unavailable or fails. Concurrent image checks use separate temporary montages, removed after the call.

## What should come next

Prove one repeatable source-to-reviewed-lesson workflow with teacher-scored evaluations before adding new agents or student products. The next architectural decision should compare this small backend with a maintained workflow or agent SDK using the same fixtures, provider, budget, and failure scenarios. Adopt another framework only if measured recovery, editing time, or maintainability improves. See [EVALUATION.md](EVALUATION.md).
