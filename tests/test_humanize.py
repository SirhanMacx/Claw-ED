"""Tests for clawed.humanize — AI-ism detection and removal."""

from clawed.humanize import detect, humanize

# ── Tier 1 replacements ───────────────────────────────────────────────


class TestTier1Replacements:
    """Tier 1 words are always replaced regardless of context."""

    def test_delve_replaced_with_explore(self):
        text = "Let's delve into the causes of the Civil War."
        result = humanize(text)
        assert "delve" not in result.lower()
        assert "explore" in result.lower()

    def test_utilize_replaced_with_use(self):
        text = "Students will utilize primary sources to build understanding."
        result = humanize(text)
        assert "utilize" not in result.lower()
        assert "use" in result.lower()

    def test_leverage_replaced_with_use(self):
        text = "We can leverage these tools to enhance learning."
        result = humanize(text)
        assert "leverage" not in result.lower()
        assert "use" in result.lower()

    def test_facilitate_replaced_with_help(self):
        text = "This activity will facilitate deeper understanding."
        result = humanize(text)
        assert "facilitate" not in result.lower()
        assert "help" in result.lower()

    def test_moreover_replaced_with_also(self):
        text = "Moreover, the Renaissance changed European culture."
        result = humanize(text)
        assert "Moreover" not in result
        assert "Also" in result

    def test_phrase_replacement_its_important_to_note(self):
        text = "It's important to note that the treaty was signed in 1648."
        result = humanize(text)
        assert "important to note" not in result.lower()

    def test_multiple_tier1_words_all_replaced(self):
        text = (
            "Let's delve into how to utilize these resources and leverage "
            "our understanding. Moreover, we should facilitate discussion."
        )
        result = humanize(text)
        assert "delve" not in result.lower()
        assert "utilize" not in result.lower()
        assert "leverage" not in result.lower()
        assert "Moreover" not in result
        assert "facilitate" not in result.lower()

    def test_case_insensitive_word_replacement(self):
        text = "The DELVE into history was important."
        result = humanize(text)
        assert "delve" not in result.lower()


# ── Education whitelist ───────────────────────────────────────────────


class TestEducationWhitelist:
    """Education-specific terms must NOT be removed even if they appear in tier lists."""

    def test_catalyst_preserved_in_chemistry(self):
        text = "A catalyst speeds up a chemical reaction without being consumed."
        result = humanize(text)
        assert "catalyst" in result.lower()

    def test_equilibrium_preserved_in_science(self):
        text = "The system reaches equilibrium when forces are balanced."
        result = humanize(text)
        assert "equilibrium" in result.lower()

    def test_function_preserved_in_math(self):
        text = "A function maps inputs to outputs."
        result = humanize(text)
        assert "function" in result.lower()

    def test_derivative_preserved_in_calculus(self):
        text = "The derivative tells us the rate of change."
        result = humanize(text)
        assert "derivative" in result.lower()

    def test_synthesis_preserved_in_science(self):
        text = "Protein synthesis occurs in the ribosome."
        result = humanize(text)
        assert "synthesis" in result.lower()


# ── Tier 2 cluster detection ─────────────────────────────────────────


class TestTier2ClusterDetection:
    """Tier 2 words are only removed when 2+ appear in the same paragraph."""

    def test_single_tier2_word_kept(self):
        text = "This was a groundbreaking discovery."
        result = humanize(text)
        # Single T2 word should be kept (not clustered)
        assert "groundbreaking" in result.lower()

    def test_two_tier2_words_triggers_removal(self):
        text = "This was a groundbreaking and seamless transformation of the field."
        result = humanize(text)
        # With 2+ T2 words in same paragraph, they should be cleaned
        # (removed or reduced, but paragraph should still be coherent)
        t2_count = sum(1 for w in ["groundbreaking", "seamless"] if w in result.lower())
        assert t2_count < 2

    def test_tier2_across_paragraphs_not_clustered(self):
        text = "This was groundbreaking.\n\nThat was seamless."
        result = humanize(text)
        # Separate paragraphs should not cluster
        assert "groundbreaking" in result.lower() or "seamless" in result.lower()


# ── Sentence preservation ─────────────────────────────────────────────


class TestNoSentenceDestruction:
    """Replacements must not destroy sentence structure or create gibberish."""

    def test_sentence_remains_readable(self):
        text = "We will delve into the subject and utilize primary sources."
        result = humanize(text)
        # Sentence should still be grammatically coherent
        assert "explore" in result.lower()
        assert "use" in result.lower()
        # Should not have orphaned punctuation or broken structure
        assert "  " not in result or result == humanize(result)

    def test_paragraph_structure_preserved(self):
        text = "First paragraph about history.\n\nSecond paragraph about science.\n\nThird paragraph about art."
        result = humanize(text)
        paragraphs = [p for p in result.split("\n\n") if p.strip()]
        assert len(paragraphs) == 3

    def test_no_triple_newlines_in_output(self):
        text = "Moreover, this is important.\n\n\n\nFurthermore, consider this."
        result = humanize(text)
        assert "\n\n\n" not in result

    def test_no_double_spaces_in_output(self):
        text = "We should utilize  and leverage these tools."
        result = humanize(text)
        assert "  " not in result


# ── Edge cases ────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases: empty input, special characters, etc."""

    def test_empty_input_returns_empty(self):
        assert humanize("") == ""

    def test_none_like_empty_returns_empty(self):
        # The function checks `if not text: return text`
        assert humanize("") == ""

    def test_plain_text_without_ai_isms_unchanged(self):
        text = "The sun rises in the east and sets in the west."
        result = humanize(text)
        assert result == text

    def test_curly_apostrophe_handled(self):
        """Curly apostrophe variant of phrases should also be caught."""
        text = "It\u2019s important to note that the war began in 1914."
        result = humanize(text)
        assert "important to note" not in result.lower()

    def test_straight_apostrophe_handled(self):
        text = "It's important to note that the war began in 1914."
        result = humanize(text)
        assert "important to note" not in result.lower()


# ── detect() function ─────────────────────────────────────────────────


class TestDetect:
    """detect() identifies AI-isms without modifying text."""

    def test_detects_tier1_words(self):
        text = "Let's delve into the topic and utilize resources."
        findings = detect(text)
        patterns = [f["pattern"] for f in findings]
        assert "delve" in patterns or "utilize" in patterns

    def test_returns_tier_info(self):
        text = "We should delve into this topic."
        findings = detect(text)
        tier1_findings = [f for f in findings if f["tier"] == "1"]
        assert len(tier1_findings) > 0

    def test_clean_text_returns_empty(self):
        text = "The earth orbits the sun."
        findings = detect(text)
        assert len(findings) == 0
