import React, { useState, useEffect, useCallback } from 'react';
import { Navigation, TabType } from './components/common/Navigation';
import { FeedScreen } from './components/feed/FeedScreen';
import { DeepTutorScreen } from './components/deep/DeepTutorScreen';
import { TracksScreen } from './components/tracks/TracksScreen';
import { SettingsModal, AVAILABLE_AI_MODELS } from './components/common/SettingsModal';
import { apiClient } from './api/client';
import { Cpu, Settings } from 'lucide-react';

interface RouteInfo {
  tab: TabType;
  trackId?: string | null;
  conceptId?: string | null;
}

function parseCurrentRoute(): RouteInfo {
  const path = window.location.pathname.replace(/^\/+|\/+$/g, '');
  const segments = path.split('/');

  if (!segments[0] || segments[0] === 'feed') {
    return { tab: 'feed' };
  }

  if (segments[0] === 'tracks') {
    const trackId = segments[1] ? decodeURIComponent(segments[1]) : (localStorage.getItem('got_it_active_track_id') || null);
    return { tab: 'tracks', trackId };
  }

  if (segments[0] === 'deep' || segments[0] === 'learn') {
    const conceptId = segments[1] ? decodeURIComponent(segments[1]) : (localStorage.getItem('got_it_deep_concept_id') || null);
    return { tab: 'deep', conceptId };
  }

  // Fallback to localStorage
  const savedTab = (localStorage.getItem('got_it_active_tab') as TabType) || 'feed';
  const savedTrackId = localStorage.getItem('got_it_active_track_id');
  const savedConceptId = localStorage.getItem('got_it_deep_concept_id');

  return {
    tab: savedTab,
    trackId: savedTrackId,
    conceptId: savedConceptId,
  };
}

function computePath(tab: TabType, trackId?: string | null, conceptId?: string | null): string {
  if (tab === 'feed') return '/feed';
  if (tab === 'tracks') return trackId ? `/tracks/${encodeURIComponent(trackId)}` : '/tracks';
  if (tab === 'deep') return conceptId ? `/deep/${encodeURIComponent(conceptId)}` : '/deep';
  return '/feed';
}

