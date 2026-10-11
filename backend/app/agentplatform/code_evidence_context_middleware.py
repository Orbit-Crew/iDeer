"""Enterprise code-evidence package context for the lead agent.

The gateway freezes a server-derived code-evidence summary into the run context
(``code_package_id`` + ``code_evidence_manifest``, see
``app/gateway/run_preparation.py``). This middleware surfaces that trusted
summary to the lead agent: the package was expanded server-side at a fixed
virtual root, so the agent reads source directly and never asks the user to
unzip anything.

This used to live inside the legacy ideer DynamicContextMiddleware; upstream
owns that middleware now, so the enterprise concern ships as a separate
middleware registered through the config-declared ``extensions.middlewares``
surface (zero-argument constructor, per that loader's contract).
"""

from __future__ import annotations

import logging
from typing import override

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

CODE_EVIDENCE_REMINDER_KEY = "code_evidence_reminder_package_id"


class CodeEvidenceContextMiddleware(AgentMiddleware):
    """Inject the trusted code-evidence package summary once per package."""

    @override
    def before_agent(self, state, runtime: Runtime) -> dict | None:
        context = getattr(runtime, "context", None) or {}
        manifest = context.get("code_evidence_manifest")
        package_id = context.get("code_package_id")
        if not isinstance(manifest, dict) or not isinstance(package_id, str) or not package_id:
            return None

        messages = list(state.get("messages", []))
        if not messages:
            return None
        # The reminder persists through checkpoints; skip when this exact
        # package was already announced (a new package id re-announces).
        if any(message.additional_kwargs.get(CODE_EVIDENCE_REMINDER_KEY) == package_id for message in messages):
            return None

        original_filename = str(manifest.get("original_filename", ""))
        accepted = manifest.get("accepted_count", 0)
        excluded = manifest.get("excluded_count", 0)
        rejected = manifest.get("rejected_count", 0)
        content = "\n".join(
            [
                "<code-evidence-package>",
                "服务端已安全展开代码包，可直接读取源码；不要要求用户本地解压。",
                f"源码根目录：/mnt/user-data/code-evidence/{package_id}/source",
                "read_file、grep 在全路径自动识别 UTF-8、UTF-8 BOM 和 GB18030（兼容 GBK）；原始 ZIP 仅作为不可直接读取的证据容器。",
                f"原始文件名：{original_filename}",
                f"已接收文件：{accepted} 个；已排除：{excluded} 项；已拒绝：{rejected} 项。",
                "C/C++ 可递归阅读并调用 analyze_code_evidence（clang-tidy、cppcheck）；"
                "Python 可调用同一工具运行固定 Ruff、Bandit 扫描；混合包同时运行两类扫描器。"
                "不得执行源码、安装依赖或传入自定义命令/参数；依据工具返回的 languages、"
                "scanner_status 披露覆盖范围、跳过项和不可用项，不能把未扫描说成无告警。",
                "</code-evidence-package>",
            ]
        )
        logger.debug("Injecting code-evidence package reminder for %s", package_id)
        return {
            "messages": [
                SystemMessage(
                    content=content,
                    additional_kwargs={"hide_from_ui": True, CODE_EVIDENCE_REMINDER_KEY: package_id},
                )
            ]
        }
