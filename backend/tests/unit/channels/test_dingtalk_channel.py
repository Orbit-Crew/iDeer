"""Tests for the DingTalk channel implementation."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from support.symlinks import symlink_or_skip

from app.channels.commands import KNOWN_CHANNEL_COMMANDS
from app.channels.dingtalk import (
    _CONVERSATION_TYPE_GROUP,
    _CONVERSATION_TYPE_P2P,
    DingTalkChannel,
    _adapt_markdown_for_dingtalk,
    _convert_markdown_table,
    _DingTalkMessageHandler,
    _extract_text_from_rich_text,
    _is_dingtalk_command,
    _normalize_allowed_users,
    _normalize_conversation_type,
)
from app.channels.message_bus import InboundMessageType, MessageBus, OutboundMessage, ResolvedAttachment
from deerflow.config.paths import VIRTUAL_PATH_PREFIX


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _take_inbound(bus: MessageBus):
    inbound = await asyncio.wait_for(bus.get_inbound(), timeout=1)
    bus.inbound_task_done()
    return inbound


# ---------------------------------------------------------------------------
# Helper: build mock ChatbotMessage
# ---------------------------------------------------------------------------


def _make_chatbot_message(
    *,
    text: str = "hello",
    message_type: str = "text",
    conversation_type: str | int = _CONVERSATION_TYPE_P2P,
    sender_staff_id: str = "user_001",
    sender_nick: str = "Test User",
    conversation_id: str = "conv_001",
    message_id: str = "msg_001",
    rich_text_list: list | None = None,
):
    """Build a minimal mock object mimicking dingtalk_stream.ChatbotMessage."""
    msg = SimpleNamespace()
    msg.message_type = message_type
    msg.conversation_type = conversation_type
    msg.sender_staff_id = sender_staff_id
    msg.sender_nick = sender_nick
    msg.conversation_id = conversation_id
    msg.message_id = message_id

    if message_type == "text":
        msg.text = SimpleNamespace(content=text)
        msg.rich_text_content = None
    elif message_type == "richText":
        msg.text = None
        msg.rich_text_content = SimpleNamespace(rich_text_list=rich_text_list or [])
    else:
        msg.text = None
        msg.rich_text_content = None

    return msg


# ---------------------------------------------------------------------------
# _DingTalkMessageHandler SDK contract
# ---------------------------------------------------------------------------


class TestDingTalkMessageHandlerSdkContract:
    def test_pre_start_exists_and_noop(self):
        bus = MessageBus()
        channel = DingTalkChannel(bus, config={})
        handler = _DingTalkMessageHandler(channel)
        handler.pre_start()

    def test_raw_process_returns_ack(self):
        pytest.importorskip("dingtalk_stream")

        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._on_chatbot_message = MagicMock()
            handler = _DingTalkMessageHandler(channel)
            cb = MagicMock()
            cb.headers.message_id = "mid-1"
            cb.data = {
                "msgtype": "text",
                "text": {"content": "hi"},
                "senderStaffId": "u1",
                "conversationType": "1",
                "msgId": "m1",
            }
            ack = await handler.raw_process(cb)
            assert ack.code == 200
            assert ack.headers.message_id == "mid-1"
            assert ack.data == {"response": "OK"}
            channel._on_chatbot_message.assert_called_once()

        _run(go())


# ---------------------------------------------------------------------------
# _normalize_allowed_users tests
# ---------------------------------------------------------------------------


class TestNormalizeAllowedUsers:
    def test_none_returns_empty(self):
        assert _normalize_allowed_users(None) == set()

    def test_empty_list_returns_empty(self):
        assert _normalize_allowed_users([]) == set()

    def test_list_of_strings(self):
        result = _normalize_allowed_users(["user1", "user2"])
        assert result == {"user1", "user2"}

    def test_single_string(self):
        result = _normalize_allowed_users("user1")
        assert result == {"user1"}

    def test_numeric_values_converted_to_string(self):
        result = _normalize_allowed_users([123, 456])
        assert result == {"123", "456"}

    def test_scalar_treated_as_single_value(self):
        result = _normalize_allowed_users(12345)
        assert result == {"12345"}


# ---------------------------------------------------------------------------
# _normalize_conversation_type tests
# ---------------------------------------------------------------------------


class TestNormalizeConversationType:
    def test_group_int_or_str(self):
        assert _normalize_conversation_type(2) == _CONVERSATION_TYPE_GROUP
        assert _normalize_conversation_type("2") == _CONVERSATION_TYPE_GROUP

    def test_p2p_or_none(self):
        assert _normalize_conversation_type(1) == _CONVERSATION_TYPE_P2P
        assert _normalize_conversation_type(None) == _CONVERSATION_TYPE_P2P


# ---------------------------------------------------------------------------
# _is_dingtalk_command tests
# ---------------------------------------------------------------------------


class TestIsDingTalkCommand:
    @pytest.mark.parametrize("command", sorted(KNOWN_CHANNEL_COMMANDS))
    def test_known_commands_recognized(self, command):
        assert _is_dingtalk_command(command) is True

    @pytest.mark.parametrize(
        "text",
        [
            "/unknown",
            "/mnt/user-data/outputs/report.md",
            "hello",
            "",
            "not a command",
        ],
    )
    def test_non_commands_rejected(self, text):
        assert _is_dingtalk_command(text) is False


# ---------------------------------------------------------------------------
# _extract_text_from_rich_text tests
# ---------------------------------------------------------------------------


class TestExtractTextFromRichText:
    def test_single_text_item(self):
        result = _extract_text_from_rich_text([{"text": "hello"}])
        assert result == "hello"

    def test_multiple_text_items(self):
        result = _extract_text_from_rich_text([{"text": "hello"}, {"text": "world"}])
        assert result == "hello world"

    def test_non_text_items_ignored(self):
        result = _extract_text_from_rich_text(
            [
                {"downloadCode": "abc123"},
                {"text": "caption"},
            ]
        )
        assert result == "caption"

    def test_empty_list(self):
        assert _extract_text_from_rich_text([]) == ""


# ---------------------------------------------------------------------------
# DingTalkChannel._extract_text tests
# ---------------------------------------------------------------------------


class TestExtractText:
    def test_plain_text(self):
        msg = _make_chatbot_message(text="Hello World")
        assert DingTalkChannel._extract_text(msg) == "Hello World"

    def test_plain_text_stripped(self):
        msg = _make_chatbot_message(text="  Hello  ")
        assert DingTalkChannel._extract_text(msg) == "Hello"

    def test_rich_text(self):
        msg = _make_chatbot_message(
            message_type="richText",
            rich_text_list=[{"text": "Part 1"}, {"text": "Part 2"}],
        )
        assert DingTalkChannel._extract_text(msg) == "Part 1 Part 2"

    def test_unknown_type_returns_empty(self):
        msg = _make_chatbot_message(message_type="picture")
        assert DingTalkChannel._extract_text(msg) == ""


# ---------------------------------------------------------------------------
# DingTalkChannel._on_chatbot_message tests (inbound parsing)
# ---------------------------------------------------------------------------


class TestOnChatbotMessage:
    def test_p2p_message_produces_correct_inbound(self):
        async def go():
            bus = MessageBus()
            bus.publish_inbound = AsyncMock()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._main_loop = asyncio.get_event_loop()
            channel._running = True

            msg = _make_chatbot_message(
                text="hello from dingtalk",
                conversation_type=_CONVERSATION_TYPE_P2P,
                sender_staff_id="user_001",
                message_id="msg_001",
            )

            channel._send_running_reply = AsyncMock()
            channel._on_chatbot_message(msg)

            await asyncio.sleep(0.1)

            inbound = await _take_inbound(bus)
            assert inbound.channel_name == "dingtalk"
            assert inbound.chat_id == "user_001"
            assert inbound.user_id == "user_001"
            assert inbound.text == "hello from dingtalk"
            assert inbound.topic_id is None
            assert inbound.metadata["conversation_type"] == _CONVERSATION_TYPE_P2P
            assert inbound.metadata["sender_staff_id"] == "user_001"

        _run(go())

    def test_group_message_produces_correct_inbound(self):
        async def go():
            bus = MessageBus()
            bus.publish_inbound = AsyncMock()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._main_loop = asyncio.get_event_loop()
            channel._running = True

            msg = _make_chatbot_message(
                text="hello group",
                conversation_type=_CONVERSATION_TYPE_GROUP,
                sender_staff_id="user_002",
                conversation_id="conv_group_001",
                message_id="msg_group_001",
            )

            channel._send_running_reply = AsyncMock()
            channel._on_chatbot_message(msg)

            await asyncio.sleep(0.1)

            inbound = await _take_inbound(bus)
            assert inbound.channel_name == "dingtalk"
            assert inbound.chat_id == "conv_group_001"
            assert inbound.user_id == "user_002"
            assert inbound.text == "hello group"
            assert inbound.topic_id == "msg_group_001"
            assert inbound.metadata["conversation_type"] == _CONVERSATION_TYPE_GROUP
            assert inbound.metadata["conversation_id"] == "conv_group_001"

        _run(go())

    @pytest.mark.parametrize("text", ["@bot /new", "@_user_1 /help", "@bot /goal ship it"])
    def test_leading_mention_before_command_classifies_and_strips(self, text):
        """DingTalk group chats leave "@bot /new" in the text; classify as COMMAND
        and strip the mention so ChannelManager receives the bare command."""

        async def go():
            bus = MessageBus()
            bus.publish_inbound = AsyncMock()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._main_loop = asyncio.get_event_loop()
            channel._running = True

            msg = _make_chatbot_message(
                text=text,
                conversation_type=_CONVERSATION_TYPE_GROUP,
                sender_staff_id="user_002",
                conversation_id="conv_group_001",
                message_id="msg_mention_cmd",
            )

            channel._send_running_reply = AsyncMock()
            channel._on_chatbot_message(msg)

            await asyncio.sleep(0.1)

            inbound = await _take_inbound(bus)
            assert inbound.msg_type == InboundMessageType.COMMAND, f"{text!r} should be COMMAND"
            assert not inbound.text.startswith("@"), "leading mention must be stripped for dispatch"
            assert inbound.text.split(maxsplit=1)[0] in KNOWN_CHANNEL_COMMANDS

        _run(go())

    def test_leading_mention_before_chat_keeps_mention(self):
        """A mentioned non-command stays CHAT and keeps the mention for the agent."""

        async def go():
            bus = MessageBus()
            bus.publish_inbound = AsyncMock()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._main_loop = asyncio.get_event_loop()
            channel._running = True

            msg = _make_chatbot_message(
                text="@bot please summarise this",
                conversation_type=_CONVERSATION_TYPE_GROUP,
                sender_staff_id="user_002",
                conversation_id="conv_group_001",
                message_id="msg_mention_chat",
            )

            channel._send_running_reply = AsyncMock()
            channel._on_chatbot_message(msg)

            await asyncio.sleep(0.1)

            inbound = await _take_inbound(bus)
            assert inbound.msg_type == InboundMessageType.CHAT
            assert inbound.text == "@bot please summarise this"

        _run(go())

    def test_group_message_integer_conversation_type_normalized(self):
        """SDK may deliver conversationType as int 2 — must still route as group."""

        async def go():
            bus = MessageBus()
            bus.publish_inbound = AsyncMock()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._main_loop = asyncio.get_event_loop()
            channel._running = True

            msg = _make_chatbot_message(
                text="hello group",
                conversation_type=2,
                sender_staff_id="user_002",
                conversation_id="conv_group_001",
                message_id="msg_group_002",
            )

            channel._send_running_reply = AsyncMock()
            channel._on_chatbot_message(msg)

            await asyncio.sleep(0.1)

            inbound = await _take_inbound(bus)
            assert inbound.chat_id == "conv_group_001"
            assert inbound.topic_id == "msg_group_002"
            assert inbound.metadata["conversation_type"] == _CONVERSATION_TYPE_GROUP

        _run(go())

    @pytest.mark.parametrize("sender_staff_id", ["", None])
    def test_p2p_message_without_sender_is_dropped(self, sender_staff_id):
        """A P2P chat_id *is* the sender, so an empty one keys every user to one thread.

        ``ChannelStore._key`` builds ``f"{channel}:{chat_id}"`` for a topic-less conversation,
        so publishing this would put every senderless P2P message under the literal
        ``"dingtalk:"`` — one shared thread, one shared history, across users.
        """

        async def go():
            bus = MessageBus()
            bus.publish_inbound = AsyncMock()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._main_loop = asyncio.get_event_loop()
            channel._running = True

            msg = _make_chatbot_message(
                text="hello",
                conversation_type=_CONVERSATION_TYPE_P2P,
                sender_staff_id=sender_staff_id,
                message_id="msg_no_sender",
            )

            channel._send_running_reply = AsyncMock()
            channel._on_chatbot_message(msg)

            await asyncio.sleep(0.1)

            bus.publish_inbound.assert_not_awaited()
            assert bus.inbound_queue.empty()

        _run(go())

    def test_group_message_without_conversation_id_is_dropped(self):
        """The group route reaches the same degenerate key from the other side."""

        async def go():
            bus = MessageBus()
            bus.publish_inbound = AsyncMock()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._main_loop = asyncio.get_event_loop()
            channel._running = True

            msg = _make_chatbot_message(
                text="hello group",
                conversation_type=_CONVERSATION_TYPE_GROUP,
                sender_staff_id="user_002",
                conversation_id="",
                message_id="msg_no_conv",
            )

            channel._send_running_reply = AsyncMock()
            channel._on_chatbot_message(msg)

            await asyncio.sleep(0.1)

            bus.publish_inbound.assert_not_awaited()
            assert bus.inbound_queue.empty()

        _run(go())

    def test_group_message_with_unknown_sender_is_still_delivered(self):
        """Reverse anchor: the guard is on the conversation identity, not on the sender.

        A group message identifies its conversation through ``conversation_id``, so an
        unknown sender must not cost the whole message.
        """

        async def go():
            bus = MessageBus()
            bus.publish_inbound = AsyncMock()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._main_loop = asyncio.get_event_loop()
            channel._running = True

            msg = _make_chatbot_message(
                text="hello group",
                conversation_type=_CONVERSATION_TYPE_GROUP,
                sender_staff_id="",
                conversation_id="conv_group_003",
                message_id="msg_group_003",
            )

            channel._send_running_reply = AsyncMock()
            channel._on_chatbot_message(msg)

            await asyncio.sleep(0.1)

            inbound = await _take_inbound(bus)
            assert inbound.chat_id == "conv_group_003"
            assert inbound.topic_id == "msg_group_003"

        _run(go())

    def test_command_classified_correctly(self):
        async def go():
            bus = MessageBus()
            bus.publish_inbound = AsyncMock()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._main_loop = asyncio.get_event_loop()
            channel._running = True

            msg = _make_chatbot_message(text="/help")
            channel._send_running_reply = AsyncMock()
            channel._on_chatbot_message(msg)

            await asyncio.sleep(0.1)

            inbound = await _take_inbound(bus)
            assert inbound.msg_type == InboundMessageType.COMMAND

        _run(go())

    def test_non_command_classified_as_chat(self):
        async def go():
            bus = MessageBus()
            bus.publish_inbound = AsyncMock()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._main_loop = asyncio.get_event_loop()
            channel._running = True

            msg = _make_chatbot_message(text="just chatting")
            channel._send_running_reply = AsyncMock()
            channel._on_chatbot_message(msg)

            await asyncio.sleep(0.1)

            inbound = await _take_inbound(bus)
            assert inbound.msg_type == InboundMessageType.CHAT

        _run(go())

    def test_empty_text_ignored(self):
        async def go():
            bus = MessageBus()
            bus.publish_inbound = AsyncMock()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._main_loop = asyncio.get_event_loop()
            channel._running = True

            msg = _make_chatbot_message(text="   ")
            channel._on_chatbot_message(msg)

            await asyncio.sleep(0.1)
            bus.publish_inbound.assert_not_awaited()
            assert bus.inbound_queue.empty()

        _run(go())


# ---------------------------------------------------------------------------
# allowed_users filtering tests
# ---------------------------------------------------------------------------


class TestAllowedUsersFiltering:
    def test_allowed_user_passes(self):
        async def go():
            bus = MessageBus()
            bus.publish_inbound = AsyncMock()
            channel = DingTalkChannel(bus, config={"allowed_users": ["user_001"]})
            channel._client_id = "test_key"
            channel._main_loop = asyncio.get_event_loop()
            channel._running = True

            msg = _make_chatbot_message(sender_staff_id="user_001")
            channel._send_running_reply = AsyncMock()
            channel._on_chatbot_message(msg)

            await asyncio.sleep(0.1)
            await _take_inbound(bus)

        _run(go())

    def test_non_allowed_user_blocked(self):
        async def go():
            bus = MessageBus()
            bus.publish_inbound = AsyncMock()
            channel = DingTalkChannel(bus, config={"allowed_users": ["user_001"]})
            channel._client_id = "test_key"
            channel._main_loop = asyncio.get_event_loop()
            channel._running = True

            msg = _make_chatbot_message(sender_staff_id="user_blocked")
            channel._on_chatbot_message(msg)

            await asyncio.sleep(0.1)
            bus.publish_inbound.assert_not_awaited()
            assert bus.inbound_queue.empty()

        _run(go())

    def test_non_allowed_user_message_content_not_logged(self, caplog):
        import logging

        async def go():
            bus = MessageBus()
            bus.publish_inbound = AsyncMock()
            channel = DingTalkChannel(bus, config={"allowed_users": ["user_001"]})
            channel._client_id = "test_key"
            channel._main_loop = asyncio.get_event_loop()
            channel._running = True

            msg = _make_chatbot_message(sender_staff_id="user_blocked", text="secret blocked content")
            with caplog.at_level(logging.INFO, logger="app.channels.dingtalk"):
                channel._on_chatbot_message(msg)
                await asyncio.sleep(0.1)

            bus.publish_inbound.assert_not_awaited()
            assert bus.inbound_queue.empty()
            # The parsed-message INFO log (with message content) must not fire for
            # a blocked sender — allowed_users still acts as a privacy/noise filter.
            assert "parsed message" not in caplog.text
            assert "secret blocked content" not in caplog.text

        _run(go())

    def test_connect_code_bypasses_allowed_users_filter(self):
        async def go():
            bus = MessageBus()
            bus.publish_inbound = AsyncMock()
            channel = DingTalkChannel(bus, config={"allowed_users": ["user_001"], "connection_repo": object()})
            channel._client_id = "test_key"
            channel._main_loop = asyncio.get_event_loop()
            channel._running = True
            channel._bind_connection_from_connect_code = AsyncMock(return_value=True)

            msg = _make_chatbot_message(sender_staff_id="user_blocked", text="/connect dingtalk-bind-code")
            channel._on_chatbot_message(msg)

            await asyncio.sleep(0.1)
            channel._bind_connection_from_connect_code.assert_awaited_once()
            bus.publish_inbound.assert_not_awaited()
            assert bus.inbound_queue.empty()

        _run(go())

    def test_empty_allowed_users_allows_all(self):
        async def go():
            bus = MessageBus()
            bus.publish_inbound = AsyncMock()
            channel = DingTalkChannel(bus, config={"allowed_users": []})
            channel._client_id = "test_key"
            channel._main_loop = asyncio.get_event_loop()
            channel._running = True

            msg = _make_chatbot_message(sender_staff_id="anyone")
            channel._send_running_reply = AsyncMock()
            channel._on_chatbot_message(msg)

            await asyncio.sleep(0.1)
            await _take_inbound(bus)

        _run(go())


# ---------------------------------------------------------------------------
# send routing tests (P2P vs Group)
# ---------------------------------------------------------------------------


class TestMarkdownFallbackPropagation:
    def test_fallback_raises_on_failure(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._cached_token = "tok"
            channel._token_expires_at = float("inf")

            channel._send_p2p_message = AsyncMock(side_effect=ConnectionError("send failed"))

            with pytest.raises(ConnectionError, match="send failed"):
                await channel._send_markdown_fallback("test_key", _CONVERSATION_TYPE_P2P, "user_001", "", "hello")

        _run(go())


class TestSendRouting:
    def test_p2p_send_uses_oto_endpoint(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._client_secret = "test_secret"

            channel._send_p2p_message = AsyncMock()
            channel._send_group_message = AsyncMock()

            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="user_001",
                thread_id="thread_001",
                text="Hello P2P",
                metadata={
                    "conversation_type": _CONVERSATION_TYPE_P2P,
                    "sender_staff_id": "user_001",
                    "conversation_id": "",
                },
            )

            await channel.send(msg)

            channel._send_p2p_message.assert_awaited_once_with("test_key", "user_001", "Hello P2P")
            channel._send_group_message.assert_not_awaited()

        _run(go())

    def test_group_send_uses_group_endpoint(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._client_secret = "test_secret"

            channel._send_p2p_message = AsyncMock()
            channel._send_group_message = AsyncMock()

            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="conv_001",
                thread_id="thread_001",
                text="Hello Group",
                metadata={
                    "conversation_type": _CONVERSATION_TYPE_GROUP,
                    "sender_staff_id": "user_001",
                    "conversation_id": "conv_001",
                },
            )

            await channel.send(msg)

            channel._send_group_message.assert_awaited_once_with("test_key", "conv_001", "Hello Group", at_user_ids=["user_001"])
            channel._send_p2p_message.assert_not_awaited()

        _run(go())

    def test_default_metadata_uses_p2p(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._client_secret = "test_secret"

            channel._send_p2p_message = AsyncMock()
            channel._send_group_message = AsyncMock()

            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="user_001",
                thread_id="thread_001",
                text="Hello",
                metadata={},
            )

            await channel.send(msg)

            channel._send_p2p_message.assert_awaited_once()
            channel._send_group_message.assert_not_awaited()

        _run(go())


# ---------------------------------------------------------------------------
# send retry tests
# ---------------------------------------------------------------------------


class TestSendRetry:
    def test_retries_on_failure_then_succeeds(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._client_secret = "test_secret"

            call_count = 0

            async def flaky_send(robot_code, user_id, text):
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise ConnectionError("network error")

            channel._send_p2p_message = AsyncMock(side_effect=flaky_send)

            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="user_001",
                thread_id="thread_001",
                text="hello",
                metadata={"conversation_type": _CONVERSATION_TYPE_P2P, "sender_staff_id": "user_001"},
            )

            await channel.send(msg)
            assert call_count == 3

        _run(go())

    def test_raises_after_all_retries_exhausted(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._client_secret = "test_secret"

            channel._send_p2p_message = AsyncMock(side_effect=ConnectionError("fail"))

            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="user_001",
                thread_id="thread_001",
                text="hello",
                metadata={"conversation_type": _CONVERSATION_TYPE_P2P, "sender_staff_id": "user_001"},
            )

            with pytest.raises(ConnectionError):
                await channel.send(msg)

            assert channel._send_p2p_message.await_count == 3

        _run(go())

    def test_raises_runtime_error_when_no_attempts_configured(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._client_secret = "test_secret"

            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="user_001",
                thread_id="thread_001",
                text="hello",
                metadata={"conversation_type": _CONVERSATION_TYPE_P2P, "sender_staff_id": "user_001"},
            )

            with pytest.raises(RuntimeError, match="without an exception"):
                await channel.send(msg, _max_retries=0)

        _run(go())


# ---------------------------------------------------------------------------
# topic_id mapping tests
# ---------------------------------------------------------------------------


class TestTopicIdMapping:
    def test_p2p_topic_is_none(self):
        async def go():
            bus = MessageBus()
            bus.publish_inbound = AsyncMock()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._main_loop = asyncio.get_event_loop()
            channel._running = True

            msg = _make_chatbot_message(
                conversation_type=_CONVERSATION_TYPE_P2P,
                message_id="msg_p2p_001",
            )
            channel._send_running_reply = AsyncMock()
            channel._on_chatbot_message(msg)

            await asyncio.sleep(0.1)
            inbound = await _take_inbound(bus)
            assert inbound.topic_id is None

        _run(go())

    def test_group_topic_is_message_id(self):
        async def go():
            bus = MessageBus()
            bus.publish_inbound = AsyncMock()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._main_loop = asyncio.get_event_loop()
            channel._running = True

            msg = _make_chatbot_message(
                conversation_type=_CONVERSATION_TYPE_GROUP,
                message_id="msg_group_001",
                conversation_id="conv_001",
            )
            channel._send_running_reply = AsyncMock()
            channel._on_chatbot_message(msg)

            await asyncio.sleep(0.1)
            inbound = await _take_inbound(bus)
            assert inbound.topic_id == "msg_group_001"

        _run(go())


# ---------------------------------------------------------------------------
# Token caching tests
# ---------------------------------------------------------------------------


class TestAccessTokenValidation:
    def test_rejects_non_dict_response(self):
        async def go():
            from unittest.mock import patch

            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "k"
            channel._client_secret = "s"

            class FakeResponse:
                def raise_for_status(self):
                    pass

                def json(self):
                    return "not a dict"

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kwargs):
                    return FakeResponse()

            with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                with pytest.raises(ValueError, match="JSON object"):
                    await channel._get_access_token()

        _run(go())

    def test_rejects_empty_access_token(self):
        async def go():
            from unittest.mock import patch

            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "k"
            channel._client_secret = "s"

            class FakeResponse:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"accessToken": "", "expireIn": 7200}

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kwargs):
                    return FakeResponse()

            with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                with pytest.raises(ValueError, match="usable accessToken"):
                    await channel._get_access_token()

        _run(go())

    def test_invalid_expire_in_uses_default(self):
        async def go():
            import time
            from unittest.mock import patch

            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "k"
            channel._client_secret = "s"

            class FakeResponse:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"accessToken": "tok_ok", "expireIn": "invalid"}

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kwargs):
                    return FakeResponse()

            before = time.monotonic()
            with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                token = await channel._get_access_token()

            assert token == "tok_ok"
            assert channel._token_expires_at > before

        _run(go())


class TestTokenCaching:
    def test_token_is_cached_across_calls(self):
        async def go():
            from unittest.mock import patch

            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._client_secret = "test_secret"

            call_count = 0

            class FakeResponse:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"accessToken": "tok_abc", "expireIn": 7200}

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kwargs):
                    nonlocal call_count
                    call_count += 1
                    return FakeResponse()

            with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                t1 = await channel._get_access_token()
                t2 = await channel._get_access_token()

            assert t1 == "tok_abc"
            assert t2 == "tok_abc"
            assert call_count == 1

        _run(go())


# ---------------------------------------------------------------------------
# Group message @ mention format tests
# ---------------------------------------------------------------------------


class TestGroupMessageMarkdownFormat:
    def test_at_user_ids_still_use_markdown(self):
        """groupMessages/send uses sampleMarkdown; @{userId} in body returns 400 so at_user_ids is ignored."""

        async def go():
            from unittest.mock import patch

            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._client_secret = "test_secret"
            channel._cached_token = "tok_test"
            channel._token_expires_at = float("inf")

            captured_json: list[dict] = []

            class FakeResponse:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"processQueryKey": "ok"}

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kwargs):
                    captured_json.append(kwargs.get("json", {}))
                    return FakeResponse()

            with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                await channel._send_group_message("bot", "conv1", "hello", at_user_ids=["staff_001"])

            assert len(captured_json) == 1
            payload = captured_json[0]
            assert payload["msgKey"] == "sampleMarkdown"
            import json

            param = json.loads(payload["msgParam"])
            assert param["text"] == "hello"
            assert "@" not in json.dumps(param)

        _run(go())

    def test_no_at_user_ids_uses_markdown(self):
        async def go():
            from unittest.mock import patch

            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._client_secret = "test_secret"
            channel._cached_token = "tok_test"
            channel._token_expires_at = float("inf")

            captured_json: list[dict] = []

            class FakeResponse:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"processQueryKey": "ok"}

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kwargs):
                    captured_json.append(kwargs.get("json", {}))
                    return FakeResponse()

            with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                await channel._send_group_message("bot", "conv1", "hello")

            assert len(captured_json) == 1
            payload = captured_json[0]
            assert payload["msgKey"] == "sampleMarkdown"

        _run(go())


class TestAdaptMarkdownForDingtalk:
    def test_fenced_code_block_to_blockquote(self):
        text = "Hello\n```python\ndef foo():\n    return 1\n```\nDone"
        result = _adapt_markdown_for_dingtalk(text)
        assert "```" not in result
        assert "> **python**" in result
        assert "> def foo():" in result
        assert ">     return 1" in result

    def test_fenced_code_block_no_language(self):
        text = "```\nplain code\n```"
        result = _adapt_markdown_for_dingtalk(text)
        assert "```" not in result
        assert "> plain code" in result

    def test_inline_code_to_bold(self):
        text = "Use `pip install` to install"
        result = _adapt_markdown_for_dingtalk(text)
        assert result == "Use **pip install** to install"

    def test_horizontal_rule_to_unicode(self):
        text = "Above\n---\nBelow"
        result = _adapt_markdown_for_dingtalk(text)
        assert "───────────" in result
        assert "---" not in result

    def test_supported_markdown_preserved(self):
        text = "# Title\n**bold** and *italic*\n- list item\n> quote\n[link](http://example.com)"
        result = _adapt_markdown_for_dingtalk(text)
        assert result == text

    def test_plain_text_unchanged(self):
        text = "Hello world, no markdown here."
        assert _adapt_markdown_for_dingtalk(text) == text

    def test_combined_elements(self):
        text = "# Report\n\nRun `make test` then:\n\n```bash\npytest -v\n```\n\n---\n\nDone."
        result = _adapt_markdown_for_dingtalk(text)
        assert "# Report" in result
        assert "**make test**" in result
        assert "> **bash**" in result
        assert "> pytest -v" in result
        assert "───────────" in result
        assert "Done." in result


class TestConvertMarkdownTable:
    def test_simple_table(self):
        text = "| Name | Age |\n|------|-----|\n| Alice | 30 |\n| Bob | 25 |"
        result = _convert_markdown_table(text)
        assert "> **Name**: Alice" in result
        assert "> **Age**: 30" in result
        assert "> **Name**: Bob" in result
        assert "> **Age**: 25" in result
        assert "|" not in result

    def test_table_with_surrounding_text(self):
        text = "Results:\n\n| Key | Value |\n|-----|-------|\n| a | 1 |\n\nEnd."
        result = _convert_markdown_table(text)
        assert "Results:" in result
        assert "> **Key**: a" in result
        assert "> **Value**: 1" in result
        assert "End." in result

    def test_no_table(self):
        text = "Just plain text\nwith lines"
        assert _convert_markdown_table(text) == text

    def test_alignment_separators(self):
        text = "| Left | Center | Right |\n|:-----|:------:|------:|\n| a | b | c |"
        result = _convert_markdown_table(text)
        assert "> **Left**: a" in result
        assert "> **Center**: b" in result
        assert "> **Right**: c" in result


class TestUploadMediaValidation:
    def test_non_dict_response_returns_none(self):
        async def go():
            from unittest.mock import patch

            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "k"
            channel._client_secret = "s"
            channel._cached_token = "tok"
            channel._token_expires_at = float("inf")

            class FakeResponse:
                def raise_for_status(self):
                    pass

                def json(self):
                    return ["not", "a", "dict"]

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kwargs):
                    return FakeResponse()

            with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                result = await channel._upload_media("/tmp/test.png", "image")

            assert result is None

        _run(go())

    def test_json_decode_error_returns_none(self):
        async def go():
            import json as json_mod
            from unittest.mock import patch

            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "k"
            channel._client_secret = "s"
            channel._cached_token = "tok"
            channel._token_expires_at = float("inf")

            class FakeResponse:
                def raise_for_status(self):
                    pass

                def json(self):
                    raise json_mod.JSONDecodeError("err", "", 0)

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kwargs):
                    return FakeResponse()

            with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                result = await channel._upload_media("/tmp/test.png", "image")

            assert result is None

        _run(go())


class TestChannelRegistration:
    def test_dingtalk_in_channel_registry(self):
        from app.channels.service import _CHANNEL_REGISTRY

        assert "dingtalk" in _CHANNEL_REGISTRY
        assert _CHANNEL_REGISTRY["dingtalk"] == "app.channels.dingtalk:DingTalkChannel"

    def test_dingtalk_in_credential_keys(self):
        from app.channels.service import _CHANNEL_CREDENTIAL_KEYS

        assert "dingtalk" in _CHANNEL_CREDENTIAL_KEYS
        assert "client_id" in _CHANNEL_CREDENTIAL_KEYS["dingtalk"]
        assert "client_secret" in _CHANNEL_CREDENTIAL_KEYS["dingtalk"]

    def test_dingtalk_in_channel_capabilities(self):
        from app.channels.manager import CHANNEL_CAPABILITIES

        assert "dingtalk" in CHANNEL_CAPABILITIES
        assert CHANNEL_CAPABILITIES["dingtalk"]["supports_streaming"] is False


# ---------------------------------------------------------------------------
# AI Card streaming mode tests
# ---------------------------------------------------------------------------


class TestCardMode:
    def test_card_mode_enabled_supports_streaming(self):
        bus = MessageBus()
        channel = DingTalkChannel(bus, config={"card_template_id": "tpl_123"})
        assert channel.supports_streaming is True

    def test_non_card_mode_no_streaming(self):
        bus = MessageBus()
        channel = DingTalkChannel(bus, config={})
        assert channel.supports_streaming is False

    def test_non_card_mode_unchanged(self):
        bus = MessageBus()
        channel = DingTalkChannel(bus, config={})
        assert channel._card_template_id == ""
        assert channel._card_track_ids == {}
        assert channel._card_repliers == {}
        assert channel._incoming_messages == {}
        assert channel._dingtalk_client is None

    def test_card_source_key_matches_inbound_using_message_id_metadata(self):
        """Outbound correlation must match inbound ``message_id`` even if ``thread_ts`` drifts."""

        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            inbound = channel._make_inbound(
                chat_id="x",
                user_id="u",
                text="hi",
                thread_ts="ts_fallback",
                metadata={
                    "conversation_type": _CONVERSATION_TYPE_P2P,
                    "sender_staff_id": "user_001",
                    "conversation_id": "",
                    "message_id": "msg_real",
                },
            )
            out = OutboundMessage(
                channel_name="dingtalk",
                chat_id="x",
                thread_id="t",
                text="ok",
                thread_ts="wrong_ts",
                metadata=dict(inbound.metadata),
            )
            assert channel._make_card_source_key(inbound) == channel._make_card_source_key_from_outbound(out)

        _run(go())

    def test_running_reply_creates_card(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={"card_template_id": "tpl_123"})
            channel._client_id = "test_key"

            channel._create_and_deliver_card = AsyncMock(return_value="track_001")

            inbound = channel._make_inbound(
                chat_id="user_001",
                user_id="user_001",
                text="hello",
                metadata={
                    "conversation_type": _CONVERSATION_TYPE_P2P,
                    "sender_staff_id": "user_001",
                    "conversation_id": "",
                    "message_id": "msg_001",
                },
            )

            mock_chatbot_msg = MagicMock()
            source_key = channel._make_card_source_key(inbound)
            channel._incoming_messages[source_key] = mock_chatbot_msg

            await channel._send_running_reply("user_001", inbound)

            channel._create_and_deliver_card.assert_awaited_once_with(
                "\u23f3 Working on it...",
                chatbot_message=mock_chatbot_msg,
            )
            assert channel._card_track_ids[source_key] == "track_001"

        _run(go())

    def test_send_streams_to_card(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={"card_template_id": "tpl_123"})
            channel._client_id = "test_key"

            channel._stream_update_card = AsyncMock()

            # Pre-populate card tracking
            source_key = f"{_CONVERSATION_TYPE_P2P}:user_001::msg_001"
            channel._card_track_ids[source_key] = "track_001"

            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="user_001",
                thread_id="thread_001",
                text="Partial response...",
                is_final=False,
                thread_ts="msg_001",
                metadata={
                    "conversation_type": _CONVERSATION_TYPE_P2P,
                    "sender_staff_id": "user_001",
                    "conversation_id": "",
                },
            )

            await channel.send(msg)

            channel._stream_update_card.assert_awaited_once_with(
                "track_001",
                "Partial response...",
                is_finalize=False,
            )
            # Track ID should still exist (not final)
            assert source_key in channel._card_track_ids

        _run(go())

    def test_send_finalizes_card(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={"card_template_id": "tpl_123"})
            channel._client_id = "test_key"

            channel._stream_update_card = AsyncMock()

            source_key = f"{_CONVERSATION_TYPE_P2P}:user_001::msg_001"
            channel._card_track_ids[source_key] = "track_001"

            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="user_001",
                thread_id="thread_001",
                text="Final answer.",
                is_final=True,
                thread_ts="msg_001",
                metadata={
                    "conversation_type": _CONVERSATION_TYPE_P2P,
                    "sender_staff_id": "user_001",
                    "conversation_id": "",
                },
            )

            await channel.send(msg)

            channel._stream_update_card.assert_awaited_once_with(
                "track_001",
                "Final answer.",
                is_finalize=True,
            )
            # Track ID should be cleaned up after final
            assert source_key not in channel._card_track_ids

        _run(go())

    def test_card_mode_skips_markdown_adaptation(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={"card_template_id": "tpl_123"})
            channel._client_id = "test_key"

            raw_markdown = "```python\ndef foo():\n    pass\n```"
            captured_content: list[str] = []

            async def capture_stream(out_track_id, content, *, is_finalize=False, is_error=False):
                captured_content.append(content)

            channel._stream_update_card = AsyncMock(side_effect=capture_stream)

            source_key = f"{_CONVERSATION_TYPE_P2P}:user_001::msg_001"
            channel._card_track_ids[source_key] = "track_001"

            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="user_001",
                thread_id="thread_001",
                text=raw_markdown,
                is_final=True,
                thread_ts="msg_001",
                metadata={
                    "conversation_type": _CONVERSATION_TYPE_P2P,
                    "sender_staff_id": "user_001",
                    "conversation_id": "",
                },
            )

            await channel.send(msg)

            # Raw markdown should be passed through without adaptation
            assert captured_content[0] == raw_markdown

        _run(go())

    def test_card_fallback_on_creation_failure(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={"card_template_id": "tpl_123"})
            channel._client_id = "test_key"

            # Card creation returns None (failure)
            channel._create_and_deliver_card = AsyncMock(return_value=None)
            channel._send_text_message_to_user = AsyncMock()

            inbound = channel._make_inbound(
                chat_id="user_001",
                user_id="user_001",
                text="hello",
                metadata={
                    "conversation_type": _CONVERSATION_TYPE_P2P,
                    "sender_staff_id": "user_001",
                    "conversation_id": "",
                    "message_id": "msg_001",
                },
            )

            source_key = channel._make_card_source_key(inbound)
            channel._incoming_messages[source_key] = MagicMock()

            await channel._send_running_reply("user_001", inbound)

            # Should fall through to text message
            channel._send_text_message_to_user.assert_awaited_once()
            assert len(channel._card_track_ids) == 0

        _run(go())

    def test_send_skips_non_final_without_card_track_when_template_configured(self):
        """Without a live card track, Manager streaming would duplicate sampleMarkdown sends."""

        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={"card_template_id": "tpl_123"})
            channel._client_id = "test_key"
            channel._send_group_message = AsyncMock()
            channel._send_p2p_message = AsyncMock()

            meta = {
                "conversation_type": _CONVERSATION_TYPE_P2P,
                "sender_staff_id": "user_001",
                "conversation_id": "",
            }
            await channel.send(
                OutboundMessage(
                    channel_name="dingtalk",
                    chat_id="user_001",
                    thread_id="t1",
                    text="partial",
                    is_final=False,
                    thread_ts="msg_001",
                    metadata=meta,
                )
            )
            channel._send_p2p_message.assert_not_called()
            channel._send_group_message.assert_not_called()

            await channel.send(
                OutboundMessage(
                    channel_name="dingtalk",
                    chat_id="user_001",
                    thread_id="t1",
                    text="final answer",
                    is_final=True,
                    thread_ts="msg_001",
                    metadata=meta,
                )
            )
            channel._send_p2p_message.assert_awaited_once()

        _run(go())

    def test_card_fallback_on_stream_failure(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={"card_template_id": "tpl_123"})
            channel._client_id = "test_key"

            channel._stream_update_card = AsyncMock(side_effect=ConnectionError("stream failed"))
            channel._send_markdown_fallback = AsyncMock()

            source_key = f"{_CONVERSATION_TYPE_P2P}:user_001::msg_001"
            channel._card_track_ids[source_key] = "track_001"

            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="user_001",
                thread_id="thread_001",
                text="Final answer.",
                is_final=True,
                thread_ts="msg_001",
                metadata={
                    "conversation_type": _CONVERSATION_TYPE_P2P,
                    "sender_staff_id": "user_001",
                    "conversation_id": "",
                },
            )

            await channel.send(msg)

            # Should fallback to markdown
            channel._send_markdown_fallback.assert_awaited_once_with(
                "test_key",
                _CONVERSATION_TYPE_P2P,
                "user_001",
                "",
                "Final answer.",
            )
            # Track ID should be cleaned up
            assert source_key not in channel._card_track_ids

        _run(go())

    def test_pre_start_stores_dingtalk_client(self):
        bus = MessageBus()
        channel = DingTalkChannel(bus, config={})
        handler = _DingTalkMessageHandler(channel)

        mock_client = MagicMock()
        handler.dingtalk_client = mock_client
        handler.pre_start()

        assert channel._dingtalk_client is mock_client

    def test_chatbot_message_stored_for_card_mode(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={"card_template_id": "tpl_123"})

            mock_message = MagicMock()
            mock_message.sender_staff_id = "user_001"
            mock_message.conversation_type = "1"
            mock_message.conversation_id = ""
            mock_message.message_id = "msg_001"
            mock_message.sender_nick = "TestUser"
            mock_message.message_type = "text"
            mock_message.text = MagicMock(content="hello")
            mock_message.rich_text_content = None

            channel._main_loop = asyncio.get_running_loop()
            channel._allowed_users = set()
            channel._running = True
            channel._send_running_reply = AsyncMock()

            channel._on_chatbot_message(mock_message)
            await asyncio.sleep(0.1)

            assert len(channel._incoming_messages) == 1
            stored_msg = list(channel._incoming_messages.values())[0]
            assert stored_msg is mock_message
            await _take_inbound(bus)

        _run(go())

    def test_card_replier_cleanup_on_final(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={"card_template_id": "tpl_123"})
            channel._client_id = "test_key"

            channel._stream_update_card = AsyncMock()

            source_key = f"{_CONVERSATION_TYPE_P2P}:user_001::msg_001"
            channel._card_track_ids[source_key] = "track_001"
            channel._card_repliers["track_001"] = MagicMock()

            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="user_001",
                thread_id="thread_001",
                text="Final answer.",
                is_final=True,
                thread_ts="msg_001",
                metadata={
                    "conversation_type": _CONVERSATION_TYPE_P2P,
                    "sender_staff_id": "user_001",
                    "conversation_id": "",
                },
            )

            await channel.send(msg)

            assert source_key not in channel._card_track_ids
            assert "track_001" not in channel._card_repliers

        _run(go())

    def test_card_creation_without_sdk_client_returns_none(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={"card_template_id": "tpl_123"})
            channel._dingtalk_client = None

            result = await channel._create_and_deliver_card(
                "test",
                chatbot_message=MagicMock(),
            )
            assert result is None

        _run(go())

    def test_card_creation_without_chatbot_message_returns_none(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={"card_template_id": "tpl_123"})
            channel._dingtalk_client = MagicMock()

            result = await channel._create_and_deliver_card(
                "test",
                chatbot_message=None,
            )
            assert result is None

        _run(go())

    def test_stream_update_card_raises_without_replier(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={"card_template_id": "tpl_123"})

            with pytest.raises(RuntimeError, match="No AICardReplier found"):
                await channel._stream_update_card("nonexistent_track", "content")

        _run(go())

    def test_stop_clears_card_state(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={"card_template_id": "tpl_123"})
            channel._running = True
            channel._dingtalk_client = MagicMock()
            channel._incoming_messages["key"] = MagicMock()
            channel._card_repliers["track"] = MagicMock()
            channel._card_track_ids["source"] = "track"

            await channel.stop()

            assert channel._dingtalk_client is None
            assert channel._incoming_messages == {}
            assert channel._card_repliers == {}
            assert channel._card_track_ids == {}

        _run(go())


# ---------------------------------------------------------------------------
# Inbound file support
# ---------------------------------------------------------------------------


def _make_picture_message(*, download_code: str = "dc_img", **kwargs):
    """Build a mock DingTalk ``picture`` message carrying an ImageContent."""
    msg = _make_chatbot_message(text="", message_type="picture", **kwargs)
    msg.image_content = SimpleNamespace(download_code=download_code)
    return msg


def _make_file_message(*, download_code: str = "dc_file", file_name: str | None = "report.xlsx", **kwargs):
    """Build a mock DingTalk ``file`` (document) message.

    dingtalk_stream does not parse ``file`` messages, so the descriptor lives on
    the raw callback payload the handler stashes as ``_df_raw_data``.
    """
    msg = _make_chatbot_message(text="", message_type="file", **kwargs)
    content: dict = {"downloadCode": download_code}
    if file_name is not None:
        content["fileName"] = file_name
    msg._df_raw_data = {"msgtype": "file", "content": content}
    return msg


def _patch_uploads(monkeypatch, uploads_dir, *, sandbox_id="local", sandbox=None):
    monkeypatch.setattr(
        "app.channels.dingtalk.get_paths",
        lambda: SimpleNamespace(
            ensure_thread_dirs=lambda thread_id, user_id=None: None,
            sandbox_uploads_dir=lambda thread_id, user_id=None: uploads_dir,
        ),
    )
    monkeypatch.setattr("app.channels.dingtalk.get_effective_user_id", lambda: "default")

    async def _acquire_async(thread_id, user_id=None):
        return sandbox_id

    monkeypatch.setattr(
        "app.channels.dingtalk.get_sandbox_provider",
        lambda: SimpleNamespace(acquire_async=_acquire_async, get=lambda sid: sandbox),
    )


class TestExtractFiles:
    def test_text_message_has_no_files(self):
        assert DingTalkChannel._extract_files(_make_chatbot_message(text="hi")) == []

    def test_picture_message(self):
        files = DingTalkChannel._extract_files(_make_picture_message(download_code="dc_1"))
        assert files == [{"type": "image", "download_code": "dc_1", "filename": "image.png"}]

    def test_picture_message_missing_download_code_ignored(self):
        msg = _make_chatbot_message(text="", message_type="picture")
        msg.image_content = SimpleNamespace(download_code=None)
        assert DingTalkChannel._extract_files(msg) == []

    def test_rich_text_images(self):
        msg = _make_chatbot_message(text="", message_type="richText")
        msg.get_image_list = lambda: ["dc_a", "dc_b"]
        files = DingTalkChannel._extract_files(msg)
        assert files == [
            {"type": "image", "download_code": "dc_a", "filename": "image_0.png"},
            {"type": "image", "download_code": "dc_b", "filename": "image_1.png"},
        ]

    def test_rich_text_get_image_list_failure_is_logged_not_silent(self, caplog):
        """An SDK parse failure must be distinguishable from "no inline images"."""
        msg = _make_chatbot_message(text="", message_type="richText")

        def _boom():
            raise RuntimeError("sdk failure")

        msg.get_image_list = _boom
        with caplog.at_level(logging.WARNING, logger="app.channels.dingtalk"):
            assert DingTalkChannel._extract_files(msg) == []

        assert any("failed to read inline images" in r.message for r in caplog.records)

    def test_file_message_from_raw_data(self):
        files = DingTalkChannel._extract_files(_make_file_message(download_code="dc_doc", file_name="报价.xlsx"))
        assert files == [{"type": "file", "download_code": "dc_doc", "filename": "报价.xlsx"}]

    def test_file_message_default_filename(self):
        files = DingTalkChannel._extract_files(_make_file_message(download_code="dc_doc", file_name=None))
        assert files == [{"type": "file", "download_code": "dc_doc", "filename": "file.bin"}]

    def test_file_message_without_raw_data_ignored(self):
        msg = _make_chatbot_message(text="", message_type="file")
        assert DingTalkChannel._extract_files(msg) == []


class TestOnChatbotMessageFiles:
    def test_picture_message_publishes_inbound_with_files(self):
        async def go():
            bus = MessageBus()
            bus.publish_inbound = AsyncMock()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._main_loop = asyncio.get_event_loop()
            channel._running = True
            channel._send_running_reply = AsyncMock()

            channel._on_chatbot_message(_make_picture_message(download_code="dc_pic", sender_staff_id="u1", message_id="m1"))
            await asyncio.sleep(0.1)

            inbound = await _take_inbound(bus)
            assert inbound.msg_type == InboundMessageType.CHAT
            assert inbound.files == [{"type": "image", "download_code": "dc_pic", "filename": "image.png"}]

        _run(go())

    def test_file_message_publishes_inbound_with_files(self):
        async def go():
            bus = MessageBus()
            bus.publish_inbound = AsyncMock()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._main_loop = asyncio.get_event_loop()
            channel._running = True
            channel._send_running_reply = AsyncMock()

            channel._on_chatbot_message(_make_file_message(download_code="dc_doc", file_name="data.csv", sender_staff_id="u1", message_id="m1"))
            await asyncio.sleep(0.1)

            inbound = await _take_inbound(bus)
            assert inbound.files == [{"type": "file", "download_code": "dc_doc", "filename": "data.csv"}]

        _run(go())

    def test_message_without_text_or_files_dropped(self):
        async def go():
            bus = MessageBus()
            bus.publish_inbound = AsyncMock()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._main_loop = asyncio.get_event_loop()
            channel._running = True

            # picture message whose image carries no download_code -> no files, no text
            msg = _make_chatbot_message(text="", message_type="picture")
            msg.image_content = SimpleNamespace(download_code=None)
            channel._on_chatbot_message(msg)
            await asyncio.sleep(0.1)

            bus.publish_inbound.assert_not_awaited()
            assert bus.inbound_queue.empty()

        _run(go())


class TestReceiveFile:
    def test_no_files_is_noop(self):
        async def go():
            channel = DingTalkChannel(MessageBus(), config={})
            msg = channel._make_inbound(chat_id="c", user_id="u", text="hi", thread_ts="m")
            out = await channel.receive_file(msg, "t1")
            assert out is msg
            assert out.text == "hi"

        _run(go())

    def test_downloads_persists_and_prepends_path(self, tmp_path, monkeypatch):
        async def go():
            channel = DingTalkChannel(MessageBus(), config={})
            channel._client_id = "robot"
            channel._download_by_code = AsyncMock(return_value=b"XLSXDATA")
            uploads = tmp_path / "uploads"
            uploads.mkdir()
            _patch_uploads(monkeypatch, uploads)

            msg = channel._make_inbound(
                chat_id="c",
                user_id="u",
                text="please translate",
                thread_ts="m",
                files=[{"type": "file", "download_code": "dc1", "filename": "quote.xlsx"}],
            )
            out = await channel.receive_file(msg, "thread-1", user_id="default")

            assert out.files == []
            assert (uploads / "quote.xlsx").read_bytes() == b"XLSXDATA"
            assert f"{VIRTUAL_PATH_PREFIX}/uploads/quote.xlsx" in out.text
            assert out.text.endswith("please translate")
            channel._download_by_code.assert_awaited_once_with("dc1")

        _run(go())

    def test_pure_file_message_text_is_only_the_path(self, tmp_path, monkeypatch):
        async def go():
            channel = DingTalkChannel(MessageBus(), config={})
            channel._download_by_code = AsyncMock(return_value=b"IMG")
            uploads = tmp_path / "uploads"
            uploads.mkdir()
            _patch_uploads(monkeypatch, uploads)

            msg = channel._make_inbound(
                chat_id="c",
                user_id="u",
                text="",
                thread_ts="m",
                files=[{"type": "image", "download_code": "dc_i", "filename": "image.png"}],
            )
            out = await channel.receive_file(msg, "t1", user_id="default")

            assert out.text == f"{VIRTUAL_PATH_PREFIX}/uploads/image.png"

        _run(go())

    def test_download_failure_surfaces_marker(self):
        """A failed download must stay visible to the agent, not vanish silently."""

        async def go():
            channel = DingTalkChannel(MessageBus(), config={})
            channel._download_by_code = AsyncMock(return_value=None)

            msg = channel._make_inbound(
                chat_id="c",
                user_id="u",
                text="hi",
                thread_ts="m",
                files=[{"type": "file", "download_code": "dc1", "filename": "x.pdf"}],
            )
            out = await channel.receive_file(msg, "t1", user_id="default")

            assert out.files == []
            assert out.text == "[failed to load file: x.pdf]\n\nhi"

        _run(go())

    def test_token_failure_yields_marker_not_exception(self):
        """An auth failure during download must degrade to a marker, not an exception.

        The manager calls ``receive_file`` without a try, so anything escaping
        here kills the whole chat turn with no reply at all.
        """

        async def go():
            channel = DingTalkChannel(MessageBus(), config={})
            channel._client_id = "robot"
            channel._get_access_token = AsyncMock(side_effect=ValueError("bad token response"))

            msg = channel._make_inbound(
                chat_id="c",
                user_id="u",
                text="hi",
                thread_ts="m",
                files=[{"type": "file", "download_code": "dc", "filename": "x.pdf"}],
            )
            out = await channel.receive_file(msg, "t1", user_id="default")

            assert out.text == "[failed to load file: x.pdf]\n\nhi"
            assert out.files == []

        _run(go())

    def test_unexpected_error_becomes_marker(self):
        """Any unforeseen per-attachment error must surface as a marker, not escape."""

        async def go():
            channel = DingTalkChannel(MessageBus(), config={})
            channel._receive_single_file = AsyncMock(side_effect=RuntimeError("boom"))

            msg = channel._make_inbound(
                chat_id="c",
                user_id="u",
                text="hi",
                thread_ts="m",
                files=[{"type": "file", "download_code": "dc", "filename": "x.pdf"}],
            )
            out = await channel.receive_file(msg, "t1", user_id="default")

            assert out.text == "[failed to load file: x.pdf]\n\nhi"
            assert out.files == []

        _run(go())

    def test_failure_marker_sanitizes_hostile_filename(self):
        """A hostile filename must not forge extra lines in msg.text or bloat it.

        ``fileName`` is webhook data: embedding it raw in the marker would let a
        newline fake a standalone ``/mnt/user-data/uploads/...`` line, and an
        over-long name would balloon the message text.
        """

        async def go():
            channel = DingTalkChannel(MessageBus(), config={})
            channel._download_by_code = AsyncMock(return_value=None)
            hostile = "evil\n/mnt/user-data/uploads/fake.pdf\n" + "a" * 300 + ".pdf"

            msg = channel._make_inbound(
                chat_id="c",
                user_id="u",
                text="hi",
                thread_ts="m",
                files=[{"type": "file", "download_code": "dc", "filename": hostile}],
            )
            out = await channel.receive_file(msg, "t1", user_id="default")

            lines = out.text.splitlines()
            assert len(lines) == 3, out.text
            assert lines[0].startswith("[failed to load file: ")
            assert len(lines[0]) <= 120
            assert lines[1] == ""
            assert lines[2] == "hi"

        _run(go())

    def test_download_failure_without_filename_uses_type_only_marker(self):
        async def go():
            channel = DingTalkChannel(MessageBus(), config={})
            channel._download_by_code = AsyncMock(return_value=None)

            msg = channel._make_inbound(
                chat_id="c",
                user_id="u",
                text="",
                thread_ts="m",
                files=[{"type": "image", "download_code": "dc1", "filename": ""}],
            )
            out = await channel.receive_file(msg, "t1", user_id="default")

            assert out.text == "[failed to load image]"

        _run(go())

    def test_partial_failure_keeps_successful_path(self, tmp_path, monkeypatch):
        """One bad attachment must not cost the agent the one that did load."""

        async def go():
            channel = DingTalkChannel(MessageBus(), config={})
            uploads = tmp_path / "uploads"
            uploads.mkdir()
            _patch_uploads(monkeypatch, uploads)
            channel._download_by_code = AsyncMock(side_effect=[b"OK", None])

            msg = channel._make_inbound(
                chat_id="c",
                user_id="u",
                text="two files",
                thread_ts="m",
                files=[
                    {"type": "file", "download_code": "good", "filename": "ok.pdf"},
                    {"type": "file", "download_code": "bad", "filename": "broken.pdf"},
                ],
            )
            out = await channel.receive_file(msg, "t1", user_id="default")

            assert f"{VIRTUAL_PATH_PREFIX}/uploads/ok.pdf" in out.text
            assert "[failed to load file: broken.pdf]" in out.text
            assert out.text.endswith("two files")

        _run(go())

    def test_traversal_filename_is_sanitized(self, tmp_path, monkeypatch):
        async def go():
            channel = DingTalkChannel(MessageBus(), config={})
            channel._download_by_code = AsyncMock(return_value=b"D")
            uploads = tmp_path / "uploads"
            uploads.mkdir()
            _patch_uploads(monkeypatch, uploads)

            msg = channel._make_inbound(
                chat_id="c",
                user_id="u",
                text="",
                thread_ts="m",
                files=[{"type": "file", "download_code": "dc", "filename": "../../etc/passwd"}],
            )
            out = await channel.receive_file(msg, "t1", user_id="default")

            written = list(uploads.iterdir())
            assert len(written) == 1
            assert written[0].name == "passwd"
            assert out.text == f"{VIRTUAL_PATH_PREFIX}/uploads/passwd"

        _run(go())

    def test_rejected_filename_falls_back_to_generated_name(self, tmp_path, monkeypatch):
        """A filename normalize_filename rejects must land on the generated name.

        ``".."`` raises inside ``normalize_filename`` (unlike ``../../etc/passwd``,
        whose basename ``passwd`` is accepted), so this exercises the except branch.
        """

        async def go():
            channel = DingTalkChannel(MessageBus(), config={})
            channel._download_by_code = AsyncMock(return_value=b"D")
            uploads = tmp_path / "uploads"
            uploads.mkdir()
            _patch_uploads(monkeypatch, uploads)

            msg = channel._make_inbound(
                chat_id="c",
                user_id="u",
                text="",
                thread_ts="m",
                files=[{"type": "file", "download_code": "abc123456789", "filename": ".."}],
            )
            out = await channel.receive_file(msg, "t1", user_id="default")

            written = list(uploads.iterdir())
            assert len(written) == 1
            assert written[0].name == "dingtalk_abc123456789.bin"
            assert out.text == f"{VIRTUAL_PATH_PREFIX}/uploads/dingtalk_abc123456789.bin"

        _run(go())

    def test_fallback_name_sanitizes_download_code(self, tmp_path, monkeypatch):
        """download_code is webhook data: it must not inject path separators."""

        async def go():
            channel = DingTalkChannel(MessageBus(), config={})
            channel._download_by_code = AsyncMock(return_value=b"D")
            uploads = tmp_path / "uploads"
            uploads.mkdir()
            _patch_uploads(monkeypatch, uploads)

            msg = channel._make_inbound(
                chat_id="c",
                user_id="u",
                text="",
                thread_ts="m",
                files=[{"type": "image", "download_code": "../../evil", "filename": ".."}],
            )
            out = await channel.receive_file(msg, "t1", user_id="default")

            written = list(uploads.iterdir())
            assert len(written) == 1
            assert "/" not in written[0].name
            assert written[0].name == "dingtalk_evil.png"
            assert out.text == f"{VIRTUAL_PATH_PREFIX}/uploads/dingtalk_evil.png"

        _run(go())

    def test_second_picture_does_not_overwrite_first(self, tmp_path, monkeypatch):
        """Two picture messages both generate "image.png" and must not collide.

        The path handed to the agent must still hold the bytes it referred to.
        """

        async def go():
            channel = DingTalkChannel(MessageBus(), config={})
            uploads = tmp_path / "uploads"
            uploads.mkdir()
            _patch_uploads(monkeypatch, uploads)

            channel._download_by_code = AsyncMock(return_value=b"FIRST")
            first = channel._make_inbound(
                chat_id="c",
                user_id="u",
                text="",
                thread_ts="m1",
                files=[{"type": "image", "download_code": "dc1", "filename": "image.png"}],
            )
            out_first = await channel.receive_file(first, "t1", user_id="default")

            channel._download_by_code = AsyncMock(return_value=b"SECOND")
            second = channel._make_inbound(
                chat_id="c",
                user_id="u",
                text="",
                thread_ts="m2",
                files=[{"type": "image", "download_code": "dc2", "filename": "image.png"}],
            )
            out_second = await channel.receive_file(second, "t1", user_id="default")

            assert out_first.text != out_second.text
            first_name = out_first.text.rsplit("/", 1)[-1]
            second_name = out_second.text.rsplit("/", 1)[-1]
            # Each advertised path must still resolve to its own bytes.
            assert (uploads / first_name).read_bytes() == b"FIRST"
            assert (uploads / second_name).read_bytes() == b"SECOND"

        _run(go())

    def test_multiple_images_in_one_message_get_distinct_paths(self, tmp_path, monkeypatch):
        async def go():
            channel = DingTalkChannel(MessageBus(), config={})
            uploads = tmp_path / "uploads"
            uploads.mkdir()
            _patch_uploads(monkeypatch, uploads)
            channel._download_by_code = AsyncMock(side_effect=[b"A", b"B"])

            msg = channel._make_inbound(
                chat_id="c",
                user_id="u",
                text="",
                thread_ts="m",
                files=[
                    {"type": "image", "download_code": "dc1", "filename": "image_0.png"},
                    {"type": "image", "download_code": "dc2", "filename": "image_0.png"},
                ],
            )
            out = await channel.receive_file(msg, "t1", user_id="default")

            paths = out.text.split("\n")
            assert len(paths) == 2
            assert paths[0] != paths[1]
            assert len(list(uploads.iterdir())) == 2
            assert {p.read_bytes() for p in uploads.iterdir()} == {b"A", b"B"}

        _run(go())

    def test_duplicate_document_names_do_not_collide(self, tmp_path, monkeypatch):
        """The same real filename sent twice must not clobber the earlier upload."""

        async def go():
            channel = DingTalkChannel(MessageBus(), config={})
            uploads = tmp_path / "uploads"
            uploads.mkdir()
            _patch_uploads(monkeypatch, uploads)

            channel._download_by_code = AsyncMock(return_value=b"V1")
            m1 = channel._make_inbound(chat_id="c", user_id="u", text="", thread_ts="m1", files=[{"type": "file", "download_code": "d1", "filename": "quote.xlsx"}])
            await channel.receive_file(m1, "t1", user_id="default")

            channel._download_by_code = AsyncMock(return_value=b"V2")
            m2 = channel._make_inbound(chat_id="c", user_id="u", text="", thread_ts="m2", files=[{"type": "file", "download_code": "d2", "filename": "quote.xlsx"}])
            await channel.receive_file(m2, "t1", user_id="default")

            assert (uploads / "quote.xlsx").read_bytes() == b"V1"
            assert len(list(uploads.iterdir())) == 2

        _run(go())

    def test_write_reserves_planted_symlink_name(self, tmp_path, monkeypatch):
        """A symlink planted at the requested name must force a unique suffix.

        Upload dirs can be mounted into local sandboxes, so a sandbox process can
        leave a symlink at a future upload name; following it would let a
        gateway-privileged write land outside the bucket. The symlink name is
        treated as occupied so the attachment still loads at the next suffix.
        """

        async def go():
            channel = DingTalkChannel(MessageBus(), config={})
            uploads = tmp_path / "uploads"
            uploads.mkdir()
            outside = tmp_path / "outside.txt"
            symlink_or_skip(uploads / "image.png", outside)
            _patch_uploads(monkeypatch, uploads)
            channel._download_by_code = AsyncMock(return_value=b"PWNED")

            msg = channel._make_inbound(
                chat_id="c",
                user_id="u",
                text="",
                thread_ts="m",
                files=[{"type": "image", "download_code": "dc", "filename": "image.png"}],
            )
            out = await channel.receive_file(msg, "t1", user_id="default")

            assert not outside.exists()
            assert (uploads / "image.png").is_symlink()
            assert (uploads / "image_1.png").read_bytes() == b"PWNED"
            assert out.text == f"{VIRTUAL_PATH_PREFIX}/uploads/image_1.png"

        _run(go())

    def test_missing_sandbox_after_acquire_yields_marker(self, tmp_path, monkeypatch):
        """A non-local sandbox that cannot be resolved must not yield a path.

        The agent's sandbox cannot see the file in that case, so handing it the
        virtual path would point at nothing readable; mirror Feishu and surface
        a failed-load marker instead.
        """

        async def go():
            channel = DingTalkChannel(MessageBus(), config={})
            channel._download_by_code = AsyncMock(return_value=b"BYTES")
            uploads = tmp_path / "uploads"
            uploads.mkdir()
            _patch_uploads(monkeypatch, uploads, sandbox_id="aio:box1", sandbox=None)

            msg = channel._make_inbound(
                chat_id="c",
                user_id="u",
                text="hi",
                thread_ts="m",
                files=[{"type": "file", "download_code": "dc", "filename": "a.pdf"}],
            )
            out = await channel.receive_file(msg, "t1", user_id="default")

            assert out.text == "[failed to load file: a.pdf]\n\nhi"

        _run(go())

    def test_update_file_failure_yields_marker(self, tmp_path, monkeypatch):
        """A failed non-local sandbox sync must not yield a path either.

        Same failure mode as the missing-sandbox case: the bytes never reached
        the agent's sandbox, so the virtual path would read as nothing. Mirrors
        Feishu, whose sync except-branch returns the failure marker.
        """

        async def go():
            channel = DingTalkChannel(MessageBus(), config={})
            channel._download_by_code = AsyncMock(return_value=b"BYTES")
            uploads = tmp_path / "uploads"
            uploads.mkdir()
            broken_sandbox = MagicMock()
            broken_sandbox.update_file.side_effect = RuntimeError("sandbox transport down")
            _patch_uploads(monkeypatch, uploads, sandbox_id="aio:box1", sandbox=broken_sandbox)

            msg = channel._make_inbound(
                chat_id="c",
                user_id="u",
                text="hi",
                thread_ts="m",
                files=[{"type": "file", "download_code": "dc", "filename": "a.pdf"}],
            )
            out = await channel.receive_file(msg, "t1", user_id="default")

            assert out.text == "[failed to load file: a.pdf]\n\nhi"

        _run(go())

    def test_non_local_sandbox_is_synced(self, tmp_path, monkeypatch):
        async def go():
            channel = DingTalkChannel(MessageBus(), config={})
            channel._download_by_code = AsyncMock(return_value=b"BYTES")
            uploads = tmp_path / "uploads"
            uploads.mkdir()
            fake_sandbox = MagicMock()
            _patch_uploads(monkeypatch, uploads, sandbox_id="aio:box1", sandbox=fake_sandbox)

            msg = channel._make_inbound(
                chat_id="c",
                user_id="u",
                text="",
                thread_ts="m",
                files=[{"type": "file", "download_code": "dc", "filename": "a.pdf"}],
            )
            await channel.receive_file(msg, "t1", user_id="default")

            fake_sandbox.update_file.assert_called_once_with(f"{VIRTUAL_PATH_PREFIX}/uploads/a.pdf", b"BYTES")

        _run(go())


class TestDownloadByCode:
    def test_two_step_download(self):
        async def go():
            from unittest.mock import patch

            channel = DingTalkChannel(MessageBus(), config={})
            channel._client_id = "robot_x"
            channel._get_access_token = AsyncMock(return_value="tok")

            class PostResponse:
                status_code = 200

                @staticmethod
                def json():
                    return {"downloadUrl": "https://dl.dingtalk/xyz"}

            captured: dict = {}

            class FakeStream:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                def raise_for_status(self):
                    pass

                async def aiter_bytes(self):
                    yield b"FILE"
                    yield b"BYTES"

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kwargs):
                    captured["post_url"] = url
                    captured["json"] = kwargs.get("json")
                    return PostResponse()

                def stream(self, method, url, **kwargs):
                    captured["get_url"] = url
                    return FakeStream()

            with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                data = await channel._download_by_code("dl_code")

            assert data == b"FILEBYTES"
            assert captured["post_url"].endswith("/v1.0/robot/messageFiles/download")
            assert captured["json"] == {"downloadCode": "dl_code", "robotCode": "robot_x"}
            assert captured["get_url"] == "https://dl.dingtalk/xyz"

        _run(go())

    def test_oversized_download_is_dropped(self, monkeypatch):
        """Inbound bytes are buffered in memory; a file over the cap must be refused.

        Outbound uploads already enforce a size cap — without an inbound one, a
        single large chat attachment balloons gateway memory.
        """

        async def go():
            from unittest.mock import patch

            channel = DingTalkChannel(MessageBus(), config={})
            channel._client_id = "robot_x"
            channel._get_access_token = AsyncMock(return_value="tok")
            monkeypatch.setattr("app.channels.dingtalk._MAX_INBOUND_FILE_SIZE_BYTES", 10)

            class PostResponse:
                status_code = 200

                @staticmethod
                def json():
                    return {"downloadUrl": "https://dl.dingtalk/big"}

            class FakeStream:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                def raise_for_status(self):
                    pass

                async def aiter_bytes(self):
                    for _ in range(4):
                        yield b"x" * 8

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kwargs):
                    return PostResponse()

                def stream(self, method, url, **kwargs):
                    return FakeStream()

            with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                assert await channel._download_by_code("dl") is None

        _run(go())

    def test_post_non_200_returns_none(self):
        async def go():
            from unittest.mock import patch

            channel = DingTalkChannel(MessageBus(), config={})
            channel._client_id = "robot_x"
            channel._get_access_token = AsyncMock(return_value="tok")

            class PostResponse:
                status_code = 403
                text = "forbidden"

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kwargs):
                    return PostResponse()

            with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                assert await channel._download_by_code("dl") is None

        _run(go())

    def test_missing_download_url_returns_none(self):
        async def go():
            from unittest.mock import patch

            channel = DingTalkChannel(MessageBus(), config={})
            channel._client_id = "robot_x"
            channel._get_access_token = AsyncMock(return_value="tok")

            class PostResponse:
                status_code = 200

                @staticmethod
                def json():
                    return {}

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kwargs):
                    return PostResponse()

            with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                assert await channel._download_by_code("dl") is None

        _run(go())


class TestHandlerStashesRawData:
    def test_process_stashes_raw_callback_payload(self):
        pytest.importorskip("dingtalk_stream")

        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            captured: dict = {}
            channel._on_chatbot_message = lambda m: captured.update(msg=m)
            handler = _DingTalkMessageHandler(channel)
            cb = MagicMock()
            cb.data = {
                "msgtype": "file",
                "content": {"downloadCode": "dc_doc", "fileName": "a.xlsx"},
                "senderStaffId": "u1",
                "conversationType": "1",
                "msgId": "m1",
            }
            await handler.process(cb)

            msg = captured["msg"]
            assert getattr(msg, "_df_raw_data", None) == cb.data
            # _extract_files can now read the document descriptor from the stash.
            assert DingTalkChannel._extract_files(msg) == [{"type": "file", "download_code": "dc_doc", "filename": "a.xlsx"}]

        _run(go())


# --- merged from test_dingtalk_channel.py (subdir-only tests; root copy is the dedup base) ---
class TestDingTalkChannelInit:
    def test_defaults(self):
        bus = MessageBus()
        channel = DingTalkChannel(bus, config={})
        assert channel.name == "dingtalk"
        assert channel._allowed_users == set()
        assert channel._cached_token == ""
        assert channel._card_template_id == ""

    def test_with_allowed_users(self):
        bus = MessageBus()
        channel = DingTalkChannel(bus, config={"allowed_users": ["u1", "u2"]})
        assert channel._allowed_users == {"u1", "u2"}

    def test_with_card_template(self):
        bus = MessageBus()
        channel = DingTalkChannel(bus, config={"card_template_id": "tpl_123"})
        assert channel._card_template_id == "tpl_123"
        assert channel.supports_streaming is True


class TestDingTalkChannelStartStop:
    def test_start_already_running(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._running = True
            await channel.start()
            assert channel._thread is None

        _run(go())

    def test_start_missing_credentials(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            await channel.start()
            assert channel._running is False

        _run(go())

    def test_stop_clears_state(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._running = True
            channel._dingtalk_client = MagicMock()
            channel._stream_client = MagicMock()
            channel._stream_client.disconnect = MagicMock()
            channel._incoming_messages["k"] = MagicMock()
            channel._card_repliers["t"] = MagicMock()
            channel._card_track_ids["s"] = "t"
            channel._thread = MagicMock()
            channel._thread.join = MagicMock()

            await channel.stop()
            assert channel._running is False
            assert channel._dingtalk_client is None

        _run(go())

    def test_stop_stream_disconnect_error(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._running = True
            channel._stream_client = MagicMock()
            channel._stream_client.disconnect.side_effect = Exception("err")
            await channel.stop()
            assert channel._running is False

        _run(go())


class TestResolveRoutingExtended:
    def test_p2p_routing(self):
        bus = MessageBus()
        channel = DingTalkChannel(bus, config={})
        msg = OutboundMessage(
            channel_name="dingtalk",
            chat_id="user1",
            thread_id="t1",
            text="hi",
            metadata={"conversation_type": "1", "sender_staff_id": "user1", "conversation_id": ""},
        )
        ct, sid, cid = channel._resolve_routing(msg)
        assert ct == "1"
        assert sid == "user1"

    def test_group_routing(self):
        bus = MessageBus()
        channel = DingTalkChannel(bus, config={})
        msg = OutboundMessage(
            channel_name="dingtalk",
            chat_id="conv1",
            thread_id="t1",
            text="hi",
            metadata={"conversation_type": "2", "sender_staff_id": "u1", "conversation_id": "conv1"},
        )
        ct, sid, cid = channel._resolve_routing(msg)
        assert ct == "2"
        assert cid == "conv1"

    def test_default_metadata(self):
        bus = MessageBus()
        channel = DingTalkChannel(bus, config={})
        msg = OutboundMessage(
            channel_name="dingtalk",
            chat_id="u1",
            thread_id="t1",
            text="hi",
            metadata={},
        )
        ct, sid, cid = channel._resolve_routing(msg)
        assert ct == "1"


class TestApiHeaders:
    def test_format(self):
        headers = DingTalkChannel._api_headers("tok")
        assert headers["x-acs-dingtalk-access-token"] == "tok"
        assert headers["Content-Type"] == "application/json"


class TestLogFutureError:
    def test_no_error(self):
        channel = DingTalkChannel(MessageBus(), config={})
        fut = MagicMock()
        fut.exception.return_value = None
        channel._log_future_error(fut, "test", "m1")

    def test_with_error(self):
        channel = DingTalkChannel(MessageBus(), config={})
        fut = MagicMock()
        fut.exception.return_value = RuntimeError("err")
        channel._log_future_error(fut, "test", "m1")

    def test_cancelled(self):
        channel = DingTalkChannel(MessageBus(), config={})
        fut = MagicMock()
        fut.exception.side_effect = asyncio.CancelledError()
        channel._log_future_error(fut, "test", "m1")

    def test_invalid_state(self):
        channel = DingTalkChannel(MessageBus(), config={})
        fut = MagicMock()
        fut.exception.side_effect = asyncio.InvalidStateError()
        channel._log_future_error(fut, "test", "m1")


class TestSendFileExtended:
    def test_file_too_large(self):
        async def go():
            from app.channels.message_bus import ResolvedAttachment

            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="u1",
                thread_id="t1",
                text="hi",
                metadata={"conversation_type": "1", "sender_staff_id": "u1"},
            )
            att = ResolvedAttachment(
                virtual_path="/tmp/big",
                actual_path=Path("/tmp/big"),
                filename="big.bin",
                mime_type="application/octet-stream",
                size=30 * 1024 * 1024,
                is_image=False,
            )
            result = await channel.send_file(msg, att)
            assert result is False

        _run(go())

    def test_upload_returns_none(self):
        async def go():
            from app.channels.message_bus import ResolvedAttachment

            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._upload_media = AsyncMock(return_value=None)
            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="u1",
                thread_id="t1",
                text="hi",
                metadata={"conversation_type": "1", "sender_staff_id": "u1"},
            )
            att = ResolvedAttachment(
                virtual_path="/tmp/f",
                actual_path=Path("/tmp/f"),
                filename="f.pdf",
                mime_type="application/pdf",
                size=1024,
                is_image=False,
            )
            result = await channel.send_file(msg, att)
            assert result is False

        _run(go())


class TestUploadMediaExtended:
    def test_success(self):
        async def go():
            import os
            import tempfile
            from unittest.mock import patch

            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "k"
            channel._cached_token = "tok"
            channel._token_expires_at = float("inf")

            class FakeResp:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"mediaId": "m123"}

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kw):
                    return FakeResp()

            with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                    f.write(b"data")
                    path = f.name
                try:
                    result = await channel._upload_media(path, "image")
                    assert result == "m123"
                finally:
                    os.unlink(path)

        _run(go())

    def test_http_error_returns_none(self):
        async def go():
            from unittest.mock import patch

            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "k"
            channel._cached_token = "tok"
            channel._token_expires_at = float("inf")

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kw):
                    raise httpx.HTTPError("fail")

            with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                result = await channel._upload_media("/tmp/nope.png", "image")
                assert result is None

        _run(go())


class TestCardModeExtended:
    def test_create_card_success(self):
        async def go():
            pytest.importorskip("dingtalk_stream")
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={"card_template_id": "tpl"})
            channel._dingtalk_client = MagicMock()
            mock_replier = MagicMock()
            mock_replier.async_create_and_deliver_card = AsyncMock(return_value="ci1")
            with patch("dingtalk_stream.card_replier.AICardReplier", return_value=mock_replier):
                result = await channel._create_and_deliver_card("text", chatbot_message=MagicMock())
            assert result == "ci1"
            assert channel._card_repliers["ci1"] is mock_replier

        _run(go())

    def test_create_card_returns_none(self):
        async def go():
            pytest.importorskip("dingtalk_stream")
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={"card_template_id": "tpl"})
            channel._dingtalk_client = MagicMock()
            mock_replier = MagicMock()
            mock_replier.async_create_and_deliver_card = AsyncMock(return_value=None)
            with patch("dingtalk_stream.card_replier.AICardReplier", return_value=mock_replier):
                result = await channel._create_and_deliver_card("text", chatbot_message=MagicMock())
            assert result is None

        _run(go())

    def test_create_card_exception(self):
        async def go():
            pytest.importorskip("dingtalk_stream")
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={"card_template_id": "tpl"})
            channel._dingtalk_client = MagicMock()
            with patch("dingtalk_stream.card_replier.AICardReplier", side_effect=Exception("err")):
                result = await channel._create_and_deliver_card("text", chatbot_message=MagicMock())
            assert result is None

        _run(go())

    def test_stream_update_card_success(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={"card_template_id": "tpl"})
            mock_replier = MagicMock()
            mock_replier.async_streaming = AsyncMock()
            channel._card_repliers["t1"] = mock_replier
            await channel._stream_update_card("t1", "content", is_finalize=True)
            mock_replier.async_streaming.assert_awaited_once()

        _run(go())

    def test_stream_update_card_error_flag(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={"card_template_id": "tpl"})
            mock_replier = MagicMock()
            mock_replier.async_streaming = AsyncMock()
            channel._card_repliers["t1"] = mock_replier
            await channel._stream_update_card("t1", "err", is_error=True)
            call_kwargs = mock_replier.async_streaming.call_args[1]
            assert call_kwargs["failed"] is True

        _run(go())


class TestRunStreamExtended:
    def test_run_stream_exception(self):
        import sys

        bus = MessageBus()
        channel = DingTalkChannel(bus, config={})
        channel._running = True
        mock_dt = MagicMock()
        mock_dt.Credential.return_value = MagicMock()
        mock_dt.DingTalkStreamClient.side_effect = Exception("init fail")
        mock_dt.chatbot.ChatbotMessage.TOPIC = "topic"
        sys.modules["dingtalk_stream"] = mock_dt
        try:
            channel._run_stream("k", "s")
            assert channel._stream_client is None
        finally:
            sys.modules.pop("dingtalk_stream", None)


class TestRunningReplyExtended:
    def test_group_running_reply(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "k"
            channel._send_text_message_to_group = AsyncMock()
            inbound = channel._make_inbound(
                chat_id="conv1",
                user_id="u1",
                text="hi",
                metadata={"conversation_type": _CONVERSATION_TYPE_GROUP, "sender_staff_id": "u1", "conversation_id": "conv1", "message_id": "m1"},
            )
            await channel._send_running_reply("conv1", inbound)
            channel._send_text_message_to_group.assert_awaited_once()

        _run(go())


class TestPrepareInbound:
    def test_order(self):
        async def go():
            bus = MessageBus()
            bus.publish_inbound = AsyncMock()
            channel = DingTalkChannel(bus, config={})
            channel._send_running_reply = AsyncMock()
            inbound = channel._make_inbound(chat_id="u1", user_id="u1", text="hi", metadata={})
            await channel._prepare_inbound("u1", inbound)
            channel._send_running_reply.assert_awaited_once()
            bus.publish_inbound.assert_awaited_once()

        _run(go())


class TestStartImportError:
    """Cover lines 152-154: dingtalk_stream not installed."""

    def test_start_returns_when_stream_not_installed(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={"client_id": "k", "client_secret": "s"})

            import sys

            saved = sys.modules.pop("dingtalk_stream", None)
            sys.modules["dingtalk_stream"] = None  # make import raise ImportError

            try:
                await channel.start()
                assert channel._running is False
                assert channel._thread is None
            finally:
                if saved is not None:
                    sys.modules["dingtalk_stream"] = saved
                else:
                    sys.modules.pop("dingtalk_stream", None)

        _run(go())


class TestStartSuccess:
    """Cover lines 163-179: successful start with valid credentials."""

    def test_start_with_valid_credentials(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(
                bus,
                config={
                    "client_id": "test_cid",
                    "client_secret": "test_secret",
                },
            )

            mock_dt = MagicMock()
            mock_dt.Credential.return_value = MagicMock()
            mock_dt.DingTalkStreamClient.return_value = MagicMock()
            mock_dt.chatbot.ChatbotMessage.TOPIC = "topic"

            import sys

            saved = sys.modules.get("dingtalk_stream")
            sys.modules["dingtalk_stream"] = mock_dt

            try:
                await channel.start()

                assert channel._running is True
                assert channel._client_id == "test_cid"
                assert channel._client_secret == "test_secret"
                assert channel._main_loop is not None
                assert channel._thread is not None
                assert channel._thread.daemon is True

                # Allow thread to finish
                channel._running = False
                channel._thread.join(timeout=2)
            finally:
                if saved is not None:
                    sys.modules["dingtalk_stream"] = saved
                else:
                    sys.modules.pop("dingtalk_stream", None)

        _run(go())

    def test_start_with_card_template_logs_info(self):
        """Cover line 168: card template info logging."""

        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(
                bus,
                config={
                    "client_id": "test_cid",
                    "client_secret": "test_secret",
                    "card_template_id": "tpl_abc",
                },
            )

            mock_dt = MagicMock()
            mock_dt.Credential.return_value = MagicMock()
            mock_dt.DingTalkStreamClient.return_value = MagicMock()
            mock_dt.chatbot.ChatbotMessage.TOPIC = "topic"

            import sys

            saved = sys.modules.get("dingtalk_stream")
            sys.modules["dingtalk_stream"] = mock_dt

            try:
                await channel.start()

                assert channel._running is True
                assert channel._card_template_id == "tpl_abc"
                assert channel.supports_streaming is True

                channel._running = False
                if channel._thread:
                    channel._thread.join(timeout=2)
            finally:
                if saved is not None:
                    sys.modules["dingtalk_stream"] = saved
                else:
                    sys.modules.pop("dingtalk_stream", None)

        _run(go())

    def test_start_missing_only_client_id(self):
        """Cover the branch where client_id is empty but client_secret exists."""

        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(
                bus,
                config={
                    "client_id": "",
                    "client_secret": "secret",
                },
            )

            mock_dt = MagicMock()
            import sys

            saved = sys.modules.get("dingtalk_stream")
            sys.modules["dingtalk_stream"] = mock_dt

            try:
                await channel.start()
                assert channel._running is False
            finally:
                if saved is not None:
                    sys.modules["dingtalk_stream"] = saved
                else:
                    sys.modules.pop("dingtalk_stream", None)

        _run(go())


class TestMarkdownFallbackGroup:
    """Cover line 287: fallback for group conversation type."""

    def test_group_fallback_uses_send_group_message(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"

            channel._send_group_message = AsyncMock()

            await channel._send_markdown_fallback("test_key", _CONVERSATION_TYPE_GROUP, "user_001", "conv_001", "hello")

            channel._send_group_message.assert_awaited_once_with("test_key", "conv_001", "hello")

        _run(go())


class TestSendFileSuccess:
    """Cover lines 307-350: complete send_file flow for image/file x P2P/group."""

    def _make_attachment(self, *, is_image=True, size=1024, filename="test.png"):
        return ResolvedAttachment(
            virtual_path=f"/tmp/{filename}",
            actual_path=Path(f"/tmp/{filename}"),
            filename=filename,
            mime_type="image/png" if is_image else "application/pdf",
            size=size,
            is_image=is_image,
        )

    def _patch_upload_and_http(self, media_id="media_001"):
        """Return context managers that patch _upload_media and httpx."""
        # Create a real temp file so _upload_media can read it
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.write(b"fake image data")
        tmp.close()

        upload_patcher = patch.object(DingTalkChannel, "_upload_media", new_callable=AsyncMock, return_value=media_id)
        return upload_patcher, tmp.name

    def test_send_image_p2p(self):
        async def go():
            upload_patcher, tmp_path = self._patch_upload_and_http()
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "robot_1"
            channel._cached_token = "tok"
            channel._token_expires_at = float("inf")

            att = ResolvedAttachment(
                virtual_path=tmp_path,
                actual_path=Path(tmp_path),
                filename="photo.png",
                mime_type="image/png",
                size=1024,
                is_image=True,
            )

            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="user_001",
                thread_id="t1",
                text="",
                metadata={
                    "conversation_type": _CONVERSATION_TYPE_P2P,
                    "sender_staff_id": "user_001",
                    "conversation_id": "",
                },
            )

            captured = []

            class FakeResp:
                def raise_for_status(self):
                    pass

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kw):
                    captured.append(kw)
                    return FakeResp()

            with upload_patcher:
                with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                    result = await channel.send_file(msg, att)

            assert result is True
            assert len(captured) == 1
            payload = captured[0]["json"]
            assert payload["msgKey"] == "sampleImageMsg"
            assert "userIds" in payload
            os.unlink(tmp_path)

        _run(go())

    def test_send_file_p2p(self):
        async def go():
            upload_patcher, tmp_path = self._patch_upload_and_http()
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "robot_1"
            channel._cached_token = "tok"
            channel._token_expires_at = float("inf")

            att = ResolvedAttachment(
                virtual_path=tmp_path,
                actual_path=Path(tmp_path),
                filename="report.pdf",
                mime_type="application/pdf",
                size=2048,
                is_image=False,
            )

            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="user_001",
                thread_id="t1",
                text="",
                metadata={
                    "conversation_type": _CONVERSATION_TYPE_P2P,
                    "sender_staff_id": "user_001",
                    "conversation_id": "",
                },
            )

            captured = []

            class FakeResp:
                def raise_for_status(self):
                    pass

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kw):
                    captured.append(kw)
                    return FakeResp()

            with upload_patcher:
                with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                    result = await channel.send_file(msg, att)

            assert result is True
            import json

            payload = captured[0]["json"]
            assert payload["msgKey"] == "sampleFile"
            param = json.loads(payload["msgParam"])
            assert param["fileName"] == "report.pdf"
            os.unlink(tmp_path)

        _run(go())

    def test_send_image_group(self):
        async def go():
            upload_patcher, tmp_path = self._patch_upload_and_http()
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "robot_1"
            channel._cached_token = "tok"
            channel._token_expires_at = float("inf")

            att = ResolvedAttachment(
                virtual_path=tmp_path,
                actual_path=Path(tmp_path),
                filename="photo.png",
                mime_type="image/png",
                size=1024,
                is_image=True,
            )

            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="conv_001",
                thread_id="t1",
                text="",
                metadata={
                    "conversation_type": _CONVERSATION_TYPE_GROUP,
                    "sender_staff_id": "user_001",
                    "conversation_id": "conv_001",
                },
            )

            captured = []

            class FakeResp:
                def raise_for_status(self):
                    pass

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kw):
                    captured.append(kw)
                    return FakeResp()

            with upload_patcher:
                with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                    result = await channel.send_file(msg, att)

            assert result is True
            payload = captured[0]["json"]
            assert payload["msgKey"] == "sampleImageMsg"
            assert "openConversationId" in payload
            os.unlink(tmp_path)

        _run(go())

    def test_send_file_group(self):
        async def go():
            upload_patcher, tmp_path = self._patch_upload_and_http()
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "robot_1"
            channel._cached_token = "tok"
            channel._token_expires_at = float("inf")

            att = ResolvedAttachment(
                virtual_path=tmp_path,
                actual_path=Path(tmp_path),
                filename="doc.pdf",
                mime_type="application/pdf",
                size=4096,
                is_image=False,
            )

            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="conv_001",
                thread_id="t1",
                text="",
                metadata={
                    "conversation_type": _CONVERSATION_TYPE_GROUP,
                    "sender_staff_id": "user_001",
                    "conversation_id": "conv_001",
                },
            )

            captured = []

            class FakeResp:
                def raise_for_status(self):
                    pass

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kw):
                    captured.append(kw)
                    return FakeResp()

            with upload_patcher:
                with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                    result = await channel.send_file(msg, att)

            assert result is True
            payload = captured[0]["json"]
            assert payload["msgKey"] == "sampleFile"
            assert "openConversationId" in payload
            os.unlink(tmp_path)

        _run(go())

    def test_send_file_http_error_returns_false(self):
        """Cover line 348: exception handler in send_file."""

        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "robot_1"

            att = self._make_attachment()

            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="user_001",
                thread_id="t1",
                text="",
                metadata={
                    "conversation_type": _CONVERSATION_TYPE_P2P,
                    "sender_staff_id": "user_001",
                },
            )

            with patch.object(DingTalkChannel, "_upload_media", new_callable=AsyncMock, return_value="media_001"):

                class FailClient:
                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *a):
                        pass

                    async def post(self, url, **kw):
                        raise httpx.HTTPError("send failed")

                with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FailClient()):
                    result = await channel.send_file(msg, att)

            assert result is False

        _run(go())


class TestRunStreamSuccess:
    """Cover lines 360-365: successful stream client setup."""

    def test_run_stream_sets_stream_client(self):
        bus = MessageBus()
        channel = DingTalkChannel(bus, config={})
        channel._running = True

        mock_dt = MagicMock()
        mock_dt.Credential.return_value = MagicMock()
        mock_dt.DingTalkStreamClient.return_value = MagicMock()
        mock_dt.chatbot.ChatbotMessage.TOPIC = "topic"

        import sys

        saved = sys.modules.get("dingtalk_stream")
        sys.modules["dingtalk_stream"] = mock_dt

        try:
            # start_forever will block, so we need to simulate an exception
            # after setup but before blocking (use Exception, not BaseException)
            mock_dt.DingTalkStreamClient.return_value.start_forever.side_effect = RuntimeError("simulated exit")

            channel._run_stream("k", "s")

            # Verify the stream setup was called
            assert mock_dt.Credential.called
            assert mock_dt.DingTalkStreamClient.called
            mock_dt.DingTalkStreamClient.return_value.register_callback_handler.assert_called_once()
            # stream_client is set to None in finally block
            assert channel._stream_client is None
        finally:
            if saved is not None:
                sys.modules["dingtalk_stream"] = saved
            else:
                sys.modules.pop("dingtalk_stream", None)

    def test_run_stream_logs_error_when_running(self):
        """Cover lines 367-368: error logging when _running is True."""
        bus = MessageBus()
        channel = DingTalkChannel(bus, config={})
        channel._running = True

        mock_dt = MagicMock()
        mock_dt.Credential.return_value = MagicMock()
        mock_dt.DingTalkStreamClient.side_effect = RuntimeError("init failed")

        import sys

        saved = sys.modules.get("dingtalk_stream")
        sys.modules["dingtalk_stream"] = mock_dt

        try:
            channel._run_stream("k", "s")
            # After error, stream_client should be None (finally block)
            assert channel._stream_client is None
        finally:
            if saved is not None:
                sys.modules["dingtalk_stream"] = saved
            else:
                sys.modules.pop("dingtalk_stream", None)

    def test_run_stream_silent_when_not_running(self):
        """Cover the case where _running is False during error (no log)."""
        bus = MessageBus()
        channel = DingTalkChannel(bus, config={})
        channel._running = False

        mock_dt = MagicMock()
        mock_dt.Credential.return_value = MagicMock()
        mock_dt.DingTalkStreamClient.side_effect = RuntimeError("init failed")

        import sys

        saved = sys.modules.get("dingtalk_stream")
        sys.modules["dingtalk_stream"] = mock_dt

        try:
            channel._run_stream("k", "s")
            assert channel._stream_client is None
        finally:
            if saved is not None:
                sys.modules["dingtalk_stream"] = saved
            else:
                sys.modules.pop("dingtalk_stream", None)


class TestOnChatbotMessageEdgeCases:
    """Cover lines 374, 442-443."""

    def test_not_running_returns_early(self):
        """Cover line 374: _on_chatbot_message when _running is False."""
        bus = MessageBus()
        bus.publish_inbound = AsyncMock()
        channel = DingTalkChannel(bus, config={})
        channel._running = False

        msg = _make_chatbot_message(text="hello")
        channel._on_chatbot_message(msg)

        bus.publish_inbound.assert_not_awaited()

    def test_exception_during_processing_caught(self):
        """Cover lines 442-443: broad exception handler."""
        bus = MessageBus()
        bus.publish_inbound = AsyncMock()
        channel = DingTalkChannel(bus, config={})
        channel._running = True

        # Create a message where accessing sender_staff_id raises
        bad_msg = MagicMock()
        type(bad_msg).sender_staff_id = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
        bad_msg.conversation_type = "1"
        bad_msg.conversation_id = "c"
        bad_msg.message_id = "m"
        bad_msg.sender_nick = "n"
        bad_msg.message_type = "text"
        bad_msg.text = None
        bad_msg.rich_text_content = None

        # Should not raise
        channel._on_chatbot_message(bad_msg)

        bus.publish_inbound.assert_not_awaited()


class TestSendRunningReplyException:
    """Cover lines 486-487: exception handler in _send_running_reply."""

    def test_running_reply_exception_caught(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "robot_1"

            # Make the text send fail
            channel._send_text_message_to_user = AsyncMock(side_effect=RuntimeError("send failed"))

            inbound = channel._make_inbound(
                chat_id="user_001",
                user_id="user_001",
                text="hi",
                metadata={
                    "conversation_type": _CONVERSATION_TYPE_P2P,
                    "sender_staff_id": "user_001",
                    "conversation_id": "",
                    "message_id": "m1",
                },
            )

            # Should not raise
            await channel._send_running_reply("user_001", inbound)

        _run(go())


class TestAccessTokenDoubleCheck:
    """Cover line 496: second check inside the lock."""

    def test_inner_lock_check_returns_cached_token(self):
        """Simulate token being refreshed by another coroutine while waiting for lock.

        When the outer check (line 492) sees an expired token but the token
        gets refreshed before the inner check (line 496) inside the lock,
        the inner check should return the cached token without making an HTTP call.
        """

        async def go():
            import time

            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "k"
            channel._client_secret = "s"

            # Start with expired token
            channel._cached_token = ""
            channel._token_expires_at = 0.0

            http_call_count = 0

            class FakeResponse:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"accessToken": "tok_from_http", "expireIn": 7200}

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kwargs):
                    nonlocal http_call_count
                    http_call_count += 1
                    return FakeResponse()

            class SimulateRefresh:
                """Lock wrapper that refreshes the token before the inner check."""

                def __init__(self, channel_ref):
                    self._channel = channel_ref
                    self._inner = asyncio.Lock()

                async def __aenter__(self):
                    await self._inner.acquire()
                    # Simulate another coroutine refreshing the token
                    # between outer check and inner check
                    self._channel._cached_token = "tok_refreshed"
                    self._channel._token_expires_at = time.monotonic() + 7200
                    return self

                async def __aexit__(self, *a):
                    self._inner.release()

            channel._token_lock = SimulateRefresh(channel)

            with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                token = await channel._get_access_token()

            # Inner check should have returned the refreshed token
            assert token == "tok_refreshed"
            # HTTP should NOT have been called since the inner check found a valid token
            assert http_call_count == 0

        _run(go())


class TestSendTextMessageToUser:
    """Cover lines 531-543: P2P text message send."""

    def test_send_text_to_user_success(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "robot_1"
            channel._cached_token = "tok"
            channel._token_expires_at = float("inf")

            captured = []

            class FakeResp:
                def raise_for_status(self):
                    pass

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kw):
                    captured.append({"url": url, **kw})
                    return FakeResp()

            with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                await channel._send_text_message_to_user("robot_1", "user_001", "hello")

            assert len(captured) == 1
            assert "oToMessages/batchSend" in captured[0]["url"]
            import json

            payload = captured[0]["json"]
            assert payload["msgKey"] == "sampleText"
            param = json.loads(payload["msgParam"])
            assert param["content"] == "hello"

        _run(go())


class TestSendTextMessageToGroup:
    """Cover lines 546-558: group text message send."""

    def test_send_text_to_group_success(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "robot_1"
            channel._cached_token = "tok"
            channel._token_expires_at = float("inf")

            captured = []

            class FakeResp:
                def raise_for_status(self):
                    pass

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kw):
                    captured.append({"url": url, **kw})
                    return FakeResp()

            with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                await channel._send_text_message_to_group("robot_1", "conv_001", "working...")

            assert len(captured) == 1
            assert "groupMessages/send" in captured[0]["url"]
            payload = captured[0]["json"]
            assert payload["msgKey"] == "sampleText"
            assert payload["openConversationId"] == "conv_001"

        _run(go())


class TestSendP2pMessage:
    """Cover lines 561-579: P2P markdown message send."""

    def test_p2p_message_with_process_query_key(self):
        """Cover lines 576-577: processQueryKey present."""

        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "robot_1"
            channel._cached_token = "tok"
            channel._token_expires_at = float("inf")

            class FakeResp:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"processQueryKey": "pqk_123"}

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kw):
                    return FakeResp()

            with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                # Should not raise
                await channel._send_p2p_message("robot_1", "user_001", "hello **world**")

        _run(go())

    def test_p2p_message_without_process_query_key(self):
        """Cover lines 578-579: warning when no processQueryKey."""

        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "robot_1"
            channel._cached_token = "tok"
            channel._token_expires_at = float("inf")

            class FakeResp:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"unexpected": "response"}

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kw):
                    return FakeResp()

            with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                # Should not raise, just log warning
                await channel._send_p2p_message("robot_1", "user_001", "hello")

        _run(go())


class TestSendGroupMessageWarning:
    """Cover line 610: warning when no processQueryKey in group send response."""

    def test_group_message_without_process_query_key(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "robot_1"
            channel._cached_token = "tok"
            channel._token_expires_at = float("inf")

            class FakeResp:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"unexpected": "data"}

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kw):
                    return FakeResp()

            with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                await channel._send_group_message("robot_1", "conv_1", "hello")

        _run(go())


class TestCreateCardImportError:
    """Cover lines 635-637: ImportError for card_replier."""

    def test_card_replier_not_available(self):
        async def go():
            import sys

            bus = MessageBus()
            channel = DingTalkChannel(bus, config={"card_template_id": "tpl"})
            channel._dingtalk_client = MagicMock()

            mock_chatbot = MagicMock()

            # Remove card_replier from dingtalk_stream module
            MagicMock(spec=["AICardReplier"])
            saved_card = sys.modules.get("dingtalk_stream.card_replier")

            # Make the card_replier import fail
            sys.modules["dingtalk_stream.card_replier"] = None

            try:
                result = await channel._create_and_deliver_card("test", chatbot_message=mock_chatbot)
                assert result is None
            finally:
                if saved_card is not None:
                    sys.modules["dingtalk_stream.card_replier"] = saved_card
                else:
                    sys.modules.pop("dingtalk_stream.card_replier", None)

        _run(go())


class TestUploadMediaInnerPaths:
    """Cover lines 692-697: JSON decode error and non-dict response in _upload_media."""

    def test_json_decode_error_with_real_file(self):
        """Cover lines 692-694: JSONDecodeError when reading upload response."""
        import json as json_mod
        import os
        import tempfile

        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "k"
            channel._cached_token = "tok"
            channel._token_expires_at = float("inf")

            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.write(b"fake data")
            tmp.close()

            class FakeResp:
                def raise_for_status(self):
                    pass

                def json(self):
                    raise json_mod.JSONDecodeError("err", "", 0)

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kw):
                    return FakeResp()

            try:
                with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                    result = await channel._upload_media(tmp.name, "image")
                assert result is None
            finally:
                os.unlink(tmp.name)

        _run(go())

    def test_non_dict_response_with_real_file(self):
        """Cover lines 696-697: non-dict JSON response from upload."""
        import os
        import tempfile

        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "k"
            channel._cached_token = "tok"
            channel._token_expires_at = float("inf")

            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp.write(b"fake data")
            tmp.close()

            class FakeResp:
                def raise_for_status(self):
                    pass

                def json(self):
                    return ["not", "a", "dict"]

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kw):
                    return FakeResp()

            try:
                with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                    result = await channel._upload_media(tmp.name, "file")
                assert result is None
            finally:
                os.unlink(tmp.name)

        _run(go())


class TestOnChatbotMessageMainLoopNotRunning:
    """Cover line 441: main loop not running warning."""

    def test_main_loop_none(self):
        """When _main_loop is None, should log warning."""
        bus = MessageBus()
        bus.publish_inbound = AsyncMock()
        channel = DingTalkChannel(bus, config={})
        channel._running = True
        channel._main_loop = None

        msg = _make_chatbot_message(text="hello")
        channel._on_chatbot_message(msg)

        bus.publish_inbound.assert_not_awaited()

    def test_main_loop_not_running(self):
        """When _main_loop.is_running() returns False, should log warning."""
        bus = MessageBus()
        bus.publish_inbound = AsyncMock()
        channel = DingTalkChannel(bus, config={})
        channel._running = True
        channel._main_loop = MagicMock()
        channel._main_loop.is_running.return_value = False

        msg = _make_chatbot_message(text="hello")
        channel._on_chatbot_message(msg)

        bus.publish_inbound.assert_not_awaited()


class TestCardStreamFailureNonFinal:
    """Cover the branch where card stream fails for non-final message."""

    def test_non_final_card_stream_failure_skips(self):
        """When card stream fails for non-final, should skip (not finalize)."""

        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={"card_template_id": "tpl"})
            channel._client_id = "test_key"

            channel._stream_update_card = AsyncMock(side_effect=ConnectionError("fail"))
            channel._send_markdown_fallback = AsyncMock()

            source_key = f"{_CONVERSATION_TYPE_P2P}:user_001::msg_001"
            channel._card_track_ids[source_key] = "track_001"

            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="user_001",
                thread_id="thread_001",
                text="Partial...",
                is_final=False,
                thread_ts="msg_001",
                metadata={
                    "conversation_type": _CONVERSATION_TYPE_P2P,
                    "sender_staff_id": "user_001",
                    "conversation_id": "",
                },
            )

            # For non-final: stream fails but since it's not final, the code
            # enters the except block, but since is_final is False,
            # it does NOT call markdown fallback.
            # It falls through to the `return` at line 248
            await channel.send(msg)

            # Track should NOT be cleaned up (not final)
            assert source_key in channel._card_track_ids

        _run(go())


class TestStopWithoutStreamClient:
    """Cover the case where stop() is called without a stream client."""

    def test_stop_without_stream(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._running = True
            channel._stream_client = None
            channel._dingtalk_client = MagicMock()

            await channel.stop()
            assert channel._running is False
            assert channel._dingtalk_client is None

        _run(go())

    def test_stop_stream_without_disconnect(self):
        """Cover the hasattr check for disconnect."""

        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._running = True
            # Stream client without disconnect method
            mock_stream = MagicMock(spec=[])  # no attributes
            channel._stream_client = mock_stream

            await channel.stop()
            assert channel._running is False
            assert channel._stream_client is None

        _run(go())


class TestOnChatbotMessageCardStorage:
    """Cover lines 428-431: storing incoming message for card mode with lock."""

    def test_card_mode_stores_message_with_lock(self):
        bus = MessageBus()
        bus.publish_inbound = AsyncMock()
        channel = DingTalkChannel(bus, config={"card_template_id": "tpl_123"})
        channel._running = True
        channel._main_loop = MagicMock()
        channel._main_loop.is_running.return_value = True

        msg = _make_chatbot_message(
            text="hello",
            sender_staff_id="u1",
            message_id="msg_001",
        )
        channel._on_chatbot_message(msg)

        # Check message was stored
        assert len(channel._incoming_messages) == 1
        key = list(channel._incoming_messages.keys())[0]
        assert "u1" in key
        assert "msg_001" in key


class TestSendP2pMarkdownAdaptation:
    """Cover line 561: markdown is adapted before sending."""

    def test_p2p_message_adapts_markdown(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "robot_1"
            channel._cached_token = "tok"
            channel._token_expires_at = float("inf")

            captured = []

            class FakeResp:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"processQueryKey": "ok"}

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kw):
                    captured.append(kw)
                    return FakeResp()

            with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                await channel._send_p2p_message("robot_1", "u1", "Use `pip install` here")

            import json

            payload = captured[0]["json"]
            param = json.loads(payload["msgParam"])
            # `pip install` should be converted to **pip install**
            assert "**pip install**" in param["text"]

        _run(go())


class TestSendGroupMarkdownAdaptation:
    """Cover line 591: markdown is adapted before group send."""

    def test_group_message_adapts_markdown(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "robot_1"
            channel._cached_token = "tok"
            channel._token_expires_at = float("inf")

            captured = []

            class FakeResp:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"processQueryKey": "ok"}

            class FakeClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    pass

                async def post(self, url, **kw):
                    captured.append(kw)
                    return FakeResp()

            with patch("app.channels.dingtalk.httpx.AsyncClient", return_value=FakeClient()):
                await channel._send_group_message("robot_1", "conv_1", "Run `make test`")

            import json

            payload = captured[0]["json"]
            param = json.loads(payload["msgParam"])
            assert "**make test**" in param["text"]

        _run(go())


class TestSendRetrySleep:
    """Cover the asyncio.sleep delay between retries."""

    def test_retry_delays_are_pow2(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._client_id = "test_key"
            channel._client_secret = "test_secret"

            delays = []

            async def flaky_send(robot_code, user_id, text):
                raise ConnectionError("fail")

            async def fake_sleep(delay):
                delays.append(delay)

            channel._send_p2p_message = AsyncMock(side_effect=flaky_send)

            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="user_001",
                thread_id="thread_001",
                text="hello",
                metadata={"conversation_type": _CONVERSATION_TYPE_P2P, "sender_staff_id": "user_001"},
            )

            with patch("app.channels.dingtalk.asyncio.sleep", side_effect=fake_sleep):
                with pytest.raises(ConnectionError):
                    await channel.send(msg)

            # 3 retries means 2 sleeps (after attempt 0 and 1)
            assert delays == [1, 2]

        _run(go())


class TestOnOutboundForwarding:
    """Cover _on_outbound from base Channel class."""

    def test_on_outbound_sends_for_matching_channel(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel.send = AsyncMock()
            channel.send_file = AsyncMock(return_value=True)

            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="u1",
                thread_id="t1",
                text="hi",
                metadata={},
            )

            await channel._on_outbound(msg)
            channel.send.assert_awaited_once_with(msg)

        _run(go())

    def test_on_outbound_skips_non_matching_channel(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel.send = AsyncMock()

            msg = OutboundMessage(
                channel_name="telegram",
                chat_id="u1",
                thread_id="t1",
                text="hi",
                metadata={},
            )

            await channel._on_outbound(msg)
            channel.send.assert_not_awaited()

        _run(go())

    def test_on_outbound_send_failure_skips_files(self):
        """Cover base.py line 104: return after send failure skips file uploads."""

        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel.send = AsyncMock(side_effect=RuntimeError("send failed"))
            channel.send_file = AsyncMock()

            att = ResolvedAttachment(
                virtual_path="/tmp/f",
                actual_path=Path("/tmp/f"),
                filename="f.pdf",
                mime_type="application/pdf",
                size=100,
                is_image=False,
            )
            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="u1",
                thread_id="t1",
                text="hi",
                metadata={},
                attachments=[att],
            )

            await channel._on_outbound(msg)
            channel.send_file.assert_not_awaited()

        _run(go())

    def test_on_outbound_file_upload_failure_caught(self):
        """Cover base.py line 112: exception during file upload."""

        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel.send = AsyncMock()
            channel.send_file = AsyncMock(side_effect=RuntimeError("upload failed"))

            att = ResolvedAttachment(
                virtual_path="/tmp/f",
                actual_path=Path("/tmp/f"),
                filename="f.pdf",
                mime_type="application/pdf",
                size=100,
                is_image=False,
            )
            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="u1",
                thread_id="t1",
                text="hi",
                metadata={},
                attachments=[att],
            )

            # Should not raise
            await channel._on_outbound(msg)

        _run(go())

    def test_on_outbound_file_upload_returns_false(self):
        """Cover base.py line 110: file upload returns False."""

        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel.send = AsyncMock()
            channel.send_file = AsyncMock(return_value=False)

            att = ResolvedAttachment(
                virtual_path="/tmp/f",
                actual_path=Path("/tmp/f"),
                filename="f.pdf",
                mime_type="application/pdf",
                size=100,
                is_image=False,
            )
            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="u1",
                thread_id="t1",
                text="hi",
                metadata={},
                attachments=[att],
            )

            await channel._on_outbound(msg)

        _run(go())


class TestOnChatbotMessageEventLoop:
    """Cover inbound scheduling onto the running main loop."""

    def test_schedules_via_event_loop(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={})
            channel._running = True
            channel._main_loop = asyncio.get_running_loop()

            channel._send_running_reply = AsyncMock()

            msg = _make_chatbot_message(text="hello via loop")
            channel._on_chatbot_message(msg)

            # Allow scheduled coroutine to complete
            await asyncio.sleep(0.1)

            inbound = bus.get_inbound_nowait()
            assert inbound.text == "hello via loop"

        _run(go())


class TestCardModeSkipNonFinal:
    """Cover line 229: skip non-final when card mode enabled but no track."""

    def test_skip_when_no_track_and_not_final(self):
        async def go():
            bus = MessageBus()
            channel = DingTalkChannel(bus, config={"card_template_id": "tpl"})
            channel._client_id = "test_key"
            channel._send_p2p_message = AsyncMock()

            msg = OutboundMessage(
                channel_name="dingtalk",
                chat_id="user_001",
                thread_id="t1",
                text="partial",
                is_final=False,
                thread_ts="msg_001",
                metadata={
                    "conversation_type": _CONVERSATION_TYPE_P2P,
                    "sender_staff_id": "user_001",
                    "conversation_id": "",
                },
            )

            await channel.send(msg)
            channel._send_p2p_message.assert_not_called()

        _run(go())


class TestNormalizeConversationTypeExtended:
    """Additional edge cases for _normalize_conversation_type."""

    def test_string_group(self):
        assert _normalize_conversation_type("2") == _CONVERSATION_TYPE_GROUP

    def test_string_p2p(self):
        assert _normalize_conversation_type("1") == _CONVERSATION_TYPE_P2P

    def test_unknown_value_defaults_p2p(self):
        assert _normalize_conversation_type("99") == _CONVERSATION_TYPE_P2P

    def test_float_value(self):
        assert _normalize_conversation_type(2.0) == _CONVERSATION_TYPE_P2P
        assert _normalize_conversation_type("2.0") == _CONVERSATION_TYPE_P2P


class TestExtractTextExtended:
    """Additional edge cases for _extract_text."""

    def test_text_with_only_whitespace(self):
        msg = _make_chatbot_message(text="   \n\t  ")
        assert DingTalkChannel._extract_text(msg) == ""

    def test_rich_text_empty_list(self):
        msg = _make_chatbot_message(
            message_type="richText",
            rich_text_list=[],
        )
        assert DingTalkChannel._extract_text(msg) == ""

    def test_rich_text_with_non_dict_items(self):
        msg = _make_chatbot_message(
            message_type="richText",
            rich_text_list=["not_a_dict", 123, None],
        )
        assert DingTalkChannel._extract_text(msg) == ""
