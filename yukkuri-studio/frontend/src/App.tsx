import { Route, Routes } from "react-router-dom";
import RequireAuth from "./auth/RequireAuth";
import AppHeader from "./components/AppHeader";
import CharacterCreatePage from "./pages/CharacterCreatePage";
import EditorPage from "./pages/EditorPage";
import LoginPage from "./pages/LoginPage";
import ProjectCreatePage from "./pages/ProjectCreatePage";
import ProjectListPage from "./pages/ProjectListPage";
import ScriptCreatePage from "./pages/ScriptCreatePage";
import UploadPage from "./pages/UploadPage";

export default function App() {
  return (
    <>
      <AppHeader />
      <main className="app-main">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<RequireAuth />}>
            <Route path="/" element={<ProjectListPage />} />
            <Route path="/projects/new" element={<ProjectCreatePage />} />
            <Route path="/characters" element={<CharacterCreatePage />} />
            <Route path="/projects/:projectId/script" element={<ScriptCreatePage />} />
            <Route path="/projects/:projectId/editor" element={<EditorPage />} />
            <Route path="/projects/:projectId/upload" element={<UploadPage />} />
          </Route>
          <Route path="*" element={<p>ページが見つかりません。</p>} />
        </Routes>
      </main>
    </>
  );
}
