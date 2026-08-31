import React, { useState, useEffect } from 'react';
import { TrackFolder } from '../../types';
import { apiClient } from '../../api/client';
import {
  X,
  Folder,
  Book,
  Code,
  Calculator,
  Atom,
  Brain,
  Compass,
  Sparkles,
  Terminal,
  Layers,
  Pin,
  Loader2,
  Check,
} from 'lucide-react';

interface FolderModalProps {
  isOpen: boolean;
  folderToEdit?: TrackFolder | null;
  onClose: () => void;
  onSaved: (folder: TrackFolder) => void;
}

export const FOLDER_COLOR_PRESETS = [
  { label: 'Indigo', value: '#6366f1', bgClass: 'bg-indigo-500', textClass: 'text-indigo-400' },
  { label: 'Cyan', value: '#06b6d4', bgClass: 'bg-cyan-500', textClass: 'text-cyan-400' },
  { label: 'Emerald', value: '#10b981', bgClass: 'bg-emerald-500', textClass: 'text-emerald-400' },
  { label: 'Amber', value: '#f59e0b', bgClass: 'bg-amber-500', textClass: 'text-amber-400' },
  { label: 'Rose', value: '#f43f5e', bgClass: 'bg-rose-500', textClass: 'text-rose-400' },
  { label: 'Purple', value: '#a855f7', bgClass: 'bg-purple-500', textClass: 'text-purple-400' },
  { label: 'Blue', value: '#3b82f6', bgClass: 'bg-blue-500', textClass: 'text-blue-400' },
  { label: 'Pink', value: '#ec4899', bgClass: 'bg-pink-500', textClass: 'text-pink-400' },
];

export const FOLDER_ICONS: { [key: string]: React.ElementType } = {
  folder: Folder,
  book: Book,
  code: Code,
  calculator: Calculator,
  atom: Atom,
  brain: Brain,
  compass: Compass,
  sparkles: Sparkles,
  terminal: Terminal,
  layers: Layers,
};

