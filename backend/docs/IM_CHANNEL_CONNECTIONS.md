---
id: backend-docs-im-channel-connections
kind: reference
status: current
owner: repository maintainers
scope: user-owned IM channel bindings: connect-code flow, ownership transfer, file pipeline, and provider configuration
last-verified: 2026-10-04
verified-against: worktree docs/agent-doc-disclosure @ 3cd547c26
---

# IM Channel Connections

DeerFlow supports user-owned IM channel bindings for Telegram, Slack, Discord, Feishu/Lark, DingTalk, WeChat, WeCom, and Buzz. The feature reuses the existing `channels.*` runtime configuration, so it works in local and private deployments with the same outbound transports already supported by DeerFlow.

No public IP, OAuth callback URL, or provider webhook is required in this implementation.

This document covers both **architecture** (how the bind / dispatch / file pipeline fits together) and **configuration / operations** (the existing `config.yaml` knobs and security notes). For the high-level orientation, see [AGENTS.md](../AGENTS.md) → "IM Channels System".

---

## Architecture Overview

A user-owned IM channel connection is a **per-DeerFlow-user bind layer** layered on top of the existing provider bot credentials in `channels.*`. The connection layer adds three things the bot credentials alone cannot give you:

1. **Owner identity** — each `(provider, external account, workspace)` maps to exactly one DeerFlow account (`owner_user_id`). Every run created from that connection runs in the owner's bucket (memory, uploads, outputs, custom agent).
2. **One-time bind codes** — the browser Connect flow mints a short-lived `secrets.token_urlsafe(16)` code (600 s TTL, single-use) and surfaces it only in the initiating user's browser. The platform worker consumes `/connect <code>` (Telegram uses `/start <code>` over a deep link) before applying any `allowed_users` filter, so a not-yet-allowlisted user can complete their first bind.
3. **Strict ownership transfer** — the latest successful bind wins; `upsert_connection` revokes other owners' active rows for the same external identity. The DB-enforced partial unique index `uq_channel_connection_active_identity` (`WHERE status != 'revoked'`) makes the invariant race-free across concurrent writers.

### Conversation-scoped Custom Agents

Connected users can run `/agent list` to inspect the Custom Agents in their own DeerFlow user bucket, then `/agent use <name>` to start a new conversation with one.
The selection is written to the new Gateway thread's channel metadata and, for a Custom Agent, to the canonical `agent_name` routing metadata used by the Web UI. It is cached by `ChannelManager` for subsequent turns; on restart, the manager reads the channel metadata before the first resumed turn. Opening that thread from Web search therefore continues under the same Custom Agent instead of falling back to the default runtime.
Because selecting an agent always creates a new thread instead of mutating the current one, an existing conversation keeps its original runtime, prompt, skills, and checkpoint lineage.
`/agent use lead_agent` starts a new conversation with the default agent.

Connect codes are deliberately **bind-time defenses**, not chat-time defenses. After binding, ordinary `allowed_users` continue to gate regular messages exactly as before.

## Connect-code Flow

The browser initiates; the provider worker consumes the code; the manager never sees the code itself.

```mermaid
sequenceDiagram
    autonumber
    participant Browser as Browser (Settings)
    participant Gateway as Gateway<br/>/api/channels/...
    participant Store as SQL store<br/>channel_oauth_states
    participant Worker as Provider worker<br/>(Telegram/Slack/...)
    participant Repo as ChannelConnection repo<br/>(upsert_connection)

    Browser->>Gateway: POST /api/channels/{provider}/connect
    Gateway->>Store: insert code (token_urlsafe(16), TTL=600s, single-use)
    Gateway-->>Browser: code + (Telegram: deep-link URL)

    Note over Browser,Worker: User sends /connect <code> (or /start <code>) to the provider bot

    Worker->>Store: consume_oauth_state(code)
    alt valid + unexpired
        Store-->>Worker: ok (state consumed once)
        Worker->>Repo: upsert_connection(provider, external_account_id, workspace_id, owner_user_id)
        Repo-->>Worker: connection row (active)
        Worker-->>Browser: success reply (via channel callback)
    else invalid / expired / used
        Store-->>Worker: reject
        Worker-->>Browser: rejected (no reply in chat)
    end

    Note over Repo: Partial unique index uq_channel_connection_active_identity<br/>revokes prior owner's active row for the same identity
```

## Single-active-owner Transfer

The partial unique index is the source of truth — application code never has to "revoke the previous owner" explicitly because the upsert that re-uses an identity fails on conflict and the loser retries against the now-visible revoked state.

```mermaid
graph LR
    classDef prior fill:#E5D2C4,stroke:#806A5B,color:#30251E
    classDef new fill:#C9D7D2,stroke:#5D706A,color:#21302C
    classDef db fill:#D7D3E8,stroke:#6B6680,color:#29263A

    Prior["Prior owner<br/>connection_id=A<br/>status=connected"]:::prior
    New["New owner<br/>connection_id=B"]:::new
    Upsert["upsert_connection()<br/>(owner_user_id=B)"]:::new
    Idx["Partial unique index<br/>uq_channel_connection_active_identity<br/>WHERE status != 'revoked'"]:::db

    Prior -->|"loser: revoke"| Idx
    New -->|"winner: insert"| Idx
    Upsert -->|"trigger"| Idx
    Idx -->|"returns"| Prior
    Idx -.->|"retry against new state"| Upsert
```

After the dust settles:

```mermaid
graph LR
    classDef winner fill:#C9D7D2,stroke:#5D706A,color:#21302C
    classDef loser fill:#D7D3E8,stroke:#6B6680,color:#29263A

    New["connection_id=B<br/>owner=B<br/>status=connected"]:::winner
    Old["connection_id=A<br/>owner=A<br/>status=revoked"]:::loser

    New --- Old
```

The same invariant protects the `find_connection_by_external_identity` lookup used by `ChannelManager._get_bound_identity_rejection` — a non-revoked row can resolve to exactly one owner at any time.

## Provider Message Flow Once Bound

After a connection is bound, every inbound message walks the same path through `ChannelManager`. Slack/Discord (no streaming) and Feishu/Telegram (streaming) diverge only at the run boundary.

