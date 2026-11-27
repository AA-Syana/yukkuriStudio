import { EMOTION_LABELS, isActive, type Emotion, type Job } from "../../types";

function labelOf(job: Job): string {
  if (job.job_type.startsWith("image:")) {
    const expression = job.job_type.slice("image:".length) as Emotion;
    return `画像の生成（${EMOTION_LABELS[expression] ?? expression}）`;
  }
  const labels: Record<string, string> = {
    voice: "音声の生成",
    voice_all: "音声の一括生成",
    voice_sample: "音声サンプルの生成",
    image_all: "画像の生成（全表情）",
    analyze: "台本解析",
    render: "MP4の書き出し",
  };
  return labels[job.job_type] ?? job.job_type;
}

const STATUS_LABELS: Record<Job["status"], string> = {
  queued: "待機中",
  running: "実行中",
  succeeded: "完了",
  failed: "失敗",
};

interface Props {
  jobs: Job[];
  onRetry: (job: Job) => void;
  onDismiss: () => void;
}

/** 生成ジョブの進捗・結果の一覧。失敗したものは再実行できる。 */
export default function JobPanel({ jobs, onRetry, onDismiss }: Props) {
  if (jobs.length === 0) return null;
  const hasFinished = jobs.some((j) => !isActive(j));
  return (
    <div className="card job-panel">
      <div className="row space-between">
        <strong>生成の状況</strong>
        {hasFinished && (
          <button className="link-button" onClick={onDismiss}>
            完了した表示を消す
          </button>
        )}
      </div>
      <ul className="job-list">
        {jobs.map((job) => (
          <li key={job.id} className={`job ${job.status}`}>
            <span className="job-label">{labelOf(job)}</span>
            <span className="badge">{STATUS_LABELS[job.status]}</span>
            {isActive(job) && <progress max={100} value={job.progress} />}
            {job.status === "failed" && (
              <>
                <span className="job-error">{job.error}</span>
                <button onClick={() => onRetry(job)}>再実行</button>
              </>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
