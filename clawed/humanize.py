"""AI writing detection and removal — make Ed's output sound human.

Detects and replaces AI-isms (characteristic phrases, vocabulary, and
structures that reveal machine authorship) so generated lessons read
like the teacher wrote them, not ChatGPT.

Adapted from: https://github.com/conorbronsdon/avoid-ai-writing

Three tiers:
- Tier 1: Always flagged and replaced (obvious AI tells)
- Tier 2: Flagged when clustered (2+ in same paragraph)
- Tier 3: Flagged only at high density (>3 per 500 words)
"""
from __future__ import annotations

import re

# ── Tier 1: Always replace (obvious AI tells) ───────────────────────

TIER1_REPLACEMENTS: dict[str, str] = {
    "delve": "explore",
    "delved": "explored",
    "delves": "explores",
    "delving": "exploring",
    "utilize": "use",
    "utilized": "used",
    "utilizes": "uses",
    "utilizing": "using",
    "utilization": "use",
    "leverage": "use",
    "leveraged": "used",
    "leverages": "uses",
    "leveraging": "using",
    "facilitate": "help",
    "facilitated": "helped",
    "facilitates": "helps",
    "facilitating": "helping",
    "Moreover": "Also",
    "Furthermore": "Also",
    "Additionally": "Also",
    "In conclusion, ": "To wrap up, ",
    "in conclusion, ": "to wrap up, ",
    "To conclude, ": "Finally, ",
    "to conclude, ": "finally, ",
    "Consequently": "So",
    "Nevertheless": "But",
    "Nonetheless": "Still",
    "Henceforth": "From now on",
    "Whereby": "where",
    "Thereof": "of it",
    "Therein": "in it",
    "paramount": "important",
    "pivotal": "key",
    "indispensable": "essential",
    "multifaceted": "complex",
    "comprehensive": "full",
    "robust": "strong",
    "synergy": "teamwork",
    "paradigm": "model",
    "holistic": "complete",
    "nuanced": "detailed",
    "myriad": "many",
    "plethora": "many",
    "tapestry": "mix",
    "landscape": "field",
    "realm": "area",
    "sphere": "area",
    "arena": "area",
    "ecosystem": "system",
    "foster": "encourage",
    "fostered": "encouraged",
    "fosters": "encourages",
    "fostering": "encouraging",
    "cultivate": "build",
    "cultivated": "built",
    "cultivates": "builds",
    "cultivating": "building",
    "harness": "use",
    "harnessed": "used",
    "harnessing": "using",
    "spearhead": "lead",
    "spearheaded": "led",
    "spearheading": "leading",
    "navigate": "handle",
    "navigated": "handled",
    "navigating": "handling",
    "embark": "start",
    "embarked": "started",
    "embarking": "starting",
    "underscore": "show",
    "underscored": "showed",
    "underscores": "shows",
    "underscoring": "showing",
    "beacon": "example",
    "watershed": "turning point",
    "nestled": "located",
    "vibrant": "lively",
    "thriving": "growing",
    "showcasing": "showing",
    "bustling": "busy",
    "ever-evolving": "changing",
    "enduring": "lasting",
    "daunting": "challenging",
    "actionable": "practical",
    "impactful": "important",
    "learnings": "lessons",
    "thought leader": "expert",
    "best practices": "proven methods",
    "commences": "begins",
    "ascertain": "find out",
    "endeavor": "try",
    "keen": "eager",
    "boasts": "has",
    "It\u2019s important to note that": "",
    "It's important to note that": "",
    "It is worth noting that": "",
    "It should be noted that": "",
    "It bears mentioning that": "",
    "This is a testament to": "This shows",
    "In today's rapidly evolving": "In today's",
    "In an era of": "With",
    "At its core": "",
    "When it comes to": "For",
    "In the realm of": "In",
    "In order to": "To",
    "Due to the fact that": "Because",
    "serves as a": "is a",
    "plays a crucial role": "matters",
    "is a testament to": "shows",
}

# ── Education whitelist: NEVER remove these in educational content ────

EDUCATION_WHITELIST: set[str] = {
    # Science vocabulary
    "catalyst", "optimize", "optimizes", "optimization",
    "synthesis", "synthesize", "integral", "integrate",
    "fundamental", "essential", "vital", "dynamic",
    "equilibrium", "momentum", "vector", "matrix",
    # Math vocabulary
    "function", "variable", "coefficient", "parameter",
    "significant", "derivative", "transformation",
    # Social studies / humanities
    "paradigm", "revolution", "reform", "progressive",
    "catalyst",  # e.g., "catalyst for change" in history
    "cornerstone",  # e.g., "cornerstone of democracy"
    # General academic vocabulary
    "analyze", "evaluate", "synthesize", "compare",
    "contrast", "distinguish", "identify", "examine",
}

# ── Tier 2: Flag when 2+ appear in same paragraph ───────────────────

