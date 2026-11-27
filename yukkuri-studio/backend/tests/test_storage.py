import io

import pytest

from app.storage.local import FileTooLarge, LocalStorage


def test_save_copy_and_delete_tree(tmp_path):
    s = LocalStorage(tmp_path)
    original = s.save_bytes("characters/c1", "images", ".png", b"data")
    copied = s.copy_file(original, "p1/characters/c2", "images")
    assert copied != original and copied.startswith("p1/characters/c2/images/") and copied.endswith(".png")
    assert s.absolute(copied).read_bytes() == b"data"

    s.delete_tree("p1")
    assert not s.absolute("p1").exists()
    assert s.absolute(original).exists()  # コピー先を消しても元は残る
    s.delete_tree("does/not/exist")  # 存在しない場所を消してもエラーにならない


def test_upload_too_large_leaves_no_file(tmp_path):
    s = LocalStorage(tmp_path)
    with pytest.raises(FileTooLarge):
        s.save_upload("p", "videos", ".mp4", io.BytesIO(b"x" * 10), max_bytes=5)
    assert list(tmp_path.rglob("*.mp4")) == []


def test_path_traversal_is_rejected(tmp_path):
    s = LocalStorage(tmp_path / "root")
    with pytest.raises(ValueError):
        s.absolute("../outside")
    with pytest.raises(ValueError):
        s.delete_tree("../outside")


def test_adopt_file_moves_a_file_into_storage(tmp_path):
    s = LocalStorage(tmp_path / "root")
    src = tmp_path / "work" / "out.mp4"
    src.parent.mkdir()
    src.write_bytes(b"mp4data")
    rel = s.adopt_file("p1", "renders", ".mp4", src)
    assert rel.startswith("p1/renders/") and rel.endswith(".mp4")
    assert s.absolute(rel).read_bytes() == b"mp4data" and not src.exists()
