import { Link } from "react-router-dom";
import { projectsApi } from "../api/projects";
import ErrorBanner from "../components/ErrorBanner";
import { useAsync } from "../hooks/useAsync";
import { useRunner } from "../hooks/useRunner";

/** 画面2: プロジェクト一覧・管理。 */
export default function ProjectListPage() {
  const projects = useAsync(() => projectsApi.list(), []);
  const { busy, error, clearError, run } = useRunner();

  async function remove(id: string, title: string) {
    const ok = window.confirm(
      `「${title}」を削除しますか？\n台本・セリフ・生成した音声と、このプロジェクト用のキャラクターが全て削除されます。\n（キャラクター管理のキャラクターは削除されません）`,
    );
    if (!ok) return;
    await run(() => projectsApi.remove(id));
    projects.reload(); // 失敗した場合もエラー表示のうえ、一覧を最新にする
  }

  return (
    <section>
      <div className="row space-between">
        <h1>プロジェクト</h1>
        <Link to="/projects/new" className="button primary">＋ 新規プロジェクト</Link>
      </div>
      <ErrorBanner message={projects.error ?? error} onClose={clearError} />
      {projects.loading && <p>読み込み中…</p>}
      {!projects.loading && projects.data?.length === 0 && (
        <p className="muted">プロジェクトがありません。「新規プロジェクト」から作成してください。</p>
      )}
      <ul className="card-list">
        {projects.data?.map((p) => (
          <li key={p.id} className="card">
            <div className="row space-between">
              <div>
                <h2 className="project-title">{p.title}</h2>
                {p.description && <p className="muted small">{p.description}</p>}
                <p className="muted small">
                  台本 {p.script_count}本 ／ キャラクター {p.character_count}人 ／ 更新 {new Date(p.updated_at).toLocaleString()}
                </p>
              </div>
              <div className="row">
                <Link to={`/projects/${p.id}/script`} className="button primary">台本・キャラクター</Link>
                <Link to={`/projects/${p.id}/editor`} className="button">動画編集</Link>
                <button className="danger" disabled={busy} onClick={() => void remove(p.id, p.title)}>削除</button>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
