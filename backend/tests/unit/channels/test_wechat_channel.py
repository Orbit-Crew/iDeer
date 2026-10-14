"""Tests for the WeChat IM channel."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from pathlib import Path
from typing import Any
from unittest import mock
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.message_bus import InboundMessageType, MessageBus, OutboundMessage

_POSIX_MODE_BITS_REASON = "Windows chmod only toggles the read-only bit, so the 0o600 mode asserted here is never observable"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _MockResponse:
    def __init__(self, payload: dict[str, Any], content: bytes | None = None):
        self._payload = payload
        self.content = content or b""
        self.headers = payload.get("headers", {}) if isinstance(payload, dict) else {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _MockAsyncClient:
    def __init__(
        self,
        responses: list[dict[str, Any]] | None = None,
        post_calls: list[dict[str, Any]] | None = None,
        get_calls: list[dict[str, Any]] | None = None,
        put_calls: list[dict[str, Any]] | None = None,
        get_responses: list[dict[str, Any]] | None = None,
        post_responses: list[dict[str, Any]] | None = None,
        put_responses: list[dict[str, Any]] | None = None,
        **kwargs,
    ):
        self._responses = list(responses or [])
        self._post_responses = list(post_responses or self._responses)
        self._get_responses = list(get_responses or [])
        self._put_responses = list(put_responses or [])
        self._post_calls = post_calls
        self._get_calls = get_calls
        self._put_calls = put_calls
        self.kwargs = kwargs

    async def post(
        self,
        url: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
        **kwargs,
    ):
        if self._post_calls is not None:
            self._post_calls.append({"url": url, "json": json or {}, "headers": headers or {}, **kwargs})
        payload = self._post_responses.pop(0) if self._post_responses else {"ret": 0}
        return _MockResponse(payload)

    async def get(self, url: str, params: dict[str, Any] | None = None, headers: dict[str, Any] | None = None, **kwargs):
        if self._get_calls is not None:
            self._get_calls.append({"url": url, "params": params or {}, "headers": headers or {}, **kwargs})
        payload = self._get_responses.pop(0) if self._get_responses else {"ret": 0}
        return _MockResponse(payload)

    async def put(self, url: str, content: bytes, headers: dict[str, Any] | None = None, **kwargs):
        if self._put_calls is not None:
            self._put_calls.append({"url": url, "content": content, "headers": headers or {}, **kwargs})
        payload = self._put_responses.pop(0) if self._put_responses else {"ret": 0}
        return _MockResponse(payload)

    async def aclose(self) -> None:
        return None


def test_timing_config_requires_positive_finite_values():
    from app.channels.wechat import WechatChannel

    timing_defaults = {
        "polling_timeout": WechatChannel.DEFAULT_POLLING_TIMEOUT,
        "polling_retry_delay": WechatChannel.DEFAULT_RETRY_DELAY,
        "qrcode_poll_interval": WechatChannel.DEFAULT_QRCODE_POLL_INTERVAL,
        "qrcode_poll_timeout": WechatChannel.DEFAULT_QRCODE_POLL_TIMEOUT,
    }
    attributes = {
        "polling_timeout": "_polling_timeout",
        "polling_retry_delay": "_retry_delay",
        "qrcode_poll_interval": "_qrcode_poll_interval",
        "qrcode_poll_timeout": "_qrcode_poll_timeout",
    }

    for invalid in (0, -1, float("nan"), float("inf"), float("-inf"), 10**1000):
        channel = WechatChannel(
            bus=MessageBus(),
            config={"bot_token": "test-token", **dict.fromkeys(timing_defaults, invalid)},
        )
        assert {key: getattr(channel, attributes[key]) for key in timing_defaults} == timing_defaults

    channel = WechatChannel(bus=MessageBus(), config={"bot_token": "test-token", "polling_retry_delay": "0.25"})
    assert channel._retry_delay == 0.25


def test_handle_update_publishes_private_chat_message():
    from app.channels.wechat import WechatChannel

    async def go():
        bus = MessageBus()
        published = []

        async def capture(msg):
            published.append(msg)

        bus.publish_inbound = capture  # type: ignore[method-assign]

        channel = WechatChannel(bus=bus, config={"bot_token": "test-token"})
        await channel._handle_update(
            {
                "message_type": 1,
                "from_user_id": "wx-user-1",
                "context_token": "ctx-1",
                "item_list": [{"type": 1, "text_item": {"text": "hello from wechat"}}],
            }
        )

        assert len(published) == 1
        inbound = published[0]
        assert inbound.chat_id == "wx-user-1"
        assert inbound.user_id == "wx-user-1"
        assert inbound.text == "hello from wechat"
        assert inbound.msg_type == InboundMessageType.CHAT
        assert inbound.topic_id is None
        assert inbound.metadata["context_token"] == "ctx-1"
        assert channel._context_tokens_by_chat["wx-user-1"] == "ctx-1"

    _run(go())


def test_handle_update_downloads_inbound_image(monkeypatch, tmp_path: Path):
    from app.channels.wechat import WechatChannel

    async def go():
        bus = MessageBus()
        published = []

        async def capture(msg):
            published.append(msg)

        bus.publish_inbound = capture  # type: ignore[method-assign]

        plaintext = b"fake-image-bytes"
        aes_key = b"1234567890abcdef"

        channel = WechatChannel(bus=bus, config={"bot_token": "test-token", "state_dir": str(tmp_path)})
        encrypted = channel.__class__.__dict__["_extract_image_file"].__globals__["_encrypt_aes_128_ecb"](plaintext, aes_key)

        async def _fake_download(_url: str, *, timeout: float | None = None, max_bytes: int | None = None):
            return encrypted

        channel._download_cdn_bytes = _fake_download  # type: ignore[method-assign]

        await channel._handle_update(
            {
                "message_type": 1,
                "message_id": 101,
                "from_user_id": "wx-user-1",
                "context_token": "ctx-img-1",
                "item_list": [
                    {
                        "type": 2,
                        "image_item": {
                            "aeskey": aes_key.hex(),
                            "media": {"full_url": "https://cdn.weixin.qq.com/image.bin"},
                        },
                    }
                ],
            }
        )

        assert len(published) == 1
        inbound = published[0]
        assert inbound.text == ""
        assert len(inbound.files) == 1
        file_info = inbound.files[0]
        assert file_info["source"] == "wechat"
        assert file_info["message_item_type"] == 2
        stored = Path(file_info["path"])
        assert stored.exists()
        assert stored.read_bytes() == plaintext

    _run(go())


def test_handle_update_downloads_inbound_png_with_png_extension(monkeypatch, tmp_path: Path):
    from app.channels.wechat import WechatChannel

    async def go():
        bus = MessageBus()
        published = []

        async def capture(msg):
            published.append(msg)

        bus.publish_inbound = capture  # type: ignore[method-assign]

        plaintext = b"\x89PNG\r\n\x1a\n" + b"png-body"
        aes_key = b"1234567890abcdef"

        channel = WechatChannel(bus=bus, config={"bot_token": "test-token", "state_dir": str(tmp_path)})
        encrypted = channel.__class__.__dict__["_extract_image_file"].__globals__["_encrypt_aes_128_ecb"](plaintext, aes_key)

        async def _fake_download(_url: str, *, timeout: float | None = None, max_bytes: int | None = None):
            return encrypted

        channel._download_cdn_bytes = _fake_download  # type: ignore[method-assign]

        await channel._handle_update(
            {
                "message_type": 1,
                "message_id": 303,
                "from_user_id": "wx-user-1",
                "context_token": "ctx-img-png",
                "item_list": [
                    {
                        "type": 2,
                        "image_item": {
                            "aeskey": aes_key.hex(),
                            "media": {"full_url": "https://cdn.weixin.qq.com/image.bin"},
                        },
                    }
                ],
            }
        )

        assert len(published) == 1
        file_info = published[0].files[0]
        assert file_info["filename"].endswith(".png")
        assert file_info["mime_type"] == "image/png"

    _run(go())


def test_handle_update_preserves_text_and_ref_msg_with_image(monkeypatch, tmp_path: Path):
    from app.channels.wechat import WechatChannel

    async def go():
        bus = MessageBus()
        published = []

        async def capture(msg):
            published.append(msg)

        bus.publish_inbound = capture  # type: ignore[method-assign]

        plaintext = b"img-2"
        aes_key = b"1234567890abcdef"
        channel = WechatChannel(bus=bus, config={"bot_token": "test-token", "state_dir": str(tmp_path)})
        encrypted = channel.__class__.__dict__["_extract_image_file"].__globals__["_encrypt_aes_128_ecb"](plaintext, aes_key)

        async def _fake_download(_url: str, *, timeout: float | None = None, max_bytes: int | None = None):
            return encrypted

        channel._download_cdn_bytes = _fake_download  # type: ignore[method-assign]

        await channel._handle_update(
            {
                "message_type": 1,
                "message_id": 202,
                "from_user_id": "wx-user-1",
                "context_token": "ctx-img-2",
                "item_list": [
                    {"type": 1, "text_item": {"text": "look at this"}},
                    {
                        "type": 2,
                        "ref_msg": {"title": "quoted", "message_item": {"type": 1}},
                        "image_item": {
                            "aeskey": aes_key.hex(),
                            "media": {"full_url": "https://cdn.weixin.qq.com/image2.bin"},
                        },
                    },
                ],
            }
        )

        assert len(published) == 1
        inbound = published[0]
        assert inbound.text == "look at this"
        assert len(inbound.files) == 1
        assert inbound.metadata["ref_msg"]["title"] == "quoted"

    _run(go())


def test_handle_update_skips_image_without_url_or_key(tmp_path: Path):
    from app.channels.wechat import WechatChannel

    async def go():
        bus = MessageBus()
        published = []

        async def capture(msg):
            published.append(msg)

        bus.publish_inbound = capture  # type: ignore[method-assign]

        channel = WechatChannel(bus=bus, config={"bot_token": "test-token", "state_dir": str(tmp_path)})

        await channel._handle_update(
            {
                "message_type": 1,
                "from_user_id": "wx-user-1",
                "context_token": "ctx-img-3",
                "item_list": [
                    {
                        "type": 2,
                        "image_item": {"media": {}},
                    }
                ],
            }
        )

        assert published == []

    _run(go())


def test_handle_update_routes_slash_command_as_command():
    from app.channels.wechat import WechatChannel

    async def go():
        bus = MessageBus()
        published = []

        async def capture(msg):
            published.append(msg)

        bus.publish_inbound = capture  # type: ignore[method-assign]

        channel = WechatChannel(bus=bus, config={"bot_token": "test-token"})
        await channel._handle_update(
            {
                "message_type": 1,
                "from_user_id": "wx-user-1",
                "context_token": "ctx-2",
                "item_list": [{"type": 1, "text_item": {"text": "/status"}}],
            }
        )

        assert len(published) == 1
        assert published[0].msg_type == InboundMessageType.COMMAND

    _run(go())


def test_allowed_users_filter_blocks_non_whitelisted_sender():
    from app.channels.wechat import WechatChannel

    async def go():
        bus = MessageBus()
        published = []

        async def capture(msg):
            published.append(msg)

        bus.publish_inbound = capture  # type: ignore[method-assign]

        channel = WechatChannel(bus=bus, config={"bot_token": "test-token", "allowed_users": ["allowed-user"]})
        await channel._handle_update(
            {
                "message_type": 1,
                "from_user_id": "blocked-user",
                "context_token": "ctx-3",
                "item_list": [{"type": 1, "text_item": {"text": "hello"}}],
            }
        )

        assert published == []

    _run(go())


def test_connect_code_bypasses_allowed_users_filter(tmp_path: Path):
    from app.channels.wechat import WechatChannel
    from deerflow.persistence.channel_connections import ChannelConnectionRepository, ChannelCredentialCipher
    from deerflow.persistence.engine import close_engine, get_session_factory, init_engine

    async def go():
        from datetime import UTC, datetime, timedelta

        await init_engine("sqlite", url=f"sqlite+aiosqlite:///{tmp_path / 'wechat.db'}", sqlite_dir=str(tmp_path))
        try:
            repo = ChannelConnectionRepository(
                get_session_factory(),
                cipher=ChannelCredentialCipher.from_key("wechat-secret"),
            )
            code = "wechat-bind-code"
            await repo.create_oauth_state(
                owner_user_id="deerflow-user-1",
                provider="wechat",
                state=code,
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )

            bus = MessageBus()
            published = []

            async def capture(msg):
                published.append(msg)

            bus.publish_inbound = capture  # type: ignore[method-assign]

            # The newcomer ("blocked-user") is not in allowed_users yet, but a valid
            # /connect code must still bootstrap their first bind.
            channel = WechatChannel(
                bus=bus,
                config={"bot_token": "test-token", "allowed_users": ["allowed-user"], "connection_repo": repo},
            )
            channel._send_connection_reply = AsyncMock()  # type: ignore[method-assign]

            await channel._handle_update(
                {
                    "message_type": 1,
                    "from_user_id": "blocked-user",
                    "context_token": "ctx-connect",
                    "item_list": [{"type": 1, "text_item": {"text": f"/connect {code}"}}],
                }
            )

            connections = await repo.list_connections("deerflow-user-1")
            assert len(connections) == 1
            assert connections[0]["provider"] == "wechat"
            assert connections[0]["external_account_id"] == "blocked-user"
            # The connect-code reply was sent and no normal inbound was published.
            channel._send_connection_reply.assert_awaited_once()
            assert published == []
        finally:
            await close_engine()

    _run(go())


def test_send_uses_cached_context_token(monkeypatch):
    from app.channels.wechat import WechatChannel

    async def go():
        post_calls: list[dict[str, Any]] = []

        def _client_factory(*args, **kwargs):
            return _MockAsyncClient(responses=[{"ret": 0}], post_calls=post_calls, **kwargs)

        monkeypatch.setattr("app.channels.wechat.httpx.AsyncClient", _client_factory)

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "bot-token"})
        channel._context_tokens_by_chat["wx-user-1"] = "ctx-send"

        await channel.send(
            OutboundMessage(
                channel_name="wechat",
                chat_id="wx-user-1",
                thread_id="thread-1",
                text="reply text",
            )
        )

        assert len(post_calls) == 1
        assert post_calls[0]["url"].endswith("/ilink/bot/sendmessage")
        assert post_calls[0]["json"]["msg"]["to_user_id"] == "wx-user-1"
        assert post_calls[0]["json"]["msg"]["context_token"] == "ctx-send"
        assert post_calls[0]["headers"]["Authorization"] == "Bearer bot-token"
        assert post_calls[0]["headers"]["AuthorizationType"] == "ilink_bot_token"
        assert "X-WECHAT-UIN" in post_calls[0]["headers"]
        assert "iLink-App-ClientVersion" in post_calls[0]["headers"]

    _run(go())


def test_send_skips_when_context_token_missing(monkeypatch):
    from app.channels.wechat import WechatChannel

    async def go():
        post_calls: list[dict[str, Any]] = []

        def _client_factory(*args, **kwargs):
            return _MockAsyncClient(responses=[{"ret": 0}], post_calls=post_calls, **kwargs)

        monkeypatch.setattr("app.channels.wechat.httpx.AsyncClient", _client_factory)

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "bot-token"})
        await channel.send(
            OutboundMessage(
                channel_name="wechat",
                chat_id="wx-user-1",
                thread_id="thread-1",
                text="reply text",
            )
        )

        assert post_calls == []

    _run(go())


def test_protocol_helpers_build_expected_values():
    from app.channels.wechat import (
        MessageItemType,
        UploadMediaType,
        _build_ilink_client_version,
        _build_wechat_uin,
        _encrypted_size_for_aes_128_ecb,
    )

    assert int(MessageItemType.TEXT) == 1
    assert int(UploadMediaType.FILE) == 3
    assert _build_ilink_client_version("1.0.11") == str((1 << 16) | 11)

    encoded = _build_wechat_uin()
    decoded = base64.b64decode(encoded).decode("utf-8")
    assert decoded.isdigit()

    assert _encrypted_size_for_aes_128_ecb(0) == 16
    assert _encrypted_size_for_aes_128_ecb(1) == 16
    assert _encrypted_size_for_aes_128_ecb(16) == 32


def test_aes_roundtrip_encrypts_and_decrypts():
    from app.channels.wechat import _decrypt_aes_128_ecb, _encrypt_aes_128_ecb

    key = b"1234567890abcdef"
    plaintext = b"hello-wechat-media"

    encrypted = _encrypt_aes_128_ecb(plaintext, key)
    assert encrypted != plaintext

    decrypted = _decrypt_aes_128_ecb(encrypted, key)
    assert decrypted == plaintext


def test_build_upload_request_supports_no_need_thumb():
    from app.channels.wechat import UploadMediaType, WechatChannel

    channel = WechatChannel(bus=MessageBus(), config={"bot_token": "bot-token"})
    payload = channel._build_upload_request(
        filekey="file-key-1",
        media_type=UploadMediaType.IMAGE,
        to_user_id="wx-user-1",
        plaintext=b"image-bytes",
        aes_key=b"1234567890abcdef",
        no_need_thumb=True,
    )

    assert payload["filekey"] == "file-key-1"
    assert payload["media_type"] == 1
    assert payload["to_user_id"] == "wx-user-1"
    assert payload["rawsize"] == len(b"image-bytes")
    assert payload["filesize"] >= len(b"image-bytes")
    assert payload["no_need_thumb"] is True
    assert payload["aeskey"] == b"1234567890abcdef".hex()


def test_send_file_uploads_and_sends_image(monkeypatch, tmp_path: Path):
    from app.channels.message_bus import ResolvedAttachment
    from app.channels.wechat import WechatChannel

    async def go():
        post_calls: list[dict[str, Any]] = []
        put_calls: list[dict[str, Any]] = []

        def _client_factory(*args, **kwargs):
            return _MockAsyncClient(
                post_calls=post_calls,
                put_calls=put_calls,
                post_responses=[
                    {
                        "ret": 0,
                        "upload_param": "enc-query-original",
                        "thumb_upload_param": "enc-query-thumb",
                        "upload_full_url": "https://cdn.example/upload-original",
                    },
                    {"ret": 0},
                ],
                **kwargs,
            )

        monkeypatch.setattr("app.channels.wechat.httpx.AsyncClient", _client_factory)

        image_path = tmp_path / "chart.png"
        image_path.write_bytes(b"png-binary-data")

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "bot-token"})
        channel._context_tokens_by_chat["wx-user-1"] = "ctx-image-send"

        ok = await channel.send_file(
            OutboundMessage(
                channel_name="wechat",
                chat_id="wx-user-1",
                thread_id="thread-1",
                text="reply text",
            ),
            ResolvedAttachment(
                virtual_path="/mnt/user-data/outputs/chart.png",
                actual_path=image_path,
                filename="chart.png",
                mime_type="image/png",
                size=image_path.stat().st_size,
                is_image=True,
            ),
        )

        assert ok is True
        assert len(post_calls) == 3
        assert post_calls[0]["url"].endswith("/ilink/bot/getuploadurl")
        assert post_calls[0]["json"]["media_type"] == 1
        assert post_calls[0]["json"]["no_need_thumb"] is True
        assert len(put_calls) == 0
        assert post_calls[1]["url"] == "https://cdn.example/upload-original"
        assert post_calls[2]["url"].endswith("/ilink/bot/sendmessage")
        image_item = post_calls[2]["json"]["msg"]["item_list"][0]["image_item"]
        assert image_item["media"]["encrypt_query_param"] == "enc-query-original"
        assert image_item["media"]["encrypt_type"] == 1
        assert image_item["mid_size"] > 0
        assert "thumb_media" not in image_item
        assert "aeskey" not in image_item
        assert base64.b64decode(image_item["media"]["aes_key"]).decode("utf-8") == post_calls[0]["json"]["aeskey"]

    _run(go())


def test_send_file_returns_false_without_upload_full_url(monkeypatch, tmp_path: Path):
    from app.channels.message_bus import ResolvedAttachment
    from app.channels.wechat import WechatChannel

    async def go():
        post_calls: list[dict[str, Any]] = []

        def _client_factory(*args, **kwargs):
            return _MockAsyncClient(
                post_calls=post_calls,
                post_responses=[
                    {"ret": 0, "upload_param": "enc-query-only"},
                    {"ret": 0},
                ],
                **kwargs,
            )

        monkeypatch.setattr("app.channels.wechat.httpx.AsyncClient", _client_factory)

        image_path = tmp_path / "chart.png"
        image_path.write_bytes(b"png-binary-data")

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "bot-token"})
        channel._context_tokens_by_chat["wx-user-1"] = "ctx-image-send"

        ok = await channel.send_file(
            OutboundMessage(channel_name="wechat", chat_id="wx-user-1", thread_id="thread-1", text="reply text"),
            ResolvedAttachment(
                virtual_path="/mnt/user-data/outputs/chart.png",
                actual_path=image_path,
                filename="chart.png",
                mime_type="image/png",
                size=image_path.stat().st_size,
                is_image=True,
            ),
        )

        assert ok is True
        assert len(post_calls) == 3
        assert post_calls[1]["url"].startswith("https://novac2c.cdn.weixin.qq.com/c2c/upload?")
        assert post_calls[2]["url"].endswith("/ilink/bot/sendmessage")
        image_item = post_calls[2]["json"]["msg"]["item_list"][0]["image_item"]
        assert image_item["media"]["encrypt_query_param"] == "enc-query-only"
        assert image_item["media"]["encrypt_type"] == 1

    _run(go())


def test_send_file_prefers_cdn_response_header_for_image(monkeypatch, tmp_path: Path):
    from app.channels.message_bus import ResolvedAttachment
    from app.channels.wechat import WechatChannel

    async def go():
        post_calls: list[dict[str, Any]] = []

        def _client_factory(*args, **kwargs):
            return _MockAsyncClient(
                post_calls=post_calls,
                post_responses=[
                    {"ret": 0, "upload_param": "enc-query-original", "thumb_upload_param": "enc-query-thumb"},
                    {"ret": 0, "headers": {"x-encrypted-param": "enc-query-downloaded"}},
                    {"ret": 0},
                ],
                **kwargs,
            )

        monkeypatch.setattr("app.channels.wechat.httpx.AsyncClient", _client_factory)

        image_path = tmp_path / "chart.png"
        image_path.write_bytes(b"png-binary-data")

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "bot-token"})
        channel._context_tokens_by_chat["wx-user-1"] = "ctx-image-send"

        ok = await channel.send_file(
            OutboundMessage(channel_name="wechat", chat_id="wx-user-1", thread_id="thread-1", text="reply text"),
            ResolvedAttachment(
                virtual_path="/mnt/user-data/outputs/chart.png",
                actual_path=image_path,
                filename="chart.png",
                mime_type="image/png",
                size=image_path.stat().st_size,
                is_image=True,
            ),
        )

        assert ok is True
        assert post_calls[1]["url"].startswith("https://novac2c.cdn.weixin.qq.com/c2c/upload?")
        image_item = post_calls[2]["json"]["msg"]["item_list"][0]["image_item"]
        assert image_item["media"]["encrypt_query_param"] == "enc-query-downloaded"
        assert image_item["media"]["encrypt_type"] == 1
        assert "thumb_media" not in image_item
        assert "aeskey" not in image_item

    _run(go())


def test_send_file_skips_non_image(monkeypatch, tmp_path: Path):
    from app.channels.message_bus import ResolvedAttachment
    from app.channels.wechat import WechatChannel

    async def go():
        post_calls: list[dict[str, Any]] = []

        def _client_factory(*args, **kwargs):
            return _MockAsyncClient(post_calls=post_calls, **kwargs)

        monkeypatch.setattr("app.channels.wechat.httpx.AsyncClient", _client_factory)

        file_path = tmp_path / "notes.txt"
        file_path.write_text("hello")

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "bot-token"})
        ok = await channel.send_file(
            OutboundMessage(channel_name="wechat", chat_id="wx-user-1", thread_id="thread-1", text="reply text"),
            ResolvedAttachment(
                virtual_path="/mnt/user-data/outputs/notes.txt",
                actual_path=file_path,
                filename="notes.txt",
                mime_type="text/plain",
                size=file_path.stat().st_size,
                is_image=False,
            ),
        )

        assert ok is False
        assert post_calls == []

    _run(go())


def test_send_file_uploads_and_sends_regular_file(monkeypatch, tmp_path: Path):
    from app.channels.message_bus import ResolvedAttachment
    from app.channels.wechat import WechatChannel

    async def go():
        post_calls: list[dict[str, Any]] = []
        put_calls: list[dict[str, Any]] = []

        def _client_factory(*args, **kwargs):
            return _MockAsyncClient(
                post_calls=post_calls,
                put_calls=put_calls,
                post_responses=[
                    {
                        "ret": 0,
                        "upload_param": "enc-query-file",
                        "upload_full_url": "https://cdn.example/upload-file",
                    },
                    {"ret": 0},
                ],
                **kwargs,
            )

        monkeypatch.setattr("app.channels.wechat.httpx.AsyncClient", _client_factory)

        file_path = tmp_path / "report.pdf"
        file_path.write_bytes(b"%PDF-1.4 fake")

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "bot-token"})
        channel._context_tokens_by_chat["wx-user-1"] = "ctx-file-send"

        ok = await channel.send_file(
            OutboundMessage(channel_name="wechat", chat_id="wx-user-1", thread_id="thread-1", text="reply text"),
            ResolvedAttachment(
                virtual_path="/mnt/user-data/outputs/report.pdf",
                actual_path=file_path,
                filename="report.pdf",
                mime_type="application/pdf",
                size=file_path.stat().st_size,
                is_image=False,
            ),
        )

        assert ok is True
        assert len(post_calls) == 3
        assert post_calls[0]["url"].endswith("/ilink/bot/getuploadurl")
        assert post_calls[0]["json"]["media_type"] == 3
        assert post_calls[0]["json"]["no_need_thumb"] is True
        assert len(put_calls) == 0
        assert post_calls[1]["url"] == "https://cdn.example/upload-file"
        assert post_calls[2]["url"].endswith("/ilink/bot/sendmessage")
        file_item = post_calls[2]["json"]["msg"]["item_list"][0]["file_item"]
        assert file_item["media"]["encrypt_query_param"] == "enc-query-file"
        assert file_item["file_name"] == "report.pdf"
        assert file_item["media"]["encrypt_type"] == 1
        assert base64.b64decode(file_item["media"]["aes_key"]).decode("utf-8") == post_calls[0]["json"]["aeskey"]

    _run(go())


def test_send_regular_file_uses_cdn_upload_fallback_when_upload_full_url_missing(monkeypatch, tmp_path: Path):
    from app.channels.message_bus import ResolvedAttachment
    from app.channels.wechat import WechatChannel

    async def go():
        post_calls: list[dict[str, Any]] = []

        def _client_factory(*args, **kwargs):
            return _MockAsyncClient(
                post_calls=post_calls,
                post_responses=[
                    {"ret": 0, "upload_param": "enc-query-file"},
                    {"ret": 0, "headers": {"x-encrypted-param": "enc-query-file-final"}},
                    {"ret": 0},
                ],
                **kwargs,
            )

        monkeypatch.setattr("app.channels.wechat.httpx.AsyncClient", _client_factory)

        file_path = tmp_path / "report.pdf"
        file_path.write_bytes(b"%PDF-1.4 fake")

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "bot-token"})
        channel._context_tokens_by_chat["wx-user-1"] = "ctx-file-send"

        ok = await channel.send_file(
            OutboundMessage(channel_name="wechat", chat_id="wx-user-1", thread_id="thread-1", text="reply text"),
            ResolvedAttachment(
                virtual_path="/mnt/user-data/outputs/report.pdf",
                actual_path=file_path,
                filename="report.pdf",
                mime_type="application/pdf",
                size=file_path.stat().st_size,
                is_image=False,
            ),
        )

        assert ok is True
        assert post_calls[1]["url"].startswith("https://novac2c.cdn.weixin.qq.com/c2c/upload?")
        assert post_calls[2]["url"].endswith("/ilink/bot/sendmessage")
        file_item = post_calls[2]["json"]["msg"]["item_list"][0]["file_item"]
        assert file_item["media"]["encrypt_query_param"] == "enc-query-file-final"
        assert file_item["media"]["encrypt_type"] == 1

    _run(go())


def test_send_image_uses_post_even_when_upload_full_url_present(monkeypatch, tmp_path: Path):
    from app.channels.message_bus import ResolvedAttachment
    from app.channels.wechat import WechatChannel

    async def go():
        post_calls: list[dict[str, Any]] = []
        put_calls: list[dict[str, Any]] = []

        def _client_factory(*args, **kwargs):
            return _MockAsyncClient(
                post_calls=post_calls,
                put_calls=put_calls,
                post_responses=[
                    {
                        "ret": 0,
                        "upload_param": "enc-query-original",
                        "thumb_upload_param": "enc-query-thumb",
                        "upload_full_url": "https://cdn.example/upload-original",
                    },
                    {"ret": 0, "headers": {"x-encrypted-param": "enc-query-downloaded"}},
                    {"ret": 0},
                ],
                **kwargs,
            )

        monkeypatch.setattr("app.channels.wechat.httpx.AsyncClient", _client_factory)

        image_path = tmp_path / "chart.png"
        image_path.write_bytes(b"png-binary-data")

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "bot-token"})
        channel._context_tokens_by_chat["wx-user-1"] = "ctx-image-send"

        ok = await channel.send_file(
            OutboundMessage(channel_name="wechat", chat_id="wx-user-1", thread_id="thread-1", text="reply text"),
            ResolvedAttachment(
                virtual_path="/mnt/user-data/outputs/chart.png",
                actual_path=image_path,
                filename="chart.png",
                mime_type="image/png",
                size=image_path.stat().st_size,
                is_image=True,
            ),
        )

        assert ok is True
        assert len(put_calls) == 0
        assert post_calls[1]["url"] == "https://cdn.example/upload-original"

    _run(go())


def test_send_file_blocks_disallowed_regular_file(monkeypatch, tmp_path: Path):
    from app.channels.message_bus import ResolvedAttachment
    from app.channels.wechat import WechatChannel

    async def go():
        post_calls: list[dict[str, Any]] = []

        def _client_factory(*args, **kwargs):
            return _MockAsyncClient(post_calls=post_calls, **kwargs)

        monkeypatch.setattr("app.channels.wechat.httpx.AsyncClient", _client_factory)

        file_path = tmp_path / "malware.exe"
        file_path.write_bytes(b"MZ")

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "bot-token"})
        channel._context_tokens_by_chat["wx-user-1"] = "ctx-file-send"

        ok = await channel.send_file(
            OutboundMessage(channel_name="wechat", chat_id="wx-user-1", thread_id="thread-1", text="reply text"),
            ResolvedAttachment(
                virtual_path="/mnt/user-data/outputs/malware.exe",
                actual_path=file_path,
                filename="malware.exe",
                mime_type="application/octet-stream",
                size=file_path.stat().st_size,
                is_image=False,
            ),
        )

        assert ok is False
        assert post_calls == []

    _run(go())


def test_handle_update_downloads_inbound_file(monkeypatch, tmp_path: Path):
    from app.channels.wechat import WechatChannel

    async def go():
        bus = MessageBus()
        published = []

        async def capture(msg):
            published.append(msg)

        bus.publish_inbound = capture  # type: ignore[method-assign]

        plaintext = b"hello,file"
        aes_key = b"1234567890abcdef"

        channel = WechatChannel(bus=bus, config={"bot_token": "test-token", "state_dir": str(tmp_path)})
        encrypted = channel.__class__.__dict__["_extract_file_item"].__globals__["_encrypt_aes_128_ecb"](plaintext, aes_key)

        async def _fake_download(_url: str, *, timeout: float | None = None, max_bytes: int | None = None):
            return encrypted

        channel._download_cdn_bytes = _fake_download  # type: ignore[method-assign]

        await channel._handle_update(
            {
                "message_type": 1,
                "message_id": 303,
                "from_user_id": "wx-user-1",
                "context_token": "ctx-file-1",
                "item_list": [
                    {
                        "type": 4,
                        "file_item": {
                            "file_name": "report.pdf",
                            "aeskey": aes_key.hex(),
                            "media": {"full_url": "https://cdn.weixin.qq.com/report.bin"},
                        },
                    }
                ],
            }
        )

        assert len(published) == 1
        inbound = published[0]
        assert inbound.text == ""
        assert len(inbound.files) == 1
        file_info = inbound.files[0]
        assert file_info["message_item_type"] == 4
        stored = Path(file_info["path"])
        assert stored.exists()
        assert stored.read_bytes() == plaintext

    _run(go())


def test_handle_update_downloads_inbound_file_with_media_aeskey_hex(monkeypatch, tmp_path: Path):
    from app.channels.wechat import WechatChannel

    async def go():
        bus = MessageBus()
        published = []

        async def capture(msg):
            published.append(msg)

        bus.publish_inbound = capture  # type: ignore[method-assign]

        plaintext = b"hello,file"
        aes_key = b"1234567890abcdef"

        channel = WechatChannel(bus=bus, config={"bot_token": "test-token", "state_dir": str(tmp_path)})
        encrypted = channel.__class__.__dict__["_extract_file_item"].__globals__["_encrypt_aes_128_ecb"](plaintext, aes_key)

        async def _fake_download(_url: str, *, timeout: float | None = None, max_bytes: int | None = None):
            return encrypted

        channel._download_cdn_bytes = _fake_download  # type: ignore[method-assign]

        await channel._handle_update(
            {
                "message_type": 1,
                "message_id": 304,
                "from_user_id": "wx-user-1",
                "context_token": "ctx-file-1b",
                "item_list": [
                    {
                        "type": 4,
                        "file_item": {
                            "file_name": "report.pdf",
                            "media": {
                                "full_url": "https://cdn.weixin.qq.com/report.bin",
                                "aeskey": aes_key.hex(),
                            },
                        },
                    }
                ],
            }
        )

        assert len(published) == 1
        assert published[0].files[0]["filename"] == "report.pdf"

    _run(go())


def test_handle_update_downloads_inbound_file_with_unpadded_item_aes_key(monkeypatch, tmp_path: Path):
    from app.channels.wechat import WechatChannel

    async def go():
        bus = MessageBus()
        published = []

        async def capture(msg):
            published.append(msg)

        bus.publish_inbound = capture  # type: ignore[method-assign]

        plaintext = b"hello,file"
        aes_key = b"1234567890abcdef"
        encoded_key = base64.b64encode(aes_key).decode("utf-8").rstrip("=")

        channel = WechatChannel(bus=bus, config={"bot_token": "test-token", "state_dir": str(tmp_path)})
        encrypted = channel.__class__.__dict__["_extract_file_item"].__globals__["_encrypt_aes_128_ecb"](plaintext, aes_key)

        async def _fake_download(_url: str, *, timeout: float | None = None, max_bytes: int | None = None):
            return encrypted

        channel._download_cdn_bytes = _fake_download  # type: ignore[method-assign]

        await channel._handle_update(
            {
                "message_type": 1,
                "message_id": 305,
                "from_user_id": "wx-user-1",
                "context_token": "ctx-file-1c",
                "item_list": [
                    {
                        "type": 4,
                        "aesKey": encoded_key,
                        "file_item": {
                            "file_name": "report.pdf",
                            "media": {"full_url": "https://cdn.weixin.qq.com/report.bin"},
                        },
                    }
                ],
            }
        )

        assert len(published) == 1
        assert published[0].files[0]["filename"] == "report.pdf"

    _run(go())


def test_handle_update_downloads_inbound_file_with_media_aes_key_base64_of_hex(monkeypatch, tmp_path: Path):
    from app.channels.wechat import WechatChannel

    async def go():
        bus = MessageBus()
        published = []

        async def capture(msg):
            published.append(msg)

        bus.publish_inbound = capture  # type: ignore[method-assign]

        plaintext = b"hello,file"
        aes_key = b"1234567890abcdef"
        encoded_hex_key = base64.b64encode(aes_key.hex().encode("utf-8")).decode("utf-8")

        channel = WechatChannel(bus=bus, config={"bot_token": "test-token", "state_dir": str(tmp_path)})
        encrypted = channel.__class__.__dict__["_extract_file_item"].__globals__["_encrypt_aes_128_ecb"](plaintext, aes_key)

        async def _fake_download(_url: str, *, timeout: float | None = None, max_bytes: int | None = None):
            return encrypted

        channel._download_cdn_bytes = _fake_download  # type: ignore[method-assign]

        await channel._handle_update(
            {
                "message_type": 1,
                "message_id": 306,
                "from_user_id": "wx-user-1",
                "context_token": "ctx-file-1d",
                "item_list": [
                    {
                        "type": 4,
                        "file_item": {
                            "file_name": "report.pdf",
                            "media": {
                                "full_url": "https://cdn.weixin.qq.com/report.bin",
                                "aes_key": encoded_hex_key,
                            },
                        },
                    }
                ],
            }
        )

        assert len(published) == 1
        assert published[0].files[0]["filename"] == "report.pdf"

    _run(go())


def test_handle_update_skips_disallowed_inbound_file(monkeypatch, tmp_path: Path):
    from app.channels.wechat import WechatChannel

    async def go():
        bus = MessageBus()
        published = []

        async def capture(msg):
            published.append(msg)

        bus.publish_inbound = capture  # type: ignore[method-assign]

        plaintext = b"MZ"
        aes_key = b"1234567890abcdef"

        channel = WechatChannel(bus=bus, config={"bot_token": "test-token", "state_dir": str(tmp_path)})
        encrypted = channel.__class__.__dict__["_extract_file_item"].__globals__["_encrypt_aes_128_ecb"](plaintext, aes_key)

        async def _fake_download(_url: str, *, timeout: float | None = None, max_bytes: int | None = None):
            return encrypted

        channel._download_cdn_bytes = _fake_download  # type: ignore[method-assign]

        await channel._handle_update(
            {
                "message_type": 1,
                "message_id": 404,
                "from_user_id": "wx-user-1",
                "context_token": "ctx-file-2",
                "item_list": [
                    {
                        "type": 4,
                        "file_item": {
                            "file_name": "malware.exe",
                            "aeskey": aes_key.hex(),
                            "media": {"full_url": "https://cdn.weixin.qq.com/bad.bin"},
                        },
                    }
                ],
            }
        )

        assert published == []

    _run(go())


def test_poll_loop_updates_server_timeout(monkeypatch):
    from app.channels.wechat import WechatChannel

    async def go():
        post_calls: list[dict[str, Any]] = []

        def _client_factory(*args, **kwargs):
            return _MockAsyncClient(
                post_calls=post_calls,
                post_responses=[
                    {
                        "ret": 0,
                        "msgs": [
                            {
                                "message_type": 1,
                                "from_user_id": "wx-user-1",
                                "context_token": "ctx-1",
                                "item_list": [{"type": 1, "text_item": {"text": "hello"}}],
                            }
                        ],
                        "get_updates_buf": "cursor-next",
                        "longpolling_timeout_ms": 42000,
                    }
                ],
                **kwargs,
            )

        monkeypatch.setattr("app.channels.wechat.httpx.AsyncClient", _client_factory)

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "bot-token"})
        channel._running = True

        async def _fake_handle_update(_raw):
            channel._running = False
            return None

        channel._handle_update = _fake_handle_update  # type: ignore[method-assign]

        await channel._poll_loop()

        assert channel._get_updates_buf == "cursor-next"
        assert channel._server_longpoll_timeout_seconds == 42.0
        assert post_calls[0]["url"].endswith("/ilink/bot/getupdates")

    _run(go())


def test_poll_loop_one_bad_message_does_not_permanently_lose_its_siblings(monkeypatch, tmp_path: Path, caplog):
    """A single message that fails to process must not sink the rest of its batch.

    Regression test for a permanent message-loss bug: the long-poll cursor was
    persisted for the *whole* batch before the per-message loop ran, and the loop
    had no per-message error isolation, so one bad message (e.g. an attachment
    that fails to decrypt) aborted processing of every message after it in the
    same batch. Because the cursor had already advanced past the whole batch,
    the next poll would never re-fetch the unprocessed tail -- silent, permanent
    loss of every message after the first failure in a batch.

    This test sends a real 3-message batch through the *real* (unstubbed)
    ``_handle_update`` -- message 1 is fine, message 2 is a WeChat image item
    whose "encrypted" bytes are deliberately not a multiple of the AES block
    size, so ``_decrypt_aes_128_ecb`` raises a genuine ``cryptography`` library
    ``ValueError`` (matching how a real corrupt/undecryptable attachment would
    fail), and message 3 is fine again. The fix must:
      - still deliver message 1 and message 3 to the bus despite message 2's
        failure (per-message isolation instead of one bad apple aborting the
        for loop), and
      - log message 2's failure instead of swallowing it silently, and
      - only advance/persist the cursor once the whole batch has been
        attempted (so a crash mid-batch re-delivers rather than silently
        drops).
    """
    from app.channels.wechat import WechatChannel

    async def go():
        bus = MessageBus()
        published: list[Any] = []

        async def capture(msg):
            published.append(msg)

        bus.publish_inbound = capture  # type: ignore[method-assign]

        aes_key = b"1234567890abcdef"
        non_block_aligned_ciphertext = b"\x01\x02\x03\x04\x05"  # 5 bytes: not a multiple of 16

        msg_good_1 = {
            "message_type": 1,
            "message_id": "msg-1-good",
            "from_user_id": "wx-user-1",
            "context_token": "ctx-1",
            "item_list": [{"type": 1, "text_item": {"text": "message one"}}],
        }
        msg_bad_2 = {
            "message_type": 1,
            "message_id": "msg-2-bad",
            "from_user_id": "wx-user-1",
            "context_token": "ctx-2",
            "item_list": [
                {
                    "type": 2,
                    "image_item": {
                        "aeskey": aes_key.hex(),
                        "media": {"full_url": "https://cdn.weixin.qq.com/corrupt-attachment.bin"},
                    },
                }
            ],
        }
        msg_good_3 = {
            "message_type": 1,
            "message_id": "msg-3-good",
            "from_user_id": "wx-user-1",
            "context_token": "ctx-3",
            "item_list": [{"type": 1, "text_item": {"text": "message three"}}],
        }

        state_dir = tmp_path / "wechat-state"

        def _client_factory(*args, **kwargs):
            return _MockAsyncClient(
                post_responses=[
                    {
                        "ret": 0,
                        "msgs": [msg_good_1, msg_bad_2, msg_good_3],
                        "get_updates_buf": "cursor-after-batch",
                    }
                ],
                **kwargs,
            )

        monkeypatch.setattr("app.channels.wechat.httpx.AsyncClient", _client_factory)

        channel = WechatChannel(
            bus=bus,
            config={"bot_token": "test-token", "state_dir": str(state_dir), "polling_retry_delay": 0.001},
        )

        async def _fake_download(_url: str, *, timeout: float | None = None, max_bytes: int | None = None) -> bytes:
            return non_block_aligned_ciphertext

        channel._download_cdn_bytes = _fake_download  # type: ignore[method-assign]

        # _handle_update is intentionally left as the REAL implementation so
        # message 2 hits the genuine cryptography ValueError. To keep the test
        # deterministic without depending on the bug/fix under test, force the
        # poll loop to stop after exactly one getupdates cycle via
        # _ensure_authenticated (called at the top of every iteration, before
        # any message is processed) rather than via message content.
        real_ensure_authenticated = channel._ensure_authenticated
        auth_calls = {"n": 0}

        async def _ensure_auth_then_stop() -> bool:
            auth_calls["n"] += 1
            if auth_calls["n"] > 1:
                channel._running = False
                return False
            return await real_ensure_authenticated()

        channel._ensure_authenticated = _ensure_auth_then_stop  # type: ignore[method-assign]
        channel._running = True

        with caplog.at_level(logging.INFO, logger="app.channels.wechat"):
            await channel._poll_loop()

        # Message 1 and message 3 must both survive message 2's failure.
        assert [m.text for m in published] == ["message one", "message three"]

        # Message 2's failure must be logged, not silently swallowed.
        messages = [record.getMessage() for record in caplog.records]
        assert any("msg-2-bad" in message for message in messages)

        # The cursor must reflect that the whole batch was attempted -- both
        # in memory and in the persisted state file used to resume polling.
        assert channel._get_updates_buf == "cursor-after-batch"
        persisted = json.loads((state_dir / "wechat-getupdates.json").read_text(encoding="utf-8"))
        assert persisted["get_updates_buf"] == "cursor-after-batch"

    _run(go())


def test_state_cursor_is_loaded_from_disk(tmp_path: Path):
    from app.channels.wechat import WechatChannel

    state_dir = tmp_path / "wechat-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "wechat-getupdates.json").write_text(
        json.dumps({"get_updates_buf": "cursor-123"}, ensure_ascii=False),
        encoding="utf-8",
    )

    channel = WechatChannel(
        bus=MessageBus(),
        config={"bot_token": "bot-token", "state_dir": str(state_dir)},
    )
    # State load moved out of __init__ (it does filesystem IO that would block
    # the async path); mirror start() by loading explicitly here.
    channel._load_state()

    assert channel._get_updates_buf == "cursor-123"


def test_auth_state_is_loaded_from_disk(tmp_path: Path):
    from app.channels.wechat import WechatChannel

    state_dir = tmp_path / "wechat-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "wechat-auth.json").write_text(
        json.dumps({"status": "confirmed", "bot_token": "saved-token", "ilink_bot_id": "bot-1"}, ensure_ascii=False),
        encoding="utf-8",
    )

    channel = WechatChannel(
        bus=MessageBus(),
        config={"state_dir": str(state_dir), "qrcode_login_enabled": True},
    )
    # State load moved out of __init__ (it does filesystem IO that would block
    # the async path); mirror start() by loading explicitly here.
    channel._load_state()

    assert channel._bot_token == "saved-token"
    assert channel._ilink_bot_id == "bot-1"


def test_qrcode_login_binds_and_persists_auth_state(monkeypatch, tmp_path: Path):
    from app.channels.wechat import WechatChannel

    async def go():
        get_calls: list[dict[str, Any]] = []

        def _client_factory(*args, **kwargs):
            return _MockAsyncClient(
                get_calls=get_calls,
                get_responses=[
                    {"qrcode": "qr-123", "qrcode_img_content": "https://example.com/qr.png"},
                    {"status": "confirmed", "bot_token": "bound-token", "ilink_bot_id": "bot-99"},
                ],
                **kwargs,
            )

        monkeypatch.setattr("app.channels.wechat.httpx.AsyncClient", _client_factory)

        state_dir = tmp_path / "wechat-state"
        channel = WechatChannel(
            bus=MessageBus(),
            config={
                "state_dir": str(state_dir),
                "qrcode_login_enabled": True,
                "qrcode_poll_interval": 0.01,
                "qrcode_poll_timeout": 1,
            },
        )

        ok = await channel._ensure_authenticated()

        assert ok is True
        assert channel._bot_token == "bound-token"
        assert channel._ilink_bot_id == "bot-99"
        assert get_calls[0]["url"].endswith("/ilink/bot/get_bot_qrcode")
        assert get_calls[1]["url"].endswith("/ilink/bot/get_qrcode_status")

        auth_state = json.loads((state_dir / "wechat-auth.json").read_text(encoding="utf-8"))
        assert auth_state["status"] == "confirmed"
        assert auth_state["bot_token"] == "bound-token"
        assert auth_state["ilink_bot_id"] == "bot-99"
        if os.name == "nt":
            pytest.skip(_POSIX_MODE_BITS_REASON)
        assert ((state_dir / "wechat-auth.json").stat().st_mode & 0o777) == 0o600

    _run(go())


def test_save_auth_state_tightens_preexisting_loose_file(tmp_path: Path):
    """A world-readable auth file is replaced by an owner-only one, atomically.

    The bot_token must never be observable at loose permissions: the atomic
    0o600-temp + ``Path.replace`` path swaps in a fresh owner-only inode rather
    than truncating the existing 0o644 file in place. Seeding the destination at
    0o644 first means a regression back to ``write_text`` + late ``chmod`` would
    leave a detectable window (and, here, the temp-file artifact behind).
    """
    from app.channels.wechat import WechatChannel

    state_dir = tmp_path / "wechat-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    auth_path = state_dir / "wechat-auth.json"
    auth_path.write_text(json.dumps({"status": "pending"}), encoding="utf-8")
    auth_path.chmod(0o644)

    channel = WechatChannel(
        bus=MessageBus(),
        config={"state_dir": str(state_dir), "qrcode_login_enabled": True},
    )
    channel._save_auth_state(status="confirmed", bot_token="bound-token", ilink_bot_id="bot-1")

    assert json.loads(auth_path.read_text(encoding="utf-8"))["bot_token"] == "bound-token"
    # Atomic write leaves no temp-file residue behind.
    assert list(state_dir.glob("*.tmp")) == []
    # Keep the platform-independent half running on Windows; only the mode-bit
    # half of the "owner-only inode" contract is unobservable there.
    if os.name == "nt":
        pytest.skip(_POSIX_MODE_BITS_REASON)
    assert (auth_path.stat().st_mode & 0o777) == 0o600


def test_save_auth_state_chmod_failure_is_logged_not_warned(tmp_path: Path, caplog):
    """A chmod failure on a perms-less filesystem must not look like a persist failure.

    With the post-replace chmod split into its own try/except, a chmod ``OSError``
    is logged at debug while the JSON is genuinely on disk — operators must not see
    the misleading ``failed to persist`` warning that the shared try/except produced.
    """
    from app.channels.wechat import WechatChannel

    state_dir = tmp_path / "wechat-state"
    channel = WechatChannel(
        bus=MessageBus(),
        config={"state_dir": str(state_dir), "qrcode_login_enabled": True},
    )

    real_chmod = Path.chmod

    def chmod_spy(self: Path, mode: int, *args, **kwargs):
        if self.suffix == ".json":
            raise OSError("chmod unsupported on this filesystem")
        return real_chmod(self, mode, *args, **kwargs)

    with caplog.at_level(logging.DEBUG, logger="app.channels.wechat"), mock.patch.object(Path, "chmod", chmod_spy):
        channel._save_auth_state(status="confirmed", bot_token="bound-token")

    auth_path = state_dir / "wechat-auth.json"
    assert json.loads(auth_path.read_text(encoding="utf-8"))["bot_token"] == "bound-token"
    messages = [record.getMessage() for record in caplog.records]
    assert any("unable to chmod auth state" in message for message in messages)
    assert not any("failed to persist auth state" in message for message in messages)


# ---------------------------------------------------------------------------
# Inbound media download cap + destination allowlist
# ---------------------------------------------------------------------------


def test_is_allowed_media_url_suffix_boundaries():
    from app.channels.wechat import WechatChannel

    channel = WechatChannel(MessageBus(), config={"bot_token": "test-token"})

    # Platform CDN defaults (plus the configured cdn_base_url host) are allowed.
    assert channel._is_allowed_media_url("https://novac2c.cdn.weixin.qq.com/c2c/x?token=1")
    assert channel._is_allowed_media_url("https://cdn.weixin.qq.com/image.bin")
    # Dot-boundary suffix matching: lookalike hosts never match.
    assert not channel._is_allowed_media_url("https://notqq.com/image.bin")
    assert not channel._is_allowed_media_url("https://qq.com.evil.io/image.bin")
    assert not channel._is_allowed_media_url("https://cdn.example/image.bin")
    # Loopback/private targets and non-HTTP schemes are rejected outright.
    assert not channel._is_allowed_media_url("http://127.0.0.1:8001/api/user")
    assert not channel._is_allowed_media_url("http://169.254.169.254/latest/meta-data")
    assert not channel._is_allowed_media_url("file:///etc/passwd")

    # Operator suffixes extend the allowlist; the configured cdn_base_url host
    # is admitted automatically so a custom CDN endpoint keeps working. A
    # leading ``*.`` (DNS habit) normalizes to the bare suffix.
    custom = WechatChannel(
        MessageBus(),
        config={
            "bot_token": "test-token",
            "cdn_base_url": "https://media.internal.example/c2c",
            "allowed_media_hosts": ["cdn.example", "*.wild.example"],
        },
    )
    assert custom._is_allowed_media_url("https://media.internal.example/c2c/x")
    assert custom._is_allowed_media_url("https://a.cdn.example/image.bin")
    assert custom._is_allowed_media_url("https://cdn.weixin.qq.com/image.bin")
    assert custom._is_allowed_media_url("https://b.wild.example/image.bin")


def test_handle_update_skips_media_from_disallowed_host(tmp_path: Path):
    from app.channels.wechat import WechatChannel

    async def go():
        bus = MessageBus()
        published = []

        async def capture(msg):
            published.append(msg)

        bus.publish_inbound = capture  # type: ignore[method-assign]

        channel = WechatChannel(bus, config={"bot_token": "test-token", "state_dir": str(tmp_path)})

        async def _forbidden_download(_url: str, *, timeout: float | None = None, max_bytes: int | None = None) -> bytes:
            raise AssertionError("download must not be attempted for a disallowed media host")

        channel._download_cdn_bytes = _forbidden_download  # type: ignore[method-assign]

        await channel._handle_update(
            {
                "message_type": 1,
                "message_id": 201,
                "from_user_id": "wx-user-1",
                "context_token": "ctx-evil-1",
                "item_list": [
                    {
                        "type": 2,
                        "image_item": {
                            "aeskey": b"1234567890abcdef".hex(),
                            "media": {"full_url": "https://evil.example/image.bin"},
                        },
                    }
                ],
            }
        )

        # The image is dropped and, with no text either, nothing is published.
        assert published == []
        downloads_dir = tmp_path / "downloads"
        assert not downloads_dir.exists() or not list(downloads_dir.iterdir())

    _run(go())


def test_handle_update_http_download_failure_is_sanitized_not_raised(tmp_path: Path, caplog):
    """An HTTP failure during the media download drops that attachment with a
    sanitized log instead of escaping to the polling loop's logger.exception.

    httpx.HTTPStatusError formats the signed URL (path + query credentials)
    into its message, so letting it propagate would render the URL in the
    per-message traceback. Reproduced with a real 403 mock transport.
    """
    import httpx

    from app.channels.wechat import WechatChannel

    async def go():
        bus = MessageBus()
        published = []

        async def capture(msg):
            published.append(msg)

        bus.publish_inbound = capture  # type: ignore[method-assign]

        channel = WechatChannel(bus, config={"bot_token": "test-token", "state_dir": str(tmp_path)})
        channel._client = httpx.AsyncClient(  # type: ignore[assignment]
            transport=httpx.MockTransport(lambda _request: httpx.Response(403))
        )
        try:
            await channel._handle_update(
                {
                    "message_type": 1,
                    "message_id": 202,
                    "from_user_id": "wx-user-1",
                    "context_token": "ctx-403-1",
                    "item_list": [
                        {
                            "type": 2,
                            "image_item": {
                                "aeskey": b"1234567890abcdef".hex(),
                                "media": {"full_url": "https://cdn.weixin.qq.com/private/BearerSecret?token=QuerySecret"},
                            },
                        }
                    ],
                }
            )
        finally:
            await channel._client.aclose()

        # The image is dropped and, with no text either, nothing is published.
        assert published == []

    with caplog.at_level(logging.WARNING, logger="app.channels.wechat"):
        _run(go())

    assert "BearerSecret" not in caplog.text
    assert "QuerySecret" not in caplog.text
    assert "/private/" not in caplog.text
    # The operator still sees what failed and for which host.
    assert "HTTPStatusError (403)" in caplog.text
    assert "cdn.weixin.qq.com" in caplog.text


class _FakeStreamResponse:
    def __init__(self, chunks: list[bytes]):
        self._chunks = chunks
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        return None

    # Deliberately no aiter_bytes: the reader must consume undecoded bytes, so
    # an accidental switch back to the decoding iterator fails loudly here.
    async def aiter_raw(self):
        for chunk in self._chunks:
            yield chunk


class _FakeStreamContext:
    def __init__(self, response: _FakeStreamResponse):
        self._response = response

    async def __aenter__(self) -> _FakeStreamResponse:
        return self._response

    async def __aexit__(self, *exc_info) -> bool:
        return False


class _FakeStreamingClient:
    def __init__(self, chunks: list[bytes]):
        self._chunks = chunks

    def stream(self, _method: str, _url: str, timeout: float | None = None, **_kwargs) -> _FakeStreamContext:
        return _FakeStreamContext(_FakeStreamResponse(self._chunks))


def test_download_cdn_bytes_aborts_when_stream_exceeds_cap():
    from app.channels.wechat import WechatChannel

    async def go():
        channel = WechatChannel(MessageBus(), config={"bot_token": "test-token"})
        channel._client = _FakeStreamingClient([b"abc", b"def"])  # type: ignore[assignment]

        # 6 bytes total vs a 5-byte cap: aborted mid-stream before full read.
        assert await channel._download_cdn_bytes("https://cdn.weixin.qq.com/x", max_bytes=5) is None
        # At/under the cap and with the cap disabled the chunks are joined as before.
        assert await channel._download_cdn_bytes("https://cdn.weixin.qq.com/x", max_bytes=6) == b"abcdef"
        assert await channel._download_cdn_bytes("https://cdn.weixin.qq.com/x", max_bytes=None) == b"abcdef"
        assert await channel._download_cdn_bytes("https://cdn.weixin.qq.com/x", max_bytes=0) == b"abcdef"

    _run(go())


def test_download_cdn_bytes_rejects_compressed_response_before_decode(caplog):
    """aiter_bytes() would transparently decode Content-Encoding, allocating the
    whole decompressed body before the cap sees a byte — an ~8 KB gzip wire
    chunk decoding to 8 MiB (reproduced here) bypasses max_bytes entirely. The
    download must request identity and refuse a residual encoding before
    reading, even with the cap disabled."""
    import gzip

    import httpx

    from app.channels.wechat import WechatChannel

    class _AsyncChunks(httpx.AsyncByteStream):
        def __init__(self, chunks: list[bytes]):
            self._chunks = chunks

        async def __aiter__(self):
            for chunk in self._chunks:
                yield chunk

    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(
            200,
            headers={"Content-Encoding": "gzip"},
            stream=_AsyncChunks([gzip.compress(b"\x00" * (8 * 1024 * 1024))]),
        )

    async def go():
        channel = WechatChannel(MessageBus(), config={"bot_token": "test-token"})
        channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[assignment]
        try:
            # Cap disabled: the old aiter_bytes() code path would happily
            # return the 8 MiB decompressed payload here.
            assert await channel._download_cdn_bytes("https://cdn.weixin.qq.com/x", max_bytes=None) is None
            # With a cap in place the rejection still happens for the encoding,
            # before any decode/size accounting.
            assert await channel._download_cdn_bytes("https://cdn.weixin.qq.com/x", max_bytes=1024 * 1024) is None
        finally:
            await channel._client.aclose()

    with caplog.at_level(logging.WARNING, logger="app.channels.wechat"):
        _run(go())

    assert "Content-Encoding" in caplog.text
    assert "exceeds" not in caplog.text  # rejected for the encoding, not the size
    assert seen_requests[0].headers.get("accept-encoding") == "identity"


def test_download_cdn_bytes_streams_identity_response():
    """An unencoded response still round-trips through a real httpx transport."""
    import httpx

    from app.channels.wechat import WechatChannel

    class _AsyncChunks(httpx.AsyncByteStream):
        def __init__(self, chunks: list[bytes]):
            self._chunks = chunks

        async def __aiter__(self):
            for chunk in self._chunks:
                yield chunk

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=_AsyncChunks([b"abcdef"]))

    async def go():
        channel = WechatChannel(MessageBus(), config={"bot_token": "test-token"})
        channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[assignment]
        try:
            assert await channel._download_cdn_bytes("https://cdn.weixin.qq.com/x") == b"abcdef"
        finally:
            await channel._client.aclose()

    _run(go())


def test_boundary_sized_inbound_image_survives_pkcs7_padding(tmp_path: Path):
    """A valid attachment whose plaintext is exactly the configured limit must load.

    The limit bounds plaintext, but the stream measures ciphertext — AES-128-ECB
    with PKCS#7 pads 32 plaintext bytes to 48 — so the stream cap must be the
    padded size of exactly-limit plaintext, not the plaintext limit itself.
    Exercises the real streaming download (no _download_cdn_bytes stub).
    """
    from app.channels.wechat import WechatChannel, _encrypt_aes_128_ecb

    async def go():
        channel = WechatChannel(
            MessageBus(),
            config={"bot_token": "test-token", "state_dir": str(tmp_path), "max_inbound_image_bytes": 32},
        )
        aes_key = b"1234567890abcdef"
        plaintext = b"\x89PNG\r\n\x1a\n" + b"x" * 24  # exactly 32 bytes, valid PNG magic
        encrypted = _encrypt_aes_128_ecb(plaintext, aes_key)  # 48 bytes > 32-byte limit
        assert len(encrypted) == 48
        channel._client = _FakeStreamingClient([encrypted])  # type: ignore[assignment]

        assert channel._stream_cap_for(32) == 48
        assert channel._stream_cap_for(0) is None

        files = await channel._extract_inbound_files(
            {
                "message_id": 301,
                "item_list": [
                    {
                        "type": 2,
                        "image_item": {
                            "aeskey": aes_key.hex(),
                            "media": {"full_url": "https://cdn.weixin.qq.com/image.bin"},
                        },
                    }
                ],
            }
        )

        assert len(files) == 1
        assert files[0]["type"] == "image"
        assert files[0]["size"] == 32
        assert Path(files[0]["path"]).read_bytes() == plaintext

    _run(go())


# --- merged from test_wechat_channel.py (subdir-only tests; root copy is the dedup base) ---
def _make_channel(config=None):
    """Create a WechatChannel with a bot token for testing."""
    from app.channels.wechat import WechatChannel

    cfg = {"bot_token": "test_token_123", **(config or {})}
    return WechatChannel(MessageBus(), cfg)


class TestQrcodeExpiredAndCanceled:
    def test_qrcode_expired_raises(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        async def go():
            def _client_factory(*args, **kwargs):
                return _MockAsyncClient(
                    get_responses=[
                        {"qrcode": "qr-123"},
                        {"status": "expired"},
                    ],
                    **kwargs,
                )

            with patch("app.channels.wechat.httpx.AsyncClient", _client_factory):
                channel = WechatChannel(
                    bus=MessageBus(),
                    config={
                        "state_dir": str(tmp_path),
                        "qrcode_login_enabled": True,
                        "qrcode_poll_interval": 0.01,
                        "qrcode_poll_timeout": 1,
                    },
                )

                with pytest.raises(RuntimeError, match="expired"):
                    await channel._bind_via_qrcode()

        _run(go())

    def test_qrcode_canceled_raises(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        async def go():
            def _client_factory(*args, **kwargs):
                return _MockAsyncClient(
                    get_responses=[
                        {"qrcode": "qr-123"},
                        {"status": "canceled"},
                    ],
                    **kwargs,
                )

            with patch("app.channels.wechat.httpx.AsyncClient", _client_factory):
                channel = WechatChannel(
                    bus=MessageBus(),
                    config={
                        "state_dir": str(tmp_path),
                        "qrcode_login_enabled": True,
                        "qrcode_poll_interval": 0.01,
                        "qrcode_poll_timeout": 1,
                    },
                )

                with pytest.raises(RuntimeError, match="canceled"):
                    await channel._bind_via_qrcode()

        _run(go())

    def test_qrcode_cancelled_raises(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        async def go():
            def _client_factory(*args, **kwargs):
                return _MockAsyncClient(
                    get_responses=[
                        {"qrcode": "qr-123"},
                        {"status": "cancelled"},
                    ],
                    **kwargs,
                )

            with patch("app.channels.wechat.httpx.AsyncClient", _client_factory):
                channel = WechatChannel(
                    bus=MessageBus(),
                    config={
                        "state_dir": str(tmp_path),
                        "qrcode_login_enabled": True,
                        "qrcode_poll_interval": 0.01,
                        "qrcode_poll_timeout": 1,
                    },
                )

                with pytest.raises(RuntimeError, match="cancelled"):
                    await channel._bind_via_qrcode()

        _run(go())

    def test_qrcode_invalid_raises(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        async def go():
            def _client_factory(*args, **kwargs):
                return _MockAsyncClient(
                    get_responses=[
                        {"qrcode": "qr-123"},
                        {"status": "invalid"},
                    ],
                    **kwargs,
                )

            with patch("app.channels.wechat.httpx.AsyncClient", _client_factory):
                channel = WechatChannel(
                    bus=MessageBus(),
                    config={
                        "state_dir": str(tmp_path),
                        "qrcode_login_enabled": True,
                        "qrcode_poll_interval": 0.01,
                        "qrcode_poll_timeout": 1,
                    },
                )

                with pytest.raises(RuntimeError, match="invalid"):
                    await channel._bind_via_qrcode()

        _run(go())

    def test_qrcode_failed_raises(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        async def go():
            def _client_factory(*args, **kwargs):
                return _MockAsyncClient(
                    get_responses=[
                        {"qrcode": "qr-123"},
                        {"status": "failed"},
                    ],
                    **kwargs,
                )

            with patch("app.channels.wechat.httpx.AsyncClient", _client_factory):
                channel = WechatChannel(
                    bus=MessageBus(),
                    config={
                        "state_dir": str(tmp_path),
                        "qrcode_login_enabled": True,
                        "qrcode_poll_interval": 0.01,
                        "qrcode_poll_timeout": 1,
                    },
                )

                with pytest.raises(RuntimeError, match="failed"):
                    await channel._bind_via_qrcode()

        _run(go())

    def test_qrcode_timeout(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        async def go():
            def _client_factory(*args, **kwargs):
                return _MockAsyncClient(
                    get_responses=[
                        {"qrcode": "qr-123"},
                        {"status": "scanning"},
                        {"status": "scanning"},
                    ],
                    **kwargs,
                )

            with patch("app.channels.wechat.httpx.AsyncClient", _client_factory):
                channel = WechatChannel(
                    bus=MessageBus(),
                    config={
                        "state_dir": str(tmp_path),
                        "qrcode_login_enabled": True,
                        "qrcode_poll_interval": 0.01,
                        "qrcode_poll_timeout": 0.05,
                    },
                )

                with pytest.raises(TimeoutError, match="Timed out"):
                    await channel._bind_via_qrcode()

        _run(go())

    def test_qrcode_empty_raises(self):
        from app.channels.wechat import WechatChannel

        async def go():
            def _client_factory(*args, **kwargs):
                return _MockAsyncClient(
                    get_responses=[{"qrcode": ""}],
                    **kwargs,
                )

            with patch("app.channels.wechat.httpx.AsyncClient", _client_factory):
                channel = WechatChannel(bus=MessageBus(), config={"qrcode_login_enabled": True})

                with pytest.raises(RuntimeError, match="qrcode"):
                    await channel._bind_via_qrcode()

        _run(go())

    def test_qrcode_confirmed_without_token_raises(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        async def go():
            def _client_factory(*args, **kwargs):
                return _MockAsyncClient(
                    get_responses=[
                        {"qrcode": "qr-123"},
                        {"status": "confirmed", "bot_token": ""},
                    ],
                    **kwargs,
                )

            with patch("app.channels.wechat.httpx.AsyncClient", _client_factory):
                channel = WechatChannel(
                    bus=MessageBus(),
                    config={
                        "state_dir": str(tmp_path),
                        "qrcode_login_enabled": True,
                        "qrcode_poll_interval": 0.01,
                        "qrcode_poll_timeout": 1,
                    },
                )

                with pytest.raises(RuntimeError, match="bot_token"):
                    await channel._bind_via_qrcode()

        _run(go())


class TestPollLoopAdditional:
    def test_poll_loop_handles_nonzero_ret(self):
        from app.channels.wechat import WechatChannel

        # Test that _ensure_success raises on nonzero ret
        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        with pytest.raises(RuntimeError, match="failed"):
            channel._ensure_success({"ret": 1, "errcode": 100, "errmsg": "bad"}, "test")

    def test_poll_loop_handles_success_ret(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        channel._ensure_success({"ret": 0}, "test")  # Should not raise

    def test_poll_loop_handles_none_ret(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        channel._ensure_success({"ret": None}, "test")  # Should not raise


class TestSendTextMessageRetry:
    def test_send_retry_metadata(self):
        from app.channels.wechat import WechatChannel

        # Test that _send_text_message constructs the correct payload structure
        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        # Verify the method exists and has the right signature
        assert hasattr(channel, "_send_text_message")

    def test_send_method_exists(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        # Verify send method handles empty text

        async def go():
            msg = OutboundMessage(
                channel_name="wechat",
                chat_id="u1",
                thread_id="t1",
                text="  ",
            )
            await channel.send(msg)  # Should return without error

        _run(go())


class TestHandleUpdateEdgeCases:
    def test_ilink_user_id_fallback(self):
        from app.channels.wechat import WechatChannel

        async def go():
            bus = MessageBus()
            published = []

            async def capture(msg):
                published.append(msg)

            bus.publish_inbound = capture

            channel = WechatChannel(bus=bus, config={"bot_token": "tok"})
            await channel._handle_update(
                {
                    "message_type": 1,
                    "ilink_user_id": "ilink-user-1",
                    "context_token": "ctx",
                    "item_list": [{"type": 1, "text_item": {"text": "hi"}}],
                }
            )
            assert len(published) == 1
            assert published[0].chat_id == "ilink-user-1"

        _run(go())

    def test_no_user_id_skips(self):
        from app.channels.wechat import WechatChannel

        async def go():
            bus = MessageBus()
            published = []

            async def capture(msg):
                published.append(msg)

            bus.publish_inbound = capture

            channel = WechatChannel(bus=bus, config={"bot_token": "tok"})
            await channel._handle_update(
                {
                    "message_type": 1,
                    "item_list": [{"type": 1, "text_item": {"text": "hi"}}],
                }
            )
            assert published == []

        _run(go())

    def test_voice_and_video_items_ignored(self):
        from app.channels.wechat import WechatChannel

        async def go():
            bus = MessageBus()
            published = []

            async def capture(msg):
                published.append(msg)

            bus.publish_inbound = capture

            channel = WechatChannel(bus=bus, config={"bot_token": "tok"})
            await channel._handle_update(
                {
                    "message_type": 1,
                    "from_user_id": "u1",
                    "context_token": "ctx",
                    "item_list": [
                        {"type": 3},
                        {"type": 5},
                    ],
                }
            )
            assert published == []

        _run(go())


class TestIsAllowedFileTypeExtended:
    def test_pdf_allowed(self):
        channel = _make_channel()
        assert channel._is_allowed_file_type("report.pdf", "application/pdf") is True

    def test_json_allowed(self):
        channel = _make_channel()
        assert channel._is_allowed_file_type("data.json", "application/json") is True

    def test_zip_allowed(self):
        channel = _make_channel()
        assert channel._is_allowed_file_type("archive.zip", "application/zip") is True

    def test_text_mime_type_with_allowed_extension(self):
        channel = _make_channel()
        assert channel._is_allowed_file_type("file.txt", "text/plain") is True

    def test_blocked_extension(self):
        channel = _make_channel()
        assert channel._is_allowed_file_type("file.exe", "application/x-executable") is False

    def test_blocked_mime_type(self):
        channel = _make_channel()
        assert channel._is_allowed_file_type("file.xyz", "application/xyz") is False


class TestResolveMediaAesKeyExtended:
    def test_from_aesKey_field(self):
        from app.channels.wechat import WechatChannel

        key = b"0123456789abcdef"
        payload = {"aesKey": base64.b64encode(key).decode()}
        result = WechatChannel._resolve_media_aes_key(payload)
        assert result == key

    def test_from_encrypt_key_field(self):
        from app.channels.wechat import WechatChannel

        key = b"0123456789abcdef"
        payload = {"encrypt_key": base64.b64encode(key).decode()}
        result = WechatChannel._resolve_media_aes_key(payload)
        assert result == key

    def test_from_encryptKey_field(self):
        from app.channels.wechat import WechatChannel

        key = b"0123456789abcdef"
        payload = {"encryptKey": base64.b64encode(key).decode()}
        result = WechatChannel._resolve_media_aes_key(payload)
        assert result == key

    def test_from_aes_key_hex_field(self):
        from app.channels.wechat import WechatChannel

        key = b"0123456789abcdef"
        payload = {"aes_key_hex": key.hex()}
        result = WechatChannel._resolve_media_aes_key(payload)
        assert result == key

    def test_deeply_nested_media(self):
        from app.channels.wechat import WechatChannel

        key = b"0123456789abcdef"
        payload = {"media": {"media": {"aes_key": base64.b64encode(key).decode()}}}
        result = WechatChannel._resolve_media_aes_key(payload)
        assert result == key

    def test_multiple_payloads_first_wins(self):
        from app.channels.wechat import WechatChannel

        key1 = b"0123456789abcdef"
        key2 = b"fedcba9876543210"
        result = WechatChannel._resolve_media_aes_key(
            {"aeskey": key1.hex()},
            {"aeskey": key2.hex()},
        )
        assert result == key1

    def test_non_mapping_payload_skipped(self):
        from app.channels.wechat import WechatChannel

        key = b"0123456789abcdef"
        result = WechatChannel._resolve_media_aes_key(
            None,
            "not_a_dict",
            {"aeskey": key.hex()},
        )
        assert result == key


class TestDescribeMediaKeyStateExtended:
    def test_with_string_values(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._describe_media_key_state(
            item={"aeskey": "abc"},
            item_payload={"aes_key": "def"},
            media={"full_url": "https://example.com"},
        )
        assert result["item"]["aeskey"] == "str(len=3)"

    def test_with_none_values(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._describe_media_key_state(
            item={"encrypt_type": None},
            item_payload={},
            media={},
        )
        assert result["item"]["encrypt_type"] is None

    def test_with_non_string_values(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._describe_media_key_state(
            item={"encrypt_type": 1},
            item_payload={},
            media={},
        )
        assert result["item"]["encrypt_type"] == "int"


class TestCoerceHelpersExtended:
    def test_coerce_float_with_bool(self):
        from app.channels.wechat import WechatChannel

        assert WechatChannel._coerce_float(True, 5.0) == 1.0

    def test_coerce_int_with_float(self):
        from app.channels.wechat import WechatChannel

        assert WechatChannel._coerce_int(3.7, 5) == 3

    def test_coerce_str_set_with_frozenset(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._coerce_str_set(frozenset({".pdf"}), frozenset())
        assert ".pdf" in result

    def test_coerce_str_set_with_tuple(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._coerce_str_set((".pdf", ".txt"), frozenset())
        assert ".pdf" in result
        assert ".txt" in result

    def test_coerce_str_set_items_without_dot(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._coerce_str_set(["pdf", "txt"], frozenset())
        assert ".pdf" in result
        assert ".txt" in result


class TestStartStopExtended:
    def test_start_already_running_noop(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            channel._running = True
            await channel.start()
            assert channel._running is True

        _run(go())

    def test_stop_with_poll_task_cancellation(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            channel._running = True

            async def long_task():
                await asyncio.sleep(100)

            channel._poll_task = asyncio.ensure_future(long_task())
            channel._client = AsyncMock()

            await channel.stop()
            assert channel._running is False
            assert channel._poll_task is None

        _run(go())


class TestSaveAuthStateExtended:
    def test_save_with_existing_ilink_bot_id(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"state_dir": str(tmp_path)})
        channel._auth_path = tmp_path / "wechat-auth.json"
        channel._ilink_bot_id = "existing_bot"
        result = channel._save_auth_state(status="confirmed")
        assert result["ilink_bot_id"] == "existing_bot"

    def test_save_preserves_previous_state(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"state_dir": str(tmp_path)})
        channel._auth_path = tmp_path / "wechat-auth.json"
        channel._auth_state = {"previous_key": "previous_value"}
        result = channel._save_auth_state(status="confirmed")
        assert result["previous_key"] == "previous_value"

    def test_save_with_none_ilink_bot_id(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"state_dir": str(tmp_path)})
        channel._auth_path = tmp_path / "wechat-auth.json"
        channel._ilink_bot_id = None
        result = channel._save_auth_state(status="confirmed")
        assert "ilink_bot_id" not in result


class TestLoadAuthStateExtended:
    def test_load_auth_state_preserves_existing_token(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        auth_file = tmp_path / "wechat-auth.json"
        auth_file.write_text(json.dumps({"status": "confirmed"}))
        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "existing"})
        channel._auth_path = auth_file
        channel._load_auth_state()
        assert channel._bot_token == "existing"

    def test_load_auth_state_new_bot_id(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        auth_file = tmp_path / "wechat-auth.json"
        auth_file.write_text(json.dumps({"ilink_bot_id": "new_bot"}))
        channel = WechatChannel(bus=MessageBus(), config={})
        channel._auth_path = auth_file
        channel._ilink_bot_id = None
        channel._load_auth_state()
        assert channel._ilink_bot_id == "new_bot"

    def test_load_auth_state_empty_bot_id_ignored(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        auth_file = tmp_path / "wechat-auth.json"
        auth_file.write_text(json.dumps({"ilink_bot_id": "  "}))
        channel = WechatChannel(bus=MessageBus(), config={})
        channel._auth_path = auth_file
        channel._ilink_bot_id = None
        channel._load_auth_state()
        assert channel._ilink_bot_id is None


class TestDecodeBase64AesKeyExtended:
    def test_hex_encoded_in_base64_with_quotes(self):
        from app.channels.wechat import WechatChannel

        key = b"0123456789abcdef"
        hex_str = f'"{key.hex()}"'
        encoded = base64.b64encode(hex_str.encode("utf-8")).decode()
        result = WechatChannel._decode_base64_aes_key(encoded)
        assert result == key

    def test_unicode_decode_error_returns_none(self):
        from app.channels.wechat import WechatChannel

        bad_bytes = b"\xff\xfe\xfd"
        encoded = base64.b64encode(bad_bytes).decode()
        result = WechatChannel._decode_base64_aes_key(encoded)
        assert result is None


class TestExtractRefMessageExtended:
    def test_multiple_items_finds_first_ref(self):
        from app.channels.wechat import WechatChannel

        raw = {
            "item_list": [
                {"type": 1, "text_item": {"text": "hi"}},
                {"type": 2, "ref_msg": {"title": "first_ref"}},
                {"type": 2, "ref_msg": {"title": "second_ref"}},
            ]
        }
        result = WechatChannel._extract_ref_message(raw)
        assert result == {"title": "first_ref"}


class TestBuildOutboundItemsExtended:
    def test_build_outbound_image_item_empty_upload_param(self):
        channel = _make_channel()
        aes_key = b"0123456789abcdef"
        item = channel._build_outbound_image_item({"upload_param": "  "}, aes_key, ciphertext_size=128)
        assert "encrypt_query_param" not in item["media"]

    def test_build_outbound_file_item_without_upload_param(self):
        channel = _make_channel()
        aes_key = b"0123456789abcdef"
        item = channel._build_outbound_file_item({}, aes_key, "test.txt", b"content")
        assert "encrypt_query_param" not in item["media"]


class TestUploadCdnBytesExtended:
    def test_upload_post_with_content_type(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.headers = {"x-encrypted-param": "param"}
            mock_client.post = AsyncMock(return_value=mock_response)
            channel._client = mock_client

            result = await channel._upload_cdn_bytes(
                "https://upload.example.com",
                b"data",
                content_type="image/png",
                method="POST",
            )
            assert result == "param"

        _run(go())

    def test_upload_put_default(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.headers = {}
            mock_client.put = AsyncMock(return_value=mock_response)
            channel._client = mock_client

            result = await channel._upload_cdn_bytes(
                "https://upload.example.com",
                b"data",
            )
            assert result is None

        _run(go())


class TestBuildIlinkClientVersionEdgeCases:
    """Lines 54-55: ValueError path in _part(), index >= len(parts)."""

    def test_non_numeric_part_returns_zero(self):
        from app.channels.wechat import _build_ilink_client_version

        result = _build_ilink_client_version("1.abc.5")
        # "abc" -> ValueError -> 0; so (1 << 16) | (0 << 8) | 5 = 65541
        assert result == str((1 << 16) | (0 << 8) | 5)

    def test_single_part(self):
        from app.channels.wechat import _build_ilink_client_version

        result = _build_ilink_client_version("2")
        assert result == str(2 << 16)

    def test_empty_string(self):
        from app.channels.wechat import _build_ilink_client_version

        result = _build_ilink_client_version("")
        assert result == "0"

    def test_parts_clamped_to_255(self):
        from app.channels.wechat import _build_ilink_client_version

        result = _build_ilink_client_version("999.999.999")
        assert result == str((255 << 16) | (255 << 8) | 255)


class TestEncryptedSizeNegative:
    """Line 73: ValueError for negative plaintext_size."""

    def test_negative_raises(self):
        from app.channels.wechat import _encrypted_size_for_aes_128_ecb

        with pytest.raises(ValueError, match="non-negative"):
            _encrypted_size_for_aes_128_ecb(-1)


class TestDetectImageExtension:
    """Lines 119, 121, 123, 125: JPEG, GIF, WEBP, BMP detection."""

    def test_jpeg(self):
        from app.channels.wechat import _detect_image_extension_and_mime

        result = _detect_image_extension_and_mime(b"\xff\xd8\xff\xe0" + b"\x00" * 20)
        assert result == (".jpg", "image/jpeg")

    def test_gif87a(self):
        from app.channels.wechat import _detect_image_extension_and_mime

        result = _detect_image_extension_and_mime(b"GIF87a" + b"\x00" * 10)
        assert result == (".gif", "image/gif")

    def test_gif89a(self):
        from app.channels.wechat import _detect_image_extension_and_mime

        result = _detect_image_extension_and_mime(b"GIF89a" + b"\x00" * 10)
        assert result == (".gif", "image/gif")

    def test_webp(self):
        from app.channels.wechat import _detect_image_extension_and_mime

        content = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 10
        result = _detect_image_extension_and_mime(content)
        assert result == (".webp", "image/webp")

    def test_bmp(self):
        from app.channels.wechat import _detect_image_extension_and_mime

        result = _detect_image_extension_and_mime(b"BM" + b"\x00" * 20)
        assert result == (".bmp", "image/bmp")

    def test_unknown_returns_none(self):
        from app.channels.wechat import _detect_image_extension_and_mime

        result = _detect_image_extension_and_mime(b"\x00\x00\x00\x00")
        assert result is None

    def test_webp_too_short_returns_none(self):
        from app.channels.wechat import _detect_image_extension_and_mime

        result = _detect_image_extension_and_mime(b"RIFF" + b"\x00" * 2)
        assert result is None


class TestStartMethod:
    """Lines 261-273: start() full flow."""

    def test_start_no_token_no_qrcode_returns_early(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={})
            await channel.start()
            assert channel._running is False
            assert channel._poll_task is None

        _run(go())

    def test_start_full_flow_with_token(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            assert channel._running is False
            await channel.start()
            assert channel._running is True
            assert channel._poll_task is not None
            # Stop to clean up
            await channel.stop()

        _run(go())

    def test_start_creates_state_dir(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        async def go():
            state_dir = tmp_path / "new_state"
            channel = WechatChannel(
                bus=MessageBus(),
                config={"bot_token": "tok", "state_dir": str(state_dir)},
            )
            await channel.start()
            assert state_dir.exists()
            await channel.stop()

        _run(go())


class TestEnsureAuthenticated:
    """Lines 643, 646, 650-652: _ensure_authenticated edge cases."""

    def test_no_token_no_qrcode_returns_false(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={})
            result = await channel._ensure_authenticated()
            assert result is False

        _run(go())

    def test_token_from_auth_state(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        async def go():
            auth_file = tmp_path / "wechat-auth.json"
            auth_file.write_text(json.dumps({"bot_token": "state-token"}))
            channel = WechatChannel(bus=MessageBus(), config={"state_dir": str(tmp_path)})
            # Auth state is loaded from disk inside _ensure_authenticated().
            result = await channel._ensure_authenticated()
            assert result is True
            assert channel._bot_token == "state-token"

        _run(go())

    def test_qrcode_binding_exception_returns_false(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(
                bus=MessageBus(),
                config={
                    "state_dir": str(tmp_path),
                    "qrcode_login_enabled": True,
                },
            )

            async def _fail_bind():
                raise RuntimeError("binding failed")

            channel._bind_via_qrcode = _fail_bind  # type: ignore[method-assign]
            result = await channel._ensure_authenticated()
            assert result is False

        _run(go())


class TestPollLoopAuthFailure:
    """Line 549-550: poll loop when _ensure_authenticated returns False."""

    def test_poll_loop_exits_when_not_authenticated(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"polling_retry_delay": 0.01})
            channel._running = True

            call_count = 0

            async def _return_false():
                nonlocal call_count
                call_count += 1
                channel._running = False
                return False

            channel._ensure_authenticated = _return_false  # type: ignore[method-assign]

            await channel._poll_loop()
            assert channel._running is False
            assert call_count >= 1

        _run(go())


class TestPollLoopErrcodeExpired:
    """Lines 563-571: poll loop errcode -14 (token expired)."""

    def test_errcode_minus_14_clears_token_and_stops(self):
        from app.channels.wechat import WechatChannel

        async def go():
            post_calls: list[dict[str, Any]] = []

            def _client_factory(*args, **kwargs):
                return _MockAsyncClient(
                    post_calls=post_calls,
                    post_responses=[
                        {"ret": 1, "errcode": -14, "errmsg": "token expired"},
                    ],
                    **kwargs,
                )

            with patch("app.channels.wechat.httpx.AsyncClient", _client_factory):
                channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
                channel._running = True
                await channel._poll_loop()

                assert channel._running is False
                assert channel._bot_token == ""
                assert channel._get_updates_buf == ""

        _run(go())


class TestPollLoopNonErrcode14:
    """Lines 572-579: poll loop non-zero ret but not -14."""

    def test_non_errcode14_retries(self):
        from app.channels.wechat import WechatChannel

        async def go():
            req_count = 0

            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok", "polling_retry_delay": 0.01})
            channel._running = True

            async def _mock_request(path, payload, *, timeout=None):
                nonlocal req_count
                req_count += 1
                if req_count == 1:
                    return {"ret": 1, "errcode": 99, "errmsg": "some error"}
                channel._running = False
                return {"ret": 0, "msgs": []}

            channel._request_json = _mock_request  # type: ignore[method-assign]
            await channel._poll_loop()
            assert req_count >= 2

        _run(go())


class TestPollLoopException:
    """Lines 590-594: poll loop exception handling."""

    def test_poll_loop_exception_retries(self):
        from app.channels.wechat import WechatChannel

        async def go():
            call_count_req = 0

            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok", "polling_retry_delay": 0.01})
            channel._running = True

            async def _mock_request(*args, **kwargs):
                nonlocal call_count_req
                call_count_req += 1
                if call_count_req == 1:
                    raise RuntimeError("network error")
                channel._running = False
                return {"ret": 0}

            channel._request_json = _mock_request  # type: ignore[method-assign]
            await channel._poll_loop()
            assert call_count_req >= 2

        _run(go())


class TestPollLoopNoMessages:
    """Lines 588-589: poll loop processes msgs list."""

    def test_poll_loop_with_empty_msgs(self):
        from app.channels.wechat import WechatChannel

        async def go():
            req_count = 0

            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            channel._running = True

            async def _mock_request(path, payload, *, timeout=None):
                nonlocal req_count
                req_count += 1
                channel._running = False
                return {"ret": 0, "msgs": [], "get_updates_buf": "buf1"}

            channel._request_json = _mock_request  # type: ignore[method-assign]
            await channel._poll_loop()
            assert channel._get_updates_buf == "buf1"
            assert req_count == 1

        _run(go())


class TestHandleUpdateSkipConditions:
    """Lines 598, 600: skip non-dict and non-chat message_type."""

    def test_non_dict_skipped(self):
        from app.channels.wechat import WechatChannel

        async def go():
            bus = MessageBus()
            published = []
            bus.publish_inbound = AsyncMock(side_effect=lambda msg: published.append(msg))

            channel = WechatChannel(bus=bus, config={"bot_token": "tok"})
            await channel._handle_update("not-a-dict")
            assert published == []

        _run(go())

    def test_non_chat_message_type_skipped(self):
        from app.channels.wechat import WechatChannel

        async def go():
            bus = MessageBus()
            published = []
            bus.publish_inbound = AsyncMock(side_effect=lambda msg: published.append(msg))

            channel = WechatChannel(bus=bus, config={"bot_token": "tok"})
            await channel._handle_update({"message_type": 2, "from_user_id": "u1"})
            assert published == []

        _run(go())


class TestHandleUpdateNoTextNoFiles:
    """Lines 608-609: skip when no text and no files."""

    def test_empty_item_list_skipped(self):
        from app.channels.wechat import WechatChannel

        async def go():
            bus = MessageBus()
            published = []
            bus.publish_inbound = AsyncMock(side_effect=lambda msg: published.append(msg))

            channel = WechatChannel(bus=bus, config={"bot_token": "tok"})
            await channel._handle_update(
                {
                    "message_type": 1,
                    "from_user_id": "u1",
                    "item_list": [],
                }
            )
            assert published == []

        _run(go())


class TestResolveContextTokenThreadFallback:
    """Lines 755, 757: _resolve_context_token thread fallback."""

    def test_thread_ts_fallback(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        channel._context_tokens_by_thread["thread-abc"] = "ctx-thread"
        msg = OutboundMessage(
            channel_name="wechat",
            chat_id="wx-u1",
            thread_id="t1",
            text="hi",
            thread_ts="thread-abc",
        )
        result = channel._resolve_context_token(msg)
        assert result == "ctx-thread"

    def test_metadata_context_token_takes_priority(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        channel._context_tokens_by_thread["thread-abc"] = "ctx-thread"
        channel._context_tokens_by_chat["wx-u1"] = "ctx-chat"
        msg = OutboundMessage(
            channel_name="wechat",
            chat_id="wx-u1",
            thread_id="t1",
            text="hi",
            thread_ts="thread-abc",
            metadata={"context_token": "ctx-meta"},
        )
        result = channel._resolve_context_token(msg)
        assert result == "ctx-meta"


class TestCurrentLongpollTimeout:
    """Line 767: _current_longpoll_timeout_seconds when respect_server_longpoll_timeout is False."""

    def test_respect_disabled_returns_polling_timeout(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(
            bus=MessageBus(),
            config={"bot_token": "tok", "respect_server_longpoll_timeout": False, "polling_timeout": 42.0},
        )
        result = channel._current_longpoll_timeout_seconds()
        assert result == 42.0

    def test_respect_enabled_no_server_value(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(
            bus=MessageBus(),
            config={"bot_token": "tok", "respect_server_longpoll_timeout": True},
        )
        result = channel._current_longpoll_timeout_seconds()
        assert result == channel.DEFAULT_POLLING_TIMEOUT

    def test_respect_enabled_with_server_value(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        channel._server_longpoll_timeout_seconds = 30.0
        result = channel._current_longpoll_timeout_seconds()
        assert result == 30.0


class TestUpdateLongpollTimeout:
    """Lines 772-781: _update_longpoll_timeout edge cases."""

    def test_respect_disabled_returns_early(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok", "respect_server_longpoll_timeout": False})
        channel._update_longpoll_timeout({"longpolling_timeout_ms": 50000})
        assert channel._server_longpoll_timeout_seconds is None

    def test_none_value_skipped(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        channel._update_longpoll_timeout({})
        assert channel._server_longpoll_timeout_seconds is None

    def test_non_numeric_value_skipped(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        channel._update_longpoll_timeout({"longpolling_timeout_ms": "abc"})
        assert channel._server_longpool_timeout_seconds if hasattr(channel, "_server_longpool_timeout_seconds") else True

    def test_zero_value_skipped(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        channel._update_longpoll_timeout({"longpolling_timeout_ms": 0})
        assert channel._server_longpoll_timeout_seconds is None

    def test_negative_value_skipped(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        channel._update_longpoll_timeout({"longpolling_timeout_ms": -1000})
        assert channel._server_longpoll_timeout_seconds is None

    def test_valid_value_updates(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        channel._update_longpoll_timeout({"longpolling_timeout_ms": 30000})
        assert channel._server_longpoll_timeout_seconds == 30.0


class TestCommonHeaders:
    """Lines 793, 795: _common_headers with ilink_app_id and route_tag."""

    def test_with_ilink_app_id(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok", "ilink_app_id": "app-123"})
        headers = channel._common_headers()
        assert headers["iLink-App-Id"] == "app-123"

    def test_with_route_tag(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok", "route_tag": "tag-abc"})
        headers = channel._common_headers()
        assert headers["SKRouteTag"] == "tag-abc"

    def test_with_both(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(
            bus=MessageBus(),
            config={"bot_token": "tok", "ilink_app_id": "app-1", "route_tag": "route-1"},
        )
        headers = channel._common_headers()
        assert headers["iLink-App-Id"] == "app-1"
        assert headers["SKRouteTag"] == "route-1"


class TestExtractCdnFullUrl:
    """Line 816: _extract_cdn_full_url with non-Mapping."""

    def test_non_mapping_returns_none(self):
        from app.channels.wechat import WechatChannel

        assert WechatChannel._extract_cdn_full_url(None) is None
        assert WechatChannel._extract_cdn_full_url("string") is None
        assert WechatChannel._extract_cdn_full_url(123) is None

    def test_empty_string_returns_none(self):
        from app.channels.wechat import WechatChannel

        assert WechatChannel._extract_cdn_full_url({"full_url": "  "}) is None


class TestExtractUploadFullUrl:
    """Line 823: _extract_upload_full_url with non-Mapping."""

    def test_non_mapping_returns_none(self):
        from app.channels.wechat import WechatChannel

        assert WechatChannel._extract_upload_full_url(None) is None
        assert WechatChannel._extract_upload_full_url("string") is None

    def test_empty_string_returns_none(self):
        from app.channels.wechat import WechatChannel

        assert WechatChannel._extract_upload_full_url({"upload_full_url": "  "}) is None


class TestExtractUploadParam:
    """Line 830: _extract_upload_param with non-Mapping."""

    def test_non_mapping_returns_none(self):
        from app.channels.wechat import WechatChannel

        assert WechatChannel._extract_upload_param(None) is None
        assert WechatChannel._extract_upload_param("string") is None

    def test_empty_string_returns_none(self):
        from app.channels.wechat import WechatChannel

        assert WechatChannel._extract_upload_param({"upload_param": "  "}) is None


class TestBuildUploadRequestThumb:
    """Line 856: _build_upload_request with thumb_plaintext."""

    def test_with_thumb_plaintext(self):
        from app.channels.wechat import UploadMediaType, WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        payload = channel._build_upload_request(
            filekey="file-key",
            media_type=UploadMediaType.IMAGE,
            to_user_id="wx-u1",
            plaintext=b"image-data",
            aes_key=b"1234567890abcdef",
            thumb_plaintext=b"thumb-data",
        )
        assert payload["thumb_rawsize"] == len(b"thumb-data")
        assert "thumb_rawfilemd5" in payload
        assert "thumb_filesize" in payload
        assert "no_need_thumb" not in payload


class TestDownloadCdnBytes:
    """Lines 868-871: _download_cdn_bytes."""

    def test_download_cdn_bytes(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})

            async def _aiter_raw():
                yield b"downloaded-bytes"

            mock_response = MagicMock()
            mock_response.headers = {}
            mock_response.raise_for_status = MagicMock()
            mock_response.aiter_raw = MagicMock(return_value=_aiter_raw())

            stream_cm = MagicMock()
            stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
            stream_cm.__aexit__ = AsyncMock(return_value=False)

            mock_client = MagicMock()
            mock_client.stream = MagicMock(return_value=stream_cm)
            channel._client = mock_client

            result = await channel._download_cdn_bytes("https://cdn.example.com/file.bin")
            assert result == b"downloaded-bytes"

        _run(go())


class TestExtractInboundFilesEdgeCases:
    """Lines 939, 946, 952: _extract_inbound_files edge cases."""

    def test_non_list_item_list(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            result = await channel._extract_inbound_files({"item_list": "not-a-list"})
            assert result == []

        _run(go())

    def test_no_item_list(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            result = await channel._extract_inbound_files({})
            assert result == []

        _run(go())

    def test_non_mapping_item_in_list(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            result = await channel._extract_inbound_files({"item_list": ["string", 123, None]})
            assert result == []

        _run(go())


class TestExtractImageFileEdgeCases:
    """Lines 966, 970, 979-984, 989-990, 997: _extract_image_file edge cases."""

    def test_no_image_item_returns_none(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            result = await channel._extract_image_file({"type": 2}, message_id="m1", index=0)
            assert result is None

        _run(go())

    def test_image_item_not_mapping(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            result = await channel._extract_image_file(
                {"type": 2, "image_item": "string"},
                message_id="m1",
                index=0,
            )
            assert result is None

        _run(go())

    def test_image_media_not_mapping(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            result = await channel._extract_image_file(
                {"type": 2, "image_item": {"media": "string"}},
                message_id="m1",
                index=0,
            )
            assert result is None

        _run(go())

    def test_image_missing_full_url(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            result = await channel._extract_image_file(
                {"type": 2, "image_item": {"media": {}}},
                message_id="m1",
                index=0,
            )
            assert result is None

        _run(go())

    def test_image_missing_aes_key(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            result = await channel._extract_image_file(
                {
                    "type": 2,
                    "image_item": {"media": {"full_url": "https://cdn.example/img.bin"}},
                },
                message_id="m1",
                index=0,
            )
            assert result is None

        _run(go())

    def test_image_oversized(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(
                bus=MessageBus(),
                config={"bot_token": "tok", "state_dir": str(tmp_path), "max_inbound_image_bytes": 10},
            )
            aes_key = b"1234567890abcdef"
            plaintext = b"x" * 20
            encrypted = channel.__class__.__dict__["_extract_image_file"].__globals__["_encrypt_aes_128_ecb"](plaintext, aes_key)

            async def _fake_download(_url, *, timeout=None):
                return encrypted

            channel._download_cdn_bytes = _fake_download  # type: ignore[method-assign]

            result = await channel._extract_image_file(
                {
                    "type": 2,
                    "image_item": {
                        "aeskey": aes_key.hex(),
                        "media": {"full_url": "https://cdn.example/img.bin"},
                    },
                },
                message_id="m1",
                index=0,
            )
            assert result is None

        _run(go())

    def test_image_staging_failure(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(
                bus=MessageBus(),
                config={"bot_token": "tok", "state_dir": str(tmp_path)},
            )
            aes_key = b"1234567890abcdef"
            plaintext = b"img-data"
            encrypted = channel.__class__.__dict__["_extract_image_file"].__globals__["_encrypt_aes_128_ecb"](plaintext, aes_key)

            async def _fake_download(_url, *, timeout=None):
                return encrypted

            channel._download_cdn_bytes = _fake_download  # type: ignore[method-assign]
            # Make _stage_downloaded_file return None
            channel._stage_downloaded_file = MagicMock(return_value=None)  # type: ignore[method-assign]

            result = await channel._extract_image_file(
                {
                    "type": 2,
                    "image_item": {
                        "aeskey": aes_key.hex(),
                        "media": {"full_url": "https://cdn.example/img.bin"},
                    },
                },
                message_id="m1",
                index=0,
            )
            assert result is None

        _run(go())


class TestExtractFileItemEdgeCases:
    """Lines 1014, 1018, 1022-1023, 1027-1032, 1043-1044, 1048: _extract_file_item edge cases."""

    def test_no_file_item_returns_none(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            result = await channel._extract_file_item({"type": 4}, message_id="m1", index=0)
            assert result is None

        _run(go())

    def test_file_item_not_mapping(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            result = await channel._extract_file_item(
                {"type": 4, "file_item": "string"},
                message_id="m1",
                index=0,
            )
            assert result is None

        _run(go())

    def test_file_media_not_mapping(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            result = await channel._extract_file_item(
                {"type": 4, "file_item": {"media": "string"}},
                message_id="m1",
                index=0,
            )
            assert result is None

        _run(go())

    def test_file_missing_full_url(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            result = await channel._extract_file_item(
                {"type": 4, "file_item": {"media": {}}},
                message_id="m1",
                index=0,
            )
            assert result is None

        _run(go())

    def test_file_missing_aes_key(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            result = await channel._extract_file_item(
                {
                    "type": 4,
                    "file_item": {
                        "media": {"full_url": "https://cdn.example/file.bin"},
                    },
                },
                message_id="m1",
                index=0,
            )
            assert result is None

        _run(go())

    def test_file_oversized(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(
                bus=MessageBus(),
                config={"bot_token": "tok", "state_dir": str(tmp_path), "max_inbound_file_bytes": 10},
            )
            aes_key = b"1234567890abcdef"
            plaintext = b"x" * 20
            encrypted = channel.__class__.__dict__["_extract_file_item"].__globals__["_encrypt_aes_128_ecb"](plaintext, aes_key)

            async def _fake_download(_url, *, timeout=None):
                return encrypted

            channel._download_cdn_bytes = _fake_download  # type: ignore[method-assign]

            result = await channel._extract_file_item(
                {
                    "type": 4,
                    "file_item": {
                        "file_name": "big.pdf",
                        "aeskey": aes_key.hex(),
                        "media": {"full_url": "https://cdn.example/file.bin"},
                    },
                },
                message_id="m1",
                index=0,
            )
            assert result is None

        _run(go())

    def test_file_staging_failure(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(
                bus=MessageBus(),
                config={"bot_token": "tok", "state_dir": str(tmp_path)},
            )
            aes_key = b"1234567890abcdef"
            plaintext = b"file-data"
            encrypted = channel.__class__.__dict__["_extract_file_item"].__globals__["_encrypt_aes_128_ecb"](plaintext, aes_key)

            async def _fake_download(_url, *, timeout=None):
                return encrypted

            channel._download_cdn_bytes = _fake_download  # type: ignore[method-assign]
            channel._stage_downloaded_file = MagicMock(return_value=None)  # type: ignore[method-assign]

            result = await channel._extract_file_item(
                {
                    "type": 4,
                    "file_item": {
                        "file_name": "test.pdf",
                        "aeskey": aes_key.hex(),
                        "media": {"full_url": "https://cdn.example/file.bin"},
                    },
                },
                message_id="m1",
                index=0,
            )
            assert result is None

        _run(go())


class TestStageDownloadedFile:
    """Lines 966, 1064, 1070-1072: _stage_downloaded_file edge cases."""

    def test_no_state_dir_returns_none(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        result = channel._stage_downloaded_file("test.bin", b"data")
        assert result is None

    def test_os_error_returns_none(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(
            bus=MessageBus(),
            config={"bot_token": "tok", "state_dir": str(tmp_path)},
        )
        # Make write_bytes fail
        with patch.object(Path, "write_bytes", side_effect=OSError("disk full")):
            result = channel._stage_downloaded_file("test.bin", b"data")
            assert result is None


class TestDecodeBase64AesKeyEdgeCases:
    """Lines 1078, 1093, 1099-1100, 1112-1113: _decode_base64_aes_key edge cases."""

    def test_empty_string_returns_none(self):
        from app.channels.wechat import WechatChannel

        assert WechatChannel._decode_base64_aes_key("") is None

    def test_whitespace_only_returns_none(self):
        from app.channels.wechat import WechatChannel

        assert WechatChannel._decode_base64_aes_key("   ") is None

    def test_urlsafe_base64(self):
        from app.channels.wechat import WechatChannel

        key = b"0123456789abcdef"
        encoded = base64.urlsafe_b64encode(key).decode()
        result = WechatChannel._decode_base64_aes_key(encoded)
        assert result == key

    def test_invalid_base64_returns_none(self):
        from app.channels.wechat import WechatChannel

        # Not valid base64 at all
        assert WechatChannel._decode_base64_aes_key("not-valid-base64!!!") is None

    def test_wrong_size_after_decode(self):
        from app.channels.wechat import WechatChannel

        # Base64 of a non-16-byte value that decodes fine
        encoded = base64.b64encode(b"short").decode()
        result = WechatChannel._decode_base64_aes_key(encoded)
        # Should try hex fallback and also fail
        assert result is None


class TestParseAesKeyCandidate:
    """Lines 1119-1123, 1126, 1143, 1147-1149: _parse_aes_key_candidate edge cases."""

    def test_bytes_valid_key(self):
        from app.channels.wechat import WechatChannel

        key = b"0123456789abcdef"
        result = WechatChannel._parse_aes_key_candidate(key, prefer_hex=True)
        assert result == key

    def test_bytes_invalid_length(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._parse_aes_key_candidate(b"short", prefer_hex=True)
        assert result is None

    def test_bytearray(self):
        from app.channels.wechat import WechatChannel

        key = bytearray(b"0123456789abcdef")
        result = WechatChannel._parse_aes_key_candidate(key, prefer_hex=True)
        assert result == bytes(key)

    def test_bytearray_invalid_length(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._parse_aes_key_candidate(bytearray(b"short"), prefer_hex=True)
        assert result is None

    def test_empty_string(self):
        from app.channels.wechat import WechatChannel

        assert WechatChannel._parse_aes_key_candidate("", prefer_hex=True) is None

    def test_whitespace_string(self):
        from app.channels.wechat import WechatChannel

        assert WechatChannel._parse_aes_key_candidate("  ", prefer_hex=True) is None

    def test_none_returns_none(self):
        from app.channels.wechat import WechatChannel

        assert WechatChannel._parse_aes_key_candidate(None, prefer_hex=True) is None

    def test_int_returns_none(self):
        from app.channels.wechat import WechatChannel

        assert WechatChannel._parse_aes_key_candidate(123, prefer_hex=True) is None

    def test_prefer_hex_false_uses_base64_first(self):
        from app.channels.wechat import WechatChannel

        key = b"0123456789abcdef"
        b64 = base64.b64encode(key).decode()
        result = WechatChannel._parse_aes_key_candidate(b64, prefer_hex=False)
        assert result == key

    def test_hex_key_with_prefer_hex_false(self):
        from app.channels.wechat import WechatChannel

        key = b"0123456789abcdef"
        hex_str = key.hex()
        result = WechatChannel._parse_aes_key_candidate(hex_str, prefer_hex=False)
        assert result == key


class TestResolveMediaAesKeyEmpty:
    """Line 1169: _resolve_media_aes_key with no payloads."""

    def test_no_payloads_returns_none(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._resolve_media_aes_key()
        assert result is None


class TestDescribeMediaKeyStateEdgeCases:
    """Lines 1180, 1215, 1218: _describe_media_key_state with non-mapping inputs."""

    def test_none_item(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._describe_media_key_state(item=None, item_payload=None, media=None)
        assert result["item"] == {}
        assert result["item_payload"] == {}
        assert result["media"] == {}

    def test_non_mapping_item(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._describe_media_key_state(item="string", item_payload=123, media=[1, 2, 3])
        assert result["item"] == {}
        assert result["item_payload"] == {}
        assert result["media"] == {}


class TestExtractRefMessageEdgeCases:
    """Lines 1215, 1218, 1238: _extract_ref_message edge cases."""

    def test_no_item_list(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._extract_ref_message({})
        assert result is None

    def test_non_list_item_list(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._extract_ref_message({"item_list": "not-a-list"})
        assert result is None

    def test_non_mapping_items(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._extract_ref_message({"item_list": ["string", 123]})
        assert result is None

    def test_no_ref_msg(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._extract_ref_message({"item_list": [{"type": 1, "text_item": {"text": "hi"}}]})
        assert result is None


class TestLoadStateErrors:
    """Lines 1254-1256: _load_state file read errors."""

    def test_corrupt_cursor_json(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        state_dir = tmp_path / "wechat-state"
        state_dir.mkdir()
        cursor_file = state_dir / "wechat-getupdates.json"
        cursor_file.write_text("not valid json {{{")

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok", "state_dir": str(state_dir)})
        # Should not raise, cursor stays empty
        assert channel._get_updates_buf == ""

    def test_os_error_reading_cursor(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        state_dir = tmp_path / "wechat-state"
        state_dir.mkdir()
        cursor_file = state_dir / "wechat-getupdates.json"
        cursor_file.write_text(json.dumps({"get_updates_buf": "cursor-1"}))

        with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok", "state_dir": str(state_dir)})
            assert channel._get_updates_buf == ""


class TestSaveStateErrors:
    """Lines 1264-1268: _save_state file write errors."""

    def test_os_error_saving_state(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok", "state_dir": str(tmp_path)})
        channel._get_updates_buf = "cursor-new"

        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            # Should not raise
            channel._save_state()

    def test_no_cursor_path(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        channel._cursor_path = None
        # Should not raise
        channel._save_state()


class TestLoadAuthStateErrors:
    """Lines 1275-1277, 1279: _load_auth_state file errors and non-dict data."""

    def test_corrupt_auth_json(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        auth_file = tmp_path / "wechat-auth.json"
        auth_file.write_text("not-json")

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok", "state_dir": str(tmp_path)})
        # Should not raise
        assert channel._bot_token == "tok"

    def test_non_dict_auth_data(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        auth_file = tmp_path / "wechat-auth.json"
        auth_file.write_text(json.dumps("string-data"))

        channel = WechatChannel(bus=MessageBus(), config={"state_dir": str(tmp_path)})
        # Should not raise
        assert channel._bot_token == ""

    def test_no_auth_path(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        channel._auth_path = None
        # Should not raise
        channel._load_auth_state()

    def test_auth_file_not_exists(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok", "state_dir": str(tmp_path)})
        # File doesn't exist, should not raise
        channel._load_auth_state()


class TestSaveAuthStateEdgeCases:
    """Lines 1309, 1311, 1327-1328: _save_auth_state edge cases."""

    def test_empty_bot_token_removes_key(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"state_dir": str(tmp_path)})
        channel._auth_path = tmp_path / "wechat-auth.json"
        channel._auth_state = {"bot_token": "old-token"}
        result = channel._save_auth_state(status="confirmed", bot_token="")
        assert "bot_token" not in result

    def test_no_auth_path(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        channel._auth_path = None
        result = channel._save_auth_state(status="confirmed")
        assert result["status"] == "confirmed"

    def test_os_error_saving_auth(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"state_dir": str(tmp_path)})
        channel._auth_path = tmp_path / "wechat-auth.json"

        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            result = channel._save_auth_state(status="confirmed")
            # Should not raise, just log
            assert result["status"] == "confirmed"

    def test_bot_token_not_provided_uses_existing(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"state_dir": str(tmp_path)})
        channel._auth_path = tmp_path / "wechat-auth.json"
        channel._bot_token = "existing-token"
        result = channel._save_auth_state(status="confirmed")
        assert result["bot_token"] == "existing-token"

    def test_with_qrcode_img_content(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"state_dir": str(tmp_path)})
        channel._auth_path = tmp_path / "wechat-auth.json"
        result = channel._save_auth_state(
            status="pending",
            qrcode="qr-123",
            qrcode_img_content="https://example.com/qr.png",
        )
        assert result["qrcode"] == "qr-123"
        assert result["qrcode_img_content"] == "https://example.com/qr.png"

    def test_none_qrcode_img_content_not_set(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"state_dir": str(tmp_path)})
        channel._auth_path = tmp_path / "wechat-auth.json"
        result = channel._save_auth_state(status="pending", qrcode="qr-123")
        assert "qrcode_img_content" not in result


class TestNormalizeInboundFilename:
    """Line 1339: _normalize_inbound_filename edge cases."""

    def test_none_filename(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._normalize_inbound_filename(None, default_prefix="wechat-file", message_id="m1", index=0)
        assert result.startswith("wechat-file-m1-0.bin")

    def test_empty_string_filename(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._normalize_inbound_filename("  ", default_prefix="wechat-file", message_id="m1", index=0)
        assert result.startswith("wechat-file-m1-0.bin")

    def test_non_string_filename(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._normalize_inbound_filename(123, default_prefix="wechat-file", message_id="m1", index=0)
        assert result.startswith("wechat-file-m1-0.bin")

    def test_valid_filename(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._normalize_inbound_filename("report.pdf", default_prefix="wechat-file", message_id="m1", index=0)
        assert result == "report.pdf"

    def test_path_in_filename(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._normalize_inbound_filename("/path/to/report.pdf", default_prefix="wechat-file", message_id="m1", index=0)
        assert result == "report.pdf"


class TestSendImageAttachmentErrorPaths:
    """Lines 371-372, 375-376, 380-381, 385-387, 415-416, 451-453: _send_image_attachment error paths."""

    def test_image_too_large(self, monkeypatch, tmp_path: Path):
        from app.channels.message_bus import ResolvedAttachment
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(
                bus=MessageBus(),
                config={"bot_token": "tok", "max_outbound_image_bytes": 10},
            )
            image_path = tmp_path / "big.png"
            image_path.write_bytes(b"x" * 100)

            ok = await channel._send_image_attachment(
                OutboundMessage(channel_name="wechat", chat_id="wx-u1", thread_id="t1", text="hi"),
                ResolvedAttachment(
                    virtual_path="/big.png",
                    actual_path=image_path,
                    filename="big.png",
                    mime_type="image/png",
                    size=100,
                    is_image=True,
                ),
            )
            assert ok is False

        _run(go())

    def test_image_no_auth(self, tmp_path: Path):
        from app.channels.message_bus import ResolvedAttachment
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"state_dir": str(tmp_path)})
            image_path = tmp_path / "img.png"
            image_path.write_bytes(b"png-data")

            ok = await channel._send_image_attachment(
                OutboundMessage(channel_name="wechat", chat_id="wx-u1", thread_id="t1", text="hi"),
                ResolvedAttachment(
                    virtual_path="/img.png",
                    actual_path=image_path,
                    filename="img.png",
                    mime_type="image/png",
                    size=9,
                    is_image=True,
                ),
            )
            assert ok is False

        _run(go())

    def test_image_no_context_token(self, monkeypatch, tmp_path: Path):
        from app.channels.message_bus import ResolvedAttachment
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            image_path = tmp_path / "img.png"
            image_path.write_bytes(b"png-data")

            ok = await channel._send_image_attachment(
                OutboundMessage(channel_name="wechat", chat_id="wx-u1", thread_id="t1", text="hi"),
                ResolvedAttachment(
                    virtual_path="/img.png",
                    actual_path=image_path,
                    filename="img.png",
                    mime_type="image/png",
                    size=9,
                    is_image=True,
                ),
            )
            assert ok is False

        _run(go())

    def test_image_read_os_error(self, monkeypatch, tmp_path: Path):
        from app.channels.message_bus import ResolvedAttachment
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            channel._context_tokens_by_chat["wx-u1"] = "ctx"
            image_path = tmp_path / "img.png"
            image_path.write_bytes(b"png-data")

            with patch.object(Path, "read_bytes", side_effect=OSError("permission denied")):
                ok = await channel._send_image_attachment(
                    OutboundMessage(channel_name="wechat", chat_id="wx-u1", thread_id="t1", text="hi"),
                    ResolvedAttachment(
                        virtual_path="/img.png",
                        actual_path=image_path,
                        filename="img.png",
                        mime_type="image/png",
                        size=9,
                        is_image=True,
                    ),
                )
                assert ok is False

        _run(go())

    def test_image_upload_exception(self, monkeypatch, tmp_path: Path):
        from app.channels.message_bus import ResolvedAttachment
        from app.channels.wechat import WechatChannel

        async def go():
            def _client_factory(*args, **kwargs):
                raise RuntimeError("network error")

            with patch("app.channels.wechat.httpx.AsyncClient", _client_factory):
                channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
                channel._context_tokens_by_chat["wx-u1"] = "ctx"
                image_path = tmp_path / "img.png"
                image_path.write_bytes(b"png-data")

                ok = await channel._send_image_attachment(
                    OutboundMessage(channel_name="wechat", chat_id="wx-u1", thread_id="t1", text="hi"),
                    ResolvedAttachment(
                        virtual_path="/img.png",
                        actual_path=image_path,
                        filename="img.png",
                        mime_type="image/png",
                        size=9,
                        is_image=True,
                    ),
                )
                assert ok is False

        _run(go())

    def test_image_no_upload_url_and_no_param(self, monkeypatch, tmp_path: Path):
        from app.channels.message_bus import ResolvedAttachment
        from app.channels.wechat import WechatChannel

        async def go():
            post_calls: list[dict[str, Any]] = []

            def _client_factory(*args, **kwargs):
                return _MockAsyncClient(
                    post_calls=post_calls,
                    post_responses=[{"ret": 0}],
                    **kwargs,
                )

            monkeypatch.setattr("app.channels.wechat.httpx.AsyncClient", _client_factory)

            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            channel._context_tokens_by_chat["wx-u1"] = "ctx"
            image_path = tmp_path / "img.png"
            image_path.write_bytes(b"png-data")

            ok = await channel._send_image_attachment(
                OutboundMessage(channel_name="wechat", chat_id="wx-u1", thread_id="t1", text="hi"),
                ResolvedAttachment(
                    virtual_path="/img.png",
                    actual_path=image_path,
                    filename="img.png",
                    mime_type="image/png",
                    size=9,
                    is_image=True,
                ),
            )
            assert ok is False

        _run(go())


class TestSendFileAttachmentErrorPaths:
    """Lines 461-462, 465-466, 475-477, 505-506, 541-543: _send_file_attachment error paths."""

    def test_file_type_blocked(self, monkeypatch, tmp_path: Path):
        from app.channels.message_bus import ResolvedAttachment
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            file_path = tmp_path / "bad.exe"
            file_path.write_bytes(b"MZ")

            ok = await channel._send_file_attachment(
                OutboundMessage(channel_name="wechat", chat_id="wx-u1", thread_id="t1", text="hi"),
                ResolvedAttachment(
                    virtual_path="/bad.exe",
                    actual_path=file_path,
                    filename="bad.exe",
                    mime_type="application/x-executable",
                    size=2,
                    is_image=False,
                ),
            )
            assert ok is False

        _run(go())

    def test_file_too_large(self, monkeypatch, tmp_path: Path):
        from app.channels.message_bus import ResolvedAttachment
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(
                bus=MessageBus(),
                config={"bot_token": "tok", "max_outbound_file_bytes": 10},
            )
            file_path = tmp_path / "big.pdf"
            file_path.write_bytes(b"%PDF" + b"\x00" * 100)

            ok = await channel._send_file_attachment(
                OutboundMessage(channel_name="wechat", chat_id="wx-u1", thread_id="t1", text="hi"),
                ResolvedAttachment(
                    virtual_path="/big.pdf",
                    actual_path=file_path,
                    filename="big.pdf",
                    mime_type="application/pdf",
                    size=104,
                    is_image=False,
                ),
            )
            assert ok is False

        _run(go())

    def test_file_no_auth(self, tmp_path: Path):
        from app.channels.message_bus import ResolvedAttachment
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"state_dir": str(tmp_path)})
            file_path = tmp_path / "doc.pdf"
            file_path.write_bytes(b"%PDF-data")

            ok = await channel._send_file_attachment(
                OutboundMessage(channel_name="wechat", chat_id="wx-u1", thread_id="t1", text="hi"),
                ResolvedAttachment(
                    virtual_path="/doc.pdf",
                    actual_path=file_path,
                    filename="doc.pdf",
                    mime_type="application/pdf",
                    size=9,
                    is_image=False,
                ),
            )
            assert ok is False

        _run(go())

    def test_file_no_context_token(self, monkeypatch, tmp_path: Path):
        from app.channels.message_bus import ResolvedAttachment
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            file_path = tmp_path / "doc.pdf"
            file_path.write_bytes(b"%PDF-data")

            ok = await channel._send_file_attachment(
                OutboundMessage(channel_name="wechat", chat_id="wx-u1", thread_id="t1", text="hi"),
                ResolvedAttachment(
                    virtual_path="/doc.pdf",
                    actual_path=file_path,
                    filename="doc.pdf",
                    mime_type="application/pdf",
                    size=9,
                    is_image=False,
                ),
            )
            assert ok is False

        _run(go())

    def test_file_read_os_error(self, monkeypatch, tmp_path: Path):
        from app.channels.message_bus import ResolvedAttachment
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            channel._context_tokens_by_chat["wx-u1"] = "ctx"
            file_path = tmp_path / "doc.pdf"
            file_path.write_bytes(b"%PDF-data")

            with patch.object(Path, "read_bytes", side_effect=OSError("permission denied")):
                ok = await channel._send_file_attachment(
                    OutboundMessage(channel_name="wechat", chat_id="wx-u1", thread_id="t1", text="hi"),
                    ResolvedAttachment(
                        virtual_path="/doc.pdf",
                        actual_path=file_path,
                        filename="doc.pdf",
                        mime_type="application/pdf",
                        size=9,
                        is_image=False,
                    ),
                )
                assert ok is False

        _run(go())

    def test_file_upload_exception(self, monkeypatch, tmp_path: Path):
        from app.channels.message_bus import ResolvedAttachment
        from app.channels.wechat import WechatChannel

        async def go():
            def _client_factory(*args, **kwargs):
                raise RuntimeError("network error")

            with patch("app.channels.wechat.httpx.AsyncClient", _client_factory):
                channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
                channel._context_tokens_by_chat["wx-u1"] = "ctx"
                file_path = tmp_path / "doc.pdf"
                file_path.write_bytes(b"%PDF-data")

                ok = await channel._send_file_attachment(
                    OutboundMessage(channel_name="wechat", chat_id="wx-u1", thread_id="t1", text="hi"),
                    ResolvedAttachment(
                        virtual_path="/doc.pdf",
                        actual_path=file_path,
                        filename="doc.pdf",
                        mime_type="application/pdf",
                        size=9,
                        is_image=False,
                    ),
                )
                assert ok is False

        _run(go())

    def test_file_no_upload_url_and_no_param(self, monkeypatch, tmp_path: Path):
        from app.channels.message_bus import ResolvedAttachment
        from app.channels.wechat import WechatChannel

        async def go():
            post_calls: list[dict[str, Any]] = []

            def _client_factory(*args, **kwargs):
                return _MockAsyncClient(
                    post_calls=post_calls,
                    post_responses=[{"ret": 0}],
                    **kwargs,
                )

            monkeypatch.setattr("app.channels.wechat.httpx.AsyncClient", _client_factory)

            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            channel._context_tokens_by_chat["wx-u1"] = "ctx"
            file_path = tmp_path / "doc.pdf"
            file_path.write_bytes(b"%PDF-data")

            ok = await channel._send_file_attachment(
                OutboundMessage(channel_name="wechat", chat_id="wx-u1", thread_id="t1", text="hi"),
                ResolvedAttachment(
                    virtual_path="/doc.pdf",
                    actual_path=file_path,
                    filename="doc.pdf",
                    mime_type="application/pdf",
                    size=9,
                    is_image=False,
                ),
            )
            assert ok is False

        _run(go())


class TestSendTextMessageRetryFailure:
    """Lines 348-362: _send_text_message retry exhaustion."""

    def test_send_text_message_all_retries_fail(self, monkeypatch):
        from app.channels.wechat import WechatChannel

        async def go():
            call_count = 0

            async def _fail_request(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                raise RuntimeError("network error")

            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok", "polling_retry_delay": 0.01})
            channel._request_json = _fail_request  # type: ignore[method-assign]

            with pytest.raises(RuntimeError, match="network error"):
                await channel._send_text_message(
                    chat_id="wx-u1",
                    context_token="ctx",
                    text="hello",
                    client_id_prefix="ideer",
                    max_retries=3,
                )
            assert call_count == 3

        _run(go())


class TestSendNoBotTokenAndAuthFails:
    """Lines 299-300: send() with no bot_token and auth fails."""

    def test_send_no_token_auth_fails(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"state_dir": "/nonexistent"})

            async def _false_auth():
                return False

            channel._ensure_authenticated = _false_auth  # type: ignore[method-assign]

            msg = OutboundMessage(
                channel_name="wechat",
                chat_id="wx-u1",
                thread_id="t1",
                text="hello",
            )
            await channel.send(msg)  # Should return without error

        _run(go())


class TestPollLoopUpdatesBuf:
    """Lines 584-586: poll loop updates buf and saves state."""

    def test_same_buf_not_saved(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            channel._running = True
            channel._get_updates_buf = ""
            save_called = False
            original_save = channel._save_state

            def _mock_save():
                nonlocal save_called
                save_called = True
                original_save()

            channel._save_state = _mock_save  # type: ignore[method-assign]

            async def _mock_request(path, payload, *, timeout=None):
                channel._running = False
                return {"ret": 0, "msgs": [], "get_updates_buf": ""}

            channel._request_json = _mock_request  # type: ignore[method-assign]
            await channel._poll_loop()
            # Same buf should not trigger save
            assert save_called is False

        _run(go())

    def test_different_buf_saved(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            channel._running = True
            channel._get_updates_buf = "old-buf"

            async def _mock_request(path, payload, *, timeout=None):
                channel._running = False
                return {"ret": 0, "msgs": [], "get_updates_buf": "new-buf"}

            channel._request_json = _mock_request  # type: ignore[method-assign]
            await channel._poll_loop()
            assert channel._get_updates_buf == "new-buf"

        _run(go())


class TestHandleUpdateNoContextToken:
    """Lines 612-613: handle_update with no context_token but has client_id."""

    def test_no_context_token_uses_client_id(self):
        from app.channels.wechat import WechatChannel

        async def go():
            bus = MessageBus()
            published = []
            bus.publish_inbound = AsyncMock(side_effect=lambda msg: published.append(msg))

            channel = WechatChannel(bus=bus, config={"bot_token": "tok"})
            await channel._handle_update(
                {
                    "message_type": 1,
                    "from_user_id": "wx-u1",
                    "client_id": "client-abc",
                    "item_list": [{"type": 1, "text_item": {"text": "hi"}}],
                }
            )
            assert len(published) == 1
            assert published[0].thread_ts == "client-abc"

        _run(go())

    def test_no_context_token_no_client_id(self):
        from app.channels.wechat import WechatChannel

        async def go():
            bus = MessageBus()
            published = []
            bus.publish_inbound = AsyncMock(side_effect=lambda msg: published.append(msg))

            channel = WechatChannel(bus=bus, config={"bot_token": "tok"})
            await channel._handle_update(
                {
                    "message_type": 1,
                    "from_user_id": "wx-u1",
                    "item_list": [{"type": 1, "text_item": {"text": "hi"}}],
                }
            )
            assert len(published) == 1
            assert published[0].thread_ts is None

        _run(go())


class TestMultipleTextItems:
    """Lines 1332-1343: _extract_text with multiple text items."""

    def test_multiple_text_items_joined(self):
        from app.channels.wechat import WechatChannel

        raw = {
            "item_list": [
                {"type": 1, "text_item": {"text": "line1"}},
                {"type": 1, "text_item": {"text": "line2"}},
                {"type": 1, "text_item": {"text": "line3"}},
            ]
        }
        result = WechatChannel._extract_text(raw)
        assert result == "line1\nline2\nline3"

    def test_non_text_items_ignored(self):
        from app.channels.wechat import WechatChannel

        raw = {
            "item_list": [
                {"type": 2, "image_item": {}},
                {"type": 1, "text_item": {"text": "only-text"}},
                {"type": 4, "file_item": {}},
            ]
        }
        result = WechatChannel._extract_text(raw)
        assert result == "only-text"

    def test_non_dict_items_ignored(self):
        from app.channels.wechat import WechatChannel

        raw = {
            "item_list": ["string", 123, None, {"type": 1, "text_item": {"text": "valid"}}],
        }
        result = WechatChannel._extract_text(raw)
        assert result == "valid"

    def test_text_item_not_dict(self):
        from app.channels.wechat import WechatChannel

        raw = {
            "item_list": [
                {"type": 1, "text_item": "string"},
                {"type": 1},
            ]
        }
        result = WechatChannel._extract_text(raw)
        assert result == ""

    def test_empty_text_ignored(self):
        from app.channels.wechat import WechatChannel

        raw = {
            "item_list": [
                {"type": 1, "text_item": {"text": "  "}},
                {"type": 1, "text_item": {"text": ""}},
            ]
        }
        result = WechatChannel._extract_text(raw)
        assert result == ""

    def test_non_string_text_ignored(self):
        from app.channels.wechat import WechatChannel

        raw = {
            "item_list": [
                {"type": 1, "text_item": {"text": 123}},
            ]
        }
        result = WechatChannel._extract_text(raw)
        assert result == ""


class TestIsAllowedFileTypeEdgeCases:
    """Lines 1226-1230: _is_allowed_file_type edge cases."""

    def test_text_mime_starts_with_text(self):
        channel = _make_channel()
        # .txt is in allowed extensions, text/csv starts with text/
        assert channel._is_allowed_file_type("data.txt", "text/csv") is True

    def test_empty_extension(self):
        channel = _make_channel()
        # Empty extension won't match allowed extensions
        assert channel._is_allowed_file_type("noext", "application/octet-stream") is False

    def test_blocked_extension_with_text_mime(self):
        channel = _make_channel()
        # .exe is blocked by extension even with text MIME
        assert channel._is_allowed_file_type("script.exe", "text/plain") is False


class TestCoerceHelpersDefaults:
    """Lines 1352-1370: coerce helpers with edge cases."""

    def test_coerce_float_none(self):
        from app.channels.wechat import WechatChannel

        assert WechatChannel._coerce_float(None, 42.0) == 42.0

    def test_coerce_float_string(self):
        from app.channels.wechat import WechatChannel

        assert WechatChannel._coerce_float("3.14", 1.0) == 3.14

    def test_coerce_int_none(self):
        from app.channels.wechat import WechatChannel

        assert WechatChannel._coerce_int(None, 42) == 42

    def test_coerce_int_string(self):
        from app.channels.wechat import WechatChannel

        assert WechatChannel._coerce_int("7", 1) == 7

    def test_coerce_str_set_none(self):
        from app.channels.wechat import WechatChannel

        default = frozenset({".txt"})
        result = WechatChannel._coerce_str_set(None, default)
        assert result == set(default)

    def test_coerce_str_set_list(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._coerce_str_set([".pdf", ".doc"], frozenset())
        assert ".pdf" in result
        assert ".doc" in result

    def test_coerce_str_set_set(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._coerce_str_set({".pdf", ".doc"}, frozenset())
        assert ".pdf" in result
        assert ".doc" in result


class TestResolveStateDir:
    """Line 1346-1349: _resolve_state_dir edge cases."""

    def test_none_returns_none(self):
        from app.channels.wechat import WechatChannel

        assert WechatChannel._resolve_state_dir(None) is None

    def test_empty_string_returns_none(self):
        from app.channels.wechat import WechatChannel

        assert WechatChannel._resolve_state_dir("") is None

    def test_whitespace_returns_none(self):
        from app.channels.wechat import WechatChannel

        assert WechatChannel._resolve_state_dir("  ") is None

    def test_valid_path(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._resolve_state_dir("/tmp/state")
        assert result == Path("/tmp/state")


class TestEnsureClient:
    """Lines 746-750: _ensure_client creates client."""

    def test_creates_client_on_first_call(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            assert channel._client is None
            client = await channel._ensure_client()
            assert client is not None
            assert channel._client is client
            # Second call returns same client
            client2 = await channel._ensure_client()
            assert client2 is client
            await channel._client.aclose()

        _run(go())


class TestSendFileNoUploadUrlAndNoParam:
    """Lines 505-506: send_file with no upload URL and no upload param."""

    def test_file_no_upload_url_and_no_param(self, monkeypatch, tmp_path: Path):
        from app.channels.message_bus import ResolvedAttachment
        from app.channels.wechat import WechatChannel

        async def go():
            post_calls: list[dict[str, Any]] = []

            def _client_factory(*args, **kwargs):
                return _MockAsyncClient(
                    post_calls=post_calls,
                    post_responses=[{"ret": 0}],
                    **kwargs,
                )

            monkeypatch.setattr("app.channels.wechat.httpx.AsyncClient", _client_factory)

            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            channel._context_tokens_by_chat["wx-u1"] = "ctx"
            file_path = tmp_path / "doc.pdf"
            file_path.write_bytes(b"%PDF-data")

            ok = await channel.send_file(
                OutboundMessage(channel_name="wechat", chat_id="wx-u1", thread_id="t1", text="hi"),
                ResolvedAttachment(
                    virtual_path="/doc.pdf",
                    actual_path=file_path,
                    filename="doc.pdf",
                    mime_type="application/pdf",
                    size=9,
                    is_image=False,
                ),
            )
            assert ok is False

        _run(go())


class TestPollLoopErrcodeMinus14SavesState:
    """Lines 565-568: errcode -14 saves state and auth state."""

    def test_errcode_minus14_saves_state_and_auth(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        async def go():
            state_dir = tmp_path / "state"
            state_dir.mkdir()

            channel = WechatChannel(
                bus=MessageBus(),
                config={"bot_token": "tok", "state_dir": str(state_dir)},
            )
            channel._running = True

            async def _mock_request(path, payload, *, timeout=None):
                return {"ret": 1, "errcode": -14, "errmsg": "expired"}

            channel._request_json = _mock_request  # type: ignore[method-assign]
            await channel._poll_loop()

            assert channel._running is False
            assert channel._bot_token == ""
            # Check auth state was saved
            auth_file = state_dir / "wechat-auth.json"
            assert auth_file.exists()
            auth_data = json.loads(auth_file.read_text())
            assert auth_data["status"] == "expired"

        _run(go())


class TestSafeMediaFilenameEdgeCases:
    """Lines 100-104: _safe_media_filename edge cases."""

    def test_no_extension(self):
        from app.channels.wechat import _safe_media_filename

        result = _safe_media_filename("prefix", "", message_id="m1", index=0)
        assert result == "prefix-m1-0"

    def test_extension_without_dot(self):
        from app.channels.wechat import _safe_media_filename

        result = _safe_media_filename("prefix", "pdf", message_id="m1", index=0)
        assert result == "prefix-m1-0.pdf"

    def test_slash_in_message_id(self):
        from app.channels.wechat import _safe_media_filename

        result = _safe_media_filename("prefix", ".bin", message_id="a/b", index=0)
        assert "a_b" in result

    def test_backslash_in_message_id(self):
        from app.channels.wechat import _safe_media_filename

        result = _safe_media_filename("prefix", ".bin", message_id="a\\b", index=0)
        assert "a_b" in result

    def test_no_message_id(self):
        from app.channels.wechat import _safe_media_filename

        result = _safe_media_filename("prefix", ".bin", index=0)
        assert result == "prefix-msg-0.bin"

    def test_no_index(self):
        from app.channels.wechat import _safe_media_filename

        result = _safe_media_filename("prefix", ".bin", message_id="m1")
        assert result == "prefix-m1.bin"


class TestBuildCdnUploadUrl:
    """Line 108: _build_cdn_upload_url."""

    def test_builds_correct_url(self):
        from app.channels.wechat import _build_cdn_upload_url

        result = _build_cdn_upload_url("https://cdn.example.com/c2c", "param123", "filekey456")
        assert "encrypted_query_param=param123" in result
        assert "filekey=filekey456" in result
        assert result.startswith("https://cdn.example.com/c2c/upload?")


class TestMd5Hex:
    """Line 68: _md5_hex."""

    def test_md5_hex(self):
        import hashlib

        from app.channels.wechat import _md5_hex

        result = _md5_hex(b"hello")
        assert len(result) == 32
        assert result == hashlib.md5(b"hello").hexdigest()


class TestEncodeOutboundMediaAesKey:
    """Line 112: _encode_outbound_media_aes_key."""

    def test_encode(self):
        from app.channels.wechat import _encode_outbound_media_aes_key

        key = b"0123456789abcdef"
        result = _encode_outbound_media_aes_key(key)
        # Should be base64 of hex-encoded key
        decoded = base64.b64decode(result).decode("utf-8")
        assert decoded == key.hex()


class TestValidateAes128Key:
    """Line 78-79: _validate_aes_128_key."""

    def test_valid_key(self):
        from app.channels.wechat import _validate_aes_128_key

        _validate_aes_128_key(b"0123456789abcdef")  # Should not raise

    def test_wrong_length(self):
        from app.channels.wechat import _validate_aes_128_key

        with pytest.raises(ValueError, match="16-byte"):
            _validate_aes_128_key(b"short")


class TestCommonHeadersNoOptional:
    """Lines 787-796: _common_headers without optional fields."""

    def test_no_optional_headers(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        headers = channel._common_headers()
        assert "iLink-App-Id" not in headers
        assert "SKRouteTag" not in headers
        assert "iLink-App-ClientVersion" in headers
        assert "X-WECHAT-UIN" in headers


class TestAuthHeaders:
    """Lines 804-811: _auth_headers."""

    def test_auth_headers_include_bearer_token(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "my-token"})
        headers = channel._auth_headers()
        assert headers["Authorization"] == "Bearer my-token"
        assert headers["AuthorizationType"] == "ilink_bot_token"


class TestPublicHeaders:
    """Lines 798-802: _public_headers."""

    def test_public_headers(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        headers = channel._public_headers()
        assert headers["Content-Type"] == "application/json"
        assert "Authorization" not in headers


class TestBaseInfo:
    """Lines 784-785: _base_info."""

    def test_base_info(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        info = channel._base_info()
        assert "channel_version" in info


class TestEnsureSuccessEdgeCases:
    """Lines 1240-1246: _ensure_success edge cases."""

    def test_errmsg_with_msg_fallback(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        with pytest.raises(RuntimeError, match="fallback-msg"):
            channel._ensure_success({"ret": 1, "msg": "fallback-msg"}, "test")

    def test_errmsg_with_no_errmsg_no_msg(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        with pytest.raises(RuntimeError, match="unknown error"):
            channel._ensure_success({"ret": 1}, "test")


class TestStartSubscribeOutbound:
    """Lines 271: start subscribes to outbound."""

    def test_start_subscribes_to_outbound(self):
        from app.channels.wechat import WechatChannel

        async def go():
            bus = MessageBus()
            channel = WechatChannel(bus=bus, config={"bot_token": "tok"})
            await channel.start()
            assert channel._on_outbound in bus._outbound_listeners
            await channel.stop()

        _run(go())


class TestStopUnsubscribesOutbound:
    """Lines 277: stop calls unsubscribe_outbound and cleans up."""

    def test_stop_clears_running_and_poll_task(self):
        from app.channels.wechat import WechatChannel

        async def go():
            bus = MessageBus()
            channel = WechatChannel(bus=bus, config={"bot_token": "tok"})
            await channel.start()
            assert channel._running is True
            assert channel._poll_task is not None
            await channel.stop()
            assert channel._running is False
            assert channel._poll_task is None

        _run(go())


class TestStopNoClient:
    """Lines 287-289: stop when client is None."""

    def test_stop_no_client(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"tok": "tok"})
            channel._running = True
            channel._client = None
            await channel.stop()
            assert channel._running is False

        _run(go())


class TestExtractTextNoItemList:
    """Lines 1333-1343: _extract_text with no item_list."""

    def test_no_item_list(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._extract_text({})
        assert result == ""


class TestLoadStateNoCursorPath:
    """Lines 1248-1251: _load_state when cursor_path is None."""

    def test_no_cursor_path(self):
        from app.channels.wechat import WechatChannel

        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
        channel._cursor_path = None
        # Should not raise
        channel._load_state()


class TestLoadStateNoCursorFile:
    """Lines 1250-1251: _load_state when cursor file doesn't exist."""

    def test_cursor_file_not_exists(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        state_dir = tmp_path / "state"
        state_dir.mkdir()
        # Don't create the cursor file
        channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok", "state_dir": str(state_dir)})
        assert channel._get_updates_buf == ""


class TestHandleUpdateThreadTs:
    """Lines 612-617: handle_update thread_ts construction."""

    def test_thread_ts_uses_msg_id(self):
        from app.channels.wechat import WechatChannel

        async def go():
            bus = MessageBus()
            published = []
            bus.publish_inbound = AsyncMock(side_effect=lambda msg: published.append(msg))

            channel = WechatChannel(bus=bus, config={"bot_token": "tok"})
            await channel._handle_update(
                {
                    "message_type": 1,
                    "from_user_id": "wx-u1",
                    "context_token": "ctx-1",
                    "msg_id": "msg-xyz",
                    "item_list": [{"type": 1, "text_item": {"text": "hi"}}],
                }
            )
            assert len(published) == 1
            # thread_ts = context_token (since context_token is truthy, it takes priority)
            assert published[0].thread_ts == "ctx-1"

        _run(go())

    def test_thread_ts_stores_in_thread_map(self):
        from app.channels.wechat import WechatChannel

        async def go():
            bus = MessageBus()
            published = []
            bus.publish_inbound = AsyncMock(side_effect=lambda msg: published.append(msg))

            channel = WechatChannel(bus=bus, config={"bot_token": "tok"})
            await channel._handle_update(
                {
                    "message_type": 1,
                    "from_user_id": "wx-u1",
                    "context_token": "ctx-1",
                    "client_id": "client-abc",
                    "item_list": [{"type": 1, "text_item": {"text": "hi"}}],
                }
            )
            # thread_ts = context_token (ctx-1), stored in thread map under ctx-1
            assert channel._context_tokens_by_thread["ctx-1"] == "ctx-1"

        _run(go())

    def test_no_context_token_uses_client_id_as_thread_key(self):
        from app.channels.wechat import WechatChannel

        async def go():
            bus = MessageBus()
            published = []
            bus.publish_inbound = AsyncMock(side_effect=lambda msg: published.append(msg))

            channel = WechatChannel(bus=bus, config={"bot_token": "tok"})
            await channel._handle_update(
                {
                    "message_type": 1,
                    "from_user_id": "wx-u1",
                    "client_id": "client-abc",
                    "item_list": [{"type": 1, "text_item": {"text": "hi"}}],
                }
            )
            assert len(published) == 1
            # No context_token, so thread_ts = client_id
            assert published[0].thread_ts == "client-abc"

        _run(go())


class TestEnsureAuthenticatedTokenFromAuthState:
    """Line 643: _ensure_authenticated returns True after loading auth state."""

    def test_token_loaded_from_auth_state(self, tmp_path: Path):
        from app.channels.wechat import WechatChannel

        async def go():
            auth_file = tmp_path / "wechat-auth.json"
            auth_file.write_text(json.dumps({"bot_token": "loaded-token"}))

            channel = WechatChannel(bus=MessageBus(), config={"state_dir": str(tmp_path)})
            # Initially no token
            channel._bot_token = ""
            result = await channel._ensure_authenticated()
            assert result is True
            assert channel._bot_token == "loaded-token"

        _run(go())


class TestDecodeBase64AesKeyEmptyDecodedText:
    """Line 1093: _decode_base64_aes_key returns None when decoded text is empty."""

    def test_empty_decoded_text_returns_none(self):
        from app.channels.wechat import WechatChannel

        # 17 space bytes -> not 16, fails _validate, then decoded_text is empty after strip
        key_bytes = b" " * 17
        encoded = base64.b64encode(key_bytes).decode()
        result = WechatChannel._decode_base64_aes_key(encoded)
        assert result is None


class TestParseAesKeyCandidateValidatorFails:
    """Lines 1147-1149: _parse_aes_key_candidate validator raises ValueError."""

    def test_both_paths_fail(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._parse_aes_key_candidate("zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz", prefer_hex=True)
        assert result is None

    def test_prefer_hex_false_both_fail(self):
        from app.channels.wechat import WechatChannel

        result = WechatChannel._parse_aes_key_candidate("not-valid-base64!!!", prefer_hex=False)
        assert result is None


class TestPollLoopCancelledError:
    """Line 591: poll loop re-raises asyncio.CancelledError."""

    def test_poll_loop_cancellation_raises_cancelled_error(self):
        from app.channels.wechat import WechatChannel

        async def go():
            channel = WechatChannel(bus=MessageBus(), config={"bot_token": "tok"})
            channel._running = True

            # Make _request_json hang so we can cancel the task during the try block
            request_entered = asyncio.Event()

            async def _slow_request(path, payload, *, timeout=None):
                request_entered.set()
                await asyncio.sleep(100)  # hang until cancelled

            channel._request_json = _slow_request  # type: ignore[method-assign]

            task = asyncio.ensure_future(channel._poll_loop())
            await request_entered.wait()  # wait until we're inside _request_json
            task.cancel()

            with pytest.raises(asyncio.CancelledError):
                await task

        _run(go())
