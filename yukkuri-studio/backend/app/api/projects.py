from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.database import get_db
from ..models import Project, Script, User
from ..schemas import ProjectCreate, ProjectOut, ProjectUpdate
from ..storage.local import LocalStorage
from .deps import get_current_user, get_project_or_404, get_storage

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = Project(user_id=user.id, title=body.title, description=body.description)
    project.scripts.append(Script(title="台本1", content=""))  # 作成直後から台本を書き始められるよう、空の台本を1つ用意する
    db.add(project)
    db.commit()
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(Project)
        .where(Project.user_id == user.id)
        .options(selectinload(Project.scripts))
        .order_by(Project.updated_at.desc())
    ).all()


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project: Project = Depends(get_project_or_404)):
    return project


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(body: ProjectUpdate, project: Project = Depends(get_project_or_404), db: Session = Depends(get_db)):
    for key, value in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(project, key, value)
    db.commit()
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage),
):
    """台本・セリフ・このプロジェクト用のキャラクター(コピー)・ジョブ・動画をまとめて削除する。
    ライブラリのキャラクターは消えない。"""
    project_id = project.id
    db.delete(project)
    db.commit()
    storage.delete_tree(project_id)  # DB削除が成功してからファイルを消す(コピーした画像もこの配下にある)