export const App: React.FC = () => {
  const initialRoute = parseCurrentRoute();

  const [activeTab, setActiveTab] = useState<TabType>(initialRoute.tab);
  const [userId, setUserId] = useState<string>('demo_user');
  const [deepTargetConceptId, setDeepTargetConceptId] = useState<string | undefined>(
    initialRoute.conceptId || undefined
  );
  const [activeTrackId, setActiveTrackId] = useState<string | null>(initialRoute.trackId || null);
  const [activeConceptId, setActiveConceptId] = useState<string | null>(initialRoute.conceptId || null);

  const [language, setLanguage] = useState<'ru' | 'en'>(() => {
    const saved = localStorage.getItem('got_it_language');
    return saved === 'en' ? 'en' : 'ru';
  });

  const [model, setModel] = useState<string>(() => {
    const saved = localStorage.getItem('got_it_model');
    return saved || 'kimi-k3';
  });

  const [ttsVoice, setTtsVoice] = useState<string>(() => {
    const saved = localStorage.getItem('got_it_tts_voice');
    return saved || 'ru-RU-SvetlanaNeural';
  });

  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);

  // Sync state and push/replace URL
  const navigate = useCallback(
    (
      tab: TabType,
      trackId?: string | null,
      conceptId?: string | null,
      replace: boolean = false
    ) => {
      setActiveTab(tab);
      localStorage.setItem('got_it_active_tab', tab);

      if (trackId !== undefined) {
        setActiveTrackId(trackId);
        if (trackId) {
          localStorage.setItem('got_it_active_track_id', trackId);
        } else {
          localStorage.removeItem('got_it_active_track_id');
        }
      }

      if (conceptId !== undefined) {
        setDeepTargetConceptId(conceptId || undefined);
        setActiveConceptId(conceptId);
        if (conceptId) {
          localStorage.setItem('got_it_deep_concept_id', conceptId);
        } else {
          localStorage.removeItem('got_it_deep_concept_id');
        }
      }

      const effectiveTrack = trackId !== undefined ? trackId : activeTrackId;
      const effectiveConcept =
        conceptId !== undefined ? conceptId : (deepTargetConceptId || activeConceptId);
      const newPath = computePath(tab, effectiveTrack, effectiveConcept);

      if (window.location.pathname !== newPath) {
        if (replace) {
          window.history.replaceState(null, '', newPath);
        } else {
          window.history.pushState(null, '', newPath);
        }
      }
    },
    [activeTrackId, deepTargetConceptId, activeConceptId]
  );

  // Browser History back/forward navigation support
  useEffect(() => {
    const handlePopState = () => {
      const route = parseCurrentRoute();
      setActiveTab(route.tab);
      if (route.trackId !== undefined) setActiveTrackId(route.trackId || null);
      if (route.conceptId !== undefined) {
        setDeepTargetConceptId(route.conceptId || undefined);
        setActiveConceptId(route.conceptId || null);
      }
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  // Initial load: synchronize URL path with current state
  useEffect(() => {
    const targetPath = computePath(activeTab, activeTrackId, deepTargetConceptId);
    if (window.location.pathname !== targetPath && window.location.pathname === '/') {
      window.history.replaceState(null, '', targetPath);
    }
  }, []);

  useEffect(() => {
    apiClient
      .getActiveUser()
      .then((user) => {
        setUserId(user.user_id);
        if (
          user.preferred_language &&
          (user.preferred_language === 'ru' || user.preferred_language === 'en')
        ) {
          setLanguage(user.preferred_language);
          localStorage.setItem('got_it_language', user.preferred_language);
        }
        if (user.preferred_model) {
          setModel(user.preferred_model);
          localStorage.setItem('got_it_model', user.preferred_model);
        }
      })
      .catch((err) => console.warn('Could not auto-fetch active user:', err));
  }, []);

  const handleTabChange = (tab: TabType) => {
    navigate(tab, undefined, undefined, false);
  };

  const handleLanguageChange = (newLang: 'ru' | 'en') => {
    setLanguage(newLang);
    localStorage.setItem('got_it_language', newLang);
    if (userId) {
      apiClient.updateUserSettings(userId, { preferred_language: newLang }).catch(console.error);
    }
  };

  const handleModelChange = (newModel: string) => {
    setModel(newModel);
    localStorage.setItem('got_it_model', newModel);
    if (userId) {
      apiClient.updateUserSettings(userId, { preferred_model: newModel }).catch(console.error);
    }
  };

  const handleTtsVoiceChange = (newVoice: string) => {
    setTtsVoice(newVoice);
    localStorage.setItem('got_it_tts_voice', newVoice);
  };

  const handleSelectConceptForDeep = (conceptId: string, trackId?: string) => {
    navigate('deep', trackId || activeTrackId, conceptId, false);
  };

  const handleTrackSelected = (trackId: string) => {
    navigate('tracks', trackId, undefined, true);
  };

  const handleActiveConceptChange = (conceptId: string, trackId?: string) => {
    if (conceptId) {
      setActiveConceptId(conceptId);
      setDeepTargetConceptId(conceptId);
      localStorage.setItem('got_it_deep_concept_id', conceptId);
      if (activeTab === 'deep') {
        const newPath = `/deep/${encodeURIComponent(conceptId)}`;
        if (window.location.pathname !== newPath) {
          window.history.replaceState(null, '', newPath);
        }
      }
    }
    if (trackId) {
      setActiveTrackId(trackId);
      localStorage.setItem('got_it_active_track_id', trackId);
    }
  };

  const activeModelMeta = AVAILABLE_AI_MODELS.find(
    (m) => m.id.toLowerCase() === model.toLowerCase()
  );
  const activeModelDisplayName = activeModelMeta ? activeModelMeta.name : model;

  return (
    <div className="min-h-screen bg-surface-950 text-slate-100 flex flex-col selection:bg-indigo-500 selection:text-white">
      {/* Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        currentLanguage={language}
        onLanguageChange={handleLanguageChange}
        currentModel={model}
        onModelChange={handleModelChange}
        currentTtsVoice={ttsVoice}
        onTtsVoiceChange={handleTtsVoiceChange}
      />

      {/* Top Header with Desktop Navigation */}
      <header className="sticky top-0 z-40 bg-surface-950 border-b border-slate-800 px-4 sm:px-6 lg:px-8 py-3.5 shadow-xl shadow-surface-950/80">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          {/* Logo & Brand (Clicking logo returns to default view) */}
          <div
            onClick={() => handleTabChange('feed')}
            className="flex items-center gap-2.5 cursor-pointer group"
          >
            <div className="w-9 h-9 flex items-center justify-center p-0.5 group-hover:scale-105 transition-transform">
              <img src="/logo.png" alt="GotThat? Logo" className="w-full h-full object-contain drop-shadow-[0_0_8px_rgba(56,189,248,0.4)]" />
            </div>
            <span className="font-black text-xl text-white tracking-tight group-hover:text-slate-100 transition-colors flex items-center">
              GotThat
              <span className="inline-block italic font-black text-cyan-400 ml-0.5 transform rotate-12 group-hover:rotate-[18deg] group-hover:scale-110 transition-all duration-300 drop-shadow-[0_0_10px_rgba(34,211,238,0.6)]">
                ?
              </span>
            </span>
          </div>

          {/* Desktop Navigation Tabs */}
          <div className="hidden md:block">
            <Navigation activeTab={activeTab} onTabChange={handleTabChange} isDesktop />
          </div>

          {/* Right Action & Status Area */}
          <div className="flex items-center gap-2.5">
            {/* Model Badge Button (Click to open settings) */}
            <button
              onClick={() => setIsSettingsOpen(true)}
              title="Выбрать AI модель и тариф"
              className="hidden sm:flex items-center gap-2 bg-surface-900 hover:bg-surface-800 border border-slate-800 hover:border-slate-700 px-3.5 py-1.5 rounded-full text-xs font-semibold text-slate-300 hover:text-white transition-all shadow-inner"
            >
              <Cpu className="w-3.5 h-3.5 text-indigo-400" />
              <span>{activeModelDisplayName}</span>
            </button>

            {/* Settings Button */}
            <button
              onClick={() => setIsSettingsOpen(true)}
              title="Настройки / Settings"
              className="p-2 rounded-full bg-surface-900 hover:bg-surface-800 border border-slate-800 hover:border-slate-700 text-slate-300 hover:text-white transition-all shadow-inner flex items-center justify-center"
            >
              <Settings className="w-4 h-4 text-indigo-400" />
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area - Persistent Tabs (Keeps State in Memory) */}
      <main className="flex-1 flex flex-col w-full">
        <div className={activeTab === 'feed' ? 'flex-1 flex flex-col w-full' : 'hidden'}>
          <FeedScreen userId={userId} />
        </div>

        <div className={activeTab === 'deep' ? 'flex-1 flex flex-col w-full' : 'hidden'}>
          <DeepTutorScreen
            userId={userId}
            targetConceptId={deepTargetConceptId}
            isActive={activeTab === 'deep'}
            language={language}
            currentModel={model}
            ttsVoice={ttsVoice}
            onActiveConceptChange={handleActiveConceptChange}
            onNavigateToFeed={() => handleTabChange('feed')}
            onNavigateToMap={() => handleTabChange('tracks')}
          />
        </div>

        <div className={activeTab === 'tracks' ? 'flex-1 flex flex-col w-full' : 'hidden'}>
          <TracksScreen
            userId={userId}
            activeTrackId={activeTrackId}
            activeConceptId={activeConceptId}
            onTrackSelected={handleTrackSelected}
            onSelectTrackForDeepStudy={handleSelectConceptForDeep}
          />
        </div>
      </main>

      {/* Mobile Bottom Tab Navigation */}
      <Navigation activeTab={activeTab} onTabChange={handleTabChange} />
    </div>
  );
};

export default App;
