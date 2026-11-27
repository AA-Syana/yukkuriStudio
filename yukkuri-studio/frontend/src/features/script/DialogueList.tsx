import { FormEvent, useEffect, useMemo, useState } from "react";
import { generationApi } from "../../api/generation";
import { formatMs, parseSeconds } from "./timeFormat";
import { EMOTIONS, EMOTION_LABELS, type Character, type Dialogue, type DialoguePatch, type Emotion, type LayoutOptions } from "../../types";

interface Props {
  dialogues: Dialogue[];
  characters: Character[]; // このプロジェクトのキャラクターだけが話者にできる
  busy: boolean;
  onUpdate: (id: string, patch: DialoguePatch) => void;
  onDelete: (id: string) => void;
  onAdd: (text: string, characterId: string | null) => void;
  onGroup: (ids: string[]) => void;
  onUngroup: (ids: string[]) => void;
  onGenerateVoice: (id: string) => void;
  onGenerateAllVoices: () => void;
  onAnalyze: () => void;
  onLayout: (options: LayoutOptions) => void;
  layoutWarnings: string[];
}

function SpeakerSelect({
  value, unregisteredName, characters, onChange, disabled,
}: {
  value: string | null; unregisteredName?: string | null; characters: Character[];
  onChange: (id: string | null) => void; disabled?: boolean;
}) {
  return (
    <select value={value ?? ""} onChange={(e) => onChange(e.target.value || null)} disabled={disabled} aria-label="話者">
      <option value="">{unregisteredName ? `⚠ 未登録: ${unregisteredName}` : "（話者未指定）"}</option>
      {characters.map((c) => (
        <option key={c.id} value={c.id}>
          {c.name}
        </option>
      ))}
    </select>
  );
}

function AudioControls({ dialogue, busy, onGenerate }: { dialogue: Dialogue; busy: boolean; onGenerate: () => void }) {
  const hasAudio = dialogue.audio_asset_id !== null;
  return (
    <div className="row dialogue-sub">
      {hasAudio ? (
        <>
          <audio controls preload="none" src={generationApi.assetUrl(dialogue.audio_asset_id!)} />
          <span className="muted small">{((dialogue.audio_duration_ms ?? 0) / 1000).toFixed(1)}秒</span>
          {dialogue.audio_stale && <span className="badge warn">セリフや設定が変わりました。再生成してください</span>}
        </>
      ) : (
        <span className="muted small">音声は未生成です</span>
      )}
      {dialogue.generation_status === "failed" && <span className="badge error">生成失敗</span>}
      <button disabled={busy || dialogue.generation_status === "generating"} onClick={onGenerate}>
        {hasAudio ? "音声を再生成" : "音声を生成"}
      </button>
    </div>
  );
}

/** セリフの開始・終了時間(秒)。手で変更すると「手動指定」になり、自動配置で動かなくなる。 */
function TimingControls({ dialogue, busy, onUpdate }: { dialogue: Dialogue; busy: boolean; onUpdate: Props["onUpdate"] }) {
  const placed = dialogue.start_ms !== null && dialogue.end_ms !== null;
  const [start, setStart] = useState(placed ? formatMs(dialogue.start_ms!) : "");
  const [end, setEnd] = useState(placed ? formatMs(dialogue.end_ms!) : "");
  useEffect(() => {
    setStart(dialogue.start_ms !== null ? formatMs(dialogue.start_ms) : "");
    setEnd(dialogue.end_ms !== null ? formatMs(dialogue.end_ms) : "");
  }, [dialogue.start_ms, dialogue.end_ms]);

  const commit = () => {
    const s = parseSeconds(start);
    const e = parseSeconds(end);
    if (s === null || e === null || e < s) {
      // 不正な入力は元に戻す
      setStart(placed ? formatMs(dialogue.start_ms!) : "");
      setEnd(placed ? formatMs(dialogue.end_ms!) : "");
      return;
    }
    if (s !== dialogue.start_ms || e !== dialogue.end_ms) onUpdate(dialogue.id, { start_ms: s, end_ms: e });
  };

  return (
    <div className="row dialogue-sub">
      <span className="muted small">時間(秒)</span>
      <input className="time-input" inputMode="decimal" value={start} placeholder="開始" disabled={busy}
        onChange={(e) => setStart(e.target.value)} onBlur={commit} aria-label="開始時間(秒)" />
      <span>〜</span>
      <input className="time-input" inputMode="decimal" value={end} placeholder="終了" disabled={busy}
        onChange={(e) => setEnd(e.target.value)} onBlur={commit} aria-label="終了時間(秒)" />
      {!placed && <span className="badge warn">未配置</span>}
      {dialogue.timing_locked && (
        <>
          <span className="badge">手動指定</span>
          <button disabled={busy} onClick={() => onUpdate(dialogue.id, { timing_locked: false })}>自動に戻す</button>
        </>
      )}
      {placed && dialogue.timing_stale && <span className="badge warn">音声の長さとずれています。再配置してください</span>}
    </div>
  );
}

