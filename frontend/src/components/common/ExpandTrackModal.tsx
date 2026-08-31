import React, { useState, useEffect } from 'react';
import { apiClient } from '../../api/client';
import { TrackSummary } from '../../types';
import {
  Sparkles,
  X,
  Loader2,
  ArrowRight,
  Zap,
  Target,
  Rocket,
  Check,
  Layers,
  CheckCircle2,
  MessageSquare,
} from 'lucide-react';

export type DepthLevel = 'low' | 'medium' | 'high';

interface ExpandTrackModalProps {
  isOpen: boolean;
  userId: string;
  trackId: string;
  trackTitle: string;
  currentDepthLevel?: string;
  currentConceptCount?: number;
  onClose: () => void;
  onTrackExpanded: (track: TrackSummary & { dag?: any }) => void;
}

export const ExpandTrackModal: React.FC<ExpandTrackModalProps> = ({
  isOpen,
  userId,
  trackId,
  trackTitle,
  currentDepthLevel = 'medium',
  currentConceptCount = 0,
  onClose,
  onTrackExpanded,
}) => {
  const [selectedDepth, setSelectedDepth] = useState<DepthLevel>(() => {
    if (currentDepthLevel === 'low') return 'medium';
    return 'high';
  });
  const [userNotes, setUserNotes] = useState<string>('');
  const [isExpanding, setIsExpanding] = useState<boolean>(false);
  const [expansionStep, setExpansionStep] = useState<string>('');

  useEffect(() => {
    if (isOpen) {
      if (currentDepthLevel === 'low') setSelectedDepth('medium');
      else setSelectedDepth('high');
      setUserNotes('');
      setExpansionStep('');
    }
  }, [isOpen, currentDepthLevel]);

  if (!isOpen) return null;

  const handleExpand = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isExpanding || !trackId) return;

    setIsExpanding(true);
    setExpansionStep('Анализ текущего дерева понятий и освоенного прогресса...');

    const timer1 = setTimeout(() => {
      setExpansionStep('Синтез расширенных модулей, подсистем и практических кейсов...');
    }, 1600);

    const timer2 = setTimeout(() => {
      setExpansionStep('Формирование обновленной топологии DAG и сохранение мастерства...');
    }, 3800);

    try {
      const res = await apiClient.expandTrack(trackId, userId, selectedDepth, userNotes.trim());
      clearTimeout(timer1);
      clearTimeout(timer2);
      onTrackExpanded(res);
      onClose();
    } catch (err: any) {
      clearTimeout(timer1);
      clearTimeout(timer2);
      console.error('Track expansion error:', err);
      alert(`Не удалось расширить объем курса: ${err.message || 'Проверьте соединение с сервером'}`);
    } finally {
      setIsExpanding(false);
      setExpansionStep('');
    }
  };

  const depthOptions: {
    id: DepthLevel;
    title: string;
    badge: string;
    subtitle: string;
    icon: React.ReactNode;
    isRecommended?: boolean;
  }[] = [
    {
      id: 'low',
      title: 'Низкая детализация',
      badge: '± 6 уроков',
      subtitle: 'Быстрый обзор ключевых основ и базовая интуиция',
      icon: <Zap className="w-4 h-4 text-amber-400" />,
    },
    {
      id: 'medium',
      title: 'Средняя детализация',
      badge: '15–25 уроков',
      subtitle: 'Уверенное практическое владение и типовые сценарии',
      icon: <Target className="w-4 h-4 text-sky-400" />,
      isRecommended: currentDepthLevel === 'low',
    },
    {
      id: 'high',
      title: 'Высокая детализация',
      badge: '40–65+ уроков',
      subtitle: 'Полный путь до уровня эксперта по атомарным микро-шагам',
      icon: <Rocket className="w-4 h-4 text-indigo-400" />,
      isRecommended: currentDepthLevel !== 'low',
    },
  ];

  const currentLevelLabel =
    currentDepthLevel === 'low'
      ? 'Низкая детализация'
      : currentDepthLevel === 'medium'
      ? 'Средняя детализация'
      : 'Высокая детализация';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fadeIn">
      <div className="w-full max-w-xl bg-surface-900 border border-indigo-500/40 rounded-3xl p-6 shadow-2xl relative overflow-hidden flex flex-col max-h-[90vh]">
        {/* Ambient background glow */}
        <div className="absolute -top-20 -right-20 w-48 h-48 bg-indigo-600/20 rounded-full blur-3xl pointer-events-none" />

        {/* Header */}
        <div className="flex items-center justify-between mb-4 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-indigo-600/30 border border-indigo-500/50 flex items-center justify-center text-indigo-300">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-black text-white tracking-tight">
                Увеличить объем курса / Expand Course Volume
              </h2>
              <p className="text-[11px] text-slate-400">
                «{trackTitle}»
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            disabled={isExpanding}
            className="p-2 rounded-full bg-surface-800 text-slate-400 hover:text-white hover:bg-surface-700 transition-all cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Current Status Banner */}
        <div className="mb-4 p-3 rounded-2xl bg-surface-950 border border-slate-800 flex items-center justify-between text-xs">
          <span className="text-slate-400">Текущий объем:</span>
          <div className="flex items-center gap-2 font-semibold">
            <span className="text-slate-200">{currentLevelLabel}</span>
            {currentConceptCount > 0 && (
              <span className="px-2 py-0.5 rounded-full bg-indigo-950 border border-indigo-500/40 text-indigo-300 text-[11px]">
                {currentConceptCount} уроков
              </span>
            )}
          </div>
        </div>

        {/* Form Body */}
        <form onSubmit={handleExpand} className="space-y-4 overflow-y-auto pr-1">
          {/* Depth Options */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-slate-300 uppercase tracking-wider block">
              Выберите целевой уровень детализации:
            </label>

            <div className="space-y-2">
              {depthOptions.map((opt) => {
                const isSelected = selectedDepth === opt.id;
                const isCurrent = currentDepthLevel === opt.id;
                return (
                  <div
                    key={opt.id}
                    onClick={() => !isExpanding && setSelectedDepth(opt.id)}
                    className={`p-3.5 rounded-2xl border transition-all cursor-pointer flex items-center justify-between gap-3 ${
                      isSelected
                        ? 'bg-indigo-950/80 border-indigo-500 ring-2 ring-indigo-500/40 shadow-lg shadow-indigo-600/20'
                        : 'bg-surface-950/60 border-slate-800 hover:border-slate-700 hover:bg-surface-950'
                    }`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-8 h-8 rounded-xl bg-surface-900 border border-slate-700/60 flex items-center justify-center shrink-0">
                        {opt.icon}
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className={`text-xs font-bold ${isSelected ? 'text-white' : 'text-slate-200'}`}>
                            {opt.title}
                          </span>
                          <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                            isSelected
                              ? 'bg-indigo-900/80 border-indigo-400/50 text-indigo-200'
                              : 'bg-surface-900 border-slate-700 text-slate-400'
                          }`}>
                            {opt.badge}
                          </span>
                          {opt.isRecommended && (
                            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-950/80 border border-emerald-500/40 text-emerald-300">
                              Рекомендуется
                            </span>
                          )}
                          {isCurrent && (
                            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700">
                              Текущий
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-slate-400 mt-0.5 truncate">
                          {opt.subtitle}
                        </p>
                      </div>
                    </div>

                    <div className="shrink-0">
                      <div className={`w-5 h-5 rounded-full flex items-center justify-center border ${
                        isSelected
                          ? 'bg-indigo-600 border-indigo-400 text-white'
                          : 'border-slate-700 bg-surface-900'
                      }`}>
                        {isSelected && <Check className="w-3 h-3 stroke-[3]" />}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Optional Focus / Notes */}
          <div className="space-y-1.5 pt-1">
            <label className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
              <MessageSquare className="w-3.5 h-3.5 text-indigo-400" />
              <span>Пожелания к расширению (опционально):</span>
            </label>
            <textarea
              value={userNotes}
              onChange={(e) => setUserNotes(e.target.value)}
              placeholder="e.g. Добавь больше прикладных кейсов, архитектурных паттернов и продвинутой оптимизации..."
              rows={2}
              disabled={isExpanding}
              className="w-full bg-surface-950 border border-slate-800 rounded-2xl p-3 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 resize-none font-sans"
            />
          </div>

          {/* Mastery Preservation Note */}
          <div className="p-3 rounded-2xl bg-emerald-950/40 border border-emerald-500/30 flex items-start gap-2.5 text-xs text-emerald-300/90 leading-relaxed">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            <span>
              <strong>Прогресс сохраняется:</strong> Все уже освоенные вами уроки останутся отмеченными как пройденные. ИИ аккуратно интегрирует новые углубленные понятия в текущий граф.
            </span>
          </div>

          {/* Loading Animation */}
          {isExpanding && (
            <div className="p-4 rounded-2xl bg-surface-950/90 border border-indigo-500/30 flex items-center gap-3 animate-pulse">
              <Loader2 className="w-5 h-5 text-indigo-400 animate-spin shrink-0" />
              <div className="text-xs text-indigo-300 font-medium leading-tight">
                {expansionStep}
              </div>
            </div>
          )}

          {/* Submit Button */}
          <div className="pt-2">
            <button
              type="submit"
              disabled={isExpanding}
              className="w-full py-3.5 bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 disabled:opacity-50 text-white font-bold text-sm rounded-2xl shadow-lg shadow-indigo-600/30 flex items-center justify-center gap-2 transition-all cursor-pointer"
            >
              {isExpanding ? (
                <span>Расширение объема курса...</span>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  <span>Увеличить объем курса</span>
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
