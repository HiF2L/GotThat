import React, { useEffect, useState, useRef } from 'react';
import { apiClient } from '../../api/client';
import { PlannedDAG, DeepStep, DeepStepResult } from '../../types';
import { StepViewer } from './StepViewer';
import { VerificationLock } from './VerificationLock';
import { LatexRenderer } from '../common/LatexRenderer';
import { VoiceRecorder } from '../common/VoiceRecorder';
import { MermaidViewer } from '../common/MermaidViewer';
import { ExpandTrackModal } from '../common/ExpandTrackModal';
import { AVAILABLE_AI_MODELS } from '../common/SettingsModal';
import {
  Loader2,
  GitBranch,
  CheckCircle,
  CheckCircle2,
  Circle,
  Play,
  Flame,
  Cpu,
  MessageSquare,
  Sparkles,
  Compass,
  Map,
  ChevronLeft,
  ChevronRight,
  Network,
  X,
  Layers,
  Terminal,
} from 'lucide-react';

interface DeepTutorScreenProps {
  userId: string;
  targetConceptId?: string;
  isActive?: boolean;
  language?: 'ru' | 'en';
  currentModel?: string;
  ttsVoice?: string;
  skipProbing?: boolean;
  onNavigateToFeed?: () => void;
  onNavigateToMap?: () => void;
  onActiveConceptChange?: (conceptId: string, trackId?: string) => void;
}

