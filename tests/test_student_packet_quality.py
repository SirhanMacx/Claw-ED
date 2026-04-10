"""Pedagogical quality tests for StudentPacket structured output.

These tests validate that the student-facing packet — the document
students actually work through in class — meets basic completeness and
quality standards. They run against parsed Pydantic model data with no
LLM required.
"""

from __future__ import annotations

from clawed.models import (
    GraphicOrganizerSpec,
    GuidedNotesBlank,
    PrimarySourceDocument,
    StudentPacket,
    VocabularyTerm,
)

# ── Fixtures ────────────────────────────────────────────────────────────


def _good_packet() -> StudentPacket:
    """A realistic, well-formed student packet on the causes of the Civil War.

    All quality checks should pass.
    """
    return StudentPacket(
        title="Causes of the Civil War — Student Packet",
        aim=("How did the debate over slavery lead to the outbreak of the Civil War?"),
        do_now_prompt=(
            "Imagine two neighbors share a fence. One neighbor wants to "
            "build a tall wall; the other wants to tear the fence down. "
            "Neither can do it without the other's agreement. Write 3-4 "
            "sentences describing what might happen if they cannot "
            "compromise. How does this connect to what we have been "
            "studying about the North and South?"
        ),
        do_now_response_lines=5,
        vocabulary=[
            VocabularyTerm(
                term="Sectionalism",
                definition=("Loyalty to one's own region (North or South) over the nation as a whole."),
            ),
            VocabularyTerm(
                term="Abolitionist",
                definition=(
                    "A person who demanded the immediate end of slavery, "
                    "such as Frederick Douglass or William Lloyd Garrison."
                ),
            ),
            VocabularyTerm(
                term="Compromise",
                definition=(
                    "An agreement where each side gives up something it "
                    "wants in order to reach a solution both can accept."
                ),
            ),
        ],
        guided_notes=[
            GuidedNotesBlank(
                sentence_with_blank=(
                    "The Missouri Compromise of 1820 drew an imaginary line "
                    "at the ______ parallel, dividing free states from slave "
                    "states."
                ),
                answer="36°30'",
            ),
            GuidedNotesBlank(
                sentence_with_blank=(
                    "The ______ Act of 1854 allowed settlers in Kansas and "
                    "Nebraska to vote on whether to permit slavery, leading "
                    "to violent conflict."
                ),
                answer="Kansas-Nebraska",
            ),
            GuidedNotesBlank(
                sentence_with_blank=(
                    "In the Dred Scott decision of 1857, the Supreme Court "
                    "ruled that enslaved people were not ______ and had no "
                    "right to sue in federal court."
                ),
                answer="citizens",
            ),
        ],
        stations=[
            PrimarySourceDocument(
                document_label="Station A",
                title="Frederick Douglass, 'What to the Slave is the Fourth of July?' (1852)",
                author="Frederick Douglass",
                date="July 5, 1852",
                context=(
                    "Douglass was invited to give a Fourth of July speech "
                    "to the Rochester Ladies' Anti-Slavery Society."
                ),
                full_text=(
                    "What, to the American slave, is your Fourth of July? "
                    "I answer: a day that reveals to him, more than all other "
                    "days in the year, the gross injustice and cruelty to "
                    "which he is the constant victim. To him, your celebration "
                    "is a sham; your boasted liberty, an unholy license; your "
                    "national greatness, swelling vanity."
                ),
                analysis_questions=[
                    "What is Douglass's main argument in this excerpt?",
                    "What tone does Douglass use? Cite a specific word or phrase.",
                    "Why might Douglass have chosen the Fourth of July to deliver this message?",
                ],
            ),
            PrimarySourceDocument(
                document_label="Station B",
                title="John C. Calhoun, Speech to the US Senate (1850)",
                author="John C. Calhoun",
                date="March 4, 1850",
                context=(
                    "Calhoun, a South Carolina senator, argued against northern restrictions on slavery's expansion."
                ),
                full_text=(
                    "The South asks for justice, simple justice, and less she "
                    "ought not to take. She has no compromise to offer but the "
                    "Constitution; and no concession or surrender to make. "
                    "How can the Union be saved? There is but one way by which "
                    "it can — and that is by adopting such measures as will "
                    "satisfy the South that she can remain in the Union "
                    "consistently with her honor and her safety."
                ),
                analysis_questions=[
                    "What does Calhoun mean by 'simple justice' for the South?",
                    "According to Calhoun, whose responsibility is it to save the Union?",
                    "How does Calhoun's view of the Constitution differ from Douglass's?",
                ],
            ),
        ],
        graphic_organizer=GraphicOrganizerSpec(
            title="North vs. South: Causes of Conflict",
            instructions=(
                "For each issue, write the Northern position in the left "
                "column and the Southern position in the right column. "
                "Use evidence from the station documents."
            ),
            columns=["Issue", "Northern Position", "Southern Position", "Key Evidence"],
            num_rows=4,
        ),
        exit_ticket_questions=[
            "Name two events that increased tension between the North and South before 1861.",
            (
                "In your own words, explain why compromise kept failing. "
                "Use at least one piece of evidence from today's documents."
            ),
            (
                "A student says: 'The Civil War was only about slavery.' "
                "Do you agree or disagree? Support your answer with a "
                "specific detail from today's lesson."
            ),
        ],
        sentence_starters=[
            "One cause of tension between the North and South was ___.",
            "The document shows that ___ because ___.",
            "I agree / disagree with this statement because ___.",
        ],
    )


