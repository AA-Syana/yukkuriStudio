"""生成・アップロードされたファイル(音声・画像)の配信と、キャラクター画像の登録・削除。"""
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..constants import EMOTIONS, MAX_IMAGE_UPLOAD_BYTES, UPLOAD_IMAGE_EXTENSIONS
from ..core.database import get_db
from ..models import Asset, Character
from ..schemas import CharacterOut
from ..services.character_service import storage_prefix
from ..services.generation import replace_character_image
from ..storage.local import FileTooLarge, LocalStorage
from .deps import get_asset_or_404, get_character_or_404, get_storage

router = APIRouter(tags=["assets"])

MEDIA_TYPES = {
    ".wav": "audio/wav", ".mp3": "audio/mpeg",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".svg": "image/svg+xml",
}
# 配信するファイルがブラウザ上でスクリプトとして動かないようにする(SVG対策)
SAFE_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "private, max-age=3600",  # 再生成するとasset_id(=URL)が変わるのでキャッシュしてよい
}


@router.get("/api/assets/{asset_id}/file")
def get_asset_file(asset: Asset = Depends(get_asset_or_404), storage: LocalStorage = Depends(get_storage)):
    if not asset.file_path:
        raise HTTPException(404, "ファイルが見つかりません")
    path = storage.absolute(asset.file_path)
    if not path.exists():
        raise HTTPException(404, "ファイルが見つかりません")
    media_type = MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type, headers=SAFE_HEADERS)


def _looks_like_image(head: bytes, ext: str) -> bool:
    """拡張子だけでなく、先頭バイトで実際に画像かを確認する。"""
    if ext == ".png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in (".jpg", ".jpeg"):
        return head.startswith(b"\xff\xd8\xff")
    if ext == ".webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    return False


@router.post("/api/characters/{character_id}/images/upload", response_model=CharacterOut, status_code=201)
def upload_character_image(
    expression: str = Form(...),
    file: UploadFile = File(...),
    character: Character = Depends(get_character_or_404),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage),
):
    """自分で用意した画像を、表情を指定して登録する(ライブラリでもプロジェクトのコピーでも可)。"""
    if expression not in EMOTIONS:
        raise HTTPException(422, f"表情は {', '.join(EMOTIONS)} のいずれかを指定してください")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in UPLOAD_IMAGE_EXTENSIONS:
        raise HTTPException(415, "PNG / JPEG / WebP の画像のみアップロードできます")
    try:
        rel_path = storage.save_upload(storage_prefix(character), "images", ext, file.file, MAX_IMAGE_UPLOAD_BYTES)
    except FileTooLarge:
        raise HTTPException(413, "画像のサイズが上限(10MB)を超えています")
    with open(storage.absolute(rel_path), "rb") as f:
        head = f.read(12)
    if not _looks_like_image(head, ext):
        storage.delete(rel_path)
        raise HTTPException(422, "画像ファイルとして読み込めません")
    replace_character_image(
        db, storage, character, expression, rel_path, {"source": "uploaded", "original_filename": file.filename}
    )
    db.refresh(character)
    return character


@router.delete("/api/characters/{character_id}/images/{expression}", status_code=204)
def delete_character_image(
    expression: str,
    character: Character = Depends(get_character_or_404),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage),
):
    asset = next((a for a in character.assets if a.asset_type == "image" and a.meta.get("expression") == expression), None)
    if asset is None:
        raise HTTPException(404, "その表情の画像は登録されていません")
    path = asset.file_path
    db.delete(asset)
    db.commit()
    if path:
        storage.delete(path)
