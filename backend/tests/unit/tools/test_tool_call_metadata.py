"""Tests for keeping AIMessage tool-call surfaces consistent when calls are removed.

Provider adapters re-serialize tool calls from ``AIMessage.content`` blocks, not
only from ``tool_calls``. A guard that strips a call from ``tool_calls`` but
leaves its content block behind sends the provider a tool call with no matching
tool result, which Anthropic and the OpenAI Responses API reject on every later
request for that thread.
"""

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI

from deerflow.agents.middlewares.tool_call_metadata import _raw_tool_call_id, clone_ai_message_with_tool_calls
from deerflow.models.claude_provider import ClaudeChatModel

# DeerFlow deployments use ClaudeChatModel, which post-processes the payload
# built by the upstream ChatAnthropic formatter; pin both.
_ANTHROPIC_MODEL_CLASSES = pytest.mark.parametrize("model_class", [ChatAnthropic, ClaudeChatModel], ids=["ChatAnthropic", "ClaudeChatModel"])


def _call(call_id: str, name: str = "bash") -> dict:
    return {"id": call_id, "name": name, "args": {}}


def _tool_use(call_id: str, name: str = "bash") -> dict:
    return {"type": "tool_use", "id": call_id, "name": name, "input": {}}


class TestContentToolCallBlockSync:
    def test_drops_anthropic_tool_use_blocks_for_removed_calls(self):
        message = AIMessage(
            content=[{"type": "text", "text": "running"}, _tool_use("a"), _tool_use("b")],
            tool_calls=[_call("a"), _call("b")],
        )

        cloned = clone_ai_message_with_tool_calls(message, [_call("a")])

        assert cloned.content == [{"type": "text", "text": "running"}, _tool_use("a")]
        assert [tc["id"] for tc in cloned.tool_calls] == ["a"]

    def test_clearing_every_call_keeps_non_tool_call_blocks(self):
        thinking = {"type": "thinking", "thinking": "hmm", "signature": "sig"}
        server_tool = {"type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search", "input": {}}
        message = AIMessage(content=[thinking, server_tool, _tool_use("a")], tool_calls=[_call("a")])

        cloned = clone_ai_message_with_tool_calls(message, [])

        assert cloned.content == [thinking, server_tool]

    def test_filters_caller_supplied_content(self):
        message = AIMessage(content=[_tool_use("a")], tool_calls=[_call("a")])
        stop_note = {"type": "text", "text": "stopped"}

        cloned = clone_ai_message_with_tool_calls(message, [], content=[*message.content, stop_note])

        assert cloned.content == [stop_note]

    def test_openai_responses_blocks_match_by_call_id_not_item_id(self):
        kept = {"type": "function_call", "id": "fc_1", "call_id": "a", "name": "bash", "arguments": "{}"}
        dropped = {"type": "function_call", "id": "fc_2", "call_id": "b", "name": "bash", "arguments": "{}"}
        dropped_custom = {"type": "custom_tool_call", "id": "ctc_3", "call_id": "c", "name": "patch", "input": "x"}
        message = AIMessage(
            content=[kept, dropped, dropped_custom],
            tool_calls=[_call("a"), _call("b"), _call("c", "patch")],
        )

        cloned = clone_ai_message_with_tool_calls(message, [_call("a")])

        assert cloned.content == [kept]

    def test_langchain_standard_tool_call_blocks_match_by_id(self):
        kept = {"type": "tool_call", "id": "a", "name": "bash", "args": {}}
        dropped = {"type": "tool_call", "id": "b", "name": "bash", "args": {}}
        dropped_chunk = {"type": "tool_call_chunk", "id": "c", "name": "bash", "args": "{}", "index": 2}
        message = AIMessage(content=[kept, dropped, dropped_chunk], tool_calls=[_call("a"), _call("b"), _call("c")])

        cloned = clone_ai_message_with_tool_calls(message, [_call("a")])

        assert cloned.content == [kept]

    def test_google_genai_function_call_blocks_match_by_id(self):
        # Keep the second of two same-named calls: an id match keeps its own
        # block, where falling back to name order would keep the first one.
        dropped = {"type": "function_call", "id": "a", "name": "bash", "args": {}}
        kept = {"type": "function_call", "id": "b", "name": "bash", "args": {}}
        message = AIMessage(content=[dropped, kept], tool_calls=[_call("a"), _call("b")])

        cloned = clone_ai_message_with_tool_calls(message, [_call("b")])

        assert cloned.content == [kept]

    def test_idless_blocks_keep_only_as_many_per_name_as_retained_calls(self):
        # Gemini-style blocks carry no id, so they pair with retained calls by
        # name, in order: truncating four same-named calls to three keeps three.
        blocks = [{"type": "function_call", "name": "task", "args": {"n": n}} for n in range(4)]
        calls = [_call(f"t{n}", "task") for n in range(4)]
        message = AIMessage(content=list(blocks), tool_calls=calls)

        cloned = clone_ai_message_with_tool_calls(message, calls[:3])

        assert cloned.content == blocks[:3]

    def test_idless_budget_skips_calls_already_paired_by_id(self):
        # A retained call whose own id-bearing block matched must not also let
        # a same-named id-less block survive on the name budget.
        with_id = {"type": "function_call", "id": "a", "name": "bash", "args": {}}
        idless = {"type": "function_call", "name": "bash", "args": {}}
        message = AIMessage(content=[with_id, idless], tool_calls=[_call("a"), _call("b")])

        assert clone_ai_message_with_tool_calls(message, [_call("a")]).content == [with_id]
        assert clone_ai_message_with_tool_calls(message, [_call("a"), _call("b")]).content is message.content

    def test_keeps_blocks_for_calls_that_remain_invalid_tool_calls(self):
        # DanglingToolCallMiddleware answers invalid_tool_calls with a placeholder
        # ToolMessage, so their content block must stay to pair with it.
        message = AIMessage(
            content=[_tool_use("bad"), _tool_use("a")],
            tool_calls=[_call("a")],
            invalid_tool_calls=[{"type": "invalid_tool_call", "id": "bad", "name": "bash", "args": "{", "error": "parse"}],
        )

        cloned = clone_ai_message_with_tool_calls(message, [])

        assert cloned.content == [_tool_use("bad")]
        assert [tc["id"] for tc in cloned.invalid_tool_calls] == ["bad"]

    def test_leaves_content_untouched_when_every_block_is_still_paired(self):
        content = [{"type": "text", "text": "hi"}, _tool_use("a")]
        message = AIMessage(content=content, tool_calls=[_call("a")])

        cloned = clone_ai_message_with_tool_calls(message, [_call("a")])

        assert cloned.content is message.content

    def test_string_content_is_unchanged(self):
        message = AIMessage(content="plain", tool_calls=[_call("a")])

        assert clone_ai_message_with_tool_calls(message, []).content == "plain"


