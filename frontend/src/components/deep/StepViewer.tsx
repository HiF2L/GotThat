import React, { useState, useEffect, useRef } from 'react';
import { DeepStep } from '../../types';
import { LatexRenderer } from '../common/LatexRenderer';
import { SvgViewer } from '../common/SvgViewer';
import { VoiceRecorder } from '../common/VoiceRecorder';
import { apiClient } from '../../api/client';
import {
  MessageCircleQuestion,
  ArrowUp,
  Loader2,
  Bot,
  User,
  RotateCw,
  GitBranch,
  Mic,
  Sparkles,
  Volume2,
  Play,
  Pause,
  X,
} from 'lucide-react';

interface StepViewerProps {
  step: DeepStep;
  sessionId?: string | null;
  onRegenerate?: () => void;
  isRegenerating?: boolean;
  progressInfo?: { completed: number; total: number };
  yapNote?: string;
  setYapNote?: (val: string) => void;
  onVoiceNoteRecorded?: (blob: Blob) => void;
  isTranscribingAudio?: boolean;
  ttsVoice?: string;
}

interface QnAPair {
  question: string;
  answer: string;
}

function formatTime(seconds: number): string {
  if (isNaN(seconds) || seconds < 0) return '00:00';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

export const StepViewer: React.FC<StepViewerProps> = React.memo(({
  step,
  sessionId,
  onRegenerate,
  isRegenerating,
  progressInfo,
  yapNote,
  setYapNote,
  onVoiceNoteRecorded,
  isTranscribingAudio,
  ttsVoice = 'alloy',
}) => {
  const [activeTab, setActiveTab] = useState<'ask' | 'reasoning'>('ask');
  const [questionText, setQuestionText] = useState<string>('');
  const [qaList, setQaList] = useState<QnAPair[]>([]);
  const [isAsking, setIsAsking] = useState<boolean>(false);
  const [isTranscribing, setIsTranscribing] = useState<boolean>(false);

  // Audio Player State
  const [audioState, setAudioState] = useState<'idle' | 'loading' | 'playing' | 'paused'>('idle');
  const [currentTime, setCurrentTime] = useState<number>(0);
  const [duration, setDuration] = useState<number>(0);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1.0);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioBlobUrlRef = useRef<string | null>(null);
  const audioBlobCacheRef = useRef<Map<string, string>>(new Map());
  const pendingPlayKeyRef = useRef<string | null>(null);

  const storageKey = `gotthat_qa_${step.session_id || 'sess'}_${step.step_sequence}_${step.concept_id}`;

  // Teardown and reset audio on step changes or unmount
  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
      if (audioBlobUrlRef.current) {
        URL.revokeObjectURL(audioBlobUrlRef.current);
        audioBlobUrlRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    pendingPlayKeyRef.current = null;
    setAudioState('idle');
    setCurrentTime(0);
    setDuration(0);
  }, [step.concept_id, step.step_sequence]);

  // Background Predictive Audio Prefetch:
  // Pre-downloads audio silently in background while user reads the lesson.
  // Completely non-blocking and independent of navigation.
  useEffect(() => {
    if (!step?.explanation_markdown) return;
    const cacheKey = `${step.concept_id}_${step.step_sequence}_${ttsVoice}`;

    if (!audioBlobCacheRef.current.has(cacheKey)) {
      let isCancelled = false;

      apiClient
        .synthesizeLessonSpeech(step.explanation_markdown, ttsVoice, 1.0)
        .then((blob) => {
          if (isCancelled) return;
          const url = URL.createObjectURL(blob);
          audioBlobCacheRef.current.set(cacheKey, url);

          // If the user clicked "Play" while it was prefetching, start playing immediately!
          if (pendingPlayKeyRef.current === cacheKey) {
            startPlayback(url);
          }
        })
        .catch((err) => {
          console.debug('Background audio prefetch skipped or error:', err);
          if (pendingPlayKeyRef.current === cacheKey) {
            setAudioState('idle');
            pendingPlayKeyRef.current = null;
          }
        });

      return () => {
        isCancelled = true;
      };
    }
  }, [step.concept_id, step.step_sequence, step.explanation_markdown, ttsVoice]);

  const startPlayback = (url: string) => {
    audioBlobUrlRef.current = url;
    const audio = new Audio(url);
    audio.playbackRate = playbackSpeed;

    audio.ontimeupdate = () => {
      setCurrentTime(audio.currentTime);
    };
    audio.onloadedmetadata = () => {
      setDuration(audio.duration);
    };
    audio.onended = () => {
      setAudioState('idle');
      setCurrentTime(0);
    };
    audio.onerror = () => {
      console.error('Audio playback error');
      setAudioState('idle');
    };

    audioRef.current = audio;
    audio
      .play()
      .then(() => {
        setAudioState('playing');
        pendingPlayKeyRef.current = null;
      })
      .catch((e) => {
        console.error('Audio playback error:', e);
        setAudioState('idle');
        pendingPlayKeyRef.current = null;
      });
  };

  const handleTogglePlay = async () => {
    if (audioState === 'playing') {
      if (audioRef.current) {
        audioRef.current.pause();
      }
      setAudioState('paused');
      return;
    }

    if (audioState === 'paused' && audioRef.current) {
      try {
        await audioRef.current.play();
        setAudioState('playing');
      } catch (e) {
        console.error('Audio resume error:', e);
      }
      return;
    }

    const cacheKey = `${step.concept_id}_${step.step_sequence}_${ttsVoice}`;
    const cachedUrl = audioBlobCacheRef.current.get(cacheKey);

    if (cachedUrl) {
      // 0ms instant playback from preloaded in-memory cache!
      startPlayback(cachedUrl);
      return;
    }

    // Audio is still prefetching in the background or starting fresh
    setAudioState('loading');
    pendingPlayKeyRef.current = cacheKey;

    try {
      const blob = await apiClient.synthesizeLessonSpeech(
        step.explanation_markdown,
        ttsVoice,
        1.0,
      );
      const url = URL.createObjectURL(blob);
      audioBlobCacheRef.current.set(cacheKey, url);
      if (pendingPlayKeyRef.current === cacheKey) {
        startPlayback(url);
      }
    } catch (err) {
      console.error('Failed to synthesize lesson speech:', err);
      alert('Не удалось воспроизвести озвучку. Пожалуйста, попробуйте еще раз.');
      setAudioState('idle');
      pendingPlayKeyRef.current = null;
    }
  };

  const handleCycleSpeed = () => {
    const nextSpeed = playbackSpeed === 1.0 ? 1.25 : playbackSpeed === 1.25 ? 1.5 : 1.0;
    setPlaybackSpeed(nextSpeed);
    if (audioRef.current) {
      audioRef.current.playbackRate = nextSpeed;
    }
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const targetTime = parseFloat(e.target.value);
    setCurrentTime(targetTime);
    if (audioRef.current) {
      audioRef.current.currentTime = targetTime;
    }
  };

  const handleStopAudio = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    if (audioBlobUrlRef.current) {
      URL.revokeObjectURL(audioBlobUrlRef.current);
      audioBlobUrlRef.current = null;
    }
    setAudioState('idle');
    setCurrentTime(0);
    setDuration(0);
  };

  // Sync Q&A from server step payload and localStorage on step change
  useEffect(() => {
    let localQa: QnAPair[] = [];
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved) localQa = JSON.parse(saved);
    } catch (e) {
      console.error('Failed to parse local Q&A:', e);
    }

    const serverQa = step.qa_history || [];
    const combined = [...serverQa];
    for (const item of localQa) {
      if (!combined.some((c) => c.question === item.question && c.answer === item.answer)) {
        combined.push(item);
      }
    }
    setQaList(combined);
  }, [step.session_id, step.step_sequence, step.concept_id, step.qa_history]);

  const handleAsk = async () => {
    if (!questionText.trim() || !sessionId || isAsking) return;
    const currentQ = questionText.trim();
    setQuestionText('');
    setIsAsking(true);

    try {
      const res = await apiClient.askTutorQuestion(
        sessionId,
        step.step_sequence,
        currentQ,
      );
      const newPair = { question: currentQ, answer: res.answer_markdown };
      setQaList((prev) => {
        const next = [...prev, newPair];
        try {
          localStorage.setItem(storageKey, JSON.stringify(next));
        } catch (e) {}
        return next;
      });
    } catch (err) {
      console.error('Failed to ask tutor question:', err);
      alert('Could not get answer from AI tutor. Please retry.');
    } finally {
      setIsAsking(false);
    }
  };

  const handleClearQa = () => {
    setQaList([]);
    try {
      localStorage.removeItem(storageKey);
    } catch (e) {}
  };

  const handleVoiceRecorded = async (blob: Blob) => {
    setIsTranscribing(true);
    try {
      const res = await apiClient.transcribeDeepNote(blob);
      if (res.transcript && res.transcript.trim()) {
        const text = res.transcript.trim();
        setQuestionText((prev) => (prev && prev.trim() ? `${prev.trim()} ${text}` : text));
      }
    } catch (err) {
      console.error('Failed to transcribe question audio:', err);
    } finally {
      setIsTranscribing(false);
    }
  };

  return (
    <div className="w-full bg-surface-900 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-3 gap-3 flex-wrap">
        <div className="flex items-center gap-2.5">
          <span className="w-7 h-7 rounded-full bg-indigo-600/30 border border-indigo-500/50 flex items-center justify-center text-xs font-bold text-indigo-300 shrink-0">
            {step.step_sequence}
          </span>
          <h2 className="text-base font-bold text-white tracking-wide">
            {step.concept_title}
          </h2>
        </div>

        <div className="flex items-center gap-2.5 flex-wrap">
          {/* Minimalist TTS Audio Player */}
          {audioState === 'idle' ? (
            <button
              onClick={handleTogglePlay}
              title="Озвучить урок (GPT-4o-mini TTS)"
              className="px-3 py-1.5 rounded-full bg-indigo-600/10 hover:bg-indigo-600/20 border border-indigo-500/30 hover:border-indigo-500/50 text-indigo-300 hover:text-indigo-200 text-xs font-semibold flex items-center gap-1.5 transition-all shadow-sm active:scale-95 cursor-pointer group"
            >
              <Volume2 className="w-3.5 h-3.5 text-indigo-400 group-hover:scale-110 transition-transform" />
              <span>Озвучить урок</span>
            </button>
          ) : (
            <div className="flex items-center gap-2 px-3 py-1 bg-surface-950 border border-indigo-500/40 rounded-full shadow-inner animate-fadeIn">
              {/* Play / Pause / Loading Button */}
              <button
                onClick={handleTogglePlay}
                disabled={audioState === 'loading'}
                className="p-1 rounded-full text-indigo-300 hover:text-white transition-colors cursor-pointer disabled:opacity-50 flex items-center justify-center"
                title={audioState === 'playing' ? 'Пауза' : 'Воспроизвести'}
              >
                {audioState === 'loading' ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-400" />
                ) : audioState === 'playing' ? (
                  <Pause className="w-3.5 h-3.5 fill-indigo-400 text-indigo-400" />
                ) : (
                  <Play className="w-3.5 h-3.5 fill-indigo-400 text-indigo-400" />
                )}
              </button>

              {/* Current Time / Duration */}
              <span className="text-[11px] font-mono text-slate-300 select-none">
                {formatTime(currentTime)}
                {duration > 0 && <span className="text-slate-500"> / {formatTime(duration)}</span>}
              </span>

              {/* Mini Scrubber */}
              {duration > 0 && (
                <input
                  type="range"
                  min={0}
                  max={duration}
                  step={0.1}
                  value={currentTime}
                  onChange={handleSeek}
                  className="w-14 sm:w-20 h-1 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
                />
              )}

              {/* Speed Button (1x / 1.25x / 1.5x) */}
              <button
                onClick={handleCycleSpeed}
                className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-indigo-950 border border-indigo-500/40 text-indigo-300 hover:text-white transition-colors cursor-pointer select-none"
                title="Скорость воспроизведения"
              >
                {playbackSpeed}x
              </button>

              {/* Stop & Close Button */}
              <button
                onClick={handleStopAudio}
                className="p-0.5 text-slate-500 hover:text-slate-300 transition-colors cursor-pointer"
                title="Закрыть плеер"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          )}

          {progressInfo && progressInfo.total > 0 && (
            <span className="text-xs font-semibold px-3 py-1.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300 flex items-center gap-1.5 shadow-sm">
              <GitBranch className="w-3.5 h-3.5 text-indigo-400" />
              <span>{progressInfo.completed} / {progressInfo.total} Освоено</span>
            </span>
          )}

          {onRegenerate && (
            <button
              onClick={onRegenerate}
              disabled={isRegenerating}
              title="Перегенерировать объяснение другими словами"
              aria-label="Перегенерировать объяснение"
              className="p-2 rounded-full bg-indigo-500/10 hover:bg-indigo-500/20 border border-indigo-500/30 text-indigo-300 hover:text-indigo-200 transition-all shadow-sm active:scale-90 disabled:opacity-50 disabled:cursor-not-allowed group cursor-pointer flex items-center justify-center"
            >
              <RotateCw className={`w-4 h-4 text-indigo-400 group-hover:rotate-180 transition-transform duration-500 ${isRegenerating ? 'animate-spin' : ''}`} />
            </button>
          )}
        </div>
      </div>

      {/* Atomic Step Explanation */}
      <div className="text-slate-200 text-sm leading-relaxed">
        <LatexRenderer content={step.explanation_markdown} />
      </div>

      {/* Visual Artifact: SVG Diagram */}
      {step.visual_artifact && step.visual_artifact.type === 'svg' && (
        <SvgViewer
          svgPayload={step.visual_artifact.payload}
          altText={step.visual_artifact.alt_text}
        />
      )}

      {/* Visual Artifact: Real Internet Image (only if not already embedded in markdown) */}
      {step.visual_artifact && step.visual_artifact.type === 'image' && !step.explanation_markdown.includes(step.visual_artifact.payload) && (
        <figure className="my-4 sm:float-right sm:ml-5 sm:mb-4 sm:mt-1 w-full sm:w-80 rounded-2xl overflow-hidden border border-slate-800 bg-surface-950 shadow-xl transition-all duration-300 hover:border-indigo-500/50 group clear-both sm:clear-none">
          <div className="relative w-full overflow-hidden bg-slate-950 flex items-center justify-center min-h-[140px] max-h-[260px]">
            <img
              src={step.visual_artifact.payload}
              alt={step.visual_artifact.alt_text || 'Educational Reference'}
              className="w-full h-auto max-h-[260px] object-contain group-hover:scale-[1.03] transition-transform duration-500 ease-out block cursor-zoom-in transparent-img-contour"
              loading="lazy"
            />
          </div>
          {step.visual_artifact.alt_text && (
            <figcaption className="px-3.5 py-2.5 text-[11px] text-slate-400 bg-surface-900/60 border-t border-slate-800/80 text-left font-sans flex items-start gap-2 leading-relaxed">
              <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 mt-1.5 shrink-0"></span>
              <span className="text-slate-300 font-medium">{step.visual_artifact.alt_text}</span>
            </figcaption>
          )}
        </figure>
      )}

      {/* Unified AI Interactive Hub (Tabs: 1. Ask Tutor / 2. Voice Reasoning) */}
      <div className="pt-4 border-t border-slate-800 space-y-4">
        {/* Tab Switcher with Hover Descriptions / Tooltips */}
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center p-1 rounded-2xl bg-surface-950 border border-slate-800 gap-1.5">
            {/* Tab 1: Q&A */}
            <div className="relative group">
              <button
                type="button"
                onClick={() => setActiveTab('ask')}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-colors ${
                  activeTab === 'ask'
                    ? 'bg-indigo-600 text-white shadow-md'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                }`}
              >
                <MessageCircleQuestion className="w-3.5 h-3.5 text-indigo-300" />
                <span>Задать вопрос по уроку</span>
                {qaList.length > 0 && (
                  <span className="text-[10px] bg-indigo-950 px-1.5 py-0.5 rounded-full border border-indigo-500 text-indigo-200">
                    {qaList.length}
                  </span>
                )}
              </button>

              {/* Tooltip / Hover Description */}
              <div className="absolute bottom-full left-0 mb-2.5 hidden group-hover:block w-72 p-3 bg-surface-950 border border-indigo-500 rounded-2xl shadow-2xl z-50 text-[11px] text-slate-300 leading-relaxed pointer-events-none animate-fadeIn">
                <div className="font-bold text-indigo-300 mb-1 flex items-center gap-1.5">
                  <MessageCircleQuestion className="w-3.5 h-3.5 text-indigo-400" />
                  Локальный Q&A диалог
                </div>
                Быстро уточнить непонятный термин или попросить дополнительный пример. Тьютор мгновенно ответит прямо здесь в чате, не меняя прогресс урока.
              </div>
            </div>

            {/* Tab 2: Voice Reasoning / Feynman Method */}
            <div className="relative group">
              <button
                type="button"
                onClick={() => setActiveTab('reasoning')}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-colors ${
                  activeTab === 'reasoning'
                    ? 'bg-indigo-600 text-white shadow-md'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                }`}
              >
                <Mic className="w-3.5 h-3.5 text-emerald-400" />
                <span>Мышление вслух</span>
                {yapNote && (
                  <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                )}
              </button>

              {/* Tooltip / Hover Description */}
              <div className="absolute bottom-full left-0 mb-2.5 hidden group-hover:block w-80 p-3 bg-surface-950 border border-emerald-500 rounded-2xl shadow-2xl z-50 text-[11px] text-slate-300 leading-relaxed pointer-events-none animate-fadeIn">
                <div className="font-bold text-emerald-300 mb-1 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
                  Метод Фейнмана (Voice Reasoning)
                </div>
                Надиктуйте или запишите свои догадки, сомнения и логику. ИИ-тьютор учтет ход ваших мыслей при проверке теста и адаптирует следующие уроки под вас.
              </div>
            </div>
          </div>

          {/* Subtext info */}
          <span className="text-[11px] text-slate-500 font-medium hidden sm:inline">
            {activeTab === 'ask' ? 'Точечные ответы в чате' : 'Контекст для адаптации курса'}
          </span>
        </div>

        {/* Tab 1 Content: Ask Tutor */}
        {activeTab === 'ask' && (
          <div className="space-y-3 animate-fadeIn">
            {qaList.length > 0 && (
              <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
                <div className="flex items-center justify-between text-[11px] text-slate-400 pb-1.5 border-b border-slate-800 px-1">
                  <span className="font-semibold text-indigo-300">Сохранённые вопросы ({qaList.length})</span>
                  <button
                    onClick={handleClearQa}
                    className="text-[10px] text-slate-500 hover:text-rose-400 transition-colors cursor-pointer"
                  >
                    Очистить историю
                  </button>
                </div>
                {qaList.map((qa, i) => (
                  <div key={i} className="space-y-2 bg-surface-950 p-4 rounded-2xl border border-slate-800 text-xs">
                    <div className="flex items-start gap-2 text-indigo-300 font-semibold">
                      <User className="w-3.5 h-3.5 mt-0.5 shrink-0 text-slate-400" />
                      <span>{qa.question}</span>
                    </div>
                    <div className="flex items-start gap-2 text-slate-200 leading-relaxed pl-1 pt-1 border-t border-slate-800">
                      <Bot className="w-3.5 h-3.5 mt-0.5 shrink-0 text-indigo-400" />
                      <div className="flex-1">
                        <LatexRenderer content={qa.answer} />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="flex items-center gap-2">
              <input
                type="text"
                value={questionText}
                onChange={(e) => setQuestionText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleAsk();
                }}
                placeholder="Спросите что угодно по текущему шагу..."
                disabled={isAsking || isTranscribing}
                className="flex-1 h-[38px] bg-surface-950 border border-slate-800 rounded-full px-5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              />

              <VoiceRecorder
                onAudioRecorded={handleVoiceRecorded}
                disabled={isAsking || isTranscribing}
              />

              <button
                onClick={handleAsk}
                disabled={!questionText.trim() || isAsking || isTranscribing}
                className="h-[38px] w-[38px] bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white rounded-full shadow-md transition-all flex items-center justify-center cursor-pointer shrink-0"
              >
                {isAsking ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <ArrowUp className="w-4 h-4" strokeWidth={2.5} />
                )}
              </button>
            </div>
          </div>
        )}

        {/* Tab 2 Content: Voice Reasoning / Scratchpad */}
        {activeTab === 'reasoning' && (
          <div className="space-y-3 animate-fadeIn">
            {isTranscribingAudio && (
              <div className="p-2.5 bg-emerald-950 border border-emerald-500/40 rounded-2xl text-xs text-emerald-300 flex items-center gap-2 animate-pulse">
                <Loader2 className="w-4 h-4 animate-spin text-emerald-400" />
                <span>Распознаю голос...</span>
              </div>
            )}

            <textarea
              value={yapNote || ''}
              onChange={(e) => setYapNote && setYapNote(e.target.value)}
              placeholder="Надиктуйте или запишите свои сомнения, мысли и интуицию перед ответом на проверочный вопрос..."
              rows={3}
              className="w-full bg-surface-950 border border-slate-800 rounded-2xl p-4 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500/50 resize-none font-mono"
            />

            <div className="flex items-center justify-between pt-1">
              <VoiceRecorder
                onAudioRecorded={(blob) => {
                  if (onVoiceNoteRecorded) onVoiceNoteRecorded(blob);
                }}
                disabled={isTranscribingAudio}
              />
              {yapNote && (
                <button
                  onClick={() => setYapNote && setYapNote('')}
                  className="text-xs text-slate-400 hover:text-slate-200 underline cursor-pointer"
                >
                  Очистить заметки
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
});