function DialogueRow({
  dialogue, characters, busy, selected, groupLabel, onToggle, onUpdate, onDelete, onGenerateVoice,
}: {
  dialogue: Dialogue; characters: Character[]; busy: boolean; selected: boolean;
  groupLabel: string | null; onToggle: () => void;
  onUpdate: Props["onUpdate"]; onDelete: Props["onDelete"]; onGenerateVoice: Props["onGenerateVoice"];
}) {
  const [text, setText] = useState(dialogue.text);
  useEffect(() => setText(dialogue.text), [dialogue.text]);

  // フォーカスが外れたときだけ保存する(1文字ごとにAPIを呼ばない)
  const commit = () => {
    const next = text.trim();
    if (!next) return setText(dialogue.text); // 空には変更できない
    if (next !== dialogue.text) onUpdate(dialogue.id, { text: next });
  };

  return (
    <li className={`dialogue ${selected ? "selected" : ""}`}>
      <div className="row dialogue-main">
        <input type="checkbox" checked={selected} onChange={onToggle} aria-label="選択" />
        <SpeakerSelect
          value={dialogue.character_id}
          unregisteredName={dialogue.character_id ? null : dialogue.speaker_name}
          characters={characters}
          disabled={busy}
          onChange={(id) => onUpdate(dialogue.id, { character_id: id })}
        />
        <select
          value={dialogue.emotion}
          disabled={busy}
          onChange={(e) => onUpdate(dialogue.id, { emotion: e.target.value as Emotion })}
          aria-label="感情"
        >
          {EMOTIONS.map((e) => (
            <option key={e} value={e}>
              {EMOTION_LABELS[e]}
            </option>
          ))}
        </select>
        <input className="grow" value={text} onChange={(e) => setText(e.target.value)} onBlur={commit} aria-label="セリフ" />
        {groupLabel && <span className="badge">同時 {groupLabel}</span>}
        <button className="danger" disabled={busy} onClick={() => onDelete(dialogue.id)}>
          削除
        </button>
      </div>
      <AudioControls dialogue={dialogue} busy={busy} onGenerate={() => onGenerateVoice(dialogue.id)} />
      <TimingControls dialogue={dialogue} busy={busy} onUpdate={onUpdate} />
      {dialogue.suggestion && <div className="suggestion">💡 {dialogue.suggestion}</div>}
    </li>
  );
}