def _anthropic_payload_turns(model_class: type[ChatAnthropic], messages: list) -> list[tuple[str, list[str]]]:
    payload = model_class(model="claude-sonnet-4-5", anthropic_api_key="sk-ant-offline")._get_request_payload(messages)
    turns = []
    for turn in payload["messages"]:
        blocks = turn["content"] if isinstance(turn["content"], list) else [{"type": "text"}]
        turns.append((turn["role"], [block.get("id") or block.get("tool_use_id") or block["type"] for block in blocks if block["type"] in ("tool_use", "tool_result")]))
    return turns


class TestProviderRequestContract:
    """Drive the real provider request builders offline; no network is used."""

    @_ANTHROPIC_MODEL_CLASSES
    def test_anthropic_request_pairs_every_tool_use_after_calls_are_cleared(self, model_class):
        message = AIMessage(
            content=[{"type": "text", "text": "reading"}, _tool_use("toolu_a")],
            tool_calls=[_call("toolu_a")],
            response_metadata={"model_provider": "anthropic"},
        )
        stopped = clone_ai_message_with_tool_calls(message, [], content=[*message.content, {"type": "text", "text": "stopped"}])

        turns = _anthropic_payload_turns(model_class, [HumanMessage("hi"), stopped, HumanMessage("continue")])

        assert turns == [("user", []), ("assistant", []), ("user", [])]

    @_ANTHROPIC_MODEL_CLASSES
    def test_anthropic_request_pairs_every_tool_use_after_calls_are_truncated(self, model_class):
        calls = [_call(f"toolu_{n}", "task") for n in range(3)]
        message = AIMessage(
            content=[_tool_use(call["id"], "task") for call in calls],
            tool_calls=calls,
            response_metadata={"model_provider": "anthropic"},
        )
        truncated = clone_ai_message_with_tool_calls(message, calls[:2])
        results = [ToolMessage(content="ok", tool_call_id=call["id"]) for call in truncated.tool_calls]

        turns = _anthropic_payload_turns(model_class, [HumanMessage("go"), truncated, *results])

        assert turns == [("user", []), ("assistant", ["toolu_0", "toolu_1"]), ("user", ["toolu_0", "toolu_1"])]

    def test_openai_responses_request_drops_function_call_after_calls_are_cleared(self):
        message = AIMessage(
            content=[{"type": "function_call", "id": "fc_1", "call_id": "call_a", "name": "bash", "arguments": "{}"}],
            tool_calls=[_call("call_a")],
            response_metadata={"model_provider": "openai"},
        )
        stopped = clone_ai_message_with_tool_calls(message, [], content=[*message.content, {"type": "text", "text": "stopped"}])
        llm = ChatOpenAI(model="gpt-5", api_key="sk-offline", use_responses_api=True, output_version="responses/v1")

        payload = llm._get_request_payload([HumanMessage("hi"), stopped, HumanMessage("continue")])

        assert [item for item in payload["input"] if item.get("type") == "function_call"] == []


