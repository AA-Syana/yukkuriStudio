import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import ErrorBanner from "../components/ErrorBanner";
import JobPanel from "../features/jobs/JobPanel";
import DialogueList from "../features/script/DialogueList";
import ProjectCharacterPanel from "../features/script/ProjectCharacterPanel";
import { useScriptEditor } from "../features/script/useScriptEditor";

const PLACEHOLDER =
  "[霊夢]\nこんにちは！\n今日も実況していきます\n[魔理沙]\nよろしくな！\n\n# 「[話者名]」の次の行から、次の [話者名] までが、その話者のセリフ（1行=1セリフ）です\n# 「#」で始まる行はコメントです";

/** 画面5: 台本作成 + このプロジェクトで使うキャラクターの編集。 */
export default function ScriptCreatePage() {
  const { projectId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const s = useScriptEditor(projectId, params.get("script"));
  const [renaming, setRenaming] = useState<string | null>(null);

  async function parse() {
    let result = await s.parse(false);
    if (result === "conflict") {
      if (!window.confirm("手動で編集したセリフがあります。台本から作り直すと、それらは上書きされます。続けますか？")) return;
      result = await s.parse(true);
    }
  }

  if (s.loading) return <p>読み込み中…</p>;
  if (!s.project) return <ErrorBanner message={s.error ?? "プロジェクトが見つかりません"} />;

  return (
    <section>
      <p><Link to="/">← プロジェクト一覧</Link></p>
      <div className="row space-between">
        <h1>{s.project.title}：台本・キャラクター</h1>
        <Link to={`/projects/${projectId}/editor`} className="button primary">動画編集へ</Link>
      </div>
      <ErrorBanner message={s.error} onClose={s.clearError} />
      <JobPanel jobs={s.jobs} onRetry={(job) => void s.retryJob(job)} onDismiss={s.dismissFinishedJobs} />

      <div className="two-col">
        <div>
          <div className="tabs" role="tablist">
            {s.scripts.map((sc) => (
              <button
                key={sc.id}
                role="tab"
                aria-selected={sc.id === s.activeId}
                className={sc.id === s.activeId ? "tab active" : "tab"}
                disabled={s.busy}
                onClick={() => {
                  setParams({ script: sc.id }, { replace: true });
                  void s.selectScript(sc.id);
                }}
              >
                {sc.title || "（無題）"}
              </button>
            ))}
            <button className="tab" disabled={s.busy} onClick={() => void s.createScript()}>＋ 台本を追加</button>
          </div>

          {!s.active && <p className="muted">台本がありません。「＋ 台本を追加」から作成してください。</p>}
          {s.active && (
            <>
              <div className="row">
                <input
                  className="grow"
                  aria-label="台本のタイトル"
                  maxLength={100}
                  value={renaming ?? s.active.title}
                  onChange={(e) => setRenaming(e.target.value)}
                  onBlur={() => {
                    const next = renaming?.trim();
                    setRenaming(null);
                    if (next && next !== s.active?.title) void s.renameScript(next);
                  }}
                />
                <button
                  className="danger"
                  disabled={s.busy}
                  onClick={() =>
                    window.confirm(`台本「${s.active!.title}」を削除しますか？\nセリフと生成した音声も削除されます。`) && void s.deleteScript()
                  }
                >
                  この台本を削除
                </button>
              </div>

              <textarea
                className="scenario-input"
                rows={12}
                value={s.content}
                placeholder={PLACEHOLDER}
                onChange={(e) => s.setContent(e.target.value)}
              />
              <div className="row">
                <button disabled={s.busy || !s.dirty} onClick={() => void s.saveScript()}>
                  {s.dirty ? "保存" : "保存済み"}
                </button>
                <button className="primary" disabled={s.busy || !s.content.trim()} onClick={() => void parse()}>
                  セリフに分割
                </button>
              </div>

              <h2>セリフ一覧</h2>
              <DialogueList
                dialogues={s.dialogues}
                characters={s.characters}
                busy={s.busy}
                onUpdate={(id, patch) => void s.updateDialogue(id, patch)}
                onDelete={(id) => void s.deleteDialogue(id)}
                onAdd={(t, c) => void s.addDialogue(t, c)}
                onGroup={(ids) => void s.group(ids)}
                onUngroup={(ids) => void s.ungroup(ids)}
                onGenerateVoice={(id) => void s.generateVoice(id)}
                onGenerateAllVoices={() => void s.generateAllVoices()}
                onAnalyze={() => void s.analyze()}
                onLayout={(options) => void s.layout(options)}
                layoutWarnings={s.layoutWarnings}
              />
            </>
          )}
        </div>

        <div>
          <h2>このプロジェクトのキャラクター</h2>
          <ProjectCharacterPanel
            characters={s.characters}
            library={s.library}
            unknown={s.unknown}
            speakerless={s.speakerless}
            busy={s.busy}
            ops={s.characterOps}
            onAdd={(id) => void s.addFromLibrary(id)}
            onUpdate={(id, input) => void s.updateCharacter(id, input)}
            onRemove={(id) => void s.removeCharacter(id)}
          />
        </div>
      </div>
    </section>
  );
}
