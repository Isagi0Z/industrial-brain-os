# M5 Summary — Basic Chat API & Copilot UI

**Milestone**: M5  
**Status**: ✅ Complete  
**Date**: 2026-06-30

## Delivered

### Backend
- **Domain**: `ChatRequest`, `ChatMessage`, `ChatContext`, `ChatResponse`, `Citation`, `TokenUsage` models; `IModelGateway`, `IChatHistoryRepository`, `IContextBuilder`, `IPromptLoader` interfaces
- **Application**: `ChatUseCase` with `prepare()` / `chat()` / `chat_stream()` / `finalize()` pattern; `GatewayError`; retry policy (3 attempts, exponential backoff 1s/2s/4s); dual-gateway fallback
- **Infrastructure**: `OllamaGateway` (httpx NDJSON streaming); `GeminiGateway` (google-generativeai, `run_in_threadpool`); `RedisChatHistoryRepository` (20-msg ring, TTL); `ContextBuilder` (dedup, token budget, formatted citations); `YamlPromptLoader` (YAML with fallback default)
- **Presentation**: `POST /api/v1/chat` (Bearer auth); `WS /api/v1/chat/stream` (token query param, `1008` on invalid)
- **AI Prompts**: `ai/prompts/knowledge_copilot.yaml` — industrial copilot system prompt + context template

### Frontend
- `ChatInterface.tsx` — WebSocket client, streaming token buffer, session management, reconnection
- `MessageBubble.tsx` — user/assistant bubbles with streaming cursor animation
- `CitationCard.tsx` — collapsible accordion with score chip and document links
- `/knowledge` route → `ChatInterface`; sidebar label updated to "Knowledge Copilot"

### Tests
- 11 new unit tests in `tests/test_chat.py` covering context building, gateway fallback, Redis history, prompt loading
- Total: 56 tests, all passing

## Files Created

```
backend/app/domain/chat/__init__.py
backend/app/domain/chat/models.py
backend/app/domain/chat/interfaces.py
backend/app/application/chat/__init__.py
backend/app/application/chat/chat_use_case.py
backend/app/infrastructure/chat/__init__.py
backend/app/infrastructure/chat/context_builder.py
backend/app/infrastructure/chat/prompt_loader.py
backend/app/infrastructure/chat/redis_history_repository.py
backend/app/infrastructure/chat/ollama_gateway.py
backend/app/infrastructure/chat/gemini_gateway.py
backend/ai/prompts/knowledge_copilot.yaml
backend/app/presentation/api/v1/endpoints/chat.py
backend/tests/test_chat.py
frontend/src/components/chat/ChatInterface.tsx
frontend/src/components/chat/MessageBubble.tsx
frontend/src/components/chat/CitationCard.tsx
```

## Files Modified

```
backend/app/infrastructure/config/settings.py   — LLM/Chat settings
backend/app/infrastructure/di/container.py      — M5 imports + get_chat_use_case()
backend/app/presentation/api/v1/router.py       — chat router registered
backend/requirements.txt                        — google-generativeai, pyyaml
frontend/src/router/routes.tsx                  — /knowledge → ChatInterface
frontend/src/components/layout/DashboardLayout.tsx — sidebar label
```

## Engineering Bible Compliance

- §8 No `Any` typing — all types explicit ✅
- §15 RBAC on every route — Bearer on REST, `token` param on WS ✅
- §23 LLM retry policy — 3 attempts, 1s/2s/4s backoff ✅
- ADR-001 — blocking Gemini calls via `run_in_threadpool` ✅
- ADR-013 — `IModelGateway` in domain, no concrete LLM import in domain ✅
- ADR-020 — system prompt loaded from YAML, not hardcoded ✅
