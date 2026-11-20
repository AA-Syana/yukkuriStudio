import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { messageOf } from "../api/client";
import { projectsApi } from "../api/projects";
import ErrorBanner from "../components/ErrorBanner";
import { useAsync } from "../hooks/useAsync";

export default function ProjectListPage() {
  const navigate = useNavigate();
  const { data: projects, loading, error, reload } = useAsync(projectsApi.list, []);
  const [name, setName] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function guard(fn: () => Promise<void>) {
    setActionError(null);
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setActionError(messageOf(e));
    } finally {
      setBusy(false);
    }
  }

  const create = (e: FormEvent) => {
    e.preventDefault();
    void guard(async () => {
      const project = await projectsApi.create(name);
      navigate(`/projects/${project.id}/upload`);
    });
  };

  const rename = (id: string, current: string) => {
    const next = window.prompt("新しいプロジェクト名", current)?.trim();
    if (!next || next === current) return;
    void guard(async () => {
      await projectsApi.rename(id, next);
      reload();
    });
  };

  const remove = (id: string, projectName: string) => {
    if (!window.confirm(`「${projectName}」を削除しますか？動画やシナリオも全て削除されます。`)) return;
    void guard(async () => {
      await projectsApi.remove(id);
      reload();
    });
  };

  return (
    <section>
      <h1>プロジェクト一覧</h1>
      <form className="row" onSubmit={create}>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="新しいプロジェクト名"
          maxLength={200}
          aria-label="プロジェクト名"
        />
        <button className="primary" disabled={busy || !name.trim()}>
          新規作成
        </button>
      </form>
      <ErrorBanner message={actionError} onClose={() => setActionError(null)} />
      <ErrorBanner message={error} />
      {loading && <p>読み込み中…</p>}
      {projects && projects.length === 0 && <p className="muted">プロジェクトはまだありません。</p>}
      <ul className="card-list">
        {projects?.map((p) => (
          <li key={p.id} className="card row space-between">
            <div>
              <Link to={`/projects/${p.id}/upload`}>{p.name}</Link>
              <div className="muted small">更新: {new Date(p.updated_at).toLocaleString()}</div>
            </div>
            <div className="row">
              <button onClick={() => rename(p.id, p.name)} disabled={busy}>
                名前変更
              </button>
              <button className="danger" onClick={() => remove(p.id, p.name)} disabled={busy}>
                削除
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
