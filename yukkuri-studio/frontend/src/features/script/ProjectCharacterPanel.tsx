import { useState } from "react";
import { Link } from "react-router-dom";
import type { CharacterOps } from "../characters/characterOps";
import CharacterEditor from "../characters/CharacterEditor";
import type { Character, CharacterInput, UnknownSpeaker } from "../../types";

interface Props {
  characters: Character[]; // このプロジェクトのキャラクター(コピー)
  library: Character[];
  unknown: UnknownSpeaker[];
  speakerless: number;
  busy: boolean;
  ops: CharacterOps;
  onAdd: (sourceId: string) => void;
  onUpdate: (id: string, input: Partial<CharacterInput>) => void;
  onRemove: (id: string) => void;
}

/** 台本に出てくるが、このプロジェクトに追加されていない話者の警告。 */
function UnknownSpeakers({ unknown, speakerless, busy, onAdd }: Pick<Props, "unknown" | "speakerless" | "busy" | "onAdd">) {
  if (unknown.length === 0 && speakerless === 0) return null;
  return (
    <div className="warning" role="alert">
      {unknown.length > 0 && (
        <>
          <strong>⚠ キャラクター未登録の話者があります。音声・立ち絵は、追加するまで作れません。</strong>
          <ul>
            {unknown.map((u) => (
              <li key={u.name} className="row">
                <span>「{u.name}」（{u.count}件）</span>
                {u.library_character_id ? (
                  <button disabled={busy} onClick={() => onAdd(u.library_character_id!)}>キャラクター管理から追加</button>
                ) : (
                  <span className="small">
                    キャラクター管理に「{u.name}」がありません。
                    <Link to="/characters" target="_blank">キャラクター管理で作成</Link>
                    してから、下の「キャラクターを追加」で追加してください。
                  </span>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      {speakerless > 0 && (
        <p className="small">
          話者が決まらないセリフが{speakerless}件あります（最初の <code>[話者名]</code> より前の行など）。セリフ一覧で話者を選んでください。
        </p>
      )}
    </div>
  );
}

export default function ProjectCharacterPanel(props: Props) {
  const { characters, library, busy } = props;
  const [picked, setPicked] = useState("");
  // すでにこのプロジェクトへ追加済み(コピー元として使われている)キャラクターは候補から除く
  const used = new Set(characters.map((c) => c.source_character_id));
  const candidates = library.filter((c) => !used.has(c.id));

  return (
    <div>
      <UnknownSpeakers {...props} />

      <div className="row">
        <select className="grow" value={picked} onChange={(e) => setPicked(e.target.value)} aria-label="追加するキャラクター">
          <option value="">キャラクター管理から選ぶ…</option>
          {candidates.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
        <button
          className="primary"
          disabled={busy || !picked}
          onClick={() => {
            props.onAdd(picked);
            setPicked("");
          }}
        >
          キャラクターを追加
        </button>
      </div>
      {library.length === 0 && (
        <p className="muted small">キャラクター管理にキャラクターがありません。<Link to="/characters">キャラクター管理</Link>で作成してください。</p>
      )}

      <div className="notice small">
        ここにあるのは、追加した時点の内容の<strong>このプロジェクト用のコピー</strong>です。ここでの編集がこのプロジェクトでは優先され、
        キャラクター管理には反映されません。キャラクター管理で後から編集した内容は、次にプロジェクトへ追加するときから反映されます
        （最新の内容を取り込みたいときは、一度「プロジェクトから外す」→再度追加。セリフは残り、話者は自動で結びつき直します）。
      </div>

      {characters.length === 0 && <p className="muted">このプロジェクトのキャラクターがいません。</p>}
      <ul className="card-list">
        {characters.map((c) => (
          <CharacterEditor
            key={c.id}
            character={c}
            busy={busy}
            ops={props.ops}
            header={
              <p className="muted small">
                {c.source_character_id ? "キャラクター管理から追加したコピー" : "コピー元はキャラクター管理から削除されました"}
              </p>
            }
            onSave={(input) => props.onUpdate(c.id, input)}
            onDelete={() => props.onRemove(c.id)}
            deleteLabel="プロジェクトから外す"
            deleteConfirm={`「${c.name}」をこのプロジェクトから外しますか？\nセリフは残り、話者が「未登録」になります（キャラクター管理のキャラクターは削除されません）。`}
          />
        ))}
      </ul>
    </div>
  );
}
