import { FormEvent, useEffect, useMemo, useState } from "react";
import type { Character, Dialogue, DialoguePatch } from "../../types";

interface Props {
  dialogues: Dialogue[];
  characters: Character[];
  busy: boolean;
  onUpdate: (id: string, patch: DialoguePatch) => void;
  onDelete: (id: string) => void;
  onAdd: (text: string, characterId: string | null) => void;
  onGroup: (ids: string[]) => void;
  onUngroup: (ids: string[]) => void;
}

function SpeakerSelect({
  value, characters, onChange, disabled,
}: { value: string | null; characters: Character[]; onChange: (id: string | null) => void; disabled?: boolean }) {
  return (
    <select value={value ?? ""} onChange={(e) => onChange(e.target.value || null)} disabled={disabled} aria-label="話者">
      <option value="">（話者未指定）</option>
      {characters.map((c) => (
        <option key={c.id} value={c.id}>
          {c.name}
        </option>
      ))}
    </select>
  );
}

function DialogueRow({
  dialogue, characters, busy, selected, groupLabel, onToggle, onUpdate, onDelete,
}: {
  dialogue: Dialogue; characters: Character[]; busy: boolean; selected: boolean; groupLabel: string | null;
  onToggle: () => void; onUpdate: Props["onUpdate"]; onDelete: Props["onDelete"];
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
      <input type="checkbox" checked={selected} onChange={onToggle} aria-label="選択" />
      <SpeakerSelect
        value={dialogue.character_id}
        characters={characters}
        disabled={busy}
        onChange={(id) => onUpdate(dialogue.id, { character_id: id })}
      />
      <input className="grow" value={text} onChange={(e) => setText(e.target.value)} onBlur={commit} aria-label="セリフ" />
      {groupLabel && <span className="badge">同時 {groupLabel}</span>}
      <button className="danger" disabled={busy} onClick={() => onDelete(dialogue.id)}>
        削除
      </button>
    </li>
  );
}

export default function DialogueList(props: Props) {
  const { dialogues, characters, busy, onUpdate, onDelete, onAdd, onGroup, onUngroup } = props;
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [newText, setNewText] = useState("");
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

  const ids = [...selected];
  return (
    <div>
      <div className="row">
        <button disabled={busy || ids.length < 2} onClick={() => onGroup(ids)}>
          選択したセリフを同時にする
        </button>
        <button disabled={busy || ids.length < 1} onClick={() => onUngroup(ids)}>
          同時を解除
        </button>
        <span className="muted small">{ids.length}件選択中</span>
      </div>

      {dialogues.length === 0 && <p className="muted">セリフがありません。シナリオを入力して「セリフに分割」を押してください。</p>}
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
