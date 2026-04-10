"""Multi-phase MasterContent generation for reliable output with smaller models.

Splits what was a single 12K-token LLM call into 4 focused phases:

1. **Phase 1 — Skeleton + Primary Sources** (~3K tokens)
   title, subject, objective, standards, vocabulary, primary_sources,
   misconceptions, prerequisite_skills, lesson_personality, lesson_format

2. **Phase 2 — Instruction + Guided Notes** (~3K tokens)
   direct_instruction (with teacher_script, hooks, transitions),
   guided_notes (10-12), formative_checks

3. **Phase 3 — Activities** (~2K tokens)
   do_now, stations (with answer keys), jigsaw, creative_activity,
   independent_work, minute_by_minute

4. **Phase 4 — Assessment + Differentiation** (~2K tokens)
   exit_ticket (CRQ progression), differentiation (IEP/ELL/Gifted),
   homework (AI-resistant)

Each downstream phase receives upstream phase output as context, so the
generated content is internally coherent (e.g. the Do Now references a
primary source from Phase 1, the exit ticket uses vocabulary from Phase 2).

Benefits over single-shot generation:
- Smaller output per call → fewer timeouts on slow models (GLM 5.1 Cloud)
- Per-phase retry → don't waste 10min regenerating whole lesson
- Per-phase quality gates → catch issues early, not after everything
- Better focus → the LLM has a smaller, clearer task per call
"""
from clawed.phases.models import (
    Phase1Skeleton,
    Phase2Instruction,
    Phase3Activities,
    Phase4Assessment,
)
from clawed.phases.pipeline import generate_master_content_phased

__all__ = [
    "Phase1Skeleton",
    "Phase2Instruction",
    "Phase3Activities",
    "Phase4Assessment",
    "generate_master_content_phased",
]
