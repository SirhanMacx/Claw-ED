"""Image sourcing for slide presentations.

Fetches relevant educational images from multiple academic sources:

1. **Teacher's own images** (highest priority -- personalized curriculum material)
2. **Library of Congress** (free, no key, public domain) -- historical images,
   maps, documents.  Ideal for history / social studies / civics.
3. **Wikimedia Commons** (free, no key, CC-licensed) -- scientific diagrams,
   paintings, illustrations.  Good for all subjects.
4. **Unsplash** (free with API key) -- modern photographs.  Generic fallback.

Sources are tried in subject-aware priority order.  Teacher images are always
checked first.  All external images are cached locally at
``~/.eduagent/cache/images/<source>/<hash>.jpg``.

Falls back gracefully to ``None`` when no image can be found -- slides still
look good without images.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(
    os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent"))
) / "cache" / "images"

# Per-image network timeout (seconds)
_FETCH_TIMEOUT = 15.0


# ── SSRF guard (v4.11.2026.1 security fix P2-4) ──────────────────────
# After DDG / Wikipedia / LoC return a search result, the first image
# URL they hand us is followed with httpx.get(). Previously the only
# check was .startswith("http"), so a compromised or MITM'd third party
# returning an AWS metadata URL (169.254.169.254) or a private-RFC1918
# address could pivot us to internal services. This helper rejects any
# URL whose host is a loopback / link-local / private IP, unless the
# operator explicitly opts in via EDUAGENT_IMAGE_FETCH_ALLOW_INTERNAL=1.


# Paid stock-photo sites serve WATERMARKED preview images (an "alamy" / "getty"
# overlay across the picture) — never usable in a classroom deck, and a licensing
# problem. We reject them at fetch time so a watermarked image never even becomes a
# candidate for the vision screen (which can miss a small watermark in a thumbnail).
_STOCK_PHOTO_HOSTS = (
    "alamy", "gettyimages", "shutterstock", "istockphoto", "dreamstime",
    "123rf", "depositphotos", "stock.adobe", "agefotostock", "fotosearch",
    "bigstock", "canstockphoto", "stockphoto", "stocksy",
)


def _is_stock_photo_url(url: str) -> bool:
    """True if the URL host is a paid stock-photo site (serves watermarked previews)."""
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    return any(s in host for s in _STOCK_PHOTO_HOSTS)


def _is_safe_image_url(url: str) -> bool:
    """Return True if ``url`` is safe to fetch as a remote image.

    Rejects:
    - non-http(s) schemes
    - missing hostnames
    - IP literals that are loopback / link-local / private / reserved
    - IPv6 link-local and private-range equivalents

    Hostnames are returned as-is (not resolved) — any attacker who can
    control DNS for a public domain can still attack us via DNS
    rebinding, but that is a much higher bar than passing a raw IP.
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        logger.debug("operation_failed", exc_info=True)
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").strip()
    if not host:
        return False

    if os.environ.get("EDUAGENT_IMAGE_FETCH_ALLOW_INTERNAL") == "1":
        return True

    # If it's an IP literal, require it to be a routable public address.
    try:
        ip = ipaddress.ip_address(host)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    except ValueError:
        # Not an IP literal — it's a hostname. Reject a handful of
        # explicit loopback names even if someone mapped them in /etc/hosts.
        if host.lower() in {"localhost", "ip6-localhost"}:
            return False
    return True

# ── Cache eviction settings ──────────────────────────────────────────
MAX_CACHE_AGE_DAYS = 30
_cache_cleaned_this_session = False


def _cleanup_cache(cache_dir: Path | None = None) -> None:
    """Remove cached images older than MAX_CACHE_AGE_DAYS to prevent unbounded growth.

    Called once per session (guarded by module-level flag) at the start of
    image fetching.  Silently ignores errors on individual files.
    """
    global _cache_cleaned_this_session
    if _cache_cleaned_this_session:
        return
    _cache_cleaned_this_session = True

    root = cache_dir or _CACHE_DIR
    if not root.exists():
        return

    cutoff = time.time() - (MAX_CACHE_AGE_DAYS * 86400)
    removed = 0
    for source_dir in root.iterdir():
        if not source_dir.is_dir():
            continue
        for f in source_dir.iterdir():
            try:
                if f.is_file() and f.stat().st_mtime < cutoff:
                    f.unlink()
                    removed += 1
            except OSError:
                pass  # file may have been removed concurrently
    if removed:
        logger.info("Cache cleanup: removed %d images older than %d days", removed, MAX_CACHE_AGE_DAYS)

# ── Subject-aware query enrichment ───────────────────────────────────

_SUBJECT_KEYWORDS: dict[str, list[str]] = {
    "history": ["historical", "primary source"],
    "social studies": ["historical", "primary source"],
    "civics": ["historical", "government"],
    "government": ["historical", "government"],
    "science": ["diagram", "illustration"],
    "biology": ["diagram", "biology"],
    "chemistry": ["diagram", "chemistry"],
    "physics": ["diagram", "physics"],
    "math": ["mathematics", "education"],
    "mathematics": ["mathematics", "education"],
    "algebra": ["mathematics", "algebra"],
    "geometry": ["mathematics", "geometry"],
    "art": ["painting", "artwork"],
    "music": ["music", "artwork"],
    "ela": ["reading", "literature", "education"],
    "english": ["reading", "literature", "education"],
    "language arts": ["reading", "literature", "education"],
}


