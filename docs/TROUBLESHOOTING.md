# Troubleshooting

Common issues and fixes.

## Installation

### `pip install clawed` fails with permission error
```bash
pip install --user clawed
# or
python -m pip install clawed
```

### `command not found: clawed` after install
Your PATH may not include the pip bin directory. Try:
```bash
python -m clawed
```

## Ingestion

### "No supported documents found"
Check that your folder contains PDF, DOCX, PPTX, TXT, or MD files. Claw-ED doesn't read `.doc` (old Word) or image-only PDFs.

### Ingestion is very slow
Large PPTX files with embedded media can take time. The system processes in batches with automatic memory management. Let it run — it won't crash.

### "ONNX model download failed" on Windows
Windows TLS can block the model download. The system retries 3 times with exponential backoff. If it still fails:
```bash
pip install onnxruntime
```
Then restart the ingest.

## Lesson Generation

### Ed generates Chinese characters in lessons
This happens with some multilingual models (MiniMax). The CJK sanitizer strips them automatically. If you see Chinese text, switch to a different model:
```
/models
```

### "Tool call failed" or no files generated
Check your LLM provider connection:
```bash
clawed setup
```
Make sure your API key is valid and the model supports tool use.

### Generated images don't match the topic
Run a full ingest of your curriculum files first:
```bash
clawed ingest ~/Documents/MyLessons/
```
Ed uses YOUR images (maps, cartoons, diagrams) from your PPTX files. Without ingestion, it falls back to generic web images.

## Telegram Bot

### Bot doesn't respond
1. Check the bot is running: `clawed bot`
2. Make sure you messaged the correct bot (@YourBotName)
3. Check the terminal for error messages
4. Try: `/start` to reinitialize

### "WinError 10054" on Windows
This is a known Windows TLS issue with some HTTP libraries. Claw-ED uses `requests` (urllib3) instead of `httpx` for Windows compatibility. If you still see this, restart the bot.

### Bot stops after closing the terminal
The bot runs as a foreground process. To keep it running:
- **Windows**: `start /B python -m clawed bot`
- **Mac/Linux**: `nohup clawed bot &`
- **Docker**: `docker run -d clawed bot`

## Models

### Which model should I use?
See [CHOOSING_A_MODEL.md](CHOOSING_A_MODEL.md) for detailed comparisons. Quick answer:
- **Best quality**: Claude Sonnet 4.6 (Anthropic, pay-per-use)
- **Best value**: GLM 5.1 Cloud or Gemma 4 31B (Ollama Pro, $20/mo)
- **Free**: Qwen 3.6 Plus on OpenRouter

### How do I switch models?
```
/models
```
On Telegram, or in the CLI:
```bash
clawed setup
```

## Still stuck?

- [GitHub Issues](https://github.com/SirhanMacx/Claw-ED/issues) — report bugs
- [GitHub Discussions](https://github.com/SirhanMacx/Claw-ED/discussions) — ask questions
