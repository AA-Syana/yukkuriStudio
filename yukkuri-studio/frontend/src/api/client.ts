// fetchの薄いラッパー。通信エラー/HTTPエラーを ApiError に統一する。
// ログインはHttpOnlyのCookieで行う(JavaScriptからトークンには触れない)。開発中はViteの中継で同じオリジンになる。
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// ログイン切れ(401)を検知したときに呼ぶ処理。AuthProvider が登録し、ログイン画面へ戻す。
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { credentials: "same-origin", ...init });
  } catch {
    throw new ApiError(0, "サーバーに接続できません。バックエンドが起動しているか確認してください");
  }
  if (!res.ok) {
    let message = `エラーが発生しました (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = "入力内容が正しくありません";
    } catch {
      /* JSONでないエラー応答はデフォルトメッセージを使う */
    }
    // ログイン・登録の失敗(パスワード違い)や、起動時の確認(/auth/me)は「ログイン切れ」ではないので除く
    if (res.status === 401 && !path.startsWith("/auth/")) onUnauthorized?.();
    throw new ApiError(res.status, message);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const http = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) => request<T>(path, json("POST", body)),
  put: <T>(path: string, body: unknown) => request<T>(path, json("PUT", body)),
  del: (path: string) => request<void>(path, { method: "DELETE" }),
  upload: <T>(path: string, form: FormData) => request<T>(path, { method: "POST", body: form }),
};

export function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : "不明なエラーが発生しました";
}
