# Claw-ED API Reference

REST API reference for the Claw-ED web server (`clawed serve`).

## Base URL

```
http://localhost:8080
```

The default port is 8080. Override with the `--port` flag or `EDUAGENT_PORT` environment variable.

## Authentication

All endpoints (except `/api/health` and `/api/share/{token}`) require a bearer token.

### Bearer Token

Include the token in the `Authorization` header:

```
Authorization: Bearer YOUR_TOKEN
```

The token is auto-generated on first server start and stored at `~/.eduagent/api_token`. Find it with:

```bash
cat ~/.eduagent/api_token
```

### Cookie Auth

For browser sessions, append `?token=YOUR_TOKEN` to any page URL on the first visit. A session cookie (`clawed_token`) is set automatically and persists for 24 hours.

### Localhost Bypass

Set `EDUAGENT_LOCAL_AUTH_BYPASS=1` to skip authentication for requests from `127.0.0.1` / `::1`. Useful for local development and testing. Do not enable this on shared or network-accessible deployments.

## Rate Limiting

Rate limits are enforced per-client-IP, in-memory. Limits reset when the server restarts.

| Endpoint Category | Limit |
|-------------------|-------|
| Generation endpoints (`/api/unit`, `/api/lesson`, `/api/materials`, `/api/full`, `/api/course`) | 10/minute |
| Chat endpoints (`/api/chat`, `/api/gateway/chat`) | 30/minute |
| Read-only endpoints (`/api/health`, `/api/settings`, `/api/units`, `/api/templates`, `/api/score/*`) | 60/minute |
| Tool endpoints (`/api/sub-packet`, `/api/parent-comm`) | 10/minute |
| Feedback & improvement (`/api/feedback`, `/api/improve`) | 10/minute |

Exceeding the limit returns `429 Too Many Requests`:

```json
{
  "detail": "Rate limit exceeded (10/minute)"
}
```

---

## Endpoints

### Health & Settings

#### `GET /api/health`

Lightweight liveness check. No authentication required. No database or LLM calls.

**Response:**

```json
{
  "status": "ok",
  "version": "4.6.2026"
}
```

---

#### `GET /api/health/diagnostics`

Full diagnostics including database stats and LLM connection test. Requires authentication.

**Response:**

```json
{
  "status": "ok",
  "llm_provider": "anthropic",
  "llm_model": "claude-sonnet-4-6",
  "llm_connected": true,
  "persona_loaded": true,
  "units_generated": 12,
  "lessons_generated": 48,
  "db_size_mb": 3.41,
  "version": "4.6.2026"
}
```

---

#### `GET /api/settings`

Get current settings. API keys are masked in the response.

**Response:**

```json
{
  "provider": "anthropic",
  "anthropic_model": "claude-sonnet-4-6",
  "openai_model": "gpt-4o",
  "ollama_model": "llama3.2",
  "ollama_base_url": "http://localhost:11434",
  "anthropic_key_masked": "sk-ant-...xxxx",
  "openai_key_masked": null,
  "has_anthropic_key": true,
  "has_openai_key": false,
  "include_homework": true,
  "export_format": "markdown"
}
```

---

#### `POST /api/settings`

Save settings and optionally update an API key.

**Request:**

```json
{
  "provider": "anthropic",
  "api_key": "sk-ant-api03-...",
  "anthropic_model": "claude-sonnet-4-6",
  "openai_model": "gpt-4o",
  "ollama_model": "llama3.2",
  "ollama_base_url": "http://localhost:11434",
  "default_grade": "8",
  "default_subject": "Science",
  "include_homework": true,
  "export_format": "markdown"
}
```

**Response:**

```json
{
  "status": "saved"
}
```

---

#### `GET /api/settings/test-connection`

Test the current LLM connection with a small probe request.

**Response:**

```json
{
  "connected": true,
  "provider": "anthropic",
  "model": "claude-sonnet-4-6",
  "latency_ms": 342
}
```

---

#### `POST /api/settings/clear-content`

Delete all generated units and lessons. Persona and settings are preserved. Use with caution.

**Response:**

```json
{
  "status": "cleared"
}
```