def _extract_key_concepts(text: str, max_concepts: int = 3) -> list[str]:
    """Extract key nouns/concepts from text for targeted image search.

    Uses simple heuristics -- capitalized proper nouns, quoted terms,
    and subject-specific keywords.
    """
    concepts: list[str] = []

    # Extract proper nouns (capitalized multi-word phrases)
    proper_nouns = re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', text)
    concepts.extend(proper_nouns[:2])

    # Extract quoted terms
    quoted = re.findall(r'"([^"]+)"', text) + re.findall(r"'([^']+)'", text)
    concepts.extend(quoted[:2])

    # Extract terms after "about", "of", "on" (topic indicators)
    topic_phrases = re.findall(
        r'(?:about|of|on|regarding|concerning)\s+(?:the\s+)?([A-Z][\w\s]{3,30})',
        text,
    )
    concepts.extend(topic_phrases[:1])

    # Deduplicate and limit
    seen: set[str] = set()
    unique: list[str] = []
    for c in concepts:
        c_lower = c.lower().strip()
        if c_lower not in seen and len(c_lower) > 3:
            seen.add(c_lower)
            unique.append(c)
    return unique[:max_concepts]


# ── Subject-specific query refinement ────────────────────────────────

_SUBJECT_QUERY_STYLE: dict[str, str] = {
    "history": "event_person_document",
    "social studies": "event_person_document",
    "civics": "event_person_document",
    "government": "event_person_document",
    "science": "process_organism_diagram",
    "biology": "process_organism_diagram",
    "chemistry": "process_organism_diagram",
    "physics": "process_organism_diagram",
    "math": "visual_representation",
    "mathematics": "visual_representation",
    "algebra": "visual_representation",
    "geometry": "visual_representation",
    "ela": "author_literary_period",
    "english": "author_literary_period",
    "language arts": "author_literary_period",
}


# ── Topic → entity map for reliable image queries ───────────────────
# When the lesson has no named historical figures, this map provides
# known-good Wikipedia-searchable entities for common topics.
# Wikipedia article thumbnails for these are verified relevant.
_TOPIC_IMAGE_QUERIES: dict[str, list[str]] = {
    "age of exploration": ["Christopher Columbus", "Vasco da Gama", "Ferdinand Magellan"],
    "exploration": ["Christopher Columbus", "Vasco da Gama", "caravel ship"],
    "renaissance": ["Leonardo da Vinci", "Michelangelo", "Raphael painter"],
    "reformation": ["Martin Luther", "John Calvin", "Protestant Reformation"],
    "absolutism": ["Louis XIV", "Palace of Versailles", "absolute monarchy"],
    "french revolution": ["Marie Antoinette", "Bastille", "Napoleon Bonaparte"],
    "american revolution": ["George Washington", "Declaration of Independence", "Paul Revere"],
    "civil war": ["Abraham Lincoln", "Battle of Gettysburg", "Ulysses Grant"],
    "reconstruction": ["Frederick Douglass", "Reconstruction era", "Freedmen's Bureau"],
    "industrial revolution": ["steam engine", "factory workers", "child labor industrial"],
    "world war i": ["trench warfare", "Archduke Franz Ferdinand", "Treaty of Versailles"],
    "world war ii": ["Adolf Hitler", "D-Day landing", "Holocaust"],
    "cold war": ["Berlin Wall", "Cuban Missile Crisis", "Iron Curtain"],
    "slavery": ["Frederick Douglass", "Harriet Tubman", "Underground Railroad"],
    "civil rights": ["Martin Luther King Jr", "Rosa Parks", "March on Washington"],
    "imperialism": ["Scramble for Africa", "British Empire", "colonialism"],
    "ancient egypt": ["Egyptian pyramid", "Sphinx", "pharaoh"],
    "ancient rome": ["Roman Colosseum", "Julius Caesar", "Roman Empire"],
    "ancient greece": ["Parthenon", "Socrates", "Athens acropolis"],
    "mesopotamia": ["Hammurabi", "Babylon ziggurat", "cuneiform writing"],
    "feudalism": ["medieval castle", "knight armor", "feudal system"],
    "crusades": ["Crusaders Jerusalem", "Richard I England", "Saladin"],
    "mongol empire": ["Genghis Khan", "Mongol Empire map", "Silk Road"],
    "ottoman empire": ["Sultan Suleiman", "Hagia Sophia", "Ottoman Empire"],
    "mughal empire": ["Taj Mahal", "Akbar emperor", "Mughal architecture"],
    "ming dynasty": ["Great Wall of China", "Ming Dynasty emperor", "Chinese junk ship"],
    "columbian exchange": ["Columbian Exchange", "New World crops", "transatlantic trade"],
    "triangular trade": ["triangular trade", "slave ship", "Atlantic slave trade"],
    "missouri compromise": ["Missouri Compromise", "Henry Clay", "slavery map 1820"],
    "manifest destiny": ["manifest destiny painting", "westward expansion", "Oregon Trail"],
    "gilded age": ["Andrew Carnegie", "Standard Oil", "railroad tycoon"],
    "progressive era": ["Theodore Roosevelt", "Jane Addams", "muckraker"],
    "new deal": ["Franklin Roosevelt", "Great Depression", "Civilian Conservation Corps"],
    "sectionalism": ["John C Calhoun", "slavery debate", "antebellum South"],
    "reform movements": ["suffrage march", "abolition movement", "temperance movement"],
    "women's suffrage": ["Susan B Anthony", "suffragette march", "19th Amendment"],
}


def _get_topic_queries(title: str) -> list[str]:
    """Return known-good image queries for a lesson title, or empty list."""
    title_lower = title.lower()
    for topic_key, queries in _TOPIC_IMAGE_QUERIES.items():
        if topic_key in title_lower:
            return queries
    # Partial word matches (e.g. "explorers" matches "exploration")
    title_words = set(title_lower.split())
    for topic_key, queries in _TOPIC_IMAGE_QUERIES.items():
        topic_words = set(topic_key.split())
        if topic_words & title_words:
            return queries
    return []


