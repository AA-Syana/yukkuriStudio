def test_project_crud(client):
    res = client.post("/api/projects", json={"name": "  実況1  "})
    assert res.status_code == 201
    pid = res.json()["id"]
    assert res.json()["name"] == "実況1"  # 前後の空白は除去される

    assert [p["id"] for p in client.get("/api/projects").json()] == [pid]
    assert client.patch(f"/api/projects/{pid}", json={"name": "改名"}).json()["name"] == "改名"
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_project_name_validation(client):
    assert client.post("/api/projects", json={"name": "   "}).status_code == 422
    assert client.post("/api/projects", json={}).status_code == 422
