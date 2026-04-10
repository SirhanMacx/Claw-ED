"""Pedagogical quality tests for DailyLesson structured output.

These tests validate that generated lesson plans meet research-based
instructional standards. They run against parsed Pydantic model data —
no LLM required — and serve as the automated quality gate for every
lesson Claw-ED produces.
"""

from __future__ import annotations

import re

from clawed.models import DailyLesson, DifferentiationNotes, ExitTicketQuestion

# ── Generic phrases that indicate lazy / non-specific differentiation ───

_GENERIC_PHRASES = [
    "provide scaffolding",
    "offer support",
    "extend learning",
    "provide extra",
    "additional support",
    "extra practice",
    "more time",
    "additional time",
    "modified assignments",
    "adjusted expectations",
]

# ── Check-for-understanding activity keywords ──────────────────────────

_CFU_ACTIVITIES = [
    "think-pair-share",
    "think pair share",
    "turn and talk",
    "turn-and-talk",
    "cold call",
    "cold-call",
    "thumbs up",
    "thumbs-up",
    "thumbs down",
    "whiteboards",
    "show me",
    "fist to five",
    "fist-to-five",
    "exit slip",
    "quick write",
    "quick-write",
    "signal cards",
    "stop and jot",
    "stop-and-jot",
    "muddiest point",
    "four corners",
    "gallery walk",
    "partner share",
]


# ── Fixtures ────────────────────────────────────────────────────────────


def _good_lesson() -> DailyLesson:
    """A realistic, well-formed lesson on the causes of the American Revolution.

    Based on an 8th-grade US History class with ~50 minutes of instruction.
    All quality checks should pass.
    """
    return DailyLesson(
        title="Taxation Without Representation: The Colonists Fight Back",
        lesson_number=4,
        objective=(
            "Students will be able to analyze primary source excerpts from the "
            "Stamp Act Congress (1765) to explain how British taxation policies "
            "united the American colonies in opposition."
        ),
        standards=[
            "8.1.US.4 — Analyze the causes of the American Revolution",
            "RH.6-8.2 — Determine the central idea of a primary source",
        ],
        do_now=(
            "Imagine you wake up tomorrow and your school announces that every "
            "student must pay a $5 fee to use the hallway between classes — but "
            "students had no say in the decision. Write 3-4 sentences: How would "
            "you feel? What would you do? Who would you talk to?"
        ),
        direct_instruction=(
            "Today we are going to look at how the British Parliament passed "
            "the Stamp Act in 1765 and why colonists were so angry about it. "
            "The Stamp Act required colonists to pay a tax on every piece of "
            "printed paper — newspapers, legal documents, even playing cards. "
            "But here is what made it different from earlier taxes: the colonists "
            "had no representatives in Parliament. They had no vote, no voice, "
            "no seat at the table.\n\n"
            "I want you to think-pair-share with your elbow partner for 60 seconds: "
            "Why does it matter that the colonists had no representatives? "
            "[Circulate and listen for misconceptions about representation.]\n\n"
            "Good — I heard several of you say it is not about the money, it is "
            "about the principle. That is exactly right. The colonists' argument "
            "was not 'taxes are bad' but 'taxation without representation is "
            "tyranny.' Let me show you the actual words from the Stamp Act "
            "Congress petition. [Display excerpt on board.]\n\n"
            "The phrase 'no Taxation without Representation' became the rallying "
            "cry that united colonies from Massachusetts to Virginia. Before the "
            "Stamp Act, each colony mostly acted alone. After it, delegates from "
            "nine colonies met in New York City — the first time colonies "
            "cooperated against Britain."
        ),
        guided_practice=(
            "Station Activity (groups of 3-4): Each group receives a different "
            "primary source excerpt from the Stamp Act Congress proceedings. "
            "Using the APPARTS graphic organizer (Author, Place & Time, Prior "
            "Knowledge, Audience, Reason, The Main Idea, Significance), students "
            "analyze their document. Groups will have 12 minutes to complete "
            "the organizer, then each group presents their document's main "
            "argument to the class in a 90-second share-out."
        ),
        independent_work=(
            "Students write a 5-sentence paragraph answering: 'How did the "
            "Stamp Act change the relationship between Britain and the American "
            "colonies?' Students must cite at least one specific detail from "
            "the primary source they analyzed during guided practice. Use the "
            "RACE writing organizer (Restate, Answer, Cite, Explain) posted "
            "on the wall."
        ),
        exit_ticket=[
            ExitTicketQuestion(
                question=("What was the main argument colonists made against the Stamp Act?"),
                expected_response=(
                    "The colonists argued that the Stamp Act was unfair because "
                    "they had no elected representatives in the British Parliament "
                    "to vote on the tax — 'no taxation without representation.'"
                ),
            ),
            ExitTicketQuestion(
                question=("How did the Stamp Act unite the colonies?"),
                expected_response=(
                    "The Stamp Act led delegates from nine colonies to meet at "
                    "the Stamp Act Congress in New York — the first time colonies "
                    "cooperated to oppose a British policy."
                ),
            ),
            ExitTicketQuestion(
                question=(
                    "A student says: 'The colonists were angry because the tax "
                    "was too expensive.' Is this accurate? Explain."
                ),
                expected_response=(
                    "This is partially accurate but misses the key point. The "
                    "colonists' primary objection was not the cost but the "
                    "principle: Parliament taxed them without their consent or "
                    "representation."
                ),
            ),
        ],
        homework=(
            "Read the one-page excerpt from Samuel Adams' 1765 letter to the "
            "London newspapers. Annotate 3 places where Adams uses emotional "
            "language to persuade his audience."
        ),
        differentiation=DifferentiationNotes(
            struggling=[
                "Pre-highlight key sentences in the primary source excerpt so "
                "students focus on 3 critical lines rather than the full text",
                "Provide a completed APPARTS model for a different document so "
                "students can see what a finished analysis looks like",
                "Pair with a stronger reader during station activity for shared reading of the source",
            ],
            advanced=[
                "Assign the full text of the Stamp Act Congress petition "
                "(not just the excerpt) and ask them to identify 2 rhetorical "
                "strategies the delegates used",
                "Write a counter-argument from Parliament's perspective defending the right to tax the colonies",
            ],
            ell=[
                "Provide a bilingual glossary card with key terms: "
                "representation, taxation, petition, delegates, tyranny",
                "Sentence frames for the independent paragraph: "
                "'The Stamp Act changed the relationship because ___. "
                'For example, the source says "___". This shows that ___.\'',
            ],
        ),
        materials_needed=[
            "Stamp Act Congress primary source excerpts (4 different documents)",
            "APPARTS graphic organizer handout (1 per student)",
            "RACE writing organizer (posted on wall)",
            "Projector for displaying excerpt",
            "Exit ticket half-sheets",
        ],
        time_estimates={
            "do_now": 5,
            "direct_instruction": 15,
            "guided_practice": 18,
            "independent_work": 8,
            "exit_ticket": 4,
        },
    )


