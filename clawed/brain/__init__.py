"""Claw-ED Brain — compounding knowledge store for teaching intelligence.

The brain is a markdown-based knowledge store with the compiled-truth +
timeline pattern (inspired by Garry Tan's gbrain). Every page has:

- **Compiled truth**: synthesis of current understanding (rewritten as
  evidence arrives)
- **Timeline**: append-only log of evidence with source citations

Over time, the brain makes Ed smarter about THIS teacher, THESE students,
THESE topics. Every lesson generation reads the brain first, and every
generation writes new information back.

Page types:
- `brain/students/{slug}.md` — per-student profiles (strengths, accommodations, history)
- `brain/topics/{slug}.md` — per-topic teaching history (what worked, misconceptions)
- `brain/lessons/{date}-{slug}.md` — per-generated-lesson record
- `brain/originals/{slug}.md` — teacher's pedagogical insights and philosophy
- `brain/classes/{slug}.md` — per-class-period observations
"""
from clawed.brain.store import BrainPage, BrainStore, TimelineEntry

__all__ = ["BrainPage", "BrainStore", "TimelineEntry"]
