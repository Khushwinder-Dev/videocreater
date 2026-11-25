from typing import List, Literal, Optional
from pydantic import BaseModel, Field


LanguageType = Literal["hindi", "english"]
GenreType = Literal["moral_stories", "kids", "mythology", "mystery", "horror"]


class TopicOption(BaseModel):
    title: str
    hook: str


class TopicsListResponse(BaseModel):
    topics: List[TopicOption]


class ProjectCreateRequest(BaseModel):
    title: Optional[str] = ""
    language: LanguageType = "english"
    genre: GenreType = "moral_stories"
    target_length_min: int = Field(default=10, ge=0, le=30)
    target_duration_sec: Optional[int] = Field(default=None, ge=15, le=1800)


class ProjectUpdateRequest(BaseModel):
    title: Optional[str] = None
    language: Optional[LanguageType] = None
    genre: Optional[GenreType] = None
    target_length_min: Optional[int] = Field(default=None, ge=0, le=30)
    target_duration_sec: Optional[int] = Field(default=None, ge=15, le=1800)
    current_step: Optional[int] = Field(default=None, ge=1, le=8)
    selected_topic: Optional[str] = None
    selected_hook: Optional[str] = None
    script: Optional[str] = None
    character_bible: Optional[str] = None
    voice_id: Optional[str] = None
    bgm_volume: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    auto_duck: Optional[bool] = None
    burn_subtitles: Optional[bool] = None


class TopicSelectRequest(BaseModel):
    title: str
    hook: str = ""


class SceneItem(BaseModel):
    scene_index: int
    narration: str
    image_prompt: str


class SceneBreakdownResponse(BaseModel):
    character_bible: str
    scenes: List[SceneItem]


class SceneUpdateRequest(BaseModel):
    narration: Optional[str] = None
    image_prompt: Optional[str] = None


class ScenesBulkUpdateRequest(BaseModel):
    character_bible: Optional[str] = None
    scenes: List[SceneItem]


class VoicePreviewRequest(BaseModel):
    language: LanguageType
    voice_id: str


class VoiceBatchRequest(BaseModel):
    voice_id: str
    force_regenerate: bool = False


class ImagesBatchRequest(BaseModel):
    force_regenerate: bool = False
    provider: Optional[Literal["local_sd", "gemini"]] = None
    test_one: bool = False


class SingleImageRegenRequest(BaseModel):
    provider: Optional[Literal["local_sd", "gemini"]] = None
    new_seed: bool = False


class AppSettingsUpdateRequest(BaseModel):
    image_provider: Optional[Literal["local_sd", "gemini"]] = None
    fastsd_url: Optional[str] = None
    upscayl_bin: Optional[str] = None
    steps: Optional[int] = Field(default=None, ge=4, le=6)
    guidance_scale: Optional[float] = Field(default=None, ge=1.0, le=1.5)
    upscale_enabled: Optional[bool] = None


class VideoRenderRequest(BaseModel):
    bgm_volume: float = Field(default=0.18, ge=0.0, le=1.0)
    auto_duck: bool = True
    burn_subtitles: bool = True
    test_preview_15s: bool = False


class ThumbnailConcept(BaseModel):
    concept_title: str
    visual_description: str
    overlay_text: str
    accent_color: str = "#FFD166"
    image_path: Optional[str] = None


class YouTubePackageModel(BaseModel):
    titles: List[str]
    description: str
    tags: List[str]
    hashtags: List[str]
    thumbnail_concepts: List[ThumbnailConcept]


class ThumbnailRegenerateRequest(BaseModel):
    concept_index: int = Field(ge=0, le=2)
    overlay_text: Optional[str] = None
    visual_description: Optional[str] = None
    source_scene_index: Optional[int] = None
    use_fresh_ai_bg: bool = True
