# 上游 PR 候选:渠道生命周期状态收敛与事件循环亲和(03-H1/H2/M3/M4/M6+M5,票 61)

- 状态:候选(待下轮收敛轨随 P003/P011/P014/P032 及 memory-proxy 候选一并 reassess;提交流程见
  `docs/offline-product-line-governance-plan.md` §修复轨/补丁卫生)。
- 目标上游仓库:`bytedance/deer-flow`(分支 `main`)。
- 来源:发现 03-H1/H2/M3/M4/M6/M5(`dev-log/code-review-2026-10-07/03-backend-channels-services.md`,
  适配器为上游起源文件,缺陷模式上游同样存在);本地修复见票 #61(commit 记录于
  `UPSTREAM_PATCH_LEDGER.md` 巡检记录 2026-10-11 行)。
- 上游基线:`v2.1.0`(`345f08be0`)。已逐文件核对上游同病:
  `slack.py:145` fire-and-forget connect、`feishu.py` stop() 无 disconnect、
  `telegram.py`/`dingtalk.py` 线程死亡不清 `_running` 且未覆写 `is_running`、
  `discord.py:578` 在 Discord 私有循环上直 await 仓储、
  `manager.py:1107` 默认 reader 无白名单。以下 diff 草稿按上游文件形态给出。

## PR 草稿

- **标题**: `fix(channels): converge lifecycle state after provider-thread death and keep repo calls on the gateway loop`
- **动机**: 五个同族缺陷让渠道在故障后"永久假活":Telegram/DingTalk 轮询线程死亡后
  `_running` 不清、`is_running` 只查标志,`ChannelService.ensure_channel_ready` 因此永不重启;
  Slack `connect()` 以无人 await 的 executor Future 启动,连接失败被静默吞掉;飞书 `stop()`
  不断开 lark WS(SDK receive loop 默认无限自动重连),旧连接存活至进程退出并重复投递事件;
  Discord 在客户端私有事件循环上直 await SQLAlchemy 异步仓储(asyncpg 池绑主循环,
  Postgres + channel_connections 部署下每条入站消息失败);manager 的默认 inbound 文件
  reader 对未注册渠道的任意 `url` 无限制抓取(SSRF 面)。
- **修复**(三个通用模式):
  1. **线程承载 SDK 循环的渠道,`is_running` 语义 = 线程存活 + 异常路径清 `_running`**
     (Telegram/DingTalk,与既有 Feishu/Discord 覆写对齐);
  2. **仓储调用派回网关主循环**:Discord 的身份附加并入 `_publish_reserved`(有 repo 时
     以 attach+commit 协程提交主循环,对齐 Slack 的 `_publish_inbound_with_connection`),
     `/connect` 绑定比照 Telegram 的 `_bind_connection_from_start_token` 提交主循环、
     回复发回 Discord 循环;
  3. **失败必须可见**:Slack 保存 connect Future 并加 done callback(清 `_running` + 记错);
     飞书 stop() 断开 WS 后停其循环再 join,并置 `_stopped` 屏蔽旧实例 `_on_message`;
     manager 无注册 reader 的渠道丢弃 URL 附件并告警(通用 reader 仅作已注册渠道的 opt-in 助手)。
- **测试**: 每个模式一条合同测试(线程死亡注入→`is_running` 收敛且可重建;Discord loop id
  断言仓储调用发生在主循环;Slack 连接失败后 `is_running` 为 False;飞书 stop 后旧连接
  断开、旧实例不处理事件;未注册渠道 URL 不触发抓取)。

## diff 草稿(通用模式 1,对上游 `telegram.py`/`dingtalk.py` 同型)

```diff
--- a/backend/app/channels/telegram.py
+++ b/backend/app/channels/telegram.py
@@ class TelegramChannel(Channel):
     @property
     def supports_streaming(self) -> bool:
         return True
+
+    @property
+    def is_running(self) -> bool:
+        """Running means the polling thread is still alive, not just started."""
+        if not self._running:
+            return False
+        return self._thread is not None and self._thread.is_alive()
 
     async def start(self) -> None:
@@     def _run_polling(self) -> None:
         except Exception:
             if self._running:
                 logger.exception("Telegram polling error")
+            # The polling thread is gone: let readiness rebuild the channel
+            # instead of reporting fake-alive forever.
+            self._running = False
         finally:
```

