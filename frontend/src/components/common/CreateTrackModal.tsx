import React, { useState, useEffect } from 'react';
import { apiClient } from '../../api/client';
import { TrackSummary, TrackFolder } from '../../types';
import { Sparkles, X, Loader2, ArrowRight, Zap, Target, Rocket, MessageSquare, Folder } from 'lucide-react';

interface CreateTrackModalProps {
  isOpen: boolean;
  userId: string;
  folders?: TrackFolder[];
  initialFolderId?: string | null;
  onClose: () => void;
  onTrackCreated: (track: TrackSummary) => void;
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
  const [depthLevel, setDepthLevel] = useState<DepthLevel>('high');
  const [selectedFolderId, setSelectedFolderId] = useState<string>(initialFolderId || '');
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationStep, setGenerationStep] = useState<string>('');

  useEffect(() => {
    if (isOpen) {
      setSelectedFolderId(initialFolderId || '');
    }
  }, [isOpen, initialFolderId]);

  if (!isOpen) return null;

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!topicInput.trim() || isGenerating) return;

    setIsGenerating(true);
    setGenerationStep('Reasoning through domain epistemology & prerequisites...');

    try {
      setTimeout(() => {
        setGenerationStep('Structuring dependency graph (DAG) with AI Engine...');
      }, 1500);

      setTimeout(() => {
        setGenerationStep('Generating diagnostic assessment questions & LaTeX formulations...');
      }, 3500);

      const track = await apiClient.generateCustomTrack(
        userId,
        topicInput.trim(),
        depthLevel,
        userWishes.trim() || undefined,
        selectedFolderId || null,
      );
      onTrackCreated(track);
      onClose();
      setTopicInput('');
      setUserWishes('');
      setSelectedFolderId('');
    } catch (err: any) {
      console.error('Track generation error:', err);
      alert(`Failed to generate course: ${err.message || 'Check backend connection'}`);
    } finally {
      setIsGenerating(false);
      setGenerationStep('');
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
      icon: <Zap className="w-3.5 h-3.5 text-amber-400" />,
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
      isRecommended: true,
      icon: <Rocket className="w-3.5 h-3.5 text-indigo-400" />,
    },
  ];

  const sampleTopics = [
    'Квантовые вычисления для начинающих',
    'Философия стоицизма: Сенека и Марк Аврелий',
    'Асинхронная архитектура в Rust (Tokio & Futures)',
    'Теория относительности Эйнштейна',
    'Экономика: Теория игр и равновесие Нэша',
  ];

  const activeLevel = depthLevels.find((d) => d.id === depthLevel) || depthLevels[2];

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
                  depthLevel === 'high'
                    ? 'bg-gradient-to-r from-indigo-500 via-indigo-400 to-emerald-400'
                    : 'bg-indigo-500'
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
                  const isHigh = lvl.id === 'high';

                  let circleStyle = '';
                  if (isHigh) {
                    circleStyle = isSelected
                      ? 'bg-emerald-600 border-emerald-400 text-white shadow-md shadow-emerald-600/40 ring-2 ring-emerald-500/40'
                      : 'bg-emerald-950/40 border-emerald-500/50 text-emerald-300 hover:border-emerald-400 hover:text-emerald-200';
                  } else {
                    circleStyle = isSelected
                      ? 'bg-indigo-600 border-indigo-400 text-white shadow-md shadow-indigo-600/40 ring-2 ring-indigo-500/30'
                      : 'bg-surface-900 border-slate-700 text-slate-400 group-hover:border-slate-500 group-hover:text-slate-200';
                  }

                  let titleStyle = '';
                  if (isHigh) {
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

          {/* Quick Suggestions */}
          {!isGenerating && (
            <div className="space-y-1 mt-0 pt-0">
              <span className="text-[10px] uppercase font-bold text-slate-500">Примеры тем:</span>
              <div className="flex flex-wrap gap-1.5">
                {sampleTopics.map((topic, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setTopicInput(topic)}
                    className="text-[11px] px-3 py-1.5 rounded-xl bg-[#151e33] hover:bg-[#1e2b48] text-slate-200 hover:text-white border border-[#233152] hover:border-indigo-500/50 transition-all cursor-pointer shadow-sm"
                  >
                    {topic}
                  </button>
                ))}
              </div>
            </div>
          )}

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

          {/* Loading Animation */}
          {isGenerating && (
            <div className="p-4 rounded-2xl bg-surface-950/80 border border-indigo-500/30 flex items-center gap-3 animate-pulse">
              <Loader2 className="w-5 h-5 text-indigo-400 animate-spin shrink-0" />
              <div className="text-xs text-indigo-300 font-medium leading-tight">
                {generationStep}
              </div>
            </div>
          )}

          {/* Submit Button */}
          <div className="pt-2">
            <button
              type="submit"
              disabled={!topicInput.trim() || isGenerating}
              className="w-full py-3.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-bold text-sm rounded-2xl shadow-lg shadow-indigo-600/30 flex items-center justify-center gap-2 transition-all"
            >
              {isGenerating ? (
                <span>Формирование онтологии и графа...</span>
              ) : (
                <>
                  <span>Создать курс и начать обучение</span>
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
