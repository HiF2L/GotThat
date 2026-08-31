import {
  FeedCard,
  QuizResult,
  TrackSummary,
  TrackFolder,
  UserMasteryOverview,
  DeepStepResult,
  DeepStep,
} from '../types';

const API_BASE = '/api/v1';

export const apiClient = {
  // 0. User resolution & Settings
  async getActiveUser(): Promise<{ user_id: string; username: string; email: string; preferred_language?: string; preferred_model?: string }> {
    const res = await fetch(`${API_BASE}/users/active`);
    if (!res.ok) throw new Error('Failed to fetch active user');
    return res.json();
  },

  async getUserSettings(userId: string): Promise<{ user_id: string; preferred_language: string; preferred_model: string }> {
    const res = await fetch(`${API_BASE}/users/${userId}/settings`);
    if (!res.ok) throw new Error('Failed to fetch user settings');
    return res.json();
  },

  async updateUserSettings(
    userId: string,
    settings: { preferred_language?: string; preferred_model?: string },
  ): Promise<{ user_id: string; preferred_language: string; preferred_model: string }> {
    const res = await fetch(`${API_BASE}/users/${userId}/settings`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    });
    if (!res.ok) throw new Error('Failed to update user settings');
    return res.json();
  },

  // 1. Quick Feed Endpoints
  async getNextFeedCard(userId: string): Promise<FeedCard> {
    const res = await fetch(`${API_BASE}/feed/next?user_id=${userId}`);
    if (!res.ok) throw new Error('Failed to fetch feed card');
    return res.json();
  },

  async submitQuizAttempt(
    userId: string,
    cardId: string,
    conceptId: string,
    selectedOptionIds: string[],
    responseTimeMs: number = 0,
    yapNote?: string,
  ): Promise<QuizResult> {
    const res = await fetch(`${API_BASE}/feed/attempt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        card_id: cardId,
        concept_id: conceptId,
        selected_option_ids: selectedOptionIds,
        response_time_ms: responseTimeMs,
        yap_text_note: yapNote,
      }),
    });
    if (!res.ok) throw new Error('Failed to submit attempt');
    return res.json();
  },

  async submitVoiceReasoning(
    userId: string,
    cardId: string,
    conceptId: string,
    selectedOptionId: string,
    audioBlob: Blob,
  ): Promise<QuizResult> {
    const formData = new FormData();
    formData.append('audio_file', audioBlob, 'yap_note.webm');
    formData.append('user_id', userId);
    formData.append('card_id', cardId);
    formData.append('concept_id', conceptId);
    formData.append('selected_option_id', selectedOptionId);

    const res = await fetch(`${API_BASE}/feed/voice-reasoning`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) throw new Error('Failed to submit voice reasoning');
    return res.json();
  },

  // 2. Deep Tutor Endpoints
  async startDeepSession(
    userId: string,
    targetConceptId: string,
    initialContext?: string,
    language: string = 'ru',
    depthLevel?: string,
  ): Promise<{ session_id: string; initial_action: any }> {
    const payload: any = {
      user_id: userId,
      target_concept_id: targetConceptId,
      initial_user_context: initialContext,
      language: language,
    };
    if (depthLevel) {
      payload.depth_level = depthLevel;
    }
    const res = await fetch(`${API_BASE}/deep/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error('Failed to start deep session');
    return res.json();
  },

  async getNextTutorAction(sessionId: string, userNotes: string = ''): Promise<any> {
    const query = userNotes ? `?user_notes=${encodeURIComponent(userNotes)}` : '';
    const res = await fetch(`${API_BASE}/deep/action/${sessionId}${query}`);
    if (!res.ok) throw new Error('Failed to get next tutor action');
    return res.json();
  },

  async selectStep(sessionId: string, conceptId: string, userNotes?: string): Promise<any> {
    const res = await fetch(`${API_BASE}/deep/select-step`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        concept_id: conceptId,
        user_notes: userNotes,
      }),
    });
    if (!res.ok) throw new Error('Failed to select concept step');
    return res.json();
  },

  async prefetchNextLesson(sessionId: string, conceptId: string, stepSequence?: number, userNotes?: string): Promise<any> {
    try {
      const res = await fetch(`${API_BASE}/deep/prefetch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          concept_id: conceptId,
          step_sequence: stepSequence,
          user_notes: userNotes,
        }),
      });
      if (res.ok) return await res.json();
    } catch (e) {
      console.warn('Prefetch trigger failed (non-critical):', e);
    }
    return null;
  },

  async transcribeDeepNote(audioBlob: Blob): Promise<{ transcript: string }> {
    const formData = new FormData();
    formData.append('audio_file', audioBlob, 'deep_yap.webm');
    const res = await fetch(`${API_BASE}/deep/transcribe-note`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) throw new Error('Failed to transcribe voice note');
    return res.json();
  },

  async submitStepVerification(
    sessionId: string,
    stepSequence: number,
    selectedOptionIds: string[],
    yapTextNote?: string,
  ): Promise<DeepStepResult> {
    const res = await fetch(`${API_BASE}/deep/submit-step`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        step_sequence: stepSequence,
        selected_option_ids: selectedOptionIds,
        yap_text_note: yapTextNote,
      }),
    });
    if (!res.ok) throw new Error('Failed to submit step answer');
    return res.json();
  },

  async submitProbeAnswer(
    sessionId: string,
    conceptId: string,
    selectedOptionId: string,
    userNotes?: string,
  ): Promise<any> {
    const res = await fetch(`${API_BASE}/deep/submit-probe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        concept_id: conceptId,
        selected_option_id: selectedOptionId,
        user_notes: userNotes,
      }),
    });
    if (!res.ok) throw new Error('Failed to submit probe answer');
    return res.json();
  },

  async askTutorQuestion(
    sessionId: string,
    stepSequence: number,
    question: string,
  ): Promise<{ answer_markdown: string }> {
    const res = await fetch(`${API_BASE}/deep/ask-tutor`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        step_sequence: stepSequence,
        question: question,
      }),
    });
    if (!res.ok) throw new Error('Failed to ask tutor');
    return res.json();
  },

  async regenerateStep(
    sessionId: string,
    conceptId?: string,
    stepSequence?: number,
    userNotes?: string,
  ): Promise<DeepStep> {
    const res = await fetch(`${API_BASE}/deep/regenerate-step`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        concept_id: conceptId,
        step_sequence: stepSequence,
        user_notes: userNotes,
      }),
    });
    if (!res.ok) throw new Error('Failed to regenerate step');
    return res.json();
  },

  async synthesizeLessonSpeech(
    text: string,
    voice: string = 'alloy',
    speed: number = 1.0,
  ): Promise<Blob> {
    const res = await fetch(`${API_BASE}/deep/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text,
        voice,
        speed,
      }),
    });
    if (!res.ok) throw new Error('Failed to synthesize speech');
    return await res.blob();
  },

  // 3. Knowledge Map & Track Endpoints
  async listTracks(): Promise<TrackSummary[]> {
    const res = await fetch(`${API_BASE}/tracks/list`);
    if (!res.ok) throw new Error('Failed to fetch tracks');
    return res.json();
  },

  async getTrackMastery(trackId: string, userId: string): Promise<UserMasteryOverview> {
    const res = await fetch(`${API_BASE}/tracks/${trackId}/mastery?user_id=${userId}`);
    if (!res.ok) throw new Error('Failed to fetch track mastery');
    return res.json();
  },

  async generateCustomTrack(
    userId: string,
    topicQuery: string,
    depthLevel: string = 'high',
    userWishes?: string,
    folderId?: string | null,
  ): Promise<TrackSummary> {
    const res = await fetch(`${API_BASE}/tracks/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        topic_query: topicQuery,
        depth_level: depthLevel,
        user_wishes: userWishes,
        folder_id: folderId || undefined,
      }),
    });
    if (!res.ok) throw new Error('Failed to generate track');
    return res.json();
  },

  async expandTrack(
    trackId: string,
    userId: string,
    depthLevel: string = 'high',
    userNotes?: string,
  ): Promise<TrackSummary & { dag?: any; message?: string }> {
    const res = await fetch(`${API_BASE}/tracks/${encodeURIComponent(trackId)}/expand`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        depth_level: depthLevel,
        user_notes: userNotes,
      }),
    });
    if (!res.ok) throw new Error('Failed to expand track volume');
    return res.json();
  },

  async deleteTrack(trackId: string): Promise<{ status: string }> {
    const res = await fetch(`${API_BASE}/tracks/${trackId}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error('Failed to delete track');
    return res.json();
  },

  // 4. Folder & Track Organization Endpoints
  async listFolders(): Promise<TrackFolder[]> {
    const res = await fetch(`${API_BASE}/tracks/folders`);
    if (!res.ok) throw new Error('Failed to fetch folders');
    return res.json();
  },

  async createFolder(payload: {
    name: string;
    description?: string;
    color?: string;
    icon?: string;
    is_pinned?: boolean;
  }): Promise<TrackFolder> {
    const res = await fetch(`${API_BASE}/tracks/folders`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error('Failed to create folder');
    return res.json();
  },

  async updateFolder(
    folderId: string,
    payload: {
      name?: string;
      description?: string;
      color?: string;
      icon?: string;
      is_pinned?: boolean;
      order_index?: number;
    },
  ): Promise<TrackFolder> {
    const res = await fetch(`${API_BASE}/tracks/folders/${encodeURIComponent(folderId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error('Failed to update folder');
    return res.json();
  },

  async deleteFolder(folderId: string): Promise<{ status: string; folder_id: string }> {
    const res = await fetch(`${API_BASE}/tracks/folders/${encodeURIComponent(folderId)}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error('Failed to delete folder');
    return res.json();
  },

  async updateTrackOrganization(
    trackId: string,
    payload: {
      folder_id?: string | null;
      is_pinned?: boolean;
    },
  ): Promise<{ track_id: string; slug: string; title: string; folder_id: string | null; is_pinned: boolean }> {
    const res = await fetch(`${API_BASE}/tracks/${encodeURIComponent(trackId)}/organization`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error('Failed to update track organization');
    return res.json();
  },
};
