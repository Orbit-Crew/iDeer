"""Chat model adapter for Dify-style app service APIs (e.g. 临空智言).

Wraps an application-level chat endpoint (``POST {base_url}/chat-messages``)
as a LangChain ``BaseChatModel``, so an orchestrated chatflow app (RAG 检索问答
等) can be selected like any other model in ``config.yaml``.

Protocol notes (Dify Service API):
- Auth is ``Authorization: Bearer {api_key}`` plus this deployment's required
  ``X-Email`` header; the body also requires a ``user`` identifier.
- Input is a single ``query`` string, not a message list. This adapter
  flattens the full LangChain message history into one role-labeled query and
  never sends ``conversation_id`` (stateless): the remote conversation state
  cannot follow iDeer's Run/Thread restore, resume or branching, so every
  request is self-contained.
- Streaming only. Dify documents a ~100s hard cutoff for blocking responses,
  so ``_generate``/``_agenerate`` aggregate the SSE stream internally instead
  of using ``response_mode=blocking``.
- SSE events are translated: ``message`` deltas become ``AIMessageChunk``
  content; ``message_end`` carries terminal ``usage_metadata`` (prompt/
  completion/total tokens) and ``response_metadata.model``; ``workflow_*`` /
  ``node_*`` / ``ping`` / ``message_file`` / ``tts_*`` are ignored;
  ``error`` raises ``RuntimeError`` with the Dify error code.
- The endpoint has no function calling, vision, or content-moderation
  replacement support: ``bind_tools`` warns and ignores the tools so agent
  runtimes degrade to plain answering instead of crashing, non-text content
  blocks are dropped during flattening, and ``message_replace`` events are
  logged and skipped (documented limitation).
"""

import json
import logging
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import RunnableBinding
from pydantic import Field

logger = logging.getLogger(__name__)

_DEFAULT_USER = "deerflow"


