"""Channel lifecycle contract tests (issue #61).

Contract seam: the ChannelService start/stop/``is_running`` state machine plus
injected provider-thread death. Each test pins one remediation from the
code-review findings 03-H1/H2/M3/M4/M6/M5 (channel availability family):

- Telegram/DingTalk provider-thread death must converge ``is_running`` to
  False (thread-backed semantics) and leave the channel rebuildable through
  ``ChannelService.ensure_channel_ready``.
- Feishu ``stop()`` must disconnect the lark WS client, let its thread exit,
  and stop the old instance from processing further provider events.
- Slack ``connect()`` failures must be observable (the future is retained and
  its exception surfaces) instead of reporting a permanently healthy channel.
- Discord repository calls (identity attach, ``/connect`` bind) must run on
  the Gateway main loop, never on the Discord client loop (Postgres/asyncpg
  pools are bound to the loop that created them).
- Channels without a registered inbound file reader must not have their URL
  attachments fetched from the gateway host (whitelist default).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.message_bus import InboundMessage, MessageBus

# Threads must finish within this budget in every wait loop below; a miss is a
# contract failure, not a slow machine.
_THREAD_DEATH_TIMEOUT_SECONDS = 5.0


async def _wait_until(predicate, *, timeout: float = _THREAD_DEATH_TIMEOUT_SECONDS) -> bool:
    """Poll *predicate* on the test loop until it holds or the deadline passes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()


def _patched_telegram_modules(initialize) -> tuple[MagicMock, MagicMock]:
    """Fake ``telegram``/``telegram.ext`` whose ApplicationBuilder builds *app*.

    start() calls ``ApplicationBuilder().token(bot_token).build()``, so the
    class call itself must return the builder (``ApplicationBuilder
    .return_value``), then ``token`` chains into ``build`` -> app.
    """
    app = MagicMock()
    app.initialize = initialize
    builder = MagicMock()
    builder.token.return_value = builder
    builder.build.return_value = app
    ext = MagicMock()
    ext.ApplicationBuilder.return_value = builder
    telegram_mod = MagicMock()
    telegram_mod.ext = ext
    return telegram_mod, ext


# ---------------------------------------------------------------------------
# 03-H2: Telegram polling-thread death converges is_running (and rebuilds)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_telegram_polling_thread_death_converges_is_running():
    from app.channels.telegram import TelegramChannel

    async def _initialize() -> None:
        # Bot API calls happen on the polling thread; keep the thread alive
        # briefly so start()-time readiness checks observe a live worker
        # before the injected death.
        await asyncio.sleep(0.2)
        raise RuntimeError("401: unauthorized token")

    telegram_mod, ext = _patched_telegram_modules(_initialize)
    channel = TelegramChannel(MessageBus(), {"bot_token": "test-token"})

    with patch.dict("sys.modules", {"telegram": telegram_mod, "telegram.ext": ext}):
        await channel.start()
        assert channel._running is True
        thread = channel._thread
        assert thread is not None

        assert await _wait_until(lambda: not thread.is_alive()), "polling thread should die from the injected failure"

        # The contract: a dead polling thread must not keep reporting healthy.
        assert channel.is_running is False

        # stop() on the dead instance must complete so the service can
        # discard it and rebuild (no wedged shutdown).
        await channel.stop()
        assert channel._thread is None


@pytest.mark.asyncio
async def test_channel_service_rebuilds_channel_after_polling_thread_death():
    from app.channels.service import ChannelService

    async def _initialize() -> None:
        await asyncio.sleep(0.2)
        raise RuntimeError("401: unauthorized token")

    telegram_mod, ext = _patched_telegram_modules(_initialize)
    service = ChannelService({"telegram": {"enabled": True, "bot_token": "test-token"}})
    service._running = True

    with patch.dict("sys.modules", {"telegram": telegram_mod, "telegram.ext": ext}):
        assert await service.ensure_channel_ready("telegram") is True
        first = service._channels["telegram"]
        assert first is not None
        assert first.is_running is True

        assert await _wait_until(lambda: not first.is_running), "dead polling thread must converge is_running to False"

        # The readiness loop observes the converged state and rebuilds.
        assert await service.ensure_channel_ready("telegram") is True
        second = service._channels["telegram"]
        assert second is not first, "ChannelService must rebuild the channel after thread death"

        await second.stop()


