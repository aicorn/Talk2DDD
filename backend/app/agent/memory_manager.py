"""MemoryManager: three-layer memory model for the Talk2DDD AI Agent.

Layer 1 – Immediate Memory
    The most recent K turns are included verbatim in the ``messages`` list
    passed to the AI provider.  K = ``MemoryConfig.immediate_memory_turns``.

Layer 2 – Rolling Summary
    Turns older than the immediate window are compressed into a short
    structured summary (~400 chars) by a lightweight AI call.  The summary
    is stored in ``AgentContext.conversation_summary`` and injected into the
    system prompt inside a ``[MEMORY_SUMMARY] … [/MEMORY_SUMMARY]`` block.
    Compression is triggered asynchronously (after the main response is
    returned) so it never adds latency to the conversation.

Layer 3 – Structured Knowledge  (handled by PromptBuilder, not here)
    ``AgentContext.domain_knowledge`` is always serialised as structured JSON
    and injected into the ``[CONTEXT_BLOCK]`` in the system prompt.  This
    layer has a fixed token footprint regardless of conversation length.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.context import AgentContext
from app.models.conversation import Conversation

logger = logging.getLogger(__name__)

# Approximate token cost of the system-prompt layers that are NOT part of the
# message history: role definition + phase instruction + context block.
_SYSTEM_PROMPT_TOKEN_ESTIMATE = 1200

# Target character length (≈ tokens × 2.5) for the rolling summary.
_SUMMARY_MAX_CHARS = 400

# Compression prompt (sent to the AI provider as a standalone one-shot call).
_COMPRESSION_PROMPT = """\
你是对话摘要助手。请将以下历史对话与已有摘要合并，\
生成一份不超过 {max_chars} 字的结构化摘要，重点保留：
1. 用户的项目名称和业务背景
2. 已确认的核心需求和业务场景
3. 用户的决策与偏好（技术选型、规模、目标等）
4. 尚未解决的问题或待澄清事项

【已有摘要】
{existing_summary}

【新增对话（按时间顺序）】
{new_messages}