export default function DialogueList(props: Props) {
  const { dialogues, characters, busy, onUpdate, onDelete, onAdd, onGroup, onUngroup, onLayout } = props;
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [newText, setNewText] = useState("");
  const [gapSec, setGapSec] = useState("0.3");
  const [overwrite, setOverwrite] = useState(false);
  const [newSpeaker, setNewSpeaker] = useState<string | null>(null);

  // 2件以上が同じグループのものだけ「同時A, B…」として表示する
  const groupLabels = useMemo(() => {
    const counts = new Map<string, number>();
    dialogues.forEach((d) => d.simultaneous_group && counts.set(d.simultaneous_group, (counts.get(d.simultaneous_group) ?? 0) + 1));
    const labels = new Map<string, string>();
    for (const d of dialogues) {
      const g = d.simultaneous_group;
      if (g && (counts.get(g) ?? 0) >= 2 && !labels.has(g)) labels.set(g, String.fromCharCode(65 + labels.size));
    }
    return labels;
  }, [dialogues]);

  // 削除などで存在しなくなったIDは選択から外す
  useEffect(() => {
    setSelected((prev) => new Set([...prev].filter((id) => dialogues.some((d) => d.id === id))));
  }, [dialogues]);

  // キャラクターを外した場合などに、選べなくなった話者が選択されたままにならないようにする
  useEffect(() => {
    if (newSpeaker && !characters.some((c) => c.id === newSpeaker)) setNewSpeaker(null);
  }, [characters, newSpeaker]);

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!newText.trim()) return;
    onAdd(newText, newSpeaker);
    setNewText("");
  };

  const layout = () => {
    const gap = parseSeconds(gapSec);
    if (gap === null) return;
    onLayout({ gap_ms: Math.min(gap, 10_000), start_ms: 0, overwrite_locked: overwrite });
  };

  const ids = [...selected];
  const needLayout = dialogues.filter((d) => d.timing_stale).length;
  const needVoice = dialogues.filter((d) => d.audio_asset_id === null || d.audio_stale).length;
  return (
    <div>
      <div className="row">
        <button className="primary" disabled={busy || dialogues.length === 0 || needVoice === 0} onClick={props.onGenerateAllVoices}>
          音声を一括生成{needVoice > 0 ? `（${needVoice}件）` : ""}
        </button>
        <button disabled={busy || dialogues.length === 0} onClick={props.onAnalyze} title="手動で編集したセリフの感情は変更されません">
          AI解析（感情・改善案）
        </button>
      </div>
      <div className="row">
        <button disabled={busy || ids.length < 2} onClick={() => onGroup(ids)}>
          選択したセリフを同時にする
        </button>
        <button disabled={busy || ids.length < 1} onClick={() => onUngroup(ids)}>
          同時を解除
        </button>
        <span className="muted small">{ids.length}件選択中</span>
      </div>

      <div className="row layout-row">
        <button className="primary" disabled={busy || dialogues.length === 0} onClick={layout}>
          タイミングを自動配置{needLayout > 0 ? `（${needLayout}件が未配置・ずれあり）` : ""}
        </button>
        <label className="small">
          セリフの間隔
          <input className="time-input" inputMode="decimal" value={gapSec} onChange={(e) => setGapSec(e.target.value)} aria-label="セリフの間隔(秒)" />秒
        </label>
        <label className="small">
          <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} />
          手動指定の時間も振り直す
        </label>
      </div>
      {props.layoutWarnings.length > 0 && (
        <div className="warning">
          <strong>配置についての注意</strong>
          <ul>{props.layoutWarnings.map((w) => <li key={w}>{w}</li>)}</ul>
        </div>
      )}

      {dialogues.length === 0 && <p className="muted">セリフがありません。台本を入力して「セリフに分割」を押してください。</p>}
      <ul className="dialogue-list">
        {dialogues.map((d) => (
          <DialogueRow
            key={d.id}
            dialogue={d}
            characters={characters}
            busy={busy}
            selected={selected.has(d.id)}
            groupLabel={d.simultaneous_group ? groupLabels.get(d.simultaneous_group) ?? null : null}
            onToggle={() => toggle(d.id)}
            onUpdate={onUpdate}
            onDelete={onDelete}
            onGenerateVoice={props.onGenerateVoice}
          />
        ))}
      </ul>

      <form className="row" onSubmit={submit}>
        <SpeakerSelect value={newSpeaker} characters={characters} onChange={setNewSpeaker} />
        <input className="grow" value={newText} onChange={(e) => setNewText(e.target.value)} placeholder="セリフを追加" />
        <button disabled={busy || !newText.trim()}>追加</button>
      </form>
    </div>
  );
}