# ---------------------------------------------------------------------------
# 03-M6: DingTalk stream-thread death converges is_running
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dingtalk_stream_thread_death_converges_is_running():
    from app.channels.dingtalk import DingTalkChannel

    def _slow_death() -> None:
        time.sleep(0.2)
        raise RuntimeError("stream auth failed")

    stream_mod = MagicMock()
    stream_mod.DingTalkStreamClient.return_value.start_forever.side_effect = _slow_death

    channel = DingTalkChannel(MessageBus(), {"client_id": "id", "client_secret": "secret"})

    with patch.dict("sys.modules", {"dingtalk_stream": stream_mod}):
        await channel.start()
        assert channel._running is True
        thread = channel._thread
        assert thread is not None

        assert await _wait_until(lambda: not thread.is_alive()), "stream thread should die from the injected failure"

        # Exception path clears the flag and is_running reflects thread death.
        assert channel._running is False
        assert channel.is_running is False

        await channel.stop()
        assert channel._thread is None


# ---------------------------------------------------------------------------
# 03-M3: Feishu stop() disconnects the WS and the old instance goes deaf
# ---------------------------------------------------------------------------


class _FakeWsThread:
    """Stand-in for the lark WS thread: a loop that runs until stopped."""

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self.loop = loop
        asyncio.set_event_loop(loop)
        self.ready.set()
        loop.run_forever()

    def start(self) -> None:
        self.thread.start()
        assert self.ready.wait(timeout=_THREAD_DEATH_TIMEOUT_SECONDS)


def _connect_code_event() -> SimpleNamespace:
    return SimpleNamespace(
        event=SimpleNamespace(
            message=SimpleNamespace(
                chat_id="oc_1",
                message_id="om_1",
                content=json.dumps({"text": "/connect bind-code"}),
                root_id=None,
                chat_type="p2p",
                parent_id=None,
                thread_id=None,
            ),
            sender=SimpleNamespace(sender_id=SimpleNamespace(open_id="ou_1")),
        )
    )


@pytest.mark.asyncio
async def test_feishu_stop_disconnects_ws_and_old_instance_stops_processing():
    from app.channels.feishu import FeishuChannel

    channel = FeishuChannel(MessageBus(), {"app_id": "id", "app_secret": "secret"})
    channel._running = True

    ws_thread = _FakeWsThread()
    ws_thread.start()

    disconnect_done = threading.Event()

    async def _fake_disconnect() -> None:
        disconnect_done.set()

    ws_client = MagicMock()
    ws_client._disconnect = _fake_disconnect
    channel._ws_client = ws_client
    channel._ws_loop = ws_thread.loop
    channel._thread = ws_thread.thread

    # The old instance must not hand any post-stop provider event to the bus:
    # a submit-capable main loop plus a repo make the pre-fix instance visibly
    # process a /connect event after stop().
    main_loop = MagicMock()
    main_loop.is_running.return_value = True
    channel._main_loop = main_loop
    submit = MagicMock(return_value=True)
    channel._submit_threadsafe_coroutine = submit
    channel._connection_repo = MagicMock()

    await channel.stop()

    assert disconnect_done.is_set(), "stop() must disconnect the lark WS client (old connection must not outlive restart)"
    assert not ws_thread.thread.is_alive(), "the WS loop must be stopped so its thread can exit (no zombie duplicate connection)"
    assert channel._stopped is True
    assert channel._ws_client is None

    channel._on_message(_connect_code_event())
    assert submit.call_count == 0, "old instance must not process provider events after stop()"


# ---------------------------------------------------------------------------
# 03-M4: Slack connect failure is observable (no permanently healthy channel)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slack_connect_failure_is_visible_and_clears_running(caplog):
    from app.channels.slack import SlackChannel

    channel = SlackChannel(MessageBus(), {"bot_token": "xoxb-test", "app_token": "xapp-broken"})

    socket_client = MagicMock()
    socket_module = MagicMock()
    socket_module.SocketModeClient.return_value = socket_client
    web_module = MagicMock()
    web_module.WebClient.return_value = MagicMock()
    response_module = MagicMock()

    failed_connect = concurrent.futures.Future()
    failed_connect.set_exception(RuntimeError("invalid app token: xapp-broken"))

    mock_loop = MagicMock()
    mock_loop.run_in_executor.return_value = failed_connect

    with (
        patch.dict(
            "sys.modules",
            {
                "slack_sdk": web_module,
                "slack_sdk.socket_mode": socket_module,
                "slack_sdk.socket_mode.response": response_module,
            },
        ),
        patch("asyncio.get_event_loop", return_value=mock_loop),
    ):
        await channel.start()

    # The connect future is retained, not dropped, and its failure is logged.
    assert channel._connect_future is failed_connect
    mock_loop.run_in_executor.assert_called_once()
    assert "Socket Mode connection failed" in caplog.text

    # Contract: a failed connection must not keep reporting a healthy channel.
    assert channel.is_running is False

    await channel.stop()


