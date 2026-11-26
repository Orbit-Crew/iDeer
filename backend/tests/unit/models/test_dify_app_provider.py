"""Tests for the Dify-style app service API provider (deerflow.models.dify_app_provider).

Covers the integration contract for app-level chat APIs (e.g. the 临空智言
"档案全文智能检索" chatflow): stateless message flattening into a single
``query``, Dify SSE event translation, terminal usage mapping, error events,
request headers/payload, and graceful tool-binding degradation.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGenerationChunk
from langchain_core.runnables import RunnableBinding

from deerflow.models.dify_app_provider import DifyAppChatModel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_model(**overrides) -> DifyAppChatModel:
    defaults = dict(base_url="https://10.20.10.88/v1", api_key="test-key", email="tester@example.com", model="linkong-archive-qa")
    defaults.update(overrides)
    return DifyAppChatModel(**defaults)


def _make_sse_lines(events: list[dict]) -> list[str]:
    lines = []
    for event in events:
        lines.append(f"data: {json.dumps(event)}")
        lines.append("")  # blank line separator
    return lines


def _make_stream_response(events: list[dict]) -> MagicMock:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.is_error = False
    mock_response.raise_for_status = MagicMock()
    mock_response.iter_lines = MagicMock(side_effect=lambda: iter(_make_sse_lines(events)))
    return mock_response


def _patch_sync_stream(events: list[dict]):
    """Patch httpx.Client in the provider module, capturing call kwargs."""
    captured = {}
    mock_response = _make_stream_response(events)
    stream_ctx = MagicMock()
    stream_ctx.__enter__ = MagicMock(return_value=mock_response)
    stream_ctx.__exit__ = MagicMock(return_value=False)
    mock_client = MagicMock()

    def fake_stream(method, url, headers=None, json=None, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json
        return stream_ctx

    mock_client.stream = MagicMock(side_effect=fake_stream)
    client_ctx = MagicMock()
    client_ctx.__enter__ = MagicMock(return_value=mock_client)
    client_ctx.__exit__ = MagicMock(return_value=False)

    def fake_client_cls(*args, **kwargs):
        captured["client_kwargs"] = kwargs
        return client_ctx

    return patch("deerflow.models.dify_app_provider.httpx.Client", side_effect=fake_client_cls), captured


class _FakeAsyncStreamResponse:
    def __init__(self, lines: list[str]):
        self._lines = lines

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeAsyncStreamCtx:
    def __init__(self, response: _FakeAsyncStreamResponse):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *exc):
        return False


def _patch_async_stream(events: list[dict]):
    lines = _make_sse_lines(events)
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.stream = MagicMock(return_value=_FakeAsyncStreamCtx(_FakeAsyncStreamResponse(lines)))
    return patch("deerflow.models.dify_app_provider.httpx.AsyncClient", return_value=mock_client)


_CHAT_EVENTS = [
    {"event": "workflow_started", "task_id": "t1", "data": {"id": "wr1"}},
    {"event": "message", "task_id": "t1", "answer": "你"},
    {"event": "ping"},
    {"event": "node_started", "task_id": "t1", "data": {"node_id": "n1"}},
    {"event": "message", "task_id": "t1", "answer": "好"},
    {"event": "message_end", "task_id": "t1", "metadata": {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}},
]

# ---------------------------------------------------------------------------
# Message flattening
# ---------------------------------------------------------------------------


class TestFlattenMessages:
    def test_roles_are_labeled_in_order(self):
        model = _make_model()
        messages = [
            SystemMessage(content="你是档案检索助手"),
            HumanMessage(content="iPhone 13 的规格是什么"),
            AIMessage(content="iPhone 13 于 2021 年发布"),
            HumanMessage(content="那屏幕尺寸呢"),
        ]
        assert model._flatten_messages(messages) == ("[系统] 你是档案检索助手\n\n[用户] iPhone 13 的规格是什么\n\n[助手] iPhone 13 于 2021 年发布\n\n[用户] 那屏幕尺寸呢")

    def test_tool_message_uses_tool_label(self):
        model = _make_model()
        messages = [HumanMessage(content="查一下"), ToolMessage(content="检索结果: A", tool_call_id="call_1", name="search")]
        assert model._flatten_messages(messages) == "[用户] 查一下\n\n[工具:search] 检索结果: A"

    def test_multimodal_content_flattens_to_text(self):
        model = _make_model()
        messages = [HumanMessage(content=[{"type": "text", "text": "图里的档案是什么"}, {"type": "image_url", "image_url": {"url": "http://x/a.png"}}])]
        assert model._flatten_messages(messages) == "[用户] 图里的档案是什么"

    def test_empty_messages_yield_empty_query(self):
        model = _make_model()
        assert model._flatten_messages([]) == ""


# ---------------------------------------------------------------------------
# Streaming (sync)
# ---------------------------------------------------------------------------


class TestStream:
    def test_yields_answer_chunks_and_terminal_usage(self):
        model = _make_model()
        with _patch_sync_stream(_CHAT_EVENTS)[0]:
            chunks = list(model._stream([HumanMessage(content="你好")]))
        assert all(isinstance(chunk, ChatGenerationChunk) for chunk in chunks)
        assert "".join(chunk.message.content for chunk in chunks) == "你好"
        final = chunks[-1].message
        assert final.usage_metadata == {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        assert final.response_metadata["model"] == "linkong-archive-qa"

    def test_workflow_ping_and_node_events_are_ignored(self):
        model = _make_model()
        with _patch_sync_stream(_CHAT_EVENTS)[0]:
            chunks = list(model._stream([HumanMessage(content="你好")]))
        assert [chunk.message.content for chunk in chunks] == ["你", "好", ""]

    def test_error_event_raises(self):
        model = _make_model()
        events = [{"event": "error", "status": 400, "code": "provider_quota_exceeded", "message": "模型调用额度不足"}]
        patcher, _ = _patch_sync_stream(events)
        with patcher, pytest.raises(RuntimeError, match="provider_quota_exceeded"):
            list(model._stream([HumanMessage(content="你好")]))

    def test_stream_without_message_end_raises(self):
        model = _make_model()
        events = [{"event": "message", "answer": "部分回答"}]
        patcher, _ = _patch_sync_stream(events)
        with patcher, pytest.raises(RuntimeError, match="message_end"):
            list(model._stream([HumanMessage(content="你好")]))

    def test_message_without_answer_field_is_skipped(self):
        model = _make_model()
        events = [
            {"event": "message", "answer": "a"},
            {"event": "message"},
            {"event": "message_end", "metadata": {}},
        ]
        patcher, _ = _patch_sync_stream(events)
        with patcher:
            chunks = list(model._stream([HumanMessage(content="你好")]))
        assert [chunk.message.content for chunk in chunks] == ["a", ""]

    def test_generate_aggregates_stream(self):
        model = _make_model()
        with _patch_sync_stream(_CHAT_EVENTS)[0]:
            result = model._generate([HumanMessage(content="你好")])
        message = result.generations[0].message
        assert isinstance(message, AIMessage)
        assert message.content == "你好"
        assert message.usage_metadata == {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}


# ---------------------------------------------------------------------------
# Streaming (async)
# ---------------------------------------------------------------------------


class TestAsyncStream:
    @pytest.mark.asyncio
    async def test_astream_yields_chunks_and_usage(self):
        model = _make_model()
        with _patch_async_stream(_CHAT_EVENTS):
            chunks = [chunk async for chunk in model._astream([HumanMessage(content="你好")])]
        assert "".join(chunk.message.content for chunk in chunks) == "你好"
        assert chunks[-1].message.usage_metadata == {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}

    @pytest.mark.asyncio
    async def test_agenerate_aggregates_stream(self):
        model = _make_model()
        with _patch_async_stream(_CHAT_EVENTS):
            result = await model._agenerate([HumanMessage(content="你好")])
        assert result.generations[0].message.content == "你好"
        assert result.generations[0].message.usage_metadata["total_tokens"] == 15


# ---------------------------------------------------------------------------
# Request contract
# ---------------------------------------------------------------------------


class TestRequestContract:
    def test_payload_headers_and_url(self):
        model = _make_model(inputs={"mode": "fulltext"})
        patcher, captured = _patch_sync_stream(_CHAT_EVENTS)
        with patcher:
            list(model._stream([SystemMessage(content="s"), HumanMessage(content="问题")]))
        assert captured["method"] == "POST"
        assert captured["url"] == "https://10.20.10.88/v1/chat-messages"
        assert captured["headers"]["Authorization"] == "Bearer test-key"
        assert captured["headers"]["X-Email"] == "tester@example.com"
        assert captured["headers"]["Accept"] == "text/event-stream"
        payload = captured["payload"]
        assert payload["query"] == "[系统] s\n\n[用户] 问题"
        assert payload["response_mode"] == "streaming"
        assert payload["conversation_id"] == ""
        assert payload["inputs"] == {"mode": "fulltext"}
        assert payload["user"] == "tester@example.com"
        assert payload["auto_generate_name"] is False

    def test_user_defaults_to_deerflow_without_email(self):
        model = _make_model(email="", dify_user="")
        patcher, captured = _patch_sync_stream(_CHAT_EVENTS)
        with patcher:
            list(model._stream([HumanMessage(content="你好")]))
        assert captured["payload"]["user"] == "deerflow"
        assert "X-Email" not in captured["headers"]

    def test_dify_user_overrides_email_as_user(self):
        model = _make_model(dify_user="abc-123")
        patcher, captured = _patch_sync_stream(_CHAT_EVENTS)
        with patcher:
            list(model._stream([HumanMessage(content="你好")]))
        assert captured["payload"]["user"] == "abc-123"
        assert captured["headers"]["X-Email"] == "tester@example.com"

    def test_verify_ssl_flag_reaches_client(self):
        model = _make_model(verify_ssl=False)
        patcher, captured = _patch_sync_stream(_CHAT_EVENTS)
        with patcher:
            list(model._stream([HumanMessage(content="你好")]))
        assert captured["client_kwargs"].get("verify") is False


# ---------------------------------------------------------------------------
# Tool binding degradation
# ---------------------------------------------------------------------------


class TestBindTools:
    def test_bind_tools_warns_and_returns_binding_without_tools(self):
        model = _make_model()
        with patch("deerflow.models.dify_app_provider.logger") as mock_logger:
            binding = model.bind_tools([{"type": "function", "function": {"name": "web_search", "parameters": {}}}])
        assert isinstance(binding, RunnableBinding)
        assert binding.bound is model
        assert mock_logger.warning.called

    def test_bound_model_still_answers(self):
        model = _make_model()
        binding = model.bind_tools([])
        patcher, _ = _patch_sync_stream(_CHAT_EVENTS)
        with patcher:
            result = binding.invoke([HumanMessage(content="你好")])
        assert isinstance(result, AIMessage)
        assert result.content == "你好"
