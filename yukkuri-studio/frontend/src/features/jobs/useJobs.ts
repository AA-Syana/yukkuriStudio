import { useCallback, useEffect, useRef, useState } from "react";
import { messageOf } from "../../api/client";
import { generationApi } from "../../api/generation";
import { isActive, type Job } from "../../types";

const POLL_INTERVAL_MS = 1000;
const MAX_LISTED = 10;

/**
 * 生成ジョブの進捗を追跡する。1秒ごとに状態を取得し、終わったら onSettled を呼ぶ
 * (呼び出し側はそこで画面のデータを取得し直す)。
 */
export function useJobs(onSettled: () => Promise<void> | void) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const alive = useRef(true);
  const tracking = useRef(new Set<string>());
  const onSettledRef = useRef(onSettled);
  onSettledRef.current = onSettled;

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const upsert = useCallback((job: Job) => {
    setJobs((prev) => [job, ...prev.filter((j) => j.id !== job.id)].slice(0, MAX_LISTED));
  }, []);

  const track = useCallback(
    async (job: Job) => {
      if (tracking.current.has(job.id)) return; // 同じジョブを二重に追跡しない
      tracking.current.add(job.id);
      upsert(job);
      let current = job;
      try {
        while (alive.current && isActive(current)) {
          await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
          if (!alive.current) return;
          try {
            current = await generationApi.getJob(job.id);
          } catch (e) {
            current = { ...current, status: "failed", error: `進捗を取得できません: ${messageOf(e)}` };
          }
          upsert(current);
        }
      } finally {
        tracking.current.delete(job.id);
      }
      if (alive.current) await onSettledRef.current();
    },
    [upsert],
  );

  /** 画面を開き直したときに、実行中のジョブを追跡し直す。完了済みは一覧にだけ出す。 */
  const resume = useCallback(
    (recent: Job[]) => {
      recent.filter(isActive).forEach((j) => void track(j));
      setJobs((prev) => (prev.length ? prev : recent.slice(0, MAX_LISTED)));
    },
    [track],
  );

  const retry = useCallback(
    async (job: Job) => {
      const restarted = await generationApi.retryJob(job.id);
      tracking.current.delete(job.id);
      void track(restarted);
    },
    [track],
  );

  const dismissFinished = useCallback(() => setJobs((prev) => prev.filter(isActive)), []);

  return { jobs, track, resume, retry, dismissFinished };
}