def extract_image_subjects(lesson: Any) -> list[dict[str, Any]]:
    """Extract specific people, places, and artifacts from lesson content for targeted image search.

    Priority:
    1. Named entities (people, places, documents) extracted from lesson text via regex
    2. Topic-keyword map lookup from lesson title — returns known-good Wikipedia queries
    3. Lesson title itself as fallback

    Filters out verb phrases, section headers, and other non-entity strings
    that regex would otherwise match.
    """
    subjects: list[dict[str, Any]] = []
    all_text = " ".join(filter(None, [
        getattr(lesson, 'title', ''),
        getattr(lesson, 'objective', ''),
        getattr(lesson, 'do_now', ''),
        getattr(lesson, 'direct_instruction', ''),
        getattr(lesson, 'guided_practice', ''),
    ]))

    # Named historical figures
    # Pattern 1: Titled names (King Louis, President Lincoln, etc.)
    # Pattern 2: Known first names of historical figures
    # Pattern 3: Any "Firstname Lastname" that appears near historical context
    common_non_names = {
        "The", "This", "That", "These", "Those", "When", "Where", "What",
        "How", "Why", "Each", "Every", "Your", "Their", "Some", "Many",
        "Most", "Both", "Other", "Such", "More", "Less", "New", "Old",
        "First", "Last", "Next", "Direct", "Independent", "Guided",
        "Exit", "Essential", "Key", "Primary", "Source", "Document",
        "Group", "Social", "Studies", "Grade", "Unit", "Lesson",
        "Common", "American", "English", "French", "British", "European",
        "Civil", "World", "Cold", "Middle", "South", "North", "West", "East",
        "Analyze", "Compare", "Evaluate", "Describe", "Explain", "Identify",
        "Test", "Review", "Movement", "Act", "Age", "Era", "Period",
    }
    # Common English verbs/adjectives that appear capitalized in headings
    # but are never historical entity names
    _non_name_second_words = {
        "Left", "Right", "Home", "Away", "Back", "Up", "Down", "Out", "Over",
        "Under", "Forever", "Together", "Apart", "Behind", "Ahead",
        "Looks", "Looked", "Looking", "Goes", "Went", "Gone", "Comes", "Came",
        "Changes", "Changed", "Begins", "Began", "Ends", "Ended", "Falls",
        "Fell", "Rises", "Rose", "Grows", "Grew", "Leads", "Led",
        "Succeeds", "Succeed", "Fails", "Failed", "Starts", "Stops",
        "Outward", "Forward", "Onward", "Beyond", "Across",
        "Explore", "Explores", "Explored", "Exploring", "Explorer",
        "Trade", "Trades", "Traded", "Trading",
        "Sail", "Sails", "Sailed", "Sailing",
        "Expand", "Expands", "Expanded", "Expanding", "Expansion",
        "Spread", "Spreads", "Discover", "Discovers", "Discovered",
        "Fight", "Fights", "Fighting", "Fought",
        "Create", "Creates", "Created", "Building", "Built",
        "Motivations", "Motivation", "Reasons", "Causes", "Effects",
        "Europe", "Europeans", "Asian", "African", "American",
        "Economic", "Political", "Religious", "Cultural", "Social",
        "Consequences", "Impact", "Significance", "Importance",
        "Developments", "Factors", "Events", "Period",
    }
    people_patterns = [
        r"((?:King |Queen |Emperor |Empress |President |Pope |Tsar |Czar )"
        r"[A-Z][a-z]+(?: [A-Z][a-z]+)*(?: the Great| [IVX]+)?)",
        r"((?:Louis|Peter|Frederick|Catherine|Elizabeth|Napoleon|Alexander)"
        r" (?:the Great|[IVX]+|[A-Z][a-z]+))",
        # General: Firstname Lastname (two+ capitalized words, not common English)
        r"\b([A-Z][a-z]{2,12} [A-Z][a-z]{2,15})\b",
        # Three-word names (Martin Luther King, John Quincy Adams)
        r"\b([A-Z][a-z]{2,12} [A-Z][a-z]{2,12} [A-Z][a-z]{2,12})\b",
    ]
    people_found: set[str] = set()
    for pattern in people_patterns:
        for match in re.findall(pattern, all_text):
            name = match.strip()
            if len(name) > 5:
                words = name.split()
                first_word = words[0]
                second_word = words[1] if len(words) > 1 else ""
                if first_word not in common_non_names and second_word not in _non_name_second_words:
                    people_found.add(name)
    for person in list(people_found)[:5]:
        subjects.append({"query": person, "type": "person", "label": person})

    # Named places/buildings
    place_patterns = re.findall(
        r"((?:Palace|Castle|Cathedral|Battle|Siege|Fort) of [A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        all_text,
    )
    for place in set(place_patterns[:3]):
        subjects.append({"query": f"{place} historical", "type": "place", "label": place})

    # Named places without "of" (e.g., "Versailles", "Bastille")
    famous_places = re.findall(
        r"\b(Versailles|Bastille|Kremlin|Vatican|Parliament|Westminster|Colosseum|Parthenon|Stonehenge)\b",
        all_text,
    )
    for place in set(famous_places[:2]):
        subjects.append({"query": place, "type": "place", "label": place})

    # Historical documents/treaties
    doc_patterns = re.findall(
        r"((?:Treaty|Declaration|Constitution|Bill|Act|Edict|Manifesto|Charter) of [A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        all_text,
    )
    for doc_name in set(doc_patterns[:2]):
        subjects.append({"query": doc_name, "type": "document", "label": doc_name})

    title = getattr(lesson, 'title', '')
    topic_queries = _get_topic_queries(title)

    # Topic-map queries always anchor the first positions — they are
    # curated, known-good Wikipedia entities that reliably produce the
    # most iconic/relevant images for the lesson topic (e.g. Columbus
    # portrait for Age of Exploration). Regex entities follow after.
    if topic_queries:
        result: list[dict[str, Any]] = [{"query": q, "type": "topic", "label": q} for q in topic_queries]
        # Append any regex-found entities that aren't already covered
        for s in subjects:
            if len(result) >= 5:
                break
            if not any(r["query"].lower() == s["query"].lower() for r in result):
                result.append(s)
        return result

    # No topic map match — use regex entities if found
    if subjects:
        return subjects

    # Last resort: lesson title main segment only
    main_title = re.split(r"[:—–-]", title)[0].strip() if title else "history"
    return [{"query": main_title, "type": "topic", "label": main_title}]


