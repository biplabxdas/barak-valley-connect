"""Lightweight, local parsing for common home-service request details."""

import re
from difflib import get_close_matches

from matcher import QUERY_SYNONYMS, STOP_WORDS, tokenize


CATEGORY_ALIASES = {
    "Electrical": ("electrician", "electrical", "wiring", "wire", "fan", "light", "switch", "socket", "power", "outlet"),
    "Plumbing": ("plumber", "plumbing", "pipe", "tap", "faucet", "leak", "leaking", "drain", "water", "bathroom", "kitchen", "toilet", "sink"),
    "Home repair": ("handyman", "home repair", "house repair", "wall", "door", "household", "maintenance"),
    "Gardening": ("garden", "gardening", "gardener", "lawn", "grass", "yard", "plant", "pruning", "hedge", "landscaping"),
    "Cleaning": ("clean", "cleaner", "cleaning", "dust", "mop", "vacuum", "deep clean"),
    "Carpentry": ("carpenter", "carpentry", "woodworker", "woodwork", "furniture", "cabinet", "shelf", "bookcase"),
}

URGENCY_TERMS = {
    "urgent", "urgently", "emergency", "immediately", "asap", "today", "now",
    "quickly", "same-day", "tonight", "right-away",
}

LOCATION_PREPOSITIONS = re.compile(r"\b(?:in|near|around|at)\s+([a-z][a-z .'-]{1,48})", re.IGNORECASE)
NON_SKILL_TERMS = {
    "in", "near", "around", "at", "tomorrow", "tonight", "weekend", "weekday",
    "someone", "somebody", "looking", "find", "local", "provider", "providers",
}


def normalized_phrase(value: str) -> str:
    return " ".join(tokenize(value))


def expand_terms(terms) -> set[str]:
    expanded = set(terms)
    for term in tuple(expanded):
        expanded.update(QUERY_SYNONYMS.get(term, ()))
    return expanded


def _find_category(description: str, providers: list[dict]) -> str | None:
    lowered = description.lower()
    categories = set(CATEGORY_ALIASES)
    categories.update(provider.get("category", "").strip() for provider in providers if provider.get("category"))
    ranked = []
    for category in categories:
        aliases = set(CATEGORY_ALIASES.get(category, ())) | {category.lower()}
        hits = [alias for alias in aliases if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lowered)]
        if hits:
            ranked.append((len(hits), max(map(len, hits)), category))
    return max(ranked)[2] if ranked else None


def _find_location(description: str, providers: list[dict]) -> str | None:
    lowered = description.lower()
    areas = sorted({provider.get("area", "").strip() for provider in providers if provider.get("area")}, key=len, reverse=True)
    for area in areas:
        if re.search(rf"(?<![a-z0-9]){re.escape(area.lower())}(?![a-z0-9])", lowered):
            return area

    # Keep an unrecognized place mention visible to callers, but only known
    # provider areas receive a location ranking bonus.
    match = LOCATION_PREPOSITIONS.search(description)
    if not match:
        return None
    candidate = re.split(r"[,;.!?]", match.group(1), maxsplit=1)[0].strip()
    candidate_words = tokenize(candidate)
    while candidate_words and candidate_words[-1] in URGENCY_TERMS | STOP_WORDS:
        candidate_words.pop()
    return " ".join(candidate_words[:4]).title() or None


def understand_requirement(description: str, providers: list[dict]) -> dict:
    """Extract a best-effort category, skill terms, location, and urgency.

    This uses a curated English service vocabulary and provider directory fields;
    it is deterministic text processing, not a generative model.
    """
    raw_words = re.findall(r"[a-z0-9]+", description.lower())
    words = tokenize(description)
    urgency_terms = sorted(set(raw_words) & URGENCY_TERMS)
    category = _find_category(description, providers)
    location = _find_location(description, providers)
    location_terms = set(tokenize(location or ""))
    vocabulary = set()
    for provider in providers:
        vocabulary.update(tokenize(" ".join((provider.get("skills", ""), provider.get("description", "")))))
    skill_terms = set()
    for word in words:
        if word in URGENCY_TERMS or word in NON_SKILL_TERMS or word in location_terms:
            continue
        corrected = get_close_matches(word, vocabulary, n=1, cutoff=0.82)
        skill_terms.add(corrected[0] if corrected else word)
    skill_terms = expand_terms(skill_terms)
    return {
        "category": category,
        "required_skills": sorted(skill_terms),
        "location": location,
        "location_matched": bool(location and any(normalized_phrase(p.get("area", "")) == normalized_phrase(location) for p in providers)),
        "urgency": "urgent" if urgency_terms else "standard",
        "urgency_terms": urgency_terms,
    }
