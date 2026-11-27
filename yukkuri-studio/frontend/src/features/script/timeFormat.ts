/** ミリ秒 ⇔ 画面表示用の秒(小数第2位まで)。 */
export function formatMs(ms: number): string {
  return (ms / 1000).toFixed(2).replace(/\.?0+$/, "");
}

/** 「1.5」「2」などの秒の入力をミリ秒に変換する。数値として読めない・負の値は null。 */
export function parseSeconds(text: string): number | null {
  const t = text.trim();
  if (!/^\d+(\.\d+)?$/.test(t)) return null;
  return Math.round(parseFloat(t) * 1000);
}
