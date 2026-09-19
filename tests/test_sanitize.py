from clawed.sanitize import sanitize_text


def test_preserves_multilingual_quotes():
    text = "Read this source: 学生阅读资料 and explain it."
    assert sanitize_text(text) == text


def test_preserves_clean_english():
    text = "The 19th Amendment was ratified in 1920."
    assert sanitize_text(text) == text


def test_no_double_spaces():
    result = sanitize_text("Hello \u4f60\u597d world")
    assert "  " not in result