```mermaid
sequenceDiagram
    autonumber
    participant Platform as Provider<br/>(Slack/Telegram/...)
    participant Worker as Provider worker
    participant Bus as MessageBus<br/>bounded admission + queue
    participant Mgr as ChannelManager<br/>fixed worker pool
    participant Client as langgraph_sdk<br/>async client
    participant Gateway as Gateway<br/>/api/* routers

    Platform->>Worker: inbound chat message<br/>(resolved to connection_id + owner_user_id)
    Worker->>Bus: reserve by Gateway handoff, then commit InboundMessage
    Bus->>Mgr: fixed worker gets msg and awaits handler inline
    Mgr->>Mgr: _channel_storage_user_id(msg)<br/>→ owner-bound user_id
    Mgr->>Mgr: _get_bound_identity_rejection()<br/>(re-check identity by provider+ext+ws)
    Mgr->>Client: _get_or_create_thread(thread_id or new)
    Client->>Gateway: threads.create(metadata={channel_source})
    Gateway-->>Client: thread_id
    Mgr->>Mgr: receive_file(msg, thread_id, user_id=...)<br/>(owner-bound bucket)
    Mgr->>Mgr: _ingest_inbound_files(thread_id, user_id=...)

    alt channel supports streaming
        Mgr->>Client: runs.stream(messages-tuple + values)
        loop each chunk
            Client-->>Mgr: delta / values snapshot
            Mgr->>Bus: publish_outbound(is_final=False)
        end
    else Slack/Discord (no streaming)
        Mgr->>Client: runs.wait()
        Client-->>Mgr: final state
    end

    Mgr->>Bus: publish_outbound(is_final=True)
    Bus->>Worker: outbound callback
    Worker->>Platform: post reply (Telegram editMessageText,<br/>Feishu patch card, etc.)
```

### Inbound capacity and overload behavior

Three top-level `channels` settings control the MessageBus/manager lifecycle: `inbound_queue_maxsize` (default `1000`) covers queued messages plus provider-side reservations that may still be doing final identity/ack preparation, `max_concurrency` (default `5`) is the exact number of long-lived `ChannelManager` workers, and `shutdown_grace_period_seconds` (default `3`) bounds graceful draining before active handlers are cancelled. Active handlers run inline in those workers, so a burst cannot create a task per message. The maximum manager-owned live intake is therefore the pending capacity plus the fixed worker count.

Admission never waits for queue space, because waiting producer coroutines would simply move the unbounded backlog outside the queue. At capacity:

- Slack, Discord, Feishu/Lark, DingTalk, Telegram, WeChat, and WeCom drop the new message before DeerFlow sends its working acknowledgment. `MessageBus` emits a rate-limited warning with a cumulative rejection count.
- Buzz leaves the per-channel replay watermark unchanged and reconnects, allowing relay history to replay the event.
- GitHub webhook fan-out returns `503`. GitHub records the delivery as failed; an operator or recovery job can retry it through the Recent Deliveries UI or REST redelivery API (GitHub does not retry failed deliveries automatically).

Shutdown first closes admission and cancels follow-up watchers, but keeps provider transports alive while workers drain accepted messages for up to `shutdown_grace_period_seconds`. Once that grace expires, it cancels active handlers, discards queue entries that never began, and awaits every manager-owned worker and watcher. Provider coroutines submitted from SDK threads are likewise retained, cancelled, and awaited before their channel tears down SDK resources. A successful stop therefore leaves no owned handler able to use a closed transport. The Gateway's outer shutdown timeout remains the process-level bound; if it cancels cleanup, the service retains its transports and singleton instead of reporting a successful stop or hiding unfinished ownership.

## Sync vs Streaming Channels

The two paths split on `ChannelRunPolicy.supports_streaming` (per-channel registration in `CHANNEL_CAPABILITIES`):

```mermaid
graph TB
    classDef sync fill:#E5D2C4,stroke:#806A5B,color:#30251E
    classDef stream fill:#C9D7D2,stroke:#5D706A,color:#21302C

    Msg["InboundMessage<br/>(channel, chat_id, text, files)"]:::sync
    Sync1["Slack"]:::sync
    Sync2["Discord"]:::sync
    Sync3["DingTalk"]:::sync
    Wait["runs.wait()<br/>→ extract final AI text"]:::sync
    Out1["publish_outbound(is_final=True)"]:::sync

    Stream1["Feishu"]:::stream
    Stream2["Telegram"]:::stream
    Stream3["WeCom (AI card)"]:::stream
    Stream["runs.stream(messages-tuple + values)"]:::stream
    Mid1["publish_outbound(is_final=False)<br/>throttled"]:::stream
    Mid2["Telegram: edit placeholder message<br/>Feishu: patch running card<br/>WeCom: PUT /v1.0/card/streaming"]:::stream
    Final["publish_outbound(is_final=True)"]:::stream

    Msg --> Sync1 --> Wait --> Out1
    Msg --> Sync2 --> Wait --> Out1
    Msg --> Sync3 --> Wait --> Out1

    Msg --> Stream1 --> Stream --> Mid1 --> Mid2 --> Final
    Msg --> Stream2 --> Stream --> Mid1 --> Mid2 --> Final
    Msg --> Stream3 --> Stream --> Mid1 --> Mid2 --> Final
```

For the special GitHub case (`fire_and_forget=True` channel policy), the manager calls `runs.create()` and returns once the run is `pending` — no outbound reply, because GitHub agents post via the `gh` CLI from inside their sandbox. See [GITHUB_AGENTS.md](GITHUB_AGENTS.md) for the full GitHub flow.

### Streaming publish allowlist

What the manager publishes from a `messages-tuple` stream is an **allowlist, not a denylist** (`manager._accumulate_stream_text`): only assistant message types — LangChain serializes `AIMessage.type` as `"ai"`, `AIMessageChunk.type` as `"AIMessageChunk"`, plus the OpenAI-style `"assistant"` spelling for foreign runtimes — become displayable text. Matching is by prefix (`ai` / `assistant`), never substring, because ordinary words contain `"ai"` (`chain`, `domain`). A bare `str` payload is never accepted: it carries no type information, so it cannot be attributed to the assistant, and nothing in DeerFlow produces one (`runtime/serialization.py::serialize_messages_tuple` always emits `[message_dict, metadata]`). `_stream_payload_type` resolves the message type for both the `model_dump()` shape DeerFlow's own gateway emits and LangChain's `to_json()` constructor shape (whose top-level `type` is the literal `"constructor"`, with the class name at the tail of the `id` path).

