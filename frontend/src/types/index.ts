export interface QuizOption {
  id: string;
  text: string;
  is_correct?: boolean;
  explanation?: string;
}

export interface FeedCard {
  card_id: string;
  concept_id: string;
  concept_title: string;
  concept_code: string;
  track_title: string;
  item_type: string;
  prompt_markdown: string;
  options: QuizOption[];
  card_mode: 'srs' | 'probe';
  current_mastery: number;
  current_uncertainty: number;
  allow_voice_reasoning: boolean;
}

export interface VoiceReasoningAnalysis {
  logical_coherence_score: number;
  demonstrated_understanding: string[];
  misconceptions_detected: string[];
  reasoning_summary: string;
  speech_hesitation_detected: boolean;
  is_genuine_understanding: boolean;
}

export interface QuizResult {
  is_correct: boolean;
  correct_option_ids: string[];
  explanation: string;
  prior_mastery: number;
  posterior_mastery: number;
  prior_uncertainty: number;
  posterior_uncertainty: number;
  next_review_due?: string;
  voice_analysis?: VoiceReasoningAnalysis;
}

export interface DAGNode {
  id: string;
  code: string;
  title: string;
  slug?: string;
  status: 'completed' | 'active' | 'pending' | 'remediation';
  mastery_prob: number;
}

export interface PlannedDAG {
  mermaid_code: string;
  nodes: DAGNode[];
  edges: { source: string; target: string; relation_type: string }[];
  total_nodes: number;
  completed_nodes: number;
}

export interface VisualArtifact {
  type: 'svg' | 'mermaid' | 'image' | 'none';
  payload: string;
  alt_text?: string;
}

export interface VerificationChallenge {
  item_id: string;
  prompt_markdown: string;
  options: QuizOption[];
  allow_voice: boolean;
}

export interface QnAPair {
  question: string;
  answer: string;
}

export interface DeepStep {
  session_id: string;
  concept_id: string;
  concept_title: string;
  concept_slug?: string;
  track_id?: string;
  track_slug?: string;
  step_sequence: number;
  step_type: string;
  explanation_markdown: string;
  visual_artifact?: VisualArtifact;
  verification_challenge?: VerificationChallenge;
  is_session_completed: boolean;
  dag_state?: PlannedDAG;
  qa_history?: QnAPair[];
}

export interface DeepStepResult {
  session_id: string;
  step_sequence: number;
  is_correct: boolean;
  explanation: string;
  remediation_required: boolean;
  remediation_node?: DAGNode;
  remediation_node_inserted?: DAGNode;
  next_step_ready: boolean;
}

export interface TrackFolder {
  id: string;
  name: string;
  description?: string;
  color?: string;
  icon?: string;
  is_pinned: boolean;
  order_index: number;
  track_count?: number;
  created_at?: string;
}

export interface TrackSummary {
  track_id: string;
  slug: string;
  title: string;
  description?: string;
  user_wishes?: string;
  depth_level?: 'low' | 'medium' | 'high' | string;
  folder_id?: string | null;
  is_pinned?: boolean;
  total_concepts: number;
  concepts: { id: string; slug?: string; code: string; title: string; summary: string }[];
}

export interface ConceptMasterySummary {
  concept_id: string;
  concept_code: string;
  title: string;
  slug?: string;
  mastery_prob: number;
  uncertainty: number;
  retrievability: number;
  stability: number;
  is_mastered: boolean;
  is_due_for_review: boolean;
}

export interface UserMasteryOverview {
  user_id: string;
  track_id: string;
  track_slug?: string;
  track_title: string;
  track_description?: string;
  track_user_wishes?: string;
  track_depth_level?: 'low' | 'medium' | 'high' | string;
  track_folder_id?: string | null;
  track_is_pinned?: boolean;
  total_concepts: number;
  mastered_concepts: number;
  in_progress_concepts: number;
  concepts: ConceptMasterySummary[];
}
