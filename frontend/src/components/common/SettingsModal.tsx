import React, { useState } from 'react';
import { X, Globe, Cpu, Sparkles, Check, DollarSign, Layers, Volume2 } from 'lucide-react';

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
  // 🔮 Google Gemini
  {
    id: 'gemini-3.1-pro',
    name: 'Gemini 3.1 Pro Preview',
    provider: 'Google Gemini',
    providerIcon: '🔮',
    price: '170,26 ₽ / 1 021,55 ₽',
    description: 'Глубокое рассуждение и академический синтез сложных тем',
  },
  {
    id: 'gemini-3-flash',
    name: 'Gemini 3 Flash Preview',
    provider: 'Google Gemini',
    providerIcon: '🔮',
    price: '42,56 ₽ / 255,39 ₽',
    description: 'Быстрый инференс и оперативная проверка ответов',
  },

  // 🧠 Anthropic
  {
    id: 'claude-opus-4.6',
    name: 'Claude Opus 4.6',
    provider: 'Anthropic',
    providerIcon: '🧠',
    price: '425,65 ₽ / 2 128,23 ₽',
    description: 'Максимальная глубина аналитического разбора',
  },
  {
    id: 'claude-opus-5',
    name: 'Claude Opus 5',
    provider: 'Anthropic',
    providerIcon: '🧠',
    price: '425,65 ₽ / 2 128,23 ₽',
    description: 'Флагманский интеллект для сложнейших технических доменов',
  },
  {
    id: 'claude-sonnet-5',
    name: 'Claude Sonnet 5',
    provider: 'Anthropic',
    providerIcon: '🧠',
    price: '170,26 ₽ / 851,29 ₽',
    description: 'Баланс педагогики Фейнмана, скорости и строгости',
  },

  // 🟩 OpenAI
  {
    id: 'gpt-5.4',
    name: 'GPT‑5.4',
    provider: 'OpenAI',
    providerIcon: '🟩',
    price: '212,82 ₽ / 1 276,94 ₽',
    description: 'Универсальный интеллект для широкого спектра дисциплин',
  },
  {
    id: 'gpt-5.6-sol',
    name: 'GPT‑5.6 Sol',
    provider: 'OpenAI',
    providerIcon: '🟩',
    price: '425,65 ₽ / 2 553,88 ₽',
    description: 'Научное рассуждение с высокой точностью формул',
  },

  // 🟥 Qwen
  {
    id: 'qwen3.7-max',
    name: 'Qwen3.7 Max',
    provider: 'Qwen',
    providerIcon: '🟥',
    price: '102,16 ₽ / 510,78 ₽',
    description: 'Мощная модель для программирования и математики',
  },

  // 🌙 Moonshot AI
  {
    id: 'kimi-k3',
    name: 'Kimi K3',
    provider: 'Moonshot AI',
    providerIcon: '🌙',
    price: '255,39 ₽ / 1 276,94 ₽',
    description: 'Основная модель курса: длинный контекст, строгая логика и DAG-планирование',
    badge: 'Рекомендуется',
  },

  // 🟦 Z.ai (GLM)
  {
    id: 'glm-5.2',
    name: 'GLM 5.2',
    provider: 'Z.ai (GLM)',
    providerIcon: '🟦',
    price: '119,18 ₽ / 374,57 ₽',
    description: 'Высокая эффективность при генерации структурированных концептов',
  },

  // ⚡ DeepSeek
  {
    id: 'deepseek-v4-pro',
    name: 'DeepSeek V4 Pro',
    provider: 'DeepSeek',
    providerIcon: '⚡',
    price: '37,03 ₽ / 74,06 ₽',
    description: 'Выдающаяся экономичность и отличное понимание алгоритмов',
  },
  {
    id: 'deepseek-v4-flash',
    name: 'DeepSeek V4 Flash 0423 / 0731',
    provider: 'DeepSeek',
    providerIcon: '⚡',
    price: '11,92 ₽ / 23,84 ₽',
    description: 'Сверхбыстрый инференс для оперативных подсказок',
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
  const [activeTab, setActiveTab] = useState<'models' | 'language' | 'voice'>('models');

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
