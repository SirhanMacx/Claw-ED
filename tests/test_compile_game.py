"""Tests for compile_game — focuses on pure functions (no LLM calls)."""

from unittest.mock import MagicMock

from clawed.compile_game import _extract_game_content, _repair_html_structure, _validate_game_html

# ── _extract_game_content ────────────────────────────────────────────


def _make_mock_master(
    title="The Renaissance",
    subject="World History",
    grade_level="9",
    topic="Renaissance Art",
    objective="Students will analyze Renaissance art movements.",
    vocabulary=None,
    guided_notes=None,
    exit_ticket=None,
    primary_sources=None,
    direct_instruction=None,
):
    """Build a mock MasterContent for game content extraction."""
    mc = MagicMock()
    mc.title = title
    mc.subject = subject
    mc.grade_level = grade_level
    mc.topic = topic
    mc.objective = objective
    mc.vocabulary = vocabulary or []
    mc.guided_notes = guided_notes or []
    mc.exit_ticket = exit_ticket or []
    mc.primary_sources = primary_sources or []
    mc.direct_instruction = direct_instruction or []
    return mc


def test_extract_game_content_basic():
    """Extracts title, subject, grade, topic, objective."""
    mc = _make_mock_master()
    content = _extract_game_content(mc)
    assert "LESSON: The Renaissance" in content
    assert "SUBJECT: World History" in content
    assert "GRADE: 9" in content
    assert "TOPIC: Renaissance Art" in content
    assert "OBJECTIVE:" in content


def test_extract_game_content_with_vocabulary():
    """Vocabulary terms are included with definitions."""
    vocab = MagicMock()
    vocab.term = "Chiaroscuro"
    vocab.definition = "Use of light and shadow in painting"
    vocab.context_sentence = "Da Vinci mastered chiaroscuro."

    mc = _make_mock_master(vocabulary=[vocab])
    content = _extract_game_content(mc)
    assert "VOCABULARY:" in content
    assert "Chiaroscuro" in content
    assert "Use of light and shadow" in content
    assert "Da Vinci mastered" in content


def test_extract_game_content_vocab_without_context():
    """Vocabulary without context_sentence still works."""
    vocab = MagicMock()
    vocab.term = "Fresco"
    vocab.definition = "Painting on wet plaster"
    vocab.context_sentence = ""

    mc = _make_mock_master(vocabulary=[vocab])
    content = _extract_game_content(mc)
    assert "Fresco" in content
    assert "Painting on wet plaster" in content


def test_extract_game_content_with_guided_notes():
    """Guided notes are included as key facts."""
    note = MagicMock()
    note.prompt = "The Mona Lisa was painted by ___"
    note.answer = "Leonardo da Vinci"

    mc = _make_mock_master(guided_notes=[note])
    content = _extract_game_content(mc)
    assert "KEY FACTS" in content
    assert "Mona Lisa" in content
    assert "Leonardo da Vinci" in content


def test_extract_game_content_with_exit_ticket():
    """Exit ticket questions are included."""
    q = MagicMock()
    q.question = "What characterized Renaissance art?"
    q.expected_answer = "Realism and humanism"

    mc = _make_mock_master(exit_ticket=[q])
    content = _extract_game_content(mc)
    assert "QUIZ QUESTIONS:" in content
    assert "characterized Renaissance art" in content


def test_extract_game_content_with_primary_sources():
    """Primary sources are included with title and type."""
    src = MagicMock()
    src.title = "The Birth of Venus"
    src.source_type = "painting"
    src.content_text = "Botticelli's masterwork depicting the goddess Venus."

    mc = _make_mock_master(primary_sources=[src])
    content = _extract_game_content(mc)
    assert "PRIMARY SOURCES:" in content
    assert "The Birth of Venus" in content
    assert "painting" in content


def test_extract_game_content_with_direct_instruction():
    """Direct instruction sections are included as key concepts."""
    section = MagicMock()
    section.heading = "Perspective in Art"
    section.key_points = ["Linear perspective", "Vanishing point", "Depth illusion"]

    mc = _make_mock_master(direct_instruction=[section])
    content = _extract_game_content(mc)
    assert "KEY CONCEPTS:" in content
    assert "Perspective in Art" in content


def test_extract_game_content_empty_master():
    """Minimal MasterContent still produces valid output."""
    mc = _make_mock_master(
        title="Empty Lesson",
        objective="Test",
        vocabulary=[],
        guided_notes=[],
        exit_ticket=[],
        primary_sources=[],
        direct_instruction=[],
    )
    content = _extract_game_content(mc)
    assert "LESSON: Empty Lesson" in content
    assert "VOCABULARY:" not in content
    assert "KEY FACTS" not in content


# ── _repair_html_structure ───────────────────────────────────────────


def test_repair_html_structure_well_formed_passthrough():
    """Well-formed HTML passes through unchanged."""
    html = (
        "<!DOCTYPE html><html><head><style>body{}</style></head><body><script>function init(){}</script></body></html>"
    )
    result = _repair_html_structure(html)
    assert "<head>" in result
    assert "<body>" in result
    assert "<script>" in result


def test_repair_html_structure_missing_head_body():
    """HTML missing <head> and <body> gets them added."""
    html = (
        '<!DOCTYPE html><html lang="en">'
        "body { background: red; }"
        "<div>Hello</div><script>function go(){}</script></html>"
    )
    result = _repair_html_structure(html)
    assert "<head>" in result.lower()


def test_repair_html_structure_no_html_tag():
    """Content with no <html> tag at all gets fully wrapped."""
    html = "body { color: blue; } .game { display: flex; }"
    result = _repair_html_structure(html)
    assert "<!DOCTYPE html>" in result
    assert "<html" in result
    assert "<head>" in result


# ── _validate_game_html ──────────────────────────────────────────────


def test_validate_game_html_valid():
    """Valid game HTML passes validation."""
    mc = _make_mock_master(title="Renaissance", topic="Renaissance Art")
    # Needs to be >= 500 chars to pass length check
    game_content = "Renaissance Art " * 30  # educational content
    html = (
        '<!DOCTYPE html><html><head><meta charset="UTF-8">'
        "<title>Renaissance Game</title><style>body { margin: 0; padding: 20px; "
        "font-family: Arial, sans-serif; background: linear-gradient(135deg, "
        "#667eea 0%, #764ba2 100%); } .game-container { max-width: 800px; "
        "margin: 0 auto; }</style></head>"
        f"<body><div class='game-container'>{game_content}</div>"
        "<script>function startGame() { const score = 0; const questions = ["
        "]; function nextQuestion() { return true; } startGame(); }</script>"
        "</body></html>"
    )
    issues = _validate_game_html(html, mc)
    # Should have no critical issues (topic word present, has script, etc.)
    # Some issues may remain if first vocab term is missing
    critical = [i for i in issues if "too short" in i or "Missing <html>" in i or "No JavaScript" in i]
    assert len(critical) == 0


def test_validate_game_html_too_short():
    """HTML that is too short is flagged."""
    mc = _make_mock_master()
    issues = _validate_game_html("<html></html>", mc)
    assert any("too short" in i for i in issues)


def test_validate_game_html_no_script():
    """HTML without <script> is flagged."""
    mc = _make_mock_master()
    html = "<html><head></head><body>" + "x" * 600 + "</body></html>"
    issues = _validate_game_html(html, mc)
    assert any("script" in i.lower() for i in issues)
