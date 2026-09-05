# Sếp Nói Gì? v2.2

A visual, chunk-based, target-language-first workplace language learning app.

## Learning philosophy

v2.2 intentionally avoids default native-language translation. A learner sees a situation, hears a chunk, reads a simple description **in the target language**, then connects that chunk to many real examples, related chunks, visual vocabulary and active speaking practice.

Example learning object:

`Let's align on this.` → workplace image → English-only explanation → 6 contextual examples → related chunks → visual map → listen/repeat → active recall.

## AI-ready architecture

The browser does **not** call ChatGPT/OpenAI directly.

```text
Browser
  -> POST /api/ai/analyze
  -> server.js
  -> ai.js provider adapter
  -> future ChatGPT/OpenAI API
  -> structured lesson JSON
  -> UI
```

`ai.js` is the provider boundary. The UI consumes a provider-neutral schema, so a future OpenAI integration can replace the demo analyzer without redesigning the pages or database.

Expected lesson fields include:

- `chunk`
- `pronunciation`
- `plain_description` (target language only)
- `usage` (target language only)
- `examples[]`
- `related_chunks[]`
- `visual_concepts[]`
- `vocabulary[]` with target-language definitions
- `suggested_replies[]`
- `practice`
- `thinking_prompt`

Check the contract at `GET /api/ai/capabilities`.

## Run

```bash
npm install
npm start
```

Open `http://localhost:3000`.

Demo account:

- Email: `demo@sepnoigi.local`
- Password: `demo1234`

## Notes for future OpenAI integration

Keep `OPENAI_API_KEY` only in `.env` on the server. Do not expose it in `public/js`.

Recommended future environment variables:

```env
AI_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_MODEL=...
SESSION_SECRET=change-me
```

When adding the provider, implement `callOpenAI()` inside `ai.js` and require JSON output matching the existing lesson contract.

## v2.2 design changes

- target-language-first learning; no default mother-tongue translation
- chunks instead of isolated vocabulary lists
- one chunk references many workplace examples
- visual context on major learning objects
- local visual assets included in the repository
- visual mind maps and chunk networks
- listen/repeat with browser speech synthesis
- active recall from images
- provider-neutral AI contract ready for ChatGPT/OpenAI

MIT License.