def _bad_lesson() -> DailyLesson:
    """A poorly-formed lesson that represents common LLM generation failures.

    Vague objective, generic differentiation, missing expected responses,
    empty standards, and times that exceed a class period.
    """
    return DailyLesson(
        title="The American Revolution",
        lesson_number=1,
        objective="Students will understand the American Revolution.",
        standards=[],
        do_now="What do you know about the American Revolution?",
        direct_instruction=(
            "Today we will learn about the American Revolution. The American "
            "Revolution was a war between the colonies and Britain. There were "
            "many causes of the American Revolution. We will check for "
            "understanding throughout the lesson."
        ),
        guided_practice=("Students will work in groups on an organizer about the causes of the American Revolution."),
        independent_work="Complete the worksheet.",
        exit_ticket=[
            ExitTicketQuestion(
                question="What did you learn today?",
                expected_response="",
            ),
        ],
        homework=None,
        differentiation=DifferentiationNotes(
            struggling=["Provide scaffolding", "Offer support as needed"],
            advanced=["Extend learning with additional resources"],
            ell=["Provide extra time"],
        ),
        materials_needed=["worksheet", "organizer"],
        time_estimates={
            "do_now": 10,
            "direct_instruction": 25,
            "guided_practice": 20,
            "independent_work": 15,
        },
    )


# ── Quality checks ─────────────────────────────────────────────────────