The earlier rule rejected only payloads whose `type` contained `"tool"` and therefore published everything else, which leaked DeerFlow's hidden model context to every streaming IM channel: `DynamicContextMiddleware` injects recalled memory as a hidden `HumanMessage` (`type == "human"`) and rewrites the user's own turn into a new `HumanMessage`, `DurableContextMiddleware` injects a hidden `<durable_context_data>` `HumanMessage`, and LangGraph fans those state writes out on the `messages-tuple` stream. The leak was proved live on a Buzz relay, which published a `<memory>` fact block and, in another run, a verbatim echo of the user's own message as the assistant's reply. Defense in depth: `buzz.py::send()` additionally refuses text carrying hidden-context markers (see the Buzz connector contract below).

A swallowed streaming failure publishes its final outbound before releasing the inbound dedupe key, so a provider redelivery can retry without overtaking the terminal reply.

## Owner-scoped File Storage

`ChannelManager` resolves the storage owner **once** at the top of `_handle_chat` via `_channel_storage_user_id(msg)` and threads that value through the entire file pipeline. The same identity is used as the run `user_id` in `run_context` and as the bucket for memory, uploads, and outputs — so the bucket the agent reads/writes is always the bucket where channel files were staged.

```mermaid
flowchart TB
    classDef owner fill:#D8CFC4,stroke:#6E6259,color:#2F2A26
    classDef resolve fill:#C9D7D2,stroke:#5D706A,color:#21302C
    classDef bucket fill:#D7D3E8,stroke:#6B6680,color:#29263A
    classDef agent fill:#E5D2C4,stroke:#806A5B,color:#30251E

    Inbound["InboundMessage<br/>connection_id, owner_user_id, workspace_id"]:::owner
    Resolve["_channel_storage_user_id(msg)<br/>sanitized + fall back to safe(msg.user_id)"]:::resolve
    UserID["user_id = OWNER"]:::resolve

    RunID["run_context['user_id']<br/>(run identity)"]:::agent
    RunUploads["ensure_uploads_dir(thread_id, user_id=OWNER)"]:::bucket
    Ingest["_ingest_inbound_files(user_id=OWNER)"]:::bucket
    Receive["Channel.receive_file(msg, thread_id, user_id=OWNER)"]:::bucket
    Resolved["_resolve_attachments(user_id=OWNER)"]:::bucket
    Artifact["_prepare_artifact_delivery(user_id=OWNER)"]:::bucket
    Memory["_resolve_memory_user_id<br/>(make_safe_user_id match)"]:::bucket

    Bucket["backend/.deer-flow/users/OWNER/.../user-data/{uploads,outputs}"]:::bucket

    Inbound --> Resolve --> UserID
    UserID --> RunID
    UserID --> Receive
    UserID --> Ingest
    UserID --> RunUploads
    UserID --> Resolved
    UserID --> Artifact
    UserID --> Memory
    RunUploads --> Bucket
    Ingest --> Bucket
    Receive --> Bucket
    Resolved --> Bucket
    Artifact --> Bucket
```

The cached value is reused across the blocking (`runs.wait`) and streaming (`_handle_streaming_chat`) paths — even if a future `Channel.receive_file` returns a rewritten `InboundMessage`, uploads and artifact delivery still target the same bucket.

## IM File Attachment Pipeline

Inbound files (images, documents) first pass through `Channel.receive_file` for
provider-specific materialization. Attachments that continue through the shared
metadata path are staged by `_ingest_inbound_files`; their metadata is placed in
`HumanMessage.additional_kwargs.files`, and `UploadsMiddleware` injects a
`<current_uploads>` block for the current message. Some providers instead consume
their descriptors while downloading and rewrite placeholders or message text with
the resulting virtual path (or a failure notice). Historical uploads are not
automatically injected on later turns; the agent discovers them with
`list_uploaded_files`.

Feishu/Lark inbound resource streams are read with a 20,000,000-byte cap before
they are persisted or synced into a non-local sandbox. Oversized resources and
per-file path failures are surfaced as a failure placeholder in the message text
without aborting later attachments in the same inbound message.

```mermaid
sequenceDiagram
    autonumber
    participant IM as Provider message<br/>(file attachment)
    participant Worker as Provider worker
    participant Mgr as ChannelManager
    participant Ch as Channel impl<br/>.receive_file
    participant FS as Uploads directory<br/>users/OWNER/.../uploads/
    participant MW as UploadsMiddleware
    participant Agent as Agent run

    IM->>Worker: message with file URL/bytes
    Worker->>Mgr: InboundMessage(files=[...], connection_id, owner_user_id)
    Mgr->>Mgr: storage_user_id = _channel_storage_user_id(msg)
    Mgr->>Ch: receive_file(msg, thread_id, user_id=storage_user_id)
    Note over Ch: provider-specific download/decrypt/read;<br/>may persist or hand bytes to manager
    Ch-->>Mgr: materialized message<br/>(provider may rewrite placeholders/text)
    alt attachment continues through shared metadata path
        Mgr->>FS: _ingest_inbound_files(<br/>thread_id, msg, user_id=storage_user_id)
        FS-->>Mgr: uploaded file metadata
        Mgr->>MW: HumanMessage with<br/>additional_kwargs.files
        MW->>Agent: prepend <current_uploads><br/>(paths under /mnt/user-data/uploads/)
    else provider supplies virtual path in message text
        Ch->>FS: persist and/or sync attachment
        Mgr->>Agent: HumanMessage with rewritten path<br/>or failure notice
    end
    Agent->>FS: read_file / view_image (sandbox)
```

Provider `receive_file` implementations (Feishu/DingTalk `_receive_single_file`) normalize provider filenames, claim a collision-free basename, and write it through `write_upload_file_no_symlink` under the same channel lock; the returned basename drives both the agent-visible virtual path and non-local sandbox sync. Non-mounted Feishu/DingTalk sandbox syncs (`sandbox_files.py`) acquire unique non-releasing execution holders, drain blocking `update_file` workers across repeated cancellation, and release only after the last sandbox operation, so a parallel run cannot close the shared client mid-upload.

### Inbound media gating (WeChat/WeCom)

