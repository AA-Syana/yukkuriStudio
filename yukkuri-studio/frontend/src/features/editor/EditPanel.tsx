import { useEffect, useRef } from "react";
import { generationApi } from "../../api/generation";
import {
  EMOTIONS, EMOTION_LABELS, type Character, type Dialogue, type Emotion, type TimelineItem, type TimelineItemPatch,
} from "../../types";
import { RangeField, TimeRangeFields } from "./fields";

export type EditTab = "audio" | "image" | "subtitle";
const TABS: { id: EditTab; label: string }[] = [
  { id: "audio", label: "音声" },
  { id: "image", label: "画像" },
  { id: "subtitle", label: "字幕" },
];

interface Props {
  tab: EditTab;
  onTab: (tab: EditTab) => void;
  dialogue: Dialogue | null;
  audioItem?: TimelineItem;
  characterItem?: TimelineItem;
  subtitleItem?: TimelineItem;
  character: Character | null;
  busy: boolean;
  onItem: (itemId: string, patch: TimelineItemPatch) => void;
  onFitToAudio: (dialogue: Dialogue) => void;
  onRegenerateVoice: (dialogueId: string) => void;
  onGenerateImage: (characterId: string, expression: Emotion) => void;
  onLayout: () => void;
}

const pct = (v: number) => `${Math.round(v * 100)}%`;

function AudioTab({ dialogue, item, busy, onItem, onFitToAudio, onRegenerateVoice }: {
  dialogue: Dialogue; item?: TimelineItem; busy: boolean;
} & Pick<Props, "onItem" | "onFitToAudio" | "onRegenerateVoice">) {
  const player = useRef<HTMLAudioElement>(null);
  // 試聴にも、設定した音量・速度を反映する
  useEffect(() => {
    if (player.current && item) {
      player.current.playbackRate = item.playback_speed;
      player.current.volume = Math.min(item.volume, 1);
    }
  }, [item?.playback_speed, item?.volume, item?.audio_asset_id]);
  const generating = dialogue.generation_status === "generating";
  return (
    <div>
      {item && item.audio_asset_id ? (
        <>
          <div className="field">
            <span className="field-label">試聴</span>
            <audio ref={player} controls preload="none" src={generationApi.assetUrl(item.audio_asset_id)} />
          </div>
          <RangeField label="音量" value={item.volume} min={0} max={2} step={0.05} format={pct} disabled={busy}
            onCommit={(v) => onItem(item.id, { volume: v })} />
          <p className="muted small">プレビューでは100%を超える音量は反映されません(書き出しで反映する予定です)。</p>
          <RangeField label="再生速度" value={item.playback_speed} min={0.5} max={2} step={0.05} format={(v) => `${v.toFixed(2)}倍`} disabled={busy}
            onCommit={(v) => onItem(item.id, { playback_speed: v })} />
          <p className="muted small">速度を変えると、音声の長さも変わります（音声ブロックの終わりが自動で動きます）。</p>
        </>
      ) : (
        <p className="muted">音声が未生成です。生成すると、音量・速度を調整できます。</p>
      )}
      {dialogue.audio_stale && <p className="badge warn">セリフや設定が変わりました。再生成してください</p>}
      {dialogue.timing_stale && dialogue.start_ms !== null && dialogue.audio_duration_ms !== null && !dialogue.timing_locked && (
        <p>
          <span className="badge warn">音声の長さと配置がずれています</span>{" "}
          <button disabled={busy} onClick={() => onFitToAudio(dialogue)}>この音声の長さに合わせる</button>
        </p>
      )}
      <div className="row">
        <button className="primary" disabled={busy || generating} onClick={() => onRegenerateVoice(dialogue.id)}>
          {item?.audio_asset_id ? "音声を再生成" : "音声を生成"}
        </button>
        {generating && <span className="muted small">生成中…</span>}
        {dialogue.generation_status === "failed" && <span className="badge error">前回の生成は失敗しました</span>}
      </div>
    </div>
  );
}