def _build_search_query(topic: str, subject: str = "") -> str:
    """Convert a lesson topic into a good image search query.

    Builds subject-aware queries that target specific visual content:
    - History: the specific event, person, or document mentioned
    - Science: the specific process or organism
    - Math: the specific visual representation
    - ELA: the author or literary period

    Examples::

        >>> _build_search_query('The American Revolution', 'history')
        'american revolution historical primary source'
        >>> _build_search_query('Photosynthesis', 'science')
        'photosynthesis diagram illustration'
        >>> _build_search_query('Solving Linear Equations', 'math')
        'solving linear equations mathematics education'
    """
    # Clean up the topic: strip punctuation, lower-case
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", topic).strip().lower()

    # Remove very common filler words to keep query focused
    stopwords = {"the", "a", "an", "of", "in", "on", "for", "and", "to", "is", "are"}
    words = [w for w in cleaned.split() if w not in stopwords]
    query_base = " ".join(words) if words else cleaned

    # Append subject-specific keywords
    subject_lower = subject.strip().lower()
    style = _SUBJECT_QUERY_STYLE.get(subject_lower, "")
    extra = _SUBJECT_KEYWORDS.get(subject_lower, ["education"])

    # Subject-style refinements: add specific qualifiers
    if style == "event_person_document":
        # History: look for dates, specific events
        date_match = re.search(r'\b(1[0-9]{3}|20[0-2][0-9])\b', topic)
        if date_match:
            extra = [date_match.group(), *extra[:1]]
    elif style == "process_organism_diagram":
        extra = ["diagram", *extra[:1]]
    elif style == "visual_representation":
        extra = ["graph", "diagram", *extra[:1]]
    elif style == "author_literary_period":
        extra = ["portrait", "literature", *extra[:1]]

    # Avoid duplicating words already in the query
    existing = set(query_base.split())
    suffix = " ".join(w for w in extra if w not in existing)

    return f"{query_base} {suffix}".strip()


# ── Relevance gate ───────────────────────────────────────────────────
#
# A noisy slide-title query (e.g. "Two Worlds Collide: What Columbus Found")
# can make Wikipedia's search rank a topically-unrelated article first — a real
# deck once landed a Catherine the Great portrait on a Columbus slide. We guard
# every accepted article by requiring it to share a meaningful word with the
# query, and SKIP the image otherwise. A MISSING image is better than a WRONG
# one: the slide compiler renders cleanly as text-only.

# Words that carry no topical signal for the title/query overlap check —
# includes the generic suffixes the query builder appends ("historical", etc.).
_RELEVANCE_STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "for", "and", "to", "is", "are", "what",
    "he", "she", "they", "his", "her", "their", "with", "from", "that", "this",
    "was", "were", "by", "as", "at", "it", "its", "into", "how", "why", "who",
    "when", "where", "two", "one", "new", "found", "wrote", "made", "over",
    "under", "between", "across", "history", "historical", "primary", "source",
    "sources", "education", "educational", "diagram", "illustration", "portrait",
    "literature", "mathematics", "graph", "photo", "image", "picture",
    "world", "worlds", "people", "account", "first", "describes", "writer",
    "celebrates", "observes", "began", "begins", "everything", "change",
    "changed", "goes", "ways", "both", "letter", "voyage",
}


def _key_tokens(text: str) -> set[str]:
    """Significant lower-case tokens (>=4 chars, not stopwords) for relevance."""
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text or "").lower()
    return {w for w in cleaned.split()
            if len(w) >= 4 and w not in _RELEVANCE_STOPWORDS}


def _pick_relevant_article(query: str, results: list[dict[str, Any]]) -> str | None:
    """Pick the search result whose title best overlaps the query's key tokens.

    Returns the title sharing the MOST meaningful words with the query, or None
    when no result shares any — signalling the caller to skip the image rather
    than show an unrelated one. Falls back to the top result only when the query
    yields no usable tokens to validate against.
    """
    if not results:
        return None
    q_tokens = _key_tokens(query)
    if not q_tokens:
        return str(results[0].get("title") or "") or None
    best_title: str | None = None
    best_overlap = 0
    for r in results:
        title = str(r.get("title") or "")
        overlap = len(_key_tokens(title) & q_tokens)
        if overlap > best_overlap:
            best_overlap = overlap
            best_title = title
    return best_title


# ── Source selection ─────────────────────────────────────────────────