# --- merged from test_tool_call_metadata.py (subdir-only tests; root copy is the dedup base) ---
def _tc(
    name: str = "test_tool",
    tc_id: str = "call_1",
    args: dict | None = None,
) -> dict:
    return {"name": name, "id": tc_id, "args": args or {}}


def _raw_tc(
    name: str = "test_tool",
    tc_id: str = "call_1",
) -> dict:
    return {
        "name": name,
        "id": tc_id,
        "type": "function",
        "function": {"arguments": "{}"},
    }


def _make_msg(
    tool_calls: list[dict] | None = None,
    additional_kwargs: dict | None = None,
    response_metadata: dict | None = None,
    content: str = "",
    msg_id: str = "msg_1",
) -> AIMessage:
    return AIMessage(
        content=content,
        tool_calls=tool_calls or [],
        additional_kwargs=additional_kwargs or {},
        response_metadata=response_metadata or {},
        id=msg_id,
    )


class TestRawToolCallId:
    def test_none_returns_none(self):
        assert _raw_tool_call_id(None) is None

    def test_non_dict_returns_none(self):
        assert _raw_tool_call_id("not a dict") is None
        assert _raw_tool_call_id(42) is None
        assert _raw_tool_call_id(["list"]) is None

    def test_empty_dict_returns_none(self):
        assert _raw_tool_call_id({}) is None

    def test_empty_string_id_returns_none(self):
        assert _raw_tool_call_id({"id": ""}) is None

    def test_non_string_id_returns_none(self):
        assert _raw_tool_call_id({"id": 123}) is None
        assert _raw_tool_call_id({"id": True}) is None
        assert _raw_tool_call_id({"id": ["nested"]}) is None

    def test_valid_string_id_returns_id(self):
        assert _raw_tool_call_id({"id": "call_abc"}) == "call_abc"

    def test_valid_id_with_extra_keys(self):
        assert _raw_tool_call_id({"id": "call_xyz", "type": "function", "function": {}}) == "call_xyz"

    def test_missing_id_key_returns_none(self):
        assert _raw_tool_call_id({"name": "foo", "type": "function"}) is None


class TestCloneCore:
    def test_creates_new_message_with_updated_tool_calls(self):
        original = _make_msg(tool_calls=[_tc("old")], content="hello")
        new_tcs = [_tc("new", "call_2")]
        cloned = clone_ai_message_with_tool_calls(original, new_tcs)
        assert cloned.tool_calls == new_tcs
        assert cloned.tool_calls != original.tool_calls

    def test_preserves_original_message_content(self):
        original = _make_msg(content="original content")
        cloned = clone_ai_message_with_tool_calls(original, [_tc()])
        assert cloned.content == "original content"

    def test_preserves_original_message_id(self):
        original = _make_msg(msg_id="my-unique-id")
        cloned = clone_ai_message_with_tool_calls(original, [_tc()])
        assert cloned.id == "my-unique-id"

    def test_returns_new_instance_does_not_mutate_original(self):
        original = _make_msg(tool_calls=[_tc("original", "call_1")])
        original_tool_calls = list(original.tool_calls)
        new_tcs = [_tc("replacement", "call_2")]
        clone_ai_message_with_tool_calls(original, new_tcs)
        assert original.tool_calls == original_tool_calls


