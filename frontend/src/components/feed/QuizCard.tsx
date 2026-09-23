import React, { useState, useEffect } from 'react';
import { FeedCard, QuizResult } from '../../types';
import { LatexRenderer } from '../common/LatexRenderer';
import { VoiceRecorder } from '../common/VoiceRecorder';
import { CheckCircle2, XCircle, ArrowRight, Brain, Sparkles, Loader2, Check } from 'lucide-react';

interface QuizCardProps {
  card: FeedCard;
  onSubmitAnswer: (selectedOptionId: string) => Promise<QuizResult>;
  onSubmitVoiceAnswer: (selectedOptionId: string, audioBlob: Blob) => Promise<QuizResult>;
  onNextCard: () => void;
}

export const QuizCard: React.FC<QuizCardProps> = React.memo(({
  card,
  onSubmitAnswer,
  onSubmitVoiceAnswer,
  onNextCard,
}) => {
  const [selectedOptionId, setSelectedOptionId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<QuizResult | null>(null);

  // Clean reset whenever card changes
  useEffect(() => {
    setSelectedOptionId(null);
    setResult(null);
    setIsSubmitting(false);
  }, [card.card_id]);

  const handleSelectOption = (optionId: string) => {
    if (result || isSubmitting) return;
    setSelectedOptionId(optionId);
  };

  const handleDirectSubmit = async () => {
    if (!selectedOptionId || result || isSubmitting) return;
    setIsSubmitting(true);
    try {
      const res = await onSubmitAnswer(selectedOptionId);
      setResult(res);
    } catch (err: any) {
      console.error('Submit error:', err);
      alert('Failed to evaluate answer. Ensure backend is running.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleVoiceRecordFinished = async (audioBlob: Blob) => {
    if (!selectedOptionId || result || isSubmitting) return;
    setIsSubmitting(true);
    try {
      const res = await onSubmitVoiceAnswer(selectedOptionId, audioBlob);
      setResult(res);
    } catch (err: any) {
      console.error('Voice submit error:', err);
      alert('Failed to process voice reasoning.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="w-full max-w-2xl mx-auto bg-surface-900 border border-slate-800 rounded-3xl p-5 sm:p-6 shadow-xl flex flex-col justify-between relative overflow-hidden">
      {/* Top Header */}
      <div>
        <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-3">
          <div className="flex items-center gap-2">
            <span className={`text-[11px] sm:text-xs font-bold px-2.5 py-0.5 sm:py-1 rounded-full uppercase tracking-wider ${
              card.card_mode === 'srs'
                ? 'bg-amber-950 border border-amber-500 text-amber-300'
                : 'bg-indigo-950 border border-indigo-500 text-indigo-300'
            }`}>
              {card.card_mode === 'srs' ? 'SRS Review' : 'Diagnostic Arc'}
            </span>
          </div>

          <div className="flex items-center gap-1.5 text-xs text-slate-400 font-semibold">
            <Brain className="w-4 h-4 text-indigo-400" />
            <span>GotThat Engine</span>
          </div>
        </div>

        {/* Concept Title */}
        <h2 className="text-lg sm:text-xl font-bold text-white mb-1.5 leading-snug">
          {card.concept_title}
        </h2>

        {/* Question Prompt Markdown + Latex */}
        <div className="text-slate-200 text-xs sm:text-sm leading-relaxed mb-3 font-sans">
          <LatexRenderer content={card.prompt_markdown} />
        </div>
      </div>

      {/* Options List */}
      <div className="space-y-1.5 my-2">
        {card.options.map((option) => {
          const isSelected = selectedOptionId === option.id;
          let optionStyle = 'bg-[#151e33] text-slate-200 hover:bg-[#1e2b48] hover:text-white';

          if (result) {
            if (result.is_correct && isSelected) {
              optionStyle = 'bg-[#064e3b] text-emerald-100 font-medium ring-1 ring-emerald-500';
            } else if (!result.is_correct && isSelected) {
              optionStyle = 'bg-[#4c0519] text-rose-100 ring-1 ring-rose-500';
            } else {
              optionStyle = 'bg-[#101726] text-slate-500 opacity-40';
            }
          } else if (isSelected) {
            optionStyle = 'bg-[#1e1b4b] text-white ring-1 ring-indigo-500';
          }

          return (
            <button
              key={option.id}
              onClick={() => handleSelectOption(option.id)}
              disabled={isSubmitting || !!result}
              className={`w-full text-left py-2.5 px-4 rounded-xl transition-colors duration-150 ${optionStyle} ${
                result || isSubmitting ? 'cursor-default' : 'cursor-pointer'
              }`}
            >
              <div className="text-xs sm:text-sm leading-snug">
                <LatexRenderer content={option.text} />
              </div>
            </button>
          );
        })}
      </div>

      {/* Footer Controls / Result Feedback Area */}
      <div className="pt-3 border-t border-slate-800">
        {!result ? (
          <div className="space-y-2.5">
            {/* Action Bar: Voice Yap or Standard Tap */}
            <div className="flex items-center gap-2.5">
              <VoiceRecorder
                onAudioRecorded={handleVoiceRecordFinished}
                disabled={!selectedOptionId || isSubmitting}
              />

              <button
                onClick={handleDirectSubmit}
                disabled={!selectedOptionId || isSubmitting}
                className="flex-1 h-[38px] px-5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white font-semibold text-xs sm:text-sm rounded-xl shadow-md flex items-center justify-center gap-2 transition-colors active:scale-[0.99]"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Evaluating...</span>
                  </>
                ) : (
                  <>
                    <Check className="w-4 h-4 text-indigo-200" strokeWidth={2.5} />
                    <span>Submit Choice</span>
                  </>
                )}
              </button>
            </div>
            
            <p className="text-[11px] text-center text-slate-500 font-medium">
              Tip: Click option first, then record voice reasoning to let AI verify your mental model!
            </p>
          </div>
        ) : (
          <div className="space-y-3 animate-fadeIn">
            {/* Feedback Message */}
            <div className={`p-3.5 sm:p-4 rounded-xl border flex items-start gap-3 ${
              result.is_correct
                ? 'bg-[#064e3b] border-emerald-500 text-emerald-100'
                : 'bg-[#4c0519] border-rose-500 text-rose-100'
            }`}>
              {result.is_correct ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
              ) : (
                <XCircle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
              )}
              <div className="flex-1">
                <div className="font-bold text-sm">
                  {result.is_correct ? 'Mastery Confirmed!' : 'Knowledge Gap Identified'}
                </div>
                <div className="text-xs mt-1 leading-relaxed opacity-90">
                  <LatexRenderer content={result.explanation} />
                </div>
                {result.voice_analysis && (
                  <div className="mt-2 text-[11px] p-2.5 rounded-xl bg-surface-950 border border-indigo-500 text-indigo-300">
                    <span className="font-semibold flex items-center gap-1 mb-1">
                      <Sparkles className="w-3.5 h-3.5 text-indigo-400" /> Spoken Mental Model Analysis:
                    </span>
                    <p className="text-slate-300">{result.voice_analysis.reasoning_summary}</p>
                  </div>
                )}
              </div>
            </div>

            {/* Next Card Button */}
            <button
              onClick={onNextCard}
              className="w-full py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs sm:text-sm shadow-md flex items-center justify-center gap-2 transition-colors"
            >
              <span>Next Question</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
});
