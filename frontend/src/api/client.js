const API_BASE = "";

async function request(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const headers = isFormData
    ? { ...(options.headers || {}) }
    : { "Content-Type": "application/json", ...(options.headers || {}) };

  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
    });
  } catch (err) {
    throw new Error(
      "Cannot reach the StoryTube backend (http://127.0.0.1:8000). Make sure the FastAPI server is running."
    );
  }

  let data = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }

  if (!res.ok) {
    const message =
      (data && (data.detail || data.message)) ||
      `Request failed with status ${res.status}`;
    const error = new Error(message);
    error.status = res.status;
    throw error;
  }
  return data;
}

export const api = {
  health: () => request("/api/health"),
  getSettings: () => request("/api/settings"),
  saveSettings: (payload) =>
    request("/api/settings", { method: "PUT", body: JSON.stringify(payload) }),
  checkLocalImageHealth: () => request("/api/local-image/health"),
  getVoices: () => request("/api/voices"),

  listProjects: () => request("/api/projects"),
  createProject: (payload) =>
    request("/api/projects", { method: "POST", body: JSON.stringify(payload) }),
  getProject: (id) => request(`/api/projects/${id}`),
  updateProject: (id, payload) =>
    request(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteProject: (id) => request(`/api/projects/${id}`, { method: "DELETE" }),

  generateTopics: (id) =>
    request(`/api/projects/${id}/topics`, { method: "POST" }),
  selectTopic: (id, payload) =>
    request(`/api/projects/${id}/topics/select`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  generateScript: (id) =>
    request(`/api/projects/${id}/script/generate`, { method: "POST" }),

  generateScenes: (id) =>
    request(`/api/projects/${id}/scenes/generate`, { method: "POST" }),
  saveAllScenes: (id, payload) =>
    request(`/api/projects/${id}/scenes`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  updateScene: (id, sceneIndex, payload) =>
    request(`/api/projects/${id}/scenes/${sceneIndex}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  regenerateSceneText: (id, sceneIndex) =>
    request(`/api/projects/${id}/scenes/${sceneIndex}/regenerate`, {
      method: "POST",
    }),

  previewVoice: (payload) =>
    request("/api/voice/preview", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  startVoiceoverBatch: (id, payload) =>
    request(`/api/projects/${id}/voiceover/generate-all`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  regenerateSceneVoiceover: (id, sceneIndex, payload) =>
    request(`/api/projects/${id}/scenes/${sceneIndex}/voiceover`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  startImagesBatch: (id, payload) =>
    request(`/api/projects/${id}/images/generate-all`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  regenerateSceneImage: (id, sceneIndex, payload = {}) =>
    request(`/api/projects/${id}/scenes/${sceneIndex}/image`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  generatePlaceholderImages: (id) =>
    request(`/api/projects/${id}/images/placeholders`, {
      method: "POST",
    }),
  uploadSceneImage: (id, sceneIndex, file) => {
    const fd = new FormData();
    fd.append("file", file);
    return request(`/api/projects/${id}/scenes/${sceneIndex}/image-upload`, {
      method: "POST",
      body: fd,
    });
  },

  uploadBgm: (id, file) => {
    const fd = new FormData();
    fd.append("file", file);
    return request(`/api/projects/${id}/bgm`, { method: "POST", body: fd });
  },
  deleteBgm: (id) => request(`/api/projects/${id}/bgm`, { method: "DELETE" }),

  startRender: (id, payload) =>
    request(`/api/projects/${id}/render`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getTaskStatus: (id, taskType) =>
    request(`/api/projects/${id}/tasks/${taskType}`),
  stopTask: (id, taskType) =>
    request(`/api/projects/${id}/tasks/${taskType}/stop`, { method: "POST" }),

  generateYouTubePackage: (id) =>
    request(`/api/projects/${id}/youtube/generate`, { method: "POST" }),
  regenerateThumbnail: (id, payload) =>
    request(`/api/projects/${id}/youtube/thumbnail`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  downloadUrl: (id, assetType) => `/api/projects/${id}/download/${assetType}`,
};
