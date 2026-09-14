<<<<<<< HEAD
# Sếp Nói Gì? — V1.2 Exact Visual Cache

A Flask + SQLite English micro-learning app built around **SEE → HEAR → NOTICE → USE → YOUR TURN**.

V1.2 adds an image pipeline designed for high semantic fidelity without paying to regenerate the same image repeatedly.

## What is included

- Real Register / Login with hashed passwords and Flask sessions.
- User profile: age, occupation, industry, English level, goals, situations, accent.
- SQLite persistence for users, lessons, patterns, progress, reviews, AI calls.
- OpenAI structured lesson generation with a strict JSON schema.
- Two-layer cache:
  1. **Lesson cache** — sentence + context group.
  2. **Visual cache** — one accepted visual per lesson.
- Lazy visual generation: image generation starts only when a learner actually opens the lesson.
- Exact visual scene contract: entities, action, environment, must-show and must-not-show details.
- AI semantic visual QA after generation.
- Rejected images are **not** published to the UI cache.
- Per-request and lifetime-per-lesson generation caps prevent accidental retry loops from burning image spend.
- Accepted image is saved locally as WebP in `static/generated/visuals/` and reused thereafter.
- Visual generation attempts and token usage are logged in SQLite.
- Scroll-snap lesson UI with moving 01–05 progress.

## Visual flow

```text
Open SEE IT
   ↓
visual_assets cache?
   ├─ accepted → serve local .webp → 0 new image generation
   └─ missing/rejected/error
          ↓
      build exact scene prompt
          ↓
      GPT image generation
          ↓
      vision semantic QA
          ↓
      score >= threshold + ALL hard checks true?
          ├─ YES → save WebP + DB → cache forever
          └─ NO  → correction prompt → retry (max configured attempts)
```

`VISUAL_MATCH_THRESHOLD=98` is intentionally strict. It is an AI semantic QA score, **not a mathematically guaranteed 98% match**. The hard boolean checks also require entities, action, context, lack of conflicting details, and instant comprehensibility.

## Windows setup

```bat
cd C:\path\to\sep-noigi-v1.2
py -m venv .venv
.venv\Scripts\activate
py -m pip install -r requirements.txt
copy .env.example .env
notepad .env
```

Put your API key in `.env`:

```text
OPENAI_API_KEY=sk-...
```

Run:

```bat
py app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Cost-control defaults

```text
OPENAI_MODEL=gpt-5.6-luna
OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_VISION_MODEL=gpt-5.6-luna
OPENAI_IMAGE_QUALITY=medium
VISUAL_MATCH_THRESHOLD=98
VISUAL_MAX_ATTEMPTS=2
VISUAL_TOTAL_MAX_ATTEMPTS=4
```

To spend less while testing, set:

```text
OPENAI_IMAGE_QUALITY=low
VISUAL_MAX_ATTEMPTS=1
```

For production-quality visuals, restore `medium` and 2 attempts after the prompt/UX is stable.

## Database

SQLite is created automatically at:

```text
instance/sep_noigi.db
```

Important V1.2 tables:

- `users`, `profiles`
- `sentences`, `lessons`
- `patterns`, `sentence_patterns`
- `user_learning`, `reviews`
- `ai_requests`
- `visual_assets` — one cached accepted visual per lesson
- `visual_attempts` — each generation + QA attempt, score and token counts

## Generated images

Accepted images are saved under:

```text
static/generated/visuals/<visual_key>.webp
```

The DB stores the public path, so future users load the local file instead of regenerating it.

## Important production notes

This is a V1 prototype architecture. Before public deployment, add CSRF protection, email verification/password reset, stronger rate limiting, a production WSGI server, HTTPS, secret management, backups, and move generated assets to object storage/CDN when traffic grows. SQLite is fine for early validation; PostgreSQL is the natural next database when concurrency becomes significant.

## V1.3 Admin Cost Dashboard

V1.3 adds a separate admin login and SQLite-backed API cost accounting.

1. Open `.env` and set:

```env
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_PASSWORD=use-a-strong-password
ADMIN_MONTHLY_BUDGET_USD=20
USD_VND_RATE=26000
```

2. Run the app as usual, then open:

```text
http://127.0.0.1:5000/admin/login
```

The admin dashboard shows:
- API cost for 7 / 30 / 90 / 365 days
- estimated VND cost using `USD_VND_RATE`
- monthly budget consumption
- lesson text vs image generation vs vision-QA cost
- cost by model and by user
- lesson cache-hit rate and estimated savings
- users, lessons, accepted visuals and token totals

Each paid API call is written to SQLite table `api_usage_events`. The row stores the model, token usage, user, lesson/visual association, computed USD cost, and a `pricing_snapshot_json`. Historical rows therefore keep the price snapshot used when the request occurred even if you later change the configured rates.

### Important pricing note
The built-in default rates are a code snapshot verified on 2026-09-06. API prices can change. Override rates through environment variables when needed; for example:

```env
PRICE_GPT_5_6_LUNA_TEXT_INPUT_PER_M=0.20
PRICE_GPT_5_6_LUNA_TEXT_CACHED_INPUT_PER_M=0.02
PRICE_GPT_5_6_LUNA_TEXT_OUTPUT_PER_M=1.20
```

Do not commit `.env` to GitHub. The admin password and OpenAI API key must remain server-side.
=======
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
>>>>>>> origin/main
