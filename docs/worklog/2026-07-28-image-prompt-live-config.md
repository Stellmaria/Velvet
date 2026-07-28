# Live Ollama recovery settings

## Production configuration

After deploying this fix, use one official Ollama vision model first:

```dotenv
AI_VISION_ENABLED=true
AI_VISION_PROVIDER=ollama
AI_VISION_BASE_URL=http://127.0.0.1:11434
AI_VISION_MODEL=qwen3-vl:4b
AI_VISION_COMPARE_MODEL=
AI_VISION_TIMEOUT_SECONDS=600
```

Only enable a comparison model after the single-model smoke test is stable.
