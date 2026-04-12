"""Teacher persona extraction from ingested documents."""

from __future__ import annotations

from pathlib import Path

from clawed.llm import LLMClient
from clawed.models import AppConfig, Document, TeacherPersona

PROMPT_PATH = Path(__file__).parent / "prompts" / "persona_extract.txt"


_MAX_TOTAL_CHARS = 50_000  # ~12k tokens — fits comfortably in any model's context
_MAX_PER_DOC_CHARS = 3_000
_MAX_DOCS = 30  # Sample at most 30 representative documents


def _build_document_block(documents: list[Document]) -> str:
    """Format documents for insertion into the prompt.

    For large corpora (1000+ docs), samples representative documents
    to stay within LLM context limits.
    """
    # Sample if corpus is very large
    sampled = documents
    if len(documents) > _MAX_DOCS:
        import random
        # Deterministic sample for reproducibility
        rng = random.Random(42)
        sampled = rng.sample(documents, _MAX_DOCS)

    parts: list[str] = []
    total = 0
    for i, doc in enumerate(sampled, 1):
        excerpt = doc.content[:_MAX_PER_DOC_CHARS]
        if total + len(excerpt) > _MAX_TOTAL_CHARS:
            break
        parts.append(
            f"--- Document {i}: {doc.title} ({doc.doc_type.value}) ---\n"
            f"{excerpt}\n"
        )
        total += len(excerpt)

    return "\n".join(parts)


async def extract_persona(
    documents: list[Document],
    config: AppConfig | None = None,
) -> TeacherPersona:
    """Analyze teaching documents and extract a structured persona.

    Sends document excerpts to the configured LLM and parses the returned
    JSON into a TeacherPersona model.
    """
    if not documents:
        raise ValueError("No documents provided for persona extraction.")

    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    doc_block = _build_document_block(documents)
    prompt = prompt_template.replace("{documents}", doc_block)

    client = LLMClient(config)
    data = await client.generate_json(
        prompt=prompt,
        system="You are an educational analysis assistant. Respond only with valid JSON.",
        temperature=0.3,
    )

    return TeacherPersona.model_validate(data)


# ── Persona merging (continuous improvement) ────────────────────────────

# Maximum list lengths to prevent unbounded growth
_LIST_CAPS: dict[str, int] = {
    "source_types": 10,
    "activity_patterns": 10,
    "scaffolding_moves": 10,
    "voice_examples": 10,
    "signature_moves": 8,
}

# String fields: only overwrite if existing is empty/default
_STRING_FIELDS = (
    "tone",
    "voice_sample",
    "do_now_style",
    "exit_ticket_style",
    "handout_style",
    "grouping_preferences",
)

# List fields eligible for union-dedup merge
_LIST_FIELDS = (
    "source_types",
    "activity_patterns",
    "scaffolding_moves",
    "signature_moves",
    "voice_examples",
)

# Identity fields: never overwrite from new extraction
_IDENTITY_FIELDS = ("teaching_style", "vocabulary_level")


def _dedup_extend(existing: list[str], new: list[str], cap: int) -> list[str]:
    """Union two lists, dedup by lowercased comparison, existing first."""
    seen = {item.lower().strip() for item in existing}
    merged = list(existing)
    for item in new:
        key = item.lower().strip()
        if key and key not in seen:
            merged.append(item)
            seen.add(key)
    return merged[:cap]


def merge_persona(existing: TeacherPersona, new: TeacherPersona) -> TeacherPersona:
    """Incrementally merge a new persona extraction with an existing one.

    Strategy: keep existing voice identity, merge pedagogical patterns.
    - Lists (source_types, activity_patterns, scaffolding_moves, signature_moves,
      voice_examples): union and dedup, existing first
    - Strings (tone, voice_sample, do_now_style, exit_ticket_style, handout_style,
      grouping_preferences): keep existing if non-empty, else use new
    - Teaching style, vocabulary level: keep existing (core identity doesn't change)
    """
    # Start from a copy of existing
    data = existing.model_dump()

    # Merge list fields with dedup
    for field in _LIST_FIELDS:
        cap = _LIST_CAPS.get(field, 10)
        existing_list = getattr(existing, field, [])
        new_list = getattr(new, field, [])
        data[field] = _dedup_extend(existing_list, new_list, cap)

    # String fields: only update if existing is empty/default
    for field in _STRING_FIELDS:
        existing_val = getattr(existing, field, "")
        new_val = getattr(new, field, "")
        if (not existing_val or existing_val == TeacherPersona.model_fields[field].default) and new_val:
            data[field] = new_val

    # Identity fields: always keep existing (never overwrite)
    for field in _IDENTITY_FIELDS:
        data[field] = getattr(existing, field)

    return TeacherPersona.model_validate(data)


def save_persona(persona: TeacherPersona, output_dir: Path) -> Path:
    """Save a persona to disk as JSON.

    Enriches the persona name from the teacher profile in config (if
    available) since the LLM extraction doesn't reliably detect the
    teacher's actual name from documents.
    """
    # Enrich name from config teacher_profile if still default
    if persona.name == "My Teaching Persona":
        try:
            from clawed.models import AppConfig
            cfg = AppConfig.load()
            if cfg.teacher_profile and cfg.teacher_profile.name:
                persona = persona.model_copy(
                    update={"name": f"{cfg.teacher_profile.name}'s Teaching Style"}
                )
        except ImportError:
            pass

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "persona.json"
    path.write_text(persona.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_persona(path: Path) -> TeacherPersona:
    """Load a persona from a JSON file."""
    if not path.exists():
        raise FileNotFoundError(f"Persona file not found: {path}")
    return TeacherPersona.model_validate_json(path.read_text(encoding="utf-8"))
