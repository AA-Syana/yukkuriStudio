"""テスト共通の補助関数。"""

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"0" * 32


def library_character(client, name="霊夢", **extra):
    res = client.post("/api/characters", json={"name": name, "appearance": "赤いリボンの巫女", **extra})
    assert res.status_code == 201, res.text
    return res.json()


def add_to_project(client, pid, library_id):
    res = client.post(f"/api/projects/{pid}/characters", json={"source_character_id": library_id})
    assert res.status_code in (200, 201), res.text
    return res.json()


def project_character(client, pid, name="霊夢", **extra):
    """ライブラリに作って、プロジェクトに追加する(=プロジェクト用のコピーを返す)。"""
    return add_to_project(client, pid, library_character(client, name, **extra)["id"])


def parse(client, script_id, text, **body):
    """台本を保存して、セリフに分割する。レスポンス全体(dialogues / unknown_speakers ...)を返す。"""
    assert client.put(f"/api/scripts/{script_id}", json={"content": text}).status_code == 200
    res = client.post(f"/api/scripts/{script_id}/parse", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def dialogues(client, script_id):
    return client.get(f"/api/scripts/{script_id}/dialogues").json()


def job(client, job_id):
    return client.get(f"/api/generation-jobs/{job_id}").json()


def images_of(client, character):
    """キャラクターの画像を {表情: 画像情報} で返す。"""
    if character.get("project_id"):
        chars = client.get(f"/api/projects/{character['project_id']}/characters").json()
    else:
        chars = client.get("/api/characters").json()
    return {i["expression"]: i for i in next(c for c in chars if c["id"] == character["id"])["images"]}