export const DeepTutorScreen: React.FC<DeepTutorScreenProps> = ({
  userId,
  targetConceptId,
  isActive = true,
  language = 'ru',
  currentModel = 'kimi-k3',
  ttsVoice = 'alloy',
  skipProbing = false,
  onNavigateToFeed,
  onNavigateToMap,
  onActiveConceptChange,
}) => {
  const activeModelMeta = AVAILABLE_AI_MODELS.find(
    (m) => m.id.toLowerCase() === (currentModel || 'kimi-k3').toLowerCase()
  );
  const activeModelDisplayName = activeModelMeta ? activeModelMeta.name : (currentModel || 'Kimi K3');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentPhase, setCurrentPhase] = useState<string>('idle'); // idle, probing, planning, teaching, completed
  const [dagPlan, setDagPlan] = useState<PlannedDAG | null>(null);
  const [currentStep, setCurrentStep] = useState<DeepStep | null>(null);
  const [probeQuestion, setProbeQuestion] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [loadingMessage, setLoadingMessage] = useState<string>('Synthesizing atomic lesson...');
  const [yapNote, setYapNote] = useState<string>('');
  const [probeNote, setProbeNote] = useState<string>('');
  const [isProbeTranscribing, setIsProbeTranscribing] = useState<boolean>(false);
  const [isTranscribingAudio, setIsTranscribingAudio] = useState<boolean>(false);
  const [selectedProbeOptionId, setSelectedProbeOptionId] = useState<string | null>(null);
  const [loadingProgress, setLoadingProgress] = useState<number>(15);
  const [loadingTimeLeft, setLoadingTimeLeft] = useState<number>(8);
  const [streamingContent, setStreamingContent] = useState<string>('');
  const [planningLogs, setPlanningLogs] = useState<string[]>([]);

  useEffect(() => {
    if (!loading) {
      setLoadingProgress(15);
      setLoadingTimeLeft(8);
      return;
    }
    const timer = setInterval(() => {
      setLoadingProgress((prev) => (prev < 90 ? prev + Math.floor(Math.random() * 8) + 4 : Math.min(prev + 1, 95)));
      setLoadingTimeLeft((prev) => (prev > 1 ? prev - 1 : 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [loading]);

  const loadedTargetRef = useRef<string | undefined>(undefined);
  const isNavigatingRef = useRef<boolean>(false);
  const isStartingSessionRef = useRef<boolean>(false);

  // Lazy & idempotent session start (only triggered when tab is active and target has changed)
  useEffect(() => {
    if (!isActive || !targetConceptId) return;

    if (targetConceptId !== loadedTargetRef.current) {
      const isAlreadyActive =
        currentStep &&
        (currentStep.concept_id === targetConceptId ||
          currentStep.concept_slug === targetConceptId ||
          currentStep.track_id === targetConceptId ||
          currentStep.track_slug === targetConceptId);

      if (!isAlreadyActive && !isStartingSessionRef.current) {
        loadedTargetRef.current = targetConceptId;
        startSession(targetConceptId, skipProbing);
      }
    } else if (!sessionId && !isStartingSessionRef.current) {
      startSession(targetConceptId, skipProbing);
    }
  }, [targetConceptId, isActive, skipProbing]);

  // Initialize Deep Learning Session
  const startSession = async (conceptId?: string, overrideSkipProbing?: boolean) => {
    if (isStartingSessionRef.current) return;
    isStartingSessionRef.current = true;
    setProbeQuestion(null);
    setSelectedProbeOptionId(null);
    setCurrentStep(null); // CRITICAL: Reset step so old lesson never renders below probing test!
    setDagPlan(null);
    setLoading(true);
    setStreamingContent('');
    setPlanningLogs([]);

    try {
      const target = conceptId || targetConceptId || '';
      loadedTargetRef.current = target;
      if (target) {
        localStorage.setItem('got_it_deep_concept_id', target);
      }
      const effectiveSkipProbing =
        overrideSkipProbing !== undefined
          ? overrideSkipProbing
          : Boolean(skipProbing || localStorage.getItem('got_it_deep_skip_probing') === 'true');

      if (effectiveSkipProbing) {
        setLoadingMessage('Инициализация курса и проектирование учебного плана...');
        await apiClient.streamCurriculum(
          userId,
          target,
          yapNote || 'Starting study session.',
          language,
          undefined,
          true,
          {
            onLog: (msg) => {
              setLoadingMessage(msg);
              setPlanningLogs((prev) => (prev.includes(msg) ? prev : [...prev, msg]));
            },
            onPlanReady: (p) => {
              setSessionId(p.sessionId);
              setDagPlan(p.dag);
              setCurrentPhase('teaching');
            },
            onLessonStart: (l) => {
              setLoadingMessage(`Синтез урока: ${l.title}...`);
              setStreamingContent('');
            },
            onToken: (tok) => {
              setStreamingContent((prev) => prev + tok);
            },
            onStepReady: (step) => {
              setCurrentStep(step);
              loadedTargetRef.current = step.concept_id;
              if (onActiveConceptChange) {
                onActiveConceptChange(step.concept_id, step.track_slug || step.track_id);
              }
              setLoading(false);
              setStreamingContent('');
            },
            onProbing: (action) => {
              handleTutorActionResponse(action);
            },
            onError: (err) => {
              console.warn('streamCurriculum error, fallback to startDeepSession:', err);
              apiClient
                .startDeepSession(userId, target, yapNote, language, undefined, true)
                .then((res) => {
                  setSessionId(res.session_id);
                  handleTutorActionResponse(res.initial_action, res.session_id);
                })
                .catch(() => {
                  setLoading(false);
                  alert('Could not start deep session. Ensure backend is running.');
                });
            },
          }
        );
        return;
      }

      setLoadingMessage('Загрузка материалов курса из базы знаний...');
      const res = await apiClient.startDeepSession(
        userId,
        target,
        yapNote || 'Starting study session.',
        language,
        undefined,
        false,
      );
      setSessionId(res.session_id);
      handleTutorActionResponse(res.initial_action, res.session_id);
    } catch (err: any) {
      console.error('Failed to start deep session:', err);
      alert('Could not start deep session. Ensure backend is running.');
      setLoading(false);
    } finally {
      isStartingSessionRef.current = false;
    }
  };

  const handleSelectConceptNode = async (
    conceptId: string,
    activeSessionId?: string,
    overrideDag?: PlannedDAG | null,
    force?: boolean
  ) => {
    if (!userId) return;
    if (!force && (loading || isNavigatingRef.current)) return;
    isNavigatingRef.current = true;
    loadedTargetRef.current = conceptId;
    setLoading(true);
    setStreamingContent('');
    setLoadingMessage('Синтез урока в реальном времени...');

    const currentSid = activeSessionId || sessionId;
    const currentDag = overrideDag || dagPlan;

    try {
      if (currentSid && currentDag?.nodes?.some((n) => n.id === conceptId || n.slug === conceptId)) {
        try {
          await apiClient.streamLessonStep(
            currentSid,
            conceptId,
            yapNote,
            (token) => {
              setStreamingContent((prev) => prev + token);
            },
            (step) => {
              setCurrentStep(step);
              const activeConceptKey = step.concept_id;
              loadedTargetRef.current = activeConceptKey;
              if (onActiveConceptChange) {
                onActiveConceptChange(
                  activeConceptKey,
                  step.track_slug || step.track_id
                );
              }
              setLoading(false);
              setStreamingContent('');
            },
            (err) => {
              console.warn('Streaming step fallback to selectStep:', err);
              apiClient.selectStep(currentSid, conceptId, yapNote).then((action) => {
                handleTutorActionResponse(action, currentSid);
              });
            }
          );
          return;
        } catch (streamErr) {
          console.warn('Streaming step error, falling back to selectStep:', streamErr);
          const action = await apiClient.selectStep(currentSid, conceptId, yapNote);
          handleTutorActionResponse(action, currentSid);
        }
      } else {
        const sessionRes = await apiClient.startDeepSession(userId, conceptId, yapNote, language);
        if (sessionRes.session_id) {
          setSessionId(sessionRes.session_id);
          handleTutorActionResponse(sessionRes.initial_action, sessionRes.session_id);
        }
      }
    } catch (err) {
      console.error('Failed to switch concept:', err);
      setLoading(false);
      setStreamingContent('');
    } finally {
      isNavigatingRef.current = false;
    }
  };

  const streamSessionPlan = async (sid: string) => {
    const target = targetConceptId || loadedTargetRef.current || '';
    setLoading(true);
    setStreamingContent('');
    setPlanningLogs([]);
    setLoadingMessage('Инициализация курса и проектирование учебного плана...');

    try {
      await apiClient.streamCurriculum(
        userId,
        target,
        yapNote || 'Starting study session.',
        language,
        undefined,
        true,
        {
          onLog: (msg) => {
            setLoadingMessage(msg);
            setPlanningLogs((prev) => (prev.includes(msg) ? prev : [...prev, msg]));
          },
          onPlanReady: (p) => {
            setSessionId(p.sessionId);
            setDagPlan(p.dag);
            setCurrentPhase('teaching');
          },
          onLessonStart: (l) => {
            setLoadingMessage(`Синтез урока: ${l.title}...`);
            setStreamingContent('');
          },
          onToken: (tok) => {
            setStreamingContent((prev) => prev + tok);
          },
          onStepReady: (step) => {
            setCurrentStep(step);
            loadedTargetRef.current = step.concept_id;
            if (onActiveConceptChange) {
              onActiveConceptChange(step.concept_id, step.track_slug || step.track_id);
            }
            setLoading(false);
            setStreamingContent('');
          },
          onProbing: (action) => {
            handleTutorActionResponse(action, sid);
          },
          onError: (err) => {
            console.error('streamSessionPlan error:', err);
            setLoading(false);
            alert('Не удалось составить план курса. Пожалуйста, попробуйте еще раз.');
          },
        },
        sid,
      );
    } catch (streamErr) {
      console.error('streamSessionPlan failed:', streamErr);
      setLoading(false);
    }
  };

  const handleTutorActionResponse = (actionData: any, activeSessionId?: string) => {
    if (!actionData) return;
    const phase = actionData.phase;
    const currentSid = activeSessionId || sessionId;
    setCurrentPhase(phase);

    if (phase === 'probing') {
      setCurrentStep(null); // Explicitly ensure currentStep is null during probing
      setProbeQuestion(actionData.probe_question);
      setLoading(false);
    } else if (phase === 'plan_needed') {
      if (currentSid) {
        streamSessionPlan(currentSid);
      }
    } else if (phase === 'plan_ready') {
      setDagPlan(actionData.dag);
      setLoadingMessage('Запуск первого урока...');
      const firstConceptId = actionData.dag?.nodes?.[0]?.id || actionData.dag?.nodes?.[0]?.concept_id;
      if (currentSid && firstConceptId) {
        handleSelectConceptNode(firstConceptId, currentSid, actionData.dag, true);
      } else if (currentSid) {
        requestNextAction(currentSid);
      }
    } else if (phase === 'step_ready' || phase === 'completed') {
      if (actionData.step) {
        setCurrentStep(actionData.step);
        const activeConceptKey = actionData.step.concept_id;
        loadedTargetRef.current = activeConceptKey;
        if (onActiveConceptChange) {
          onActiveConceptChange(
            activeConceptKey,
            actionData.step.track_slug || actionData.step.track_id
          );
        }
      }
      if (actionData.dag) {
        setDagPlan(actionData.dag);
      }
      setLoading(false);
    }
  };

  const requestNextAction = async (sId: string, notes: string = '') => {
    setLoading(true);
    setStreamingContent('');
    setLoadingMessage('Загрузка следующего шага...');
    try {
      const uncompletedNode = dagPlan?.nodes?.find((n) => n.status !== 'completed');
      if (uncompletedNode) {
        await handleSelectConceptNode(uncompletedNode.id, sId, dagPlan, true);
        return;
      }
      const notesToSend = notes || yapNote;
      const action = await apiClient.getNextTutorAction(sId, notesToSend);
      handleTutorActionResponse(action, sId);
    } catch (err) {
      console.error('Failed to get next action:', err);
      setLoading(false);
      setStreamingContent('');
    }
  };

  const handleVoiceNoteRecorded = async (audioBlob: Blob) => {
    setIsTranscribingAudio(true);
    try {
      const res = await apiClient.transcribeDeepNote(audioBlob);
      if (res.transcript && res.transcript.trim()) {
        const text = res.transcript.trim();
        setYapNote((prev) => (prev && prev.trim() ? `${prev.trim()}\n${text}` : text));
      }
    } catch (err) {
      console.error('Failed to transcribe audio note:', err);
    } finally {
      setIsTranscribingAudio(false);
    }
  };

  const handleProbeVoiceRecorded = async (audioBlob: Blob) => {
    setIsProbeTranscribing(true);
    try {
      const res = await apiClient.transcribeDeepNote(audioBlob);
      if (res.transcript && res.transcript.trim()) {
        const text = res.transcript.trim();
        setProbeNote((prev) => (prev && prev.trim() ? `${prev.trim()}\n${text}` : text));
      }
    } catch (err) {
      console.error('Failed to transcribe probe audio:', err);
    } finally {
      setIsProbeTranscribing(false);
    }
  };

  const handleAnswerProbe = async (chosenOptionId: string) => {
    if (!sessionId) return;
    if (chosenOptionId === 'generate_plan_now') {
      streamSessionPlan(sessionId);
      return;
    }
    setSelectedProbeOptionId(chosenOptionId);
    setLoading(true);
    setLoadingMessage('Profiling cognitive boundaries & factoring reasoning...');

    try {
      const qId = probeQuestion ? (probeQuestion.card_id || probeQuestion.id || probeQuestion.concept_id) : '';
      const action = await apiClient.submitProbeAnswer(
        sessionId,
        qId,
        chosenOptionId,
        probeNote,
      );
      setSelectedProbeOptionId(null);
      setProbeNote(''); // Clear for next question
      handleTutorActionResponse(action, sessionId);
    } catch (err) {
      console.error('Failed to submit probe answer:', err);
      alert('Failed to submit diagnostic answer. Please retry.');
      setLoading(false);
    }
  };

  const [isGraphModalOpen, setIsGraphModalOpen] = useState<boolean>(false);
  const [isExpandModalOpen, setIsExpandModalOpen] = useState<boolean>(false);
  const [isRegenerating, setIsRegenerating] = useState<boolean>(false);

  const handleTrackExpanded = async (expandedTrackData: any) => {
    setIsGraphModalOpen(false);
    if (expandedTrackData?.dag) {
      setDagPlan(expandedTrackData.dag);
    }
    const targetCid = expandedTrackData?.concepts?.[0]?.id || currentStep?.concept_id || targetConceptId;
    if (targetCid) {
      await startSession(targetCid);
    }
  };

  const handleSubmitStepAnswer = async (selectedOptionId: string): Promise<DeepStepResult> => {
    if (!sessionId || !currentStep) {
      throw new Error('No active session or step');
    }
    const res = await apiClient.submitStepVerification(
      sessionId,
      currentStep.step_sequence,
      [selectedOptionId],
      yapNote,
      currentStep.concept_id,
    );

    if (res.is_correct) {
      setDagPlan((prev) => {
        if (!prev) return prev;
        const updatedNodes = prev.nodes.map((n) =>
          n.id === currentStep.concept_id ? { ...n, status: 'completed' as const } : n
        );
        const completedCount = updatedNodes.filter((n) => n.status === 'completed').length;
        return {
          ...prev,
          nodes: updatedNodes,
          completed_nodes: Math.max(prev.completed_nodes, completedCount),
        };
      });
    }

    return res;
  };

  const currentConceptIdx = dagPlan?.nodes?.findIndex(
    (n) => n.id === currentStep?.concept_id || n.slug === currentStep?.concept_slug
  ) ?? -1;

  const nodes = dagPlan?.nodes || [];
  const hasPrev = currentConceptIdx > 0;
  const prevNode = hasPrev && dagPlan?.nodes ? dagPlan.nodes[currentConceptIdx - 1] : null;

  // Cyclic Gap Discovery: find the first unmastered node forward, or wrap-around from beginning
  const nextTargetNode = (() => {
    if (!nodes || nodes.length === 0) return null;
    // 1. Forward scan: look for first unmastered node ahead
    if (currentConceptIdx >= 0) {
      for (let i = currentConceptIdx + 1; i < nodes.length; i++) {
        if (nodes[i].status !== 'completed') {
          return nodes[i];
        }
      }
    }
    // 2. Wrap-around scan: check from start (0 .. currentConceptIdx)
    const maxWrap = currentConceptIdx >= 0 ? currentConceptIdx : nodes.length;
    for (let i = 0; i < maxWrap; i++) {
      if (nodes[i].status !== 'completed') {
        return nodes[i];
      }
    }
    // 3. If all nodes are already mastered, fall back to sequential next if available
    if (currentConceptIdx >= 0 && currentConceptIdx + 1 < nodes.length) {
      return nodes[currentConceptIdx + 1];
    }
    return null;
  })();

  const hasUnmasteredAnywhere = nodes.some((n, idx) => idx !== currentConceptIdx && n.status !== 'completed');
  const hasNext = nodes.length > 1 && (currentConceptIdx < nodes.length - 1 || hasUnmasteredAnywhere);
  const nextNode = nextTargetNode;

  const handleProceedPrevStep = () => {
    if (loading || isNavigatingRef.current) return;
    if (prevNode) {
      handleSelectConceptNode(prevNode.id);
    }
  };

  const handleProceedNextStep = () => {
    if (loading || isNavigatingRef.current) return;
    if (!dagPlan || !dagPlan.nodes || dagPlan.nodes.length === 0 || !currentStep) {
      if (sessionId) {
        requestNextAction(sessionId);
      }
      return;
    }

    // Advance to next unmastered node (cyclic) or conclude course if 100% completed
    if (nextTargetNode) {
      handleSelectConceptNode(nextTargetNode.id);
    } else if (sessionId) {
      requestNextAction(sessionId);
    }
  };


  const handleRegenerateStep = async () => {
    if (!sessionId || !currentStep || isRegenerating) return;
    setIsRegenerating(true);
    try {
      const freshStep = await apiClient.regenerateStep(
        sessionId,
        currentStep.concept_id,
        currentStep.step_sequence,
        yapNote,
      );
      setCurrentStep(freshStep);
    } catch (err) {
      console.error('Failed to regenerate step:', err);
      alert('Не удалось перегенерировать объяснение. Попробуйте еще раз.');
    } finally {
      setIsRegenerating(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto w-full pb-32 space-y-6">
      {/* State: Idle / Need Start */}
      {currentPhase === 'idle' && (
        <div className="bg-surface-900 border border-slate-800 p-8 sm:p-12 rounded-3xl text-center space-y-5 max-w-2xl mx-auto shadow-xl">
          <div className="w-16 h-16 rounded-2xl bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center mx-auto text-indigo-400">
            <GitBranch className="w-8 h-8" />
          </div>
          <h2 className="text-2xl font-black text-white">Start Deep Guided Arc</h2>
          <p className="text-sm text-slate-300 leading-relaxed max-w-md mx-auto">
            Personalized individual curriculum from zero to advanced mastery: multi-stage diagnostic profiling, personalized Mermaid DAG, and continuous step-by-step guidance.
          </p>
          <button
            onClick={() => startSession(targetConceptId)}
            disabled={loading}
            className="px-8 py-4 bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-sm sm:text-base rounded-2xl shadow-xl shadow-indigo-600/30 flex items-center justify-center gap-2.5 mx-auto transition-all"
          >
            {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Play className="w-5 h-5 fill-white" />}
            <span>Begin Guided Session</span>
          </button>
        </div>
      )}

      {/* State: Multi-Stage Diagnostic Profiling (Phase 1) */}
      {currentPhase === 'probing' && probeQuestion && (
        <div className="bg-surface-900 border border-amber-500/40 p-5 sm:p-6 rounded-3xl shadow-xl space-y-3.5 sm:space-y-4 max-w-3xl mx-auto w-full animate-fadeIn">
          {/* Header with Step indicator */}
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2.5 text-amber-400 text-xs font-bold uppercase tracking-wider">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-500"></span>
              <span>Diagnostic Profiling</span>
              {probeQuestion.probe_index && (
                <span className="bg-amber-950 px-2.5 py-0.5 rounded-full border border-amber-500 text-[11px] text-amber-300 font-bold">
                  Question {probeQuestion.probe_index} of {probeQuestion.total_probes || 30}
                </span>
              )}
            </div>
            {loading && (
              <span className="text-xs text-amber-300 flex items-center gap-1.5 font-semibold">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Profiling...
              </span>
            )}
          </div>

          <h3 className="text-base sm:text-lg font-bold text-white leading-snug">
            {probeQuestion.concept_title}
          </h3>

          <div className="text-xs sm:text-sm text-slate-200 bg-surface-950 p-4 sm:p-5 rounded-2xl border border-slate-800 leading-relaxed">
            <LatexRenderer content={probeQuestion.prompt} />
          </div>

          {/* Options */}
          <div className="space-y-1.5 pt-0.5">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Выберите вариант ответа:
            </p>
            {probeQuestion.options.map((opt: any) => {
              const isSelected = selectedProbeOptionId === opt.id;
              return (
                <button
                  key={opt.id}
                  onClick={() => handleAnswerProbe(opt.id)}
                  disabled={loading}
                  className={`w-full text-left py-2.5 px-4 rounded-xl text-xs flex items-center transition-colors duration-150 ${
                    isSelected
                      ? 'bg-[#1e1b4b] text-white ring-1 ring-indigo-500'
                      : 'bg-[#151e33] hover:bg-[#1e2b48] hover:text-white text-slate-200'
                  }`}
                >
                  <div className="flex-1 text-xs sm:text-sm leading-snug">
                    <LatexRenderer content={opt.text} />
                  </div>
                </button>
              );
            })}
          </div>

          {/* Diagnostic Voice Reasoning & Thoughts Scratchpad (Clean Title) */}
          <div className="p-3.5 rounded-2xl bg-surface-950 border border-amber-500/30 space-y-2 shadow-inner mt-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-amber-300 flex items-center gap-1.5">
                <MessageSquare className="w-3.5 h-3.5 text-amber-400" />
                <span>Голосовые заметки</span>
              </span>
              {isProbeTranscribing && (
                <span className="text-[11px] text-amber-300 flex items-center gap-1 font-semibold animate-pulse">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  Распознаю голос...
                </span>
              )}
            </div>

            <textarea
              value={probeNote}
              onChange={(e) => setProbeNote(e.target.value)}
              placeholder="Напишите или наговорите голосом свои мысли, сомнения или в чем вы не уверены. Модель учтет это при создании персонального курса!"
              rows={2}
              className="w-full bg-surface-900 border border-slate-800 rounded-xl p-3 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-amber-500/80 resize-none font-sans"
            />

            <div className="flex items-center justify-between pt-0.5">
              <VoiceRecorder
                onAudioRecorded={handleProbeVoiceRecorded}
                disabled={isProbeTranscribing || loading}
              />
              {probeNote && (
                <button
                  type="button"
                  onClick={() => setProbeNote('')}
                  className="text-[11px] text-slate-400 hover:text-slate-200 underline"
                >
                  Очистить
                </button>
              )}
            </div>
          </div>

          {/* Quick-Advance to Course Plan Button (Always Available) */}
          <div className="pt-3 border-t border-slate-800 flex items-center justify-between flex-wrap gap-2">
            <span className="text-[11px] text-slate-400">
              Хотите пропустить диагностику и сразу начать уроки?
            </span>
            <button
              onClick={() => handleAnswerProbe('generate_plan_now')}
              disabled={loading}
              className="px-4 py-2 bg-indigo-600/30 hover:bg-indigo-600 text-indigo-200 hover:text-white rounded-xl text-xs font-bold border border-indigo-500/40 transition-all flex items-center gap-2 shadow-lg cursor-pointer"
            >
              <Sparkles className="w-4 h-4 text-indigo-300" />
              <span>Пропустить тест и перейти к урокам</span>
            </button>
          </div>
        </div>
      )}

      {/* Live AI Status with Visual Progress */}
      {loading && (
        <div className="p-6 rounded-3xl bg-surface-900 border border-indigo-500/30 shadow-xl space-y-4 max-w-2xl mx-auto w-full animate-fadeIn">
          <div className="flex items-center justify-between text-xs font-bold uppercase tracking-wider">
            <div className="flex items-center gap-2 text-indigo-400">
              <Cpu className="w-4 h-4 animate-pulse" />
              <span>{activeModelDisplayName}</span>
            </div>
            <span className="text-slate-400 font-medium">
              {loadingTimeLeft > 0 ? `Осталось примерно: ~${loadingTimeLeft} сек` : 'Завершение обработки...'}
            </span>
          </div>

          <div className="p-4 bg-surface-950 rounded-2xl border border-slate-800 space-y-2.5">
            <div className="flex items-center justify-between text-xs text-slate-200">
              <div className="flex items-center gap-2">
                <Loader2 className="w-4 h-4 text-indigo-400 animate-spin shrink-0" />
                <span className="font-semibold text-sm">{loadingMessage}</span>
              </div>
              <span className="text-indigo-400 font-bold">{loadingProgress}%</span>
            </div>

            {/* Progress track */}
            <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-indigo-500 via-sky-400 to-emerald-400 transition-all duration-300 rounded-full"
                style={{ width: `${loadingProgress}%` }}
              />
            </div>
          </div>

          {/* Planning logs console */}
          {planningLogs.length > 0 && (
            <div className="p-3.5 bg-surface-950/80 rounded-2xl border border-slate-800/80 space-y-2 text-xs font-mono">
              <div className="flex items-center gap-2 text-slate-400 font-bold uppercase tracking-wider text-[10px]">
                <Terminal className="w-3.5 h-3.5 text-indigo-400" />
                <span>Процесс проектирования курса</span>
              </div>
              <div className="space-y-1 max-h-36 overflow-y-auto pr-1">
                {planningLogs.map((log, idx) => (
                  <div key={idx} className="flex items-start gap-2 text-slate-300 text-[11px] animate-fadeIn">
                    <span className="text-emerald-400 shrink-0 font-bold">✓</span>
                    <span className="leading-tight">{log}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* DAG Map Ready Badge during lesson streaming */}
          {dagPlan && dagPlan.nodes && dagPlan.nodes.length > 0 && (
            <div className="p-3 bg-surface-950/60 rounded-2xl border border-indigo-500/20 flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs text-indigo-300">
                <Network className="w-4 h-4 text-indigo-400" />
                <span>Граф курса сформирован: <strong className="text-white">{dagPlan.nodes.length}</strong> уроков</span>
              </div>
              {dagPlan.mermaid_code && (
                <button
                  type="button"
                  onClick={() => setIsGraphModalOpen(true)}
                  className="px-2.5 py-1 text-xs font-medium text-indigo-300 hover:text-white bg-indigo-600/20 hover:bg-indigo-600/40 rounded-lg border border-indigo-500/30 transition-all cursor-pointer"
                >
                  Схема DAG
                </button>
              )}
            </div>
          )}

          {streamingContent && (
            <div className="mt-4 pt-4 border-t border-slate-800 space-y-3 animate-fadeIn">
              <div className="flex items-center justify-between">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                  Прямая трансляция генерации
                </span>
                <span className="text-[11px] text-slate-500">Стриминг токенов без задержки</span>
              </div>
              <div className="max-h-80 overflow-y-auto pr-2 rounded-xl bg-surface-950/70 p-4 border border-slate-800/80 text-sm text-slate-200 leading-relaxed font-sans prose prose-invert max-w-none">
                <LatexRenderer content={streamingContent} />
                <span className="inline-block w-1.5 h-4 ml-1 bg-indigo-400 animate-pulse align-middle" />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Floating Side Navigation Chevrons ("<" and ">") */}
      {!loading && currentStep && currentPhase !== 'probing' && (
        <>
          {/* Left Chevron ("<") */}
          {hasPrev && (
            <button
              onClick={handleProceedPrevStep}
              title={prevNode ? `Предыдущий урок: ${prevNode.title}` : 'Предыдущий урок'}
              className="fixed left-2 sm:left-4 lg:left-8 top-1/2 -translate-y-1/2 z-30 p-2 sm:p-3 rounded-2xl bg-surface-900/40 hover:bg-surface-850 border border-slate-800/50 hover:border-indigo-500/60 text-slate-400 hover:text-white backdrop-blur-md opacity-20 hover:opacity-100 transition-all duration-200 hover:scale-110 shadow-2xl cursor-pointer group"
              aria-label="Предыдущий урок"
            >
              <ChevronLeft className="w-5 h-5 sm:w-6 sm:h-6 text-slate-400 group-hover:text-indigo-300 transition-colors" />
            </button>
          )}

          {/* Right Chevron (">") */}
          {hasNext && (
            <button
              onClick={handleProceedNextStep}
              title={nextNode ? `Следующий урок: ${nextNode.title}` : 'Следующий урок'}
              className="fixed right-2 sm:right-4 lg:right-8 top-1/2 -translate-y-1/2 z-30 p-2 sm:p-3 rounded-2xl bg-surface-900/40 hover:bg-surface-850 border border-slate-800/50 hover:border-indigo-500/60 text-slate-400 hover:text-white backdrop-blur-md opacity-20 hover:opacity-100 transition-all duration-200 hover:scale-110 shadow-2xl cursor-pointer group"
              aria-label="Следующий урок"
            >
              <ChevronRight className="w-5 h-5 sm:w-6 sm:h-6 text-slate-400 group-hover:text-indigo-300 transition-colors" />
            </button>
          )}
        </>
      )}

      {/* State: Teaching or Reviewing Completed Course (Centered Single Column Layout) */}
      {!loading && currentStep && currentPhase !== 'probing' && (
        <div className="max-w-4xl mx-auto w-full space-y-6 animate-fadeIn relative">
          {/* 1. Main Lesson Content + Visuals + Unified AI Interactive Hub */}
          <StepViewer
            step={currentStep}
            sessionId={sessionId}
            onRegenerate={handleRegenerateStep}
            isRegenerating={isRegenerating}
            progressInfo={dagPlan ? { completed: dagPlan.completed_nodes, total: dagPlan.total_nodes } : undefined}
            yapNote={yapNote}
            setYapNote={setYapNote}
            onVoiceNoteRecorded={handleVoiceNoteRecorded}
            isTranscribingAudio={isTranscribingAudio}
            ttsVoice={ttsVoice}
          />

          {/* 2. Verification Challenge Lock (Centered directly below lesson) */}
          {currentStep.verification_challenge && (
            <div className="w-full">
              <VerificationLock
                challenge={currentStep.verification_challenge}
                onSubmit={handleSubmitStepAnswer}
                onProceedNextStep={handleProceedNextStep}
                allowSkip={true}
                isLoading={loading}
              />
            </div>
          )}

          {/* 3. Curriculum Stepper / Local Mini-Roadmap */}
          {dagPlan && dagPlan.nodes && dagPlan.nodes.length > 0 && (
            <div className="w-full bg-surface-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-3.5 animate-fadeIn">
              <div className="flex items-center justify-between text-xs text-slate-400 pb-2 border-b border-slate-800">
                <span className="font-semibold flex items-center gap-2 text-indigo-300">
                  <Compass className="w-4 h-4 text-indigo-400" />
                  <span>Маршрут курса</span>
                </span>

                <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
                  <span className="font-bold text-indigo-400">
                    {dagPlan.completed_nodes} / {dagPlan.total_nodes} Освоено
                  </span>

                  <button
                    onClick={() => setIsExpandModalOpen(true)}
                    className="px-2.5 py-1 rounded-xl bg-indigo-950/80 hover:bg-indigo-900 border border-indigo-500/40 text-indigo-300 hover:text-white text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer shadow-sm"
                    title="Увеличить объем курса и добавить новые уроки"
                  >
                    <Layers className="w-3.5 h-3.5 text-indigo-400" />
                    <span>Увеличить объем</span>
                  </button>

                  {dagPlan.mermaid_code && (
                    <button
                      onClick={() => setIsGraphModalOpen(true)}
                      className="px-2.5 py-1 rounded-xl bg-indigo-950/80 hover:bg-indigo-900 border border-indigo-500/40 text-indigo-300 hover:text-white text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer shadow-sm"
                      title="Показать полную граф-схему зависимостей курса"
                    >
                      <Network className="w-3.5 h-3.5 text-indigo-400" />
                      <span>Схема DAG</span>
                    </button>
                  )}

                  {onNavigateToMap && (
                    <button
                      onClick={onNavigateToMap}
                      className="text-xs text-slate-400 hover:text-indigo-300 flex items-center gap-1 transition-colors group cursor-pointer"
                      title="Открыть интерактивную карту курса"
                    >
                      <Map className="w-3.5 h-3.5 text-indigo-400 group-hover:scale-110 transition-transform" />
                      <span className="hidden sm:inline">Вся карта знаний</span>
                    </button>
                  )}
                </div>
              </div>

              {/* Progress Bar */}
              <div className="w-full bg-surface-950 h-1.5 rounded-full overflow-hidden border border-slate-800">
                <div
                  className="bg-gradient-to-r from-indigo-500 via-indigo-400 to-emerald-400 h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${Math.max(
                      4,
                      Math.min(100, (dagPlan.completed_nodes / Math.max(1, dagPlan.total_nodes)) * 100)
                    )}%`,
                  }}
                />
              </div>

              {/* Stepper Window: Up to 4 relevant nodes (Clickable to jump to any lesson) */}
              <div className="flex items-center gap-2 overflow-x-auto py-1 scrollbar-none">
                {(() => {
                  const nodes = dagPlan.nodes;
                  const activeIdx = nodes.findIndex(
                    (n) => n.id === currentStep?.concept_id || n.status === 'active'
                  );
                  const targetIdx = activeIdx >= 0 ? activeIdx : 0;
                  const start = Math.max(0, targetIdx - 1);
                  const end = Math.min(nodes.length, start + 4);
                  const adjustedStart = Math.max(0, end - 4);
                  const visibleNodes = nodes.slice(adjustedStart, end);

                  return visibleNodes.map((node, i) => {
                    const isCurrent =
                      node.id === currentStep?.concept_id ||
                      (activeIdx === -1 && i === 0) ||
                      node.status === 'active';
                    const isDone = node.status === 'completed' && !isCurrent;

                    return (
                      <React.Fragment key={node.id}>
                        {i > 0 && (
                          <ChevronRight className="w-3.5 h-3.5 text-slate-600 shrink-0" />
                        )}

                        <div
                          onClick={() => {
                            if (!loading) handleSelectConceptNode(node.id);
                          }}
                          title={`Открыть урок: ${node.title}`}
                          className={`flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs shrink-0 transition-all ${
                            loading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:scale-102'
                          } ${
                            isCurrent
                              ? 'bg-indigo-600 text-white font-bold shadow-md shadow-indigo-600/30 ring-1 ring-indigo-400/40'
                              : isDone
                              ? 'bg-emerald-950/80 border border-emerald-500/40 text-emerald-300 font-medium hover:border-emerald-400'
                              : 'bg-surface-950 border border-slate-800 text-slate-400 hover:border-slate-700'
                          }`}
                        >
                          {isDone ? (
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                          ) : isCurrent ? (
                            <span className="w-2 h-2 rounded-full bg-white animate-pulse shrink-0" />
                          ) : (
                            <Circle className="w-3 h-3 text-slate-600 shrink-0" />
                          )}
                          <span className="truncate max-w-[170px] sm:max-w-[220px]">
                            {node.title}
                          </span>
                        </div>
                      </React.Fragment>
                    );
                  });
                })()}
              </div>
            </div>
          )}
        </div>
      )}

      {/* State: Completed (Fallback if no step is currently open) */}
      {currentPhase === 'completed' && !currentStep && (
        <div className="bg-emerald-950 border border-emerald-500/40 p-8 sm:p-12 rounded-3xl text-center space-y-5 shadow-xl max-w-2xl mx-auto animate-fadeIn">
          <CheckCircle className="w-14 h-14 text-emerald-400 mx-auto" />
          <h2 className="text-2xl font-bold text-white">Full Track Arc Completed!</h2>
          <p className="text-sm text-slate-300 leading-relaxed max-w-md mx-auto">
            You have mastered the entire dependency tree. All concepts are now locked into your long-term memory graph and scheduled in the Quick Feed!
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
            {dagPlan && dagPlan.nodes && dagPlan.nodes.length > 0 && (
              <button
                onClick={() => handleSelectConceptNode(dagPlan.nodes[0].id)}
                className="px-6 py-3.5 bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-sm rounded-2xl shadow-xl shadow-indigo-600/30 flex items-center justify-center gap-2 transition-all cursor-pointer"
              >
                <span>Открыть материалы курса</span>
              </button>
            )}
            <button
              onClick={() => setIsExpandModalOpen(true)}
              className="px-6 py-3.5 bg-indigo-950 hover:bg-indigo-900 border border-indigo-500/50 text-indigo-200 hover:text-white font-bold text-sm rounded-2xl shadow-xl flex items-center justify-center gap-2 transition-all cursor-pointer"
            >
              <Layers className="w-4 h-4 text-indigo-400" />
              <span>Увеличить объем (3 уровня)</span>
            </button>
            {onNavigateToFeed && (
              <button
                onClick={onNavigateToFeed}
                className="px-6 py-3.5 bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-sm rounded-2xl shadow-xl shadow-emerald-600/30 flex items-center justify-center gap-2 mx-auto transition-all cursor-pointer"
              >
                <Flame className="w-4 h-4" />
                <span>Quick Feed</span>
              </button>
            )}
          </div>
        </div>
      )}

      {/* Full Course Knowledge Graph Modal (Mermaid DAG) */}
      {isGraphModalOpen && dagPlan && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fadeIn">
          <div className="bg-surface-900 border border-indigo-500/50 rounded-3xl p-6 max-w-4xl w-full max-h-[85vh] flex flex-col shadow-2xl space-y-4">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-800 pb-3.5">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-xl bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400">
                  <Network className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white">Интерактивная схема курса (DAG)</h3>
                  <p className="text-xs text-slate-400">
                    {dagPlan.completed_nodes} из {dagPlan.total_nodes} концептов освоено
                  </p>
                </div>
              </div>

              <button
                onClick={() => setIsGraphModalOpen(false)}
                className="p-2 rounded-xl bg-surface-950 text-slate-400 hover:text-white border border-slate-800 hover:border-slate-700 transition-colors cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Legend */}
            <div className="flex items-center gap-4 text-xs font-semibold px-2 py-1 bg-surface-950 rounded-xl border border-slate-800/80 flex-wrap">
              <div className="flex items-center gap-1.5 text-emerald-400">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
                <span>✔ Освоено ({dagPlan.completed_nodes})</span>
              </div>
              <div className="flex items-center gap-1.5 text-indigo-400">
                <span className="w-2.5 h-2.5 rounded-full bg-indigo-500"></span>
                <span>▶ Текущий урок</span>
              </div>
              <div className="flex items-center gap-1.5 text-slate-400">
                <span className="w-2.5 h-2.5 rounded-full bg-slate-600"></span>
                <span>В очереди ({dagPlan.total_nodes - dagPlan.completed_nodes})</span>
              </div>
            </div>

            {/* Mermaid Graph Container */}
            <div className="flex-1 overflow-auto max-h-[45vh] rounded-2xl bg-surface-950 p-4 border border-slate-800">
              <MermaidViewer chart={dagPlan.mermaid_code || ''} />
            </div>

            {/* Direct Concept Jump Navigation Grid */}
            {dagPlan.nodes && dagPlan.nodes.length > 0 && (
              <div className="space-y-2 border-t border-slate-800 pt-3">
                <p className="text-xs font-semibold text-slate-400">Уроки курса (нажмите для перехода):</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 max-h-36 overflow-y-auto pr-1">
                  {dagPlan.nodes.map((n, idx) => (
                    <button
                      key={n.id}
                      onClick={() => {
                        setIsGraphModalOpen(false);
                        handleSelectConceptNode(n.id);
                      }}
                      className={`p-2 rounded-xl text-xs text-left font-medium border transition-all flex items-center justify-between gap-2 cursor-pointer ${
                        n.id === currentStep?.concept_id
                          ? 'bg-indigo-600 border-indigo-400 text-white font-bold'
                          : n.status === 'completed'
                          ? 'bg-emerald-950/60 border-emerald-500/30 text-emerald-300 hover:bg-emerald-900/60'
                          : 'bg-surface-950 border-slate-800 text-slate-300 hover:bg-surface-800'
                      }`}
                    >
                      <span className="truncate">{idx + 1}. {n.title}</span>
                      {n.status === 'completed' && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Modal Footer */}
            <div className="flex items-center justify-between pt-1 gap-2">
              <button
                onClick={() => {
                  setIsGraphModalOpen(false);
                  setIsExpandModalOpen(true);
                }}
                className="px-4 py-2.5 bg-indigo-950 hover:bg-indigo-900 border border-indigo-500/40 text-indigo-300 hover:text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center gap-1.5 cursor-pointer"
              >
                <Layers className="w-3.5 h-3.5 text-indigo-400" />
                <span>Увеличить объем курса</span>
              </button>

              <button
                onClick={() => setIsGraphModalOpen(false)}
                className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-bold transition-all shadow-md cursor-pointer"
              >
                Закрыть схему
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Expand Track Volume Modal */}
      {(currentStep?.track_id || currentStep?.track_slug || targetConceptId) && (
        <ExpandTrackModal
          isOpen={isExpandModalOpen}
          userId={userId}
          trackId={currentStep?.track_id || currentStep?.track_slug || targetConceptId || ''}
          trackTitle={currentStep?.concept_title || 'Current Track'}
          currentDepthLevel="medium"
          currentConceptCount={dagPlan?.total_nodes || 0}
          onClose={() => setIsExpandModalOpen(false)}
          onTrackExpanded={handleTrackExpanded}
        />
      )}
    </div>
  );
};