class DifyAppChatModel(BaseChatModel):
    """LangChain chat model backed by a Dify-style app service API.

    Config example::

        - name: linkong-archive-qa
          display_name: 档案全文智能检索
          use: deerflow.models.dify_app_provider:DifyAppChatModel
          model: linkong-archive-qa
          base_url: https://10.20.10.88/v1
          api_key: $DIFY_APP_API_KEY
          email: $DIFY_APP_EMAIL        # X-Email header required by this deployment
          verify_ssl: false             # internal deployment uses a self-signed certificate
    """

    base_url: str
    api_key: str
    model: str = ""
    email: str = ""
    dify_user: str = ""
    inputs: dict = Field(default_factory=dict)
    verify_ssl: bool = True
    timeout: float = 300.0

    @classmethod
    def is_lc_serializable(cls) -> bool:
        return True

    @property
    def _llm_type(self) -> str:
        return "dify-app"

    def model_post_init(self, __context: Any) -> None:
        if not self.api_key:
            raise ValueError("DifyAppChatModel requires an `api_key` (the app's service API key).")
        super().model_post_init(__context)

    # ------------------------------------------------------------------
    # Message flattening
    # ------------------------------------------------------------------

    @staticmethod
    def _content_to_text(content: Any) -> str:
        """Flatten LangChain content blocks into plain text.

        Non-text blocks (images, audio, ...) are dropped: the app endpoint
        accepts text only in ``query``.
        """
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(filter(None, (DifyAppChatModel._content_to_text(item) for item in content)))
        if isinstance(content, dict):
            block_type = content.get("type")
            if block_type and block_type != "text":
                return ""
            text = content.get("text")
            if isinstance(text, str):
                return text
            nested = content.get("content")
            if nested is not None:
                return DifyAppChatModel._content_to_text(nested)
            try:
                return json.dumps(content, ensure_ascii=False)
            except TypeError:
                return str(content)
        return str(content)

    def _flatten_messages(self, messages: list[BaseMessage]) -> str:
        """Flatten the message history into one role-labeled ``query`` string."""
        parts = []
        for msg in messages:
            if isinstance(msg, ToolMessage):
                prefix = f"[工具:{getattr(msg, 'name', '') or 'tool'}]"
            elif isinstance(msg, SystemMessage):
                prefix = "[系统]"
            elif isinstance(msg, HumanMessage):
                prefix = "[用户]"
            elif isinstance(msg, AIMessage):
                prefix = "[助手]"
            else:
                prefix = "[消息]"
            text = self._content_to_text(msg.content)
            if not text.strip():
                continue
            parts.append(f"{prefix} {text}")
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Request building
    # ------------------------------------------------------------------

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if self.email:
            headers["X-Email"] = self.email
        return headers

    def _build_payload(self, query: str) -> dict:
        return {
            "inputs": self.inputs,
            "query": query,
            "response_mode": "streaming",
            "conversation_id": "",
            "user": self.dify_user or self.email or _DEFAULT_USER,
            "auto_generate_name": False,
        }

    def _chat_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat-messages"

    def _client_timeout(self) -> httpx.Timeout:
        # SSE streams are long-lived; the read timeout bounds per-chunk gaps,
        # not total generation time. Blocking mode is deliberately unused.
        return httpx.Timeout(connect=30.0, read=self.timeout, write=60.0, pool=30.0)

    # ------------------------------------------------------------------
    # SSE parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_sse_data_line(line: str) -> dict | None:
        if not line.startswith("data:"):
            return None
        raw_data = line[5:].strip()
        if not raw_data:
            return None
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            logger.debug("Skipping non-JSON Dify SSE frame: %s", raw_data[:200])
            return None
        return data if isinstance(data, dict) else None

    def _post_stream(self, payload: dict) -> Iterator[dict]:
        with httpx.Client(timeout=self._client_timeout(), verify=self.verify_ssl) as client:
            with client.stream("POST", self._chat_url(), headers=self._build_headers(), json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    data = self._parse_sse_data_line(line)
                    if data is not None:
                        yield data

    async def _apost_stream(self, payload: dict) -> AsyncIterator[dict]:
        async with httpx.AsyncClient(timeout=self._client_timeout(), verify=self.verify_ssl) as client:
            async with client.stream("POST", self._chat_url(), headers=self._build_headers(), json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    data = self._parse_sse_data_line(line)
                    if data is not None:
                        yield data

    @staticmethod
    def _usage_metadata(usage: dict) -> dict | None:
        if not usage:
            return None
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": usage.get("total_tokens", input_tokens + output_tokens),
        }

    def _chunk_from_event(self, event: dict) -> ChatGenerationChunk | None:
        event_type = event.get("event")
        if event_type == "message":
            answer = event.get("answer")
            if answer:
                return ChatGenerationChunk(message=AIMessageChunk(content=answer))
            return None
        if event_type == "message_end":
            usage = (event.get("metadata") or {}).get("usage") or {}
            return ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    usage_metadata=self._usage_metadata(usage),
                    response_metadata={"model": self.model, "model_provider": self._llm_type},
                )
            )
        if event_type == "error":
            raise RuntimeError(f"Dify app stream error (status={event.get('status')}, code={event.get('code', 'unknown')}): {event.get('message', '')}")
        if event_type == "message_replace":
            logger.warning("Dify app content-moderation message_replace event is not rendered; ignoring.")
            return None
        # workflow_started/finished, node_started/finished, ping, message_file,
        # tts_message/tts_message_end carry no model answer text.
        return None

    # ------------------------------------------------------------------
    # LangChain hooks
    # ------------------------------------------------------------------

    def _stream(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: CallbackManagerForLLMRun | None = None, **kwargs: Any) -> Iterator[ChatGenerationChunk]:
        payload = self._build_payload(self._flatten_messages(messages))
        saw_end = False
        for event in self._post_stream(payload):
            chunk = self._chunk_from_event(event)
            if chunk is not None:
                yield chunk
            if event.get("event") == "message_end":
                saw_end = True
        if not saw_end:
            raise RuntimeError("Dify app stream ended without a message_end event")

    async def _astream(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: AsyncCallbackManagerForLLMRun | None = None, **kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        payload = self._build_payload(self._flatten_messages(messages))
        saw_end = False
        async for event in self._apost_stream(payload):
            chunk = self._chunk_from_event(event)
            if chunk is not None:
                yield chunk
            if event.get("event") == "message_end":
                saw_end = True
        if not saw_end:
            raise RuntimeError("Dify app stream ended without a message_end event")

    @staticmethod
    def _chunks_to_result(chunks: list[ChatGenerationChunk]) -> ChatResult:
        content = "".join(chunk.message.content for chunk in chunks if isinstance(chunk.message.content, str))
        usage_metadata = next((chunk.message.usage_metadata for chunk in reversed(chunks) if chunk.message.usage_metadata), None)
        response_metadata = next((chunk.message.response_metadata for chunk in reversed(chunks) if chunk.message.response_metadata), {})
        message = AIMessage(content=content, usage_metadata=usage_metadata, response_metadata=response_metadata)
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: CallbackManagerForLLMRun | None = None, **kwargs: Any) -> ChatResult:
        chunks = list(self._stream(messages, stop=stop, run_manager=run_manager, **kwargs))
        return self._chunks_to_result(chunks)

    async def _agenerate(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: AsyncCallbackManagerForLLMRun | None = None, **kwargs: Any) -> ChatResult:
        chunks = [chunk async for chunk in self._astream(messages, stop=stop, run_manager=run_manager, **kwargs)]
        return self._chunks_to_result(chunks)

    def bind_tools(self, tools: list, **kwargs: Any) -> Any:
        """Accept bound tools without sending them: the endpoint cannot call tools.

        Agent runtimes (``langchain.agents.create_agent``) unconditionally call
        ``bind_tools``; raising here would make the model unusable there, so the
        binding degrades to the bare model and the agent falls back to direct
        answering.
        """
        names = []
        for tool in tools:
            if isinstance(tool, dict):
                name = (tool.get("function") or {}).get("name") or tool.get("name")
            else:
                name = getattr(tool, "name", None)
            names.append(str(name) if name else repr(tool))
        logger.warning("Dify app endpoint does not support tool calling; ignoring bound tools: %s", ", ".join(names) or "(none)")
        return RunnableBinding(bound=self, kwargs={})
