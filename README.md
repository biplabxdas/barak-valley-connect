# Barak Valley Connect

A local services directory for discovering service providers in Silchar, Assam, with an AI-assisted natural-language discovery feature.

**Existing live website:** https://barak-valley-connect.onrender.com

## Features

- Browse providers by category and area.
- Submit customer service requests.
- Owner-managed provider listings and request status.
- AI-assisted natural-language service discovery.
- Embedding-based semantic retrieval over provider records.
- LLM-generated answers grounded in retrieved provider records.
- Provider matches are returned separately from the generated explanation.

## AI architecture

1. The browser sends a customer's natural-language question to `POST /api/ai/ask`.
2. FastAPI loads provider names, categories and areas from the existing database.
3. The AI module creates embeddings for the question and provider descriptions.
4. Cosine similarity ranks the provider records and selects up to five candidates.
5. The selected records are passed as context to an LLM.
6. The LLM is instructed to answer only from the retrieved records and not invent businesses, phone numbers, prices or availability.
7. FastAPI returns the answer and matching provider records to the browser.

This is a small, request-time retrieval-augmented generation (RAG) implementation. Embeddings are generated on demand; this pilot does not yet persist vectors in a dedicated vector database. For a larger directory, add persistent vector storage, caching, evaluation and monitoring.

## Technology

- **Backend:** Python, FastAPI
- **Frontend:** HTML, CSS, vanilla JavaScript
- **Database:** SQLite locally; PostgreSQL on the hosted deployment
- **AI:** OpenAI-compatible embeddings and chat-completions API
- **Hosting:** Render

## Configuration

Set these environment variables in your local `.env` file or hosting provider:

- `AI_API_KEY` — required API key; keep it secret.
- `AI_API_BASE` — optional API base URL; defaults to `https://api.openai.com/v1`.
- `AI_CHAT_MODEL` — optional chat model; defaults to `gpt-4o-mini`.
- `AI_EMBEDDING_MODEL` — optional embedding model; defaults to `text-embedding-3-small`.

Never commit `.env`, API keys, passwords or database files. The AI endpoint returns a clear service-unavailable response when the API key is not configured.

## Run locally on macOS

1. Install Python 3.
2. Create and activate a virtual environment:
   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```sh
   python -m pip install -r requirements.txt
   ```
4. Configure the existing database and owner settings using `.env.example`, and add `AI_API_KEY` if you want to test the AI assistant.
5. Start the app:
   ```sh
   python -m uvicorn main:app --reload
   ```
6. Open http://127.0.0.1:8000.

## API

`POST /api/ai/ask`

Request:
```json
{"question":"I need an electrician in Silchar to repair a ceiling fan"}
```

Response includes an `answer` and a `matches` array containing provider IDs, names, categories, areas and similarity scores.

## Current limitations

- AI requests require a configured external API key and internet access.
- Embeddings are calculated for all providers on each request; this is suitable for a small pilot, not a large directory.
- The similarity score is a retrieval signal, not a probability or a guarantee of suitability.
- The LLM can still make mistakes; verify provider details before acting.
- Provider availability, pricing and service quality are not inferred.
- No dedicated vector database, automated evaluation suite or user feedback loop is implemented yet.

## Learning goals

This project is intended to demonstrate practical understanding of REST APIs, embeddings, cosine similarity, semantic retrieval, RAG, prompt constraints, database integration, secrets management and deployment.
