"""Synthetic recovery, provider-wire, and evidence tests; no paid calls."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import BaseModel

from clawed.agent import _call_with_native_tools
from clawed.agent_core.core import _LLMClientAdapter
from clawed.model_capabilities import output_parameters, sampling_parameters
from clawed.models import AppConfig, LLMProvider
from clawed.phases.pipeline import _run_phase
from clawed.source_manifest import capture_sources, check_quotations, render_sources
from clawed.task_queue import TaskQueue, TaskStatus, TaskType, current_task, run_worker


async def test_concurrent_tools_are_request_scoped(monkeypatch):
    import clawed.agent as agent
    original = agent.TOOL_DEFINITIONS
    seen = []
    both_started = asyncio.Event()

    async def call(messages, system, config, definitions):
        seen.append(definitions)
        if len(seen) == 2:
            both_started.set()
        await both_started.wait()
        assert agent.TOOL_DEFINITIONS is original
        return {"type": "text", "content": definitions[0]["function"]["name"]}

    monkeypatch.setattr(agent, "_call_with_native_tools", call)
    adapter = _LLMClientAdapter(AppConfig())
    results = await asyncio.gather(*[
        adapter.generate([], [{"type": "function", "function": {"name": name}}])
        for name in ("one", "two")
    ])
    assert [result["content"] for result in results] == ["one", "two"]


async def test_astra_responses_preserves_tool_reasoning(monkeypatch):
    monkeypatch.setattr("clawed.config.get_api_key", lambda provider: "synthetic-key")
    requests = []
    output = [{"type": "reasoning", "id": "r1", "encrypted_content": "opaque", "summary": []},
              {"type": "function_call", "call_id": "c1", "name": "search", "arguments": '{"query":"test"}'}]

    async def post(self, url, **kwargs):
        requests.append((url, kwargs["json"]))
        payload = {"output": output} if len(requests) == 1 else {
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "Done"}]}]}
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    config = AppConfig(provider=LLMProvider.OPENAI, openai_model="gpt-6-astra")
    definitions = [{"type": "function", "function": {"name": "search", "parameters": {"type": "object"}}}]
    first = await _call_with_native_tools([{"role": "user", "content": "Find it"}], "system", config, definitions)
    result = await _call_with_native_tools([
        {"role": "assistant", "response_output": first["response_output"]},
        {"role": "tool", "tool_call_id": "c1", "content": "found"},
    ], "system", config, definitions)
    assert result["content"] == "Done"
    assert requests[0][0].endswith("/responses")
    assert "temperature" not in requests[0][1]
    assert requests[0][1]["store"] is False
    assert requests[1][1]["input"][:2] == output
    assert requests[1][1]["input"][2]["call_id"] == "c1"


async def test_google_tools_use_google_endpoint(monkeypatch):
    monkeypatch.setattr("clawed.config.get_api_key", lambda provider: "synthetic-key")

    async def post(self, url, **kwargs):
        assert url == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        assert kwargs["json"]["model"] == "chosen-google-model"
        assert kwargs["json"]["tools"] == []
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    result = await _LLMClientAdapter(AppConfig(provider=LLMProvider.GOOGLE,
        google_model="chosen-google-model")).generate([])
    assert result["content"] == "ok"


async def test_fable_preserves_native_thinking_across_tool_turns(monkeypatch):
    import anthropic

    from clawed.agent import _anthropic_with_tools
    from clawed.llm import LLMClient

    monkeypatch.setattr("clawed.config.get_api_key", lambda provider: "synthetic-key")
    native = [
        {"type": "thinking", "thinking": "Synthetic reasoning", "signature": "opaque-signature"},
        {"type": "tool_use", "id": "call-1", "name": "search", "input": {"query": "fixture"}},
    ]

    def block(data):
        return SimpleNamespace(**data, model_dump=lambda: dict(data))

    create = AsyncMock(side_effect=[
        SimpleNamespace(content=[block(data) for data in native]),
        SimpleNamespace(content=[block({"type": "text", "text": "Tool completed"})]),
        SimpleNamespace(content=[block(native[0]), block({"type": "text", "text": "Draft"})]),
    ])
    monkeypatch.setattr(anthropic, "AsyncAnthropic", lambda **kwargs: SimpleNamespace(
        messages=SimpleNamespace(create=create)))
    config = AppConfig(provider=LLMProvider.ANTHROPIC, anthropic_model="claude-fable-5-1")
    tools = [{"type": "function", "function": {
        "name": "search", "description": "Find a fixture", "parameters": {"type": "object"}}}]
    first = await _anthropic_with_tools([{"role": "user", "content": "Find it"}], "system", config, tools)
    result = await _anthropic_with_tools([
        {"role": "assistant", "anthropic_content": first["anthropic_content"]},
        {"role": "tool", "tool_call_id": "call-1", "content": "Fixture found"},
    ], "system", config, tools)
    assert result["content"] == "Tool completed"
    second = create.await_args_list[1].kwargs
    assert second["messages"][0]["content"] == native
    assert second["messages"][1]["content"][0]["tool_use_id"] == "call-1"
    assert await LLMClient(config)._anthropic("prompt", "system", .4, 1000) == "Draft"
    assert "temperature" not in create.await_args_list[2].kwargs


async def test_vision_keeps_selected_models_and_fails_closed(monkeypatch, tmp_path):
    from clawed.image_pipeline import check_image_quality
    from clawed.llm import LLMClient

    monkeypatch.setattr("clawed.config.get_api_key", lambda provider: "synthetic-key")
    monkeypatch.delenv("OLLAMA_VISION_MODEL", raising=False)
    monkeypatch.setattr("clawed.llm.asyncio.sleep", AsyncMock())
    requests = []

    async def post(self, url, **kwargs):
        requests.append(kwargs["json"])
        return httpx.Response(429, json={}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    config = AppConfig(provider=LLMProvider.OPENROUTER, openrouter_model="openai/gpt-6-astra")
    with pytest.raises(RuntimeError, match="vision screening failed"):
        await LLMClient(config)._vision_openrouter("prompt", "image", "image/png", "", .3, 100)
    assert [req["model"] for req in requests] == ["openai/gpt-6-astra"] * 2
    assert all("temperature" not in req for req in requests)
    requests.clear()
    config = AppConfig(provider=LLMProvider.OLLAMA, ollama_model="qwen3.5:9b")
    with pytest.raises(RuntimeError, match="vision screening failed"):
        await LLMClient(config)._vision_ollama("prompt", "image", .3, 100)
    assert requests[0]["model"] == "qwen3.5:9b"
    monkeypatch.setattr("clawed.config.get_api_key", lambda provider: None)
    image = tmp_path / "fixture.png"
    image.write_bytes(b"synthetic-image" * 100)
    for provider in (LLMProvider.ANTHROPIC, LLMProvider.OPENAI, LLMProvider.GOOGLE):
        assert not await check_image_quality(image, "Synthetic", config=AppConfig(provider=provider))


async def test_concurrent_image_montages_are_isolated_and_removed(tmp_path, monkeypatch):
    from PIL import Image

    from clawed.image_pipeline import vision_filter_batch

    source = tmp_path / "fixture.png"
    Image.new("RGB", (100, 100), "green").save(source)
    paths = []
    both_started = asyncio.Event()

    async def inspect(self, **kwargs):
        path = kwargs["image_path"]
        paths.append(path)
        if len(paths) == 2:
            both_started.set()
        await both_started.wait()
        assert path.exists()
        return "#1:Y"

    monkeypatch.setattr("clawed.llm.LLMClient.generate_with_image", inspect)
    results = await asyncio.gather(*[
        vision_filter_batch([(spec, source)], config=AppConfig()) for spec in ("one", "two")])
    assert results == [{"one"}, {"two"}]
    assert len(set(paths)) == 2
    assert not any(path.exists() for path in paths)


def test_frontier_parameters_and_multilingual_evidence():
    from clawed.sanitize import sanitize_text
    for name in ("gpt-6-astra", "anthropic/claude-fable-5.1", "claude-sonnet-5"):
        assert sampling_parameters(name, .4) == {}
    assert output_parameters("gpt-6-astra", 1000) == {"max_completion_tokens": 1000}
    quote = "学生は資料を読みます。 学生阅读资料。 학생들은 자료를 읽습니다."
    assert sanitize_text(quote) == quote
    evidence = capture_sources([{"doc_title": "Synthetic multilingual fixture", "source_path": "fixture.txt",
                                 "chunk_text": quote, "metadata": {"page": 2}}])
    assert quote in render_sources(evidence)
    assert evidence[0].locator == "page: 2"
    sources = [SimpleNamespace(id="supplied", content_text=quote),
               SimpleNamespace(id="invented", content_text="An invented quotation with enough characters to check.")]
    checks = check_quotations(sources, evidence)
    assert [check.status for check in checks] == ["matched_excerpt", "needs_teacher_verification"]
    assert json.loads(evidence[0].model_dump_json())["excerpt"] == quote


def test_atomic_claim_and_worker_ownership(tmp_path):
    first, second = TaskQueue(tmp_path / "jobs.db"), TaskQueue(tmp_path / "jobs.db")
    job = first.submit(TaskType.LESSON_BUNDLE, {"topic": "Synthetic"})
    assert first.next_queued().id == job
    assert second.next_queued() is None
    second.mark_done(job, {"wrong_worker": True})
    assert first.get_status(job).status == TaskStatus.RUNNING
    first.mark_done(job, {"correct_worker": True})
    assert second.get_result(job) == {"correct_worker": True}
    first.close()
    second.close()


def test_cancel_at_completion_and_stale_recovery(tmp_path):
    queue = TaskQueue(tmp_path / "jobs.db")
    for finalize in (lambda job: queue.mark_done(job, {"ok": True}),
                     lambda job: queue.mark_failed(job, "Failed")):
        job = queue.submit(TaskType.LESSON_BUNDLE)
        queue.next_queued()
        queue.cancel(job)
        finalize(job)
        assert queue.get_status(job).status == TaskStatus.CANCELLED
    stale = queue.submit(TaskType.LESSON_BUNDLE)
    queue.next_queued()
    assert queue.recover_interrupted() == 0
    queue._get_conn().execute("UPDATE tasks SET heartbeat = 0 WHERE id = ?", (stale,))
    queue._get_conn().commit()
    assert queue.recover_interrupted() == 1
    assert queue.get_status(stale).status == TaskStatus.INTERRUPTED
    assert queue.resume(stale)
    assert queue.next_queued().id == stale
    queue.close()


async def test_cancel_running_job_without_marking_done(tmp_path, monkeypatch):
    queue = TaskQueue(tmp_path / "jobs.db")
    job = queue.submit(TaskType.LESSON_BUNDLE)
    started = asyncio.Event()

    async def execute(task):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("clawed.task_queue._execute_task", execute)
    worker = asyncio.create_task(run_worker(queue, once=True, poll_interval=.01))
    await started.wait()
    queue.cancel(job)
    await asyncio.wait_for(worker, 1)
    assert queue.get_status(job).status == TaskStatus.CANCELLED
    assert queue.get_result(job) is None
    queue.close()


class StepResult(BaseModel):
    value: str


async def test_checkpoint_survives_restart_and_invalidates_changed_model(tmp_path):
    path = tmp_path / "jobs.db"
    queue = TaskQueue(path)
    job = queue.submit(TaskType.LESSON_BUNDLE)
    queue.next_queued()
    client = SimpleNamespace(config=AppConfig(), safe_generate_json=AsyncMock(return_value=StepResult(value="saved")))
    token = current_task.set((queue, job))
    try:
        await _run_phase("skeleton", "prompt", "system", StepResult, client, "master_content")
    finally:
        current_task.reset(token)
        queue.close()

    queue = TaskQueue(path)
    token = current_task.set((queue, job))
    try:
        result = await _run_phase("skeleton", "prompt", "system", StepResult, client, "master_content")
        assert result.value == "saved"
        assert client.safe_generate_json.await_count == 1
        client.config.anthropic_model = "different-explicit-model"
        await _run_phase("skeleton", "prompt", "system", StepResult, client, "master_content")
        assert client.safe_generate_json.await_count == 2
    finally:
        current_task.reset(token)
        queue.close()


def test_jobs_api_shares_ledger_and_requires_auth(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from clawed.api.server import create_app

    client = TestClient(create_app())
    assert client.get("/jobs").status_code == 200
    response = client.post("/api/jobs", json={"topic": "Synthetic plants", "subject": "Science", "grade": "5"})
    assert response.status_code == 200
    job = response.json()["id"]
    queue = TaskQueue()
    assert queue.get_status(job).payload["topic"] == "Synthetic plants"
    assert client.post(f"/api/jobs/{job}/cancel").status_code == 200
    assert queue.get_status(job).status == TaskStatus.CANCELLED
    assert client.post(f"/api/jobs/{job}/resume").status_code == 200
    assert queue.get_status(job).status == TaskStatus.QUEUED
    assert client.get(f"/api/jobs/{job}/files/-1").status_code == 404
    monkeypatch.delenv("EDUAGENT_LOCAL_AUTH_BYPASS")
    assert client.get("/api/jobs").status_code == 401
    assert client.post(f"/api/jobs/{job}/cancel").status_code == 401
    queue.close()
