"""ContextManager: loads and saves AgentContext from/to the database."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.agent.context import AgentContext
from app.models.conversation import Conversation, Message


class ContextManager:
    """Persist and retrieve AgentContext using the Conversation.extra_data JSON column."""

    _KEY = "agent_context"
    # Maximum number of recent messages to include in each AI call (keeps token usage bounded)
    MAX_HISTORY_MESSAGES = 40

    async def load(
        self,
        session_id: str,
        db: AsyncSession,
        project_id: Optional[str] = None,
    ) -> AgentContext:
        """Return the AgentContext for *session_id*, creating a fresh one if absent."""
        try:
            conv_uuid = uuid.UUID(session_id)
        except ValueError:
            return AgentContext(session_id=session_id, project_id=project_id)

        result = await db.execute(
            select(Conversation).where(Conversation.id == conv_uuid)
        )
        convo = result.scalar_one_or_none()

        if (
            convo is None
            or convo.extra_data is None
            or self._KEY not in convo.extra_data
        ):
            return AgentContext(session_id=session_id, project_id=project_id)

        ctx = AgentContext.model_validate(convo.extra_data[self._KEY])

        # Back-fill project_id if supplied and not already set
        if project_id and not ctx.project_id:
            ctx.project_id = project_id

        return ctx

    async def load_messages(
        self,
        session_id: str,
        db: AsyncSession,
    ) -> List[Dict[str, Any]]:
        """Return the recent conversation messages for *session_id* as OpenAI-style dicts.

        Returns an empty list if the conversation doesn't exist or has no messages.
        Only returns ``user`` and ``assistant`` roles (system messages are excluded
        because the caller constructs the system prompt separately).
        """
        try:
            conv_uuid = uuid.UUID(session_id)
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

        history = [
            {"role": msg.role, "content": msg.content}
            for msg in convo.messages
            if msg.role in ("user", "assistant")
        ]
        # Trim to most-recent N messages to keep token usage bounded
        return history[-self.MAX_HISTORY_MESSAGES :]

    async def save(self, ctx: AgentContext, db: AsyncSession) -> None:
        """Persist *ctx* back into the Conversation record."""
        try:
            conv_uuid = uuid.UUID(ctx.session_id)
        except ValueError:
            return

        result = await db.execute(
            select(Conversation).where(Conversation.id == conv_uuid)
        )
        convo = result.scalar_one_or_none()
        if convo is None:
            return

        extra = dict(convo.extra_data) if convo.extra_data else {}
        extra[self._KEY] = ctx.model_dump(mode="json")
        convo.extra_data = extra
        flag_modified(convo, "extra_data")
        await db.flush()

    async def append_messages(
        self,
        session_id: str,
        user_message: str,
        assistant_reply: str,
        db: AsyncSession,
    ) -> None:
        """Persist a user + assistant message pair to the Message table."""
        try:
            conv_uuid = uuid.UUID(session_id)
        except ValueError:
            return

        db.add(
            Message(
                conversation_id=conv_uuid,
                role="user",
                content=user_message,
            )
        )
        db.add(
            Message(
                conversation_id=conv_uuid,
                role="assistant",
                content=assistant_reply,
            )
        )
        await db.flush()
