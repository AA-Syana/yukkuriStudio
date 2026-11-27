import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export default function AppHeader() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <header className="app-header">
      <Link to="/" className="brand">AI Yukkuri Studio</Link>
      {user && (
        <nav>
          <NavLink to="/" end>プロジェクト</NavLink>
          <NavLink to="/characters">キャラクター管理</NavLink>
          <span className="spacer" />
          <span className="user-email">{user.email}</span>
          <button
            className="header-button"
            onClick={async () => {
              await logout();
              navigate("/login", { replace: true });
            }}
          >
            ログアウト
          </button>
        </nav>
      )}
    </header>
  );
}
