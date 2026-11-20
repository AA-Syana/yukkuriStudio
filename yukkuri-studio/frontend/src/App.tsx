import { Link, Route, Routes } from "react-router-dom";
import ProjectListPage from "./pages/ProjectListPage";
import ScenarioPage from "./pages/ScenarioPage";
import UploadPage from "./pages/UploadPage";

export default function App() {
  return (
    <>
      <header className="app-header">
        <Link to="/">AI Yukkuri Studio</Link>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<ProjectListPage />} />
          <Route path="/projects/:projectId/upload" element={<UploadPage />} />
          <Route path="/projects/:projectId/scenario" element={<ScenarioPage />} />
          <Route path="*" element={<p>ページが見つかりません。</p>} />
        </Routes>
      </main>
    </>
  );
}
