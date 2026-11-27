import { useEffect, useState } from "react";
import { formatMs, parseSeconds } from "../script/timeFormat";
import { MIN_DURATION_MS } from "./timelineMath";

/** スライダー。ドラッグ中は画面上の値だけを変え、指を離したとき(またはキー操作の後)に1回だけ保存する。 */
export function RangeField(props: {
  label: string; value: number; min: number; max: number; step: number;
  format?: (v: number) => string; disabled?: boolean; onCommit: (v: number) => void;
}) {
  const { label, value, min, max, step, format, disabled, onCommit } = props;
  const [v, setV] = useState(value);
  useEffect(() => setV(value), [value]);
  const commit = () => {
    if (v !== value) onCommit(v);
  };
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <input
        type="range" min={min} max={max} step={step} value={v} disabled={disabled}
        onChange={(e) => setV(Number(e.target.value))} onPointerUp={commit} onKeyUp={commit} onBlur={commit}
      />
      <span className="field-value">{format ? format(v) : v}</span>
    </label>
  );
}

/** 秒の入力欄。確定(フォーカスを外す/Enter)したときに保存し、不正な値は元に戻す。 */
export function SecondsInput(props: { value: number; disabled?: boolean; ariaLabel: string; onCommit: (ms: number) => void }) {
  const { value, disabled, ariaLabel, onCommit } = props;
  const [text, setText] = useState(formatMs(value));
  useEffect(() => setText(formatMs(value)), [value]);
  const commit = () => {
    const ms = parseSeconds(text);
    if (ms === null) return setText(formatMs(value));
    if (ms !== value) onCommit(ms);
  };
  return (
    <input
      className="time-input" inputMode="decimal" value={text} disabled={disabled} aria-label={ariaLabel}
      onChange={(e) => setText(e.target.value)} onBlur={commit} onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
    />
  );
}

/** 表示の開始・終了時間(秒)。終了は開始より後(最小の長さ以上)でなければ受け付けない。 */
export function TimeRangeFields(props: {
  start: number; end: number; disabled?: boolean; onCommit: (start: number, end: number) => void;
}) {
  const { start, end, disabled, onCommit } = props;
  const [error, setError] = useState<string | null>(null);
  const apply = (s: number, e: number) => {
    if (e - s < MIN_DURATION_MS) return setError("終了は開始より後にしてください");
    setError(null);
    onCommit(s, e);
  };
  return (
    <div className="field">
      <span className="field-label">表示時間(秒)</span>
      <span className="field-inline">
        <SecondsInput value={start} disabled={disabled} ariaLabel="開始時間(秒)" onCommit={(s) => apply(s, end)} />
        〜
        <SecondsInput value={end} disabled={disabled} ariaLabel="終了時間(秒)" onCommit={(e) => apply(start, e)} />
      </span>
      {error && <span className="field-error">{error}</span>}
    </div>
  );
}
