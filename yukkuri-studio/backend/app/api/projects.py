from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models import Project, Script
from ..schemas import ProjectCreate, ProjectOut, ProjectUpdate
from ..storage.local import LocalStorage
from .deps import get_project_or_404, get_storage

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=body.name)
    project.script = Script(raw_text="")  # 1プロジェクト=1シナリオ。作成時に空で用意する
    db.add(project)
    db.commit()
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.scalars(select(Project).order_by(Project.updated_at.desc())).all()


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project: Project = Depends(get_project_or_404)):
    return project


@router.patch("/{project_id}", response_model=ProjectOut)
def rename_project(
    body: ProjectUpdate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    project.name = body.name
    db.commit()
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage),
):
    project_id = project.id
    db.delete(project)
    db.commit()
    storage.delete_project(project_id)  # DB削除が成功してからファイルを消す
