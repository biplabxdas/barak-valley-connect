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
        provider.get("name", ""), category, extra_terms, provider.get("area", ""),
        provider.get("description", ""), provider.get("skills", ""),
    ))


def rank_providers(description: str, providers: list[dict], limit: int = 3) -> list[dict]:
    """Rank listings by cosine similarity between TF-IDF weighted word vectors."""
    if not providers:
        return []

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
    ranked = []
    for provider, document in zip(providers, documents):
        provider_vector = weighted_vector(Counter(document))
        score = cosine_similarity(query_vector, provider_vector)
        if score < 0.06:
            continue
        overlap = [term for term in expanded_query if term in provider_vector]
        ranked.append({
            **provider,
            "score": round(score, 3),
            "reasons": overlap[:4] or [provider.get("category", "")],
        })
    return sorted(ranked, key=lambda item: (-item["score"], item["name"]))[:limit]
