"""Small, explainable TF-IDF matching for public provider listings."""

from collections import Counter
from difflib import get_close_matches
import math
import re


CATEGORY_TERMS = {
    "electrical": "electrician electrical wiring wire fan light switch socket power repair working",
    "home repair": "fixing maintenance handyman home household broken repair",
    "gardening": "garden plants lawn landscaping gardener outdoor yard grass trimming pruning",
    "plumbing": "plumber plumbing pipe tap faucet leak leaking drain water bathroom kitchen toilet sink",
    "cleaning": "cleaner cleaning house deep clean dust wash",
    "carpentry": "carpenter wood woodworker woodworking furniture door cabinet shelf shelves timber repair",
}
STOP_WORDS = {
    "the", "and", "for", "with", "need", "help", "want", "please", "a", "an",
    "my", "in", "to", "is", "of", "on", "at", "can", "you", "me", "some",
    # These words occur across many categories and should not create a false match alone.
    "repair", "repairs", "fix", "fixing", "maintenance", "service", "services",
    "work", "working", "job", "jobs",
    "someone", "somebody", "looking", "find", "local", "provider", "providers",
    "today", "now", "urgent", "urgently", "emergency", "asap", "immediately",
}
QUERY_SYNONYMS = {
    "electrician": ("electrical", "wiring", "power"),
    "electricians": ("electrical", "wiring", "power"),
    "switch": ("electrical", "wiring"),
    "socket": ("electrical", "power"),
    "faucet": ("tap", "plumber", "plumbing"),
    "tap": ("plumber", "plumbing"),
    "toilet": ("plumber", "plumbing", "pipe"),
    "drain": ("plumbing", "pipe"),
    "yard": ("garden", "lawn", "gardener"),
    "mow": ("grass", "lawn", "gardening"),
    "weeds": ("garden", "gardening", "plants"),
    "handyman": ("home", "household", "repair"),
    "cracks": ("wall", "broken", "repair"),
    "woodworker": ("carpenter", "woodworking", "furniture"),
    "vacuum": ("cleaning", "cleaner", "house"),
    "mop": ("cleaning", "cleaner", "house"),
    "hedge": ("garden", "gardening", "pruning"),
    "hedges": ("garden", "gardening", "pruning"),
    "sofa": ("furniture", "carpentry", "wood"),
    "couch": ("furniture", "carpentry", "wood"),
    "bookcase": ("bookshelf", "shelf", "shelves", "carpentry"),
    "bookshelf": ("bookcase", "shelf", "shelves", "carpentry"),
    "cupboard": ("cabinet", "carpentry", "furniture"),
    "cupboards": ("cabinet", "carpentry", "furniture"),
    "dripping": ("drip", "leak", "plumbing", "pipe"),
    "drips": ("drip", "leak", "plumbing", "pipe"),
}


def tokenize(text: str) -> list[str]:
    return [word for word in re.findall(r"[a-z0-9]+", text.lower()) if word not in STOP_WORDS]


def cosine_similarity(first: dict[str, float], second: dict[str, float]) -> float:
    """Return cosine similarity for sparse term-weight dictionaries."""
    first_length = math.sqrt(sum(value * value for value in first.values()))
    second_length = math.sqrt(sum(value * value for value in second.values()))
    if not first_length or not second_length:
        return 0.0
    dot_product = sum(value * second.get(term, 0.0) for term, value in first.items())
    return dot_product / (first_length * second_length)


def provider_profile(provider: dict) -> str:
    category = provider.get("category", "")
    extra_terms = next(
        (terms for category_name, terms in CATEGORY_TERMS.items() if category_name in category.lower()),
        "",
    )
    return " ".join((
        provider.get("name", ""), category, extra_terms,
        provider.get("description", ""), provider.get("skills", ""),
    ))


