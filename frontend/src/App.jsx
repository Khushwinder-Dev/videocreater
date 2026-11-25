import React, { useCallback, useEffect, useState } from "react";
import { api } from "./api/client";
import Navbar from "./components/Navbar";
import ProjectsPage from "./pages/ProjectsPage";
import SettingsPage from "./pages/SettingsPage";
import StudioWizard from "./pages/StudioWizard";

export default function App() {
  const [view, setView] = useState("projects"); // 'projects' | 'wizard' | 'settings'
  const [activeProject, setActiveProject] = useState(null);
  const [health, setHealth] = useState(null);
  const [voices, setVoices] = useState({ hindi: [], english: [] });

  const refreshHealth = useCallback(() => {
    api.health().then(setHealth).catch(() => {});
  }, []);

  useEffect(() => {
    refreshHealth();
    api.getVoices().then(setVoices).catch(() => {});
  }, [refreshHealth]);

  const handleOpenProject = async (projectId) => {
    try {
      const proj = await api.getProject(projectId);
      setActiveProject(proj);
      setView("wizard");
    } catch (err) {
      alert(err.message);
    }
  };

  const handleNewProject = () => {
    setActiveProject(null);
    setView("wizard");
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <Navbar
        health={health}
        activeView={view}
        activeProject={activeProject}
        onGoProjects={() => setView("projects")}
        onGoSettings={() => setView("settings")}
        onNewProject={handleNewProject}
      />

      {view === "projects" && (
        <ProjectsPage
          onOpenProject={handleOpenProject}
          onCreateNew={handleNewProject}
        />
      )}

      {view === "settings" && (
        <SettingsPage onSettingsSaved={() => refreshHealth()} />
      )}

      {view === "wizard" && (
        <StudioWizard
          project={activeProject}
          voices={voices}
          onProjectChange={setActiveProject}
        />
      )}
    </div>
  );
}
