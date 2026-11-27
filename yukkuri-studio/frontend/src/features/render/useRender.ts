import { useCallback, useEffect, useState } from "react";
import { messageOf } from "../../api/client";
import { generationApi } from "../../api/generation";
import { renderApi } from "../../api/render";
import { isActive, type RenderOptions, type RenderStatus } from "../../types";

/** 書き出しの状態。実行中は1秒ごとに進捗を取得する。画面を開き直しても、実行中の書き出しを追跡し直せる。 */
export function useRender(projectId: string) {
  const [status, setStatus] = useState<RenderStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const refresh = useCallback(async () => {
    setStatus(await renderApi.status(projectId));
  }, [projectId]);

  useEffect(() => {
    refresh().catch((e) => setError(messageOf(e)));
  }, [refresh]);

  const active = !!status?.job && isActive(status.job);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => refresh().catch((e) => setError(messageOf(e))), 1000);
    return () => clearInterval(timer);
  }, [active, refresh]);

  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    setStarting(true);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setStarting(false);
    }
  };

  return {
    status, error, active, starting, clearError: () => setError(null),
    start: (options: RenderOptions) => run(() => renderApi.start(projectId, options)),
    retry: () => status?.job && run(() => generationApi.retryJob(status.job!.id)),
  };
}
