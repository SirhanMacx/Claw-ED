"""Tests for Curriculum Knowledge Graph."""

import pytest

from clawed.agent_core.memory.knowledge_graph import CurriculumKG, _normalize_id


class TestNormalizeId:
    def test_basic(self):
        assert _normalize_id("American Revolution") == "american_revolution"

    def test_strips_special_chars(self):
        assert _normalize_id("U.S. History!") == "us_history"

    def test_empty_returns_empty(self):
        assert _normalize_id("") == ""

    def test_truncates_long_names(self):
        result = _normalize_id("a" * 200)
        assert len(result) <= 120


class TestCurriculumKG:
    @pytest.fixture()
    def kg(self, tmp_path):
        db = tmp_path / "test_kg.db"
        return CurriculumKG(db_path=db)

    def test_add_entity_returns_id(self, kg):
        eid = kg.add_entity("teacher1", "American Revolution", "topic", embed=False)
        assert eid == "american_revolution"

    def test_add_entity_dedup(self, kg):
        kg.add_entity("teacher1", "Civil War", "topic", embed=False)
        kg.add_entity("teacher1", "Civil War", "topic", embed=False)
        stats = kg.stats("teacher1")
        assert stats["entity_count"] == 1

    def test_query_entity(self, kg):
        kg.add_entity("teacher1", "Reconstruction", "topic", embed=False)
        result = kg.query_entity("teacher1", "Reconstruction")
        assert result is not None
        assert result["name"] == "Reconstruction"
        assert result["entity_type"] == "topic"

    def test_query_entity_not_found(self, kg):
        result = kg.query_entity("teacher1", "Nonexistent")
        assert result is None

    def test_add_triple_auto_creates_entities(self, kg):
        kg.add_triple("teacher1", "Civil War", "prerequisite_for", "Reconstruction")
        stats = kg.stats("teacher1")
        assert stats["entity_count"] == 2
        assert stats["triple_count"] == 1

    def test_add_triple_returns_id(self, kg):
        tid = kg.add_triple("teacher1", "Topic A", "related_to", "Topic B")
        assert tid.startswith("t_")

    def test_triple_dedup(self, kg):
        kg.add_triple("teacher1", "A", "related_to", "B")
        kg.add_triple("teacher1", "A", "related_to", "B")
        stats = kg.stats("teacher1")
        assert stats["triple_count"] == 1

    def test_invalidate(self, kg):
        tid = kg.add_triple("teacher1", "X", "taught_in", "Fall 2024")
        assert kg.invalidate("teacher1", tid)
        stats = kg.stats("teacher1")
        assert stats["expired_facts"] == 1

    def test_invalidate_nonexistent(self, kg):
        assert not kg.invalidate("teacher1", "t_fake_id")

    def test_query_related_outgoing(self, kg):
        kg.add_triple("teacher1", "Civil War", "prerequisite_for", "Reconstruction")
        results = kg.query_related("teacher1", "Civil War", direction="outgoing")
        assert len(results) == 1
        assert results[0]["entity"] == "Reconstruction"
        assert results[0]["predicate"] == "prerequisite_for"

    def test_query_related_incoming(self, kg):
        kg.add_triple("teacher1", "Civil War", "prerequisite_for", "Reconstruction")
        results = kg.query_related("teacher1", "Reconstruction", direction="incoming")
        assert len(results) == 1
        assert results[0]["entity"] == "Civil War"

    def test_query_related_both(self, kg):
        kg.add_triple("teacher1", "A", "related_to", "B")
        kg.add_triple("teacher1", "C", "related_to", "A")
        results = kg.query_related("teacher1", "A", direction="both")
        assert len(results) == 2

    def test_query_related_filters_expired(self, kg):
        tid = kg.add_triple("teacher1", "X", "related_to", "Y")
        kg.invalidate("teacher1", tid)
        results = kg.query_related("teacher1", "X", include_expired=False)
        assert len(results) == 0

    def test_query_related_includes_expired(self, kg):
        tid = kg.add_triple("teacher1", "X", "related_to", "Y")
        kg.invalidate("teacher1", tid)
        results = kg.query_related("teacher1", "X", include_expired=True)
        assert len(results) == 1

    def test_query_related_by_predicate(self, kg):
        kg.add_triple("teacher1", "A", "related_to", "B")
        kg.add_triple("teacher1", "A", "prerequisite_for", "C")
        results = kg.query_related(
            "teacher1",
            "A",
            predicate="prerequisite_for",
            direction="outgoing",
        )
        assert len(results) == 1
        assert results[0]["entity"] == "C"

    def test_get_prerequisites(self, kg):
        kg.add_triple("teacher1", "Slavery", "prerequisite_for", "Civil War")
        kg.add_triple("teacher1", "Civil War", "builds_on", "Slavery")
        prereqs = kg.get_prerequisites("teacher1", "Civil War")
        assert len(prereqs) >= 1
        names = {p["entity"] for p in prereqs}
        assert "Slavery" in names

    def test_get_topic_context_empty(self, kg):
        result = kg.get_topic_context("teacher1", "Unknown Topic")
        assert result == ""

    def test_get_topic_context_with_data(self, kg):
        kg.add_triple("teacher1", "Revolution", "covers_standard", "CCSS.RH.8.1")
        kg.add_triple("teacher1", "Revolution", "includes_vocab", "Taxation")
        ctx = kg.get_topic_context("teacher1", "Revolution")
        assert "Standards:" in ctx
        assert "vocabulary:" in ctx.lower()

    def test_teacher_isolation(self, kg):
        kg.add_entity("teacher1", "Topic A", embed=False)
        kg.add_entity("teacher2", "Topic B", embed=False)
        assert kg.stats("teacher1")["entity_count"] == 1
        assert kg.stats("teacher2")["entity_count"] == 1

    def test_stats(self, kg):
        kg.add_triple("teacher1", "A", "related_to", "B")
        kg.add_triple("teacher1", "A", "covers_standard", "C")
        stats = kg.stats("teacher1")
        assert stats["entity_count"] == 3
        assert stats["triple_count"] == 2
        assert "related_to" in stats["predicates"]
        assert "covers_standard" in stats["predicates"]


