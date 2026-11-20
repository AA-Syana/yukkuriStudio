from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..models import Project
from ..storage.local import LocalStorage


def get_storage() -> LocalStorage:
    return LocalStorage(settings.storage_dir)


def get_project_or_404(project_id: str, db: Session = Depends(get_db)) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "プロジェクトが見つかりません")
    return project
