# Phase 3: LLM client

## What was built

- **`app/llm/base.py`**: the abstract `LLMClient` with `generate(prompt, system=None) -> str` and `stream(prompt, system=None) -> Iterator[str]`. It also has two provider-independent helpers: `retry_call` (exponential backoff with jitter, capped at 30 s, honours a provider's `retry_after`) and `retry_stream` (retries only until the first piece of text arrives).
- **`app/llm/errors.py`**: `LLMError` and three subclasses, `MissingAPIKeyError`, `RateLimitError` (`retry_after`, `daily_quota`) and `ProviderError` (`status_code`). Each has a technical `str()` for logs and a friendly `user_message` for the API layer. Each also has a `retryable` flag that the retry helpers read.
- **`app/llm/gemini.py`**: `GeminiClient`, built on the `google-genai` SDK. It reads the key, model, retries and timeout from settings, and translates SDK/httpx exceptions into our errors. An empty or blocked answer becomes a `ProviderError` that includes the reason, such as a safety block.
- **`app/api/deps.py`**: `get_llm_client()`, created lazily and cached. The app starts without a key, and only LLM requests fail.
- **Settings:** `gemini_model` (default `gemini-3.8-flash`), `llm_max_retries` (3), `llm_retry_base_delay` (1.0 s), `llm_timeout_seconds` (60). `.env.example` now has `GEMINI_MODEL`.
- **Dependency:** `google-genai==2.28.0`; `requirements.txt` was regenerated with `pip freeze`. Note: this downgraded `websockets` from 17.2 to 16.1.1 (google-genai's pin).
- **Tests (36 new, 66 total), none of which call the real API:** `test_llm_retry.py`, `test_gemini_client.py` (a fake SDK object injected through `client=`, with real `google.genai.errors` classes), `test_fake_llm.py`, `test_llm_deps.py`. `tests/fakes.py` has a `FakeLLMClient` for the Phase 4 endpoint tests. `tests/conftest.py` has an autouse guard that makes `genai.Client(...)` raise in every test.

## Gemini API facts (checked 2026-10-08; these change often)

- **SDK:** `google-genai` (`from google import genai`). The old `google-generativeai` package has been deprecated since 2025-11-30.
- **Free-tier text models** (pricing page, 2026-10-07): `gemini-3.8-flash`, `3.7-flash`, `3.6-flash`, `3.5-flash`, `3.5-flash-lite`, `3.1-flash-lite`, `3-flash-preview`, and the older `2.5-pro/flash/flash-lite`. `gemini-3.1-pro-preview` has no free tier, and `gemini-2.0-flash(-lite)` has been shut down.
- **Rate limits** are no longer published as numbers in the docs. They depend on the project and tier and are shown in AI Studio (aistudio.google.com/rate-limit).
- **Errors:** retry 429, 408 and 5xx; never retry 400, 401, 402, 403 or 404. A 429 means either a per-minute limit (retry) or the daily quota (don't).
- **SDK details verified in the installed package:** `HttpOptions.timeout` is in **milliseconds**. The SDK does **not** retry unless `retry_options` is set, so our retries don't stack with its own. Network timeouts come out as raw `httpx.TimeoutException`.

## How the pieces connect

```
endpoint (Phase 4) ──Depends(get_llm_client)──► GeminiClient.generate / .stream
                                                    │
                          retry_call / retry_stream (base.py, backoff, retryable flag)
                                                    │
                         _translated_errors ◄── client.models.generate_content[_stream]
                                                    │
         APIError 429 → RateLimitError · 401/403/bad key → ProviderError · 404 → ProviderError
         408/5xx/httpx timeout or network → ProviderError(retryable) · empty/blocked → ProviderError
```

## Design decisions

- **Retry logic is ours, not the SDK's or tenacity's.** It is about 20 lines, the sleep function is injected (tests take no time), and the "what is retryable" decision sits in one place: the `retryable` flag set by error translation. tenacity is only a transitive dependency of chromadb, so it isn't relied on.
- **Daily quota isn't retried.** Google's 429 carries a `QuotaFailure` whose `quotaId` contains `PerDay` for the daily cap. Retrying that would only waste time, so it fails fast with a "try tomorrow" message. `RetryInfo.retryDelay` (for example `"34s"`) is honoured as a minimum wait.
- **Streams retry only before the first chunk.** After text has reached the user, a retry would duplicate it, so mid-stream errors are raised as they are.
- **Sync, not async.** This matches the rest of the codebase. FastAPI runs sync endpoints in a threadpool, and `StreamingResponse` accepts a sync iterator.
- **Lazy client.** Nothing touches Gemini at import or startup. `lru_cache` doesn't cache exceptions, so adding a key later works.
- **Unknown exceptions pass through untouched.** Only SDK and network errors are translated. A `TypeError` in our own code stays a bug and isn't hidden as "provider error".
- **No secrets in messages.** Error text comes from Google's message and the status code, never the key or the prompt.

## Interview questions

1. **Q: Why put an abstract `LLMClient` in front of Gemini?**
   A: The RAG code depends on two methods, not on a vendor SDK. That gives three things: tests use a `FakeLLMClient` with no network or quota; switching provider (OpenAI, a local model) means writing one new class; and the provider's quirks (error types, timeout units, response shapes) stay inside `gemini.py` instead of leaking into endpoints.

2. **Q: How do you decide what to retry, and how long to wait?**
   A: Only transient failures: 429 per-minute limits, 408, 5xx, and network timeouts. Client errors such as a bad request, bad key or unknown model fail the same way every time, so retrying only adds latency. Waits double each attempt (1, 2, 4 s) with up to 10% random jitter, so many clients don't retry in lockstep, and they are capped at 30 s. If Google sends `RetryInfo`, I wait at least that long. A daily-quota 429 is not retried at all.

3. **Q: What's tricky about retrying a streaming response?**
   A: Once you've sent tokens to the user you can't take them back. Retrying would restart the answer and duplicate text. So I retry only until the first chunk arrives. That covers the common failures (rate limit, server busy), which happen on connect. After that, errors propagate and the endpoint can tell the user the answer was cut off.

4. **Q: How do you guarantee tests never hit the real API?**
   A: In three layers. `GeminiClient` takes an injected `client`, so its tests pass a fake object that mimics `client.models` and raises real `google.genai.errors` instances. Endpoint tests will override `get_llm_client` with `FakeLLMClient`. And an autouse fixture in `conftest.py` replaces `genai.Client` with a function that raises, so any accidental real construction fails the test loudly instead of spending quota.

5. **Q: The app needs an API key, but it starts without one. Why, and how?**
   A: Upload, listing and health checks don't need the LLM, so a missing key shouldn't take the whole service down. A missing key should also be obvious, not a crash at boot. The client is built lazily in a cached dependency. The first request that needs it gets `MissingAPIKeyError`, which the API layer will turn into a clear 503-style message. Because `lru_cache` doesn't cache exceptions, setting the key later works without code changes.
