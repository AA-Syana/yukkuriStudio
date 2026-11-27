import assert from "node:assert/strict";
import {
  activeAt, assignRows, audioOffsetSec, dragRange, formatClock, neighborStart, pickImage, subtitleStack, tickStepMs,
} from "../src/features/editor/timelineMath.ts";

let n = 0;
const t = (name: string, fn: () => void) => { fn(); n++; console.log("ok -", name); };

t("move keeps length, snaps, and stops at 0", () => {
  assert.deepEqual(dragRange("move", { start: 1000, end: 2000 }, 503), { start: 1500, end: 2500 });
  assert.deepEqual(dragRange("move", { start: 1000, end: 2000 }, -5000), { start: 0, end: 1000 });
});
t("resize start cannot pass end or go below 0", () => {
  assert.deepEqual(dragRange("start", { start: 1000, end: 2000 }, 5000), { start: 1900, end: 2000 });
  assert.deepEqual(dragRange("start", { start: 1000, end: 2000 }, -5000), { start: 0, end: 2000 });
});
t("resize end keeps minimum length", () => {
  assert.deepEqual(dragRange("end", { start: 1000, end: 2000 }, -5000), { start: 1000, end: 1100 });
  assert.deepEqual(dragRange("end", { start: 1000, end: 2000 }, 1234), { start: 1000, end: 3230 });
});
t("activeAt is start-inclusive, end-exclusive", () => {
  const items = [{ start: 0, end: 1000, id: "a" }, { start: 1000, end: 2000, id: "b" }, { start: 500, end: 1500, id: "c" }];
  assert.deepEqual(activeAt(items, 1000).map((i) => i.id), ["b", "c"]);
  assert.deepEqual(activeAt(items, 2000), []);
});
t("assignRows stacks overlapping blocks and reuses rows", () => {
  const { rows, rowCount } = assignRows([
    { start: 0, end: 1000 }, { start: 500, end: 1500 }, { start: 1000, end: 2000 }, { start: 3000, end: 4000 },
  ]);
  assert.deepEqual(rows, [0, 1, 0, 0]);
  assert.equal(rowCount, 2);
  assert.deepEqual(assignRows([]), { rows: [], rowCount: 1 });
});
t("neighborStart prev/next", () => {
  const starts = [0, 1000, 3000, 3000];
  assert.equal(neighborStart(starts, 1000, "next"), 3000);
  assert.equal(neighborStart(starts, 3000, "next"), null);
  assert.equal(neighborStart(starts, 3500, "prev"), 3000); // セリフの途中 → そのセリフの頭
  assert.equal(neighborStart(starts, 3100, "prev"), 1000); // 頭のすぐ後 → ひとつ前
  assert.equal(neighborStart(starts, 100, "prev"), null);
});
t("audioOffsetSec follows playback speed", () => {
  assert.equal(audioOffsetSec(1000, 2000, 1), 1);
  assert.equal(audioOffsetSec(1000, 2000, 2), 2);
  assert.equal(audioOffsetSec(1000, 500, 1), 0);
});
t("pickImage falls back: expression -> emotion -> neutral -> any -> null", () => {
  const imgs = [{ expression: "neutral", asset_id: "n" }, { expression: "sad", asset_id: "s" }];
  assert.equal(pickImage(imgs, "sad", "happy", "neutral")?.asset_id, "s");
  assert.equal(pickImage(imgs, null, "sad", "neutral")?.asset_id, "s");
  assert.equal(pickImage(imgs, "angry", "happy", "neutral")?.asset_id, "n");
  assert.equal(pickImage([{ expression: "sad", asset_id: "s" }], null, "happy", "neutral")?.asset_id, "s");
  assert.equal(pickImage([], null, "happy", "neutral"), null);
});
t("subtitleStack separates same-position subtitles only", () => {
  const m = subtitleStack([
    { id: "a", x: 0.5, y: 0.9 }, { id: "b", x: 0.5, y: 0.9 }, { id: "c", x: 0.2, y: 0.5 }, { id: "d", x: 0.51, y: 0.89 },
  ]);
  assert.deepEqual([m.get("a"), m.get("b"), m.get("c"), m.get("d")], [0, 1, 0, 2]);
});
t("tick step grows as zoom decreases", () => {
  assert.equal(tickStepMs(200), 500);
  assert.equal(tickStepMs(80), 1000);
  assert.equal(tickStepMs(10), 10_000);
  assert.equal(tickStepMs(0.1), 300_000);
});
t("formatClock", () => {
  assert.equal(formatClock(0), "00:00.0");
  assert.equal(formatClock(65_450), "01:05.4");
  assert.equal(formatClock(-5), "00:00.0");
});
console.log(`${n} passed`);
