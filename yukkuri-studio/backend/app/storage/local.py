"""ローカルディスクへのファイル保存。将来S3等に差し替えるため、呼び出し側はこのクラスの
メソッドだけに依存する。DBには storage root からの相対パスだけを保存する。"""
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO


class FileTooLarge(Exception):
    pass


class LocalStorage:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def absolute(self, rel_path: str) -> Path:
        path = (self.root / rel_path).resolve()
        if not path.is_relative_to(self.root):  # パストラバーサル対策
            raise ValueError("invalid storage path")
        return path

    def save_upload(
        self, project_id: str, category: str, ext: str, fileobj: BinaryIO, max_bytes: int
    ) -> str:
        """チャンク単位で保存する(大容量動画でもメモリを使い切らない)。保存先の相対パスを返す。"""
        rel = f"{project_id}/{category}/{uuid.uuid4().hex}{ext}"
        dest = self.absolute(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        try:
            with open(dest, "wb") as out:
                while chunk := fileobj.read(1024 * 1024):
                    written += len(chunk)
                    if written > max_bytes:
                        raise FileTooLarge()
                    out.write(chunk)
        except BaseException:
            dest.unlink(missing_ok=True)
            raise
        return rel

    def delete(self, rel_path: str) -> None:
        self.absolute(rel_path).unlink(missing_ok=True)

    def delete_project(self, project_id: str) -> None:
        shutil.rmtree(self.absolute(project_id), ignore_errors=True)