def _select_sources(subject: str, topic: str = "") -> list[str]:
    """Pick the best image sources for this subject.

    Returns an ordered list of source identifiers to try. Web image search
    (broad topical coverage) is tried first, then license-clean academic sources
    (LoC public domain, Wikipedia article thumbnails). Whatever is fetched is
    then screened by the vision-model relevance filter (``check_image_quality``),
    which looks at the actual pixels and rejects off-topic, text-only, and
    watermarked results — so broad sourcing is safe here: a wrong or watermarked
    image never survives the downstream screen. A missing image beats a wrong one.
    """
    subject_lower = subject.strip().lower()
    if any(s in subject_lower
           for s in ("science", "biology", "chemistry", "physics", "art", "music")):
        return ["teacher_files", "web", "wikimedia", "loc"]
    return ["teacher_files", "web", "loc", "wikimedia"]


# ── Cache helpers ────────────────────────────────────────────────────


def _cache_path(source: str, query: str, base: Path | None = None) -> Path:
    """Return the local cache path for a given source + query."""
    h = hashlib.sha256(f"{source}:{query}".encode()).hexdigest()[:16]
    root = base or _CACHE_DIR
    return root / source / f"{h}.jpg"


def _check_cache(source: str, query: str, base: Path | None = None) -> Path | None:
    """Return cached image path if it exists and is non-empty."""
    path = _cache_path(source, query, base)
    if path.exists() and path.stat().st_size > 0:
        logger.debug("Image cache hit [%s] for query: %s", source, query)
        return path
    return None


def _save_to_cache(
    data: bytes, source: str, query: str, base: Path | None = None,
) -> Path:
    """Write image bytes to the cache and return the path."""
    path = _cache_path(source, query, base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


# ── Individual source fetchers ───────────────────────────────────────


async def _fetch_loc(
    query: str, cache_dir: Path | None = None,
) -> Path | None:
    """Fetch an image from the Library of Congress free API.

    Endpoint returns JSON with ``results[].image_url`` (list) or
    ``results[].thumb_gallery``.
    """
    import httpx

    cached = _check_cache("loc", query, cache_dir)
    if cached:
        return cached

    url = "https://www.loc.gov/search/"
    params: dict[str, str | int] = {
        "q": query,
        "fa": "online-format:image",
        "fo": "json",
        "c": 5,
    }

    try:
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            image_url: str | None = None
            for item in results:
                # Prefer image_url (list of URLs)
                urls = item.get("image_url", [])
                if urls:
                    # Take highest resolution (last URL), strip fragment
                    image_url = urls[-1].split("#")[0]
                    break
                # Fallback to thumb_gallery
                thumb = item.get("thumb_gallery")
                if thumb:
                    image_url = thumb
                    break

            if not image_url:
                logger.debug("No LOC results for query: %s", query)
                return None

            # v4.11.2026.1 SSRF guard
            if not _is_safe_image_url(image_url):
                logger.warning(
                    "LOC returned unsafe image URL (blocked SSRF): %s",
                    image_url,
                )
                return None

            img_resp = await client.get(image_url, timeout=_FETCH_TIMEOUT)
            img_resp.raise_for_status()

            path = _save_to_cache(img_resp.content, "loc", query, cache_dir)
            logger.info("Downloaded LOC image for '%s' -> %s", query, path)
            return path

    except Exception as e:
        logger.debug("LOC fetch failed for '%s': %s", query, e)
        return None


async def _fetch_wikimedia(
    query: str, cache_dir: Path | None = None,
) -> Path | None:
    """Fetch a relevant image from Wikipedia/Wikimedia for a given query.

    Strategy (in order):
    1. Wikipedia article thumbnail — search for the Wikipedia article most
       closely matching the query, then pull its lead image.  This gives the
       canonical, highly-relevant image editors chose for that topic.
    2. Wikimedia Commons file search — fallback when no article image exists.

    Wikipedia article thumbnails are almost always directly relevant
    (e.g. "Hernán Cortés" → his portrait, "Caravel" → a drawing of one).
    The old Commons file-namespace search returned loosely-matching results.
    """
    import httpx

    cached = _check_cache("wikimedia", query, cache_dir)
    if cached:
        return cached

    headers = {"User-Agent": "ClawED/1.0 (https://github.com/SirhanMacx/Claw-ED; educational)"}

    try:
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT, headers=headers) as client:

            # ── Strategy 1: Wikipedia article thumbnail ───────────────────
            # Use the Wikipedia OpenSearch to find the best-matching article,
            # then fetch its page image via the pageimages prop.
            search_resp = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": 5,
                    "srnamespace": 0,
                    "format": "json",
                },
            )
            search_resp.raise_for_status()
            search_data = search_resp.json()
            search_results = search_data.get("query", {}).get("search", [])

            # Relevance-gate the search results: skip an article that shares no
            # meaningful word with the query (a MISSING image beats a WRONG one).
            page_title = _pick_relevant_article(query, search_results)
            if not page_title and search_results:
                logger.info(
                    "Wikipedia results for '%s' share no key term with the query "
                    "(top: %r) — skipping to avoid an irrelevant image",
                    query, [r.get("title") for r in search_results[:3]],
                )
            if page_title:
                img_resp = await client.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "titles": page_title,
                        "prop": "pageimages",
                        "pithumbsize": 1200,
                        "piprop": "thumbnail",
                        "format": "json",
                    },
                )
                img_resp.raise_for_status()
                img_data = img_resp.json()
                pages = img_data.get("query", {}).get("pages", {})
                image_url: str | None = None
                for page in pages.values():
                    thumb = page.get("thumbnail", {})
                    if thumb.get("source"):
                        image_url = thumb["source"]
                        break

                if image_url:
                    # v4.11.2026.1 SSRF guard
                    if not _is_safe_image_url(image_url):
                        logger.warning(
                            "Wikipedia returned unsafe image URL "
                            "(blocked SSRF): %s",
                            image_url,
                        )
                    else:
                        dl = await client.get(image_url, timeout=_FETCH_TIMEOUT)
                        dl.raise_for_status()
                        path = _save_to_cache(dl.content, "wikimedia", query, cache_dir)
                        logger.info(
                            "Wikipedia article image for '%s' (article: '%s') -> %s",
                            query, page_title, path,
                        )
                        return path

            # Commons file-namespace search is DISABLED.
            # It matches on file description text and returns completely
            # unrelated content (e.g. government CBRN weapons presentations
            # for "Religious Motivations" queries). Wikipedia article
            # thumbnails are the only safe source — if no article image
            # exists for a query, return None rather than risk an
            # irrelevant or harmful image.
            logger.debug("No Wikipedia article image for query: %s", query)
            return None

    except Exception as e:
        logger.debug("Wikimedia fetch failed for '%s': %s", query, e)
        return None


