import { FormEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { messageOf } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import ErrorBanner from "../components/ErrorBanner";

/** 画面1: ログイン / 新規登録。 */
export default function LoginPage() {
  const { user, loading, login, register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (loading) return <p>読み込み中…</p>;
  if (user) return <Navigate to={from} replace />;

  const registering = mode === "register";
  const mismatch = registering && confirm !== "" && confirm !== password;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (registering && password !== confirm) {
      setError("パスワードが一致しません");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await (registering ? register : login)(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="auth-card card">
      <h1>{registering ? "新規登録" : "ログイン"}</h1>
      <ErrorBanner message={error} onClose={() => setError(null)} />
      <form onSubmit={submit}>
        <label className="field">
          メールアドレス
          <input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="field">
          パスワード{registering && "（8文字以上）"}
          <input
            type="password"
            autoComplete={registering ? "new-password" : "current-password"}
            required
            minLength={registering ? 8 : undefined}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {registering && (
          <label className="field">
            パスワード（確認）
            <input type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
            {mismatch && <span className="field-error">パスワードが一致しません</span>}
          </label>
        )}
        <div className="row">
          <button className="primary" disabled={busy || mismatch}>{registering ? "登録して始める" : "ログイン"}</button>
          <button
            type="button"
            className="link-button"
            onClick={() => {
              setMode(registering ? "login" : "register");
              setError(null);
            }}
          >
            {registering ? "アカウントをお持ちの方はログイン" : "アカウントを作成する"}
          </button>
        </div>
      </form>
    </section>
  );
}