export const FolderModal: React.FC<FolderModalProps> = ({
  isOpen,
  folderToEdit,
  onClose,
  onSaved,
}) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [color, setColor] = useState('#6366f1');
  const [icon, setIcon] = useState('folder');
  const [isPinned, setIsPinned] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (folderToEdit) {
      setName(folderToEdit.name);
      setDescription(folderToEdit.description || '');
      setColor(folderToEdit.color || '#6366f1');
      setIcon(folderToEdit.icon || 'folder');
      setIsPinned(folderToEdit.is_pinned);
    } else {
      setName('');
      setDescription('');
      setColor('#6366f1');
      setIcon('folder');
      setIsPinned(false);
    }
    setError(null);
  }, [folderToEdit, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Пожалуйста, введите название папки');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      if (folderToEdit) {
        const updated = await apiClient.updateFolder(folderToEdit.id, {
          name: name.trim(),
          description: description.trim() || undefined,
          color,
          icon,
          is_pinned: isPinned,
        });
        onSaved(updated);
      } else {
        const created = await apiClient.createFolder({
          name: name.trim(),
          description: description.trim() || undefined,
          color,
          icon,
          is_pinned: isPinned,
        });
        onSaved(created);
      }
      onClose();
    } catch (err: any) {
      console.error('Failed to save folder:', err);
      setError(err.message || 'Ошибка сохранения папки');
    } finally {
      setIsSubmitting(false);
    }
  };

  const SelectedIconComponent = FOLDER_ICONS[icon] || Folder;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 animate-fade-in">
      <div
        className="bg-surface-900 border border-slate-800 rounded-3xl w-full max-w-md shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-6 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className="w-10 h-10 rounded-2xl flex items-center justify-center shadow-lg transition-colors"
              style={{ backgroundColor: `${color}25`, color }}
            >
              <SelectedIconComponent className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white">
                {folderToEdit ? 'Редактировать папку' : 'Создать папку курсов'}
              </h2>
              <p className="text-xs text-slate-400">
                Группируйте предметы по темам для быстрого доступа
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-2 rounded-xl hover:bg-surface-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          {error && (
            <div className="p-3 rounded-xl bg-rose-950/60 border border-rose-800/60 text-xs text-rose-300">
              {error}
            </div>
          )}

          {/* Folder Name */}
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5">
              Название папки <span className="text-rose-400">*</span>
            </label>
            <input
              type="text"
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="например, Математика и алгоритмы"
              className="w-full bg-surface-950 border border-slate-800 rounded-2xl px-4 py-3 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
            />
          </div>

          {/* Description (Optional) */}
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5">
              Описание (необязательно)
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Краткое описание или заметка"
              className="w-full bg-surface-950 border border-slate-800 rounded-2xl px-4 py-2.5 text-xs text-white placeholder:text-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
            />
          </div>

          {/* Color Picker */}
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-2">
              Цвет папки
            </label>
            <div className="flex flex-wrap gap-2.5">
              {FOLDER_COLOR_PRESETS.map((preset) => {
                const isSelected = color === preset.value;
                return (
                  <button
                    type="button"
                    key={preset.value}
                    onClick={() => setColor(preset.value)}
                    className={`w-7 h-7 rounded-xl flex items-center justify-center transition-all ${preset.bgClass} ${
                      isSelected ? 'ring-2 ring-white scale-110 shadow-lg' : 'opacity-70 hover:opacity-100'
                    }`}
                    title={preset.label}
                  >
                    {isSelected && <Check className="w-4 h-4 text-white" />}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Icon Picker */}
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-2">
              Иконка
            </label>
            <div className="grid grid-cols-5 gap-2">
              {Object.entries(FOLDER_ICONS).map(([key, IconComp]) => {
                const isSelected = icon === key;
                return (
                  <button
                    type="button"
                    key={key}
                    onClick={() => setIcon(key)}
                    className={`p-2.5 rounded-xl border flex items-center justify-center transition-all ${
                      isSelected
                        ? 'bg-surface-800 border-indigo-500 text-white shadow-md'
                        : 'bg-surface-950 border-slate-800 text-slate-400 hover:text-slate-200 hover:border-slate-700'
                    }`}
                  >
                    <IconComp className="w-4 h-4" />
                  </button>
                );
              })}
            </div>
          </div>

          {/* Pin Folder Toggle */}
          <div className="pt-1">
            <label className="flex items-center gap-3 p-3 rounded-2xl bg-surface-950 border border-slate-800/80 cursor-pointer hover:border-slate-700 transition-colors">
              <input
                type="checkbox"
                checked={isPinned}
                onChange={(e) => setIsPinned(e.target.checked)}
                className="hidden"
              />
              <div
                className={`w-8 h-8 rounded-xl flex items-center justify-center transition-all ${
                  isPinned
                    ? 'bg-amber-500/20 text-amber-300 border border-amber-500/50'
                    : 'bg-surface-900 text-slate-500 border border-slate-800'
                }`}
              >
                <Pin className={`w-4 h-4 ${isPinned ? 'fill-amber-400' : ''}`} />
              </div>
              <div className="flex-1">
                <span className="text-xs font-bold text-white block">Закрепить папку (Pin)</span>
                <span className="text-[11px] text-slate-400 block">
                  Папка будет всегда отображаться наверху списка
                </span>
              </div>
            </label>
          </div>

          {/* Actions */}
          <div className="pt-3 flex items-center justify-end gap-2.5 border-t border-slate-800/80">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2.5 rounded-xl text-xs font-bold text-slate-400 hover:text-white hover:bg-surface-800 transition-colors"
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={isSubmitting || !name.trim()}
              className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl text-xs font-bold shadow-lg shadow-indigo-600/30 flex items-center gap-2 transition-all cursor-pointer"
            >
              {isSubmitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              <span>{folderToEdit ? 'Сохранить изменения' : 'Создать папку'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
