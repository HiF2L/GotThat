import React, { useEffect, useState, useMemo } from 'react';
import { TrackSummary, TrackFolder, UserMasteryOverview } from '../../types';
import { apiClient } from '../../api/client';
import { CreateTrackModal } from '../common/CreateTrackModal';
import { ExpandTrackModal } from '../common/ExpandTrackModal';
import { FolderModal, FOLDER_ICONS } from './FolderModal';
import {
  CheckCircle,
  Sparkles,
  Loader2,
  Play,
  Plus,
  Compass,
  ArrowRight,
  Activity,
  Trash2,
  BookOpen,
  Layers,
  MessageSquare,
  Folder,
  FolderPlus,
  Pin,
  Search,
  X,
  ChevronDown,
  ChevronRight,
  MoreVertical,
  FolderInput,
  Edit2,
} from 'lucide-react';

interface TracksScreenProps {
  userId: string;
  activeTrackId?: string | null;
  activeConceptId?: string | null;
  onSelectTrackForDeepStudy: (conceptId: string, trackId?: string, skipProbing?: boolean) => void;
  onTrackSelected?: (trackId: string) => void;
}

export const TracksScreen: React.FC<TracksScreenProps> = ({
  userId,
  activeTrackId,
  activeConceptId,
  onSelectTrackForDeepStudy,
  onTrackSelected,
}) => {
  const [tracks, setTracks] = useState<TrackSummary[]>([]);
  const [folders, setFolders] = useState<TrackFolder[]>([]);
  const [selectedTrackId, setSelectedTrackId] = useState<string | null>(null);
  const [masteryOverview, setMasteryOverview] = useState<UserMasteryOverview | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);

  // Modals state
  const [isCreateModalOpen, setIsCreateModalOpen] = useState<boolean>(false);
  const [isExpandModalOpen, setIsExpandModalOpen] = useState<boolean>(false);
  const [isFolderModalOpen, setIsFolderModalOpen] = useState<boolean>(false);
  const [folderToEdit, setFolderToEdit] = useState<TrackFolder | null>(null);

  // UI state: Search, Filter, Collapsed folders, Open menus
  const [assignTrackIdOnFolderCreate, setAssignTrackIdOnFolderCreate] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [activeFilter, setActiveFilter] = useState<'all' | 'pinned' | string>('all');
  const [collapsedFolderIds, setCollapsedFolderIds] = useState<Set<string>>(() => {
    try {
      const saved = localStorage.getItem('got_it_collapsed_folders');
      return saved ? new Set(JSON.parse(saved)) : new Set();
    } catch {
      return new Set();
    }
  });
  const [openFolderMenuId, setOpenFolderMenuId] = useState<string | null>(null);
  const [openTrackMoveMenuId, setOpenTrackMoveMenuId] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const [trackList, folderList] = await Promise.all([
        apiClient.listTracks(),
        apiClient.listFolders(),
      ]);
      setTracks(trackList);
      setFolders(folderList);

      if (trackList.length > 0) {
        // Prioritize actively studied track from Deep Tutor or URL or current selection
        let targetTrack = trackList[0];
        if (activeTrackId) {
          const match = trackList.find((t) => t.track_id === activeTrackId || t.slug === activeTrackId);
          if (match) targetTrack = match;
        } else if (selectedTrackId) {
          const match = trackList.find((t) => t.track_id === selectedTrackId || t.slug === selectedTrackId);
          if (match) targetTrack = match;
        }
        setSelectedTrackId(targetTrack.track_id);
        try {
          const overview = await apiClient.getTrackMastery(targetTrack.slug || targetTrack.track_id, userId);
          setMasteryOverview(overview);
        } catch (err) {
          console.warn('Failed to load track mastery, using resilient fallback:', err);
          setMasteryOverview({
            user_id: userId,
            track_id: targetTrack.track_id,
            track_title: targetTrack.title,
            track_slug: targetTrack.slug,
            track_description: targetTrack.description,
            track_user_wishes: targetTrack.user_wishes,
            track_depth_level: targetTrack.depth_level,
            total_concepts: targetTrack.total_concepts || targetTrack.concepts?.length || 0,
            mastered_concepts: 0,
            in_progress_concepts: 0,
            concepts: (targetTrack.concepts || []).map((c: any) => ({
              concept_id: c.id,
              concept_code: c.code || '',
              title: c.title,
              slug: c.slug,
              mastery_prob: 0,
              uncertainty: 1.0,
              retrievability: 1.0,
              stability: 1.0,
              is_mastered: false,
              is_due_for_review: false,
            })),
          });
        }
      } else {
        setSelectedTrackId(null);
        setMasteryOverview(null);
      }
    } catch (err) {
      console.error('Failed to load knowledge map data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [userId]);

  // Sync when activeTrackId changes from Deep Tutor or URL
  useEffect(() => {
    if (activeTrackId && tracks.length > 0) {
      const match = tracks.find((t) => t.track_id === activeTrackId || t.slug === activeTrackId);
      if (match && match.track_id !== selectedTrackId) {
        handleSelectTrack(match.slug || match.track_id, false);
      }
    }
  }, [activeTrackId, tracks]);

  // Close menus on click outside
  useEffect(() => {
    const handleWindowClick = () => {
      setOpenFolderMenuId(null);
      setOpenTrackMoveMenuId(null);
    };
    window.addEventListener('click', handleWindowClick);
    return () => window.removeEventListener('click', handleWindowClick);
  }, []);

  const handleSelectTrack = async (trackIdOrSlug: string, triggerCallback: boolean = true) => {
    const targetTrack = tracks.find((t) => t.track_id === trackIdOrSlug || t.slug === trackIdOrSlug);
    const effectiveId = targetTrack?.track_id || trackIdOrSlug;
    const effectiveSlug = targetTrack?.slug || trackIdOrSlug;
    setSelectedTrackId(effectiveId);

    if (triggerCallback && onTrackSelected) {
      onTrackSelected(effectiveSlug);
    }
    try {
      const overview = await apiClient.getTrackMastery(effectiveSlug, userId);
      setMasteryOverview(overview);
    } catch (err) {
      console.warn('Failed to load track mastery on select, using fallback:', err);
      if (targetTrack) {
        setMasteryOverview({
          user_id: userId,
          track_id: targetTrack.track_id,
          track_title: targetTrack.title,
          track_slug: targetTrack.slug,
          track_description: targetTrack.description,
          track_user_wishes: targetTrack.user_wishes,
          track_depth_level: targetTrack.depth_level,
          total_concepts: targetTrack.total_concepts || targetTrack.concepts?.length || 0,
          mastered_concepts: 0,
          in_progress_concepts: 0,
          concepts: (targetTrack.concepts || []).map((c: any) => ({
            concept_id: c.id,
            concept_code: c.code || '',
            title: c.title,
            slug: c.slug,
            mastery_prob: 0,
            uncertainty: 1.0,
            retrievability: 1.0,
            stability: 1.0,
            is_mastered: false,
            is_due_for_review: false,
          })),
        });
      }
    }
  };

  const handleTrackCreated = async (newTrack: TrackSummary, startMode: 'quiz' | 'direct' = 'quiz') => {
    await loadData();
    // Immediately open Deep Tutor in user's chosen start mode!
    onSelectTrackForDeepStudy(
      newTrack.slug || newTrack.track_id,
      newTrack.track_id,
      startMode === 'direct',
    );
  };

  const handleTrackExpanded = async (updatedTrack: any) => {
    await loadData();
    const effectiveTarget = updatedTrack?.slug || updatedTrack?.track_id || selectedTrackId;
    if (effectiveTarget) {
      handleSelectTrack(effectiveTarget, false);
    }
  };

  const handleDeleteTrack = async (trackId: string, trackTitle: string) => {
    if (!window.confirm(`Вы уверены, что хотите удалить предмет «${trackTitle}» и его карту знаний?`)) {
      return;
    }
    setIsDeleting(true);
    try {
      await apiClient.deleteTrack(trackId);
      setSelectedTrackId(null);
      await loadData();
    } catch (err) {
      console.error('Failed to delete track:', err);
      alert('Не удалось удалить курс.');
    } finally {
      setIsDeleting(false);
    }
  };

  // Folder Operations
  const handleOpenCreateFolder = (trackIdToAssign?: string) => {
    setAssignTrackIdOnFolderCreate(trackIdToAssign || null);
    setFolderToEdit(null);
    setIsFolderModalOpen(true);
  };

  const handleOpenEditFolder = (folder: TrackFolder, e: React.MouseEvent) => {
    e.stopPropagation();
    setOpenFolderMenuId(null);
    setFolderToEdit(folder);
    setIsFolderModalOpen(true);
  };

  const handleDeleteFolder = async (folder: TrackFolder, e: React.MouseEvent) => {
    e.stopPropagation();
    setOpenFolderMenuId(null);
    if (
      !window.confirm(
        `Удалить папку «${folder.name}»?\nСами курсы внутри нее не удалятся, а переместятся в общий список.`
      )
    ) {
      return;
    }
    try {
      await apiClient.deleteFolder(folder.id);
      await loadData();
    } catch (err) {
      console.error('Failed to delete folder:', err);
      alert('Не удалось удалить папку.');
    }
  };

  const handleFolderSaved = async (savedFolder: TrackFolder) => {
    setFolders((prev) => {
      const idx = prev.findIndex((f) => f.id === savedFolder.id);
      if (idx >= 0) {
        const next = [...prev];
        next[idx] = savedFolder;
        return next;
      }
      return [savedFolder, ...prev];
    });

    // If folder was created specifically from a course, assign that course to this folder immediately!
    if (assignTrackIdOnFolderCreate) {
      const trackId = assignTrackIdOnFolderCreate;
      setAssignTrackIdOnFolderCreate(null);
      try {
        await apiClient.updateTrackOrganization(trackId, { folder_id: savedFolder.id });
      } catch (err) {
        console.error('Failed to automatically assign track to newly created folder:', err);
      }
    }

    await loadData();
  };

  const toggleFolderCollapse = (folderId: string) => {
    setCollapsedFolderIds((prev) => {
      const next = new Set(prev);
      if (next.has(folderId)) {
        next.delete(folderId);
      } else {
        next.add(folderId);
      }
      try {
        localStorage.setItem('got_it_collapsed_folders', JSON.stringify(Array.from(next)));
      } catch {}
      return next;
    });
  };

  const handleTogglePinFolder = async (folder: TrackFolder, e: React.MouseEvent) => {
    e.stopPropagation();
    const nextPinned = !folder.is_pinned;
    // Optimistic update
    setFolders((prev) =>
      prev.map((f) => (f.id === folder.id ? { ...f, is_pinned: nextPinned } : f))
    );
    try {
      await apiClient.updateFolder(folder.id, { is_pinned: nextPinned });
      // Re-sort folders
      const updatedList = await apiClient.listFolders();
      setFolders(updatedList);
    } catch (err) {
      console.error('Failed to toggle folder pin:', err);
      loadData();
    }
  };

  const handleTogglePinTrack = async (track: TrackSummary, e: React.MouseEvent) => {
    e.stopPropagation();
    const nextPinned = !track.is_pinned;
    // Optimistic update
    setTracks((prev) =>
      prev.map((t) => (t.track_id === track.track_id ? { ...t, is_pinned: nextPinned } : t))
    );
    try {
      await apiClient.updateTrackOrganization(track.track_id, { is_pinned: nextPinned });
      const updatedTracks = await apiClient.listTracks();
      setTracks(updatedTracks);
    } catch (err) {
      console.error('Failed to toggle track pin:', err);
      loadData();
    }
  };

  const handleMoveTrackToFolder = async (
    trackId: string,
    targetFolderId: string | null,
    e: React.MouseEvent
  ) => {
    e.stopPropagation();
    setOpenTrackMoveMenuId(null);
    // Optimistic update
    setTracks((prev) =>
      prev.map((t) => (t.track_id === trackId ? { ...t, folder_id: targetFolderId } : t))
    );
    try {
      await apiClient.updateTrackOrganization(trackId, { folder_id: targetFolderId });
      await loadData();
    } catch (err) {
      console.error('Failed to move track to folder:', err);
      loadData();
    }
  };

  // Searching and Filtering
  const { filteredTracks, matchingLessonsByTrackId } = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const matchesMap = new Map<string, string>();

    const filtered = tracks.filter((t) => {
      // 1. Filter by Active Tab / Chip
      if (activeFilter === 'pinned') {
        const folder = folders.find((f) => f.id === t.folder_id);
        const isTrackPinned = !!t.is_pinned;
        const isFolderPinned = !!folder?.is_pinned;
        if (!isTrackPinned && !isFolderPinned) return false;
      } else if (activeFilter !== 'all') {
        // activeFilter is a specific folderId
        if (t.folder_id !== activeFilter) return false;
      }

      // 2. Search Query Matching (Topic title, description, or individual concepts/lessons!)
      if (!q) return true;

      const titleMatch = t.title.toLowerCase().includes(q);
      const descMatch = (t.description || '').toLowerCase().includes(q);

      // Check concept titles
      let conceptMatchTitle: string | null = null;
      if (t.concepts && t.concepts.length > 0) {
        for (const c of t.concepts) {
          if (
            c.title.toLowerCase().includes(q) ||
            c.code.toLowerCase().includes(q) ||
            (c.summary && c.summary.toLowerCase().includes(q))
          ) {
            conceptMatchTitle = c.title;
            break;
          }
        }
      }

      if (conceptMatchTitle) {
        matchesMap.set(t.track_id, conceptMatchTitle);
      }

      return titleMatch || descMatch || !!conceptMatchTitle;
    });

    return {
      filteredTracks: filtered,
      matchingLessonsByTrackId: matchesMap,
    };
  }, [tracks, folders, searchQuery, activeFilter]);

  // Group filtered tracks by folder
  const { folderGroupMap, uncategorizedTracks } = useMemo(() => {
    const map = new Map<string, TrackSummary[]>();
    const uncategorized: TrackSummary[] = [];

    // Sort: pinned tracks first, then order
    const sorted = [...filteredTracks].sort((a, b) => {
      if (a.is_pinned === b.is_pinned) return 0;
      return a.is_pinned ? -1 : 1;
    });

    sorted.forEach((t) => {
      if (t.folder_id) {
        const list = map.get(t.folder_id) || [];
        list.push(t);
        map.set(t.folder_id, list);
      } else {
        uncategorized.push(t);
      }
    });

    return { folderGroupMap: map, uncategorizedTracks: uncategorized };
  }, [filteredTracks]);

  // Folders sorted: pinned folders first
  const sortedFolders = useMemo(() => {
    return [...folders].sort((a, b) => {
      if (a.is_pinned !== b.is_pinned) return a.is_pinned ? -1 : 1;
      return a.order_index - b.order_index;
    });
  }, [folders]);

  // Count pinned total
  const totalPinnedCount = useMemo(() => {
    const pinnedFolderCount = folders.filter((f) => f.is_pinned).length;
    const pinnedTrackCount = tracks.filter((t) => t.is_pinned).length;
    return pinnedFolderCount + pinnedTrackCount;
  }, [folders, tracks]);

  const selectedTrack = tracks.find(
    (t) => t.track_id === selectedTrackId || t.slug === selectedTrackId
  );

  const progressPercent = masteryOverview
    ? Math.round(
        (masteryOverview.mastered_concepts / Math.max(1, masteryOverview.total_concepts)) * 100,
      )
    : 0;

  // Render a Single Track Card
  const renderTrackCard = (t: TrackSummary, isNested: boolean = false) => {
    const isSelected = selectedTrackId === t.track_id;
    const isSessionTrack = activeTrackId === t.track_id;
    const matchingLesson = matchingLessonsByTrackId.get(t.track_id);
    const isMoveMenuOpen = openTrackMoveMenuId === t.track_id;
    const currentFolder = folders.find((f) => f.id === t.folder_id);

    return (
      <div
        key={t.track_id}
        onClick={() => handleSelectTrack(t.track_id)}
        className={`p-3.5 rounded-2xl border cursor-pointer transition-all duration-200 group relative ${
          isSelected
            ? 'bg-gradient-to-br from-indigo-950/90 to-surface-900/90 border-indigo-500/80 shadow-xl shadow-indigo-950/50 ring-1 ring-indigo-500/50'
            : 'bg-surface-900/75 hover:bg-surface-900/95 hover:border-slate-700 border-slate-800/90 text-slate-300 shadow-sm'
        } ${isNested ? 'ml-3 sm:ml-4 border-l-2' : ''}`}
        style={
          isNested && currentFolder?.color
            ? { borderLeftColor: currentFolder.color }
            : undefined
        }
      >
        <div className="flex items-center justify-between mb-1 gap-2">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <h4
              className={`text-xs sm:text-sm font-bold truncate ${
                isSelected ? 'text-white font-extrabold' : 'text-slate-100 group-hover:text-white'
              }`}
            >
              {t.title}
            </h4>
            {isSessionTrack && (
              <span className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse shrink-0" title="Активный курс"></span>
            )}
          </div>

          {/* Card Action Buttons (Move, Pin, Concept Count) */}
          <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
            {/* Move to Folder Button & Dropdown */}
            <div className="relative">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setOpenTrackMoveMenuId(isMoveMenuOpen ? null : t.track_id);
                }}
                title="Переместить в папку..."
                className={`p-1.5 rounded-lg transition-all ${
                  isMoveMenuOpen
                    ? 'text-indigo-300 bg-indigo-950/60'
                    : 'text-slate-500 hover:text-slate-300 hover:bg-surface-800 opacity-0 group-hover:opacity-100 focus:opacity-100'
                }`}
              >
                <FolderInput className="w-3.5 h-3.5" />
              </button>

              {/* Move to Folder Dropdown Menu */}
              {isMoveMenuOpen && (
                <div
                  className="absolute right-0 top-full mt-1 w-52 bg-surface-900 border border-slate-700 rounded-2xl shadow-2xl z-50 p-1.5 space-y-1 animate-fade-in"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="px-2.5 py-1.5 text-[10px] font-bold text-slate-400 uppercase tracking-wider border-b border-slate-800">
                    Переместить в папку
                  </div>
                  {/* Option: Uncategorized / Root */}
                  <button
                    type="button"
                    onClick={(e) => handleMoveTrackToFolder(t.track_id, null, e)}
                    className={`w-full text-left px-2.5 py-1.5 rounded-xl text-xs flex items-center justify-between transition-colors ${
                      !t.folder_id
                        ? 'bg-indigo-950/80 text-indigo-300 font-bold'
                        : 'text-slate-300 hover:bg-surface-800 hover:text-white'
                    }`}
                  >
                    <span>Без папки (Общий список)</span>
                    {!t.folder_id && <CheckCircle className="w-3.5 h-3.5 text-indigo-400" />}
                  </button>

                  {/* Folders Options */}
                  {folders.map((f) => {
                    const isCurrent = t.folder_id === f.id;
                    const IconComp = FOLDER_ICONS[f.icon || 'folder'] || Folder;
                    return (
                      <button
                        key={f.id}
                        type="button"
                        onClick={(e) => handleMoveTrackToFolder(t.track_id, f.id, e)}
                        className={`w-full text-left px-2.5 py-1.5 rounded-xl text-xs flex items-center justify-between transition-colors ${
                          isCurrent
                            ? 'bg-indigo-950/80 text-indigo-300 font-bold'
                            : 'text-slate-300 hover:bg-surface-800 hover:text-white'
                        }`}
                      >
                        <span className="flex items-center gap-2 truncate">
                          <span
                            className="w-4 h-4 rounded-md flex items-center justify-center shrink-0"
                            style={{ backgroundColor: `${f.color || '#6366f1'}25`, color: f.color || '#6366f1' }}
                          >
                            <IconComp className="w-2.5 h-2.5" />
                          </span>
                          <span className="truncate">{f.name}</span>
                        </span>
                        {isCurrent && <CheckCircle className="w-3.5 h-3.5 text-indigo-400" />}
                      </button>
                    );
                  })}

                  <div className="border-t border-slate-800 pt-1">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setOpenTrackMoveMenuId(null);
                        handleOpenCreateFolder(t.track_id);
                      }}
                      className="w-full text-left px-2.5 py-1.5 rounded-xl text-xs text-indigo-400 hover:text-indigo-300 hover:bg-surface-800 flex items-center gap-1.5 font-medium"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      <span>Создать новую папку</span>
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Pin Track Button */}
            <button
              type="button"
              onClick={(e) => handleTogglePinTrack(t, e)}
              title={t.is_pinned ? 'Открепить курс' : 'Закрепить курс наверху'}
              className={`p-1.5 rounded-lg transition-all ${
                t.is_pinned
                  ? 'text-amber-300 bg-amber-950/50 hover:bg-amber-900/60'
                  : 'text-slate-500 hover:text-slate-300 hover:bg-surface-800 opacity-0 group-hover:opacity-100 focus:opacity-100'
              }`}
            >
              <Pin className={`w-3.5 h-3.5 ${t.is_pinned ? 'fill-amber-400' : ''}`} />
            </button>

            {/* Concepts count badge */}
            <span
              className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border shrink-0 ${
                isSelected
                  ? 'bg-indigo-950/90 border-indigo-500/40 text-indigo-200'
                  : 'bg-surface-950/80 border-slate-800 text-slate-400'
              }`}
            >
              {t.total_concepts}
            </span>
          </div>
        </div>

        {/* Matching lesson notice if search matched an inner concept */}
        {matchingLesson && (
          <div className="my-1 px-2 py-0.5 rounded-lg bg-cyan-950/80 border border-cyan-500/40 text-[10px] text-cyan-300 flex items-center gap-1.5 truncate">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-ping"></span>
            <span className="font-bold">Урок:</span>
            <span className="truncate">{matchingLesson}</span>
          </div>
        )}

        <p className={`text-xs line-clamp-2 leading-relaxed ${isSelected ? 'text-slate-300' : 'text-slate-400'}`}>
          {t.description || 'Адаптивный граф знаний и трекер мастерства.'}
        </p>
      </div>
    );
  };

  return (
    <div className="flex-1 flex flex-col p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto w-full pb-32 space-y-6">
      {/* Create Track Modal */}
      <CreateTrackModal
        isOpen={isCreateModalOpen}
        userId={userId}
        folders={folders}
        initialFolderId={activeFilter !== 'all' && activeFilter !== 'pinned' ? activeFilter : null}
        onClose={() => setIsCreateModalOpen(false)}
        onTrackCreated={handleTrackCreated}
      />

      {/* Folder Create/Edit Modal */}
      <FolderModal
        isOpen={isFolderModalOpen}
        folderToEdit={folderToEdit}
        onClose={() => {
          setIsFolderModalOpen(false);
          setFolderToEdit(null);
        }}
        onSaved={handleFolderSaved}
      />

      {/* Expand Track Volume Modal */}
      {selectedTrack && (
        <ExpandTrackModal
          isOpen={isExpandModalOpen}
          userId={userId}
          trackId={selectedTrack.track_id}
          trackTitle={selectedTrack.title}
          currentDepthLevel={selectedTrack.depth_level || masteryOverview?.track_depth_level || 'medium'}
          currentConceptCount={masteryOverview?.total_concepts || selectedTrack.total_concepts || 0}
          onClose={() => setIsExpandModalOpen(false)}
          onTrackExpanded={handleTrackExpanded}
        />
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-5">
        <div>
          <h1 className="text-2xl lg:text-3xl font-black text-white tracking-tight flex items-center gap-2.5">
            <Compass className="w-7 h-7 text-indigo-400" />
            <span>Knowledge Map & Curricula</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Карта знаний, папки курсов и адаптивные образовательные траектории
          </p>
        </div>

        <div className="flex items-center gap-2.5 self-start sm:self-auto flex-wrap">
          {/* New Folder Button */}
          <button
            onClick={() => handleOpenCreateFolder()}
            className="px-4 py-2.5 bg-surface-900 hover:bg-surface-800 border border-slate-800 hover:border-slate-700 text-slate-200 hover:text-white rounded-2xl text-xs sm:text-sm font-bold shadow-md flex items-center gap-2 transition-all cursor-pointer"
          >
            <FolderPlus className="w-4 h-4 text-indigo-400" />
            <span>Новая папка</span>
          </button>

          {/* New Track Button */}
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="px-5 py-2.5 bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 text-white rounded-2xl text-xs sm:text-sm font-bold shadow-xl shadow-indigo-600/30 flex items-center justify-center gap-2 transition-all cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            <span>Создать курс</span>
          </button>
        </div>
      </div>

      {/* Mobile-only Track Selector with Folder Chips */}
      <div className="lg:hidden space-y-3">
        {/* Mobile Search */}
        <div className="relative">
          <Search className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Поиск курса или урока..."
            className="w-full bg-surface-900 border border-slate-800 rounded-2xl pl-10 pr-9 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white p-1"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Mobile Horizontal Selector */}
        <div className="flex gap-2 overflow-x-auto pb-1 items-center">
          {filteredTracks.map((t) => (
            <button
              key={t.track_id}
              onClick={() => handleSelectTrack(t.track_id)}
              className={`px-3.5 py-2 rounded-2xl text-xs font-bold whitespace-nowrap transition-all border flex items-center gap-1.5 ${
                selectedTrackId === t.track_id
                  ? 'bg-indigo-600 border-indigo-500 text-white shadow-lg shadow-indigo-600/30'
                  : 'bg-surface-900 border-slate-800 text-slate-400 hover:text-slate-200'
              }`}
            >
              {t.is_pinned && <Pin className="w-3 h-3 fill-amber-400 text-amber-400 shrink-0" />}
              <span>{t.title}</span>
            </button>
          ))}

          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="px-3 py-2 rounded-2xl text-xs font-semibold bg-surface-950 border border-dashed border-slate-700 text-indigo-400 hover:text-indigo-300 hover:border-indigo-500 whitespace-nowrap flex items-center gap-1 transition-all"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Добавить</span>
          </button>
        </div>
      </div>

      {/* Desktop 2-Column Responsive Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column on Desktop: Subject/Tracks Sidebar with Folders & Search */}
        <div className="hidden lg:block lg:col-span-4 space-y-4">
          {/* Search Bar */}
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Поиск по курсам и урокам..."
              className="w-full bg-surface-900 border border-slate-800/90 rounded-2xl pl-10 pr-9 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all shadow-inner"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white p-1 rounded-md"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Quick Filter Chips (All, Pinned, Folders) */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-[11px] font-semibold no-scrollbar">
            <button
              onClick={() => setActiveFilter('all')}
              className={`px-3 py-1 rounded-xl transition-all whitespace-nowrap border ${
                activeFilter === 'all'
                  ? 'bg-indigo-600/30 border-indigo-500 text-indigo-200'
                  : 'bg-surface-900 border-slate-800 text-slate-400 hover:text-slate-200'
              }`}
            >
              Все ({tracks.length})
            </button>

            {totalPinnedCount > 0 && (
              <button
                onClick={() => setActiveFilter('pinned')}
                className={`px-2.5 py-1 rounded-xl transition-all whitespace-nowrap border flex items-center gap-1 ${
                  activeFilter === 'pinned'
                    ? 'bg-amber-500/25 border-amber-500/60 text-amber-300 font-bold'
                    : 'bg-surface-900 border-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                <Pin className="w-3 h-3 fill-amber-400 text-amber-400" />
                <span>Pins ({totalPinnedCount})</span>
              </button>
            )}

            {folders.map((f) => (
              <button
                key={f.id}
                onClick={() => setActiveFilter(activeFilter === f.id ? 'all' : f.id)}
                className={`px-2.5 py-1 rounded-xl transition-all whitespace-nowrap border flex items-center gap-1.5 ${
                  activeFilter === f.id
                    ? 'bg-surface-800 border-slate-600 text-white font-bold'
                    : 'bg-surface-900 border-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                <span
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{ backgroundColor: f.color || '#6366f1' }}
                />
                <span className="truncate max-w-[100px]">{f.name}</span>
              </button>
            ))}
          </div>

          {/* Section Header */}
          <div className="flex items-center justify-between px-1 pt-1">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
              <span>Предметы и папки</span>
              <span className="text-[10px] text-slate-500 font-normal">
                ({filteredTracks.length} из {tracks.length})
              </span>
            </h3>

            <button
              onClick={() => handleOpenCreateFolder()}
              className="text-[11px] text-indigo-400 hover:text-indigo-300 font-bold flex items-center gap-1 hover:underline cursor-pointer"
            >
              <FolderPlus className="w-3.5 h-3.5" />
              <span>Папка</span>
            </button>
          </div>

          {/* Subject List & Folders Container */}
          <div className="space-y-3">
            {/* 1. Folders Section */}
            {sortedFolders.map((folder) => {
              const folderTracks = folderGroupMap.get(folder.id) || [];
              const isCollapsed =
                collapsedFolderIds.has(folder.id) && !searchQuery.trim();
              const isFolderPinned = folder.is_pinned;
              const isFolderMenuOpen = openFolderMenuId === folder.id;
              const FolderIconComp = FOLDER_ICONS[folder.icon || 'folder'] || Folder;

              // Hide folder if searching and no tracks match inside it and activeFilter is not this folder
              if (
                (searchQuery.trim() || activeFilter !== 'all') &&
                folderTracks.length === 0 &&
                activeFilter !== folder.id
              ) {
                return null;
              }

              return (
                <div
                  key={folder.id}
                  className="rounded-2xl border border-slate-800/80 bg-surface-950/40 overflow-hidden shadow-sm transition-all"
                >
                  {/* Folder Header */}
                  <div
                    onClick={() => toggleFolderCollapse(folder.id)}
                    className="p-3 bg-surface-900/60 hover:bg-surface-900 border-b border-slate-800/40 flex items-center justify-between cursor-pointer group select-none transition-colors"
                  >
                    <div className="flex items-center gap-2.5 min-w-0 flex-1">
                      <button
                        type="button"
                        className="text-slate-400 group-hover:text-white transition-transform"
                      >
                        {isCollapsed ? (
                          <ChevronRight className="w-4 h-4" />
                        ) : (
                          <ChevronDown className="w-4 h-4" />
                        )}
                      </button>

                      <div
                        className="w-6 h-6 rounded-lg flex items-center justify-center shrink-0 shadow-sm"
                        style={{
                          backgroundColor: `${folder.color || '#6366f1'}25`,
                          color: folder.color || '#6366f1',
                        }}
                      >
                        <FolderIconComp className="w-3.5 h-3.5" />
                      </div>

                      <span className="text-xs font-bold text-slate-200 group-hover:text-white truncate">
                        {folder.name}
                      </span>

                      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-surface-950 border border-slate-800 text-slate-400">
                        {folderTracks.length}
                      </span>
                    </div>

                    {/* Folder Pin & Options */}
                    <div
                      className="flex items-center gap-1 shrink-0"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {/* Pin Folder Button */}
                      <button
                        type="button"
                        onClick={(e) => handleTogglePinFolder(folder, e)}
                        title={isFolderPinned ? 'Открепить папку' : 'Закрепить папку наверху'}
                        className={`p-1.5 rounded-lg transition-all ${
                          isFolderPinned
                            ? 'text-amber-300 bg-amber-950/50 hover:bg-amber-900/60'
                            : 'text-slate-500 hover:text-slate-300 hover:bg-surface-800 opacity-0 group-hover:opacity-100 focus:opacity-100'
                        }`}
                      >
                        <Pin
                          className={`w-3.5 h-3.5 ${isFolderPinned ? 'fill-amber-400' : ''}`}
                        />
                      </button>

                      {/* Folder Options Menu */}
                      <div className="relative">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setOpenFolderMenuId(isFolderMenuOpen ? null : folder.id);
                          }}
                          className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-surface-800 transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
                        >
                          <MoreVertical className="w-3.5 h-3.5" />
                        </button>

                        {isFolderMenuOpen && (
                          <div
                            className="absolute right-0 top-full mt-1 w-44 bg-surface-900 border border-slate-700 rounded-2xl shadow-2xl z-50 p-1.5 space-y-1 animate-fade-in"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <button
                              type="button"
                              onClick={(e) => handleOpenEditFolder(folder, e)}
                              className="w-full text-left px-3 py-2 rounded-xl text-xs text-slate-200 hover:text-white hover:bg-surface-800 flex items-center gap-2 transition-colors"
                            >
                              <Edit2 className="w-3.5 h-3.5 text-indigo-400" />
                              <span>Редактировать</span>
                            </button>
                            <button
                              type="button"
                              onClick={(e) => handleDeleteFolder(folder, e)}
                              className="w-full text-left px-3 py-2 rounded-xl text-xs text-rose-400 hover:text-rose-300 hover:bg-rose-950/50 flex items-center gap-2 transition-colors"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                              <span>Удалить папку</span>
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Folder Contents */}
                  {!isCollapsed && (
                    <div className="p-2 space-y-2">
                      {folderTracks.length > 0 ? (
                        folderTracks.map((t) => renderTrackCard(t, true))
                      ) : (
                        <div className="py-4 px-3 text-center text-[11px] text-slate-500">
                          В этой папке пока нет курсов.
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}

            {/* 2. Uncategorized / General Tracks Section */}
            {uncategorizedTracks.length > 0 && (
              <div className="space-y-2">
                {sortedFolders.length > 0 && (
                  <div className="px-1 pt-2 pb-1 text-[11px] font-bold text-slate-500 uppercase tracking-wider flex items-center gap-2">
                    <Folder className="w-3 h-3 text-slate-600" />
                    <span>Общие курсы (без папки)</span>
                  </div>
                )}
                {uncategorizedTracks.map((t) => renderTrackCard(t, false))}
              </div>
            )}

            {/* Empty Search / Empty Tracks Notice */}
            {filteredTracks.length === 0 && !loading && (
              <div className="py-8 text-center text-slate-500 text-xs bg-surface-900/40 rounded-2xl border border-slate-800/60 p-4">
                {searchQuery
                  ? 'По вашему запросу ничего не найдено.'
                  : 'Список предметов пуст. Создайте свой первый курс!'}
              </div>
            )}

            {/* New Topic Button */}
            <button
              onClick={() => setIsCreateModalOpen(true)}
              className="w-full p-4 rounded-2xl border border-dashed border-slate-700/80 bg-surface-950/50 hover:bg-surface-900/50 hover:border-indigo-500/60 text-indigo-300 font-bold text-xs flex items-center justify-center gap-2 transition-all cursor-pointer"
            >
              <Plus className="w-4 h-4" />
              <span>Создать новый предмет / тему</span>
            </button>
          </div>
        </div>

        {/* Right Column: Selected Track Details & Knowledge Nodes */}
        <div className="lg:col-span-8 space-y-6">
          {loading ? (
            <div className="py-16 flex flex-col items-center justify-center text-center">
              <Loader2 className="w-10 h-10 text-indigo-500 animate-spin mb-3" />
              <p className="text-xs text-slate-400">Loading topic ontology and mastery state...</p>
            </div>
          ) : masteryOverview && selectedTrack ? (
            <div className="space-y-6">
              {/* Main Guided Arc Action Card */}
              <div className="p-6 sm:p-8 rounded-3xl bg-gradient-to-br from-indigo-950/90 via-surface-900 to-surface-900 border border-indigo-500/40 shadow-2xl relative overflow-hidden">
                <div className="flex items-start sm:items-center justify-between gap-4 mb-3 flex-wrap">
                  <div className="flex items-center gap-2.5 flex-wrap">
                    <h2 className="text-2xl sm:text-3xl font-black text-white tracking-tight">{selectedTrack.title}</h2>
                    {selectedTrack.is_pinned && (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/20 border border-amber-500/40 text-amber-300 flex items-center gap-1">
                        <Pin className="w-3 h-3 fill-amber-400" />
                        Pinned
                      </span>
                    )}
                    {selectedTrack.depth_level && (
                      <span className={`text-[11px] font-bold px-2.5 py-0.5 rounded-full border ${
                        selectedTrack.depth_level === 'low'
                          ? 'bg-amber-950/80 border-amber-500/40 text-amber-300'
                          : selectedTrack.depth_level === 'medium'
                          ? 'bg-sky-950/80 border-sky-500/40 text-sky-300'
                          : 'bg-indigo-950/80 border-indigo-500/40 text-indigo-300'
                      }`}>
                        {selectedTrack.depth_level === 'low' ? '±6 уроков (Low)' : selectedTrack.depth_level === 'medium' ? '15–25 уроков (Med)' : '40+ уроков (High)'}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {/* Pin/Unpin Button in Header */}
                    <button
                      onClick={(e) => handleTogglePinTrack(selectedTrack, e)}
                      title={selectedTrack.is_pinned ? 'Открепить курс' : 'Закрепить курс'}
                      className={`px-3 py-2 rounded-xl border transition-all flex items-center gap-1.5 text-xs font-bold shrink-0 cursor-pointer shadow-md ${
                        selectedTrack.is_pinned
                          ? 'bg-amber-950/60 text-amber-300 border-amber-500/50 hover:bg-amber-900/80'
                          : 'bg-surface-950/80 hover:bg-surface-800 text-slate-300 border-slate-800 hover:border-slate-700'
                      }`}
                    >
                      <Pin className={`w-3.5 h-3.5 ${selectedTrack.is_pinned ? 'fill-amber-400' : ''}`} />
                      <span>{selectedTrack.is_pinned ? 'Открепить' : 'Закрепить'}</span>
                    </button>

                    {/* Expand Course Volume Button */}
                    <button
                      onClick={() => setIsExpandModalOpen(true)}
                      title="Увеличить объем и уровень детализации курса"
                      className="px-3 py-2 rounded-xl bg-indigo-950/80 hover:bg-indigo-900 text-indigo-300 hover:text-white border border-indigo-500/40 hover:border-indigo-500/80 transition-all flex items-center gap-1.5 text-xs font-bold shrink-0 cursor-pointer shadow-md"
                    >
                      <Layers className="w-3.5 h-3.5 text-indigo-400" />
                      <span>Увеличить объем</span>
                    </button>

                    {/* Delete Subject Button */}
                    <button
                      onClick={() => handleDeleteTrack(selectedTrack.track_id, selectedTrack.title)}
                      disabled={isDeleting}
                      title="Delete this topic"
                      className="p-2 rounded-xl bg-surface-950/80 hover:bg-rose-950 text-slate-400 hover:text-rose-300 border border-slate-800 hover:border-rose-500/40 transition-all flex items-center gap-1.5 text-xs font-semibold shrink-0 cursor-pointer"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      <span className="hidden sm:inline">Delete Topic</span>
                    </button>
                  </div>
                </div>
                <p className="text-sm text-slate-300 mb-4 leading-relaxed max-w-2xl">
                  {masteryOverview.track_description || selectedTrack.description || `Комплексный курс по теме «${selectedTrack.title}»: системное освоение ключевых понятий и практических навыков.`}
                </p>

                {(masteryOverview.track_user_wishes || selectedTrack.user_wishes) && (
                  <div className="mb-5 p-3.5 rounded-2xl bg-indigo-950/60 border border-indigo-500/30 flex items-start gap-2.5 text-xs text-indigo-200/90 leading-relaxed shadow-inner">
                    <MessageSquare className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-bold text-indigo-300">Пожелания к курсу: </span>
                      <span>{masteryOverview.track_user_wishes || selectedTrack.user_wishes}</span>
                    </div>
                  </div>
                )}

                {/* Track Progress Bar */}
                <div className="mb-6 space-y-2">
                  <div className="flex justify-between text-xs font-semibold">
                    <span className="text-slate-400">Track Mastery Progress</span>
                    <span className="text-indigo-300 font-bold">{progressPercent}% ({masteryOverview.mastered_concepts}/{masteryOverview.total_concepts} Mastered)</span>
                  </div>
                  <div className="w-full h-3 bg-surface-950 rounded-full overflow-hidden border border-slate-800 shadow-inner">
                    <div
                      className="h-full bg-gradient-to-r from-indigo-500 via-indigo-400 to-emerald-400 rounded-full transition-all duration-500"
                      style={{ width: `${progressPercent}%` }}
                    />
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row gap-3">
                  <button
                    onClick={() => {
                      const target = selectedTrack.slug || selectedTrack.track_id;
                      onSelectTrackForDeepStudy(target, selectedTrack.track_id, false);
                    }}
                    className="flex-1 py-4 bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-sm sm:text-base rounded-2xl shadow-xl shadow-indigo-600/30 flex items-center justify-center gap-2.5 transition-all cursor-pointer"
                  >
                    <Play className="w-5 h-5 fill-white" />
                    <span>
                      {masteryOverview.mastered_concepts === 0 && masteryOverview.in_progress_concepts === 0
                        ? 'Начать обучение'
                        : 'Продолжить обучение'}
                    </span>
                    <ArrowRight className="w-5 h-5" />
                  </button>
                </div>
              </div>

              {/* Concepts List in Track */}
              <div className="space-y-3">
                <div className="flex items-center justify-between px-1">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                    {masteryOverview.mastered_concepts > 0 || masteryOverview.in_progress_concepts > 0 || masteryOverview.concepts.length > 5
                      ? `Personalized Course Trajectory (${masteryOverview.concepts.length} Concepts)`
                      : 'Diagnostic Assessment Ready'}
                  </h3>
                  <span className="text-[11px] text-slate-500">Ordered by Prerequisites</span>
                </div>

                {/* If track is newly created and awaiting diagnostic assessment */}
                {masteryOverview.total_concepts <= 5 && masteryOverview.mastered_concepts === 0 && masteryOverview.in_progress_concepts === 0 ? (
                  <div className="p-8 rounded-3xl bg-surface-900/60 border border-slate-800 text-center space-y-3">
                    <Compass className="w-10 h-10 text-indigo-400 mx-auto" />
                    <h4 className="text-base font-bold text-white">Cognitive Profiling & Tailored Curriculum</h4>
                    <p className="text-sm text-slate-400 max-w-md mx-auto leading-relaxed">
                      Click <strong>«Start Complete Guided Deep Arc»</strong> above to complete the fast diagnostic assessment. The AI architect will then compile a complete 20–35+ concept individual course DAG for you!
                    </p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {(() => {
                      const nextUpIdx = masteryOverview.concepts.findIndex(
                        (c) => !(c.is_mastered || c.mastery_prob >= 0.85)
                      );

                      return masteryOverview.concepts.map((concept, idx) => {
                        const isMastered = concept.is_mastered || concept.mastery_prob >= 0.85;
                        const inProgress = !isMastered && concept.mastery_prob >= 0.2;
                        const isCurrentActive = activeConceptId === concept.concept_id || activeConceptId === concept.slug;
                        const isNextUp = !isCurrentActive && idx === nextUpIdx;

                        return (
                          <div
                            key={concept.concept_id}
                            onClick={() => onSelectTrackForDeepStudy(concept.slug || concept.concept_id, selectedTrack.track_id)}
                            className={`p-4 rounded-2xl border transition-all flex items-center justify-between gap-3 cursor-pointer ${
                              isCurrentActive
                                ? 'bg-indigo-950/80 border-indigo-400 shadow-xl shadow-indigo-600/20 ring-2 ring-indigo-500/50'
                                : isNextUp
                                ? 'bg-surface-900/75 hover:bg-surface-900/90 border-cyan-500/60 hover:border-cyan-400 shadow-md shadow-cyan-950/30'
                                : isMastered
                                ? 'bg-surface-900/40 hover:bg-surface-900/65 border-emerald-500/40 hover:border-emerald-500/60 shadow-sm'
                                : inProgress
                                ? 'bg-surface-900/40 hover:bg-surface-900/65 border-indigo-500/40 hover:border-indigo-500/60'
                                : 'bg-surface-900/40 hover:bg-surface-900/65 border-slate-800/80 hover:border-slate-700'
                            }`}
                          >
                            <div className="flex items-start gap-3 flex-1 min-w-0">
                              <div className="mt-0.5 shrink-0">
                                {isCurrentActive ? (
                                  <Sparkles className="w-5 h-5 text-indigo-400 animate-pulse" />
                                ) : isMastered ? (
                                  <CheckCircle className="w-5 h-5 text-emerald-400" />
                                ) : isNextUp ? (
                                  <div className="w-5 h-5 rounded-full bg-cyan-950/80 border border-cyan-400/60 flex items-center justify-center text-[10px] text-cyan-300 font-bold">
                                    <Play className="w-2.5 h-2.5 fill-cyan-400 text-cyan-400 ml-0.5" />
                                  </div>
                                ) : inProgress ? (
                                  <Activity className="w-5 h-5 text-indigo-400 animate-pulse" />
                                ) : (
                                  <div className="w-5 h-5 rounded-full border border-slate-700 flex items-center justify-center text-[10px] text-slate-500 font-bold">
                                    {idx + 1}
                                  </div>
                                )}
                              </div>

                              <div className="min-w-0 flex-1">
                                <h4 className={`text-xs font-bold truncate ${
                                  isCurrentActive
                                    ? 'text-indigo-200 font-extrabold'
                                    : isNextUp
                                    ? 'text-cyan-100 font-bold'
                                    : 'text-white'
                                }`}>
                                  {concept.title}
                                </h4>
                                <p className="text-[11px] text-slate-400 truncate mt-0.5">
                                  {Math.round(concept.mastery_prob * 100)}% Mastery
                                </p>
                              </div>
                            </div>

                            <div className="text-xs font-semibold px-2 py-1 rounded-lg shrink-0">
                              {isCurrentActive ? (
                                <span className="text-white bg-indigo-600 px-2.5 py-0.5 rounded-md text-[10px] font-bold shadow-md shadow-indigo-600/40 flex items-center gap-1">
                                  <Sparkles className="w-3 h-3 fill-white" />
                                  Current
                                </span>
                              ) : isMastered ? (
                                <span className="text-emerald-400 bg-emerald-950/60 border border-emerald-500/30 px-2 py-0.5 rounded-md text-[10px]">
                                  Mastered
                                </span>
                              ) : isNextUp ? (
                                <span className="text-cyan-300 bg-cyan-950/80 border border-cyan-500/40 px-2 py-0.5 rounded-md text-[10px] font-medium flex items-center gap-1">
                                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
                                  Next Up
                                </span>
                              ) : inProgress ? (
                                <span className="text-indigo-300 bg-indigo-950/60 border border-indigo-500/30 px-2 py-0.5 rounded-md text-[10px]">
                                  In Progress
                                </span>
                              ) : (
                                <span className="text-slate-500 text-[10px]">Ready</span>
                              )}
                            </div>
                          </div>
                        );
                      });
                    })()}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="p-8 text-center text-slate-400 bg-surface-900 rounded-3xl border border-slate-800">
              <BookOpen className="w-10 h-10 text-slate-600 mx-auto mb-3" />
              <p>Select a subject from the list to view its knowledge graph.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
