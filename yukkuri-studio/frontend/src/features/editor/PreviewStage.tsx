import { useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent, RefObject } from "react";
import { generationApi } from "../../api/generation";
import { videosApi } from "../../api/videos";
import type { Character, Dialogue, TimelineItem, VideoInfo } from "../../types";
import { activeAt, clamp, pickImage, subtitleStack, type Range } from "./timelineMath";
import { useTime, type TimeStore } from "./usePlayback";

interface Props {
  projectId: string;
  video: VideoInfo | null;
  videoRef: RefObject<HTMLVideoElement>;
  characters: Character[];
  dialogues: Dialogue[];
  items: TimelineItem[];
  store: TimeStore;
  selectedDialogueId: string | null;
  onSelect: (dialogueId: string, track: "character" | "subtitle") => void;
  onMoveCharacter: (itemId: string, x: number, y: number) => void;
}

const BASE_FONT_PX = 40; // 1080px高さのときの既定の字幕サイズ
const BASE_CHARACTER_HEIGHT = 0.6; // 拡大率1のときの立ち絵の高さ(画面の高さに対する割合)

/** 再生位置の立ち絵・字幕を、元動画の上に重ねて表示する。立ち絵はドラッグで位置を変えられる。 */
export default function PreviewStage(props: Props) {
  const { projectId, video, videoRef, characters, dialogues, items, store, selectedDialogueId } = props;
  const time = useTime(store);
  const stageRef = useRef<HTMLDivElement>(null);
  const [stageH, setStageH] = useState(360);
  const [drag, setDrag] = useState<{ id: string; x: number; y: number } | null>(null);

  useEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setStageH(el.clientHeight));
    ro.observe(el);
    setStageH(el.clientHeight);
    return () => ro.disconnect();
  }, []);

  const dialogueOrder = useMemo(() => new Map(dialogues.map((d) => [d.id, d.order_index])), [dialogues]);
  const charById = useMemo(() => new Map(characters.map((c) => [c.id, c])), [characters]);

  const blocks: (TimelineItem & Range)[] = useMemo(
    () => items.map((i) => ({ ...i, start: i.start_ms, end: i.end_ms })),
    [items],
  );
  const activeCharacters = activeAt(blocks.filter((i) => i.track_type === "character"), time);
  const activeSubtitles = activeAt(blocks.filter((i) => i.track_type === "subtitle"), time).sort(
    (a, b) => (dialogueOrder.get(a.dialogue_id) ?? 0) - (dialogueOrder.get(b.dialogue_id) ?? 0),
  );
  const stack = subtitleStack(activeSubtitles.map((s) => ({ id: s.id, x: s.position_x, y: s.position_y })));
  const fontScale = stageH / 1080;

  const startDrag = (e: ReactPointerEvent<HTMLDivElement>, item: TimelineItem) => {
    const stage = stageRef.current;
    if (!stage) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    props.onSelect(item.dialogue_id, "character");
    const rect = stage.getBoundingClientRect();
    const grab = { dx: item.position_x - (e.clientX - rect.left) / rect.width, dy: item.position_y - (e.clientY - rect.top) / rect.height };
    let last = { x: item.position_x, y: item.position_y };
    const move = (ev: PointerEvent) => {
      last = {
        x: clamp((ev.clientX - rect.left) / rect.width + grab.dx, 0, 1),
        y: clamp((ev.clientY - rect.top) / rect.height + grab.dy, 0, 1),
      };
      setDrag({ id: item.id, ...last });
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      setDrag(null);
      if (Math.abs(last.x - item.position_x) > 0.002 || Math.abs(last.y - item.position_y) > 0.002) {
        props.onMoveCharacter(item.id, Number(last.x.toFixed(3)), Number(last.y.toFixed(3)));
      }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const aspect = video && video.width && video.height ? `${video.width} / ${video.height}` : "16 / 9";
  return (
    <div className="stage" ref={stageRef} style={{ aspectRatio: aspect }} aria-label="プレビュー">
      {video ? (
        <video ref={videoRef} className="stage-video" src={videosApi.streamUrl(projectId)} playsInline preload="auto" />
      ) : (
        <div className="stage-empty">元動画なし（黒い背景で表示しています）</div>
      )}

      {activeCharacters.map((item) => {
        const character = item.character_id ? charById.get(item.character_id) : undefined;
        const image = character ? pickImage(character.images, item.expression, item.emotion, "neutral") : null;
        const pos = drag?.id === item.id ? drag : { x: item.position_x, y: item.position_y };
        const selected = item.dialogue_id === selectedDialogueId;
        return (
          <div
            key={item.id}
            className={`stage-character ${selected ? "selected" : ""}`}
            style={{ left: `${pos.x * 100}%`, top: `${pos.y * 100}%`, height: `${BASE_CHARACTER_HEIGHT * item.scale * 100}%` }}
            onPointerDown={(e) => startDrag(e, item)}
            title="ドラッグで位置を変えられます"
          >
            {image ? (
              <img src={generationApi.assetUrl(image.asset_id)} alt={character?.name ?? ""} draggable={false} />
            ) : (
              <div className="stage-noimage">{character?.name ?? item.speaker_name ?? "?"}<small>（画像なし）</small></div>
            )}
          </div>
        );
      })}

      {activeSubtitles.map((item) => {
        const fontPx = (item.font_size ?? BASE_FONT_PX) * fontScale;
        const level = stack.get(item.id) ?? 0;
        const selected = item.dialogue_id === selectedDialogueId;
        return (
          <div
            key={item.id}
            className={`stage-subtitle ${selected ? "selected" : ""}`}
            style={{
              left: `${item.position_x * 100}%`,
              top: `${item.position_y * 100}%`,
              fontSize: `${fontPx}px`,
              transform: `translate(-50%, calc(-50% - ${level * 1.4 * fontPx}px))`, // 同時の字幕は上へずらして重ねない
            }}
            onClick={() => props.onSelect(item.dialogue_id, "subtitle")}
          >
            {item.text_override ?? item.text}
          </div>
        );
      })}
    </div>
  );
}