def _get_unsplash_key() -> str | None:
    """Return the Unsplash access key from env or config, or None."""
    key = os.environ.get("UNSPLASH_ACCESS_KEY")
    if key:
        return key
    # Try the secure config store
    try:
        from clawed.config import get_api_key

        return get_api_key("unsplash")
    except ImportError:
        return None


async def _fetch_unsplash(
    query: str, cache_dir: Path | None = None,
) -> Path | None:
    """Fetch an image from the Unsplash API (requires API key)."""
    import httpx

    access_key = _get_unsplash_key()
    if not access_key:
        logger.debug("No Unsplash API key configured -- skipping")
        return None

    cached = _check_cache("unsplash", query, cache_dir)
    if cached:
        return cached

    url = "https://api.unsplash.com/search/photos"
    params: dict[str, str | int] = {
        "query": query,
        "per_page": 1,
        "orientation": "landscape",
    }
    headers = {"Authorization": f"Client-ID {access_key}"}

    try:
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            if not results:
                logger.debug("No Unsplash results for query: %s", query)
                return None

            image_url = results[0]["urls"].get("regular") or results[0]["urls"].get("small")
            if not image_url:
                return None

            # v4.11.2026.1 SSRF guard
            if not _is_safe_image_url(image_url):
                logger.warning(
                    "Unsplash returned unsafe image URL (blocked SSRF): %s",
                    image_url,
                )
                return None

            img_resp = await client.get(image_url, timeout=_FETCH_TIMEOUT)
            img_resp.raise_for_status()

            path = _save_to_cache(img_resp.content, "unsplash", query, cache_dir)
            logger.info("Downloaded Unsplash image for '%s' -> %s", query, path)
            return path

    except Exception as e:
        logger.debug("Unsplash fetch failed for '%s': %s", query, e)
        return None


def _score_teacher_image_row(
    row: Any,
    keywords: list[str],
    query_lower: str,
) -> int:
    """Score a teacher image row by relevance to the search keywords.

    Scoring rules:
    - Exact phrase match in context/title: +5
    - Keyword found in filename (basename of image_path): +3 per keyword
    - Keyword found in context_text or asset title: +2 per keyword
    - Partial word match (e.g. "suffrage" in "suffragist"): +1 per keyword
    """
    context = (row["context_text"] or "").lower()
    title = (row["title"] or "").lower()
    image_path = (row["image_path"] or "").lower()
    filename = Path(image_path).stem.replace("_", " ").replace("-", " ").lower()
    combined = f"{context} {title}"

    score = 0

    # Exact phrase match in content gets big bonus
    if query_lower in combined:
        score += 5

    # Keyword matches -- filename matches are weighted higher
    for kw in keywords:
        if kw in filename:
            score += 3
        if kw in combined:
            score += 2

    # Partial word matches (e.g., "suffrage" matches "suffragist")
    for kw in keywords:
        if kw not in combined and kw not in filename:
            all_words = combined.split() + filename.split()
            for word in all_words:
                if len(kw) >= 4 and len(word) >= 4 and (kw in word or word in kw):
                    score += 1
                    break

    return score


def _query_teacher_images_db(
    search_keywords: list[str],
    limit: int = 150,
) -> list[Any]:
    """Run a SQL query against the teacher's image database.

    Returns matching rows with image_path, context_text, and title.
    Uses OR matching so any single keyword can surface results.
    """
    import sqlite3

    from clawed.paths import data_dir
    db_path = data_dir() / "memory" / "curriculum_kb.db"
    if not db_path.exists():
        return []

    if not search_keywords:
        return []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        like_clauses = " OR ".join(
            "(lower(ai.context_text) LIKE '%' || ? || '%'"
            " OR lower(a.title) LIKE '%' || ? || '%'"
            " OR lower(ai.image_path) LIKE '%' || ? || '%')"
            for _ in search_keywords[:8]
        )
        params: list[str] = []
        for kw in search_keywords[:8]:
            params.extend([kw, kw, kw])
        rows = conn.execute(
            f"SELECT ai.image_path, ai.context_text, a.title "
            f"FROM asset_images ai "
            f"JOIN assets a ON ai.asset_id = a.id "
            f"WHERE ai.image_path != '' AND ({like_clauses}) "
            f"LIMIT {limit}",
            params,
        ).fetchall()
    return rows


def _best_from_rows(
    rows: list[Any],
    keywords: list[str],
    query_lower: str,
    min_score: int = 4,
) -> Path | None:
    """Pick the best image from a set of DB rows, respecting a minimum score."""
    if not rows:
        return None

    scored: list[tuple[int, str]] = []
    for row in rows:
        s = _score_teacher_image_row(row, keywords, query_lower)
        if s >= min_score:
            scored.append((s, row["image_path"]))

    if not scored:
        return None

    # Sort descending by score, take best
    scored.sort(key=lambda x: x[0], reverse=True)
    # Return the top match if file actually exists
    for _score, path_str in scored[:5]:
        p = Path(path_str)
        if p.exists():
            return p

    return None


