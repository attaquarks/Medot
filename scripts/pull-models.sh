#!/usr/bin/env bash
# Pull the default models into native Ollama on the host.
# Override with LLM_LOCAL_MODEL_TAG / LLM_EMBEDDING_MODEL_TAG.
set -euo pipefail

CHAT_MODEL="${LLM_LOCAL_MODEL_TAG:-llama3.1:8b-instruct-q4_K_M}"
EMBED_MODEL="${LLM_EMBEDDING_MODEL_TAG:-nomic-embed-text}"

command -v ollama >/dev/null 2>&1 || {
  echo "Native Ollama is required: https://ollama.com/download"
  exit 1
}

echo "Waiting for native Ollama to be ready..."
for _ in $(seq 1 30); do
  if ollama list >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

ollama list >/dev/null 2>&1 || {
  echo "Ollama is installed but not responding. Start Ollama, then rerun this script."
  exit 1
}

echo "Pulling chat model: ${CHAT_MODEL}"
ollama pull "${CHAT_MODEL}"

echo "Pulling embedding model: ${EMBED_MODEL}"
ollama pull "${EMBED_MODEL}"

echo "Models ready."
