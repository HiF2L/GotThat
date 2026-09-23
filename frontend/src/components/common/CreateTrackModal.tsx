import React, { useState, useEffect } from 'react';
import { apiClient } from '../../api/client';
import { TrackSummary, TrackFolder } from '../../types';
import { Sparkles, X, ArrowRight, Zap, Target, Rocket, MessageSquare, Folder, ShieldAlert, Brain } from 'lucide-react';

export type StartMode = 'quiz' | 'direct';

interface CreateTrackModalProps {
  isOpen: boolean;
  userId: string;
  folders?: TrackFolder[];
  initialFolderId?: string | null;
  onClose: () => void;
  onTrackCreated: (track: TrackSummary, startMode: StartMode) => void;
}

export type DepthLevel = 'low' | 'medium' | 'high';

export const CreateTrackModal: React.FC<CreateTrackModalProps> = ({
  isOpen,
  userId,
  folders = [],
  initialFolderId = null,
  onClose,
  onTrackCreated,
}) => {
  const [topicInput, setTopicInput] = useState('');
  const [userWishes, setUserWishes] = useState('');
  const [depthLevel, setDepthLevel] = useState<DepthLevel>('low');
  const [startMode, setStartMode] = useState<StartMode>('direct');
  const [selectedFolderId, setSelectedFolderId] = useState<string>(initialFolderId || '');
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationStep, setGenerationStep] = useState<string>('');
  const [progressPercent, setProgressPercent] = useState<number>(0);
  const [estimatedSeconds, setEstimatedSeconds] = useState<number>(8);
  const [currentStageIndex, setCurrentStageIndex] = useState<number>(1);
  const totalStages = 4;
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setSelectedFolderId(initialFolderId || '');
    }
  }, [isOpen, initialFolderId]);

  // Countdown timer for estimated remaining seconds
  useEffect(() => {
    if (!isGenerating) return;
    const interval = setInterval(() => {
      setEstimatedSeconds((prev) => (prev > 1 ? prev - 1 : 1));
    }, 1000);
    return () => clearInterval(interval);
  }, [isGenerating]);

  if (!isOpen) return null;

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!topicInput.trim() || isGenerating) return;

    setIsGenerating(true);
    setErrorMessage(null);
    setProgressPercent(15);
    setCurrentStageIndex(1);
    setEstimatedSeconds(7);
    setGenerationStep('Анализ предметной области и проверка стандартов...');

    const timer1 = setTimeout(() => {
      setProgressPercent(45);
      setCurrentStageIndex(2);
      setEstimatedSeconds(5);
      setGenerationStep('Построение дерева зависимостей (DAG)...');
    }, 1100);

    const timer2 = setTimeout(() => {
      setProgressPercent(75);
      setCurrentStageIndex(3);
      setEstimatedSeconds(3);
      setGenerationStep('Синтез структуры уроков и ключевых понятий...');
    }, 2500);

    const timer3 = setTimeout(() => {
      setProgressPercent(92);
      setCurrentStageIndex(4);
      setEstimatedSeconds(1);
      setGenerationStep('Финализация учебного плана и сохранение...');
    }, 4200);

    try {
      const track = await apiClient.generateCustomTrack(
        userId,
        topicInput.trim(),
        depthLevel,
        userWishes.trim() || undefined,
        selectedFolderId || null,
      );
      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);

      setProgressPercent(100);
      setEstimatedSeconds(0);
      setGenerationStep('Курс успешно создан!');

      setTimeout(() => {
        onTrackCreated(track, startMode);
        onClose();
        setTopicInput('');
        setUserWishes('');
        setSelectedFolderId('');
        setErrorMessage(null);
        setIsGenerating(false);
      }, 350);
    } catch (err: any) {
      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);
      console.error('Track generation error:', err);
      setErrorMessage(err.message || 'Не удалось создать курс. Пожалуйста, проверьте соединение.');
      setIsGenerating(false);
    }
  };

  const depthLevels: {
    id: DepthLevel;
    lessonCount: string;
    title: string;
    subtitle: string;
    isRecommended?: boolean;
    icon: React.ReactNode;
  }[] = [
    {
      id: 'low',
      lessonCount: '±6',
      title: 'Низкая',
      subtitle: 'Быстрый обзор ключевых основ и базовая интуиция',
      isRecommended: true,
      icon: <Zap className="w-3.5 h-3.5 text-emerald-400" />,
    },
    {
      id: 'medium',
      lessonCount: '15–25',
      title: 'Средняя',
      subtitle: 'Уверенная практика и типовые сценарии',
      icon: <Target className="w-3.5 h-3.5 text-sky-400" />,
    },
    {
      id: 'high',
      lessonCount: '40+',
      title: 'Высокая',
      subtitle: 'Полный путь до уровня эксперта по атомарным микро-шагам',
      icon: <Rocket className="w-3.5 h-3.5 text-indigo-400" />,
    },
  ];

  const activeLevel = depthLevels.find((d) => d.id === depthLevel) || depthLevels[0];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 animate-fadeIn">
      <div className="w-full max-w-xl bg-surface-900 border border-indigo-500/40 rounded-3xl p-6 shadow-2xl relative overflow-hidden flex flex-col max-h-[90vh]">
        {/* Background glow */}
        <div className="absolute -top-20 -right-20 w-48 h-48 bg-indigo-600/20 rounded-full blur-3xl pointer-events-none" />

        {/* Header */}
        <div className="flex items-center justify-between mb-4 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-indigo-600/30 border border-indigo-500/50 flex items-center justify-center text-indigo-300">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-black text-white tracking-tight">
                Создать новый курс
              </h2>
            </div>
          </div>

          <button
            onClick={onClose}
            disabled={isGenerating}
            className="p-2 rounded-full bg-surface-800 text-slate-400 hover:text-white hover:bg-surface-700 transition-all cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Form Body (Scrollable) */}
        <form onSubmit={handleGenerate} className="space-y-3 overflow-y-auto pr-1">
          {/* Error Banner */}
          {errorMessage && (
            <div className="flex items-start gap-2.5 p-3.5 bg-rose-950/50 border border-rose-500/50 rounded-2xl text-rose-200 text-xs animate-fadeIn">
              <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <div className="flex-1 leading-relaxed">{errorMessage}</div>
            </div>
          )}

          {/* Topic Input */}
          <div>
            <label className="text-xs font-bold text-slate-300 uppercase tracking-wider block mb-2">
              Что вы хотите изучить?
            </label>
            <input
              type="text"
              value={topicInput}
              onChange={(e) => setTopicInput(e.target.value)}
              placeholder="e.g. Квантовая физика, Архитектура микросервисов, FastAPI..."
              disabled={isGenerating}
              className="w-full bg-surface-950 border border-slate-700/80 rounded-2xl px-4 py-3 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-all"
              autoFocus
            />
          </div>

          {/* Minimalist Linear Immersion Level Selector */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs flex-wrap gap-1">
              <label className="font-bold text-slate-300 uppercase tracking-wider text-[11px]">
                Уровень детализации:
              </label>
              <span className="text-slate-400 font-medium text-[11px] truncate max-w-[360px]">
                {activeLevel.subtitle}
              </span>
            </div>

            {/* Minimalist Track & Circular Nodes */}
            <div className="relative pt-1 pb-0">
              {/* Connecting Horizontal Line passing through vertical center of 40px circles (y = 24px) */}
              <div className="absolute top-[24px] left-[16.66%] right-[16.66%] h-[2px] bg-slate-800 -translate-y-1/2 z-0" />
              <div
                className={`absolute top-[24px] left-[16.66%] h-[2px] -translate-y-1/2 z-0 transition-all duration-300 ${
                  depthLevel === 'low'
                    ? 'bg-emerald-500'
                    : 'bg-gradient-to-r from-emerald-500 to-indigo-500'
                }`}
                style={{
                  width:
                    depthLevel === 'low'
                      ? '0%'
                      : depthLevel === 'medium'
                      ? '33.33%'
                      : '66.66%',
                }}
              />

              {/* 3 Circular Lesson Count Nodes */}
              <div className="relative z-10 flex items-start justify-between">
                {depthLevels.map((lvl) => {
                  const isSelected = depthLevel === lvl.id;
                  const isLow = lvl.id === 'low';

                  let circleStyle = '';
                  if (isLow) {
                    circleStyle = isSelected
                      ? 'bg-emerald-600 border-emerald-400 text-white shadow-md shadow-emerald-600/40 ring-2 ring-emerald-500/40'
                      : 'bg-emerald-950/40 border-emerald-500/50 text-emerald-300 hover:border-emerald-400 hover:text-emerald-200';
                  } else {
                    circleStyle = isSelected
                      ? 'bg-indigo-600 border-indigo-400 text-white shadow-md shadow-indigo-600/40 ring-2 ring-indigo-500/30'
                      : 'bg-surface-900 border-slate-700 text-slate-400 group-hover:border-slate-500 group-hover:text-slate-200';
                  }

                  let titleStyle = '';
                  if (isLow) {
                    titleStyle = isSelected
                      ? 'text-emerald-300 font-bold'
                      : 'text-emerald-400/90 font-medium group-hover:text-emerald-300';
                  } else {
                    titleStyle = isSelected
                      ? 'text-white font-bold'
                      : 'text-slate-400 group-hover:text-slate-300';
                  }

                  return (
                    <button
                      key={lvl.id}
                      type="button"
                      disabled={isGenerating}
                      onClick={() => setDepthLevel(lvl.id)}
                      className="flex flex-col items-center group cursor-pointer focus:outline-none flex-1 pb-0"
                    >
                      {/* Perfectly Circular Node */}
                      <div
                        className={`w-10 h-10 rounded-full flex items-center justify-center font-bold transition-all duration-200 border ${
                          lvl.id === 'medium' ? 'text-[11px]' : 'text-xs'
                        } ${circleStyle}`}
                      >
                        {lvl.lessonCount}
                      </div>

                      {/* Text Below */}
                      <div className="mt-1 flex flex-col items-center">
                        <span className={`text-[11px] block transition-colors leading-tight ${titleStyle}`}>
                          {lvl.title}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Folder Selection (Optional) */}
          {folders.length > 0 && (
            <div className="space-y-1.5 pt-1">
              <label className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                <Folder className="w-3.5 h-3.5 text-indigo-400" />
                <span>Папка курса (опционально)</span>
              </label>
              <select
                value={selectedFolderId}
                onChange={(e) => setSelectedFolderId(e.target.value)}
                disabled={isGenerating}
                className="w-full bg-surface-950 border border-slate-700/80 rounded-2xl px-3 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 transition-all"
              >
                <option value="">Без папки (в общий список)</option>
                {folders.map((f) => (
                  <option key={f.id} value={f.id}>
                    📁 {f.name} {f.is_pinned ? '📌' : ''}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Course Wishes / Preferences Input */}
          <div className="space-y-1.5 pt-1">
            <label className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
              <MessageSquare className="w-3.5 h-3.5 text-indigo-400" />
              <span>Пожелания к курсу (опционально)</span>
            </label>
            <textarea
              value={userWishes}
              onChange={(e) => setUserWishes(e.target.value)}
              placeholder="e.g. Сделай упор на практику и реальные кейсы, хочу писать код с нуля, без абстрактной теории..."
              rows={2}
              disabled={isGenerating}
              className="w-full bg-surface-950 border border-slate-700/80 rounded-2xl p-3 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 resize-none font-sans transition-all"
            />
          </div>

          {/* Format of starting learning: Diagnostic Test vs Start Immediately */}
          <div className="space-y-1.5 pt-1">
            <label className="text-xs font-bold text-slate-300 flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <Brain className="w-3.5 h-3.5 text-indigo-400" />
                <span>Формат начала обучения:</span>
              </span>
            </label>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <button
                type="button"
                disabled={isGenerating}
                onClick={() => setStartMode('quiz')}
                className={`p-3 rounded-2xl border text-left transition-all cursor-pointer flex flex-col justify-between ${
                  startMode === 'quiz'
                    ? 'bg-indigo-950/70 border-indigo-500 shadow-md shadow-indigo-600/20 ring-1 ring-indigo-500/50'
                    : 'bg-surface-950 border-slate-800 hover:border-slate-700 text-slate-300'
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <div className={`w-4 h-4 rounded-full border flex items-center justify-center shrink-0 ${
                    startMode === 'quiz' ? 'border-indigo-400 bg-indigo-600' : 'border-slate-600'
                  }`}>
                    {startMode === 'quiz' && <div className="w-1.5 h-1.5 rounded-full bg-white" />}
                  </div>
                  <span className={`text-xs font-bold ${startMode === 'quiz' ? 'text-white' : 'text-slate-300'}`}>
                    Экспресс-тест знаний
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 leading-tight pl-6">
                  Оценить текущие знания, чтобы не начинать с нуля и пропустить знакомое.
                </p>
              </button>

              <button
                type="button"
                disabled={isGenerating}
                onClick={() => setStartMode('direct')}
                className={`p-3 rounded-2xl border text-left transition-all cursor-pointer flex flex-col justify-between ${
                  startMode === 'direct'
                    ? 'bg-emerald-950/70 border-emerald-500 shadow-md shadow-emerald-600/20 ring-1 ring-emerald-500/50'
                    : 'bg-surface-950 border-slate-800 hover:border-slate-700 text-slate-300'
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <div className={`w-4 h-4 rounded-full border flex items-center justify-center shrink-0 ${
                    startMode === 'direct' ? 'border-emerald-400 bg-emerald-600' : 'border-slate-600'
                  }`}>
                    {startMode === 'direct' && <div className="w-1.5 h-1.5 rounded-full bg-white" />}
                  </div>
                  <span className={`text-xs font-bold ${startMode === 'direct' ? 'text-white' : 'text-slate-300'}`}>
                    Сразу к первому уроку
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 leading-tight pl-6">
                  Без теста, начать изучение с базовых основ курса с чистого листа.
                </p>
              </button>
            </div>
          </div>

          {/* Detailed Generation Progress Card */}
          {isGenerating && (
            <div className="p-4 rounded-2xl bg-surface-950/90 border border-emerald-500/40 space-y-2.5 animate-fadeIn shadow-lg">
              <div className="flex items-center justify-between text-xs">
                <span className="font-bold text-emerald-400 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 animate-spin" />
                  <span>Генерация курса ({progressPercent}%)</span>
                </span>
                <span className="text-[11px] text-slate-400 font-medium">
                  {estimatedSeconds > 0 ? `Осталось примерно: ~${estimatedSeconds} сек` : 'Завершение...'}
                </span>
              </div>

              {/* Progress Track */}
              <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-emerald-500 via-teal-400 to-indigo-500 transition-all duration-300 rounded-full"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>

              {/* Current Action / Stage */}
              <div className="flex items-center justify-between text-[11px] text-slate-400">
                <span className="text-slate-300 font-medium truncate max-w-[340px]">{generationStep}</span>
                <span className="text-slate-500 shrink-0 font-semibold">{currentStageIndex} из {totalStages}</span>
              </div>
            </div>
          )}

          {/* Submit Button */}
          <div className="pt-2">
            <button
              type="submit"
              disabled={!topicInput.trim() || isGenerating}
              className={`w-full py-3.5 text-white font-bold text-sm rounded-2xl shadow-lg flex items-center justify-center gap-2 transition-all cursor-pointer ${
                startMode === 'direct'
                  ? 'bg-emerald-600 hover:bg-emerald-500 shadow-emerald-600/30'
                  : 'bg-indigo-600 hover:bg-indigo-500 shadow-indigo-600/30'
              } disabled:opacity-50`}
            >
              {isGenerating ? (
                <span>Формирование онтологии и графа...</span>
              ) : (
                <>
                  <span>
                    {startMode === 'quiz'
                      ? 'Создать курс и пройти тест'
                      : 'Создать курс и начать с 1 урока'}
                  </span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