---

#### `POST /api/settings/reset`

Full factory reset. Deletes all data including persona, lessons, and settings.

**Response:**

```json
{
  "status": "reset"
}
```

---

### Ingestion & Persona

#### `POST /api/ingest`

Upload teaching materials (lesson plans, handouts, slideshows) to build the teacher persona and curriculum knowledge base.

**Request:** `multipart/form-data` with one or more files.

Supported formats: PDF, DOCX, DOC, PPTX, PPT, TXT, MD, HTML, XLSX.

```bash
curl -X POST http://localhost:8080/api/ingest \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "files=@my_lesson_plan.docx" \
  -F "files=@unit_slides.pptx"
```

**Response:**

```json
{
  "teacher_id": "t_abc123",
  "persona": {
    "name": "Ms. Rodriguez",
    "teaching_style": "socratic",
    "subject_area": "History",
    "grade_levels": ["7", "8"]
  },
  "documents_ingested": 2
}
```

---

#### `GET /api/persona`

Get the current teacher persona.

**Response:**

```json
{
  "teacher_id": "t_abc123",
  "persona": {
    "name": "Ms. Rodriguez",
    "teaching_style": "socratic",
    "subject_area": "History",
    "grade_levels": ["7", "8"]
  }
}
```

Returns `404` if no persona exists (no files uploaded yet).

---

### Generation

#### `POST /api/unit`

Generate a unit plan.

**Request:**

