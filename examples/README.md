# Example Materials

These sample curriculum files let you test Claw-ED without using your own materials.

## Quick Start

```bash
# Ingest the sample curriculum
clawed ingest examples/sample_curriculum/

# Generate a lesson
clawed lesson "Supply and Demand" -g 11 -s "Economics"
```

## What's Included

### sample_curriculum/US_History/
- `american_revolution_overview.md` — lesson outline with vocabulary and primary sources
- `civil_war_causes.md` — document-based lesson with scaffolding

### sample_curriculum/Economics/
- `supply_and_demand.md` — introductory economics lesson with graphs

## Using Your Own Materials

For best results, point Ed at your actual teaching files:

```bash
clawed ingest ~/Documents/MyLessons/
```

Ed reads PDF, DOCX, PPTX, DOC, PPT, TXT, MD, HTML, and XLSX files. The more you give it, the better it learns your teaching voice.