async def _fetch_teacher_image(
    query: str,
    cache_dir: Path | None = None,
    subject: str = "",
) -> Path | None:
    """Search the teacher's extracted images with progressive broadening.

    Checks the asset_images table for images whose context_text, parent
    asset title, or filename has keyword overlap with the query.  Uses a
    three-stage search strategy:

    1. **Full query** -- all keywords combined (high precision)
    2. **Individual keywords** -- each significant keyword independently
       (broader recall), scored by how many terms match
    3. **Subject fallback** -- just the subject name (broadest)

    Returns the local image path if found -- no network call needed.
    """
    try:
        # Stage 1: Full query -- all keywords at once
        all_keywords = [w.lower() for w in query.split() if len(w) > 2]
        if not all_keywords:
            return None

        query_lower = query.lower()
        rows = _query_teacher_images_db(all_keywords)

        result = _best_from_rows(rows, all_keywords, query_lower, min_score=6)
        if result:
            logger.info(
                "Teacher image match (full query) for '%s' -> %s", query, result,
            )
            return result

        # Stage 2: Try individual significant keywords (drop stopwords + short words)
        # Sort keywords longest-first so the most specific term is tried first
        stopwords = {"the", "a", "an", "of", "in", "on", "for", "and", "to", "is", "are", "was", "were"}
        significant = sorted(
            [w for w in all_keywords if w not in stopwords and len(w) > 3],
            key=len,
            reverse=True,
        )

        for kw in significant:
            kw_rows = _query_teacher_images_db([kw])
            # Score against all original keywords even though we searched by one
            result = _best_from_rows(kw_rows, all_keywords, query_lower, min_score=4)
            if result:
                logger.info(
                    "Teacher image match (keyword '%s') for '%s' -> %s",
                    kw, query, result,
                )
                return result

        # Stage 3: Subject-name fallback (e.g., "history", "biology")
        if subject:
            subj_lower = subject.strip().lower()
            subj_keywords = [w for w in subj_lower.split() if len(w) > 2]
            if subj_keywords:
                subj_rows = _query_teacher_images_db(subj_keywords)
                result = _best_from_rows(
                    subj_rows, all_keywords + subj_keywords, query_lower, min_score=3,
                )
                if result:
                    logger.info(
                        "Teacher image match (subject '%s') for '%s' -> %s",
                        subject, query, result,
                    )
                    return result

    except Exception as e:
        logger.debug("Teacher image lookup failed: %s", e)
    return None


async def _fetch_web_scrape(
    query: str, cache_dir: Path | None = None,
) -> Path | None:
    """Scrape an image from the web via DuckDuckGo image search.

    No API key needed. Uses the DDG image search endpoint which returns
    direct image URLs. This is the most reliable source for specific
    educational images (diagrams, maps, historical figures, etc.).

    Includes retry logic for VQD token acquisition (DDG can be flaky)
    and graceful fallback when DDG is unavailable.
    """
    import asyncio

    import httpx

    cached = _check_cache("web", query, cache_dir)
    if cached:
        return cached

    # DDG image search endpoint
    search_url = "https://duckduckgo.com/"

    # VQD token patterns — DDG changes these periodically
    vqd_patterns = [
        r"vqd=([^&'\"]+)",
        r"vqd['\"]:\s*['\"]([^'\"]+)",
        r"vqd4=([^&'\"]+)",
        r"vqd=\"([^\"]+)\"",
    ]

    # Retry settings for VQD acquisition
    max_vqd_attempts = 3
    backoff_seconds = [0.5, 1.5, 3.0]

    try:
        async with httpx.AsyncClient(
            timeout=8.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            },
        ) as client:
            # Acquire VQD token with retry logic
            vqd: str | None = None
            last_error: Exception | None = None

            for attempt in range(max_vqd_attempts):
                try:
                    resp = await client.get(
                        search_url, params={"q": query}, timeout=5.0,
                    )
                    # Try multiple VQD token patterns (DDG changes format)
                    for pattern in vqd_patterns:
                        vqd_match = re.search(pattern, resp.text)
                        if vqd_match:
                            vqd = vqd_match.group(1)
                            break
                    if vqd:
                        break
                except httpx.TimeoutException as e:
                    last_error = e
                    logger.debug(
                        "DDG VQD request timed out (attempt %d/%d) for: %s",
                        attempt + 1, max_vqd_attempts, query,
                    )
                except httpx.HTTPStatusError as e:
                    last_error = e
                    logger.debug(
                        "DDG returned HTTP %d (attempt %d/%d) for: %s",
                        e.response.status_code, attempt + 1, max_vqd_attempts, query,
                    )
                except httpx.HTTPError as e:
                    last_error = e
                    logger.debug(
                        "DDG request failed (attempt %d/%d) for '%s': %s",
                        attempt + 1, max_vqd_attempts, query, e,
                    )

                # Backoff before retry (skip on last attempt)
                if attempt < max_vqd_attempts - 1:
                    backoff = backoff_seconds[min(attempt, len(backoff_seconds) - 1)]
                    await asyncio.sleep(backoff)

            if not vqd:
                if last_error:
                    logger.warning(
                        "DDG unavailable for '%s' after %d attempts (%s); "
                        "falling back to next image source",
                        query, max_vqd_attempts, type(last_error).__name__,
                    )
                else:
                    logger.warning(
                        "Could not extract DDG VQD token for '%s' after %d attempts; "
                        "DDG may have changed their page format — "
                        "falling back to next image source",
                        query, max_vqd_attempts,
                    )
                return None

            # Fetch image results using the VQD token
            img_url = "https://duckduckgo.com/i.js"
            img_params = {
                "q": query,
                "vqd": vqd,
                "l": "us-en",
                "o": "json",
                "f": ",,,,,",
                "p": "1",
            }

            try:
                img_resp = await client.get(img_url, params=img_params)
            except httpx.HTTPError as e:
                logger.warning(
                    "DDG image results request failed for '%s': %s; "
                    "falling back to next image source",
                    query, e,
                )
                return None

            if img_resp.status_code != 200:
                logger.warning(
                    "DDG image results returned HTTP %d for '%s'; "
                    "falling back to next image source",
                    img_resp.status_code, query,
                )
                return None

            try:
                data = img_resp.json()
            except (ValueError, KeyError) as e:
                logger.warning("DDG returned invalid JSON for '%s': %s", query, e)
                return None

            results = data.get("results", [])
            if not results:
                logger.debug("No DDG image results for: %s", query)
                return None

            # Pick the first result with a reasonable image
            # v4.11.2026.1 SSRF guard: reject URLs whose host is a
            # loopback / link-local / private / reserved IP literal.
            image_url = None
            for r in results[:5]:
                url = r.get("image", "")
                if (
                    url
                    and url.startswith("http")
                    and not url.endswith(".svg")
                    and not _is_stock_photo_url(url)
                    and _is_safe_image_url(url)
                ):
                    image_url = url
                    break

            if not image_url:
                return None

            # Download the image
            try:
                dl_resp = await client.get(image_url, timeout=_FETCH_TIMEOUT)
                dl_resp.raise_for_status()
            except httpx.HTTPError as e:
                logger.debug("Failed to download DDG image from %s: %s", image_url, e)
                return None

            if len(dl_resp.content) < 1000:
                return None  # Too small, probably an error page

            path = _save_to_cache(dl_resp.content, "web", query, cache_dir)
            logger.info("Downloaded web image for '%s' -> %s", query, path)
            return path

    except Exception as e:
        logger.warning(
            "DDG web image scrape failed for '%s': %s; "
            "falling back to next image source",
            query, e,
        )
        return None


