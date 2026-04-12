# Claw-ED Privacy Model (ED-8)

## Route Visibility

| Route pattern | Auth required | Audience | Why public |
|---|---|---|---|
| `/api/share/{token}` | No | Anyone with the link | Share links are the distribution mechanism for lessons |
| `/api/classroom/{code}/state` | No (class code) | Students in the room | Students need slide/timer state during class |
| `/api/classroom/{code}/ws` | No (class code) | Students in the room | Real-time sync for student devices |
| `/api/classroom/{code}/respond` | No (class code) | Students in the room | Poll/exit-ticket submission |
| `/api/chat/student` | No (lesson_id + share_token) | Students with the share link | LMS-embedded chatbot |
| `/student/{code}` | No (class code) | Students in the room | Student-facing class page |
| All other `/api/*` routes | Bearer token | Teacher only | Generation, settings, export, feedback |

## Data Visible to Students

- **Classroom state:** slide number, timer, poll question, poll response count (not raw responses).
- **Shared lessons:** lesson title, objective, content sections, standards. No teacher name or identity fields.
- **Student chat:** lesson content only; no teacher persona name is surfaced in chat responses.

## Teacher Name Visibility

Teacher identity is stripped from all student-facing and community-sharing paths:
- `_scrub_pii()` recursively removes `teacher_name`, `school`, `teacher_id`, `persona`, `teacher_email`, `name`, `author`, `author_email`, and `creator` from community-shared lessons.
- The `/classroom/{code}/state` endpoint and WebSocket never include teacher identity.
- Student chat responses reference "your teacher" generically.

## Student-Generated Content Retention

- **Poll responses:** stored in-memory only; lost on process restart. TTL is 24 hours.
- **Chat messages:** persisted in SQLite (`chat_messages` table) keyed by `lesson_id`. No student identity beyond a session-scoped ID is stored.
- **Student questions (Telegram):** stored in SQLite with a `student_id` (Telegram user ID). Teachers can view via class reports; students cannot query other students' data.

## Analytics Data Handling

- **Feedback:** lesson ratings and free-text notes stored in SQLite. Tied to `lesson_id`, not student identity.
- **Prompt versions:** A/B test metrics (avg rating, usage count) are aggregate; no per-student tracking.
- **No third-party analytics:** Claw-ED does not integrate with Google Analytics, Mixpanel, or any external tracking service.

## In-Memory Store Lifecycle

All in-memory stores (classroom sessions, saved sources, community lessons) have:
- 24-hour TTL expiration.
- Maximum size caps (100 sessions, 1000 sources, 500 community lessons).
- No persistence across process restarts.