class TestCloneAdditionalKwargs:
    def test_matching_raw_calls_are_preserved(self):
        original = _make_msg(
            tool_calls=[_tc("a", "call_keep")],
            additional_kwargs={
                "tool_calls": [
                    _raw_tc("a", "call_keep"),
                    _raw_tc("b", "call_drop"),
                ]
            },
        )
        cloned = clone_ai_message_with_tool_calls(original, [_tc("a", "call_keep")])
        assert len(cloned.additional_kwargs["tool_calls"]) == 1
        assert cloned.additional_kwargs["tool_calls"][0]["id"] == "call_keep"

    def test_non_matching_raw_calls_are_filtered_out(self):
        original = _make_msg(
            tool_calls=[_tc("old")],
            additional_kwargs={"tool_calls": [_raw_tc("old", "call_drop")]},
        )
        cloned = clone_ai_message_with_tool_calls(original, [_tc("new", "call_new")])
        assert "tool_calls" not in cloned.additional_kwargs

    def test_no_matching_raw_calls_removes_key(self):
        original = _make_msg(
            tool_calls=[_tc("a", "call_a")],
            additional_kwargs={"tool_calls": [_raw_tc("b", "call_b")]},
        )
        cloned = clone_ai_message_with_tool_calls(original, [_tc("c", "call_c")])
        assert "tool_calls" not in cloned.additional_kwargs

    def test_empty_additional_kwargs_works(self):
        original = _make_msg(additional_kwargs={})
        cloned = clone_ai_message_with_tool_calls(original, [_tc()])
        assert cloned.additional_kwargs == {}

    def test_additional_kwargs_is_none(self):
        msg = AIMessage(content="", tool_calls=[_tc()])
        msg.additional_kwargs = None
        cloned = clone_ai_message_with_tool_calls(msg, [_tc("a", "call_1")])
        assert cloned.additional_kwargs == {}

    def test_non_list_tool_calls_in_additional_kwargs_ignored(self):
        original = _make_msg(
            additional_kwargs={"tool_calls": "not-a-list"},
        )
        cloned = clone_ai_message_with_tool_calls(original, [_tc()])
        assert cloned.additional_kwargs == {"tool_calls": "not-a-list"}

    def test_empty_tool_calls_removes_function_call(self):
        original = _make_msg(
            tool_calls=[_tc()],
            additional_kwargs={"function_call": {"name": "foo"}},
        )
        cloned = clone_ai_message_with_tool_calls(original, [])
        assert "function_call" not in cloned.additional_kwargs

    def test_non_empty_tool_calls_keeps_function_call(self):
        original = _make_msg(
            additional_kwargs={"function_call": {"name": "foo"}},
        )
        cloned = clone_ai_message_with_tool_calls(original, [_tc()])
        assert cloned.additional_kwargs["function_call"] == {"name": "foo"}

    def test_mixed_match_partial_filter(self):
        original = _make_msg(
            tool_calls=[_tc("a", "keep"), _tc("b", "keep_too")],
            additional_kwargs={
                "tool_calls": [
                    _raw_tc("a", "keep"),
                    _raw_tc("b", "keep_too"),
                    _raw_tc("c", "drop"),
                ]
            },
        )
        cloned = clone_ai_message_with_tool_calls(original, [_tc("a", "keep"), _tc("b", "keep_too")])
        assert len(cloned.additional_kwargs["tool_calls"]) == 2

    def test_populated_additional_kwargs_other_keys_preserved(self):
        original = _make_msg(
            tool_calls=[_tc("a", "keep")],
            additional_kwargs={
                "tool_calls": [_raw_tc("a", "keep")],
                "other_key": "still-here",
            },
        )
        cloned = clone_ai_message_with_tool_calls(original, [_tc("a", "keep")])
        assert cloned.additional_kwargs["other_key"] == "still-here"

    def test_empty_tool_calls_no_function_call_key(self):
        original = _make_msg(additional_kwargs={"tool_calls": [_raw_tc()]})
        cloned = clone_ai_message_with_tool_calls(original, [])
        assert "function_call" not in cloned.additional_kwargs
        assert "tool_calls" not in cloned.additional_kwargs


class TestCloneResponseMetadata:
    def test_empty_tool_calls_changes_finish_reason_tool_calls_to_stop(self):
        original = _make_msg(
            response_metadata={"finish_reason": "tool_calls"},
        )
        cloned = clone_ai_message_with_tool_calls(original, [])
        assert cloned.response_metadata["finish_reason"] == "stop"

    def test_non_empty_tool_calls_keeps_finish_reason_unchanged(self):
        original = _make_msg(
            tool_calls=[_tc()],
            response_metadata={"finish_reason": "tool_calls"},
        )
        cloned = clone_ai_message_with_tool_calls(original, [_tc()])
        assert cloned.response_metadata["finish_reason"] == "tool_calls"

    def test_finish_reason_not_tool_calls_unchanged(self):
        original = _make_msg(
            response_metadata={"finish_reason": "stop"},
        )
        cloned = clone_ai_message_with_tool_calls(original, [])
        assert cloned.response_metadata["finish_reason"] == "stop"

        original2 = _make_msg(
            response_metadata={"finish_reason": "length"},
        )
        cloned2 = clone_ai_message_with_tool_calls(original2, [_tc()])
        assert cloned2.response_metadata["finish_reason"] == "length"

    def test_empty_response_metadata_works(self):
        original = _make_msg(response_metadata={})
        cloned = clone_ai_message_with_tool_calls(original, [])
        assert cloned.response_metadata == {}

    def test_response_metadata_is_none(self):
        msg = AIMessage(content="", tool_calls=[])
        msg.response_metadata = None
        cloned = clone_ai_message_with_tool_calls(msg, [])
        assert cloned.response_metadata == {}

    def test_empty_tool_calls_preserves_other_metadata_keys(self):
        original = _make_msg(
            tool_calls=[_tc()],
            response_metadata={
                "finish_reason": "tool_calls",
                "model_name": "gpt-4",
                "token_usage": {"total": 100},
            },
        )
        cloned = clone_ai_message_with_tool_calls(original, [])
        assert cloned.response_metadata["finish_reason"] == "stop"
        assert cloned.response_metadata["model_name"] == "gpt-4"
        assert cloned.response_metadata["token_usage"] == {"total": 100}


