import { DragEvent, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { messageOf } from "../api/client";
import { projectsApi } from "../api/projects";
import { videosApi } from "../api/videos";
import ErrorBanner from "../components/ErrorBanner";
import { formatDuration } from "../format";
import { useAsync } from "../hooks/useAsync";

export default function UploadPage() {
  const { projectId = "" } = useParams();
  const project = useAsync(() => projectsApi.get(projectId), [projectId]);
  const video = useAsync(() => videosApi.get(projectId), [projectId]);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nameDraft, setNameDraft] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function upload(file: File | undefined) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".mp4")) {
      setError("MP4形式の動画を選択してください");
      return;
    }
    setError(null);
    setUploading(true);
    try {
      video.setData(await videosApi.upload(projectId, file));
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setUploading(false);
    }
  }

  async function commitName() {
    const next = nameDraft?.trim();
    setNameDraft(null);
    if (!next || next === project.data?.title) return;
    try {
      project.setData(await projectsApi.update(projectId, { title: next }));
    } catch (e) {
      setError(messageOf(e));
    }
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    void upload(e.dataTransfer.files[0]);
  };

  const v = video.data;
  return (
    <section>
      <p>
        <Link to={`/projects/${projectId}/editor`}>← 動画編集に戻る</Link>
      </p>
      <h1>元動画のアップロード（任意）</h1>
      <ErrorBanner message={project.error ?? video.error} />
      <ErrorBanner message={error} onClose={() => setError(null)} />

      <label className="field">
        プロジェクト名
        <input
          value={nameDraft ?? project.data?.title ?? ""}
          onChange={(e) => setNameDraft(e.target.value)}
          onBlur={() => void commitName()}
          maxLength={100}
        />
      </label>

      <div
        className={`dropzone ${dragging ? "dragging" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        {uploading ? (
          <p>アップロード・解析中…（動画が大きい場合は時間がかかります）</p>
        ) : (
          <>
            <p>ここにMP4をドラッグ＆ドロップ</p>
            <button onClick={() => inputRef.current?.click()}>ファイルを選択</button>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept=".mp4,video/mp4"
          hidden
          onChange={(e) => {
            void upload(e.target.files?.[0]);
            e.target.value = ""; // 同じファイルを再選択できるようにする
          }}
        />
      </div>

      {v && (
        <div className="card">
          <h2>{v.original_filename}</h2>
          <dl className="info">
            <dt>長さ</dt>
            <dd>{formatDuration(v.duration_ms)}</dd>
            <dt>解像度</dt>
            <dd>
              {v.width} × {v.height}
            </dd>
            <dt>フレームレート</dt>
            <dd>{v.fps ? `${v.fps} fps` : "不明"}</dd>
          </dl>
          <video className="preview" controls src={`${videosApi.streamUrl(projectId)}?v=${v.id}`} />
        </div>
      )}

    </section>
  );
}
