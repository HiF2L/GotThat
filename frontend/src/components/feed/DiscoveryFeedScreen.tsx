import React, { useEffect, useState, useCallback, useRef } from 'react';
import { DiscoveryLessonTeaser } from '../../types';
import { apiClient } from '../../api/client';
import { LatexRenderer } from '../common/LatexRenderer';
import {
  Sparkles,
  ArrowRight,
  ArrowBigUp,
  ArrowBigDown,
  RefreshCw,
  BookOpen,
  CheckCircle2,
  AlertCircle,
  GraduationCap,
  Share2,
  Bookmark,
  Check,
} from 'lucide-react';

interface DiscoveryFeedScreenProps {
  userId: string;
  isActive?: boolean;
  feedRefreshTrigger?: number;
  onOpenLesson: (conceptId: string, trackIdentifier?: string) => void;
  onOpenTrack?: (trackIdentifier: string) => void;
}

export const DiscoveryFeedScreen: React.FC<DiscoveryFeedScreenProps> = ({
  userId,
  isActive = true,
  feedRefreshTrigger = 0,
  onOpenLesson,
  onOpenTrack,
}) => {
  const [teasers, setTeasers] = useState<DiscoveryLessonTeaser[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [bookmarkedIds, setBookmarkedIds] = useState<Set<string>>(() => {
    try {
      const saved = localStorage.getItem('gotthat_bookmarked_concepts');
      return saved ? new Set(JSON.parse(saved)) : new Set();
    } catch {
      return new Set();
    }
  });
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const scrollPosRef = useRef<number>(0);
  const wasActiveRef = useRef<boolean>(isActive);
  const isInitialMount = useRef<boolean>(true);
  const prevTriggerRef = useRef<number>(feedRefreshTrigger);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage((cur) => (cur === msg ? null : cur));
    }, 2400);
  };

  const fetchFeed = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.getDiscoveryFeed(userId, 25);
      setTeasers(data);
    } catch (err: any) {
      console.error('Failed to load discovery feed:', err);
      setError('Не удалось загрузить рекомендации уроков. Убедитесь, что сервер запущен.');
    } finally {
      setLoading(false);
    }
  }, [userId]);

  // Continuously track window scroll position while the feed is active
  useEffect(() => {
    if (!isActive) return;

    const handleScroll = () => {
      scrollPosRef.current = window.scrollY;
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', handleScroll);
    };
  }, [isActive]);

  // Initial load and tab transition behavior:
  // If the user returns to the feed while at the top (scrollTop <= 120), refresh & shuffle posts.
  // If the user was already reading down the feed (scrollTop > 120), preserve posts and restore scroll position.
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      wasActiveRef.current = isActive;
      fetchFeed();
      return;
    }

    if (isActive && !wasActiveRef.current) {
      if (scrollPosRef.current <= 120) {
        // Return to top: refresh feed with fresh shuffled posts
        fetchFeed();
        window.scrollTo({ top: 0, behavior: 'instant' });
      } else {
        // Return to where user was reading: preserve feed state and restore scroll position
        const targetY = scrollPosRef.current;
        requestAnimationFrame(() => {
          window.scrollTo({ top: targetY, behavior: 'instant' });
          setTimeout(() => {
            if (isActive) {
              window.scrollTo({ top: targetY, behavior: 'instant' });
            }
          }, 40);
        });
      }
    }

    wasActiveRef.current = isActive;
  }, [isActive, fetchFeed]);

  // When clicking the Feed navigation tab or logo while already on the Feed:
  // If scrolled down -> smooth scroll to top.
  // If already at the top -> refresh & shuffle.
  useEffect(() => {
    if (feedRefreshTrigger > 0 && feedRefreshTrigger !== prevTriggerRef.current) {
      prevTriggerRef.current = feedRefreshTrigger;
      if (window.scrollY > 120) {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      } else {
        fetchFeed();
      }
    }
  }, [feedRefreshTrigger, fetchFeed]);

  const handleVote = async (
    conceptId: string,
    currentVote: 'upvote' | 'downvote' | null | undefined,
    voteAction: 'upvote' | 'downvote'
  ) => {
    const nextVote: 'upvote' | 'downvote' | null = currentVote === voteAction ? null : voteAction;

    let delta = 0;
    if (currentVote === 'upvote') delta -= 1;
    if (currentVote === 'downvote') delta += 1;
    if (nextVote === 'upvote') delta += 1;
    if (nextVote === 'downvote') delta -= 1;

    // Optimistic UI update
    setTeasers((prev) =>
      prev.map((t) => {
        if (t.concept_id !== conceptId) return t;
        const curScore = t.score ?? 0;
        const curUp = t.upvotes ?? 0;
        const curDown = t.downvotes ?? 0;

        return {
          ...t,
          user_vote: nextVote,
          score: curScore + delta,
          upvotes: nextVote === 'upvote' ? curUp + 1 : currentVote === 'upvote' ? Math.max(0, curUp - 1) : curUp,
          downvotes: nextVote === 'downvote' ? curDown + 1 : currentVote === 'downvote' ? Math.max(0, curDown - 1) : curDown,
        };
      })
    );

    try {
      const apiVoteType = nextVote === null ? 'clear' : nextVote;
      const res = await apiClient.voteConcept(userId, conceptId, apiVoteType);
      setTeasers((prev) =>
        prev.map((t) => {
          if (t.concept_id !== conceptId) return t;
          return {
            ...t,
            user_vote: res.user_vote,
            score: res.score,
            upvotes: res.upvotes,
            downvotes: res.downvotes,
          };
        })
      );
    } catch (err) {
      console.error('Failed to submit vote:', err);
      showToast('Ошибка сохранения голоса');
    }
  };

  const toggleBookmark = (conceptId: string) => {
    setBookmarkedIds((prev) => {
      const next = new Set(prev);
      if (next.has(conceptId)) {
        next.delete(conceptId);
        showToast('Удалено из закладок');
      } else {
        next.add(conceptId);
        showToast('Сохранено в закладки');
      }
      try {
        localStorage.setItem('gotthat_bookmarked_concepts', JSON.stringify(Array.from(next)));
      } catch (e) {
        console.error(e);
      }
      return next;
    });
  };

  const handleShare = (teaser: DiscoveryLessonTeaser) => {
    const url = `${window.location.origin}/#deep?concept=${teaser.concept_id}&track=${teaser.track_slug || teaser.track_id}`;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(url).then(() => {
        showToast('Ссылка на урок скопирована!');
      }).catch(() => {
        showToast('Не удалось скопировать ссылку');
      });
    } else {
      showToast(`Урок: ${teaser.concept_title}`);
    }
  };

  return (
    <div className="flex-1 flex flex-col items-center p-3 sm:p-6 lg:p-8 max-w-3xl mx-auto w-full pb-28 sm:pb-32 animate-fadeIn min-h-[calc(100vh-5rem)]">
      {/* Toast Notification in Bottom Right Corner */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 px-4 py-2.5 bg-slate-900/95 border border-indigo-500/50 text-white text-xs sm:text-sm font-semibold rounded-2xl shadow-2xl backdrop-blur-md flex items-center gap-2.5 animate-fadeIn">
          <Check className="w-4 h-4 text-indigo-400" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Feed Header */}
      <div className="w-full flex items-center justify-between mb-5 px-1">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h1 className="text-lg sm:text-xl font-black text-white tracking-tight leading-none">
              Лента рекомендаций
            </h1>
            <p className="text-[11px] sm:text-xs text-slate-400 mt-1">
              Ключевые интуиции и вступления уроков из всей базы знаний
            </p>
          </div>
        </div>

        <button
          onClick={fetchFeed}
          disabled={loading}
          className="p-2 sm:px-3 sm:py-2 rounded-xl bg-surface-900 hover:bg-surface-800 border border-slate-800 text-slate-400 hover:text-white transition-colors cursor-pointer flex items-center gap-1.5 text-xs"
          title="Обновить ленту"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-indigo-400' : ''}`} />
          <span className="hidden sm:inline">Обновить</span>
        </button>
      </div>

      {/* Feed Content */}
      {loading && teasers.length === 0 ? (
        <div className="flex flex-col items-center justify-center p-16 text-center space-y-4 w-full">
          <div className="w-14 h-14 rounded-2xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
            <Sparkles className="w-7 h-7 animate-spin" />
          </div>
          <div>
            <h3 className="text-base font-bold text-white">Формируем персональную ленту...</h3>
            <p className="text-xs text-slate-400 mt-1">
              Подбираем захватывающие идеи и вступления из курсов
            </p>
          </div>
        </div>
      ) : error ? (
        <div className="bg-surface-900 border border-rose-500/30 p-8 rounded-3xl text-center max-w-md shadow-2xl space-y-4 my-8">
          <div className="w-12 h-12 rounded-2xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center mx-auto text-rose-400">
            <AlertCircle className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-base font-bold text-white">Ошибка загрузки</h3>
            <p className="text-xs text-slate-400 mt-1.5 leading-relaxed">{error}</p>
          </div>
          <button
            onClick={fetchFeed}
            className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 rounded-xl text-white text-xs font-bold transition-all shadow-md flex items-center gap-2 mx-auto cursor-pointer"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Повторить попытку</span>
          </button>
        </div>
      ) : teasers.length > 0 ? (
        <div className="w-full space-y-4 sm:space-y-5">
          {teasers.map((teaser) => {
            const isUpvoted = teaser.user_vote === 'upvote';
            const isDownvoted = teaser.user_vote === 'downvote';
            const score = teaser.score ?? 0;
            const isBookmarked = bookmarkedIds.has(teaser.concept_id);
            return (
              <article
                key={teaser.concept_id}
                className="bg-surface-900 border border-slate-800/90 hover:border-slate-700/80 rounded-2xl sm:rounded-3xl shadow-lg transition-all duration-200 overflow-hidden p-5 sm:p-6 flex flex-col justify-between space-y-4 group relative w-full"
              >
                {/* Post Header: Course Badge & Status */}
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                  <button
                    type="button"
                    onClick={() => {
                      const trackRef = teaser.track_slug || teaser.track_id;
                      if (onOpenTrack && trackRef) {
                        onOpenTrack(trackRef);
                      } else {
                        onOpenLesson(teaser.concept_id, trackRef);
                      }
                    }}
                    className="inline-flex items-center gap-1.5 px-3 py-1 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700/60 hover:border-indigo-500/50 text-slate-300 hover:text-white font-semibold text-[11px] sm:text-xs transition-colors cursor-pointer group/badge text-left"
                    title="Открыть курс в Knowledge Map"
                  >
                    <BookOpen className="w-3.5 h-3.5 text-indigo-400 group-hover/badge:text-indigo-300" />
                    <span className="truncate max-w-[240px] sm:max-w-sm">{teaser.track_title}</span>
                  </button>

                  <div>
                    {teaser.is_mastered ? (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-950/70 border border-emerald-500/40 text-emerald-300 text-[11px] font-bold">
                        <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                        <span>Освоено</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-indigo-950/70 border border-indigo-500/40 text-indigo-300 text-[11px] font-bold">
                        <GraduationCap className="w-3 h-3 text-indigo-400" />
                        <span>Новый урок</span>
                      </span>
                    )}
                  </div>
                </div>

                {/* Post Title */}
                <div>
                  <h2
                    onClick={() => onOpenLesson(teaser.concept_id, teaser.track_slug || teaser.track_id)}
                    className="text-lg sm:text-xl font-bold text-white group-hover:text-indigo-300 transition-colors cursor-pointer leading-snug tracking-tight"
                  >
                    {teaser.concept_title}
                  </h2>
                  {teaser.concept_code && (
                    <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider block mt-0.5">
                      {teaser.concept_code}
                    </span>
                  )}
                </div>

                {/* Article Content (Full text, floated side images matching Deep Tutor) */}
                <div className="text-slate-200 text-sm sm:text-base leading-relaxed flow-root">
                  <LatexRenderer content={teaser.teaser_text} className="feed-markdown" />
                </div>

                {/* Bottom Action Bar: Upvote/Downvote BEFORE Bookmark and Share */}
                <div className="pt-2 flex flex-wrap items-center justify-between gap-3 border-t border-slate-800/50">
                  <div className="flex items-center gap-2">
                    {/* Upvote / Score / Downvote Pill */}
                    <div className="flex items-center bg-surface-950/80 border border-slate-800/80 rounded-xl px-1.5 py-0.5 shadow-inner">
                      <button
                        onClick={() => handleVote(teaser.concept_id, teaser.user_vote, 'upvote')}
                        className={`p-1.5 rounded-lg transition-colors cursor-pointer ${
                          isUpvoted
                            ? 'text-[#FF4500] bg-[#FF4500]/15'
                            : 'text-slate-400 hover:text-[#FF4500] hover:bg-slate-800/60'
                        }`}
                        title="Нравится (Upvote)"
                        aria-label="Upvote"
                      >
                        <ArrowBigUp className={`w-5 h-5 ${isUpvoted ? 'fill-current' : ''}`} />
                      </button>

                      <span
                        className={`font-mono text-xs sm:text-sm font-black px-1.5 transition-colors select-none ${
                          isUpvoted
                            ? 'text-[#FF4500]'
                            : isDownvoted
                            ? 'text-[#7193FF]'
                            : 'text-slate-300'
                        }`}
                      >
                        {score}
                      </span>

                      <button
                        onClick={() => handleVote(teaser.concept_id, teaser.user_vote, 'downvote')}
                        className={`p-1.5 rounded-lg transition-colors cursor-pointer ${
                          isDownvoted
                            ? 'text-[#7193FF] bg-[#7193FF]/15'
                            : 'text-slate-400 hover:text-[#7193FF] hover:bg-slate-800/60'
                        }`}
                        title="Не нравится (Downvote)"
                        aria-label="Downvote"
                      >
                        <ArrowBigDown className={`w-5 h-5 ${isDownvoted ? 'fill-current' : ''}`} />
                      </button>
                    </div>

                    {/* Bookmark Button */}
                    <button
                      onClick={() => toggleBookmark(teaser.concept_id)}
                      className={`p-2 sm:p-2.5 rounded-xl border transition-colors cursor-pointer flex items-center gap-1.5 text-xs ${
                        isBookmarked
                          ? 'bg-amber-950/60 border-amber-500/40 text-amber-300'
                          : 'bg-surface-950/80 hover:bg-surface-800 border-slate-800 text-slate-400 hover:text-slate-200'
                      }`}
                      title={isBookmarked ? 'В закладках' : 'Сохранить в закладки'}
                    >
                      <Bookmark className={`w-4 h-4 ${isBookmarked ? 'fill-current' : ''}`} />
                    </button>

                    {/* Share Button */}
                    <button
                      onClick={() => handleShare(teaser)}
                      className="p-2 sm:p-2.5 rounded-xl bg-surface-950/80 hover:bg-surface-800 border border-slate-800 text-slate-400 hover:text-slate-200 transition-colors cursor-pointer flex items-center gap-1.5 text-xs"
                      title="Поделиться уроком"
                    >
                      <Share2 className="w-4 h-4" />
                    </button>
                  </div>

                  {/* Primary CTA: Jump into Lesson */}
                  <button
                    onClick={() => onOpenLesson(teaser.concept_id, teaser.track_slug || teaser.track_id)}
                    className="px-4 py-2 sm:px-5 sm:py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs sm:text-sm transition-all shadow-md shadow-indigo-600/20 flex items-center gap-2 cursor-pointer group/btn"
                  >
                    <span>Читать дальше</span>
                    <ArrowRight className="w-3.5 h-3.5 sm:w-4 sm:h-4 group-hover/btn:translate-x-1 transition-transform" />
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="bg-surface-900 border border-slate-800 p-8 rounded-3xl text-center max-w-sm space-y-4 my-8">
          <BookOpen className="w-10 h-10 text-slate-500 mx-auto" />
          <h3 className="text-base font-bold text-white">Рекомендации пока пусты</h3>
          <p className="text-xs text-slate-400">Начните изучать темы на вкладке «Курсы», чтобы наполнить ленту.</p>
          <button
            onClick={fetchFeed}
            className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 rounded-xl text-white text-xs font-bold transition-all shadow-md flex items-center gap-2 mx-auto cursor-pointer"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Обновить</span>
          </button>
        </div>
      )}
    </div>
  );
};
