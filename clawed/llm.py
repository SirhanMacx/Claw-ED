"""Unified LLM client supporting Anthropic, OpenAI, and Ollama backends."""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from clawed.models import AppConfig, LLMProvider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from clawed.models import AdminLessonPlan, StudentPacket

logger = logging.getLogger(__name__)

_ModelT = TypeVar("_ModelT", bound=BaseModel)


class LLMClient:
    """Unified async LLM client for all supported backends."""

    def __init__(self, config: AppConfig | None = None):
        self.config = config or AppConfig.load()

    async def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        demo_hint: str = "",
        json_mode: bool = False,
    ) -> str:
        """Generate text from the configured LLM backend.

        In demo mode (no API key configured), returns a canned sample lesson
        so teachers can try Claw-ED without any LLM credentials.

        Automatically injects workspace context (identity, soul, memory)
        into the system prompt when available.
        """
        from clawed.demo import is_demo_mode

        if is_demo_mode(config=self.config):
            return self._demo_response(prompt, demo_hint=demo_hint)

        # Inject workspace context into system prompt
        system = self._enrich_system_prompt(system, prompt=prompt)

        from clawed.sanitize import sanitize_text

        if self.config.provider == LLMProvider.ANTHROPIC:
            raw = await self._anthropic(prompt, system, temperature, max_tokens)
        elif self.config.provider == LLMProvider.OPENAI:
            raw = await self._openai(prompt, system, temperature, max_tokens)
        elif self.config.provider == LLMProvider.OLLAMA:
            raw = await self._ollama(prompt, system, temperature, max_tokens, json_mode)
        elif self.config.provider == LLMProvider.GOOGLE:
            raw = await self._google(prompt, system, temperature, max_tokens)
        elif self.config.provider == LLMProvider.OPENROUTER:
            raw = await self._openrouter(prompt, system, temperature, max_tokens)
        else:
            raise ValueError(f"Unknown provider: {self.config.provider}")
        return sanitize_text(raw)

    async def generate_stream(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        """Stream a text completion token-by-token.

        Yields incremental text chunks as the model produces them, so the UI
        can render the answer live. OpenRouter and Ollama stream natively;
        other providers fall back to a single yield of the full result.
        """
        from clawed.demo import is_demo_mode

        if is_demo_mode(config=self.config):
            yield self._demo_response(prompt, demo_hint="")
            return

        system = self._enrich_system_prompt(system, prompt=prompt)
        provider = self.config.provider
        if provider == LLMProvider.OPENROUTER:
            async for chunk in self._openrouter_stream(
                prompt, system, temperature, max_tokens
            ):
                yield chunk
            return
        if provider == LLMProvider.OLLAMA:
            async for chunk in self._ollama_stream(
                prompt, system, temperature, max_tokens
            ):
                yield chunk
            return

        # Providers without a streaming path here: emit the full result once.
        from clawed.sanitize import sanitize_text

        if provider == LLMProvider.ANTHROPIC:
            raw = await self._anthropic(prompt, system, temperature, max_tokens)
        elif provider == LLMProvider.OPENAI:
            raw = await self._openai(prompt, system, temperature, max_tokens)
        elif provider == LLMProvider.GOOGLE:
            raw = await self._google(prompt, system, temperature, max_tokens)
        else:
            raise ValueError(f"Unknown provider: {provider}")
        yield sanitize_text(raw)

    async def _openrouter_stream(
        self, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> AsyncIterator[str]:
        from clawed.config import get_api_key

        api_key = get_api_key("openrouter")
        if not api_key:
            raise OSError(
                "OpenRouter API key not found. Get one at https://openrouter.ai/keys"
            )
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        base_url = getattr(
            self.config, "openrouter_base_url", "https://openrouter.ai/api/v1"
        )
        async with httpx.AsyncClient(timeout=7200.0) as client, client.stream(
            "POST",
            f"{base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/SirhanMacx/Claw-ED",
                "X-Title": "Claw-ED",
            },
            json={
                "model": self.config.openrouter_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
                # Quick co-teacher help should feel instant. Tell reasoning
                # models (e.g. minimax-m3) to skip the long chain-of-thought
                # so the answer streams right away. Ignored by non-reasoning
                # models. (OpenRouter unified `reasoning` control.)
                "reasoning": {"enabled": False},
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                choices = obj.get("choices") or [{}]
                delta = choices[0].get("delta", {}).get("content")
                if delta:
                    yield str(delta)

    async def _ollama_stream(
        self, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> AsyncIterator[str]:
        api_key = getattr(self.config, "ollama_api_key", None) or os.environ.get(
            "OLLAMA_API_KEY"
        )
        headers = {}
        if api_key and api_key != "ollama":
            headers["Authorization"] = f"Bearer {api_key}"
        base = self.config.ollama_base_url.rstrip("/")
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        num_ctx = getattr(self.config, "ollama_num_ctx", 0) or 8192
        async with httpx.AsyncClient(timeout=600.0) as client, client.stream(
            "POST",
            f"{base}/api/chat",
            headers=headers,
            json={
                "model": self.config.ollama_model,
                "messages": messages,
                "stream": True,
                "think": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "num_ctx": num_ctx,
                },
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                chunk = obj.get("message", {}).get("content")
                if chunk:
                    yield str(chunk)

    async def generate_with_image(
        self,
        prompt: str,
        image_path: str | os.PathLike[str],
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 150,
    ) -> str:
        """Send an image + text prompt to a vision-capable LLM.

        Used for image quality filtering — the vision model evaluates whether
        a fetched image is educationally appropriate, clear, and relevant.

        Falls back to text-only generate() if the provider doesn't support
        vision, returning a permissive "GOOD" to avoid blocking images.
        """
        import base64
        from pathlib import Path

        path = Path(image_path)
        if not path.exists():
            return "REJECT: Image file not found"

        data = path.read_bytes()
        if len(data) < 1000:
            return "REJECT: Image too small"

        b64 = base64.standard_b64encode(data).decode("utf-8")

        # Detect MIME type
        if path.suffix.lower() in (".jpg", ".jpeg"):
            media_type = "image/jpeg"
        elif path.suffix.lower() == ".png":
            media_type = "image/png"
        elif path.suffix.lower() == ".gif":
            media_type = "image/gif"
        elif path.suffix.lower() == ".webp":
            media_type = "image/webp"
        else:
            media_type = "image/jpeg"  # Default assumption

        if self.config.provider == LLMProvider.ANTHROPIC:
            return await self._vision_anthropic(prompt, b64, media_type, system, temperature, max_tokens)
        if self.config.provider == LLMProvider.OPENAI:
            return await self._vision_openai(prompt, b64, media_type, system, temperature, max_tokens)
        if self.config.provider == LLMProvider.OLLAMA:
            return await self._vision_ollama(prompt, b64, temperature, max_tokens)

        # Providers without vision support
        return "GOOD"

    async def _vision_anthropic(
        self,
        prompt: str,
        b64: str,
        media_type: str,
        system: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Anthropic vision API call."""
        try:
            import anthropic

            from clawed.config import get_api_key, is_anthropic_oauth_token

            api_key = get_api_key("anthropic")
            if not api_key:
                return "GOOD"  # No key = permissive

            is_oauth = is_anthropic_oauth_token(api_key)
            client: Any
            if is_oauth:
                client = anthropic.Anthropic(
                    auth_token=api_key,
                    default_headers={
                        "anthropic-beta": "oauth-2025-04-20",
                        "x-app": "cli",
                    },
                )
            else:
                client = anthropic.Anthropic(api_key=api_key)

            msg = client.messages.create(
                model=self.config.anthropic_model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system or "",
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
            return str(msg.content[0].text)
        except Exception as e:
            logger.debug("Vision check failed (Anthropic): %s", e)
            return "GOOD"  # Permissive on failure

    async def _vision_openai(
        self,
        prompt: str,
        b64: str,
        media_type: str,
        system: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """OpenAI vision API call."""
        try:
            from clawed.config import get_api_key

            api_key = get_api_key("openai")
            if not api_key:
                return "GOOD"

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": self.config.openai_model,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "messages": [
                            {"role": "system", "content": system} if system else None,
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:{media_type};base64,{b64}",
                                            "detail": "low",
                                        },
                                    },
                                ],
                            },
                        ],
                    },
                )
                resp.raise_for_status()
                return str(resp.json()["choices"][0]["message"]["content"])
        except Exception as e:
            logger.debug("Vision check failed (OpenAI): %s", e)
            return "GOOD"

    async def _vision_ollama(
        self,
        prompt: str,
        b64: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Ollama vision API call with auto-detection of vision model."""
        try:
            # Pick a vision-capable model. Allow override via
            # OLLAMA_VISION_MODEL env var.
            import os as _os
            vision_model = _os.environ.get("OLLAMA_VISION_MODEL", "")
            if not vision_model:
                # Auto-detect: query /api/tags and pick a vision model
                async with httpx.AsyncClient(timeout=10) as c:
                    tags_resp = await c.get(
                        f"{self.config.ollama_base_url.rstrip('/')}/api/tags"
                    )
                if tags_resp.status_code == 200:
                    models = tags_resp.json().get("models", [])
                    # Probe capabilities for each, in priority order
                    vision_candidates = []
                    for m in models:
                        name = m.get("name", "")
                        # Known vision model families
                        if any(k in name.lower() for k in [
                            "gemma4", "gemma3", "llava", "qwen2.5-vl",
                            "minicpm-v", "cogvlm", "boris",
                        ]):
                            vision_candidates.append(name)
                    if vision_candidates:
                        # Prefer gemma4 (Google vision), then boris
                        for pref in ["gemma4:latest", "gemma4", "boris:latest", "boris"]:
                            for cand in vision_candidates:
                                if cand.startswith(pref):
                                    vision_model = cand
                                    break
                            if vision_model:
                                break
                        if not vision_model:
                            vision_model = vision_candidates[0]

            if not vision_model:
                logger.debug(
                    "No vision-capable Ollama model found. Install one "
                    "with 'ollama pull gemma3' or similar."
                )
                return "GOOD"

            logger.debug("Using Ollama vision model: %s", vision_model)
            base = self.config.ollama_base_url.rstrip("/")
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{base}/api/generate",
                    json={
                        "model": vision_model,
                        "prompt": prompt,
                        "images": [b64],
                        "stream": False,
                        # CRITICAL: disable thinking mode. Gemma 4 and
                        # other reasoning models will consume the entire
                        # token budget on internal thoughts and return
                        # an empty response otherwise.
                        "think": False,
                        "options": {
                            "temperature": temperature,
                            "num_predict": max_tokens,
                        },
                    },
                )
                if resp.status_code != 200:
                    logger.debug(
                        "Ollama vision returned %d: %s",
                        resp.status_code, resp.text[:200],
                    )
                    return "GOOD"
                data = resp.json()
                response_text: str = str(data.get("response", "") or "").strip()
                if not response_text:
                    logger.debug(
                        "Ollama vision empty response. eval_count=%s think=%s",
                        data.get("eval_count"),
                        bool(data.get("thinking")),
                    )
                    return "GOOD"
                return response_text
        except Exception as e:
            logger.debug("Vision check failed (Ollama): %s", e)
            return "GOOD"

    @staticmethod
    def _demo_response(prompt: str, demo_hint: str = "") -> str:
        """Return a canned demo response based on schema hint or prompt keywords."""
        from clawed.demo import load_demo

        HINT_TO_FIXTURE = {  # noqa: N806
            "MasterContent": "master_content",
            "DailyLesson": "lesson_social_studies_g8",
            "UnitPlan": "unit_plan",
            "Quiz": "quiz",
            "Rubric": "rubric",
            "YearMap": "year_map",
            "FormativeAssessment": "formative_assessment",
            "SummativeAssessment": "assessment",
            "DBQAssessment": "assessment",
            "LessonMaterials": "lesson_materials",
            "PacingGuide": "pacing_guide",
        }
        if demo_hint and demo_hint in HINT_TO_FIXTURE:
            data = load_demo(HINT_TO_FIXTURE[demo_hint])
            return json.dumps(data, indent=2)

        # Keep existing keyword fallback below
        prompt_lower = prompt.lower()
        if "assessment" in prompt_lower or "dbq" in prompt_lower:
            data = load_demo("assessment")
        elif "unit" in prompt_lower:
            data = load_demo("unit_plan")
        elif "science" in prompt_lower:
            data = load_demo("lesson_science_g6")
        else:
            data = load_demo("lesson_social_studies_g8")
        return json.dumps(data, indent=2)

    def _enrich_system_prompt(self, system: str, prompt: str = "") -> str:
            """Append workspace context and improvement context to the system prompt.

            This injects teacher identity, teaching philosophy, memory, and
            today's notes so the LLM has full context about the teacher.
            Additionally injects learned patterns from the feedback loop
            (memory engine) so generation quality improves over time.
            Fails silently if workspace is not initialized.

            Args:
            system: The current system prompt.
            prompt: The user prompt text — used to detect the subject being
                generated so multi-subject teachers get the right feedback.
            """
            try:
                from clawed.workspace import inject_workspace_context

                ws_context = inject_workspace_context()
                if ws_context:
                    system = (system + ws_context) if system else ws_context
            except ImportError:
                pass  # Workspace not available -- that's fine

            # Inject improvement context from the memory engine (feedback loop).
            # Detect subject from the prompt text so multi-subject teachers get
            # correctly filtered feedback (not always subjects[0]).
            try:
                from clawed.memory_engine import build_improvement_context

                subject = self._detect_subject_from_prompt(prompt)
                improvement_ctx = build_improvement_context(subject=subject)
                if improvement_ctx:
                    system = (system + "\n" + improvement_ctx) if system else improvement_ctx
            except ImportError:
                pass  # Memory engine not available -- that's fine

            return system

    def _detect_subject_from_prompt(self, prompt: str) -> str:
        """Detect the subject being generated from the prompt text.

        Checks for explicit subject mentions, then falls back to
        teacher_profile.subjects[0].
        """
        if not prompt:
            return self._default_subject()

        lower = prompt.lower()
        # Check for explicit subject keywords in the prompt
        subject_keywords = {
            "history": "History",
            "social studies": "Social Studies",
            "science": "Science",
            "biology": "Science",
            "chemistry": "Science",
            "physics": "Science",
            "math": "Math",
            "algebra": "Math",
            "geometry": "Math",
            "calculus": "Math",
            "english": "ELA",
            "ela": "ELA",
            "language arts": "ELA",
            "literature": "ELA",
            "reading": "ELA",
            "writing": "ELA",
            "art": "Art",
            "music": "Music",
            "physical education": "PE",
            "computer science": "Computer Science",
            "spanish": "Foreign Language",
            "french": "Foreign Language",
        }
        for keyword, subject in subject_keywords.items():
            if keyword in lower:
                return subject

        return self._default_subject()

    def _default_subject(self) -> str:
        """Get the first subject from teacher profile, or empty string."""
        if hasattr(self.config, "teacher_profile") and self.config.teacher_profile:
            subjects = getattr(self.config.teacher_profile, "subjects", [])
            return subjects[0] if subjects else ""
        return ""

    async def generate_json(
        self,
            prompt: str,
            system: str = "",
            temperature: float = 0.4,
            max_tokens: int = 8192,
            demo_hint: str = "",
    ) -> dict[str, Any]:
            """Generate and parse a JSON response from the LLM."""
            raw = await self.generate(
                prompt, system, temperature, max_tokens,
                demo_hint=demo_hint, json_mode=True,
            )
            if not raw or not raw.strip():
                raise ValueError(
                    "LLM returned empty output. This model may not support "
                    "structured JSON generation. Try a larger model or different provider."
                )
            # Strip <think>...</think> blocks (common in reasoning models like Qwen)
            cleaned = raw.strip()
            import re
            cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                # Drop first line (```json or ```) and last line (```)
                lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned = "\n".join(lines)
            # Step 1: try strict JSON parsing
            try:
                parsed: Any = json.loads(cleaned)
                return parsed  # type: ignore[no-any-return]
            except json.JSONDecodeError:
                pass

            # Step 2: fall back to json_repair for truncated/malformed JSON
            import json_repair

            try:
                result = json_repair.loads(cleaned)
                if isinstance(result, (dict, list)):
                    return result  # type: ignore[return-value]
            except Exception:
                logger.debug("operation_failed", exc_info=True)

            # Step 3: raise a clear error with raw LLM output for debugging
            preview = raw[:500] + ("..." if len(raw) > 500 else "")
            raise ValueError(
                f"LLM returned unparseable JSON. Raw output:\n{preview}"
            )

    async def safe_generate_json(
            self,
            prompt: str,
            model_class: type[_ModelT],
            max_retries: int = 1,
            demo_hint: str = "",
            **kwargs: Any,
    ) -> _ModelT:
            """Generate JSON and parse into a Pydantic model with automatic retry.

            On validation failure, retries once with the error appended to the prompt.
            On second failure, raises a clear RuntimeError (not a traceback).
            """
            demo_hint = demo_hint or model_class.__name__
            last_error = ""
            for attempt in range(max_retries + 1):
                current_prompt = prompt
                if attempt > 0:
                    current_prompt = prompt + f"\n\nPREVIOUS ATTEMPT FAILED. Fix these errors:\n{last_error}"
                raw = await self.generate_json(current_prompt, demo_hint=demo_hint, **kwargs)
                try:
                    return model_class.model_validate(raw)
                except ValidationError as e:
                    last_error = str(e)
                    if attempt >= max_retries:
                        raise RuntimeError(
                            f"Generation failed after {max_retries + 1} attempts. "
                            f"The AI returned data that doesn't match the expected format. "
                            f"Try again or use a different AI model.\n"
                            f"Validation errors: {last_error[:500]}"
                        ) from e
            raise RuntimeError("unreachable")

    async def generate_student_handout(
            self,
            lesson_json: str,
            persona_context: str = "",
            subject: str = "",
            grade: str = "",
    ) -> str:
            """Generate a student handout as a first-class LLM output.

            Sends the completed lesson plan as context and asks the LLM to produce
            the student-facing materials. This is NOT regex extraction from the
            lesson --- it's a separate generation that understands what the lesson
            references and creates matching materials.
            """
            system = (
                "You are creating a student handout for a lesson. The handout is what "
                "students receive --- it must be self-contained, printable, and include "
                "everything referenced in the lesson plan.\n\n"
                f"{persona_context}\n" if persona_context else ""
            )

            prompt = (
                f"Here is the complete lesson plan:\n\n{lesson_json}\n\n"
                "Create a student handout that includes ALL of these sections "
                "(skip any that don't apply to this lesson):\n\n"
                "1. **Header**: Lesson title, date line, Name: _________ Period: _____\n"
                "2. **Do Now**: The student-facing prompt only (not the teacher script), "
                "with lined space for writing\n"
                "3. **Vocabulary**: Key terms with definitions extracted from the lesson. "
                "Format: Term --- definition\n"
                "4. **Primary Source Excerpts**: Any quoted passages referenced in the lesson, "
                "with full attribution (author, date, title). Quote them completely.\n"
                "5. **Graphic Organizer**: If the lesson references an organizer (source analysis, "
                "comparison chart, etc.), create the actual table with column headers and empty rows. "
                "Include clear instructions.\n"
                "6. **Activity Instructions**: Student-facing version of guided/independent practice\n"
                "7. **Exit Ticket**: Numbered questions with lined answer space\n\n"
                "Return the handout as structured JSON with these keys:\n"
                '{"title": "...", "do_now": "...", "vocabulary": [{"term": "...", "definition": "..."}], '
                '"source_excerpts": [{"text": "...", "attribution": "..."}], '
                '"organizer": {"title": "...", "columns": ["..."], "instructions": "...", "num_rows": 4}, '
                '"activity_instructions": "...", '
                '"exit_ticket_questions": ["...", "..."]}\n\n'
                "If the lesson references visual materials (paintings, maps, diagrams, "
                "charts, images), include an 'image_descriptions' key:\n"
                '"image_descriptions": [{"description": "...", "context": "where this appears in the lesson"}]\n'
                "These help the teacher know what to display on the projector."
            )

            return await self.generate(prompt, system=system, temperature=0.4, max_tokens=4096)

    async def generate_student_packet(
            self,
            lesson_json: str,
            persona_context: str = "",
    ) -> StudentPacket:
            """Generate a structured student packet from a completed lesson.

            Returns a validated StudentPacket model with fill-in-the-blank guided
            notes, station sections with primary source text and analysis questions,
            graphic organizer tables, and exit ticket with sentence starters.
            """
            from pathlib import Path

            from clawed.models import StudentPacket

            prompt_path = Path(__file__).parent / "prompts" / "student_packet.txt"
            prompt_template = prompt_path.read_text(encoding="utf-8")

            # Build handout style block from persona context
            import re as _re
            handout_style = ""
            if persona_context:
                hs_match = _re.search(
                    r"=== Handout Style ===\n(.+?)(?:\n===|\Z)",
                    persona_context, _re.DOTALL,
                )
                if hs_match:
                    handout_style = hs_match.group(1).strip()

            if handout_style:
                handout_style_block = (
                    f"This teacher's handout style: {handout_style}. "
                    "Match this format. If the teacher uses guided notes, include them. "
                    "If they use graphic organizers, lead with those. If they prefer "
                    "dense source packets, make the sources the centerpiece. "
                    "Don't impose a format the teacher wouldn't recognize as their own."
                )
            else:
                handout_style_block = (
                    "No specific handout style detected — use the default format below."
                )

            prompt = (
                prompt_template
                .replace("{lesson_json}", lesson_json[:6000])
                .replace("{persona}", persona_context)
                .replace("{handout_style_block}", handout_style_block)
            )

            system = (
                "You are creating a student packet — a 4-6 page workbook that students "
                "complete during class. It must include fill-in-the-blank guided notes, "
                "full primary source texts with analysis questions, a graphic organizer "
                "table, and an exit ticket with sentence starters.\n"
                "Respond only with valid JSON. Do NOT use XML tags or markdown."
            )

            return await self.safe_generate_json(
                prompt=prompt,
                model_class=StudentPacket,
                system=system,
                temperature=0.4,
                max_tokens=8192,
            )

    async def generate_admin_plan(
            self,
            lesson_json: str,
            persona_context: str = "",
    ) -> AdminLessonPlan:
            """Generate an administrator-ready lesson plan from a completed lesson.

            Returns a validated AdminLessonPlan with per-section teacher/student
            actions, observer look-fors, anticipated responses, and teacher
            content knowledge.
            """
            from pathlib import Path

            from clawed.models import AdminLessonPlan

            prompt_path = Path(__file__).parent / "prompts" / "admin_lesson_plan.txt"
            prompt_template = prompt_path.read_text(encoding="utf-8")
            prompt = (
                prompt_template
                .replace("{lesson_json}", lesson_json[:6000])
                .replace("{persona}", persona_context)
            )

            system = (
                "You are creating an observation-ready lesson plan for an administrator. "
                "It must include per-section teacher actions (with scripted language), "
                "student actions, observer look-fors, differentiation, anticipated "
                "student responses and misconceptions, and teacher content knowledge.\n"
                "Respond only with valid JSON. Do NOT use XML tags or markdown."
            )

            return await self.safe_generate_json(
                prompt=prompt,
                model_class=AdminLessonPlan,
                system=system,
                temperature=0.3,
                max_tokens=6000,
            )

    async def review_lesson_package(
            self,
            lesson_json: str,
            standards_present: bool,
            has_handout: bool,
            has_slideshow: bool,
    ) -> dict[str, Any]:
            """Self-review a lesson package against observation-ready standards.

            Returns a dict with 'passed' (bool) and 'issues' (list of strings).
            Fails closed: any exception returns passed=False (NLAH Section 3, Stage 4).
            """
            try:
                prompt = (
                    f"Review this lesson package against observation-ready quality standards.\n\n"
                    f"Lesson:\n{lesson_json[:3000]}\n\n"
                    f"Package status: standards={'yes' if standards_present else 'MISSING'}, "
                    f"handout={'yes' if has_handout else 'MISSING'}, "
                    f"slideshow={'yes' if has_slideshow else 'MISSING'}\n\n"
                    "Check these standards:\n"
                    "1. Do all section times add up to a full class period (42-45 min)?\n"
                    "2. Are specific standards codes listed (not just 'aligned to standards')?\n"
                    "3. Is vocabulary defined for all content-specific terms?\n"
                    "4. Are there checks for understanding every 7-10 minutes?\n"
                    "5. Are all referenced materials self-contained (no phantom handouts)?\n"
                    "6. Is the Do Now completable in 5 minutes?\n"
                    "7. Are transitions scripted between sections?\n\n"
                    'Return JSON: {"passed": true/false, "issues": ["issue 1", "issue 2"]}'
                )
                raw = await self.generate(prompt, temperature=0.2, max_tokens=1000)
                cleaned = raw.strip()
                if cleaned.startswith("```"):
                    lines = cleaned.split("\n")[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    cleaned = "\n".join(lines)
                result: dict[str, Any] = json.loads(cleaned)
                if "passed" not in result:
                    return {"passed": False, "issues": ["LLM response missing 'passed' field"]}
                return result
            except Exception as e:
                logger.warning("REVIEW_FAILED: %s", e)
                return {"passed": False, "issues": [f"Quality review failed: {type(e).__name__}"]}

    # ── Anthropic ────────────────────────────────────────────────────────

    async def _anthropic(
            self, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> str:
            import anthropic

            from clawed.config import get_api_key, is_anthropic_oauth_token

            api_key = get_api_key("anthropic")
            if not api_key:
                raise OSError(
                    "Anthropic API key not found. Set ANTHROPIC_API_KEY, store via "
                    "keyring, or run: clawed config set-model ollama"
                )

            # Use the official SDK — handles OAuth (auth_token) and API keys properly
            is_oauth = is_anthropic_oauth_token(api_key)
            if is_oauth:
                client = anthropic.Anthropic(
                    auth_token=api_key,
                    default_headers={
                        "anthropic-beta": "oauth-2025-04-20",
                        "x-app": "cli",
                    },
                    max_retries=3,
                )
            else:
                client = anthropic.Anthropic(
                    api_key=api_key,
                    max_retries=3,
                )

            try:
                kwargs: dict[str, Any] = {
                    "model": self.config.anthropic_model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}],
                }
                if system:
                    kwargs["system"] = system

                msg = client.messages.create(**kwargs)
                return str(msg.content[0].text)

            except anthropic.AuthenticationError as e:
                raise OSError(
                    "Invalid API key or OAuth token. Check with: clawed debug"
                ) from e
            except anthropic.RateLimitError as e:
                raise RuntimeError(
                    "The AI service is busy right now. Wait a minute and try again."
                ) from e
            except anthropic.APIConnectionError as e:
                raise ConnectionError(
                    "Could not connect to the Anthropic API.\n"
                    "Check your internet connection and try again."
                ) from e

    # ── OpenAI ───────────────────────────────────────────────────────────

    async def _openai(
            self, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> str:
            from clawed.config import get_api_key

            api_key = get_api_key("openai")
            if not api_key:
                raise OSError(
                    "OpenAI API key not found. Set OPENAI_API_KEY, store via "
                    "keyring, or run: clawed config set-model ollama"
                )
            messages: list[dict[str, str]] = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            try:
                async with httpx.AsyncClient(timeout=7200.0) as client:
                    resp = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-type": "application/json",
                        },
                        json={
                            "model": self.config.openai_model,
                            "messages": messages,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    choices = data.get("choices", [])
                    if not choices:
                        raise RuntimeError("OpenAI returned an empty response (content may have been filtered)")
                    return str(choices[0].get("message", {}).get("content", "") or "")
            except httpx.ConnectError as exc:
                raise ConnectionError(
                    "Could not connect to the OpenAI API.\n"
                    "Check your internet connection and try again."
                ) from exc
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    raise OSError(
                        "Invalid OPENAI_API_KEY. Check your key at https://platform.openai.com"
                    ) from e
                raise

    # ── OpenRouter ───────────────────────────────────────────────────────

    async def _openrouter(
            self, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> str:
            """OpenRouter — OpenAI-compatible API at openrouter.ai/api/v1."""
            from clawed.config import get_api_key

            api_key = get_api_key("openrouter")
            if not api_key:
                raise OSError(
                    "OpenRouter API key not found. Get one at https://openrouter.ai/keys"
                )
            messages: list[dict[str, str]] = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            base_url = getattr(self.config, "openrouter_base_url", "https://openrouter.ai/api/v1")

            try:
                async with httpx.AsyncClient(timeout=7200.0) as client:
                    resp = await client.post(
                        f"{base_url.rstrip('/')}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-type": "application/json",
                            "HTTP-Referer": "https://github.com/SirhanMacx/Claw-ED",
                            "X-Title": "Claw-ED",
                        },
                        json={
                            "model": self.config.openrouter_model,
                            "messages": messages,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    choices = data.get("choices", [])
                    if not choices:
                        raise RuntimeError("OpenRouter returned an empty response (no choices)")
                    return str(choices[0].get("message", {}).get("content", "") or "")
            except httpx.ConnectError as exc:
                raise ConnectionError(
                    "Could not connect to OpenRouter. Check your internet connection."
                ) from exc
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    raise OSError(
                        "Invalid OpenRouter API key. Check at https://openrouter.ai/keys"
                    ) from e
                raise

    # ── Ollama ───────────────────────────────────────────────────────────

    async def _ollama(
            self, prompt: str, system: str, temperature: float, max_tokens: int,
            json_mode: bool = False,
    ) -> str:
            # Support both local Ollama (no auth) and Ollama Cloud (Bearer token)
            api_key = getattr(self.config, "ollama_api_key", None) or os.environ.get("OLLAMA_API_KEY")
            headers = {}
            if api_key and api_key != "ollama":
                headers["Authorization"] = f"Bearer {api_key}"

            # Ollama Cloud uses OpenAI-compatible API; local uses /api/generate
            from clawed.config import is_ollama_cloud

            base = self.config.ollama_base_url.rstrip("/")
            is_cloud = is_ollama_cloud(base)
            model = self.config.ollama_model

            try:
                if is_cloud:
                    # Use OpenAI-compatible endpoint for cloud
                    messages = []
                    if system:
                        messages.append({"role": "system", "content": system})
                    messages.append({"role": "user", "content": prompt})
                    async with httpx.AsyncClient(timeout=600.0, follow_redirects=True) as client:
                        # Normalize: strip trailing slashes, append /v1 exactly once
                        cloud_base = base.rstrip("/")
                        if not cloud_base.endswith("/v1"):
                            cloud_base = f"{cloud_base}/v1"
                        resp = await client.post(
                            f"{cloud_base}/chat/completions",
                            headers=headers,
                            json={
                                "model": model,
                                "messages": messages,
                                "temperature": temperature,
                                "max_tokens": max_tokens,
                                "stream": False,
                            },
                        )
                        if resp.status_code == 404:
                            raise ConnectionError(
                                f"Ollama model '{model}' not found on the cloud.\n"
                                f"Check available models at https://ollama.com/library"
                            )
                        resp.raise_for_status()
                        data = resp.json()
                        choices = data.get("choices", [])
                        if not choices:
                            raise RuntimeError("Ollama Cloud returned an empty response")
                        return str(choices[0].get("message", {}).get("content", "") or "")
                else:
                    # Local Ollama: use the chat endpoint so the model's chat
                    # template is applied. Modern instruct/reasoning models
                    # (Gemma 4, Qwen, etc.) return an EMPTY completion from the
                    # raw /api/generate endpoint because the template isn't
                    # applied; /api/chat fixes that. We also disable thinking
                    # mode ("think": False) for fast, direct output — mirroring
                    # the vision path — so a local 12B model answers in seconds
                    # instead of spending hundreds of tokens reasoning aloud.
                    messages = []
                    if system:
                        messages.append({"role": "system", "content": system})
                    messages.append({"role": "user", "content": prompt})
                    # Cap the context window. Some local models (e.g. Gemma 4)
                    # ship a 128K default num_ctx; loading that KV cache is slow
                    # and memory-hungry on consumer hardware. 8K is ample for a
                    # persona + instructions + a generation, and keeps a local
                    # 12B responsive. Overridable via config.ollama_num_ctx.
                    num_ctx = getattr(self.config, "ollama_num_ctx", 0) or 8192
                    payload: dict[str, Any] = {
                        "model": model,
                        "messages": messages,
                        "stream": False,
                        "think": False,
                        "options": {
                            "temperature": temperature,
                            "num_predict": max_tokens,
                            "num_ctx": num_ctx,
                        },
                    }
                    if json_mode:
                        # Constrain decoding to valid JSON. This eliminates
                        # parse failures and the costly validate-then-retry
                        # round-trip, which roughly halves wall-clock time for
                        # structured generation on a local model.
                        payload["format"] = "json"
                    async with httpx.AsyncClient(timeout=600.0) as client:
                        resp = await client.post(
                            f"{base}/api/chat",
                            headers=headers,
                            json=payload,
                        )
                        if resp.status_code == 404:
                            # Parse Ollama's error body for details
                            try:
                                err_body = resp.json()
                                err_msg = err_body.get("error", "")
                            except (json.JSONDecodeError, KeyError):
                                err_msg = ""
                            raise ConnectionError(
                                f"Ollama model '{model}' not installed.\n"
                                f"Run: ollama pull {model}"
                                + (f"\n\nOllama says: {err_msg}" if err_msg else "")
                            )
                        resp.raise_for_status()
                        data = resp.json()
                        content = str(
                            data.get("message", {}).get("content", "") or ""
                        )
                        # Belt-and-suspenders: some builds ignore think=False and
                        # still emit a <think>…</think> preamble — strip it.
                        import re as _re

                        content = _re.sub(
                            r"<think>.*?</think>", "", content, flags=_re.DOTALL
                        ).strip()
                        return content
            except httpx.ConnectError as exc:
                raise ConnectionError(
                    "Could not connect to Ollama.\n"
                    "Install from https://ollama.com and make sure it's running."
                ) from exc

    # ── Google Gemini ────────────────────────────────────────────────────

    async def _google(
            self, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> str:
            """Call Google Gemini API via API key."""
            from clawed.auth.google_auth import get_google_api_key

            api_key = get_google_api_key()
            if not api_key:
                raise OSError(
                    "No Google API key found. Get a free key at "
                    "https://aistudio.google.com/apikey and set GOOGLE_API_KEY, "
                    "or run `clawed setup --reset` to configure."
                )

            model = self.config.google_model
            base_url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent"
            )

            params = {"key": api_key}
            headers: dict[str, str] = {"Content-Type": "application/json"}

            # Build contents
            contents: list[dict[str, Any]] = []
            if system:
                contents.append({"role": "user", "parts": [{"text": system}]})
                contents.append({"role": "model", "parts": [{"text": "Understood."}]})
            contents.append({"role": "user", "parts": [{"text": prompt}]})

            body: dict[str, Any] = {
                "contents": contents,
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                },
            }

            try:
                async with httpx.AsyncClient(timeout=7200.0) as client:
                    resp = await client.post(
                        base_url, params=params, headers=headers, json=body,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if not candidates:
                        raise RuntimeError("Gemini returned an empty response (content may have been filtered)")
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if not parts:
                        reason = candidates[0].get("finishReason", "unknown")
                        raise RuntimeError(f"Gemini blocked this request (reason: {reason})")
                    return str(parts[0].get("text", "") or "")
            except httpx.ConnectError as exc:
                raise ConnectionError(
                    "Could not connect to the Google Gemini API.\n"
                    "Check your internet connection and try again."
                ) from exc
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    raise OSError(
                        "Google credentials expired or invalid.\n"
                        "Run `clawed setup --reset` to re-authenticate."
                    ) from e
                raise
