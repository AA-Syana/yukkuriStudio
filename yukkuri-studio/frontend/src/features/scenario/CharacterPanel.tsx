import { FormEvent, useEffect, useState } from "react";
import type { Character, CharacterInput } from "../../types";

interface Props {
  characters: Character[];
  busy: boolean;
  onAdd: (name: string) => void;
  onUpdate: (id: string, input: Partial<CharacterInput>) => void;
  onDelete: (id: string) => void;
}

// 編集対象のフィールドだけを取り出す(id等を除く)
const toInput = (c: Character): CharacterInput => ({
  name: c.name,
  appearance: c.appearance,
  personality: c.personality,
  speaking_style: c.speaking_style,
  voice_settings: c.voice_settings,
});

function CharacterCard({ character, busy, onUpdate, onDelete }: { character: Character; busy: boolean } & Pick<Props, "onUpdate" | "onDelete">) {
  const [draft, setDraft] = useState<CharacterInput>(toInput(character));
  useEffect(() => setDraft(toInput(character)), [character]);

  const set = <K extends keyof CharacterInput>(key: K, value: CharacterInput[K]) => setDraft((d) => ({ ...d, [key]: value }));
  const setVoice = (key: "pitch" | "speed", raw: string) =>
    set("voice_settings", { ...draft.voice_settings, [key]: raw === "" ? undefined : Number(raw) });

  const dirty = JSON.stringify(draft) !== JSON.stringify(toInput(character));

  return (
    <li className="card">
      <label className="field">名前<input value={draft.name} onChange={(e) => set("name", e.target.value)} /></label>
      <label className="field">外見<textarea rows={2} value={draft.appearance} onChange={(e) => set("appearance", e.target.value)} /></label>
      <label className="field">性格<textarea rows={2} value={draft.personality} onChange={(e) => set("personality", e.target.value)} /></label>
      <label className="field">話し方<textarea rows={2} value={draft.speaking_style} onChange={(e) => set("speaking_style", e.target.value)} /></label>
      <div className="row">
        <label className="field">声の高さ
          <input type="number" step="0.05" value={draft.voice_settings.pitch ?? ""} onChange={(e) => setVoice("pitch", e.target.value)} />
        </label>
        <label className="field">話速
          <input type="number" step="0.1" min="0.1" value={draft.voice_settings.speed ?? ""} onChange={(e) => setVoice("speed", e.target.value)} />
        </label>
      </div>
      <div className="row space-between">
        <button className="primary" disabled={busy || !dirty || !draft.name.trim()} onClick={() => onUpdate(character.id, draft)}>
          保存
        </button>
        <button className="danger" disabled={busy} onClick={() => window.confirm(`「${character.name}」を削除しますか？（セリフは残り、話者が未指定になります）`) && onDelete(character.id)}>
          削除
        </button>
      </div>
    </li>
  );
}

export default function CharacterPanel({ characters, busy, onAdd, onUpdate, onDelete }: Props) {
  const [name, setName] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    onAdd(name.trim());
    setName("");
  };
  return (
    <div>
      <form className="row" onSubmit={submit}>
        <input className="grow" value={name} onChange={(e) => setName(e.target.value)} placeholder="キャラクター名" />
        <button disabled={busy || !name.trim()}>追加</button>
      </form>
      {characters.length === 0 && <p className="muted">キャラクターがいません。シナリオ分割で話者が自動登録されます。</p>}
      <ul className="card-list">
        {characters.map((c) => (
          <CharacterCard key={c.id} character={c} busy={busy} onUpdate={onUpdate} onDelete={onDelete} />
        ))}
      </ul>
      <p className="muted small">キャラクター画像・表情差分の登録は Phase 2 で追加します。</p>
    </div>
  );
}
