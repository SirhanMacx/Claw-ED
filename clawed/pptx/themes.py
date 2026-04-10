"""Topic-based visual theming for PPTX slides.

Maps lesson topic keywords to color palettes so that a lesson on the
Renaissance gets warm browns while a lesson on chemistry gets teals.

Extracted from the monolithic export_pptx.py for maintainability.
The canonical subject-based themes live in ``clawed.export_theme``;
this module adds topic-keyword matching on top.
"""

from __future__ import annotations

# ── Topic-based theme definitions ─────────────────────────────────────
# Each entry: ([keywords], {palette dict})
# First match wins when scanning lesson title + subject.

TOPIC_THEMES: list[tuple[list[str], dict[str, str]]] = [
    # Exploration / nautical topics
    (
        [
            "exploration",
            "nautical",
            "voyage",
            "navigation",
            "maritime",
            "columbus",
            "magellan",
            "ocean",
            "sailing",
            "expedition",
            "discover",
        ],
        {
            "primary": "1a3a5c",
            "secondary": "c9a96e",
            "accent": "e8eef5",
            "bg_dark": "0f2440",
            "bg_light": "f0f3f8",
            "text_dark": "1A1A1A",
            "text_light": "FFFFFF",
            "text_dim": "888888",
        },
    ),
    # Renaissance / art / history topics — Jon's warm brown palette
    (
        [
            "renaissance",
            "art",
            "painting",
            "sculpture",
            "michelangelo",
            "da vinci",
            "medici",
            "baroque",
            "classical art",
            "gallery",
            "fresco",
            "patron",
            "reform",
            "movement",
            "amendment",
            "constitution",
            "rights",
            "abolition",
            "suffrage",
            "progressive",
        ],
        {
            "primary": "8B6914",
            "secondary": "DAA520",
            "accent": "F5E6C8",
            "bg_dark": "2C1810",
            "bg_light": "FFF8F0",
            "text_dark": "2C1810",
            "text_light": "FFFFFF",
            "text_dim": "888888",
        },
    ),
    # Revolution / war topics
    (
        [
            "revolution",
            "war",
            "battle",
            "conflict",
            "military",
            "independence",
            "civil war",
            "rebellion",
            "uprising",
            "army",
            "combat",
            "wwi",
            "wwii",
            "world war",
        ],
        {
            "primary": "8b0000",
            "secondary": "ffd700",
            "accent": "fce8e8",
            "bg_dark": "4a0000",
            "bg_light": "fdf5f5",
            "text_dark": "1A1A1A",
            "text_light": "FFFFFF",
            "text_dim": "888888",
        },
    ),
    # Science topics
    (
        [
            "science",
            "biology",
            "chemistry",
            "physics",
            "experiment",
            "hypothesis",
            "laboratory",
            "cell",
            "atom",
            "molecule",
            "ecosystem",
            "evolution",
            "genetics",
        ],
        {
            "primary": "1a4a4a",
            "secondary": "00c853",
            "accent": "e0f5ef",
            "bg_dark": "0f2e2e",
            "bg_light": "f0faf5",
            "text_dark": "1A1A1A",
            "text_light": "FFFFFF",
            "text_dim": "888888",
        },
    ),
    # Math topics
    (
        [
            "math",
            "algebra",
            "geometry",
            "calculus",
            "equation",
            "fraction",
            "polynomial",
            "trigonometry",
            "statistics",
            "probability",
            "arithmetic",
            "number",
        ],
        {
            "primary": "2a1a4a",
            "secondary": "ff9800",
            "accent": "f0e8f8",
            "bg_dark": "1a0f30",
            "bg_light": "f8f5fc",
            "text_dark": "1A1A1A",
            "text_light": "FFFFFF",
            "text_dim": "888888",
        },
    ),
]

DEFAULT_TOPIC_THEME: dict[str, str] = {
    "primary": "2D5F3C",
    "secondary": "D4A843",
    "accent": "EAF0E4",
    "bg_dark": "1A3D25",
    "bg_light": "F4F7F2",
    "text_dark": "1A1A1A",
    "text_light": "FFFFFF",
    "text_dim": "888888",
}


def get_topic_theme(title: str, subject: str = "") -> dict[str, str]:
    """Select a color theme based on lesson topic keywords.

    Scans the lesson title and subject for keywords associated with
    thematic palettes. Returns the first matching theme or the default.
    """
    combined = f"{title} {subject}".lower()
    for keywords, theme in TOPIC_THEMES:
        for kw in keywords:
            if kw in combined:
                return theme
    return DEFAULT_TOPIC_THEME
