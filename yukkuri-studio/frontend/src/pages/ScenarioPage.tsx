import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ErrorBanner from "../components/ErrorBanner";
import CharacterPanel from "../features/scenario/CharacterPanel";
import DialogueList from "../features/scenario/DialogueList";
import { useScenario } from "../features/scenario/useScenario";

const PLACEHOLDER = "霊夢: こんにちは！\n魔理沙: 今日も実況していくぜ！\n# 「話者: セリフ」の形式で入力します";

export default function ScenarioPage() {
  const { projectId = "" } = useParams();
  const s = useScenario(projectId);
  const [text, setText] = useState("");

  // 初回読み込み時にだけ保存済みテキストを入力欄へ反映する
  useEffect(() => {
    if (s.script) setText((cur) => (cur === "" ? s.script!.raw_text : cur));
  }, [s.script]);

  async function parse() {
    let result = await s.parse(text, false);
    if (result === "conflict") {
      if (!window.confirm("手動で編集したセリフがあります。シナリオから作り直すと、それらは上書きされます。続けますか？")) return;
      result = await s.parse(text, true);
    }
  }

  if (s.loading) return <p>読み込み中…</p>;

  return (
    <section>
      <p>
        <Link to={`/projects/${projectId}/upload`}>← 動画アップロードに戻る</Link>
      </p>
      <h1>2. シナリオ入力・キャラクター設定</h1>
      <ErrorBanner message={s.error} onClose={s.clearError} />

      <div className="two-col">
        <div>
          <h2>シナリオ</h2>
          <textarea className="scenario-input" rows={10} value={text} placeholder={PLACEHOLDER} onChange={(e) => setText(e.target.value)} />
          <div className="row">
            <button disabled={s.busy} onClick={() => void s.saveScript(text)}>保存</button>
            <button className="primary" disabled={s.busy || !text.trim()} onClick={() => void parse()}>
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
          />
        </div>

        <div>
          <h2>キャラクター</h2>
          <CharacterPanel
            characters={s.characters}
            busy={s.busy}
            onAdd={(n) => void s.addCharacter(n)}
            onUpdate={(id, input) => void s.updateCharacter(id, input)}
            onDelete={(id) => void s.deleteCharacter(id)}
          />
        </div>
      </div>

      <div className="row end">
        <button className="primary" disabled title="AI生成はPhase 2以降で実装します">
          AI生成（未実装）
        </button>
      </div>
    </section>
  );
}