def rank_providers(description: str, providers: list[dict], limit: int = 3) -> list[dict]:
    """Rank listings using explainable text, skill, category, area, and availability signals."""
    if not providers:
        return []

    from query_understanding import expand_terms, normalized_phrase, understand_requirement

    analysis = understand_requirement(description, providers)
    documents = [tokenize(provider_profile(provider)) for provider in providers]
    query = Counter(tokenize(description))
    document_frequency = Counter()
    for document in documents:
        document_frequency.update(set(document))
    document_count = len(documents)
    inverse_frequency = {
        term: math.log((document_count + 1) / (frequency + 1)) + 1
        for term, frequency in document_frequency.items()
    }
    vocabulary = set(inverse_frequency)
    expanded_query = Counter()
    for term, count in query.items():
        normalized = term
        if term not in vocabulary and len(term) >= 5:
            correction = get_close_matches(term, vocabulary, n=1, cutoff=0.84)
            if correction:
                normalized = correction[0]
        expanded_query[normalized] += count
        for alias in QUERY_SYNONYMS.get(normalized, ()):
            if alias in vocabulary:
                expanded_query[alias] += 1

    def weighted_vector(counts: Counter) -> dict[str, float]:
        vector = {
            term: (1 + math.log(count)) * inverse_frequency[term]
            for term, count in counts.items() if term in inverse_frequency
        }
        length = math.sqrt(sum(value * value for value in vector.values()))
        return {term: value / length for term, value in vector.items()} if length else {}

    query_vector = weighted_vector(expanded_query)
    required_skills = set(analysis["required_skills"])
    category_aliases = {
        "electrical": {"electrical", "electrician", "wiring", "wire", "fan", "light", "switch", "socket", "power", "outlet"},
        "plumbing": {"plumbing", "plumber", "pipe", "tap", "faucet", "leak", "leaking", "drain", "water", "bathroom", "kitchen", "toilet", "sink"},
        "home repair": {"home repair", "handyman", "wall", "door", "household", "maintenance"},
        "gardening": {"garden", "gardening", "gardener", "lawn", "grass", "yard", "plant", "pruning", "hedge", "landscaping"},
        "cleaning": {"clean", "cleaner", "cleaning", "dust", "mop", "vacuum", "deep clean"},
        "carpentry": {"carpenter", "carpentry", "woodworker", "woodwork", "furniture", "cabinet", "shelf", "bookcase"},
    }
    availability_values = {"available": 1.0, "busy": 0.35, "unavailable": 0.0, "not specified": 0.60}
    ranked = []
    for provider, document in zip(providers, documents):
        provider_vector = weighted_vector(Counter(document))
        text_score = cosine_similarity(query_vector, provider_vector)
        provider_skills = expand_terms(tokenize(" ".join((provider.get("skills", ""), provider.get("description", "")))))
        skill_overlap = sorted(required_skills & provider_skills)
        skill_score = len(skill_overlap) / len(required_skills) if required_skills else 0.0
        requested_category = analysis["category"]
        provider_category = provider.get("category", "")
        category_score = None
        if requested_category:
            requested_key = normalized_phrase(requested_category)
            provider_key = normalized_phrase(provider_category)
            aliases = category_aliases.get(requested_key, {requested_key})
            category_score = 1.0 if provider_key == requested_key or provider_key in aliases else 0.0
        location_score = None
        if analysis["location_matched"]:
            location_score = 1.0 if normalized_phrase(provider.get("area", "")) == normalized_phrase(analysis["location"]) else 0.0
        availability = provider.get("availability", "Not specified")
        availability_score = availability_values.get(str(availability).lower(), 0.60)

        if analysis["urgency"] == "urgent":
            weights = {"text": 0.33, "skills": 0.27, "category": 0.16, "location": 0.10, "availability": 0.14}
        else:
            weights = {"text": 0.40, "skills": 0.28, "category": 0.16, "location": 0.10, "availability": 0.06}
        active_weights = {"text": weights["text"], "skills": weights["skills"], "availability": weights["availability"]}
        if category_score is not None:
            active_weights["category"] = weights["category"]
        if location_score is not None:
            active_weights["location"] = weights["location"]
        weight_total = sum(active_weights.values())
        feature_values = {
            "text": text_score,
            "skills": skill_score,
            "category": category_score,
            "location": location_score,
            "availability": availability_score,
        }
        score = sum(feature_values[name] * weight for name, weight in active_weights.items()) / weight_total

        # Availability is a tie-breaker, not a source of service relevance.
        if text_score < 0.04 and skill_score == 0 and category_score != 1:
            continue
        if score < 0.10:
            continue
        reasons = []
        if category_score == 1:
            reasons.append(f"Category matches {provider_category}")
        if skill_overlap:
            reasons.append("Skills include " + ", ".join(skill_overlap[:3]))
        if location_score == 1:
            reasons.append(f"Serves {provider.get('area')} as requested")
        elif analysis["location_matched"]:
            reasons.append(f"Serves {provider.get('area')}; requested {analysis['location']}")
        reasons.append({
            "available": "Listed as available",
            "busy": "Listed as busy",
            "unavailable": "Listed as unavailable",
            "not specified": "Availability not stated",
        }.get(str(availability).lower(), "Availability not stated"))
        overlap = [term for term in expanded_query if term in provider_vector]
        if not skill_overlap and overlap:
            reasons.append("Listing shares terms: " + ", ".join(overlap[:3]))
        ranked.append({
            **provider,
            "score": round(score, 3),
            "reasons": reasons,
            "feature_scores": {
                "text": round(text_score, 3),
                "skills": round(skill_score, 3),
                "category": None if category_score is None else round(category_score, 3),
                "location": None if location_score is None else round(location_score, 3),
                "availability": round(availability_score, 3),
            },
        })
    return sorted(ranked, key=lambda item: (-item["score"], item["name"]))[:limit]
