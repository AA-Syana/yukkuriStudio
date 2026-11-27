import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { generationApi } from "../../api/generation";
import {
  APPEARANCE_FIELDS, EMOTIONS, EMOTION_LABELS,
  type AppearanceKey, type Character, type CharacterInput, type Emotion,
} from "../../types";
import type { CharacterOps } from "./characterOps";

// 編集対象のフィールドだけを取り出す(id等を除く)
const toInput = (c: Character): CharacterInput => ({
  name: c.name,
  description: c.description,
  personality: c.personality,
  appearance: c.appearance,
  appearance_details: c.appearance_details ?? {},
  speaking_style: c.speaking_style,
  voice_settings: c.voice_settings ?? {},
});

/** 表情ごとの画像スロット。生成・アップロード・削除ができる。 */
function ExpressionImages({ character, busy, ops }: { character: Character; busy: boolean; ops: CharacterOps }) {
  const byExpression = new Map(character.images.map((i) => [i.expression, i]));
  return (
    <div>
      <div className="row space-between">
        <strong className="small">立ち絵・表情差分</strong>
        <button
          disabled={busy}
          onClick={() => void ops.generateImage(character.id, null)}
          title="保存済みの外見設定をもとに、全表情を生成します"
        >
          全表情を生成
        </button>
      </div>
      <div className="expression-grid">
        {EMOTIONS.map((expression) => {
          const image = byExpression.get(expression);
          return (
            <div key={expression} className="expression-slot">
              <div className="expression-thumb">
                {image ? (
                  <img src={generationApi.assetUrl(image.asset_id)} alt={`${character.name}（${EMOTION_LABELS[expression]}）`} />
                ) : (
                  <span className="muted small">未登録</span>
                )}
              </div>
              <div className="small">{EMOTION_LABELS[expression]}</div>
              <div className="slot-buttons">
                <button disabled={busy} onClick={() => void ops.generateImage(character.id, expression)}>生成</button>
                <label className={`button ${busy ? "disabled" : ""}`}>
                  取込
                  <input
                    type="file"
                    accept=".png,.jpg,.jpeg,.webp"
                    hidden
                    disabled={busy}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) void ops.uploadImage(character.id, expression as Emotion, file);
                      e.target.value = "";
                    }}
                  />
                </label>
                {image && (
                  <button className="danger" disabled={busy} onClick={() => void ops.deleteImage(character.id, expression)}>
                    削除
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

interface Props {
  character: Character;
  busy: boolean;
  ops: CharacterOps;
  onSave: (input: CharacterInput) => void;
  onDelete: () => void;
  deleteLabel: string;
  deleteConfirm: string;
  header?: ReactNode; // 名前の上に出す補足(「このプロジェクト用のコピー」など)
}

/** キャラクターの編集フォーム。ライブラリ(管理画面)とプロジェクト用のコピー(編集画面)の両方で使う。 */
export default function CharacterEditor({ character, busy, ops, onSave, onDelete, deleteLabel, deleteConfirm, header }: Props) {
  const [draft, setDraft] = useState<CharacterInput>(toInput(character));
  // 画像の更新などでキャラクターが再取得されても、編集中の入力は消さない(保存済みの内容が変わったときだけ反映する)
  const savedKey = JSON.stringify(toInput(character));
  useEffect(() => setDraft(JSON.parse(savedKey)), [savedKey]);

  const set = <K extends keyof CharacterInput>(key: K, value: CharacterInput[K]) => setDraft((d) => ({ ...d, [key]: value }));
  const setDetail = (key: AppearanceKey, value: string) =>
    set("appearance_details", { ...draft.appearance_details, [key]: value });
  const setVoice = (key: "pitch" | "speed", raw: string) =>
    set("voice_settings", { ...draft.voice_settings, [key]: raw === "" ? undefined : Number(raw) });

  const dirty = JSON.stringify(draft) !== savedKey;

  return (
    <li className="card">
      {header}
      <label className="field">名前<input value={draft.name} maxLength={100} onChange={(e) => set("name", e.target.value)} /></label>
      <label className="field">説明<textarea rows={2} value={draft.description} onChange={(e) => set("description", e.target.value)} /></label>
      <label className="field">性格<textarea rows={2} value={draft.personality} onChange={(e) => set("personality", e.target.value)} /></label>
      <label className="field">話し方<textarea rows={2} value={draft.speaking_style} onChange={(e) => set("speaking_style", e.target.value)} /></label>

      <fieldset className="appearance">
        <legend className="small">外見（画像生成の指示になります）</legend>
        <div className="appearance-grid">
          {(Object.keys(APPEARANCE_FIELDS) as AppearanceKey[]).map((key) => (
            <label key={key} className="field">
              {APPEARANCE_FIELDS[key]}
              <input maxLength={200} value={draft.appearance_details[key] ?? ""} onChange={(e) => setDetail(key, e.target.value)} />
            </label>
          ))}
        </div>
        <label className="field">自由記述<textarea rows={2} value={draft.appearance} onChange={(e) => set("appearance", e.target.value)} /></label>
      </fieldset>

      <div className="row">
        <label className="field">声の高さ
          <input type="number" step="0.05" min="-1" max="1" value={draft.voice_settings.pitch ?? ""} onChange={(e) => setVoice("pitch", e.target.value)} />
        </label>
        <label className="field">話速
          <input type="number" step="0.1" min="0.25" max="4" value={draft.voice_settings.speed ?? ""} onChange={(e) => setVoice("speed", e.target.value)} />
        </label>
        <button disabled={busy} onClick={() => void ops.generateVoiceSample(character.id)} title="保存済みの声の設定でサンプルを作ります">
          音声サンプルを生成
        </button>
      </div>
      {character.voice_sample_asset_id && (
        <div className="row">
          <audio controls preload="none" src={generationApi.assetUrl(character.voice_sample_asset_id)} />
          {character.voice_sample_stale && <span className="badge warn">声の設定が変わりました。サンプルを作り直してください</span>}
        </div>
      )}

      {dirty && <p className="small muted">※ 画像・音声サンプルの生成は、保存済みの設定で行われます。先に「保存」してください。</p>}
      <ExpressionImages character={character} busy={busy} ops={ops} />
      <div className="row space-between">
        <button className="primary" disabled={busy || !dirty || !draft.name.trim()} onClick={() => onSave(draft)}>
          保存
        </button>
        <button className="danger" disabled={busy} onClick={() => window.confirm(deleteConfirm) && onDelete()}>
          {deleteLabel}
        </button>
      </div>
    </li>
  );
}
