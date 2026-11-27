import type { HistoryState, TimelineItem, TimelineItemPatch } from "../types";
import { http } from "./client";

export const timelineApi = {
  updateItem: (itemId: string, patch: TimelineItemPatch) => http.put<TimelineItem>(`/timeline-items/${itemId}`, patch),
  history: (projectId: string) => http.get<HistoryState>(`/projects/${projectId}/history`),
  undo: (projectId: string) => http.post<HistoryState>(`/projects/${projectId}/history/undo`, {}),
  redo: (projectId: string) => http.post<HistoryState>(`/projects/${projectId}/history/redo`, {}),
};