TIER2_WORDS: set[str] = {
    "streamline", "streamlines", "streamlining",
    "bolster", "bolsters", "bolstering",
    "augment", "augments", "augmenting",
    "amplify", "amplifies", "amplifying",
    "linchpin",
    "underpinning", "bedrock", "hallmark",
    "epitome", "quintessential", "seminal",
    "groundbreaking", "trailblazing", "cutting-edge",
    "state-of-the-art", "best-in-class", "world-class",
    "game-changer", "transformative", "revolutionary",
    "seamless", "seamlessly", "effortless", "effortlessly",
    "meticulous", "meticulously", "intricate", "intricately",
}

# ── Tier 3: Flag at high density (>3 per 500 words) ─────────────────

TIER3_WORDS: set[str] = {
    "innovative", "dynamic", "strategic", "impactful",
    "significant", "substantial", "remarkable", "notable",
    "compelling", "engaging", "insightful", "thoughtful",
    "meaningful", "profound", "pivotal", "crucial",
    "essential", "fundamental", "integral", "vital",
    "ensure", "ensures", "ensuring",
    "empower", "empowers", "empowering",
    "enable", "enables", "enabling",
    "drive", "drives", "driving",
    "align", "aligns", "aligning",
}

# ── Structure patterns (AI formatting tells) ────────────────────────

_STRUCTURE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Colon-heavy headers: "Key Takeaway: The revolution..."
    (re.compile(r"^(#{1,3}\s+\w[\w\s]{2,20}):\s+", re.MULTILINE), r"\1 — "),
    # Em-dash lists (AI loves these)
    (re.compile(r"\s+—\s+(and|but|or|yet)\s+"), r" \1 "),
    # NOTE: Removed rhetorical question and "Let's" openers — they
    # deleted entire sentences when replaced with "". Word-level Tier 1
    # replacements are sufficient without these destructive patterns.
]


def humanize(text: str, aggressive: bool = False) -> str:
    """Remove AI-isms from text, preserving meaning.

    Args:
        text: The text to clean
        aggressive: If True, also apply Tier 2 replacements unconditionally

    Returns:
        Cleaned text with AI patterns replaced by natural alternatives
    """
    if not text:
        return text

    # Tier 1: Always replace
    for ai_phrase, human_phrase in TIER1_REPLACEMENTS.items():
        # Case-sensitive for capitalized phrases, case-insensitive for words
        if ai_phrase[0].isupper():
            text = text.replace(ai_phrase, human_phrase)
        else:
            text = re.sub(
                rf"\b{re.escape(ai_phrase)}\b",
                human_phrase,
                text,
                flags=re.IGNORECASE,
            )

    # Tier 2: Replace if clustered (2+ in same paragraph) or aggressive mode
    paragraphs = text.split("\n\n")
    cleaned_paragraphs = []
    for para in paragraphs:
        para_lower = para.lower()
        t2_count = sum(1 for w in TIER2_WORDS if w in para_lower)
        if t2_count >= 2 or aggressive:
            for word in TIER2_WORDS:
                # Skip words in education whitelist (real content, not filler)
                if word.lower() in EDUCATION_WHITELIST:
                    continue
                para = re.sub(
                    rf"\b{re.escape(word)}\b",
                    "",
                    para,
                    flags=re.IGNORECASE,
                )
            # Clean up double spaces from removals
            para = re.sub(r"  +", " ", para)
        cleaned_paragraphs.append(para)
    text = "\n\n".join(cleaned_paragraphs)

    # Tier 3: Replace at high density
    words = text.split()
    word_count = len(words)
    if word_count > 0:
        t3_count = sum(
            1 for w in words if w.lower().strip(".,!?;:") in TIER3_WORDS
        )
        density = t3_count / max(word_count / 500, 1)
        if density > 3:
            for word in TIER3_WORDS:
                # Skip words in education whitelist
                if word.lower() in EDUCATION_WHITELIST:
                    continue
                text = re.sub(
                    rf"\b{re.escape(word)}\b",
                    "",
                    text,
                    flags=re.IGNORECASE,
                )
            text = re.sub(r"  +", " ", text)

    # Structure patterns
    for pattern, replacement in _STRUCTURE_PATTERNS:
        text = pattern.sub(replacement, text)

    # Final cleanup
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"  +", " ", text)

    return text.strip()


def detect(text: str) -> list[dict[str, str]]:
    """Detect AI-isms without modifying text. Returns list of findings.

    Each finding: {"pattern": ..., "tier": "1"|"2"|"3", "context": ...}
    """
    findings: list[dict[str, str]] = []

    for ai_phrase in TIER1_REPLACEMENTS:
        if ai_phrase.lower() in text.lower():
            # Find surrounding context
            idx = text.lower().index(ai_phrase.lower())
            start = max(0, idx - 30)
            end = min(len(text), idx + len(ai_phrase) + 30)
            findings.append({
                "pattern": ai_phrase,
                "tier": "1",
                "context": text[start:end],
            })

    para_lower = text.lower()
    for word in TIER2_WORDS:
        if word in para_lower:
            findings.append({"pattern": word, "tier": "2", "context": ""})

    return findings
