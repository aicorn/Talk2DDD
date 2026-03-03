import uuid
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    domain_name: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    domain_name: Optional[str] = None
    status: Optional[str] = None


class ProjectResponse(ProjectBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocumentVersionBase(BaseModel):
    content: Optional[str] = None
    document_type: str = "requirements"


class DocumentVersionCreate(DocumentVersionBase):
    project_id: uuid.UUID
    version_number: int


class DocumentVersionResponse(DocumentVersionBase):
    id: uuid.UUID
    project_id: uuid.UUID
    version_number: int
    is_current: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
