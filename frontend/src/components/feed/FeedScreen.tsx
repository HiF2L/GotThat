import React, { useEffect, useState } from 'react';
import { FeedCard, QuizResult } from '../../types';
import { apiClient } from '../../api/client';
import { QuizCard } from './QuizCard';
import { Loader2, RefreshCw, AlertCircle } from 'lucide-react';

interface FeedScreenProps {
  userId: string;
}

export const FeedScreen: React.FC<FeedScreenProps> = ({ userId }) => {
  const [currentCard, setCurrentCard] = useState<FeedCard | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCard = async () => {
    setLoading(true);
    setError(null);
    try {
      const card = await apiClient.getNextFeedCard(userId);
      setCurrentCard(card);
    } catch (err: any) {
      console.error(err);
      setError('Could not load next feed card. Make sure the backend server is running.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCard();
  }, [userId]);

  const handleSubmitAnswer = async (selectedOptionId: string): Promise<QuizResult> => {
    if (!currentCard) throw new Error('No active card');
    return await apiClient.submitQuizAttempt(
      userId,
      currentCard.card_id,
      currentCard.concept_id,
      [selectedOptionId],
    );
  };

  const handleSubmitVoiceAnswer = async (
    selectedOptionId: string,
    audioBlob: Blob,
  ): Promise<QuizResult> => {
    if (!currentCard) throw new Error('No active card');
    return await apiClient.submitVoiceReasoning(
      userId,
      currentCard.card_id,
      currentCard.concept_id,
      selectedOptionId,
      audioBlob,
    );
  };

  return (
    <div className="flex-1 flex flex-col justify-center items-center p-4 sm:p-6 max-w-2xl mx-auto w-full pb-20">
      {loading && !currentCard ? (
        <div className="flex flex-col items-center justify-center p-12 text-center">
          <Loader2 className="w-10 h-10 text-indigo-500 animate-spin mb-4" />
          <p className="text-sm text-slate-400 font-medium">
            Sampling optimal learning frontier...
          </p>
        </div>
      ) : error ? (
        <div className="bg-surface-900 border border-rose-500/30 p-6 rounded-3xl text-center max-w-sm">
          <AlertCircle className="w-10 h-10 text-rose-400 mx-auto mb-3" />
          <p className="text-sm text-slate-300 mb-4">{error}</p>
          <button
            onClick={fetchCard}
            className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 rounded-xl text-white text-sm font-semibold flex items-center gap-2 mx-auto"
          >
            <RefreshCw className="w-4 h-4" />
            <span>Try Again</span>
          </button>
        </div>
      ) : currentCard ? (
        <QuizCard
          key={currentCard.card_id}
          card={currentCard}
          onSubmitAnswer={handleSubmitAnswer}
          onSubmitVoiceAnswer={handleSubmitVoiceAnswer}
          onNextCard={fetchCard}
        />
      ) : null}
    </div>
  );
};