(`dingtalk.py` 的 `_run_stream` 同型:`is_running` 覆写 + except 分支清 `_running`。)

## diff 草稿(通用模式 2,对上游 `discord.py`)

```diff
--- a/backend/app/channels/discord.py
+++ b/backend/app/channels/discord.py
@@     def _publish_reserved(self, inbound, reservation) -> bool:
-        """Transfer an already-reserved message to the Gateway loop."""
+        """Transfer an already-reserved message to the Gateway loop.
+
+        With a connection repo, identity attachment is a repository call on
+        the engine bound to the Gateway main loop; submit attach+commit as
+        one main-loop coroutine (mirrors Slack) instead of awaiting the repo
+        on this client's private loop.
+        """
         if self._main_loop and self._main_loop.is_running():
+            if self._connection_repo is not None:
+                scheduled = self._submit_threadsafe_coroutine(
+                    self._publish_inbound_with_identity(inbound, reservation=reservation),
+                    self._main_loop,
+                    name="publish_inbound",
+                    msg_id=inbound.metadata.get("message_id"),
+                    reservation=reservation,
+                )
+                if not scheduled:
+                    logger.info("[Discord] main loop stopped before reserved inbound could be scheduled")
+                return scheduled
             try:
                 self._main_loop.call_soon_threadsafe(self._commit_reserved_inbound, reservation, inbound)
                 return True
@@
         reservation.release()
         return False
+
+    async def _publish_inbound_with_identity(self, inbound, *, reservation) -> None:
+        try:
+            inbound = await self._attach_connection_identity(inbound, guild_id=inbound.metadata.get("guild_id"))
+            self._commit_reserved_inbound(reservation, inbound)
+        finally:
+            reservation.release()
```

(`_handle_admitted_message` 两处删除内联 `await self._attach_connection_identity(...)`;
`_bind_connection_from_connect_code` 比照 telegram `_bind_connection_from_start_token`
提交主循环、回复经 `_run_on_discord_loop` 发回。)

## diff 草稿(通用模式 3,要点)

- `slack.py`: `self._connect_future = asyncio.get_event_loop().run_in_executor(None, self._socket_client.connect)`;
  `self._connect_future.add_done_callback(self._on_socket_connect_done)`;callback 内
  `future.exception()` 非 None 时 `logger.error(...)` 并 `self._running = False`。
- `feishu.py`: `_run_ws` 发布 `self._ws_client`/`self._ws_loop`;`stop()` 置 `_stopped`
  屏蔽 `_on_message` → `run_coroutine_threadsafe(ws_client._disconnect(), ws_loop)`
  (有界等待)→ `ws_loop.call_soon_threadsafe(ws_loop.stop)`(阻断 SDK 无限自动重连并让
  线程退出)→ join;`_on_message` 顶部 `if self._stopped: return`。
- `manager.py`: `INBOUND_FILE_READERS.get(msg.channel_name)` 无默认;无 reader 的渠道对
  每个非内联文件记录 warning 并丢弃,`_read_http_inbound_file` 仅作为已注册渠道(Wecom)
  的 opt-in 助手。

## 本地验证证据(2026-10-11,票 #61)

- 先红后绿:`backend/tests/unit/channels/test_channel_lifecycle_contracts.py` 新增 10 条
  合同测试,实现前 8/8 目标用例失败(含 1 条阳性对照先绿),实现后全绿且连跑 3 轮稳定;
- 回归:`backend/tests/unit/channels/` 1480 passed;邻接面
  `tests/test_channels.py`、`tests/test_channel_file_attachments.py`、
  `tests/test_discord_channel.py`、`tests/unit/tools/test_behavior.py`、
  `tests/test_discord_channel_connections.py`、`tests/blocking_io/test_channels_ingest.py`
  (该文件随白名单默认把默认 reader 注入改为按渠道注册)全绿;
- `ruff check` / `ruff format --check` 改动文件通过。
