import React from 'react';
import { Flame, Compass, BookOpen } from 'lucide-react';

export type TabType = 'feed' | 'deep' | 'tracks';

interface NavigationProps {
  activeTab: TabType;
  onTabChange: (tab: TabType) => void;
  className?: string;
  isDesktop?: boolean;
}

export const Navigation: React.FC<NavigationProps> = React.memo(({ activeTab, onTabChange, className = '', isDesktop = false }) => {
  const tabs = [
    { id: 'feed' as TabType, label: 'Quick Feed', icon: Flame },
    { id: 'deep' as TabType, label: 'Deep Tutor', icon: BookOpen },
    { id: 'tracks' as TabType, label: 'Knowledge Map', icon: Compass },
  ];

  if (isDesktop) {
    return (
      <div className={`flex items-center gap-1.5 bg-surface-900 border border-slate-800 p-1.5 rounded-2xl shadow-inner ${className}`}>
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all duration-200 ${
                isActive
                  ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30 ring-1 ring-indigo-400/50'
                  : 'text-slate-400 hover:text-slate-100 hover:bg-surface-800'
              }`}
            >
              <Icon className={`w-4 h-4 ${isActive ? 'fill-white/20' : ''}`} />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>
    );
  }

  // Mobile Bottom Navigation Bar
  return (
    <nav className={`md:hidden fixed bottom-0 left-0 right-0 z-50 bg-surface-950 border-t border-slate-800 px-4 py-2 flex justify-around items-center ${className}`}>
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={`flex flex-col items-center gap-1 py-1 px-4 rounded-xl transition-all duration-200 ${
              isActive
                ? 'text-indigo-400 font-bold scale-105'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Icon className={`w-5 h-5 ${isActive ? 'fill-indigo-500/20 text-indigo-400' : ''}`} />
            <span className="text-[10px] tracking-wide">{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );
});
