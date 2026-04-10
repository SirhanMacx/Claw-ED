"""Tests for the Curriculum Knowledge Base."""

from __future__ import annotations

import tempfile
from pathlib import Path

from clawed.agent_core.memory.curriculum_kb import CurriculumKB


class TestCurriculumKB:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = Path(self.tmp) / "test_kb.db"
        self.kb = CurriculumKB(db_path=self.db_path)

    def test_index_and_search(self):
        self.kb.index(
            teacher_id="t1",
            doc_title="Civil War Unit",
            source_path="/docs/civil_war.docx",
            full_text=(
                "The Civil War began in 1861 when Confederate forces attacked "
                "Fort Sumter. Key causes included slavery, states rights, and "
                "economic differences between the North and South."
            ),
            metadata={"subject": "History", "grade": "8"},
        )
        results = self.kb.search("t1", "What caused the Civil War?", top_k=5)
        assert len(results) > 0
        assert "Civil War" in results[0]["chunk_text"]
        assert results[0]["doc_title"] == "Civil War Unit"

    def test_deduplication(self):
        text = "Photosynthesis converts light energy into chemical energy."
        self.kb.index("t1", "Bio Notes", "/bio.docx", text)
        self.kb.index("t1", "Bio Notes", "/bio.docx", text)
        results = self.kb.search("t1", "photosynthesis", top_k=100)
        chunks = [r["chunk_text"] for r in results]
        assert len(chunks) == len(set(chunks))

    def test_stats(self):
        self.kb.index("t1", "Doc A", "/a.docx", "Content about math fractions.")
        self.kb.index("t1", "Doc B", "/b.docx", "Content about science cells.")
        stats = self.kb.stats("t1")
        assert stats["doc_count"] == 2
        assert stats["chunk_count"] >= 2

    def test_search_empty_kb(self):
        results = self.kb.search("t1", "anything", top_k=5)
        assert results == []

    def test_teacher_isolation(self):
        self.kb.index("t1", "T1 Doc", "/t1.docx", "Teacher one unique material.")
        self.kb.index("t2", "T2 Doc", "/t2.docx", "Teacher two unique material.")
        results = self.kb.search("t1", "material", top_k=10)
        for r in results:
            assert "Teacher two" not in r["chunk_text"]

    def test_index_returns_chunk_count(self):
        added = self.kb.index("t1", "Doc", "/d.docx", "Some content here.")
        assert added >= 1

    def test_chunking_long_text(self):
        long_text = " ".join(["word"] * 1200)
        added = self.kb.index("t1", "Long Doc", "/long.docx", long_text)
        assert added >= 2  # Should produce multiple chunks

    def test_empty_text_produces_no_chunks(self):
        added = self.kb.index("t1", "Empty", "/e.docx", "")
        assert added == 0
        assert self.kb.stats("t1")["chunk_count"] == 0
