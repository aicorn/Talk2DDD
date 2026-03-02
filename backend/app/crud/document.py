import uuid
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.document import Project, DocumentVersion
from app.schemas.document import ProjectCreate, ProjectUpdate, DocumentVersionCreate


class ProjectCRUD:
    async def get_by_id(self, db: AsyncSession, project_id: uuid.UUID) -> Optional[Project]:
        result = await db.execute(select(Project).where(Project.id == project_id))
        return result.scalar_one_or_none()

    async def get_by_owner(self, db: AsyncSession, owner_id: uuid.UUID) -> List[Project]:
        result = await db.execute(select(Project).where(Project.owner_id == owner_id))
        return list(result.scalars().all())

    async def create(self, db: AsyncSession, project_in: ProjectCreate, owner_id: uuid.UUID) -> Project:
        project = Project(
            name=project_in.name,
            description=project_in.description,
            domain_name=project_in.domain_name,
            owner_id=owner_id,
        )
        db.add(project)
        await db.flush()
        await db.refresh(project)
        return project

    async def update(self, db: AsyncSession, project: Project, project_in: ProjectUpdate) -> Project:
        update_data = project_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(project, field, value)
        db.add(project)
        await db.flush()
        await db.refresh(project)
        return project

    async def delete(self, db: AsyncSession, project_id: uuid.UUID) -> bool:
        project = await self.get_by_id(db, project_id)
        if not project:
            return False
        await db.delete(project)
        await db.flush()
        return True


class DocumentVersionCRUD:
    async def get_by_id(self, db: AsyncSession, version_id: uuid.UUID) -> Optional[DocumentVersion]:
        result = await db.execute(select(DocumentVersion).where(DocumentVersion.id == version_id))
        return result.scalar_one_or_none()

    async def get_by_project(self, db: AsyncSession, project_id: uuid.UUID) -> List[DocumentVersion]:
        result = await db.execute(
            select(DocumentVersion).where(DocumentVersion.project_id == project_id)
        )
        return list(result.scalars().all())

    async def create(self, db: AsyncSession, version_in: DocumentVersionCreate) -> DocumentVersion:
        version = DocumentVersion(
            project_id=version_in.project_id,
            version_number=version_in.version_number,
            content=version_in.content,
            document_type=version_in.document_type,
        )
        db.add(version)
        await db.flush()
        await db.refresh(version)
        return version
