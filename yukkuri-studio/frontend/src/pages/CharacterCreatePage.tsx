import { FormEvent, useState } from "react";
import ErrorBanner from "../components/ErrorBanner";
import CharacterEditor from "../features/characters/CharacterEditor";
import { useLibrary } from "../features/characters/useLibrary";
import JobPanel from "../features/jobs/JobPanel";

/** 画面4: キャラクター作成・管理(ログインユーザーごとのライブラリ)。 */
export default function CharacterCreatePage() {
  const lib = useLibrary();
  const [name, setName] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (await lib.create({ name: name.trim() })) setName("");
  }

  if (lib.loading) return <p>読み込み中…</p>;
  return (
    <section>
      <h1>キャラクター管理</h1>
      <div className="notice">
        ここで作ったキャラクターは、どのプロジェクトからも「追加」して使えます。
        <strong>プロジェクトに追加した時点の内容がコピーされる</strong>ため、ここでの編集は、
        すでにプロジェクトへ追加済みのキャラクターには反映されません（次に追加するときから反映されます）。
      </div>
      <ErrorBanner message={lib.error} onClose={lib.clearError} />
      <JobPanel jobs={lib.jobs} onRetry={(job) => void lib.retryJob(job)} onDismiss={lib.dismissFinishedJobs} />

      <form className="row" onSubmit={submit}>
        <input className="grow" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} placeholder="新しいキャラクターの名前（台本の [話者名] と同じにします）" />
        <button className="primary" disabled={lib.busy || !name.trim()}>作成</button>
      </form>

      {lib.characters.length === 0 && <p className="muted">キャラクターがいません。名前を入力して作成してください。</p>}
      <ul className="card-list">
        {lib.characters.map((c) => (
          <CharacterEditor
            key={c.id}
            character={c}
            busy={lib.busy}
            ops={lib.ops}
            header={<p className="muted small">{c.project_count > 0 ? `${c.project_count}件のプロジェクトで使用中` : "どのプロジェクトにも未追加"}</p>}
            onSave={(input) => void lib.update(c.id, input)}
            onDelete={() => void lib.remove(c.id)}
            deleteLabel="削除"
            deleteConfirm={`「${c.name}」を削除しますか？\nプロジェクトに追加済みのキャラクターは、そのまま残ります。`}
          />
        ))}
      </ul>
      <p className="muted small">現在の画像生成・音声生成はモック（仮の絵・仮の音）です。本物のAIへの差し替えは後の工程で行います。</p>
    </section>
  );
}
