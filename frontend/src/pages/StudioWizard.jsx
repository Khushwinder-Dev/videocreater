import React, { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import ErrorBanner from "../components/ErrorBanner";
import WizardStepper from "../components/WizardStepper";
import Step1Setup from "../components/steps/Step1Setup";
import Step2Topics from "../components/steps/Step2Topics";
import Step3Script from "../components/steps/Step3Script";
import Step4Scenes from "../components/steps/Step4Scenes";
import Step5Voiceover from "../components/steps/Step5Voiceover";
import Step6Images from "../components/steps/Step6Images";
import Step7VideoRender from "../components/steps/Step7VideoRender";
import Step8YouTubePackage from "../components/steps/Step8YouTubePackage";

export default function StudioWizard({
  project,
  voices,
  onProjectChange,
}) {
  const [activeStep, setActiveStep] = useState(project?.current_step || 1);
  const [error, setError] = useState("");

  useEffect(() => {
    if (project?.id) {
      setActiveStep(project.current_step || 1);
    } else {
      setActiveStep(1);
    }
    setError("");
  }, [project?.id]);

  const maxReachedStep = useMemo(() => {
    if (!project) return 1;
    let maxStep = Math.max(2, project.current_step || 1);
    if (project.selected_topic) maxStep = Math.max(maxStep, 3);
    if (project.script) maxStep = Math.max(maxStep, 4);
    if (project.scenes?.length > 0) maxStep = Math.max(maxStep, 5);
    const allAudio = project.scenes?.length > 0 && project.scenes.every((s) => Boolean(s.audio_url));
    if (allAudio) maxStep = Math.max(maxStep, 6);
    const allImg = project.scenes?.length > 0 && project.scenes.every((s) => Boolean(s.image_url));
    if (allImg) maxStep = Math.max(maxStep, 7);
    if (project.video_url) maxStep = Math.max(maxStep, 8);
    return Math.min(8, maxStep);
  }, [project]);

  const refreshProject = useCallback(async () => {
    if (!project?.id) return null;
    const latest = await api.getProject(project.id);
    onProjectChange(latest);
    return latest;
  }, [project?.id, onProjectChange]);

  const goToStep = async (stepNum) => {
    setError("");
    setActiveStep(stepNum);
    if (project?.id && stepNum > (project.current_step || 1)) {
      try {
        const updated = await api.updateProject(project.id, { current_step: stepNum });
        onProjectChange(updated);
      } catch {
        // non-blocking
      }
    }
  };

  // Step 1
  const handleStep1Save = async (payload) => {
    setError("");
    try {
      let updated;
      if (!project?.id) {
        updated = await api.createProject(payload);
        updated = await api.updateProject(updated.id, { current_step: 2 });
      } else {
        updated = await api.updateProject(project.id, {
          ...payload,
          current_step: Math.max(2, project.current_step || 1),
        });
      }
      onProjectChange(updated);
      setActiveStep(2);
    } catch (err) {
      setError(err.message);
    }
  };

  // Step 2
  const handleGenerateTopics = async () => {
    setError("");
    try {
      const updated = await api.generateTopics(project.id);
      onProjectChange(updated);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleSelectTopic = async (payload) => {
    setError("");
    try {
      const updated = await api.selectTopic(project.id, payload);
      onProjectChange(updated);
      setActiveStep(3);
    } catch (err) {
      setError(err.message);
    }
  };

  // Step 3
  const handleGenerateScript = async () => {
    setError("");
    try {
      const updated = await api.generateScript(project.id);
      onProjectChange(updated);
      return updated;
    } catch (err) {
      setError(err.message);
      return null;
    }
  };

  const handleSaveScript = async (scriptText) => {
    setError("");
    try {
      const updated = await api.updateProject(project.id, { script: scriptText });
      onProjectChange(updated);
      return updated;
    } catch (err) {
      setError(err.message);
      throw err;
    }
  };

  // Step 4
  const handleGenerateScenes = async () => {
    setError("");
    try {
      const updated = await api.generateScenes(project.id);
      onProjectChange(updated);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleSaveAllScenes = async (payload) => {
    setError("");
    try {
      const updated = await api.saveAllScenes(project.id, payload);
      onProjectChange(updated);
    } catch (err) {
      setError(err.message);
      throw err;
    }
  };

  const handleRegenerateSingleScene = async (sceneIndex) => {
    setError("");
    try {
      const updated = await api.regenerateSceneText(project.id, sceneIndex);
      onProjectChange(updated);
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div>
      <WizardStepper
        activeStep={activeStep}
        maxReachedStep={maxReachedStep}
        onStepClick={(s) => goToStep(s)}
      />

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <ErrorBanner error={error} onDismiss={() => setError("")} />

        {activeStep === 1 && (
          <Step1Setup project={project} onSaveAndContinue={handleStep1Save} />
        )}

        {activeStep === 2 && project && (
          <Step2Topics
            project={project}
            onGenerateTopics={handleGenerateTopics}
            onSelectTopic={handleSelectTopic}
          />
        )}

        {activeStep === 3 && project && (
          <Step3Script
            project={project}
            onGenerateScript={handleGenerateScript}
            onSaveScript={handleSaveScript}
            onProceedToScenes={() => goToStep(4)}
          />
        )}

        {activeStep === 4 && project && (
          <Step4Scenes
            project={project}
            onGenerateScenes={handleGenerateScenes}
            onSaveAllScenes={handleSaveAllScenes}
            onRegenerateSingleScene={handleRegenerateSingleScene}
            onProceedToVoiceover={() => goToStep(5)}
          />
        )}

        {activeStep === 5 && project && (
          <Step5Voiceover
            project={project}
            voices={voices}
            onRefreshProject={refreshProject}
            onError={setError}
            onProceedToImages={() => goToStep(6)}
          />
        )}

        {activeStep === 6 && project && (
          <Step6Images
            project={project}
            onRefreshProject={refreshProject}
            onError={setError}
            onProceedToRender={() => goToStep(7)}
          />
        )}

        {activeStep === 7 && project && (
          <Step7VideoRender
            project={project}
            onRefreshProject={refreshProject}
            onError={setError}
            onProceedToYouTube={() => goToStep(8)}
          />
        )}

        {activeStep === 8 && project && (
          <Step8YouTubePackage
            project={project}
            onRefreshProject={refreshProject}
            onError={setError}
          />
        )}
      </main>
    </div>
  );
}
