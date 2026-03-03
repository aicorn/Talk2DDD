import uuid
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.conversation import Conversation, Message


class ConversationCRUD:
    async def get_by_id(self, db: AsyncSession, conversation_id: uuid.UUID) -> Optional[Conversation]:
        result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
        return result.scalar_one_or_none()

    async def get_by_user(self, db: AsyncSession, user_id: uuid.UUID) -> List[Conversation]:
        result = await db.execute(
            select(Conversation).where(Conversation.user_id == user_id)
        )
        return list(result.scalars().all())

    async def create(self, db: AsyncSession, conversation_data: dict) -> Conversation:
        conversation = Conversation(**conversation_data)
        db.add(conversation)
        await db.flush()
        await db.refresh(conversation)
        return conversation


class MessageCRUD:
    async def get_by_conversation(self, db: AsyncSession, conversation_id: uuid.UUID) -> List[Message]:
        result = await db.execute(
            select(Message).where(Message.conversation_id == conversation_id)
        )
        return list(result.scalars().all())

    async def create(self, db: AsyncSession, message_data: dict) -> Message:
        message = Message(**message_data)
        db.add(message)
        await db.flush()
        await db.refresh(message)
        return message
