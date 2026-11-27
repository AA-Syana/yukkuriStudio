import { useCallback, useState } from "react";
import { messageOf } from "../api/client";

/** 操作の実行中フラグとエラー表示をまとめる。失敗時は undefined を返す。 */
export function useRunner() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setError(null);
    setBusy(true);
    try {
      return await fn();
    } catch (e) {
      setError(messageOf(e));
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);

  const clearError = useCallback(() => setError(null), []);
  return { busy, error, setError, clearError, run };
}