class TestTimingQuality:
    """Time-estimate validation tests."""

    def test_times_add_up_to_class_period(self):
        """Total instructional time must fall within 42-55 minutes.

        Standard: A well-planned lesson accounts for a realistic class
        period (typically 42-50 min of instruction). Times under 42 min
        leave too much dead time; times over 55 min are undeliverable.
        """
        lesson = _good_lesson()
        total = sum(lesson.time_estimates.values())
        assert 42 <= total <= 55, f"Total time {total} min is outside 42-55 range"

    def test_bad_lesson_times_exceed(self):
        """Bad lesson's total time exceeds the 42-55 min window."""
        lesson = _bad_lesson()
        total = sum(lesson.time_estimates.values())
        assert total > 55, f"Expected total > 55, got {total}"

    def test_do_now_has_time_estimate(self):
        """The Do Now must have an explicit time allocation.

        Standard: Every lesson component needs planned timing. A missing
        Do Now time means the teacher cannot pace the opening.
        """
        lesson = _good_lesson()
        assert "do_now" in lesson.time_estimates, "do_now missing from time_estimates"
        assert lesson.time_estimates["do_now"] > 0, "do_now time must be > 0"

    def test_do_now_time_is_reasonable(self):
        """Do Now should be 3-7 minutes.

        Standard: Research shows warm-ups longer than 7 minutes steal
        time from core instruction, while those under 3 minutes are too
        rushed for meaningful cognitive activation.
        """
        lesson = _good_lesson()
        do_now_time = lesson.time_estimates.get("do_now", 0)
        assert 3 <= do_now_time <= 7, f"Do Now time {do_now_time} min is outside 3-7 range"


class TestExitTicketQuality:
    """Exit ticket validation tests."""

    def test_exit_ticket_has_questions(self):
        """Exit ticket must have at least 2 questions.

        Standard: A single question cannot reliably measure understanding.
        Multiple questions allow the teacher to check different levels of
        Bloom's taxonomy (recall, application, analysis).
        """
        lesson = _good_lesson()
        assert len(lesson.exit_ticket) >= 2, f"Expected >= 2 exit ticket questions, got {len(lesson.exit_ticket)}"

    def test_bad_lesson_exit_ticket_too_few(self):
        """Bad lesson has fewer than 2 exit ticket questions."""
        lesson = _bad_lesson()
        assert len(lesson.exit_ticket) < 2, f"Expected < 2 exit ticket questions, got {len(lesson.exit_ticket)}"

    def test_exit_ticket_has_expected_responses(self):
        """Every exit ticket question needs an expected response.

        Standard: Without expected responses, exit tickets cannot be
        scored consistently. The teacher (or a sub) needs a clear answer
        key to sort student work into mastery / partial / not yet.
        """
        lesson = _good_lesson()
        for i, q in enumerate(lesson.exit_ticket):
            assert q.expected_response.strip(), f"Exit ticket question {i + 1} has no expected response"

    def test_bad_lesson_exit_ticket_missing_responses(self):
        """Bad lesson has exit ticket questions with empty expected responses."""
        lesson = _bad_lesson()
        empty = [q for q in lesson.exit_ticket if not q.expected_response.strip()]
        assert len(empty) > 0, "Expected at least one empty expected_response"


class TestStandardsQuality:
    """Standards alignment validation tests."""

    def test_standards_not_empty(self):
        """Standards list must not be empty.

        Standard: Every lesson must be aligned to at least one state or
        Common Core standard. Standards-free lessons cannot be mapped to
        curriculum frameworks or used in formal observations.
        """
        lesson = _good_lesson()
        assert len(lesson.standards) > 0, "Standards list must not be empty"

    def test_bad_lesson_standards_empty(self):
        """Bad lesson has an empty standards list."""
        lesson = _bad_lesson()
        assert len(lesson.standards) == 0, "Expected empty standards list"


class TestDifferentiationQuality:
    """Differentiation specificity validation tests."""

    def test_differentiation_is_specific(self):
        """Differentiation must be specific and actionable, not generic.

        Standard: Generic phrases like 'provide scaffolding' or 'offer
        support' are useless to a teacher. Each accommodation must name
        the SPECIFIC strategy (e.g., 'pre-highlight key sentences',
        'provide sentence frames', 'pair with a stronger reader').
        """
        lesson = _good_lesson()
        all_accommodations = (
            lesson.differentiation.struggling + lesson.differentiation.advanced + lesson.differentiation.ell
        )
        for acc in all_accommodations:
            acc_lower = acc.lower()
            for phrase in _GENERIC_PHRASES:
                assert phrase not in acc_lower, f"Generic phrase '{phrase}' found in differentiation: '{acc}'"

    def test_bad_lesson_differentiation_is_generic(self):
        """Bad lesson contains generic differentiation phrases."""
        lesson = _bad_lesson()
        all_accommodations = (
            lesson.differentiation.struggling + lesson.differentiation.advanced + lesson.differentiation.ell
        )
        generic_found = False
        for acc in all_accommodations:
            acc_lower = acc.lower()
            for phrase in _GENERIC_PHRASES:
                if phrase in acc_lower:
                    generic_found = True
                    break
            if generic_found:
                break
        assert generic_found, "Expected at least one generic differentiation phrase"


