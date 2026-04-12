"""ContextManager: loads and saves AgentContext from/to the database."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.agent.context import AgentContext
from app.models.conversation import Conversation


class ContextManager:
    """Persist and retrieve AgentContext using the Conversation.extra_data JSON column."""

    _KEY = "agent_context"

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
