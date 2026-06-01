#!/usr/bin/env bash
# Pull the default local models into the Ollama container.
# Override with LLM_LOCAL_MODEL / LLM_EMBEDDING_MODEL env vars.
set -euo pipefail
cd "$(dirname "$0")/.."

CHAT_MODEL="${LLM_LOCAL_MODEL_TAG:-llama3.1:8b-instruct-q4_K_M}"
EMBED_MODEL="${LLM_EMBEDDING_MODEL_TAG:-nomic-embed-text}"

echo "▶ Waiting for Ollama to be ready…"
for i in {1..30}; do
  if docker compose exec -T ollama ollama list >/dev/null 2>&1; then break; fi
  sleep 2
done

echo "▶ Pulling chat model: ${CHAT_MODEL}"
docker compose exec -T ollama ollama pull "${CHAT_MODEL}"

echo "▶ Pulling embedding model: ${EMBED_MODEL}"
docker compose exec -T ollama ollama pull "${EMBED_MODEL}"

echo "✅ Models ready."
