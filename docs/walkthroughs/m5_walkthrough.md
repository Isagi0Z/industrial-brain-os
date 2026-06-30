# M5 Walkthrough — Basic Chat API & Copilot UI

## Overview

M5 implements the Expert Engineering Copilot chat layer on top of the M4 embedding pipeline. It adds:

- A streaming WebSocket chat endpoint with full gateway fallback
- A non-streaming REST chat endpoint
- Redis-backed session history (20 messages, 1 h TTL)
- RAG context assembly with citation deduplication and token budgeting
- Dual LLM gateway support (Ollama primary / Gemini fallback, or vice-versa)
- React chat UI: streaming token display, citation accordion, session reset

## Architecture

```
POST  /api/v1/chat        → ChatEndpoint (REST)
WS    /api/v1/chat/stream → ChatEndpoint (WebSocket)
         │
    ChatUseCase
      ├── prepare()        # Redis history + semantic search + context build
      ├── chat()           # Non-streaming: _generate_with_fallback → _retry × 3
      ├── chat_stream()    # Streaming: _active_gateway → generate_stream()
      └── finalize()       # Persist history, return ChatResponse
         │
    IContextBuilder     → ContextBuilder
    IPromptLoader       → YamlPromptLoader  (ai/prompts/knowledge_copilot.yaml)
    IChatHistoryRepository → RedisChatHistoryRepository
    IModelGateway (primary) → OllamaGateway | GeminiGateway
    IModelGateway (fallback)→ GeminiGateway | OllamaGateway
```

## Clean Architecture Layer Map

| Layer | Files |
|-------|-------|
| Domain | `domain/chat/models.py`, `domain/chat/interfaces.py` |
| Application | `application/chat/chat_use_case.py` |
| Infrastructure | `infrastructure/chat/{context_builder,prompt_loader,redis_history_repository,ollama_gateway,gemini_gateway}.py` |
| Presentation | `presentation/api/v1/endpoints/chat.py` |
| AI Prompts | `ai/prompts/knowledge_copilot.yaml` |
| Frontend | `frontend/src/components/chat/{ChatInterface,MessageBubble,CitationCard}.tsx` |

## WebSocket Protocol

```
Client → Server:
  { "query": "...", "session_id": "...", "top_k": 5, "role_scope": "public" }

Server → Client (streaming):
  { "type": "token", "content": "..." }        # per chunk
  { "type": "done", "citations": [...], "token_usage": {...}, "session_id": "..." }
  { "type": "error", "message": "..." }        # on failure
```

## Gateway Retry Policy (Engineering Bible §23)

```
For each gateway (primary → fallback):
  Attempt 1: immediate
  Attempt 2: sleep 1 s
  Attempt 3: sleep 2 s
  Attempt 4: sleep 4 s  → raise GatewayError
If all gateways exhausted: raise GatewayError("All configured gateways failed")
```

## Context Builder

- Deduplicates chunks by `chunk_id`
- Sorts by `score` descending
- Formats: `[Source: {title}, p.N]\n{text}` blocks separated by `---`
- Token budget: `len(block) // 4` chars-per-token approximation
- Returns `(context_text, List[Citation])`

## Configuration

| Setting | Default | Purpose |
|---------|---------|---------|
| `LLM_PROVIDER` | `ollama` | Primary gateway selection |
| `OLLAMA_HOST` | `127.0.0.1` | Ollama service host |
| `OLLAMA_PORT` | `11434` | Ollama service port |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model name |
| `GEMINI_API_KEY` | `""` | Enables Gemini fallback if set |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model |
| `CHAT_MAX_TOKENS` | `2048` | Max completion tokens |
| `CHAT_SESSION_TTL_SECONDS` | `3600` | Redis session lifetime |
| `PROMPT_FILE` | `ai/prompts/knowledge_copilot.yaml` | System prompt path |