def _bad_packet() -> StudentPacket:
    """A poorly-formed student packet representing common LLM failures.

    Short Do Now, missing vocabulary, too few exit ticket questions,
    lazy station text, and no graphic organizer.
    """
    return StudentPacket(
        title="Civil War Packet",
        aim="Learn about the Civil War.",
        do_now_prompt="Short q.",
        do_now_response_lines=2,
        vocabulary=[
            VocabularyTerm(term="War", definition="A conflict."),
        ],
        guided_notes=[
            GuidedNotesBlank(
                sentence_with_blank="The Civil War started in ______.",
                answer="1861",
            ),
        ],
        stations=[
            PrimarySourceDocument(
                document_label="Station 1",
                title="Document",
                full_text="See textbook page 145.",
                analysis_questions=["What happened?"],
            ),
            PrimarySourceDocument(
                document_label="Station 2",
                title="Another Document",
                full_text="See page 200 for details.",
                analysis_questions=["Why?"],
            ),
        ],
        graphic_organizer=GraphicOrganizerSpec(
            title="Organizer",
            instructions="Fill in.",
            columns=["Topic"],
            num_rows=2,
        ),
        exit_ticket_questions=[
            "What did you learn today?",
        ],
        sentence_starters=[],
    )


# ── Quality checks ─────────────────────────────────────────────────────


class TestDoNowQuality:
    """Do Now prompt validation tests."""

    def test_packet_has_do_now(self):
        """Do Now prompt must be non-empty and longer than 10 characters.

        Standard: The Do Now is the cognitive warm-up that activates
        prior knowledge or previews the lesson concept. A prompt shorter
        than 10 characters cannot pose a meaningful task.
        """
        packet = _good_packet()
        assert packet.do_now_prompt.strip(), "do_now_prompt must not be empty"
        assert len(packet.do_now_prompt) > 10, f"do_now_prompt is only {len(packet.do_now_prompt)} chars — must be > 10"

    def test_bad_packet_do_now_too_short(self):
        """Bad packet has a Do Now prompt that is too short (<= 10 chars)."""
        packet = _bad_packet()
        assert len(packet.do_now_prompt) <= 10, f"Expected do_now_prompt <= 10 chars, got {len(packet.do_now_prompt)}"