function ImageTab({ dialogue, item, character, busy, onItem, onGenerateImage }: {
  dialogue: Dialogue; item?: TimelineItem; character: Character | null; busy: boolean;
} & Pick<Props, "onItem" | "onGenerateImage">) {
  if (!item || !character) {
    return <p className="muted">このセリフには、立ち絵がありません（話者がプロジェクトに未登録、または未配置です）。</p>;
  }
  const effective: Emotion = item.expression ?? dialogue.emotion;
  const has = (e: Emotion) => character.images.some((i) => i.expression === e);
  return (
    <div>
      <label className="field">
        <span className="field-label">表情</span>
        <select
          value={item.expression ?? ""} disabled={busy} aria-label="表情"
          onChange={(e) => onItem(item.id, { expression: (e.target.value || null) as Emotion | null })}
        >
          <option value="">自動（セリフの感情：{EMOTION_LABELS[dialogue.emotion]}）</option>
          {EMOTIONS.map((e) => (
            <option key={e} value={e}>{EMOTION_LABELS[e]}{has(e) ? "" : "（画像なし）"}</option>
          ))}
        </select>
      </label>
      {!has(effective) && (
        <p>
          <span className="badge warn">「{EMOTION_LABELS[effective]}」の画像がありません（近い画像で代用して表示中）</span>{" "}
          <button disabled={busy} onClick={() => onGenerateImage(character.id, effective)}>この表情の画像を生成</button>
        </p>
      )}
      <RangeField label="サイズ" value={item.scale} min={0.2} max={2.5} step={0.05} format={pct} disabled={busy}
        onCommit={(v) => onItem(item.id, { scale: v })} />
      <RangeField label="位置 左右" value={item.position_x} min={0} max={1} step={0.01} format={pct} disabled={busy}
        onCommit={(v) => onItem(item.id, { position_x: v })} />
      <RangeField label="位置 上下" value={item.position_y} min={0} max={1} step={0.01} format={pct} disabled={busy}
        onCommit={(v) => onItem(item.id, { position_y: v })} />
      <p className="muted small">プレビュー上の立ち絵をドラッグして動かすこともできます。</p>
      <TimeRangeFields start={item.start_ms} end={item.end_ms} disabled={busy}
        onCommit={(s, e) => onItem(item.id, { start_ms: s, end_ms: e })} />
    </div>
  );
}

function SubtitleTab({ dialogue, item, busy, onItem }: {
  dialogue: Dialogue; item?: TimelineItem; busy: boolean;
} & Pick<Props, "onItem">) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const shown = item ? item.text_override ?? item.text : "";
  useEffect(() => {
    if (ref.current) ref.current.value = shown;
  }, [shown, item?.id]);
  if (!item) return <p className="muted">字幕がありません。先にタイミングを自動配置してください。</p>;
  const commitText = () => {
    const next = ref.current?.value ?? "";
    if (next === shown) return;
    // セリフ本文と同じなら「既定」に戻す(空文字もサーバー側で既定に戻る)
    onItem(item.id, { text_override: next === dialogue.text ? null : next });
  };
  return (
    <div>
      <label className="field">
        <span className="field-label">字幕テキスト</span>
        <textarea ref={ref} rows={3} defaultValue={shown} disabled={busy} onBlur={commitText} aria-label="字幕テキスト" />
      </label>
      <p className="muted small">
        字幕だけを変えます。セリフ本文・音声は変わりません。
        {item.text_override !== null && (
          <> <button disabled={busy} onClick={() => onItem(item.id, { text_override: null })}>セリフ本文に戻す</button></>
        )}
      </p>
      <RangeField label="文字サイズ" value={item.font_size ?? 40} min={16} max={120} step={2} format={(v) => `${v}`} disabled={busy}
        onCommit={(v) => onItem(item.id, { font_size: v })} />
      {item.font_size !== null && (
        <p className="small"><button disabled={busy} onClick={() => onItem(item.id, { font_size: null })}>文字サイズを既定に戻す</button></p>
      )}
      <RangeField label="位置 左右" value={item.position_x} min={0} max={1} step={0.01} format={pct} disabled={busy}
        onCommit={(v) => onItem(item.id, { position_x: v })} />
      <RangeField label="位置 上下" value={item.position_y} min={0} max={1} step={0.01} format={pct} disabled={busy}
        onCommit={(v) => onItem(item.id, { position_y: v })} />
      <TimeRangeFields start={item.start_ms} end={item.end_ms} disabled={busy}
        onCommit={(s, e) => onItem(item.id, { start_ms: s, end_ms: e })} />
    </div>
  );
}

/** 右側の編集パネル。タブを切り替えても選択中のセリフは変わらない。 */
export default function EditPanel(props: Props) {
  const { tab, onTab, dialogue, busy } = props;
  if (!dialogue) {
    return <div className="card"><p className="muted">タイムラインのセリフ（またはプレビューの立ち絵・字幕）をクリックすると、ここで編集できます。</p></div>;
  }
  const placed = dialogue.start_ms !== null && dialogue.end_ms !== null;
  return (
    <div className="card edit-panel">
      <div className="edit-target">
        <strong>{dialogue.speaker_name ?? "話者未指定"}</strong>
        <span className="muted small">{EMOTION_LABELS[dialogue.emotion]}</span>
        <div className="edit-text">{dialogue.text}</div>
      </div>
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? "tab active" : "tab"} onClick={() => onTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      {!placed && (
        <p>
          <span className="badge warn">このセリフはまだ時間が配置されていません</span>{" "}
          <button disabled={busy} onClick={props.onLayout}>タイミングを自動配置</button>
        </p>
      )}
      {tab === "audio" && (
        <AudioTab dialogue={dialogue} item={props.audioItem} busy={busy} onItem={props.onItem}
          onFitToAudio={props.onFitToAudio} onRegenerateVoice={props.onRegenerateVoice} />
      )}
      {tab === "image" && (
        <ImageTab dialogue={dialogue} item={props.characterItem} character={props.character} busy={busy}
          onItem={props.onItem} onGenerateImage={props.onGenerateImage} />
      )}
      {tab === "subtitle" && <SubtitleTab dialogue={dialogue} item={props.subtitleItem} busy={busy} onItem={props.onItem} />}
    </div>
  );
}