class TestKGExtractor:
    def test_extract_entities_from_title(self):
        from clawed.agent_core.memory.kg_extractor import extract_entities_from_document

        entities = extract_entities_from_document("American Revolution", "", [])
        names = [e["name"] for e in entities]
        assert "American Revolution" in names

    def test_extract_entities_from_tags(self):
        from clawed.agent_core.memory.kg_extractor import extract_entities_from_document

        entities = extract_entities_from_document("", "", ["Civil War", "Reconstruction"])
        names = [e["name"] for e in entities]
        assert "Civil War" in names
        assert "Reconstruction" in names

    def test_extract_standard_codes(self):
        from clawed.agent_core.memory.kg_extractor import extract_standard_codes

        codes = extract_standard_codes("Aligned to CCSS.ELA.RL.8.1 and CCSS.ELA.W.8.2")
        assert len(codes) == 2
        assert "CCSS.ELA.RL.8.1" in codes

    def test_extract_vocabulary_terms(self):
        from clawed.agent_core.memory.kg_extractor import extract_entities_from_document

        content = "Key vocabulary: taxation, representation, boycott, Parliament"
        entities = extract_entities_from_document("Test", content, [])
        types = {e["entity_type"] for e in entities}
        assert "term" in types

    def test_infer_relationships_vocab(self):
        from clawed.agent_core.memory.kg_extractor import infer_relationships

        entities = [
            {"name": "Revolution", "entity_type": "topic"},
            {"name": "Boycott", "entity_type": "term"},
        ]
        rels = infer_relationships(entities, "Revolution")
        assert any(r["predicate"] == "includes_vocab" for r in rels)

    def test_infer_relationships_standard(self):
        from clawed.agent_core.memory.kg_extractor import infer_relationships

        entities = [
            {"name": "Revolution", "entity_type": "topic"},
            {"name": "CCSS.RH.8.1", "entity_type": "standard"},
        ]
        rels = infer_relationships(entities, "Revolution")
        assert any(r["predicate"] == "covers_standard" for r in rels)

    def test_empty_doc(self):
        from clawed.agent_core.memory.kg_extractor import extract_entities_from_document

        entities = extract_entities_from_document("", "", [])
        assert entities == []