class TestVocabularyQuality:
    """Vocabulary completeness tests."""

    def test_packet_has_vocabulary(self):
        """Student packet must include at least 2 vocabulary terms.

        Standard: Content-area literacy requires explicit vocabulary
        instruction. Fewer than 2 terms suggests the packet skipped
        vocabulary or the lesson lacked domain-specific language.
        """
        packet = _good_packet()
        assert len(packet.vocabulary) >= 2, f"Expected >= 2 vocabulary terms, got {len(packet.vocabulary)}"

    def test_bad_packet_vocabulary_too_few(self):
        """Bad packet has fewer than 2 vocabulary terms."""
        packet = _bad_packet()
        assert len(packet.vocabulary) < 2, f"Expected < 2 vocabulary terms, got {len(packet.vocabulary)}"


class TestExitTicketQuality:
    """Exit ticket completeness tests."""

    def test_exit_ticket_has_multiple_questions(self):
        """Student packet must have at least 2 exit ticket questions.

        Standard: A single question cannot measure understanding across
        multiple cognitive levels. Two or more questions allow the
        teacher to check recall AND application or analysis.
        """
        packet = _good_packet()
        assert len(packet.exit_ticket_questions) >= 2, (
            f"Expected >= 2 exit ticket questions, got {len(packet.exit_ticket_questions)}"
        )

    def test_bad_packet_exit_ticket_too_few(self):
        """Bad packet has fewer than 2 exit ticket questions."""
        packet = _bad_packet()
        assert len(packet.exit_ticket_questions) < 2, (
            f"Expected < 2 exit ticket questions, got {len(packet.exit_ticket_questions)}"
        )


class TestSourceQuality:
    """Primary source station validation tests."""

    def test_source_excerpts_are_substantive(self):
        """Station full_text must be >30 chars and not a textbook reference.

        Standard: A primary source station requires actual source text
        for students to analyze. Directions like 'see textbook' or
        'see page' defeat the purpose — the student packet must be
        self-contained so students can work without finding another book.
        """
        packet = _good_packet()
        for station in packet.stations:
            text = station.full_text.strip()
            assert len(text) > 30, (
                f"Station '{station.document_label}' full_text is only {len(text)} chars — must be > 30"
            )
            text_lower = text.lower()
            assert "see textbook" not in text_lower, (
                f"Station '{station.document_label}' says 'see textbook' — must include actual source text"
            )
            assert "see page" not in text_lower, (
                f"Station '{station.document_label}' says 'see page' — must include actual source text"
            )

    def test_bad_packet_sources_are_lazy(self):
        """Bad packet has station text that is a textbook reference."""
        packet = _bad_packet()
        lazy_found = False
        for station in packet.stations:
            text_lower = station.full_text.lower()
            if "see textbook" in text_lower or "see page" in text_lower:
                lazy_found = True
                break
        assert lazy_found, "Expected at least one station with 'see textbook' or 'see page'"


class TestGraphicOrganizerQuality:
    """Graphic organizer validation tests."""

    def test_graphic_organizer_has_columns(self):
        """Graphic organizer must have at least 2 columns.

        Standard: A single-column organizer is just a list. A useful
        graphic organizer requires at least 2 columns to show
        relationships, comparisons, or categorization.
        """
        packet = _good_packet()
        assert packet.graphic_organizer is not None, "Graphic organizer must be present"
        assert len(packet.graphic_organizer.columns) >= 2, (
            f"Expected >= 2 columns, got {len(packet.graphic_organizer.columns)}"
        )

    def test_bad_packet_organizer_too_few_columns(self):
        """Bad packet's graphic organizer has fewer than 2 columns."""
        packet = _bad_packet()
        assert packet.graphic_organizer is not None, (
            "Bad packet fixture should have a graphic organizer with too few columns"
        )
        assert len(packet.graphic_organizer.columns) < 2, (
            f"Expected < 2 columns, got {len(packet.graphic_organizer.columns)}"
        )