# ---------------------------------------------------------------------------
# 03-H1: Discord repository calls run on the Gateway main loop
# ---------------------------------------------------------------------------


def _start_secondary_loop() -> tuple[_FakeWsThread, asyncio.AbstractEventLoop]:
    holder = _FakeWsThread()
    holder.start()
    assert holder.loop is not None
    return holder, holder.loop


class _LoopBoundRepo:
    """Repo stub that records which loop each call ran on.

    The production failure mode (Postgres/asyncpg) is a loop-affinity
    exception when the pool is used from a foreign loop; recording the loop
    lets the test assert the Gateway-main-loop discipline directly.
    """

    def __init__(self) -> None:
        self.loops_used: list[tuple[str, asyncio.AbstractEventLoop]] = []

    async def find_connection_by_external_identity(self, **kwargs):
        self.loops_used.append(("find_connection", asyncio.get_running_loop()))
        return None

    async def consume_oauth_state(self, *, provider, state):
        self.loops_used.append(("consume_state", asyncio.get_running_loop()))
        return {"owner_user_id": "deerflow-user-1"}

    async def upsert_connection(self, **kwargs):
        self.loops_used.append(("upsert_connection", asyncio.get_running_loop()))
        return {"id": "conn-1"}


def _make_discord_module(ch):
    mock_discord = MagicMock()
    mock_discord.Thread = type("Thread", (), {})

    class MockHTTPException(Exception):
        def __init__(self, code=0):
            super().__init__()
            self.code = code

    mock_discord.errors.HTTPException = MockHTTPException
    ch._discord_module = mock_discord


async def _drain_discord_loop_tasks(holder: _FakeWsThread, ch) -> None:
    """Cancel ephemeral typing/reaction tasks before the test loop stops."""
    if holder.loop is not None and holder.loop.is_running():
        await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(ch._cancel_ephemeral_tasks(), holder.loop))
        holder.loop.call_soon_threadsafe(holder.loop.stop)


@pytest.mark.asyncio
async def test_discord_inbound_identity_attach_runs_on_main_loop():
    from app.channels.discord import DiscordChannel

    main_loop = asyncio.get_running_loop()
    bus = MessageBus()
    channel = DiscordChannel(bus, {"bot_token": "test-token", "mention_only": False, "thread_mode": False})
    channel._running = True
    channel._main_loop = main_loop
    channel._connection_repo = _LoopBoundRepo()
    _make_discord_module(channel)
    client = MagicMock()
    client.user.id = "bot123"
    client.user.mention = "<@bot123>"
    channel._client = client

    holder, discord_loop = _start_secondary_loop()
    try:
        message = MagicMock()
        message.content = "hello bot"
        message.id = "msg_1"
        message.author.id = "987"
        message.author.bot = False
        message.author.display_name = "Alice"
        message.channel.id = "200001"
        message.channel.type = MagicMock()
        message.channel.parent_id = None
        message.guild = None
        message.add_reaction = AsyncMock()

        await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(channel._on_message(message), discord_loop))

        # The message must still be delivered (identity attach must not fail
        # or drop the message under Postgres + channel_connections).
        inbound = await asyncio.wait_for(bus.get_inbound(), timeout=_THREAD_DEATH_TIMEOUT_SECONDS)
        assert inbound.text == "hello bot"
        assert inbound.chat_id == "200001"
    finally:
        await _drain_discord_loop_tasks(holder, channel)
        holder.thread.join(timeout=_THREAD_DEATH_TIMEOUT_SECONDS)

    repo = channel._connection_repo
    assert repo.loops_used, "identity attach should query the connection repo when configured"
    wrong = [entry for entry in repo.loops_used if entry[1] is not main_loop]
    assert not wrong, f"repo calls must run on the Gateway main loop, saw foreign loops: {wrong}"