class TestCloneContent:
    def test_provided_content_is_set(self):
        original = _make_msg(content="original")
        cloned = clone_ai_message_with_tool_calls(original, [_tc()], content="overridden")
        assert cloned.content == "overridden"

    def test_provided_content_empty_string(self):
        original = _make_msg(content="original")
        cloned = clone_ai_message_with_tool_calls(original, [_tc()], content="")
        assert cloned.content == ""

    def test_content_is_none_preserves_original(self):
        original = _make_msg(content="original content")
        cloned = clone_ai_message_with_tool_calls(original, [_tc()], content=None)
        assert cloned.content == "original content"

    def test_preserves_list_content_when_no_content_arg(self):
        original = _make_msg(content="hello")
        cloned = clone_ai_message_with_tool_calls(original, [_tc()])
        assert cloned.content == "hello"


class TestCloneEdgeCases:
    def test_empty_tool_calls_list(self):
        original = _make_msg(tool_calls=[_tc()])
        cloned = clone_ai_message_with_tool_calls(original, [])
        assert cloned.tool_calls == []

    def test_tool_call_without_id_in_new_list_kept_metadata_unchanged(self):
        """A tool call without 'id' won't be in kept_ids, so raw calls are all dropped."""
        original = _make_msg(
            tool_calls=[_tc("a", "call_1")],
            additional_kwargs={"tool_calls": [_raw_tc("a", "call_1")]},
        )
        cloned = clone_ai_message_with_tool_calls(original, [{"name": "no_id", "args": {}}])
        assert "tool_calls" not in cloned.additional_kwargs

    def test_original_message_unchanged_after_clone(self):
        original = _make_msg(
            tool_calls=[_tc("a", "call_1")],
            additional_kwargs={"tool_calls": [_raw_tc("a", "call_1")]},
            response_metadata={"finish_reason": "tool_calls"},
            content="before",
        )
        original_tool_calls = list(original.tool_calls)
        clone_ai_message_with_tool_calls(original, [], content="after")
        assert original.tool_calls == original_tool_calls
        assert "tool_calls" in original.additional_kwargs
        assert original.response_metadata["finish_reason"] == "tool_calls"
        assert original.content == "before"

    def test_type_and_constructor_are_aimessage(self):
        cloned = clone_ai_message_with_tool_calls(_make_msg(), [_tc()])
        assert isinstance(cloned, AIMessage)

    def test_name_is_preserved(self):
        original = AIMessage(content="", tool_calls=[], name="assistant")
        cloned = clone_ai_message_with_tool_calls(original, [])
        assert cloned.name == "assistant"

    def test_none_tool_calls_raises_type_error(self):
        with pytest.raises(TypeError):
            clone_ai_message_with_tool_calls(_make_msg(), None)

    def test_non_dict_item_in_tool_calls_raises_attribute_error(self):
        with pytest.raises(AttributeError):
            clone_ai_message_with_tool_calls(_make_msg(), ["not_a_dict"])

    def test_clone_carries_provided_tool_calls(self):
        original = _make_msg()
        new_tcs = [_tc("a", "call_1")]
        cloned = clone_ai_message_with_tool_calls(original, new_tcs)
        # Upstream stores the provided list as-is on the clone (documented
        # contract; callers pass a freshly built list). Assert the clone is a
        # distinct message carrying exactly the provided calls.
        assert cloned is not original
        assert cloned.tool_calls == [{"name": "a", "id": "call_1", "args": {}}]
        assert cloned.tool_calls[0]["id"] == "call_1"
