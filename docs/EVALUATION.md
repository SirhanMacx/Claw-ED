# Evidence before model or harness claims

The default tests use synthetic curriculum examples and mocked providers. They verify software behavior; they do not establish teaching quality. Do not import private classroom or colleague material into public test fixtures.

For a model or framework comparison, use the same permitted source packet, objective, grade, prompt, output schema, and token budget. Record provider, exact model ID, date, input/output tokens, retry cost, wall time, and failures. Keep the original outputs and teacher edits side by side.

Score each result on a 0–4 rubric with a teacher reviewing it:

| Dimension | Evidence required |
| --- | --- |
| Accuracy | Check factual claims against the supplied sources; record errors |
| Source fidelity | Verify quotations, locations, attribution, and missing evidence |
| Answer support | Answer every question from the stimulus; check every answer key |
| Reading level | Inspect vocabulary, directions, and support for the intended learners |
| Classroom use | Check pacing, student actions, teacher directions, and editable layouts |
| Editing effort | Record minutes until the teacher would use the material |
| Recovery | Interrupt after a completed phase; confirm resumed work and total additional cost |

The automated regression cases in `tests/test_harness_regressions.py` check concurrent tool isolation, provider request contracts, multilingual evidence, atomic worker claims, cancellation, and checkpoint reuse/invalidation. Add representative teacher-reviewed fixtures before setting a pedagogical pass threshold. A missed source, unsupported answer, or mislabeled successful delivery is a release finding even if prose sounds polished.

A comparison against LangGraph or an official agent SDK should keep the teaching schema, compilers, sources, and evaluation rubric fixed. Compare only the orchestration layer. Do not spend on live runs or change a teacher's configured model automatically.