@pytest.mark.asyncio
async def test_discord_connect_bind_runs_repo_on_main_loop_and_reply_on_discord_loop():
    from app.channels.discord import DiscordChannel

    main_loop = asyncio.get_running_loop()
    channel = DiscordChannel(MessageBus(), {"bot_token": "test-token"})
    channel._running = True
    channel._main_loop = main_loop
    channel._connection_repo = _LoopBoundRepo()

    holder, discord_loop = _start_secondary_loop()
    try:
        message = MagicMock()
        message.id = "msg_1"
        message.author.id = "987"
        message.author.display_name = "Alice"
        message.guild.id = "123"
        message.guild.name = "Deer Guild"
        message.channel.id = "456"
        message.channel.send = AsyncMock()

        handled = await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(channel._bind_connection_from_connect_code(message, "bind-code"), discord_loop))
        assert handled is True, "a scheduled bind flow owns the /connect message"

        # The bind coroutine runs on the main loop; wait for the upsert and
        # the Discord-loop reply to complete before asserting.
        def _bind_completed() -> bool:
            repo = channel._connection_repo
            return any(kind == "upsert_connection" for kind, _ in repo.loops_used) and message.channel.send.await_count >= 1

        assert await _wait_until(_bind_completed), "bind flow should upsert the connection and reply"
    finally:
        await _drain_discord_loop_tasks(holder, channel)
        holder.thread.join(timeout=_THREAD_DEATH_TIMEOUT_SECONDS)

    repo = channel._connection_repo
    kinds = [kind for kind, _ in repo.loops_used]
    assert "consume_state" in kinds and "upsert_connection" in kinds
    wrong = [entry for entry in repo.loops_used if entry[1] is not main_loop]
    assert not wrong, f"bind repo calls must run on the Gateway main loop, saw foreign loops: {wrong}"
    # The connection reply goes back over the Discord client loop.
    message.channel.send.assert_awaited()


# ---------------------------------------------------------------------------
# 03-M5: default inbound file reader is whitelist-only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unregistered_channel_does_not_fetch_url_attachments(tmp_path, monkeypatch, caplog):
    from app.channels import manager

    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()

    fetched_urls: list[str] = []

    async def _spy_default_reader(file_info, client):
        fetched_urls.append(str(file_info.get("url")))
        return b"fetched-from-attacker"

    monkeypatch.setattr(manager, "_read_http_inbound_file", _spy_default_reader)

    msg = InboundMessage(
        channel_name="rogue-channel",  # not in INBOUND_FILE_READERS
        chat_id="c1",
        user_id="u1",
        text="see attachment",
        files=[{"filename": "steal.txt", "url": "http://169.254.169.254/latest/meta-data"}],
    )

    created = await manager._ingest_inbound_files("t1", msg)

    assert created == []
    assert fetched_urls == [], "the generic HTTP reader must not run for channels without a registered reader"
    assert "no inbound file reader registered" in caplog.text


@pytest.mark.asyncio
async def test_registered_reader_still_ingests_files(tmp_path, monkeypatch):
    """Positive control: the whitelist only affects unregistered channels."""
    from app.channels import manager

    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()

    async def _reader(file_info, client):
        return b"platform media"

    monkeypatch.setitem(manager.INBOUND_FILE_READERS, "gated-channel", _reader)

    msg = InboundMessage(
        channel_name="gated-channel",
        chat_id="c1",
        user_id="u1",
        text="see attachment",
        files=[{"filename": "report.pdf", "url": "https://media.example/report.pdf"}],
    )

    with patch("deerflow.uploads.manager.ensure_uploads_dir", return_value=uploads_dir):
        created = await manager._ingest_inbound_files("t1", msg)

    assert len(created) == 1
    assert created[0]["filename"] == "report.pdf"
    assert (uploads_dir / "report.pdf").read_bytes() == b"platform media"


@pytest.mark.asyncio
async def test_unregistered_channel_still_ingests_inline_content(tmp_path, monkeypatch):
    """Inline message content does not need a reader (Telegram-style files)."""
    from app.channels import manager
    from app.channels.message_bus import INBOUND_FILE_CONTENT_KEY

    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()

    msg = InboundMessage(
        channel_name="inline-channel",  # not in INBOUND_FILE_READERS
        chat_id="c1",
        user_id="u1",
        text="see attachment",
        files=[{INBOUND_FILE_CONTENT_KEY: b"inline-bytes", "filename": "note.txt"}],
    )

    with patch("deerflow.uploads.manager.ensure_uploads_dir", return_value=uploads_dir):
        created = await manager._ingest_inbound_files("t1", msg)

    assert len(created) == 1
    assert (uploads_dir / "note.txt").read_bytes() == b"inline-bytes"