WeChat iLink inbound image/file downloads stream with an in-flight cap derived from `channels.wechat.max_inbound_image_bytes` / `max_inbound_file_bytes` (20 MB / 50 MB defaults) that aborts before the full read, and the payload-supplied `media.full_url` must pass a scheme + dot-boundary host-suffix allowlist (`channels.wechat.allowed_media_hosts`, defaulting to the `qq.com` family plus the configured `cdn_base_url` host) before anything is fetched. The limits are PLAINTEXT limits while the stream measures CIPHERTEXT, so the in-flight cap is the PKCS#7-padded size of exactly-limit plaintext (`WechatChannel._stream_cap_for`); the exact post-decryption check stays as the authority. There is deliberately **no URL re-fetch fallback**: `_read_wechat_inbound_file` (manager) only reads the locally staged `path` — the channel always stages one before publishing — so nothing fetches a WeChat URL outside the channel-side gate.

WeCom media URLs (frame-supplied `url`, no per-channel size config) get the same style of host gate — `qq.com` suffixes plus the COS shape `ww-aibot-img-<APPID>.cos.<region>.myqcloud.com` WeCom serves signed links from, where the numeric suffix must be one of the verified WeCom-owned Tencent Cloud APPIDs (`_WECOM_MEDIA_COS_APPIDS`, currently only the `1258476243` observed in Tencent's published callback examples) because bucket names are user-chosen and any Tencent Cloud account can register a lookalike `ww-aibot-img-*` bucket; other accounts go through operator suffixes from `channels.wecom.allowed_media_hosts` resolved from the live channel at read time — and the manager-level `MAX_INBOUND_URL_FILE_BYTES` (50 MB) streaming cap.

Both URL downloads and `_download_cdn_bytes` request `Accept-Encoding: identity`, refuse a response with any residual `Content-Encoding` before reading, and iterate `aiter_raw()`: httpx's transparent decoding would allocate the full decompressed body before the byte cap sees a chunk.

### No media URLs in logs

No URL-based inbound-media log line may contain any part of the URL (signed links carry credentials in path and query): failure labels use the attachment filename or host only (`manager._inbound_file_label`), and reader failures log a sanitized exception summary — class name plus HTTP status (`manager._reader_error_summary`, `wechat._media_download_error_summary`), never the URL-bearing message or traceback.

The rule extends to the HTTP client libraries' own records. httpx emits `HTTP Request: GET <full URL>` at INFO via the bare `httpx` logger. urllib3 — enumerated against the installed source; every remaining emitter logs host:port only (connection establishment/reset) or one absolute URL (the header-parse warning) that the generic pattern rewrites — renders a request target in five shapes, each needing a dedicated redaction pattern because the generic absolute-URL pass cannot see a target with no scheme: `Redirecting <target> -> <target>` at INFO via `urllib3.poolmanager` and DEBUG via `urllib3.connectionpool` (either slot may be an origin-form relative Location, which pool/connection callers pass or the Location header carries; the shape keeps the `^Redirecting ` prefix anchor because `-> /path` arrows also appear in non-URL logs — sandbox mount mappings — and must pass through untouched, while both slots consume through end-of-line: the raw Location header may carry interior spaces, and the recursive urlopen frame can pass it on as the next request target), the per-request `scheme://host:port "METHOD /path?query HTTP/x.x"` DEBUG line, `Retry: <target>` DEBUG and `Retrying (…) after connection broken by '<error>': <target>` **WARNING** — above the INFO root, so reachable at the default log level — via `urllib3.connectionpool`, and `Incremented Retry for (url='<target>')` DEBUG via `urllib3.util.retry` (origin-form on the request path, absolute on the redirect path). The generic pass's `rest` treats a quote as a closing mark only at a boundary — followed by whitespace, a closing parenthesis, or end of string — so urllib3's `Incremented Retry for (url='…')` keeps its `')` scaffolding while a quote embedded in a URL stays consumed and redacted. Logger filters only see records emitted through that exact logger — child loggers neither inherit them nor trigger them on propagation — so `UrlRedactionFilter` is attached to the `httpx` logger AND to every root handler by `configure_logging` (handler-level filters see propagated records), which also keeps Telegram's token-bearing Bot API paths (`api.telegram.org/bot<token>/...`, emitted by python-telegram-bot's httpx client) out of the logs.

## Cross-references

- [AGENTS.md](../AGENTS.md) → "IM Channels System" — the index view in `backend/AGENTS.md` (configuration knobs, message flow, component list)
- [GITHUB_AGENTS.md](GITHUB_AGENTS.md) — webhook-driven GitHub channel, agent bindings, fan-out, token lifecycle
- `app/channels/manager.py` — dispatcher, `_channel_storage_user_id`, `_handle_chat`, `_handle_streaming_chat`
- `deerflow.persistence.channel_connections` — SQL tables (`channel_connections`, `channel_oauth_states`, `channel_conversations`, `channel_credentials`) and `upsert_connection` / `consume_oauth_state` / `find_connection_by_external_identity`

---

# Configuration

Configure the actual IM bots under the existing `channels` block:

```yaml
channels:
  inbound_queue_maxsize: 1000
  max_concurrency: 5
  shutdown_grace_period_seconds: 3

  telegram:
    enabled: true
    bot_token: $TELEGRAM_BOT_TOKEN

  slack:
    enabled: true
    bot_token: $SLACK_BOT_TOKEN
    app_token: $SLACK_APP_TOKEN

  discord:
    enabled: true
    bot_token: $DISCORD_BOT_TOKEN

  feishu:
    enabled: true
    app_id: $FEISHU_APP_ID
    app_secret: $FEISHU_APP_SECRET

  dingtalk:
    enabled: true
    client_id: $DINGTALK_CLIENT_ID
    client_secret: $DINGTALK_CLIENT_SECRET

  wechat:
    enabled: true
    bot_token: $WECHAT_BOT_TOKEN

  wecom:
    enabled: true
    bot_id: $WECOM_BOT_ID
    bot_secret: $WECOM_BOT_SECRET

  buzz:
    enabled: true
    relay_url: wss://buzz.example.com
    private_key: $BUZZ_PRIVATE_KEY   # hex or nsec1…