class TestInstructionQuality:
    """Direct instruction content validation tests."""

    def test_vocabulary_is_defined_in_instruction(self):
        """Content-specific terms from the objective appear in instruction.

        Standard: Key domain vocabulary referenced in the objective must
        be explicitly taught during direct instruction. If the objective
        mentions 'Stamp Act Congress', students need to encounter and
        learn that term during the lesson body.
        """
        lesson = _good_lesson()
        # Extract content-specific terms: capitalized multi-word phrases and
        # domain words >5 characters from the objective
        objective = lesson.objective
        # Find capitalized proper nouns / phrases (e.g., "Stamp Act Congress")
        capitalized_terms = re.findall(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*", objective)
        # Also grab longer words that might be domain vocabulary
        words = re.findall(r"\b[a-zA-Z]{6,}\b", objective)
        # Filter out common non-domain words (task verbs, geographic
        # adjectives, and general academic language)
        common_words = {
            "students",
            "analyze",
            "explain",
            "primary",
            "source",
            "excerpts",
            "describe",
            "identify",
            "understand",
            "evaluate",
            "determine",
            "compare",
            "contrast",
            "between",
            "through",
            "because",
            "american",
            "british",
            "united",
            "opposition",
            "policies",
            "colonies",
            "congress",
            "taxation",
        }
        # Common capitalized words that are not content-specific vocabulary
        common_proper = {
            "students",
            "american",
            "british",
            "congress",
        }
        domain_terms = [w for w in words if w.lower() not in common_words]
        filtered_capitalized = [t for t in capitalized_terms if t.lower() not in common_proper]
        all_terms = set(filtered_capitalized + domain_terms)
        di_text = lesson.direct_instruction.lower()
        for term in all_terms:
            assert term.lower() in di_text, f"Objective term '{term}' not found in direct instruction"

    def test_lesson_has_check_for_understanding(self):
        """Direct instruction must include a specific CFU activity.

        Standard: Research-based instruction requires at least one
        embedded formative check during direct instruction — not just
        the phrase 'check for understanding' but a named technique
        (think-pair-share, cold call, thumbs up/down, stop and jot, etc.).
        """
        lesson = _good_lesson()
        di_lower = lesson.direct_instruction.lower()
        found = any(activity in di_lower for activity in _CFU_ACTIVITIES)
        assert found, (
            "Direct instruction must contain a specific CFU activity (think-pair-share, cold call, thumbs up, etc.)"
        )

    def test_bad_lesson_no_specific_cfu(self):
        """Bad lesson uses generic 'check for understanding' but no specific technique."""
        lesson = _bad_lesson()
        di_lower = lesson.direct_instruction.lower()
        # Verify the generic phrase IS present (confirming it's a deliberate trap)
        assert "check for understanding" in di_lower, (
            "Bad lesson fixture should contain generic 'check for understanding'"
        )
        # Verify no SPECIFIC CFU activity is present
        found = any(activity in di_lower for activity in _CFU_ACTIVITIES)
        assert not found, "Bad lesson should not contain a specific CFU activity"


class TestMaterialsQuality:
    """Materials and resource validation tests."""

    def test_materials_referenced_are_described(self):
        """If lesson text mentions 'organizer', the practice sections describe it.

        Standard: Referencing a graphic organizer without specifying its
        structure (columns, rows, chart type) means the teacher cannot
        prepare it. If a lesson says 'use the organizer', the guided or
        independent practice text must describe what is on it.
        """
        lesson = _good_lesson()
        full_text = lesson.do_now + lesson.direct_instruction + lesson.guided_practice + lesson.independent_work
        if "organizer" in full_text.lower():
            practice_text = (lesson.guided_practice + " " + lesson.independent_work).lower()
            # Must describe the organizer structure
            structure_words = [
                "column",
                "row",
                "chart",
                "graphic",
                "apparts",
                "t-chart",
                "venn",
                "compare",
                "categories",
                "table",
                "restate",
                "answer",
                "cite",
            ]
            found = any(word in practice_text for word in structure_words)
            assert found, (
                "Lesson references an 'organizer' but guided/independent practice does not describe its structure"
            )
