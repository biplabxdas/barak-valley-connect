"""Embedding-based retrieval and grounded answer generation for Barak Valley Connect.

Uses OpenAI-compatible REST endpoints via the Python standard library.
No API key is stored in source control.
"""
from __future__ import annotations

import json
import math
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_BASE = os.getenv("AI_API_BASE", "https://api.openai.com/v1").rstrip("/")
API_KEY = os.getenv("AI_API_KEY", "")
CHAT_MODEL = os.getenv("AI_CHAT_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL = os.getenv("AI_EMBEDDING_MODEL", "text-embedding-3-small")


def _post_json(path: str, payload: dict) -> dict:
    if not API_KEY:
        raise RuntimeError("AI assistant is not configured. Set AI_API_KEY in the hosting environment.")
    request = Request(
        f"{API_BASE}/{path.lstrip('/')}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"AI provider returned HTTP {error.code}: {detail}") from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError("Could not reach the AI provider. Please try again.") from error


def _embed(texts: list[str]) -> list[list[float]]:
    result = _post_json("embeddings", {"model": EMBEDDING_MODEL, "input": texts})
    return [item["embedding"] for item in sorted(result["data"], key=lambda x: x["index"])]


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def answer_service_query(question: str, providers: list[dict]) -> dict:
    """Retrieve relevant provider records, then ask the LLM to answer from those records."""
    descriptions = [
        f"Provider: {p['name']}. Category: {p['category']}. Area: {p['area']}."
        for p in providers
    ]
    vectors = _embed([question, *descriptions])
    query_vector, provider_vectors = vectors[0], vectors[1:]
    ranked = sorted(
        zip(providers, provider_vectors),
        key=lambda pair: _cosine(query_vector, pair[1]),
        reverse=True,
    )[:5]

    matches = [
        {
            "id": provider["id"],
            "name": provider["name"],
            "category": provider["category"],
            "area": provider["area"],
            "similarity": round(_cosine(query_vector, vector), 3),
        }
        for provider, vector in ranked
    ]

    context = [
        {key: item[key] for key in ("id", "name", "category", "area")}
        for item in matches
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "You are the service discovery assistant for Barak Valley Connect. "
                "Use only the provider records supplied in the context. Never invent a provider, "
                "phone number, service, location, availability, price, or guarantee. "
                "If no record is relevant, say so and suggest trying another description. "
                "Be concise and explain which listed providers may fit. Do not claim a provider "
                "is available or verified. Return plain text."
            ),
        },
        {
            "role": "user",
            "content": f"Customer request: {question}\nProvider records (retrieved from database): "
                       f"{json.dumps(context, ensure_ascii=False)}",
        },
    ]
    completion = _post_json(
        "chat/completions",
        {"model": CHAT_MODEL, "messages": messages, "temperature": 0.2},
    )
    answer = completion["choices"][0]["message"]["content"].strip()
    return {"answer": answer, "matches": matches}
