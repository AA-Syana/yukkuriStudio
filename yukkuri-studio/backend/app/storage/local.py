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
        self, prefix: str, category: str, ext: str, fileobj: BinaryIO, max_bytes: int
    ) -> str:
        """チャンク単位で保存する(大容量動画でもメモリを使い切らない)。保存先の相対パスを返す。"""
        rel = f"{prefix}/{category}/{uuid.uuid4().hex}{ext}"
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

    def save_bytes(self, prefix: str, category: str, ext: str, data: bytes) -> str:
        """生成した音声・画像など、メモリ上のデータを保存する。"""
        rel = f"{prefix}/{category}/{uuid.uuid4().hex}{ext}"
        dest = self.absolute(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return rel

    def adopt_file(self, prefix: str, category: str, ext: str, src: Path) -> str:
        """作業用フォルダで作ったファイルを、保存場所へ移す(大きなMP4をメモリに載せないため)。"""
        rel = f"{prefix}/{category}/{uuid.uuid4().hex}{ext}"
        dest = self.absolute(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        return rel

    def delete(self, rel_path: str) -> None:
        self.absolute(rel_path).unlink(missing_ok=True)

    def delete_tree(self, prefix: str) -> None:
        """prefix 以下のファイルをまとめて削除する(プロジェクト単位・キャラクター単位の掃除に使う)。"""
        shutil.rmtree(self.absolute(prefix), ignore_errors=True)

    def copy_file(self, src_rel_path: str, prefix: str, category: str) -> str:
        """既存のファイルを別の場所へ複製する(ライブラリの画像を、プロジェクト用のコピーへ渡すときに使う)。"""
        src = self.absolute(src_rel_path)
        rel = f"{prefix}/{category}/{uuid.uuid4().hex}{src.suffix}"
        dest = self.absolute(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        return rel