```json
{
  "topic": "The American Revolution",
  "grade_level": "8",
  "subject": "History",
  "duration_weeks": 3,
  "standards": ["8.1.a", "8.1.b"]
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `topic` | string | Yes | -- | Lesson topic (1-500 chars) |
| `grade_level` | string | No | `"8"` | Grade level |
| `subject` | string | No | `"Science"` | Subject area |
| `duration_weeks` | integer | No | `3` | Unit duration (1-52 weeks) |
| `standards` | string[] | No | `[]` | Specific standards to align to |

**Response:**

```json
{
  "unit_id": "u_def456",
  "unit": {
    "title": "The American Revolution",
    "subject": "History",
    "grade_level": "8",
    "topic": "The American Revolution",
    "duration_weeks": 3,
    "daily_lessons": [
      { "lesson_number": 1, "topic": "Causes of the Revolution" },
      { "lesson_number": 2, "topic": "Key Battles and Turning Points" }
    ]
  }
}
```

---

#### `POST /api/lesson`

Generate a single lesson plan for an existing unit.

**Request:**

```json
{
  "unit_id": "u_def456",
  "lesson_number": 1
}
```

**Response:**

```json
{
  "lesson_id": "l_ghi789",
  "lesson": {
    "lesson_number": 1,
    "title": "Causes of the American Revolution",
    "objective": "Students will analyze the economic and political causes...",
    "standards": ["8.1.a"]
  }
}
```

---

#### `POST /api/materials`

Generate student materials (worksheets, handouts) for an existing lesson.

**Request:**

```json
{
  "lesson_id": "l_ghi789"
}
```

**Response:**

```json
{
  "lesson_id": "l_ghi789",
  "materials": {
    "worksheet_items": [...],
    "vocabulary": [...],
    "exit_ticket": [...]
  }
}
```

---

#### `POST /api/full`

End-to-end pipeline: generates a unit plan, all lessons, and all materials. Returns a Server-Sent Events (SSE) stream with progress updates.

**Request:**

```json
{
  "topic": "Photosynthesis",
  "grade_level": "7",
  "subject": "Science",
  "duration_weeks": 2,
  "standards": [],
  "include_homework": true,
  "max_lessons": 5,
  "template_slug": null
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `topic` | string | Yes | -- | Topic (1-500 chars) |
| `grade_level` | string | No | `"8"` | Grade level |
| `subject` | string | No | `"Science"` | Subject area |
| `duration_weeks` | integer | No | `3` | Unit duration |
| `standards` | string[] | No | `[]` | Standards to align to |
| `include_homework` | boolean | No | `true` | Generate homework assignments |
| `max_lessons` | integer | No | all | Cap the number of lessons generated |
| `template_slug` | string | No | `null` | Lesson structure template to use |

**Response:** SSE stream with events:

```
event: progress
data: {"step": "unit", "status": "generating", "message": "Generating unit plan..."}

event: progress
data: {"step": "unit", "status": "done", "unit_id": "u_def456", "title": "Photosynthesis", "lesson_count": 5}

event: progress
data: {"step": "lesson", "status": "generating", "lesson_number": 1, "topic": "Introduction to Photosynthesis"}

event: progress
data: {"step": "lesson", "status": "done", "lesson_id": "l_ghi789", "lesson_number": 1, "title": "Introduction to Photosynthesis"}

event: done
data: {"unit_id": "u_def456", "lesson_count": 5}
```

---

#### `GET /api/stream/unit`

Stream unit plan generation via SSE (for EventSource clients).

**Query parameters:** `topic` (required), `grade_level`, `subject`, `duration_weeks`.

```
GET /api/stream/unit?topic=Fractions&grade_level=5&subject=Math
```

---

#### `GET /api/stream/lesson`

Stream a single lesson generation via SSE.

**Query parameters:** `unit_id` (required), `lesson_number` (default `1`).

---

#### `POST /api/course`

Generate a full course structure from a list of topics. Returns SSE stream.

**Request:**

```json
{
  "subject": "Science",
  "grade_level": "7",
  "topics": ["Cells", "Photosynthesis", "Ecosystems"],
  "weeks_per_topic": 2
}
```

---

#### `GET /api/score/{lesson_id}`

Score a lesson on quality dimensions (alignment, engagement, rigor).

**Response:**

```json
{
  "lesson_id": "l_ghi789",
  "scores": {
    "alignment": 4.2,
    "engagement": 3.8,
    "rigor": 4.0,
    "overall": 4.0
  }
}
```

---

#### `POST /api/suggest/{lesson_id}`

Generate improvement suggestions for a lesson based on quality scores and teacher feedback.

**Response:**

```json
{
  "lesson_id": "l_ghi789",
  "suggestions": [
    "Add a higher-order thinking question to the exit ticket",
    "Include a primary source excerpt in the direct instruction"
  ]
}
```

---

#### `GET /api/templates`

List all available lesson structure templates.

**Response:**

```json
{
  "templates": [
    {
      "name": "Jigsaw",
      "slug": "jigsaw",
      "description": "Cooperative learning through expert groups",
      "best_for": "Complex topics with multiple subtopics"
    },
    {
      "name": "Socratic Seminar",
      "slug": "socratic_seminar",
      "description": "Discussion-based inquiry",
      "best_for": "Texts, primary sources, ethical dilemmas"
    }
  ]
}
```

---

#### `GET /api/units`

List all generated units.

**Response:**

```json
{
  "units": [
    {
      "id": "u_def456",
      "title": "The American Revolution",
      "subject": "History",
      "grade_level": "8",
      "lesson_count": 5
    }
  ]
}
```

---

#### `GET /api/lessons/{unit_id}`

List all lessons for a unit.

**Response:**

```json
{
  "lessons": [
    {
      "id": "l_ghi789",
      "lesson_number": 1,
      "title": "Causes of the American Revolution"
    }
  ]
}
```

---

### Feedback & Analytics

#### `POST /api/feedback`

Submit a rating and notes for a generated lesson. Lessons rated 4+ are auto-contributed to the teaching corpus.

**Request:**

```json
{
  "lesson_id": "l_ghi789",
  "rating": 4,
  "notes": "Great primary source, but the exit ticket was too easy",
  "sections_edited": ["exit_ticket"]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `lesson_id` | string | Yes | The lesson to rate |
| `rating` | integer | Yes | 1-5 stars |
| `notes` | string | No | Free-text feedback |
| `sections_edited` | string[] | No | Which sections the teacher manually edited |

**Response:**

```json
{
  "feedback_id": "f_jkl012",
  "message": "Feedback recorded. Thank you! This lesson has been added to your teaching corpus to improve future generations.",
  "corpus_contributed": true
}
```

---

#### `GET /api/feedback/{lesson_id}`

Get all feedback entries for a lesson.

**Response:**

```json
{
  "feedback": [
    {
      "id": "f_jkl012",
      "rating": 4,
      "notes": "Great primary source, but the exit ticket was too easy",
      "created_at": "2026-04-07T14:30:00"
    }
  ]
}
```

---

#### `GET /api/feedback-analysis`

Aggregate feedback analysis for a time window.

**Query parameters:** `days` (default `7`).

---

#### `GET /api/stats`

Get comprehensive analytics for the default teacher.

**Query parameters:** `teacher_id` (default `"local-teacher"`).

---

#### `GET /api/stats/{teacher_id}`

Get analytics for a specific teacher.

---

#### `POST /api/improve`

Trigger a prompt improvement cycle based on recent feedback.

**Request (optional):**

```json
{
  "feedback_window_days": 7
}
```

---

### Export & Sharing

#### `GET /api/export/{lesson_id}`

Export a lesson as Markdown, PDF, or DOCX.

**Query parameters:** `fmt` -- one of `markdown` (default), `pdf`, `docx`.

```
GET /api/export/l_ghi789?fmt=docx
```

Returns the file as a download.

---

#### `POST /api/export/{lesson_id}/classroom`

Generate a Google Classroom-compatible CourseWork JSON payload.

**Response:**

```json
{
  "lesson_id": "l_ghi789",
  "coursework": {
    "title": "Causes of the American Revolution",
    "description": "Students will analyze...",
    "materials": [...],
    "maxPoints": 100,
    "workType": "ASSIGNMENT",
    "state": "DRAFT"
  }
}
```

---

#### `POST /api/lessons/{lesson_id}/share`

Generate a shareable URL for a lesson.

**Response:**

```json
{
  "share_url": "/shared/abc123token",
  "token": "abc123token"
}
```

---

#### `GET /api/share/{token}`

Retrieve a shared lesson by its share token. No authentication required.

**Response:**

```json
{
  "lesson_id": "l_ghi789",
  "title": "Causes of the American Revolution",
  "share_token": "abc123token",
  "lesson": { ... }
}
```

---

#### `POST /api/import`

Import a lesson from a share URL or token.

**Request:**

```json
{
  "url": "http://localhost:8080/shared/abc123token",
  "token": null,
  "server": "http://localhost:8080"
}
```

Provide either `url` or `token`. Import is restricted to localhost by default. Override with `EDUAGENT_IMPORT_ALLOW_URLS`.

---

### Chat

#### `POST /api/chat`

Student chatbot -- a student asks a question about a specific lesson and gets an answer in the teacher's voice.

**Request:**

```json
{
  "lesson_id": "l_ghi789",
  "question": "Why did the colonists dump the tea?",
  "history": []
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `lesson_id` | string | Yes | Lesson to ground the response in |
| `question` | string | Yes | Student's question |
| `history` | object[] | No | Prior chat messages (`role`/`content` pairs) |

**Response:**

```json
{
  "response": "Great question! The colonists dumped the tea as a protest against...",
  "lesson_id": "l_ghi789"
}
```

---

#### `POST /api/gateway/chat`

Teacher chat through the Gateway. The `teacher_id` is resolved server-side from config -- callers cannot specify or impersonate a different teacher.

**Request:**

```json
{
  "message": "Make a lesson on the water cycle for 5th grade science"
}
```

**Response:**

```json
{
  "text": "Working on your lesson materials for \"The Water Cycle\" now...",
  "files": ["/Users/you/clawed_output/Water_Cycle_teacher.docx"],
  "buttons": []
}
```

---

### Tools

#### `POST /api/sub-packet`

Generate a complete substitute teacher packet.

**Request:**

```json
{
  "teacher_name": "Ms. Rodriguez",
  "school": "Lincoln Middle School",
  "class_name": "Period 3 US History",
  "grade": "8",
  "subject": "History",
  "date": "2026-04-10",
  "period_or_time": "10:00 AM - 10:50 AM",
  "lesson_topic": "The Boston Tea Party",
  "lesson_context": "Students finished reading the Declaration of Independence yesterday"
}
```

**Response:**

```json
{
  "packet": { ... },
  "markdown": "# Substitute Teacher Packet\n..."
}
```

---

#### `POST /api/parent-comm`

Generate a professional parent communication email.

**Request:**

```json
{
  "comm_type": "progress_update",
  "student_description": "7th grader who has been improving in class participation",
  "class_context": "US History, currently studying the Civil War",
  "tone": "professional and warm",
  "additional_notes": "Mention the upcoming project"
}
```

Valid `comm_type` values: `progress_update`, `behavior_concern`, `positive_note`, `upcoming_unit`, `permission_request`, `general_update`.

---

### School Deployment

#### `POST /api/school/setup`

Set up a school for multi-teacher deployment.

**Request:**

```json
{
  "name": "Lincoln Middle School",
  "state": "CA",
  "district": "LAUSD",
  "grade_levels": ["6", "7", "8"]
}
```

---

#### `GET /api/school/{school_id}`

Get school details.

---

#### `POST /api/school/add-teacher`

Add a teacher to a school.

**Request:**

```json
{
  "school_id": "s_abc123",
  "teacher_id": "t_def456",
  "role": "teacher",
  "department": "History"
}
```

---

#### `GET /api/school/{school_id}/teachers`

List all teachers in a school.

---

#### `POST /api/school/share`

Share a unit or lesson to the school's curriculum library.

**Request:**

```json
{
  "school_id": "s_abc123",
  "teacher_id": "t_def456",
  "content_type": "unit",
  "content_id": "u_ghi789",
  "department": "History"
}
```

---

#### `GET /api/school/{school_id}/shared-library`

Browse the school's shared curriculum library. Returns top-rated content.

**Query parameters:** `department` (optional), `limit` (default `50`).

---

#### `POST /api/school/rate-shared`

Rate a piece of shared content (1-5).

**Request:**

```json
{
  "shared_id": "sh_xyz",
  "rating": 5
}
```

---

### Onboarding

#### `POST /api/onboarding/persona-form`

Create a teacher persona from the quick setup form (no file upload needed).

**Request:**

```json
{
  "name": "Ms. Rodriguez",
  "subject_area": "History",
  "grade_levels": "7, 8",
  "teaching_style": "socratic",
  "preferred_lesson_format": "I Do / We Do / You Do"
}
```

Valid `teaching_style` values: `direct_instruction`, `socratic`, `inquiry_based`, `project_based`.

---

#### `POST /api/onboarding/step`

Update onboarding progress for a teacher.

**Request:**

```json
{
  "teacher_id": "t_abc123",
  "step": 2
}
```

---

#### `GET /api/onboarding/state`

Get the current onboarding state (persona status, step completed).

**Response:**

```json
{
  "has_persona": true,
  "step_completed": 3,
  "teacher_id": "t_abc123",
  "persona": { ... }
}
```

---

## Error Responses

All errors follow a consistent format:

```json
{
  "error": "Description of what went wrong"
}
```

| Status Code | Meaning |
|-------------|---------|
| `400` | Bad request -- missing or invalid parameters |
| `401` | Authentication required or invalid token |
| `404` | Resource not found |
| `429` | Rate limit exceeded |
| `500` | Internal server error |

---

## CORS

By default, CORS is restricted to `http://localhost:8000` and `http://127.0.0.1:8000`. Override with the `EDUAGENT_CORS_ORIGINS` environment variable (comma-separated list of origins).

Allowed methods: `GET`, `POST`. Allowed headers: `Authorization`, `Content-Type`.

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `EDUAGENT_CORS_ORIGINS` | Comma-separated allowed CORS origins | `http://localhost:8000` |
| `EDUAGENT_LOCAL_AUTH_BYPASS` | Set to `1` to skip auth for localhost requests | unset |
| `EDUAGENT_DATA_DIR` | Data directory for DB, token, and secrets | `~/.eduagent` |
| `EDUAGENT_IMPORT_ALLOW_URLS` | Comma-separated additional allowed import URLs | unset |
| `EDUAGENT_PORT` | Server port | `8080` |
