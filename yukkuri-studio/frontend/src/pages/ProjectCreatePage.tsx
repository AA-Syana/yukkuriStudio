import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { projectsApi } from "../api/projects";
import ErrorBanner from "../components/ErrorBanner";
import { useRunner } from "../hooks/useRunner";

/** 画面3: プロジェクト作成。 */
export default function ProjectCreatePage() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const { busy, error, clearError, run } = useRunner();

  async function submit(e: FormEvent) {
    e.preventDefault();
    const project = await run(() => projectsApi.create(title.trim(), description.trim()));
    if (project) navigate(`/projects/${project.id}/script`);
  }

  return (
    <section>
      <p><Link to="/">← プロジェクト一覧</Link></p>
      <h1>プロジェクトを作成</h1>
      <ErrorBanner message={error} onClose={clearError} />
      <form onSubmit={submit} className="card">
        <label className="field">
          プロジェクト名
          <input value={title} maxLength={100} required autoFocus onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label className="field">
          説明（任意）
          <textarea rows={3} maxLength={2000} value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <div className="row end">
          <button className="primary" disabled={busy || !title.trim()}>作成して台本へ</button>
        </div>
      </form>
    </section>
  );
}
