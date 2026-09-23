import React, { useState, useEffect } from 'react';
import { X, Globe, Cpu, Sparkles, Check, DollarSign, Layers, Volume2, Loader2, RefreshCw } from 'lucide-react';
import { apiClient } from '../../api/client';

export interface AIModelOption {
  id: string;
  name: string;
  provider: string;
  providerIcon: string;
  price: string;
  description?: string;
  badge?: string;
}

export interface TtsVoiceOption {
  id: string;
  name: string;
  lang: string;
  flag: string;
  gender: string;
  description: string;
  badge?: string;
}

export const AVAILABLE_TTS_VOICES: TtsVoiceOption[] = [
  {
    id: 'ru-RU-SvetlanaNeural',
    name: 'Светлана (Svetlana)',
    lang: 'Русский',
    flag: '🇷🇺',
    gender: 'Женский',
    description: 'Студийный выразительный голос для комфортного восприятия уроков',
    badge: 'Рекомендуется',
  },
  {
    id: 'ru-RU-DmitryNeural',
    name: 'Дмитрий (Dmitry)',
    lang: 'Русский',
    flag: '🇷🇺',
    gender: 'Мужской',
    description: 'Глубокий, размеренный и авторитетный голос профессора',
  },
  {
    id: 'en-US-JennyNeural',
    name: 'Jenny',
    lang: 'English (US)',
    flag: '🇺🇸',
    gender: 'Женский',
    description: 'Естественный, живой американский английский',
  },
  {
    id: 'en-US-GuyNeural',
    name: 'Guy',
    lang: 'English (US)',
    flag: '🇺🇸',
    gender: 'Мужской',
    description: 'Чёткий, уверенный мужской тембр',
  },
  {
    id: 'en-GB-SoniaNeural',
    name: 'Sonia',
    lang: 'English (UK)',
    flag: '🇬🇧',
    gender: 'Женский',
    description: 'Элегантный британский академический акцент',
  },
  {
    id: 'en-US-AriaNeural',
    name: 'Aria',
    lang: 'English (US)',
    flag: '🇺🇸',
    gender: 'Женский',
    description: 'Ясный, образный и мелодичный голос',
  },
];

export const AVAILABLE_AI_MODELS: AIModelOption[] = [
  // 🟩 OpenAI
  {
    id: 'openai/gpt-4.1-mini',
    name: 'GPT‑4.1 Mini',
    provider: 'OpenAI (ProxyAPI)',
    providerIcon: '🟩',
    price: '104 ₽ / 413 ₽',
    description: 'Основная модель уроков: эталонная математическая строгость LaTeX, высокая скорость (136 tok/s) и лучшая цена',
    badge: 'Рекомендуется',
  },

  // 🔮 Google Gemini
  {
    id: 'google/gemini-2.5-flash',
    name: 'Gemini 2.5 Flash',
    provider: 'Google Gemini',
    providerIcon: '🔮',
    price: '78 ₽ / 645 ₽',
    description: 'Сверхбыстрый инференс (182 tok/s), контекст 1M токенов, живые метафоры и мультимодальность',
    badge: 'Суперскорость',
  },
  {
    id: 'google/gemini-3-flash-preview',
    name: 'Gemini 3 Flash Preview',
    provider: 'Google Gemini',
    providerIcon: '🔮',
    price: '152 ₽ / 910 ₽',
    description: 'Интеллектуальный синтез курсов, построение адаптивных DAG-маршрутов на 25-35 уроков',
  },
  {
    id: 'google/gemini-2.5-pro',
    name: 'Gemini 2.5 Pro',
    provider: 'Google Gemini',
    providerIcon: '🔮',
    price: '323 ₽ / 2 577 ₽',
    description: 'Глубокое мультимодальное рассуждение и академический синтез сложных тем',
  },

  // ⚡ DeepSeek
  {
    id: 'deepseek/deepseek-chat',
    name: 'DeepSeek V3 (Chat)',
    provider: 'DeepSeek',
    providerIcon: '⚡',
    price: '43 ₽ / 126 ₽',
    description: 'Ультрадоступная модель для точных наук, физики, математических формул и программного кода',
    badge: 'Экономный выбор',
  },
  {
    id: 'deepseek/deepseek-v4-pro',
    name: 'DeepSeek V4 Pro',
    provider: 'DeepSeek',
    providerIcon: '⚡',
    price: '190 ₽ / 375 ₽',
    description: 'Выдающаяся аналитическая глубина и отличное понимание сложных алгоритмов',
  },

  // 🧠 Anthropic
  {
    id: 'anthropic/claude-sonnet-4-5',
    name: 'Claude Sonnet 4.5',
    provider: 'Anthropic',
    providerIcon: '🧠',
    price: '774 ₽ / 3 866 ₽',
    description: 'Шедевральная проза: максимальная глубина нарратива, философия, история и психология без клише',
    badge: 'Премиум проза',
  },
  {
    id: 'anthropic/claude-opus-4-1',
    name: 'Claude Opus 4.1',
    provider: 'Anthropic',
    providerIcon: '🧠',
    price: '3 866 ₽ / 19 327 ₽',
    description: 'Флагманский аналитический интеллект для сложнейших междисциплинарных исследований',
  },

  // 🌙 Moonshot AI
  {
    id: 'moonshotai/kimi-k3',
    name: 'Kimi K3',
    provider: 'Moonshot AI',
    providerIcon: '🌙',
    price: '550 ₽ / 2 700 ₽',
    description: 'Длинный контекст, строгая логика рассуждений и структурированный вывод',
  },
];


interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentLanguage: 'ru' | 'en';
  onLanguageChange: (lang: 'ru' | 'en') => void;
  currentModel?: string;
  onModelChange?: (modelId: string) => void;
  currentTtsVoice?: string;
  onTtsVoiceChange?: (voice: string) => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  currentLanguage,
  onLanguageChange,
  currentModel = 'kimi-k3',
  onModelChange,
  currentTtsVoice = 'alloy',
  onTtsVoiceChange,
}) => {
  const [activeTab, setActiveTab] = useState<'models' | 'language' | 'voice' | 'costs'>('models');
  const [costsData, setCostsData] = useState<any>(null);
  const [loadingCosts, setLoadingCosts] = useState<boolean>(false);

  const fetchCosts = async () => {
    setLoadingCosts(true);
    try {
      const data = await apiClient.getCostsReport();
      setCostsData(data);
    } catch (e) {
      console.error('Failed to load costs:', e);
    } finally {
      setLoadingCosts(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'costs' && !costsData) {
      fetchCosts();
    }
  }, [activeTab]);

  if (!isOpen) return null;

  // Group models by provider
  const providers = Array.from(new Set(AVAILABLE_AI_MODELS.map((m) => m.provider)));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/80 animate-fadeIn">
      <div className="bg-surface-900 border border-slate-800 rounded-3xl w-full max-w-2xl shadow-2xl overflow-hidden animate-scaleUp flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-slate-800/80 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">Параметры обучения / Settings</h2>
              <p className="text-[11px] text-slate-400">Выбор AI-модели, языка и голоса озвучки</p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-surface-950 border border-slate-800 flex items-center justify-center text-slate-400 hover:text-white hover:border-slate-700 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tab Switcher */}
        <div className="flex border-b border-slate-800/80 px-6 pt-3 gap-3 shrink-0 bg-surface-950/40 flex-wrap">
          <button
            onClick={() => setActiveTab('models')}
            className={`pb-3 text-xs font-bold transition-all border-b-2 flex items-center gap-2 ${
              activeTab === 'models'
                ? 'text-indigo-400 border-indigo-500'
                : 'text-slate-400 border-transparent hover:text-slate-200'
            }`}
          >
            <Cpu className="w-4 h-4" />
            <span>AI Модели</span>
          </button>

          <button
            onClick={() => setActiveTab('voice')}
            className={`pb-3 text-xs font-bold transition-all border-b-2 flex items-center gap-2 ${
              activeTab === 'voice'
                ? 'text-indigo-400 border-indigo-500'
                : 'text-slate-400 border-transparent hover:text-slate-200'
            }`}
          >
            <Volume2 className="w-4 h-4" />
            <span>Голос озвучки (TTS)</span>
          </button>

          <button
            onClick={() => setActiveTab('language')}
            className={`pb-3 text-xs font-bold transition-all border-b-2 flex items-center gap-2 ${
              activeTab === 'language'
                ? 'text-indigo-400 border-indigo-500'
                : 'text-slate-400 border-transparent hover:text-slate-200'
            }`}
          >
            <Globe className="w-4 h-4" />
            <span>Язык курса</span>
          </button>

          <button
            onClick={() => setActiveTab('costs')}
            className={`pb-3 text-xs font-bold transition-all border-b-2 flex items-center gap-2 ${
              activeTab === 'costs'
                ? 'text-emerald-400 border-emerald-500'
                : 'text-slate-400 border-transparent hover:text-slate-200'
            }`}
          >
            <DollarSign className="w-4 h-4" />
            <span>Расходы и Токены</span>
          </button>
        </div>

        {/* Scrollable Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1">
          {activeTab === 'models' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
                    <Layers className="w-4 h-4 text-indigo-400" />
                    <span>Выбор языковой модели (LLM Engine)</span>
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Стоимость указана за 1 млн входных / 1 млн выходных токенов
                  </p>
                </div>
              </div>

              {/* Providers & Models List */}
              <div className="space-y-5">
                {providers.map((provider) => {
                  const providerModels = AVAILABLE_AI_MODELS.filter((m) => m.provider === provider);
                  const icon = providerModels[0]?.providerIcon || '🤖';

                  return (
                    <div key={provider} className="space-y-2.5">
                      <div className="flex items-center gap-2 px-1 text-xs font-bold text-slate-300">
                        <span>{icon}</span>
                        <span>{provider}</span>
                      </div>

                      <div className="space-y-2">
                        {providerModels.map((model) => {
                          const isSelected = (currentModel || 'kimi-k3').toLowerCase() === model.id.toLowerCase();

                          return (
                            <div
                              key={model.id}
                              onClick={() => onModelChange && onModelChange(model.id)}
                              className={`p-3.5 sm:p-4 rounded-2xl border transition-all cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                                isSelected
                                  ? 'bg-indigo-950/80 border-indigo-500 ring-2 ring-indigo-500/40 shadow-lg shadow-indigo-600/20'
                                  : 'bg-surface-950/70 border-slate-800 hover:border-slate-700 hover:bg-surface-950'
                              }`}
                            >
                              <div className="flex items-start gap-3 flex-1 min-w-0">
                                <div className="mt-0.5 shrink-0">
                                  <div className={`w-5 h-5 rounded-full flex items-center justify-center border ${
                                    isSelected
                                      ? 'bg-indigo-600 border-indigo-400 text-white'
                                      : 'border-slate-700 bg-surface-900'
                                  }`}>
                                    {isSelected && <Check className="w-3 h-3 stroke-[3]" />}
                                  </div>
                                </div>

                                <div className="min-w-0 flex-1">
                                  <div className="flex items-center gap-2 flex-wrap">
                                    <span className={`text-xs sm:text-sm font-bold ${isSelected ? 'text-white' : 'text-slate-200'}`}>
                                      {model.name}
                                    </span>
                                    {model.badge && (
                                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-950 border border-emerald-500/40 text-emerald-300">
                                        {model.badge}
                                      </span>
                                    )}
                                  </div>
                                  {model.description && (
                                    <p className="text-[11px] text-slate-400 mt-0.5">
                                      {model.description}
                                    </p>
                                  )}
                                </div>
                              </div>

                              {/* Price Tag */}
                              <div className="shrink-0 self-end sm:self-auto">
                                <span className={`text-xs font-mono font-semibold px-2.5 py-1 rounded-xl border flex items-center gap-1 ${
                                  isSelected
                                    ? 'bg-indigo-900/80 border-indigo-400/50 text-indigo-200'
                                    : 'bg-surface-900 border-slate-800 text-slate-300'
                                }`}>
                                  <DollarSign className="w-3 h-3 text-emerald-400" />
                                  <span>{model.price}</span>
                                </span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {activeTab === 'voice' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
                    <Volume2 className="w-4 h-4 text-indigo-400" />
                    <span>Голос озвучки уроков (Studio Neural TTS)</span>
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Выберите студийный нейросетевой голос для озвучивания учебных материалов курса
                  </p>
                </div>
              </div>

              <div className="space-y-2.5 pt-1">
                {AVAILABLE_TTS_VOICES.map((voice) => {
                  const isSelected = (currentTtsVoice || 'ru-RU-SvetlanaNeural').toLowerCase() === voice.id.toLowerCase();

                  return (
                    <div
                      key={voice.id}
                      onClick={() => onTtsVoiceChange && onTtsVoiceChange(voice.id)}
                      className={`p-3.5 sm:p-4 rounded-2xl border transition-all cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                        isSelected
                          ? 'bg-indigo-950/80 border-indigo-500 ring-2 ring-indigo-500/40 shadow-lg shadow-indigo-600/20'
                          : 'bg-surface-950/70 border-slate-800 hover:border-slate-700 hover:bg-surface-950'
                      }`}
                    >
                      <div className="flex items-start gap-3 flex-1 min-w-0">
                        <div className="mt-0.5 shrink-0">
                          <div className={`w-5 h-5 rounded-full flex items-center justify-center border ${
                            isSelected
                              ? 'bg-indigo-600 border-indigo-400 text-white'
                              : 'border-slate-700 bg-surface-900'
                          }`}>
                            {isSelected && <Check className="w-3 h-3 stroke-[3]" />}
                          </div>
                        </div>

                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-base">{voice.flag}</span>
                            <span className={`text-xs sm:text-sm font-bold ${isSelected ? 'text-white' : 'text-slate-200'}`}>
                              {voice.name}
                            </span>
                            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300">
                              {voice.gender}
                            </span>
                            {voice.badge && (
                              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-950 border border-emerald-500/40 text-emerald-300">
                                {voice.badge}
                              </span>
                            )}
                          </div>
                          <p className="text-[11px] text-slate-400 mt-0.5">
                            {voice.description}
                          </p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {activeTab === 'language' && (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
                <Globe className="w-4 h-4 text-indigo-400" />
                <span>Язык обучения и объяснений</span>
              </div>

              <p className="text-xs text-slate-300">
                AI-тьютор будет строго придерживаться выбранного языка при генерации уроков, вопросов и пояснений:
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                {/* Russian */}
                <button
                  type="button"
                  onClick={() => onLanguageChange('ru')}
                  className={`p-4 rounded-2xl border text-left transition-all flex flex-col justify-between gap-2 relative ${
                    currentLanguage === 'ru'
                      ? 'bg-indigo-950/80 border-indigo-500 ring-2 ring-indigo-500/40 shadow-lg shadow-indigo-600/20'
                      : 'bg-surface-950/60 border-slate-800 hover:border-slate-700 hover:bg-surface-950'
                  }`}
                >
                  <div className="flex items-center justify-between w-full">
                    <div className="flex items-center gap-2">
                      <span className="text-xl">🇷🇺</span>
                      <span className="text-sm font-bold text-white">Русский</span>
                    </div>
                    {currentLanguage === 'ru' && (
                      <span className="w-5 h-5 rounded-full bg-indigo-600 flex items-center justify-center text-white">
                        <Check className="w-3 h-3 stroke-[3]" />
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-400 leading-snug">
                    Все уроки, тесты и диалоги строго на русском языке.
                  </p>
                </button>

                {/* English */}
                <button
                  type="button"
                  onClick={() => onLanguageChange('en')}
                  className={`p-4 rounded-2xl border text-left transition-all flex flex-col justify-between gap-2 relative ${
                    currentLanguage === 'en'
                      ? 'bg-indigo-950/80 border-indigo-500 ring-2 ring-indigo-500/40 shadow-lg shadow-indigo-600/20'
                      : 'bg-surface-950/60 border-slate-800 hover:border-slate-700 hover:bg-surface-950'
                  }`}
                >
                  <div className="flex items-center justify-between w-full">
                    <div className="flex items-center gap-2">
                      <span className="text-xl">🇬🇧</span>
                      <span className="text-sm font-bold text-white">English</span>
                    </div>
                    {currentLanguage === 'en' && (
                      <span className="w-5 h-5 rounded-full bg-indigo-600 flex items-center justify-center text-white">
                        <Check className="w-3 h-3 stroke-[3]" />
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-400 leading-snug">
                    All lessons, quizzes, and tutor replies strictly in English.
                  </p>
                </button>
              </div>
            </div>
          )}

          {activeTab === 'costs' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white">Статистика расходов и токенов (ProxyAPI)</h3>
                  <p className="text-[11px] text-slate-400">
                    Учет расходов по официальным тарифам в реальном времени. Все утечки устранены.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={fetchCosts}
                  disabled={loadingCosts}
                  className="px-3 py-1.5 rounded-xl bg-surface-950 border border-slate-800 text-xs text-slate-300 hover:text-white flex items-center gap-1.5 transition-colors cursor-pointer"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${loadingCosts ? 'animate-spin' : ''}`} />
                  <span>Обновить</span>
                </button>
              </div>

              {loadingCosts && !costsData && (
                <div className="p-8 text-center text-slate-400 flex items-center justify-center gap-2">
                  <Loader2 className="w-5 h-5 animate-spin text-indigo-400" />
                  <span>Загрузка финансовой сводки...</span>
                </div>
              )}

              {costsData && (
                <div className="space-y-5">
                  {/* Top Stats Cards */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="p-3.5 rounded-2xl bg-surface-950 border border-slate-800 space-y-1">
                      <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Сегодня расход</div>
                      <div className="text-lg font-black text-emerald-400">
                        {(costsData.today_spent_rub ?? costsData.total_cost_rub ?? 0).toFixed(2)} ₽
                      </div>
                    </div>
                    <div className="p-3.5 rounded-2xl bg-surface-950 border border-slate-800 space-y-1">
                      <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Всего токенов</div>
                      <div className="text-lg font-black text-sky-400">
                        {(costsData.today_tokens ?? costsData.total_tokens ?? 0).toLocaleString()}
                      </div>
                    </div>
                    <div className="p-3.5 rounded-2xl bg-surface-950 border border-slate-800 space-y-1">
                      <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Всего вызовов LLM</div>
                      <div className="text-lg font-black text-indigo-400">
                        {costsData.today_calls ?? costsData.calls_count ?? 0}
                      </div>
                    </div>
                    <div className="p-3.5 rounded-2xl bg-surface-950 border border-slate-800 space-y-1">
                      <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Статус учета</div>
                      <div className="text-xs font-semibold text-emerald-400 flex items-center gap-1.5 pt-1">
                        <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                        <span>ProxyAPI Активен</span>
                      </div>
                    </div>
                  </div>

                  {/* Model Distribution */}
                  {(costsData.breakdown_by_model || costsData.by_model) && Object.keys(costsData.breakdown_by_model || costsData.by_model).length > 0 && (
                    <div className="p-4 rounded-2xl bg-surface-950 border border-slate-800 space-y-3">
                      <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                        Распределение по моделям
                      </h4>
                      <div className="space-y-2">
                        {Object.entries(costsData.breakdown_by_model || costsData.by_model).map(([modelName, info]: [string, any]) => (
                          <div key={modelName} className="flex items-center justify-between text-xs py-1 border-b border-slate-800/50 last:border-none">
                            <span className="font-semibold text-white">{modelName}</span>
                            <div className="flex items-center gap-4 text-slate-400">
                              <span>{info.calls} вызовов</span>
                              <span>{info.tokens?.toLocaleString()} ток.</span>
                              <span className="font-bold text-emerald-400">{info.cost_rub?.toFixed(2)} ₽</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Task Type Breakdown */}
                  {costsData.breakdown_by_task && Object.keys(costsData.breakdown_by_task).length > 0 && (
                    <div className="p-4 rounded-2xl bg-surface-950 border border-slate-800 space-y-3">
                      <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                        Распределение по задачам (Архитектура)
                      </h4>
                      <div className="space-y-2">
                        {Object.entries(costsData.breakdown_by_task).map(([taskName, info]: [string, any]) => (
                          <div key={taskName} className="flex items-center justify-between text-xs py-1 border-b border-slate-800/50 last:border-none">
                            <span className="font-mono text-[11px] text-indigo-300">{taskName}</span>
                            <div className="flex items-center gap-4 text-slate-400 text-xs">
                              <span>{info.calls} вызовов</span>
                              <span>{info.tokens?.toLocaleString()} ток.</span>
                              <span className="font-bold text-slate-200">{info.cost_rub?.toFixed(2)} ₽</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Recent Calls Ledger */}
                  {costsData.recent_calls && costsData.recent_calls.length > 0 && (
                    <div className="space-y-2">
                      <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                        Последние вызовы LLM
                      </h4>
                      <div className="max-h-56 overflow-y-auto space-y-1.5 pr-1">
                        {costsData.recent_calls.map((call: any, idx: number) => (
                          <div
                            key={idx}
                            className="p-2.5 rounded-xl bg-surface-950/70 border border-slate-800/80 flex items-center justify-between text-[11px]"
                          >
                            <div className="flex items-center gap-2">
                              <span className={`w-2 h-2 rounded-full ${call.status === 'success' ? 'bg-emerald-400' : 'bg-rose-500'}`} />
                              <span className="font-bold text-white">{call.model}</span>
                              <span className="text-slate-500">[{call.task_type}]</span>
                            </div>
                            <div className="flex items-center gap-3 text-slate-400">
                              <span>{call.total_tokens?.toLocaleString()} ток.</span>
                              <span>{call.latency_ms ? `${(call.latency_ms / 1000).toFixed(1)}s` : ''}</span>
                              <span className="font-bold text-emerald-400">{call.cost_rub?.toFixed(3)} ₽</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 bg-surface-950 border-t border-slate-800/80 flex justify-end shrink-0">
          <button
            onClick={onClose}
            className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold rounded-xl shadow-lg shadow-indigo-600/30 transition-all"
          >
            Готово / Done
          </button>
        </div>
      </div>
    </div>
  );
};
