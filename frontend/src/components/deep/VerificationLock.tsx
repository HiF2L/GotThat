import React, { useState, useEffect } from 'react';
import { VerificationChallenge, DeepStepResult } from '../../types';
import { LatexRenderer } from '../common/LatexRenderer';
import {
  HelpCircle,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  Loader2,
  Sparkles,
  RotateCcw,
} from 'lucide-react';

interface VerificationLockProps {
  challenge: VerificationChallenge;
  onSubmit: (selectedOptionId: string) => Promise<DeepStepResult>;
  onProceedNextStep: () => void;
  allowSkip?: boolean;
  isLoading?: boolean;
}

export const VerificationLock: React.FC<VerificationLockProps> = React.memo(({
  challenge,
  onSubmit,
  onProceedNextStep,
  allowSkip = true,
  isLoading = false,
}) => {
  const [selectedOptionId, setSelectedOptionId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [result, setResult] = useState<DeepStepResult | null>(null);

  // Reset when challenge changes
  useEffect(() => {
    setSelectedOptionId(null);
    setResult(null);
    setIsSubmitting(false);
  }, [challenge.item_id]);

  const handleSelect = (optionId: string) => {
    if (isSubmitting) return;
    if (result) {
      setResult(null); // Allow changing answer/retrying
    }
    setSelectedOptionId(optionId);
  };

  const handleConfirmSubmit = async () => {
    if (!selectedOptionId || isSubmitting) return;
    setIsSubmitting(true);
    try {
      const res = await onSubmit(selectedOptionId);
      setResult(res);
    } catch (err: any) {
      console.error('Verification submit error:', err);
      alert('Не удалось отправить ответ. Пожалуйста, попробуйте еще раз.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="w-full bg-surface-900 border border-slate-800 rounded-3xl p-5 sm:p-6 shadow-xl space-y-3.5 sm:space-y-4 animate-fadeIn">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 border-b border-slate-800 pb-2.5">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-full bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400 shrink-0">
            <HelpCircle className="w-3.5 h-3.5" />
          </div>
          <div>
            <span className="text-xs font-bold uppercase tracking-wider text-slate-200">
              Проверка понимания
            </span>
          </div>
        </div>

        {selectedOptionId && !result && (
          <span className="text-xs text-indigo-300 font-medium px-2.5 py-0.5 rounded-full bg-indigo-950 border border-indigo-500/40">
            Ответ выбран
          </span>
        )}
      </div>

      {/* Question Prompt */}
      <div className="text-sm sm:text-[15px] font-semibold text-white leading-relaxed px-0.5">
        <LatexRenderer content={challenge.prompt_markdown} />
      </div>

      {/* Options */}
      <div className="space-y-1.5">
        {challenge.options.map((option) => {
          const isSelected = selectedOptionId === option.id;
          let containerStyle =
            'bg-[#151e33] hover:bg-[#1e2b48] hover:text-white text-slate-200';

          if (result) {
            if (result.is_correct && isSelected) {
              containerStyle = 'bg-[#064e3b] text-emerald-100 font-medium ring-1 ring-emerald-500';
            } else if (!result.is_correct && isSelected) {
              containerStyle = 'bg-[#4c0519] text-rose-100 ring-1 ring-rose-500';
            } else {
              containerStyle = 'bg-[#101726] opacity-60 text-slate-400';
            }
          } else if (isSelected) {
            containerStyle =
              'bg-[#1e1b4b] text-white ring-1 ring-indigo-500';
          }

          return (
            <button
              key={option.id}
              onClick={() => handleSelect(option.id)}
              disabled={isSubmitting}
              className={`w-full text-left py-2.5 px-4 rounded-xl transition-colors duration-150 cursor-pointer disabled:cursor-default ${containerStyle}`}
            >
              <div className="text-xs sm:text-sm leading-relaxed">
                <LatexRenderer content={option.text} />
              </div>
            </button>
          );
        })}
      </div>

      {/* Submit or Result Feedback */}
      {!result ? (
        <div className="flex flex-col items-center gap-2.5 pt-2">
          <button
            onClick={handleConfirmSubmit}
            disabled={!selectedOptionId || isSubmitting || isLoading}
            className="w-full sm:w-auto min-w-[220px] px-8 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:hover:bg-indigo-600 text-white font-semibold text-xs sm:text-sm rounded-xl shadow-md flex items-center justify-center gap-2 transition-colors active:scale-[0.99] cursor-pointer disabled:cursor-not-allowed"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Проверяю ответ...</span>
              </>
            ) : isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Загрузка...</span>
              </>
            ) : (
              <>
                <span>Проверить ответ</span>
                <Sparkles className="w-4 h-4" />
              </>
            )}
          </button>

          {allowSkip && onProceedNextStep && (
            <button
              onClick={onProceedNextStep}
              disabled={isLoading || isSubmitting}
              className="text-xs text-slate-400 hover:text-indigo-300 disabled:opacity-40 transition-colors flex items-center gap-1.5 font-medium py-1 px-3 rounded-lg hover:bg-surface-950/60 cursor-pointer disabled:cursor-not-allowed group"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Синтез урока...</span>
                </>
              ) : (
                <>
                  <span>Пропустить вопрос и перейти к следующему уроку</span>
                  <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
                </>
              )}
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-3 animate-fadeIn pt-2 border-t border-slate-800">
          {result.is_correct ? (
            <div className="p-3.5 sm:p-4 bg-[#064e3b] border border-emerald-500 rounded-xl text-xs sm:text-sm text-emerald-100 flex items-start gap-3 shadow-lg">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <p className="font-bold text-white flex items-center gap-1.5">
                  <Sparkles className="w-4 h-4 text-emerald-400" />
                  Отлично! Концепт закреплен
                </p>
                <p className="opacity-90 leading-relaxed text-xs sm:text-sm">{result.explanation}</p>
              </div>
            </div>
          ) : (
            <div className="p-3.5 sm:p-4 bg-[#4c0519] border border-rose-500 rounded-xl text-xs sm:text-sm text-rose-100 flex items-start gap-3 shadow-lg">
              <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
              <div className="space-y-1.5">
                <p className="font-bold text-white">Выявлено заблуждение</p>
                <p className="opacity-90 leading-relaxed text-xs sm:text-sm">{result.explanation}</p>
                {result.remediation_node && (
                  <div className="text-xs font-semibold text-amber-300 pt-1">
                    Подключаем разбор подтемы: {result.remediation_node.title}
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="flex items-center justify-center gap-3 pt-2 flex-wrap">
            <button
              onClick={() => setResult(null)}
              disabled={isLoading}
              className="px-5 py-2.5 bg-surface-950 hover:bg-surface-800 disabled:opacity-40 border border-slate-700/80 hover:border-slate-600 text-slate-300 hover:text-white font-medium text-xs sm:text-sm rounded-xl transition-all flex items-center gap-1.5 cursor-pointer disabled:cursor-not-allowed"
            >
              <RotateCcw className="w-3.5 h-3.5 text-slate-400" />
              <span>Ответить заново</span>
            </button>

            <button
              onClick={onProceedNextStep}
              disabled={isLoading}
              className="px-7 py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:hover:bg-emerald-600 text-white font-semibold text-xs sm:text-sm rounded-xl shadow-lg shadow-emerald-600/30 flex items-center justify-center gap-2 transition-all active:scale-[0.99] cursor-pointer disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Загрузка урока...</span>
                </>
              ) : (
                <>
                  <span>Следующий урок</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
});