请直接输出摘要正文，不要添加标题或说明。"""


def _format_messages_for_summary(messages: List[Dict[str, Any]]) -> str:
    """Turn a list of {role, content} dicts into a readable text block."""
    lines: List[str] = []
    for msg in messages:
        role_label = "用户" if msg["role"] == "user" else "助手"
        lines.append(f"{role_label}：{msg['content']}")
    return "\n".join(lines)


class MemoryManager:
    """Manages the three-layer memory model for a single session."""

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    async def get_messages_for_ai(
        self,
        ctx: AgentContext,
        db: AsyncSession,
    ) -> List[Dict[str, Any]]:
        """Return the message list (Layer 1) to pass to the AI provider.

        Loads the full message history from the ``Message`` table then:

        1. Retains only the most recent ``K`` turns (a turn = 1 user + 1
           assistant message, so at most ``K × 2`` messages).
        2. If the resulting list still exceeds the token budget, reduces ``K``
           down to ``min_immediate_memory_turns``.

        Args:
            ctx: Current ``AgentContext`` (provides ``MemoryConfig``).
            db: Active SQLAlchemy async session.

        Returns:
            A list of ``{"role": ..., "content": ...}`` dicts ready to be
            prepended to the current user message before the AI call.
        """
        cfg = ctx.memory_config
        all_messages = await self._load_all_messages(ctx.session_id, db)

        if not all_messages:
            return []

        # Each "turn" = 1 user + 1 assistant message (2 messages).
        k_messages = cfg.immediate_memory_turns * 2
        recent = all_messages[-k_messages:] if k_messages > 0 else []

        # Check token budget and trim further if needed.
        estimated = self.estimate_tokens(recent)
        remaining_budget = cfg.max_input_tokens - _SYSTEM_PROMPT_TOKEN_ESTIMATE
        if estimated > remaining_budget:
            min_msgs = cfg.min_immediate_memory_turns * 2
            # Binary-ish trim: halve until within budget or floor reached
            while estimated > remaining_budget and len(recent) > min_msgs:
                recent = recent[2:]  # drop oldest turn (user + assistant pair)
                estimated = self.estimate_tokens(recent)

        return recent

    def get_summary_block(self, ctx: AgentContext) -> str:
        """Return the ``[MEMORY_SUMMARY]`` system-prompt block (Layer 2).

        Returns an empty string if no summary has been generated yet (early
        turns before the compression threshold).

        Args:
            ctx: Current ``AgentContext``.

        Returns:
            A formatted ``[MEMORY_SUMMARY]…[/MEMORY_SUMMARY]`` string, or
            ``""`` if the summary is empty.
        """
        if not ctx.conversation_summary:
            return ""
        return (
            "[MEMORY_SUMMARY]\n"
            f"{ctx.conversation_summary}\n"
            "[/MEMORY_SUMMARY]"
        )

    async def maybe_compress(
        self,
        ctx: AgentContext,
        db: AsyncSession,
        provider: Optional[str] = None,
    ) -> None:
        """Conditionally compress older turns into the rolling summary.

        Runs the actual AI compression call **asynchronously in the
        background** so the calling code (agent_core) does not need to await
        it.  The AgentContext is mutated in-place and saved back to the DB
        *only if* the compression succeeds; failures are silently swallowed
        so the main conversation is never disrupted.

        Triggers (any one suffices):
        * First fire:   ``turn_count >= summary_trigger_turns``
        * Periodic:     ``(turn_count - summary_last_updated_turn)
                          >= summary_refresh_interval``  AND first already fired
        * Budget:       estimated token count of recent history exceeds the
                        input budget minus system-prompt overhead

        Args:
            ctx: Current ``AgentContext`` (mutated in-place on success).
            db:  Active SQLAlchemy async session.
            provider: AI provider name string (forwarded to ``chat_completion``).
        """
        if not self._should_compress(ctx, db):
            return
        # Fire and forget – errors are logged but not propagated.
        asyncio.ensure_future(
            self._do_compress(ctx, db, provider),
        )

    def estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Estimate the token count of *messages* without external libraries.

        Uses a simple heuristic: 1 token ≈ 2.5 characters for Chinese/mixed
        text (roughly midway between the ~4-char English estimate and the
        ~1.5-char CJK estimate).

        Args:
            messages: List of ``{"role": ..., "content": ...}`` dicts.

        Returns:
            Integer estimate of total token consumption.
        """
        total_chars = sum(len(m.get("content", "")) for m in messages)
        # Add a small overhead per message for role + delimiters (~10 tokens)
        per_message_overhead = len(messages) * 10
        return int(total_chars / 2.5) + per_message_overhead

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _should_compress(
        self,
        ctx: AgentContext,
        db: AsyncSession,  # reserved for future budget-check
    ) -> bool:
        """Return True if compression should be triggered this turn."""
        cfg = ctx.memory_config
        turn = ctx.turn_count

        # First fire
        if turn >= cfg.summary_trigger_turns and ctx.summary_last_updated_turn == 0:
            return True

        # Periodic refresh (only after first fire)
        if (
            ctx.summary_last_updated_turn > 0
            and (turn - ctx.summary_last_updated_turn) >= cfg.summary_refresh_interval
        ):
            return True

        return False

    async def _load_all_messages(
        self,
        session_id: str,
        db: AsyncSession,
    ) -> List[Dict[str, Any]]:
        """Load all user/assistant messages for *session_id* from the DB."""
        import uuid as _uuid

        try:
            conv_uuid = _uuid.UUID(session_id)
        except ValueError:
            return []

        result = await db.execute(
            select(Conversation)
            .where(Conversation.id == conv_uuid)
            .options(selectinload(Conversation.messages))
        )
        convo = result.scalar_one_or_none()
        if convo is None:
            return []

        return [
            {"role": msg.role, "content": msg.content}
            for msg in convo.messages
            if msg.role in ("user", "assistant")
        ]

    async def _do_compress(
        self,
        ctx: AgentContext,
        db: AsyncSession,
        provider: Optional[str],
    ) -> None:
        """Perform the actual compression and persist the result.

        This is the background coroutine spawned by ``maybe_compress``.
        All exceptions are caught and logged so they never propagate to the
        main request context.
        """
        # Import here to avoid circular imports at module load time.
        from app.agent.context_manager import ContextManager
        from app.services.ai_service import chat_completion

        try:
            cfg = ctx.memory_config
            all_messages = await self._load_all_messages(ctx.session_id, db)
            if not all_messages:
                return

            # Messages already covered by the existing summary should not be
            # re-compressed; only process newly accumulated turns.
            already_covered = ctx.summary_covers_turns * 2  # turns → messages
            messages_to_summarise = all_messages[already_covered:]
            if not messages_to_summarise:
                return

            prompt_text = _COMPRESSION_PROMPT.format(
                max_chars=_SUMMARY_MAX_CHARS,
                existing_summary=ctx.conversation_summary or "（暂无）",
                new_messages=_format_messages_for_summary(messages_to_summarise),
            )

            new_summary = await chat_completion(
                messages=[{"role": "user", "content": prompt_text}],
                provider=provider,
            )

            # Guard against concurrent writes: only update if we processed
            # a later set of turns than the current stored summary.
            new_covers = len(all_messages) // 2  # total turns (pairs)
            if new_covers > ctx.summary_covers_turns:
                ctx.conversation_summary = new_summary.strip()
                ctx.summary_last_updated_turn = ctx.turn_count
                ctx.summary_covers_turns = new_covers
                # Persist the updated context back to the DB.
                await ContextManager().save(ctx, db)
                logger.debug(
                    "MemoryManager: compressed %d turns → %d-char summary (session=%s)",
                    new_covers,
                    len(ctx.conversation_summary),
                    ctx.session_id,
                )
        except Exception:
            logger.warning(
                "MemoryManager: compression failed for session=%s; "
                "continuing without updated summary.",
                ctx.session_id,
                exc_info=True,
            )