```

Then enable user bindings in `channel_connections`:

```yaml
channel_connections:
  enabled: true
  # Auth-enabled deployments require ordinary IM messages to come from a
  # connected DeerFlow user by default. Set this to false only for legacy
  # operator-owned/open-bot deployments that intentionally route unbound
  # platform users to platform-ID user buckets.
  require_bound_identity: true

  telegram:
    enabled: true
    bot_username: $TELEGRAM_BOT_USERNAME

  slack:
    enabled: true

  discord:
    enabled: true

  feishu:
    enabled: true

  dingtalk:
    enabled: true

  wechat:
    enabled: true

  wecom:
    enabled: true

  buzz:
    enabled: true
```

`channel_connections` does not duplicate provider secrets. It only controls the browser-facing connect UI and stores per-user binding records. Telegram needs `bot_username` only so the frontend can open a deep link.

When `channel_connections.enabled` and `require_bound_identity` are true, auth-enabled deployments reject ordinary unbound IM messages before creating a DeerFlow thread or run. Users must connect the channel from DeerFlow Settings first. Auth-disabled local mode still routes channel messages to the auth-disabled default user, and legacy open-bot behavior can be restored explicitly with `require_bound_identity: false`.

Upgrade note: existing auth-enabled deployments that already have `channel_connections.enabled: true` will start rejecting ordinary unbound IM messages after this field is introduced because `require_bound_identity` defaults to true. Legacy operator-owned/open-bot deployments that intentionally allow unbound platform users to create DeerFlow runs should set `require_bound_identity: false` before upgrading and restart the service.

## Connect Flow

Telegram:

- The frontend creates a short one-time code.
- The Connect button opens `https://t.me/<bot_username>?start=<code>`.
- The existing Telegram long-polling worker receives `/start <code>` and binds that Telegram chat/user to the current DeerFlow user.

Slack:

- The frontend creates a short one-time code.
- The UI shows `Send /connect <code> to the DeerFlow Slack bot.`
- The existing Slack Socket Mode worker receives the message and binds the Slack user/team to the current DeerFlow user.

Discord:

- The frontend creates a short one-time code.
- The UI shows `Send /connect <code> to the DeerFlow Discord bot.`
- The existing Discord Gateway worker receives the message and binds the Discord user/guild to the current DeerFlow user.

Feishu/Lark, DingTalk, WeChat, and WeCom:

- The frontend creates a short one-time code.
- The UI shows `Send /connect <code> to the DeerFlow <Provider> bot.`
- The already-running long-connection or polling worker receives the message and binds the platform user/workspace identity to the current DeerFlow user.

Buzz:

- Unlike the bot/app credentials above, Buzz has no separate developer console: DeerFlow joins the relay as an ordinary member identity. Generate a Nostr keypair for that identity — everything below refers to its **hex public key**.
- **Onboarding takes two separate steps, and both are required.** Relay membership and channel membership are different things, and doing only the first produces a connector that connects and authenticates cleanly while receiving nothing:

  1. **Register the pubkey as a relay member** — `buzz-admin add-member --pubkey <hex>`. This is what lets the identity authenticate (NIP-42) and publish at all.
  2. **Add it to each channel it should participate in** — `buzz channels add-member --channel <uuid> --pubkey <hex> --role bot`. Chat events are only delivered to a channel's members, and the relay additionally **rejects** any message that `p`-mentions a non-member with `mentioned pubkeys are not channel members` — so without this step the connector can neither hear a mention nor answer one.

  See the [Buzz project](https://github.com/block/buzz) for the admin tooling.
- **Channels are auto-discovered — you do not list them in `config.yaml`.** On every connection the connector asks the relay which channels this identity belongs to and subscribes to each one individually. Adding it to a new channel later takes effect **live**, without a restart or reconnect: the relay sends a membership notification and the connector starts listening immediately (and stops listening when it is removed). If you see `channel discovery returned no channels` in the logs, step 2 above has not been done.
- Configure `relay_url` and `private_key` (hex or `nsec1…`) under `channels.buzz`, then enable `channel_connections.buzz`.
- The frontend creates a short one-time code.
- The UI shows `Send /connect <code> to the DeerFlow Buzz bot.`
- The already-running Buzz relay-loop worker receives the message — sent as a DM or an @mention in a channel both parties belong to — and binds the sender's Nostr pubkey to the current DeerFlow user.
- Requires the `buzz` dependency extra (`uv sync --extra buzz`) for the `coincurve` library. `scripts/detect_uv_extras.py` (and Docker/production builds via `backend/Dockerfile`) auto-detect and preserve this extra when `channels.buzz.enabled: true` in `config.yaml`, the same way the `browser` extra is auto-detected for `browser_navigate`.

### Buzz subscription model

Buzz's relay only delivers chat events to **channel-scoped** subscriptions, which is why the connector's subscriptions look the way they do. A global `REQ {"kinds":[9]}` is accepted and answered with `EOSE`, but no chat event is ever fanned out to it, and a single subscription cannot cover several channels either (a multi-value `#h` matches nothing). So, on **every** connection, after NIP-42 auth completes:

| Subscription | Filter | Purpose |
|---|---|---|
| `buzz-discovery` | `{"kinds":[39000]}` | Historical query listing exactly the channels this identity is a member of (one stored event each, then `EOSE`). Supplies each channel's name and type, which is also what the DM mention-exemption reads. Do **not** narrow it with `#p` — that matches nothing. |
| `buzz-membership` | `{"kinds":[44100,44101], "#p":["<our pubkey>"], "since": …}` | **Live** membership notifications. `44100` (added) subscribes to the new channel immediately; `44101` (removed) closes that channel's subscription. This is what makes a newly added channel work without a restart. |
| `buzz-chat-<uuid>` | `{"kinds":[9], "#h":["<uuid>"], "since": …}` | One per discovered channel — the only shape that actually receives messages. |

Consequences worth knowing operationally:

- **Replay is tracked per channel.** Each channel carries its own `since` watermark, advanced only by events DeerFlow actually processed. A single shared watermark would let a busy channel drag the cursor past a quiet channel's unread messages and skip them after a reconnect; per-channel cursors can only ever cost duplicate delivery (which the manager's inbound dedupe absorbs), never a miss.
- **Membership is scoped to live events.** The relay *stores* 44100/44101 events, so without a `since` every connection replayed the whole membership history as if it had just happened — re-running channel discovery once per stored add (you would see several `channel discovery complete` lines for one connect, and channels logged as `<unnamed>`), re-subscribing channels you have since been removed from, and briefly unsubscribing channels you are still in. The subscription is therefore anchored at the moment the socket opened, minus 60s of slack so a membership change made *during* the connect/auth handshake — or a small relay clock skew — is still picked up.
- **The number of channel subscriptions is capped** (256). The channel list comes off the wire, so it is bounded like any other remote-fed state. At the cap, new channels are refused and named in a `per-channel subscription limit reached` warning rather than an existing, working subscription being evicted.
- **A subscription the relay closes is re-opened, up to 3 times per connection.** Every subscription on the socket fails *silently* when the relay drops it: a chat subscription deafens one channel, `buzz-membership` stops DeerFlow ever learning it was added to or removed from a channel, `buzz-discovery` kills the completeness sweep. So a `CLOSED` frame is recovered, not just noted, and the subscription that went quiet is always named at WARNING level. Recovery is skipped when the relay's stated reason says the subscription is not ours any more — a NIP-01/NIP-42 `auth-required:` / `restricted:` / `blocked:` / `invalid:` prefix, or buzz-relay's own revocation wording — because re-issuing the same REQ then just fights the relay. Any other reason (including a `CLOSED` with no reason at all) is treated as a hiccup and retried, with the 3-attempt budget as the backstop; after that it stays down until the next reconnect, which rebuilds everything from scratch.
- **Known bound: more than 2000 unread messages in one channel across a disconnect loses the oldest of them.** The relay caps historical delivery at 2000 events per subscription and serves them newest-first, even with a `since`. DeerFlow processes what it receives and the channel's watermark advances past the rest, so those older messages are never delivered and never retried. Every other gap in the design fails toward duplicate delivery (which is absorbed by inbound dedupe); this is the one remaining case that can skip, and it needs both a disconnect and a >2000-message backlog in a *single* channel to occur.

