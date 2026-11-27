import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { generationApi } from "../../api/generation";
import type { TimelineItem } from "../../types";
import { audioOffsetSec, clamp } from "./timelineMath";

/** 再生位置(ms)の置き場。毎フレーム更新されるので、必要な部品(再生ヘッド・時計・プレビュー)だけが購読する。 */
export class TimeStore {
  private t = 0;
  private listeners = new Set<() => void>();
  get = () => this.t;
  subscribe = (fn: () => void) => {
    this.listeners.add(fn);
    return () => void this.listeners.delete(fn);
  };
  set(ms: number) {
    if (ms === this.t) return;
    this.t = ms;
    this.listeners.forEach((fn) => fn());
  }
}

export const useTime = (store: TimeStore) => useSyncExternalStore(store.subscribe, store.get);

const VIDEO_DRIFT_MS = 400;

interface Options {
  items: TimelineItem[];
  totalMs: number;
  getVideo: () => HTMLVideoElement | null;
  videoSound: boolean;
}

/**
 * プレビューの再生。時計(performance.now)を基準に、音声(セリフごとに1つのAudio)と元動画を同じ位置に合わせる。
 * 立ち絵・字幕は、再生位置からの計算だけで表示が決まる(ここでは扱わない)。
 */
export function usePlayback({ items, totalMs, getVideo, videoSound }: Options) {
  const store = useRef(new TimeStore()).current;
  const [playing, setPlaying] = useState(false);
  const audios = useRef(new Map<string, { el: HTMLAudioElement; assetId: string }>());
  const itemsRef = useRef(items);
  itemsRef.current = items;
  const totalRef = useRef(totalMs);
  totalRef.current = totalMs;
  const playingRef = useRef(false);
  const wall = useRef({ startedAt: 0, base: 0 });

  const pauseAudios = useCallback(() => audios.current.forEach(({ el }) => el.pause()), []);

  const syncMedia = useCallback(
    (t: number, isPlaying: boolean) => {
      // 音声: 再生範囲に入ったら鳴らし、出たら止める
      const live = new Set<string>();
      for (const item of itemsRef.current) {
        if (item.track_type !== "audio" || !item.audio_asset_id) continue;
        live.add(item.id);
        let entry = audios.current.get(item.id);
        // Audio は必要になるまで作らない(全セリフ分を一度に読み込まない)。再生中は、2秒先までのセリフを先に読み込む
        const needed = isPlaying && t >= item.start_ms - 2000 && t < item.end_ms;
        if (!needed && (!entry || entry.assetId !== item.audio_asset_id)) {
          entry?.el.pause();
          audios.current.delete(item.id);
          continue;
        }
        if (!entry || entry.assetId !== item.audio_asset_id) {
          entry?.el.pause();
          entry = { el: new Audio(generationApi.assetUrl(item.audio_asset_id)), assetId: item.audio_asset_id };
          entry.el.preload = "auto";
          audios.current.set(item.id, entry);
        }
        const { el } = entry;
        const inRange = t >= item.start_ms && t < item.end_ms;
        if (isPlaying && inRange) {
          el.playbackRate = item.playback_speed;
          el.volume = clamp(item.volume, 0, 1); // ブラウザの音量は1まで(1を超える設定は書き出し時に反映)
          if (el.paused) {
            el.currentTime = audioOffsetSec(item.start_ms, t, item.playback_speed);
            void el.play().catch(() => undefined); // 自動再生の制限などで失敗しても、画面は進める
          }
        } else if (!el.paused) {
          el.pause();
        }
      }
      for (const [id, { el }] of audios.current) {
        if (!live.has(id)) {
          el.pause();
          audios.current.delete(id);
        }
      }

      // 元動画: 動画の長さの範囲だけ、同じ位置で再生する
      const video = getVideo();
      if (video) {
        const inVideo = t / 1000 < (video.duration || Infinity);
        if (isPlaying && inVideo) {
          if (Math.abs(video.currentTime * 1000 - t) > VIDEO_DRIFT_MS) video.currentTime = t / 1000;
          if (video.paused) void video.play().catch(() => undefined);
        } else {
          if (!video.paused) video.pause();
          if (inVideo && Math.abs(video.currentTime * 1000 - t) > 50) video.currentTime = t / 1000;
        }
      }
    },
    [getVideo],
  );

  const stop = useCallback(() => {
    playingRef.current = false;
    setPlaying(false);
    pauseAudios();
    getVideo()?.pause();
  }, [getVideo, pauseAudios]);

  const seek = useCallback(
    (ms: number) => {
      const t = clamp(Math.round(ms), 0, Math.max(totalRef.current, 0));
      store.set(t);
      wall.current = { startedAt: performance.now(), base: t };
      pauseAudios(); // 位置が変わったので、鳴らし直す(再生中なら次のフレームで正しい位置から再開)
      syncMedia(t, playingRef.current);
    },
    [pauseAudios, store, syncMedia],
  );

  const play = useCallback(() => {
    if (playingRef.current) return;
    const from = store.get() >= totalRef.current ? 0 : store.get();
    playingRef.current = true;
    setPlaying(true);
    seek(from);
  }, [seek, store]);

  // 再生中は毎フレーム、時計から再生位置を求める
  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    const tick = () => {
      const t = wall.current.base + (performance.now() - wall.current.startedAt);
      if (t >= totalRef.current) {
        store.set(totalRef.current);
        stop();
        return;
      }
      store.set(Math.round(t));
      syncMedia(t, true);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, stop, store, syncMedia]);

  // 編集で項目が変わったら、停止中でも動画の位置などを合わせ直す
  useEffect(() => {
    if (!playingRef.current) syncMedia(store.get(), false);
  }, [items, store, syncMedia]);

  // 元動画の音の入/切
  useEffect(() => {
    const video = getVideo();
    if (video) video.muted = !videoSound;
  }, [getVideo, videoSound]);

  // 画面を離れるときに止める
  useEffect(
    () => () => {
      audios.current.forEach(({ el }) => el.pause());
      audios.current.clear();
    },
    [],
  );

  return { store, playing, play, pause: stop, toggle: () => (playingRef.current ? stop() : play()), seek };
}
