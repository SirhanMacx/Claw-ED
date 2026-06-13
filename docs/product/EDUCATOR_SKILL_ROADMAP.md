# Claw-ED Educator Skill Roadmap

Status: prototype. The Mac release is still coming soon; do not publish public downloads until the Mac app and iOS companion are tested together.

## Product Thesis

Claw-ED is an agent harness for teacher work. The Mac mini is the local operator: it indexes lesson materials, learns the teacher's style, runs the agent loop, asks for permission before risky actions, and writes usable classroom artifacts. The iPhone is the remote: it sends tasks, resolves approvals, and lets a teacher start work without sitting at the Mac.

The important claim is not "AI lesson planner." It is "your local teaching agent can use your own curriculum, your own style, and your own approval rules."

## Now Exposed In The Harness

- Agent chat with live tool progress and approvals.
- Materials ingestion and style profiles.
- Curriculum index status/search through `curriculum_index`.
- Brain stats/search/read/capture/dream through `brain_stats`, `brain_search`, `brain_read`, `brain_capture`, and `brain_dream`.
- Self-improvement through `self_distill`, now correctly treated as a local-write action.
- Scheduling and recurring tasks through `schedule_task`.
- Full material generation through the existing lesson, bundle, assessment, game, simulation, parent communication, sub-packet, differentiation, Drive, and Mac-file tools.
- iPhone remote quick actions for index, lesson bundle, Do Now, dream preview, self-improvement, and brain search.

## Skill Families To Add Next

1. UDL and accessibility review
   - Add `udl_review` to inspect a generated lesson/handout for engagement, representation, and action/expression options.
   - Add `accessibility_rewrite` to produce vocabulary supports, alternate modalities, accessible document structure, and assistive-tech-friendly variants.
   - Source basis: CAST UDL Guidelines 3.0 emphasize multiple means of engagement, representation, and action/expression, with learner agency as the goal: https://udlguidelines.cast.org/

2. Formative assessment loop
   - Add `exit_ticket_analyzer` for pasted or photographed exit tickets.
   - Add `reteach_plan` that turns evidence into tomorrow's small-group moves.
   - Add `student_evidence_capture` that writes non-sensitive observations to the brain.
   - Source basis: IES describes formative assessment as gathering, interpreting, and using evidence to adjust instruction in a short period of time: https://ies.ed.gov/use-work/resource-library/report/descriptive-study/formative-assessment-and-elementary-school-student-academic-achievement-review-evidence

3. AI-use and privacy coach
   - Add `ai_use_notice_builder` for district/teacher-facing explanations of what is local, what goes to provider APIs, and when human review is required.
   - Add `provider_boundary_check` that warns when a requested task will send excerpts to a cloud model, OpenRouter, Ollama cloud, Google Drive, or another service.
   - Source basis: UNESCO's AI competency framework for teachers names human-centred mindset, ethics of AI, AI foundations/applications, AI pedagogy, and professional learning as core dimensions: https://www.unesco.org/en/articles/ai-competency-framework-teachers

4. Human-in-the-loop lesson QA
   - Add `teacher_ready_review` that checks factuality, standards alignment, timing, cognitive demand, answer keys, and classroom usability before a bundle is marked ready.
   - Add `source_grounding_report` that lists which indexed materials influenced a generated artifact.
   - Source basis: the U.S. Department of Education report argues people must remain involved in goal setting, pattern analysis, and decision-making for educational AI: https://www.ed.gov/sites/ed/files/documents/ai-report/ai-report.pdf

5. District pilot portfolio builder
   - Add `portfolio_build` that runs a controlled sample from a folder of safe lesson materials and emits a demo set: teacher lesson plan, student handout, slides outline, assessment, differentiation notes, parent note, and a readiness report.
   - Add `portfolio_manifest` so public advertising can show sample outputs without exposing private teacher files.

6. Classroom operations pack
   - Add `morning_prep` skill around schedule/task orchestration: today's Do Now, agenda, copies list, slide opener, and parent/student reminders.
   - Add `absence_recovery` to produce a sub packet and catch-up path from the current unit.
   - Add `iep_504_guardrails` to turn accommodation notes into practical lesson moves without diagnosing or making placement decisions.

## Release Gate For Advertising Samples

- Use synthetic or explicitly cleared lesson materials only.
- Every sample artifact must include a manifest with source status: synthetic, public-domain, teacher-cleared, or generated.
- Run a no-cloud mode sample with Ollama/local model if available, plus a cloud-provider sample with the provider boundary disclosed.
- Verify the Mac app can ingest the sample folder, generate a lesson bundle, export/open files, and show approval prompts.
- Verify the iOS app can send at least one quick action, receive streamed progress, and resolve one approval against the same Mac.