### Buzz trust model

On a team-run Buzz relay the relay operator is not necessarily the DeerFlow operator, so be precise about what the connector proves and what it takes on trust:

**Verified (cryptographically, on every inbound event):** DeerFlow recomputes each event's NIP-01 id from the delivered payload and verifies its BIP-340 Schnorr signature against the claimed `pubkey` before the event can influence anything. A relay therefore cannot rewrite a member's message, replay one author's signature onto another payload, or claim an allowlisted author it does not hold the key for. This applies to `/connect` binds as well as ordinary chat, so a relay cannot bind someone else's pubkey to an attacker's DeerFlow account. Events that fail verification are dropped with a warning.

**Trusted (not verified):** the *authorship* of kind-39000 channel metadata. Buzz publishes channel discovery events from the relay's own keypair, but nothing already configured identifies that key (`relay_url` is a network address, not a signing key), so DeerFlow only proves such an event was signed by *some* member. Because channel discovery and subscription are now driven by exactly these events, a forged kind-39000 has two effects, not one:

1. It can mark a channel `type: "dm"`, which relaxes the `require_mention` requirement for that channel.
2. It can make DeerFlow **open a chat subscription** for a channel of the forger's choosing, since the set of channels DeerFlow listens to is the set it holds metadata for.

Neither can make anything be *acted on*. The `allowed_users` allowlist and per-event signature verification are independent gates: an author who is not allowlisted is dropped regardless of channel type or how the subscription was opened. The blast radius of (2) is a relay reading its own traffic back to a subscriber that ignores it, bounded by the 256-subscription cap (which refuses new subscriptions rather than evicting working ones, so an induced subscription cannot displace a real channel). The same applies to a forged kind-44100 membership notification, except that its `p` tag is re-checked locally, so it must at least name this identity. If you need the mention requirement to be unforgeable on a relay whose members you do not all trust, keep those channels out of `mention_free_channels` and treat DM detection as convenience rather than a boundary.

**Deny-by-default allowlist:** unlike other providers (where an empty `allowed_users` means "allow everyone"), `channels.buzz.allowed_users` is deliberately deny-by-default — an empty list means *nobody* can trigger a run, and DeerFlow logs a startup warning saying so. Add each member pubkey (hex or `npub1…`) that should be able to reach the agent. Individual drops are logged at DEBUG level.