# Source name -> fetcher function mapping
_SOURCE_FETCHERS: dict[str, Any] = {
    "teacher_files": _fetch_teacher_image,
    "web": _fetch_web_scrape,
    "loc": _fetch_loc,
    "wikimedia": _fetch_wikimedia,
    "unsplash": _fetch_unsplash,
}


# ── Public API ───────────────────────────────────────────────────────


async def fetch_slide_image(
    topic: str,
    subject: str = "",
    cache_dir: Path | None = None,
) -> Path | None:
    """Fetch a relevant image for a slide topic.

    Tries sources in priority order:
      1. Teacher's own uploaded images (personalized, no network needed)
      2. Library of Congress (free, public domain, high quality)
      3. Wikimedia Commons (free, CC-licensed)
      4. Unsplash (requires API key, may not be configured)

    If a teacher image is found, external sources are skipped entirely.
    Failures at each level cascade to the next source.

    Parameters
    ----------
    topic:
        The slide topic / title (e.g. "The American Revolution").
    subject:
        Optional subject area for better source routing and teacher image search.
    cache_dir:
        Override cache directory (useful for tests).
    """
    # Run cache cleanup once per session
    _cleanup_cache(cache_dir)

    query = _build_search_query(topic, subject)
    sources = _select_sources(subject, topic)

    for source_name in sources:
        fetcher = _SOURCE_FETCHERS.get(source_name)
        if not fetcher:
            continue
        try:
            # Pass subject to teacher image fetcher for subject-aware broadening
            if source_name == "teacher_files":
                path: Path | None = await fetcher(query, cache_dir, subject=subject)
            else:
                path = await fetcher(query, cache_dir)
            if path:
                return path
        except Exception as e:
            logger.debug("Source %s failed for '%s': %s", source_name, query, e)
            continue

    logger.debug("No image found from any source for '%s'", query)
    return None


async def fetch_content_image(
    content_text: str,
    subject: str = "",
    fallback_topic: str = "",
    cache_dir: Path | None = None,
) -> Path | None:
    """Fetch an image based on the *content* of a slide, not just the title.

    Extracts key concepts from ``content_text`` and searches for each one
    individually, returning the first good result.  Falls back to
    ``fallback_topic`` (typically the lesson title) if no concept-specific
    image is found.

    Parameters
    ----------
    content_text:
        The slide body text to extract search concepts from.
    subject:
        Subject area for source routing and query enrichment.
    fallback_topic:
        Lesson title used as a last resort if concept extraction
        yields no results.
    cache_dir:
        Override cache directory (useful for tests).
    """
    concepts = _extract_key_concepts(content_text)

    for concept in concepts:
        query = _build_search_query(concept, subject)
        sources = _select_sources(subject, concept)

        for source_name in sources:
            fetcher = _SOURCE_FETCHERS.get(source_name)
            if not fetcher:
                continue
            try:
                if source_name == "teacher_files":
                    path: Path | None = await fetcher(query, cache_dir, subject=subject)
                else:
                    path = await fetcher(query, cache_dir)
                if path:
                    logger.info(
                        "Content image found via concept '%s' -> %s",
                        concept, path,
                    )
                    return path
            except Exception as e:
                logger.debug(
                    "Source %s failed for concept '%s': %s",
                    source_name, concept, e,
                )
                continue

    # Fallback to lesson title
    if fallback_topic:
        logger.debug(
            "No concept-specific image found, falling back to topic: %s",
            fallback_topic,
        )
        return await fetch_slide_image(fallback_topic, subject, cache_dir)

    return None
