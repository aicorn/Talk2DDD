import uuid
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.step import Step, AISuggestion


class StepCRUD:
    async def get_by_id(self, db: AsyncSession, step_id: uuid.UUID) -> Optional[Step]:
        result = await db.execute(select(Step).where(Step.id == step_id))
        return result.scalar_one_or_none()

    async def get_by_project(self, db: AsyncSession, project_id: uuid.UUID) -> List[Step]:
        result = await db.execute(
            select(Step).where(Step.project_id == project_id).order_by(Step.order_index)
        )
        return list(result.scalars().all())

    async def create(self, db: AsyncSession, step_data: dict) -> Step:
        step = Step(**step_data)
        db.add(step)
        await db.flush()
        await db.refresh(step)
        return step

    async def update_status(self, db: AsyncSession, step_id: uuid.UUID, status: str) -> Optional[Step]:
        step = await self.get_by_id(db, step_id)
        if not step:
            return None
        step.status = status
        db.add(step)
        await db.flush()
        await db.refresh(step)
        return step


class AISuggestionCRUD:
    async def get_by_step(self, db: AsyncSession, step_id: uuid.UUID) -> List[AISuggestion]:
        result = await db.execute(select(AISuggestion).where(AISuggestion.step_id == step_id))
        return list(result.scalars().all())

    async def create(self, db: AsyncSession, suggestion_data: dict) -> AISuggestion:
        suggestion = AISuggestion(**suggestion_data)
        db.add(suggestion)
        await db.flush()
        await db.refresh(suggestion)
        return suggestion
