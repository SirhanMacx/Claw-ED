"""Tests for the image pipeline."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from clawed.image_pipeline import _collect_image_specs, fetch_all_images

# ── _collect_image_specs ─────────────────────────────────────────────


def _make_mock_master(
    vocab_specs=None,
    ps_specs=None,
    di_specs=None,
    et_specs=None,
):
    """Build a mock MasterContent with configurable image_spec fields."""
    mc = MagicMock()

    # vocabulary entries
    vocab = []
    for spec in (vocab_specs or []):
        entry = MagicMock()
        entry.image_spec = spec
        vocab.append(entry)
    mc.vocabulary = vocab

    # primary_sources
    sources = []
    for spec in (ps_specs or []):
        ps = MagicMock()
        ps.image_spec = spec
        sources.append(ps)
    mc.primary_sources = sources

    # direct_instruction sections
    sections = []
    for spec in (di_specs or []):
        sec = MagicMock()
        sec.image_spec = spec
        sections.append(sec)
    mc.direct_instruction = sections

    # exit_ticket (StimulusQuestion with stimulus_image_spec)
    tickets = []
    for spec in (et_specs or []):
        sq = MagicMock()
        sq.stimulus_image_spec = spec
        tickets.append(sq)
    mc.exit_ticket = tickets

    return mc


def test_collect_image_specs_empty():
    """Empty MasterContent yields no specs."""
    mc = _make_mock_master()
    specs = _collect_image_specs(mc)
    assert len(specs) == 0
    assert isinstance(specs, dict)


def test_collect_image_specs_gathers_content_specs():
    """Specs are collected ONLY from slide types that embed an image.

    Instruction sections and the exit ticket embed images; the vocabulary and
    primary-source builders are text-only, so collecting their specs would waste
    a fetch + a vision call on an image that never renders. They are skipped.
    """
    mc = _make_mock_master(
        vocab_specs=["vocab_img_1", "vocab_img_2"],
        ps_specs=["source_img_1"],
        di_specs=["instruction_img_1"],
        et_specs=["ticket_img_1"],
    )
    specs = _collect_image_specs(mc)
    assert set(specs.keys()) == {
        "instruction_img_1",
        "ticket_img_1",
    }
    # Vocabulary + primary-source slides are text-only — specs intentionally skipped.
    assert "vocab_img_1" not in specs
    assert "source_img_1" not in specs


def test_collect_image_specs_deduplicates():
    """Duplicate specs across collected section types are deduplicated."""
    mc = _make_mock_master(
        di_specs=["shared_spec"],
        et_specs=["shared_spec"],
    )
    specs = _collect_image_specs(mc)
    assert len(specs) == 1
    assert "shared_spec" in specs


def test_collect_image_specs_skips_empty_strings():
    """Empty image_spec strings are not collected."""
    mc = _make_mock_master(
        di_specs=["", "real_spec"],
        ps_specs=[""],
    )
    specs = _collect_image_specs(mc)
    assert set(specs.keys()) == {"real_spec"}


# ── fetch_all_images ─────────────────────────────────────────────────


def test_fetch_all_images_empty():
    """No specs means no images fetched, returns empty dict."""
    mc = _make_mock_master()
    mc.subject = "Science"
    result = asyncio.run(fetch_all_images(mc))
    assert isinstance(result, dict)
    assert len(result) == 0


def test_fetch_all_images_with_specs():
    """Fetches images for each spec, returns successful ones."""
    mc = _make_mock_master(di_specs=["test_image"])
    mc.subject = "History"

    fake_path = MagicMock()
    fake_path.exists.return_value = True

    async def fake_fetch(spec, subject=""):
        return fake_path

    with patch("clawed.image_pipeline._fetch_one") as mock_fetch:
        mock_fetch.return_value = ("test_image", fake_path)

        # We need to make it an awaitable
        async def run():
            with patch("clawed.image_pipeline._fetch_one", new=AsyncMock(return_value=("test_image", fake_path))), \
                 patch("clawed.image_pipeline.vision_filter_batch",
                       new=AsyncMock(side_effect=lambda items, **kw: {s for s, _ in items})):
                return await fetch_all_images(mc)

        result = asyncio.run(run())
        assert "test_image" in result


def test_fetch_all_images_handles_failures():
    """Failed fetches are excluded from the result dict."""
    mc = _make_mock_master(di_specs=["good_img", "bad_img"])
    mc.subject = "Math"

    good_path = MagicMock()
    good_path.exists.return_value = True

    async def fake_fetch_one(spec, subject="", context="", timeout=15):
        if spec == "good_img":
            return (spec, good_path)
        return (spec, None)

    with patch("clawed.image_pipeline._fetch_one", side_effect=fake_fetch_one), \
         patch("clawed.image_pipeline.vision_filter_batch",
               new=AsyncMock(side_effect=lambda items, **kw: {s for s, _ in items})):
        result = asyncio.run(fetch_all_images(mc))
        assert "good_img" in result
        assert "bad_img" not in result


def test_fetch_all_images_handles_exceptions_in_gather():
    """Exceptions in individual fetches are logged, not raised."""
    mc = _make_mock_master(vocab_specs=["crash_img"])
    mc.subject = "Science"

    async def fake_fetch_one(spec, subject="", context="", timeout=15):
        raise ConnectionError("Network down")

    with patch("clawed.image_pipeline._fetch_one", side_effect=fake_fetch_one):
        result = asyncio.run(fetch_all_images(mc))
        # Exceptions are caught by gather(return_exceptions=True)
        assert isinstance(result, dict)
        assert len(result) == 0


# ── _resolve_from_teacher_assets ────────────────────────────────────


def test_resolve_teacher_assets_dedup():
    """Same query for different specs returns different images (no reuse)."""
    from clawed.image_pipeline import _resolve_from_teacher_assets

    fake_matches = [
        {"path": "/tmp/img_a.png", "score": 0.9},
        {"path": "/tmp/img_b.png", "score": 0.8},
        {"path": "/tmp/img_c.png", "score": 0.7},
    ]

    mock_registry = MagicMock()
    mock_registry.search_images_for_topic.return_value = fake_matches

    # All three fake paths must "exist"
    with patch("clawed.asset_registry.AssetRegistry", return_value=mock_registry), \
         patch("clawed.image_pipeline.Path") as mock_path_cls:
        # Make every Path(match["path"]).exists() return True
        mock_path_inst = MagicMock()
        mock_path_inst.exists.return_value = True
        mock_path_cls.side_effect = lambda p: mock_path_inst if isinstance(p, str) else MagicMock()
        # But we need unique str() values for dedup tracking

        def path_side_effect(p):
            if isinstance(p, str):
                m = MagicMock()
                m.exists.return_value = True
                m.__str__ = lambda self, _p=p: _p
                return m
            return MagicMock()

        mock_path_cls.side_effect = path_side_effect

        spec_map = {
            "cell division diagram": "mitosis and meiosis",
            "DNA structure": "double helix structure",
        }
        resolved = _resolve_from_teacher_assets(spec_map, "teacher-1")

        # Both specs should resolve, but to DIFFERENT images
        assert len(resolved) == 2
        paths_used = [str(v) for v in resolved.values()]
        assert len(set(paths_used)) == 2, "Same image used for two specs — dedup failed"


def test_resolve_empty_returns_empty():
    """Empty spec_map produces empty result without errors."""
    from clawed.image_pipeline import _resolve_from_teacher_assets

    result = _resolve_from_teacher_assets({}, "teacher-1")
    assert result == {}


def test_used_paths_tracking():
    """Already-used paths are skipped, forcing fallback to next candidate."""
    from clawed.image_pipeline import _resolve_from_teacher_assets

    # Registry returns the SAME image for both queries
    single_match = [{"path": "/tmp/only_one.png", "score": 0.9}]

    mock_registry = MagicMock()
    mock_registry.search_images_for_topic.return_value = single_match

    def path_side_effect(p):
        if isinstance(p, str):
            m = MagicMock()
            m.exists.return_value = True
            m.__str__ = lambda self, _p=p: _p
            return m
        return MagicMock()

    with patch("clawed.asset_registry.AssetRegistry", return_value=mock_registry), \
         patch("clawed.image_pipeline.Path", side_effect=path_side_effect):

        spec_map = {
            "spec_a": "context a",
            "spec_b": "context b",
        }
        resolved = _resolve_from_teacher_assets(spec_map, "teacher-1")

        # Only one spec can get the image — the other has no unused candidates
        assert len(resolved) == 1, (
            f"Expected 1 resolved (dedup should block reuse), got {len(resolved)}"
        )