**Bound identity:** once a pubkey completes `/connect`, its inbound messages resolve to that connection and run under the bound DeerFlow user (memory, files, and artifacts land in that user's buckets). Bindings are scoped to the relay host, so the same pubkey on a different relay is a different identity and must bind separately.

Codes use 128 bits of randomness, expire after 10 minutes, and are single-use.

For providers with an `allowed_users` allowlist (Telegram, Slack, DingTalk, WeChat, …), a valid `/connect <code>` (or Telegram `/start <code>`) is consumed **before** the allowlist is checked. This is intentional: a user who is not yet on the allowlist — and whose platform identity the bot has therefore never seen — can still complete their first browser-initiated bind. After binding, `allowed_users` continues to gate ordinary (non-bind) messages as before.

### Buzz connector engineering contract

Engineering-level invariants behind the operator-facing models above, for changes to `app/channels/buzz.py` / `buzz_nostr.py` / `buzz_seen_events.py`:

- **Subscription shapes.** Exactly one REQ per channel: `buzz-discovery` `{"kinds":[39000]}` (historical, no `#p` — adding it returns zero; supplies channel name/type, which the DM mention-exemption reads), one `buzz-membership` `{"kinds":[44100,44101],"#p":["<us>"],"since":<connect time − MEMBERSHIP_LOOKBACK_SECONDS>}` (relay-signed member-added/member-removed notifications whose `p` tag names the affected member and `h` tag the channel), and one `buzz-chat-<uuid>` `{"kinds":[9],"#h":["<uuid>"]}` per discovered channel, opened as each kind-39000 arrives; the discovery `EOSE` is the completeness barrier that retries failed chat subscriptions and warns when discovery found nothing. Subscription ids are deterministic per channel so one can be replaced or closed without disturbing the others on the socket; `_chat_subscriptions` is per-socket state cleared on session end, on re-auth (a pre-auth REQ may have been rejected), and by `stop()`.
- **Membership is LIVE-scoped.** The relay *stores* 44100/44101 and serves history newest-first (default limit 2000). An unscoped filter replayed the whole membership history on every connect — every stored add read as live, re-running discovery once each (M+1 discovery passes × N stored kind-39000 events per connect, observed live as two `channel discovery complete` lines and one channel logged `<unnamed>` because the 44100 path subscribed before its metadata arrived), re-subscribing channels we have since been removed from, and letting a stored 44101 transiently unsubscribe a channel we are still in. `since` is anchored at the moment the socket opened (`_session_started_at`) minus `MEMBERSHIP_LOOKBACK_SECONDS` (60), covering both relay clock skew and a membership change published *during* the connect/auth handshake; the slack can only cost an idempotent replay of the last minute.
- **Live add/remove.** A kind-44100 for our pubkey subscribes to the new channel **live**, then re-issues discovery only when that channel's metadata is actually missing — an unconditional refresh is how a burst of 44100s multiplied into one discovery pass each. A kind-44101 issues `buzz_nostr.close_frame` for exactly that channel's subscription and drops its metadata.
- **A `CLOSED` frame is recovered, not forgotten.** `_handle_closed` re-issues the subscription, bounded by `MAX_RESUBSCRIBE_ATTEMPTS` (3) per subscription id per connection **and per auth epoch** (`_resubscribe_attempts` resets on session start, on re-auth, and by `stop()`, so pre-auth rejections — which the auth branch already recovers wholesale — never spend the authenticated session's budget). The first retry is immediate (the common case is a one-off hiccup); later ones back off 1s then 2s, awaited inline in the read loop rather than in a background task that could outlive its own socket. `auth-required:` before this socket has completed its NIP-42 handshake is the expected bootstrap sequence, not a refusal: the connector opens its control REQs immediately in case the relay serves unauthenticated reads, a closed relay answers `auth-required:` plus an `AUTH` challenge, and the auth branch re-opens everything. That case is logged at DEBUG and consumes neither the permanent-refusal branch nor the retry budget (a chat subscription is still dropped from `_chat_subscriptions`, since it genuinely is not subscribed and discovery is what re-opens it). Treating it as permanent once produced an operator-facing warning claiming discovery/membership tracking was DOWN in the same run where discovery then completed, every channel was subscribed, and a brand-new channel's kind-44100 was picked up one second later. The boundary is the per-socket `_auth_completed` flag, set once the signed AUTH event has been sent and cleared on session entry, session exit, and `stop()`; the same reason *after* that stays loud, and says the subscription is down until the relay's next AUTH challenge or the next reconnect rather than borrowing the non-auth wording. `_is_transient_close` decides whether to retry at all: NIP-01/NIP-42 `auth-required:`/`restricted:`/`blocked:`/`mute:`/`invalid:`/`pow:` prefixes and buzz-relay's own removal/revocation prose are permanent (do not fight the relay over a channel that is no longer ours; a post-auth `auth-required:` is recovered by the AUTH branch, not by re-issuing), `rate-limited:`/`error:`/no-reason-at-all and anything unrecognized are transient — the default resolves toward "keep listening" because going silently deaf is the failure this exists to remove, and the attempt budget bounds a wrong guess. A chat `CLOSED` is only ever recovered for a channel already in `_chat_subscriptions`: a `CLOSED` is relay-supplied, so acting on an unknown one would let a relay induce a subscription just by naming a channel. Every subscription that goes unlistened is logged at WARNING, never INFO.
- **Bounds on remote-fed state.** `MAX_CACHED_CHANNELS` (512) caps the kind-39000 metadata cache, the watermark map, and the resubscribe-attempt map; `MAX_CHANNEL_SUBSCRIPTIONS` (256, well under buzz-relay's own 1024-per-connection ceiling) caps live chat subscriptions — at the cap new channels are refused and named in a warning rather than evicting a working subscription.
- **Cursors.** The replay cursor (`since`) is **per channel**, advances only for events that were actually processed, and never past `now + MAX_FUTURE_SKEW_SECONDS` (60), because it is peer-supplied (`created_at`) and a single future-dated event otherwise made the connector permanently deaf. Per channel rather than global is the safety-critical half: subscriptions are per channel, so one shared cursor is the newest event seen in *any* channel and a busy channel would drag it past a quiet channel's unread messages, skipping them on the next reconnect — measured on a live relay, three channels of one identity sat ~28h apart. Per-channel cursors can only ever cost duplicate delivery (absorbed by the manager's `event_id` dedupe), and an evicted cursor degrades to "no `since`", i.e. the relay's default backlog — both fail toward replay, never toward a miss. The known 2000-event historical bound above remains the one path that can skip.
- **Streaming bookkeeping.** Streaming tracks every oversize chunk index (`_stream_targets` for chunk 0, `_stream_tails` for the rest), since the manager republishes cumulative text and reposting `chunks[1:]` per update flooded the channel; all of it is per-connection state cleared by `stop()`.
- **Hidden-context send refusal.** `send()` refuses outright to publish text carrying a hidden model-context wrapper (`<memory>`, `<durable_context_data>`, `<system-reminder>` — `_HIDDEN_CONTEXT_MARKERS`), logging at ERROR and clearing the stream bookkeeping on a blocked `is_final`. This is defense in depth behind the manager's allowlist, and it lives here rather than in a sibling connector because on Buzz a leak is permanent: every streaming update is an immutable public Nostr event, so a corrective edit only changes what clients render while the original leaked event stays on the relay. Matching is on the literal opening tag, so a reply that merely talks about memory is still published.
- **Seen-event store.** The durable replay guard uses async `aseen()` / `arecord()` / `aflush()` boundaries: initial JSON reads and coalesced atomic writes run off the Gateway event loop. `aflush()` awaits any in-flight write, attempts at most one final snapshot, leaves a still-changing generation dirty for fail-open replay, and returns without a live persistence timer. A Gateway cancellation does not cancel the underlying worker-thread write; `BuzzChannel.stop()` tracks cleanup completion separately from transport admission so ChannelService can retry the retained channel without racing a second snapshot against that write. The store is quiesced before stop (including the already-stopped guard), so a timed-out relay task that records after stop only marks data dirty and cannot schedule detached file work; a repeated `stop()` still drains that dirty state, and `BuzzChannel.start()` explicitly resumes scheduling and flushes it automatically.
- **Trust primitives.** `buzz_nostr.verify_event` is pure and total (malformed input returns `False`, never raises); a forged kind-44100 has its `p` tag re-checked locally so it must at least name this identity.

## Runtime Model

Connection records live in SQL tables under `deerflow.persistence.channel_connections`:

- `channel_connections`: owner user, provider identity, workspace/guild/team, status, metadata.
- `channel_oauth_states`: one-time connect codes and Telegram deep-link state.
- `channel_conversations`: connection-scoped IM conversation to DeerFlow thread mapping.
- `channel_credentials`: reserved for future provider-token flows, not used by the local/private binding flow.

Incoming messages that resolve to a connection carry `connection_id`, `owner_user_id`, and `workspace_id`. `ChannelManager` uses `owner_user_id` as the DeerFlow run user id and preserves the raw platform user id as `channel_user_id`.

Runtime provider credentials are deployment-level bot secrets, not user-owned
connection credentials. They can come from `channels.*` in `config.yaml` or
from the browser runtime setup flow, which persists them through
`ChannelRuntimeConfigStore` so local/private deployments can configure bots
without editing YAML. The runtime store is a local plaintext JSON fallback with
owner-only file permissions (`0600`); use it only where the DeerFlow data
directory is already trusted as secret storage. WeChat QR login auth state
follows the same local-runtime model and may persist a QR-derived bot token in
the channel state directory.

### Channel user id runtime context

For user-owned connections, incoming messages carry `connection_id`,
`owner_user_id`, and `workspace_id`; `owner_user_id` becomes the DeerFlow run
`user_id`, while the raw platform user id remains `channel_user_id`. The Gateway
accepts `channel_user_id` only from an internally authenticated channel caller's
top-level `body.context`, clears it from both free-form `body.config` sections,
and writes it into runtime context only (never `configurable`, which is
checkpointed). `bash_tool` exposes it to sandbox commands as the fixed env var
`DEERFLOW_CHANNEL_USER_ID` — via a shell-quoted command-string prefix, NOT the
`execute_command(env=...)` channel, which is reserved for request-scoped secrets
and would switch `AioSandbox` onto the `bash.exec` path (image >= 1.9.3, fresh
session per call).

Per-call injection keeps group-chat identity correct (one thread/sandbox, many
senders) **without depending on the AIO shell's session semantics**: every
IM-channel command carries an explicit `export VAR=<id>; ` (valid id) or
`unset VAR; ` (empty / non-str / over the 256-char cap). The AIO no-env path
reuses a persistent shell session (the reason for the class lock, #1433), so a
bare command could otherwise resolve a stale id an earlier sender exported; the
`unset` closes the window the length/type guard would open (a dropped id would
inherit the previous sender's value). Non-IM runs (no `channel_user_id` in
context) are left untouched. Not injected on the Windows local sandbox (its
PowerShell/cmd.exe fallback has no `export`/`unset`).

The value propagates across `task` delegation: `task_tool` captures the
dispatching turn's id and the subagent executor forwards it into the subagent's
runtime context, same as the guardrail attribution fields. The runtime-context
value is authorization-grade at the Gateway/guardrail boundary, but the exported
shell variable remains informational because any bash command can overwrite its
own environment; skills must not treat the shell variable itself as
authenticated identity. Tests: `backend/tests/test_gateway_services.py`,
`backend/tests/test_channel_user_id_env.py`.

### WeChat and WeCom connection runtime limits

WeChat timing settings (`polling_timeout`, `polling_retry_delay`,
`qrcode_poll_interval`, `qrcode_poll_timeout`) accept only positive finite
seconds; invalid values fall back to their defaults so polling cannot enter a
hot loop or sleep forever.

WeCom serializes `start()` and `stop()` for each channel instance. The SDK
`connect()` task covers connection setup only; after the handshake, the SDK owns
a separate receive task. Shutdown cancels an in-progress connection attempt and
awaits the SDK's actual asynchronous receive-task/socket cleanup before
releasing lifecycle state or allowing a restart. Cancellation of `stop()` still
propagates, but only after owned cleanup finishes and lifecycle references are
cleared; real connection failures remain reported by `_on_ws_task_done`.

WeCom outbound content is capped at the protocol's 20480 UTF-8 bytes: stream
replies clip on a character boundary with a truncation marker (one stream
carries the whole reply and cannot split mid-way), while proactive pushes split
into at most 10 sequential markdown messages per push, with the remaining tail
clipped and marker-terminated. Both paths measure bytes, not characters. A
per-chat send lock serializes each split batch end to end, because manager
workers run concurrently and two long pushes to the same chat would otherwise
interleave chunks; locks are reference-counted and reclaimed once no sender
holds or waits on them, so the registry does not grow for the life of the
Gateway.

## Security Notes

- Browser APIs remain authenticated and CSRF-protected.
- Connect codes are 128-bit random, short-lived, and single-use.
- Runtime provider bot tokens are shared deployment secrets. Runtime setup
  responses mask password fields, and mutating runtime/channel-worker APIs
  require an admin user.
- Stored per-connection credentials use the `channel_credentials` encryption
  path. If stored credential material cannot be decrypted, DeerFlow treats it
  as unavailable instead of using corrupt secrets.
- The local plaintext runtime credential fallback is documented above; prefer
  deployment-managed environment/config secrets for non-local deployments until
  a dedicated secret backend is configured.
- `allowed_users` is **not** a bind-time defense. Because connect codes are processed before the allowlist (see Connect Flow), anyone who possesses a valid code can consume it — not only allowlisted users. Bind security therefore rests entirely on the code's confidentiality: it is 128-bit random, expires after 10 minutes, is single-use, and is shown only in the initiating user's browser (never echoed back to chat). Treat connect codes like one-time passwords and do not forward them.
- An external identity — `(provider, external account, workspace/team/guild)` — has at most one active owner. The most recent successful bind wins: connecting an identity that another DeerFlow user already holds transfers ownership and revokes the previous owner's binding (and its stored credentials). This is enforced at the database layer, so two users racing to bind the same identity cannot both end up connected.
- Provider bot tokens remain in `channels.*` and are never returned to the browser.
- Stored per-connection credentials are encrypted. If stored credential material cannot be decrypted, DeerFlow treats it as unavailable instead of using corrupt secrets.
- This implementation does not add public provider callback or webhook routes.
