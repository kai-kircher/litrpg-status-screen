'use client';

import { useState, useEffect, useCallback } from 'react';

type Job = {
  id: number;
  job_type: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  started_at: string | null;
  completed_at: string | null;
  config: any;
  progress: any;
  result: any;
  error_message: string | null;
  created_at: string;
};

type Stats = {
  chapters: { total: number; scraped: number };
  characters: number;
  events: {
    total: number;
    assigned: number;
    processed: number;
    archived: number;
    byType: { event_type: string; count: string }[];
  };
  recentJobs: Job[];
  aiStats: any[] | null;
};

type RawEvent = {
  id: number;
  event_type: string | null;
  raw_text: string;
  parsed_data: any;
  context: string;
  surrounding_text: string;
  event_index: number;
  total_chapter_events: number;
  is_assigned: boolean;
  is_processed: boolean;
  character_id: number | null;
  archived: boolean;
  order_index: number;
  chapter_number: string;
  chapter_title: string | null;
  character_name: string | null;
  created_at: string;
};

type Character = {
  id: number;
  name: string;
  aliases: string[] | null;
  first_appearance_chapter_id: number | null;
  notes: string | null;
  created_at: string;
};

type Chapter = {
  id: number;
  chapter_number: string;
  title: string | null;
};

export default function AdminPage() {
  const [events, setEvents] = useState<RawEvent[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<RawEvent | null>(null);
  const [selectedEventIds, setSelectedEventIds] = useState<Set<number>>(new Set());
  const [expandedContexts, setExpandedContexts] = useState<Set<number>>(new Set());
  const [searchTerm, setSearchTerm] = useState('');
  const [eventFilter, setEventFilter] = useState('');
  const [newCharacterName, setNewCharacterName] = useState('');
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<'unassigned' | 'needs_review' | 'ready_to_process' | 'processed' | 'archived' | 'all'>('unassigned');
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const limit = 100;

  // Classification state
  const [classifyingEvent, setClassifyingEvent] = useState<RawEvent | null>(null);
  const [classificationType, setClassificationType] = useState<string>('');
  const [classificationTitle, setClassificationTitle] = useState<string>('');

  // Tab state
  const [activeTab, setActiveTab] = useState<'events' | 'characters'>('events');

  // Character management state
  const [allCharacters, setAllCharacters] = useState<Character[]>([]);
  const [characterSearchTerm, setCharacterSearchTerm] = useState('');
  const [editingCharacter, setEditingCharacter] = useState<Character | null>(null);
  const [characterFormData, setCharacterFormData] = useState<{
    name: string;
    aliases: string[];
    first_appearance_chapter_id: number | null;
    notes: string;
  }>({ name: '', aliases: [], first_appearance_chapter_id: null, notes: '' });
  const [newAliasInput, setNewAliasInput] = useState('');
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [characterLoading, setCharacterLoading] = useState(false);
  const [characterOffset, setCharacterOffset] = useState(0);
  const [characterTotal, setCharacterTotal] = useState(0);
  const characterLimit = 50;

  // Jobs & Stats state
  const [stats, setStats] = useState<Stats | null>(null);
  const [runningJob, setRunningJob] = useState<Job | null>(null);
  const [showJobPanel, setShowJobPanel] = useState(true);
  const [jobConfig, setJobConfig] = useState<{
    startChapter?: number;
    endChapter?: number;
    maxChapters?: number;
    dryRun?: boolean;
  }>({});

  // Load stats
  const loadStats = useCallback(async () => {
    try {
      const response = await fetch('/api/admin/stats');
      const data = await response.json();
      setStats(data);
    } catch (err) {
      console.error('Error loading stats:', err);
    }
  }, []);

  // Load jobs
  const loadJobs = useCallback(async () => {
    try {
      const response = await fetch('/api/admin/jobs?limit=5');
      const data = await response.json();
      setRunningJob(data.running);
    } catch (err) {
      console.error('Error loading jobs:', err);
    }
  }, []);

  // Start a job
  const startJob = async (jobType: string) => {
    if (runningJob) {
      alert('A job is already running');
      return;
    }

    try {
      const response = await fetch('/api/admin/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jobType, config: jobConfig }),
      });

      if (response.ok) {
        const data = await response.json();
        alert(`Job started: ${data.message}`);
        loadJobs();
        setJobConfig({});
      } else {
        const error = await response.json();
        alert(`Error: ${error.error}`);
      }
    } catch (err) {
      console.error('Error starting job:', err);
      alert('Failed to start job');
    }
  };

  // Cancel a job
  const cancelJob = async () => {
    if (!runningJob) return;

    if (!confirm('Are you sure you want to cancel the running job?')) return;

    try {
      const response = await fetch(`/api/admin/jobs?jobId=${runningJob.id}`, {
        method: 'DELETE',
      });

      if (response.ok) {
        alert('Job cancelled');
        loadJobs();
      } else {
        const error = await response.json();
        alert(`Error: ${error.error}`);
      }
    } catch (err) {
      console.error('Error cancelling job:', err);
      alert('Failed to cancel job');
    }
  };

  // Reset actions
  const performReset = async (action: string, confirmMessage: string) => {
    if (!confirm(confirmMessage)) return;

    try {
      const response = await fetch('/api/admin/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      });

      if (response.ok) {
        const data = await response.json();
        alert(data.message);
        loadStats();
        loadEvents();
        if (activeTab === 'characters') {
          loadAllCharacters();
        }
      } else {
        const error = await response.json();
        alert(`Error: ${error.error}`);
      }
    } catch (err) {
      console.error('Error performing reset:', err);
      alert('Failed to perform reset');
    }
  };

  // Initial load and polling
  useEffect(() => {
    loadStats();
    loadJobs();

    // Poll for job status every 5 seconds
    const interval = setInterval(() => {
      loadJobs();
    }, 5000);

    return () => clearInterval(interval);
  }, [loadStats, loadJobs]);

  useEffect(() => {
    loadEvents();
    loadTopCharacters();
  }, [statusFilter, offset]);

  // Debounce search - reload events 300ms after user stops typing
  useEffect(() => {
    const timer = setTimeout(() => {
      setOffset(0); // Reset to first page when searching
      loadEvents();
    }, 300);

    return () => clearTimeout(timer);
  }, [eventFilter]);

  const loadTopCharacters = async () => {
    try {
      const response = await fetch('/api/characters?limit=5');
      const data = await response.json();
      setCharacters(data);
    } catch (err) {
      console.error('Error loading top characters:', err);
    }
  };

  const loadEvents = async () => {
    try {
      let url = `/api/admin/events?limit=${limit}&offset=${offset}`;

      // Build query params based on status filter
      if (statusFilter === 'unassigned') {
        url += '&assigned=false';
      } else if (statusFilter === 'needs_review') {
        url += '&assigned=true&needs_review=true';
      } else if (statusFilter === 'ready_to_process') {
        url += '&assigned=true&processed=false&needs_review=false';
      } else if (statusFilter === 'processed') {
        url += '&assigned=true&processed=true';
      } else if (statusFilter === 'archived') {
        url += '&archived=true';
      } else if (statusFilter === 'all') {
        url += '&archived=all';
      }

      // Add search parameter if present
      if (eventFilter) {
        url += `&search=${encodeURIComponent(eventFilter)}`;
      }

      const response = await fetch(url);
      const data = await response.json();
      setEvents(data.events || []);
      setTotal(data.total || 0);
      setLoading(false);
    } catch (err) {
      console.error('Error loading events:', err);
      setError('Failed to load events');
      setLoading(false);
    }
  };

  const searchCharacters = async (term: string) => {
    if (!term) {
      // When search is cleared, reload top 5 characters
      loadTopCharacters();
      return;
    }

    try {
      const response = await fetch(`/api/characters?search=${encodeURIComponent(term)}`);
      const data = await response.json();
      setCharacters(data);
    } catch (err) {
      console.error('Error searching characters:', err);
    }
  };

  const createCharacter = async () => {
    if (!newCharacterName.trim()) return;

    try {
      const response = await fetch('/api/characters', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newCharacterName.trim() }),
      });

      if (response.ok) {
        const character = await response.json();
        setCharacters([character, ...characters]);
        setNewCharacterName('');
        setSearchTerm('');
      } else {
        const error = await response.json();
        alert(`Error: ${error.error}`);
      }
    } catch (err) {
      console.error('Error creating character:', err);
      alert('Failed to create character');
    }
  };

  const toggleEventSelection = (eventId: number) => {
    const newSelection = new Set(selectedEventIds);
    if (newSelection.has(eventId)) {
      newSelection.delete(eventId);
    } else {
      newSelection.add(eventId);
    }
    setSelectedEventIds(newSelection);
  };

  const toggleSelectAll = () => {
    if (selectedEventIds.size === events.length && events.length > 0) {
      setSelectedEventIds(new Set());
    } else {
      setSelectedEventIds(new Set(events.map(e => e.id)));
    }
  };

  const toggleContext = (eventId: number) => {
    const newExpanded = new Set(expandedContexts);
    if (newExpanded.has(eventId)) {
      newExpanded.delete(eventId);
    } else {
      newExpanded.add(eventId);
    }
    setExpandedContexts(newExpanded);
  };

  const assignEvent = async (characterId: number) => {
    // Batch assignment if multiple events selected
    if (selectedEventIds.size > 0) {
      try {
        const response = await fetch('/api/admin/assign', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            eventIds: Array.from(selectedEventIds),
            characterId,
          }),
        });

        if (response.ok) {
          const result = await response.json();
          alert(`Successfully assigned ${result.count} events`);
          await loadEvents();
          setSelectedEventIds(new Set());
          setSearchTerm('');
          setCharacters([]);
        } else {
          const error = await response.json();
          alert(`Error: ${error.error}`);
        }
      } catch (err) {
        console.error('Error assigning events:', err);
        alert('Failed to assign events');
      }
      return;
    }

    // Single assignment (original behavior)
    if (!selectedEvent) return;

    try {
      const response = await fetch('/api/admin/assign', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          eventId: selectedEvent.id,
          characterId,
        }),
      });

      if (response.ok) {
        // Refresh events list
        await loadEvents();
        setSelectedEvent(null);
        setSearchTerm('');
        setCharacters([]);
      } else {
        const error = await response.json();
        alert(`Error: ${error.error}`);
      }
    } catch (err) {
      console.error('Error assigning event:', err);
      alert('Failed to assign event');
    }
  };

  const unassignEvent = async (eventId: number) => {
    try {
      const response = await fetch(`/api/admin/assign?eventId=${eventId}`, {
        method: 'DELETE',
      });

      if (response.ok) {
        await loadEvents();
      }
    } catch (err) {
      console.error('Error unassigning event:', err);
    }
  };

  const processEvent = async (eventId: number) => {
    try {
      const response = await fetch('/api/admin/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ eventId }),
      });

      if (response.ok) {
        const result = await response.json();
        alert(`Success: ${result.message}`);
        await loadEvents();
      } else {
        const error = await response.json();
        alert(`Error: ${error.error}\n${error.details || ''}`);
      }
    } catch (err) {
      console.error('Error processing event:', err);
      alert('Failed to process event');
    }
  };

  const processAllEvents = async () => {
    // Get all event IDs that are ready to process (assigned but not processed)
    const eventIdsToProcess = events
      .filter(e => e.is_assigned && !e.is_processed)
      .map(e => e.id);

    if (eventIdsToProcess.length === 0) {
      alert('No events to process');
      return;
    }

    if (!confirm(`Are you sure you want to process ${eventIdsToProcess.length} event(s)?`)) {
      return;
    }

    try {
      const response = await fetch('/api/admin/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ eventIds: eventIdsToProcess }),
      });

      if (response.ok) {
        const result = await response.json();
        let message = `Success: ${result.message}`;
        if (result.errors && result.errors.length > 0) {
          message += '\n\nErrors:\n' + result.errors.map((e: any) => `- ${e.rawText}: ${e.error}`).join('\n');
        }
        alert(message);
        await loadEvents();
      } else {
        const error = await response.json();
        alert(`Error: ${error.error}\n${error.details || ''}`);
      }
    } catch (err) {
      console.error('Error processing events:', err);
      alert('Failed to process events');
    }
  };

  const archiveEvents = async () => {
    if (selectedEventIds.size === 0) return;

    try {
      const response = await fetch('/api/admin/archive', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ eventIds: Array.from(selectedEventIds) }),
      });

      if (response.ok) {
        const result = await response.json();
        alert(result.message);
        await loadEvents();
        setSelectedEventIds(new Set());
      } else {
        const error = await response.json();
        alert(`Error: ${error.error}`);
      }
    } catch (err) {
      console.error('Error archiving events:', err);
      alert('Failed to archive events');
    }
  };

  const archiveEvent = async (eventId: number) => {
    try {
      const response = await fetch('/api/admin/archive', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ eventId }),
      });

      if (response.ok) {
        await loadEvents();
      } else {
        const error = await response.json();
        alert(`Error: ${error.error}`);
      }
    } catch (err) {
      console.error('Error archiving event:', err);
      alert('Failed to archive event');
    }
  };

  const unarchiveEvent = async (eventId: number) => {
    try {
      const response = await fetch(`/api/admin/archive?eventId=${eventId}`, {
        method: 'DELETE',
      });

      if (response.ok) {
        await loadEvents();
      } else {
        const error = await response.json();
        alert(`Error: ${error.error}`);
      }
    } catch (err) {
      console.error('Error unarchiving event:', err);
      alert('Failed to unarchive event');
    }
  };

  const classifyEvent = async () => {
    if (!classifyingEvent || !classificationType) {
      alert('Please select an event type');
      return;
    }

    try {
      const response = await fetch('/api/admin/classify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          eventId: classifyingEvent.id,
          eventType: classificationType,
          title: classificationTitle,
        }),
      });

      if (response.ok) {
        alert('Event classified successfully');
        await loadEvents();
        setClassifyingEvent(null);
        setClassificationType('');
        setClassificationTitle('');
      } else {
        const error = await response.json();
        alert(`Error: ${error.error}`);
      }
    } catch (err) {
      console.error('Error classifying event:', err);
      alert('Failed to classify event');
    }
  };

  // Character Management Functions
  const loadAllCharacters = useCallback(async () => {
    setCharacterLoading(true);
    try {
      let url = `/api/characters?limit=${characterLimit}&offset=${characterOffset}`;
      if (characterSearchTerm) {
        url = `/api/characters?search=${encodeURIComponent(characterSearchTerm)}`;
      }
      const response = await fetch(url);
      const data = await response.json();
      setAllCharacters(data);
      // For now, estimate total from returned count
      setCharacterTotal(data.length >= characterLimit ? characterOffset + characterLimit + 1 : characterOffset + data.length);
    } catch (err) {
      console.error('Error loading characters:', err);
    } finally {
      setCharacterLoading(false);
    }
  }, [characterOffset, characterSearchTerm]);

  const loadChapters = useCallback(async () => {
    try {
      const response = await fetch('/api/chapters');
      const data = await response.json();
      setChapters(data);
    } catch (err) {
      console.error('Error loading chapters:', err);
    }
  }, []);

  // Load chapters when tab changes to characters
  useEffect(() => {
    if (activeTab === 'characters') {
      loadAllCharacters();
      if (chapters.length === 0) {
        loadChapters();
      }
    }
  }, [activeTab, loadAllCharacters, loadChapters, chapters.length]);

  // Debounce character search
  useEffect(() => {
    if (activeTab !== 'characters') return;
    const timer = setTimeout(() => {
      setCharacterOffset(0);
      loadAllCharacters();
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [characterSearchTerm, activeTab]);

  const openCharacterEditor = (character: Character) => {
    setEditingCharacter(character);
    setCharacterFormData({
      name: character.name,
      aliases: character.aliases || [],
      first_appearance_chapter_id: character.first_appearance_chapter_id,
      notes: character.notes || '',
    });
    setNewAliasInput('');
  };

  const closeCharacterEditor = () => {
    setEditingCharacter(null);
    setCharacterFormData({ name: '', aliases: [], first_appearance_chapter_id: null, notes: '' });
    setNewAliasInput('');
  };

  const addAlias = () => {
    const trimmed = newAliasInput.trim();
    if (trimmed && !characterFormData.aliases.includes(trimmed)) {
      setCharacterFormData({
        ...characterFormData,
        aliases: [...characterFormData.aliases, trimmed],
      });
      setNewAliasInput('');
    }
  };

  const removeAlias = (alias: string) => {
    setCharacterFormData({
      ...characterFormData,
      aliases: characterFormData.aliases.filter((a) => a !== alias),
    });
  };

  const saveCharacter = async () => {
    if (!editingCharacter) return;

    try {
      const response = await fetch(`/api/characters/${editingCharacter.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: characterFormData.name,
          aliases: characterFormData.aliases,
          first_appearance_chapter_id: characterFormData.first_appearance_chapter_id,
          notes: characterFormData.notes || null,
        }),
      });

      if (response.ok) {
        alert('Character updated successfully');
        closeCharacterEditor();
        loadAllCharacters();
        loadStats();
      } else {
        const error = await response.json();
        alert(`Error: ${error.error}`);
      }
    } catch (err) {
      console.error('Error saving character:', err);
      alert('Failed to save character');
    }
  };

  const deleteCharacter = async (characterId: number, characterName: string) => {
    if (!confirm(`Are you sure you want to delete "${characterName}"? This cannot be undone.`)) {
      return;
    }

    try {
      const response = await fetch(`/api/characters/${characterId}`, {
        method: 'DELETE',
      });

      if (response.ok) {
        alert('Character deleted successfully');
        closeCharacterEditor();
        loadAllCharacters();
        loadStats();
      } else {
        const error = await response.json();
        if (error.details) {
          alert(`Cannot delete: Character has ${error.details.classes} classes, ${error.details.abilities} abilities, and ${error.details.events} events linked.`);
        } else {
          alert(`Error: ${error.error}`);
        }
      }
    } catch (err) {
      console.error('Error deleting character:', err);
      alert('Failed to delete character');
    }
  };

  const getEventTypeColor = (type: string) => {
    switch (type) {
      case 'class_obtained':
        return 'bg-purple-100 text-purple-800';
      case 'class_evolution':
        return 'bg-purple-200 text-purple-900';
      case 'class_consolidation':
        return 'bg-purple-200 text-purple-900';
      case 'class_removed':
        return 'bg-red-100 text-red-800';
      case 'level_up':
        return 'bg-blue-100 text-blue-800';
      case 'skill_obtained':
        return 'bg-green-100 text-green-800';
      case 'skill_change':
        return 'bg-green-200 text-green-900';
      case 'skill_consolidation':
        return 'bg-green-200 text-green-900';
      case 'skill_removed':
        return 'bg-red-100 text-red-800';
      case 'spell_obtained':
        return 'bg-yellow-100 text-yellow-800';
      case 'spell_removed':
        return 'bg-red-100 text-red-800';
      case 'condition':
        return 'bg-orange-100 text-orange-800';
      case 'aspect':
        return 'bg-pink-100 text-pink-800';
      case 'title':
        return 'bg-indigo-100 text-indigo-800';
      case 'rank':
        return 'bg-cyan-100 text-cyan-800';
      case 'other':
        return 'bg-slate-100 text-slate-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };


  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-lg">Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-3xl font-bold mb-6">Admin Dashboard</h1>

        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
            {error}
          </div>
        )}

        {/* Stats & Jobs Panel */}
        <div className="mb-6">
          <button
            onClick={() => setShowJobPanel(!showJobPanel)}
            className="flex items-center gap-2 text-lg font-semibold text-gray-700 hover:text-gray-900 mb-3"
          >
            <span>{showJobPanel ? '▼' : '▶'}</span>
            <span>Stats & Jobs</span>
            {runningJob && (
              <span className="ml-2 px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded animate-pulse">
                Job Running
              </span>
            )}
          </button>

          {showJobPanel && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
              {/* Stats Card */}
              <div className="bg-white rounded-lg shadow p-4">
                <h3 className="font-semibold mb-3">Database Stats</h3>
                {stats ? (
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <p className="text-gray-500">Chapters</p>
                      <p className="text-xl font-bold">
                        {stats.chapters.scraped}
                        <span className="text-gray-400 text-sm font-normal">
                          /{stats.chapters.total}
                        </span>
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-500">Characters</p>
                      <p className="text-xl font-bold">{stats.characters}</p>
                    </div>
                    <div>
                      <p className="text-gray-500">Events</p>
                      <p className="text-xl font-bold">{stats.events.total}</p>
                    </div>
                    <div>
                      <p className="text-gray-500">Processed</p>
                      <p className="text-xl font-bold text-green-600">
                        {stats.events.processed}
                      </p>
                    </div>
                  </div>
                ) : (
                  <p className="text-gray-400">Loading stats...</p>
                )}
              </div>

              {/* Jobs Card */}
              <div className="bg-white rounded-lg shadow p-4">
                <h3 className="font-semibold mb-3">Background Jobs</h3>

                {runningJob ? (
                  <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium text-blue-900">
                        {runningJob.job_type}
                      </span>
                      <span className="text-xs text-blue-600 animate-pulse">
                        Running...
                      </span>
                    </div>
                    {runningJob.progress && (
                      <p className="text-xs text-blue-700 mb-2">
                        Chapters: {runningJob.progress.chaptersProcessed || 0}
                        {runningJob.progress.eventsProcessed ? `, Events: ${runningJob.progress.eventsProcessed}` : ''}
                      </p>
                    )}
                    <button
                      onClick={cancelJob}
                      className="text-xs px-3 py-1 bg-red-100 text-red-700 rounded hover:bg-red-200"
                    >
                      Cancel Job
                    </button>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {/* Job Config */}
                    <div className="flex gap-2 text-sm">
                      <input
                        type="number"
                        placeholder="Start"
                        value={jobConfig.startChapter || ''}
                        onChange={(e) => setJobConfig({...jobConfig, startChapter: e.target.value ? parseInt(e.target.value) : undefined})}
                        className="w-20 px-2 py-1 border rounded"
                      />
                      <input
                        type="number"
                        placeholder="End"
                        value={jobConfig.endChapter || ''}
                        onChange={(e) => setJobConfig({...jobConfig, endChapter: e.target.value ? parseInt(e.target.value) : undefined})}
                        className="w-20 px-2 py-1 border rounded"
                      />
                      <input
                        type="number"
                        placeholder="Max"
                        value={jobConfig.maxChapters || ''}
                        onChange={(e) => setJobConfig({...jobConfig, maxChapters: e.target.value ? parseInt(e.target.value) : undefined})}
                        className="w-20 px-2 py-1 border rounded"
                      />
                      <label className="flex items-center gap-1 text-xs">
                        <input
                          type="checkbox"
                          checked={jobConfig.dryRun || false}
                          onChange={(e) => setJobConfig({...jobConfig, dryRun: e.target.checked})}
                        />
                        Dry run
                      </label>
                    </div>

                    {/* Job Buttons */}
                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={() => startJob('build-toc')}
                        className="px-3 py-1.5 text-sm bg-gray-600 text-white rounded hover:bg-gray-700"
                      >
                        Build ToC
                      </button>
                      <button
                        onClick={() => startJob('scrape')}
                        className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
                      >
                        Scrape
                      </button>
                      <button
                        onClick={() => startJob('scrape-wiki')}
                        className="px-3 py-1.5 text-sm bg-purple-600 text-white rounded hover:bg-purple-700"
                      >
                        Scrape Wiki
                      </button>
                      <button
                        onClick={() => startJob('attribute-events')}
                        className="px-3 py-1.5 text-sm bg-green-600 text-white rounded hover:bg-green-700"
                        title="Real-time processing (faster but more expensive)"
                      >
                        Attribute Events
                      </button>
                      <button
                        onClick={() => startJob('batch-attribute-events')}
                        className="px-3 py-1.5 text-sm bg-emerald-600 text-white rounded hover:bg-emerald-700"
                        title="Batch processing (50% cheaper, async - results within 24h)"
                      >
                        Batch Attribute (50% off)
                      </button>
                      <button
                        onClick={() => startJob('process-ai')}
                        className="px-3 py-1.5 text-sm bg-indigo-600 text-white rounded hover:bg-indigo-700"
                      >
                        Full AI Process
                      </button>
                    </div>

                    {/* Reset Actions */}
                    <div className="mt-3 pt-3 border-t border-gray-200">
                      <p className="text-xs text-gray-500 mb-2">Reset Actions</p>
                      <div className="flex flex-wrap gap-2">
                        <button
                          onClick={() => performReset(
                            'unassign-all-events',
                            'Are you sure you want to unassign ALL events? This will remove character assignments but keep processed status.'
                          )}
                          className="px-3 py-1.5 text-sm bg-orange-100 text-orange-700 rounded hover:bg-orange-200"
                        >
                          Unassign All Events
                        </button>
                        <button
                          onClick={() => performReset(
                            'clear-progression-data',
                            'Are you sure you want to clear all progression data? This will delete all classes, levels, abilities, and unassign all events. Characters from the wiki will remain.'
                          )}
                          className="px-3 py-1.5 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200"
                        >
                          Clear Progression Data
                        </button>
                        <button
                          onClick={() => performReset(
                            'full-reset',
                            'Are you sure you want to perform a FULL RESET? This will clear all progression data (classes, levels, abilities) and reset all events to unassigned/unprocessed. Wiki characters will remain.'
                          )}
                          className="px-3 py-1.5 text-sm bg-red-600 text-white rounded hover:bg-red-700"
                        >
                          Full Reset
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* Recent Jobs */}
                {stats?.recentJobs && stats.recentJobs.length > 0 && (
                  <div className="mt-4 pt-3 border-t">
                    <p className="text-xs text-gray-500 mb-2">Recent Jobs</p>
                    <div className="space-y-1">
                      {stats.recentJobs.slice(0, 3).map((job) => (
                        <div key={job.id} className="flex items-center justify-between text-xs">
                          <span className="font-medium">{job.job_type}</span>
                          <span className={
                            job.status === 'completed' ? 'text-green-600' :
                            job.status === 'failed' ? 'text-red-600' :
                            job.status === 'running' ? 'text-blue-600' :
                            'text-gray-500'
                          }>
                            {job.status}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Tab Navigation */}
        <div className="mb-6 border-b border-gray-200">
          <nav className="-mb-px flex space-x-8">
            <button
              onClick={() => setActiveTab('events')}
              className={`py-2 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'events'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Events
            </button>
            <button
              onClick={() => setActiveTab('characters')}
              className={`py-2 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'characters'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Characters
            </button>
          </nav>
        </div>

        {/* Events Tab Content */}
        {activeTab === 'events' && (
          <>
            {/* Filters */}
            <div className="mb-6 space-y-4">
              {/* Status Filter */}
              <div>
                <label className="block text-sm font-medium mb-2">Filter by Status</label>
                <select
                  value={statusFilter}
                  onChange={(e) => {
                    setStatusFilter(e.target.value as any);
                    setOffset(0); // Reset to first page when changing filter
                  }}
                  className="px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                >
                  <option value="unassigned">Unassigned (needs character assignment)</option>
                  <option value="needs_review">Needs Review (AI flagged for human review)</option>
                  <option value="ready_to_process">Ready to Process (assigned, not processed)</option>
                  <option value="processed">Processed (live in database)</option>
                  <option value="archived">Archived (false positives)</option>
                  <option value="all">All Events</option>
                </select>
              </div>

              {/* Search/Filter Events */}
              <div>
                <label className="block text-sm font-medium mb-2">Search Events</label>
                <div className="relative">
                  <input
                    type="text"
                    value={eventFilter}
                    onChange={(e) => setEventFilter(e.target.value)}
                    placeholder="Filter by text, chapter, character, or type..."
                    className="w-full px-4 py-2 pl-10 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                  <div className="absolute left-3 top-1/2 -translate-y-1/2">
                    <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                  </div>
                  {eventFilter && (
                    <button
                      onClick={() => setEventFilter('')}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  )}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Events List */}
          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold">
                Events
                {eventFilter && total > 0 && (
                  <span className="text-sm text-gray-500 ml-2">
                    ({total} matching)
                  </span>
                )}
              </h2>
              <div className="text-sm text-gray-600">
                Showing {offset + 1}-{Math.min(offset + limit, total)} of {total}
              </div>
            </div>

            {/* Selection Controls */}
            {statusFilter === 'unassigned' && events.length > 0 && (
              <div className="mb-4 space-y-2">
                <div className="flex items-center justify-between p-3 bg-indigo-50 border border-indigo-200 rounded">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedEventIds.size === events.length && events.length > 0}
                      onChange={toggleSelectAll}
                      className="w-4 h-4 text-indigo-600"
                    />
                    <span className="text-sm font-medium">
                      Select All on Page
                    </span>
                  </label>
                  {selectedEventIds.size > 0 && (
                    <span className="text-sm font-semibold text-indigo-700">
                      {selectedEventIds.size} event{selectedEventIds.size !== 1 ? 's' : ''} selected
                    </span>
                  )}
                </div>
                {selectedEventIds.size > 0 && (
                  <button
                    onClick={archiveEvents}
                    className="w-full px-4 py-2 bg-orange-600 text-white rounded hover:bg-orange-700 text-sm font-medium"
                  >
                    Archive Selected ({selectedEventIds.size})
                  </button>
                )}
              </div>
            )}

            {/* Pagination Controls */}
            <div className="flex gap-2 mb-4">
              <button
                onClick={() => setOffset(Math.max(0, offset - limit))}
                disabled={offset === 0}
                className="px-4 py-2 bg-gray-200 text-gray-800 rounded hover:bg-gray-300 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Previous
              </button>
              <button
                onClick={() => setOffset(offset + limit)}
                disabled={offset + limit >= total}
                className="px-4 py-2 bg-gray-200 text-gray-800 rounded hover:bg-gray-300 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>

            {/* Process All Button (only for ready_to_process status) */}
            {statusFilter === 'ready_to_process' && events.length > 0 && (
              <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-green-900">
                      Batch Process
                    </p>
                    <p className="text-xs text-green-700 mt-0.5">
                      Process all {events.filter(e => e.is_assigned && !e.is_processed).length} event(s) on this page
                    </p>
                  </div>
                  <button
                    onClick={processAllEvents}
                    className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 font-medium"
                  >
                    Process All
                  </button>
                </div>
              </div>
            )}

            <div className="space-y-3 max-h-[600px] overflow-y-auto">
              {events.map((event) => (
                <div
                  key={event.id}
                  className={`border rounded-lg p-4 transition ${
                    selectedEvent?.id === event.id
                      ? 'border-blue-500 bg-blue-50'
                      : selectedEventIds.has(event.id)
                      ? 'border-indigo-500 bg-indigo-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    {/* Checkbox for multi-select (only for unassigned events) */}
                    {statusFilter === 'unassigned' && (
                      <input
                        type="checkbox"
                        checked={selectedEventIds.has(event.id)}
                        onChange={(e) => {
                          e.stopPropagation();
                          toggleEventSelection(event.id);
                        }}
                        className="mt-1 w-4 h-4 text-indigo-600 cursor-pointer"
                      />
                    )}

                    {/* Event content */}
                    <div className="flex-1 cursor-pointer" onClick={() => setSelectedEvent(event)}>
                      <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2">
                      {event.event_type ? (
                        <span
                          className={`px-2 py-1 rounded text-xs font-medium ${getEventTypeColor(
                            event.event_type
                          )}`}
                        >
                          {event.event_type.replace('_', ' ')}
                        </span>
                      ) : (
                        <span className="px-2 py-1 rounded text-xs font-medium bg-gray-100 text-gray-600">
                          unclassified
                        </span>
                      )}
                      <span className="text-xs text-gray-500">
                        #{event.event_index + 1} of {event.total_chapter_events}
                      </span>
                    </div>
                    <span className="text-sm text-gray-500">{event.chapter_number}</span>
                  </div>

                  <p className="text-sm font-mono mb-2">{event.raw_text}</p>

                  {event.parsed_data && (
                    <p className="text-xs text-gray-600">
                      {JSON.stringify(event.parsed_data)}
                    </p>
                  )}

                  {/* Context toggle and display */}
                  {event.context && (
                    <div className="mt-2">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleContext(event.id);
                        }}
                        className="text-xs text-indigo-600 hover:text-indigo-800 font-medium flex items-center gap-1"
                      >
                        {expandedContexts.has(event.id) ? '▼' : '▶'} Show Context
                      </button>
                      {expandedContexts.has(event.id) && (
                        <div className="mt-2 p-3 bg-gray-50 rounded border border-gray-200 text-xs text-gray-700 whitespace-pre-wrap max-h-40 overflow-y-auto">
                          {event.context}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Action buttons */}
                  <div className="mt-2 flex gap-2">
                    {!event.event_type && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setClassifyingEvent(event);
                          setClassificationType('');
                          setClassificationTitle('');
                        }}
                        className="text-xs px-2 py-1 bg-indigo-600 text-white hover:bg-indigo-700 rounded"
                      >
                        Classify
                      </button>
                    )}
                    {statusFilter === 'archived' ? (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          unarchiveEvent(event.id);
                        }}
                        className="text-xs px-2 py-1 bg-blue-600 text-white hover:bg-blue-700 rounded"
                      >
                        Unarchive
                      </button>
                    ) : statusFilter === 'unassigned' && !event.character_name ? (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          archiveEvent(event.id);
                        }}
                        className="text-xs px-2 py-1 bg-orange-600 text-white hover:bg-orange-700 rounded"
                      >
                        Archive
                      </button>
                    ) : null}
                  </div>

                  {event.character_name && (
                    <div className="mt-2">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium text-blue-600">
                          → {event.character_name}
                        </span>
                        {event.is_processed && (
                          <span className="text-xs px-2 py-0.5 bg-green-100 text-green-800 rounded font-medium">
                            ✓ Processed
                          </span>
                        )}
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            processEvent(event.id);
                          }}
                          disabled={event.is_processed}
                          className={`text-xs px-2 py-1 rounded ${
                            event.is_processed
                              ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                              : 'bg-green-600 text-white hover:bg-green-700'
                          }`}
                        >
                          Process
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            unassignEvent(event.id);
                          }}
                          className="text-xs px-2 py-1 text-red-600 hover:text-red-800"
                        >
                          Unassign
                        </button>
                      </div>
                    </div>
                  )}
                    </div>
                  </div>
                </div>
              ))}

              {events.length === 0 && (
                <p className="text-gray-500 text-center py-8">
                  {eventFilter ? 'No events match your search' : 'No events found'}
                </p>
              )}
            </div>
          </div>

          {/* Character Assignment */}
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4">Assign to Character</h2>

            {selectedEventIds.size === 0 && !selectedEvent ? (
              <p className="text-gray-500">
                {statusFilter === 'unassigned'
                  ? 'Select event(s) from the left to assign'
                  : 'Select an event from the left to assign it'}
              </p>
            ) : selectedEventIds.size > 0 ? (
              /* Bulk assignment mode */
              <div className="space-y-4">
                <div className="bg-indigo-50 p-4 rounded border border-indigo-200">
                  <p className="text-sm text-indigo-900 font-medium mb-1">
                    Bulk Assignment Mode
                  </p>
                  <p className="text-xs text-indigo-700">
                    Assigning {selectedEventIds.size} event{selectedEventIds.size !== 1 ? 's' : ''} to a character
                  </p>
                </div>

                {/* Search/Create Character */}
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Search or Create Character
                  </label>
                  <input
                    type="text"
                    value={searchTerm}
                    onChange={(e) => {
                      setSearchTerm(e.target.value);
                      searchCharacters(e.target.value);
                    }}
                    placeholder="Type character name..."
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                </div>

                {/* Character Results */}
                {characters.length > 0 && (
                  <div className="border rounded-md max-h-60 overflow-y-auto">
                    {characters.map((character) => (
                      <button
                        key={character.id}
                        onClick={() => assignEvent(character.id)}
                        className="w-full text-left px-4 py-2 hover:bg-gray-50 border-b last:border-b-0"
                      >
                        <div className="font-medium">{character.name}</div>
                        {character.aliases && character.aliases.length > 0 && (
                          <div className="text-xs text-gray-500">
                            Aliases: {character.aliases.join(', ')}
                          </div>
                        )}
                      </button>
                    ))}
                  </div>
                )}

                {/* Create New Character */}
                {searchTerm && characters.length === 0 && (
                  <div className="border-2 border-dashed border-gray-300 rounded-md p-4">
                    <p className="text-sm text-gray-600 mb-2">Character not found</p>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={newCharacterName}
                        onChange={(e) => setNewCharacterName(e.target.value)}
                        placeholder="New character name"
                        className="flex-1 px-3 py-2 border border-gray-300 rounded-md"
                      />
                      <button
                        onClick={createCharacter}
                        className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700"
                      >
                        Create
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : selectedEvent ? (
              /* Single assignment mode */
              <div className="space-y-4">
                <div className="bg-gray-50 p-4 rounded">
                  <p className="text-sm text-gray-600 mb-1">Selected Event:</p>
                  <p className="font-mono text-sm">{selectedEvent.raw_text}</p>
                  <p className="text-xs text-gray-500 mt-1">
                    {selectedEvent.chapter_number}
                    {selectedEvent.chapter_title && `: ${selectedEvent.chapter_title}`}
                  </p>
                </div>

                {/* Search/Create Character */}
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Search or Create Character
                  </label>
                  <input
                    type="text"
                    value={searchTerm}
                    onChange={(e) => {
                      setSearchTerm(e.target.value);
                      searchCharacters(e.target.value);
                    }}
                    placeholder="Type character name..."
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                </div>

                {/* Character Results */}
                {characters.length > 0 && (
                  <div className="border rounded-md max-h-60 overflow-y-auto">
                    {characters.map((character) => (
                      <button
                        key={character.id}
                        onClick={() => assignEvent(character.id)}
                        className="w-full text-left px-4 py-2 hover:bg-gray-50 border-b last:border-b-0"
                      >
                        <div className="font-medium">{character.name}</div>
                        {character.aliases && character.aliases.length > 0 && (
                          <div className="text-xs text-gray-500">
                            Aliases: {character.aliases.join(', ')}
                          </div>
                        )}
                      </button>
                    ))}
                  </div>
                )}

                {/* Create New Character */}
                {searchTerm && characters.length === 0 && (
                  <div className="border-2 border-dashed border-gray-300 rounded-md p-4">
                    <p className="text-sm text-gray-600 mb-2">Character not found</p>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={newCharacterName}
                        onChange={(e) => setNewCharacterName(e.target.value)}
                        placeholder="New character name"
                        className="flex-1 px-3 py-2 border border-gray-300 rounded-md"
                      />
                      <button
                        onClick={createCharacter}
                        className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700"
                      >
                        Create
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : null}
          </div>
        </div>
          </>
        )}

        {/* Characters Tab Content */}
        {activeTab === 'characters' && (
          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold">Character Management</h2>
              <div className="text-sm text-gray-600">
                {characterLoading ? 'Loading...' : `${allCharacters.length} characters`}
              </div>
            </div>

            {/* Search */}
            <div className="mb-4">
              <div className="relative">
                <input
                  type="text"
                  value={characterSearchTerm}
                  onChange={(e) => setCharacterSearchTerm(e.target.value)}
                  placeholder="Search characters by name..."
                  className="w-full px-4 py-2 pl-10 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
                <div className="absolute left-3 top-1/2 -translate-y-1/2">
                  <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                </div>
                {characterSearchTerm && (
                  <button
                    onClick={() => setCharacterSearchTerm('')}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                )}
              </div>
            </div>

            {/* Pagination */}
            <div className="flex gap-2 mb-4">
              <button
                onClick={() => setCharacterOffset(Math.max(0, characterOffset - characterLimit))}
                disabled={characterOffset === 0}
                className="px-4 py-2 bg-gray-200 text-gray-800 rounded hover:bg-gray-300 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Previous
              </button>
              <button
                onClick={() => setCharacterOffset(characterOffset + characterLimit)}
                disabled={allCharacters.length < characterLimit}
                className="px-4 py-2 bg-gray-200 text-gray-800 rounded hover:bg-gray-300 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>

            {/* Character List */}
            <div className="space-y-2 max-h-[600px] overflow-y-auto">
              {allCharacters.map((character) => (
                <div
                  key={character.id}
                  className="border rounded-lg p-4 hover:border-gray-300 cursor-pointer transition"
                  onClick={() => openCharacterEditor(character)}
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="font-medium text-lg">{character.name}</div>
                      {character.aliases && character.aliases.length > 0 && (
                        <div className="text-sm text-gray-500 mt-1">
                          Aliases: {character.aliases.join(', ')}
                        </div>
                      )}
                      {character.notes && (
                        <div className="text-sm text-gray-600 mt-1 line-clamp-2">
                          {character.notes}
                        </div>
                      )}
                    </div>
                    <div className="text-xs text-gray-400">
                      ID: {character.id}
                    </div>
                  </div>
                </div>
              ))}

              {allCharacters.length === 0 && !characterLoading && (
                <p className="text-gray-500 text-center py-8">
                  {characterSearchTerm ? 'No characters match your search' : 'No characters found'}
                </p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Character Edit Modal */}
      {editingCharacter && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold">Edit Character</h2>
              <button
                onClick={closeCharacterEditor}
                className="text-gray-400 hover:text-gray-600"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="space-y-4">
              {/* Name */}
              <div>
                <label className="block text-sm font-medium mb-2">Name *</label>
                <input
                  type="text"
                  value={characterFormData.name}
                  onChange={(e) => setCharacterFormData({ ...characterFormData, name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>

              {/* Aliases */}
              <div>
                <label className="block text-sm font-medium mb-2">Aliases</label>
                <div className="flex flex-wrap gap-2 mb-2">
                  {characterFormData.aliases.map((alias, index) => (
                    <span
                      key={index}
                      className="inline-flex items-center gap-1 px-3 py-1 bg-gray-100 text-gray-800 rounded-full text-sm"
                    >
                      {alias}
                      <button
                        onClick={() => removeAlias(alias)}
                        className="text-gray-500 hover:text-red-500"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </span>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newAliasInput}
                    onChange={(e) => setNewAliasInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        addAlias();
                      }
                    }}
                    placeholder="Add alias..."
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                  <button
                    onClick={addAlias}
                    disabled={!newAliasInput.trim()}
                    className="px-4 py-2 bg-gray-200 text-gray-800 rounded-md hover:bg-gray-300 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Add
                  </button>
                </div>
              </div>

              {/* First Appearance Chapter */}
              <div>
                <label className="block text-sm font-medium mb-2">First Appearance Chapter</label>
                <select
                  value={characterFormData.first_appearance_chapter_id || ''}
                  onChange={(e) => setCharacterFormData({
                    ...characterFormData,
                    first_appearance_chapter_id: e.target.value ? parseInt(e.target.value) : null
                  })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                >
                  <option value="">Not set</option>
                  {chapters.map((chapter) => (
                    <option key={chapter.id} value={chapter.id}>
                      {chapter.chapter_number}{chapter.title ? `: ${chapter.title}` : ''}
                    </option>
                  ))}
                </select>
              </div>

              {/* Notes */}
              <div>
                <label className="block text-sm font-medium mb-2">Notes</label>
                <textarea
                  value={characterFormData.notes}
                  onChange={(e) => setCharacterFormData({ ...characterFormData, notes: e.target.value })}
                  rows={4}
                  placeholder="Add notes about this character..."
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>

              {/* Meta Info */}
              <div className="text-xs text-gray-500 pt-2 border-t">
                <p>Character ID: {editingCharacter.id}</p>
                <p>Created: {new Date(editingCharacter.created_at).toLocaleString()}</p>
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-3 mt-6">
              <button
                onClick={saveCharacter}
                disabled={!characterFormData.name.trim()}
                className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Save Changes
              </button>
              <button
                onClick={() => deleteCharacter(editingCharacter.id, editingCharacter.name)}
                className="px-4 py-2 bg-red-100 text-red-700 rounded-md hover:bg-red-200"
              >
                Delete
              </button>
              <button
                onClick={closeCharacterEditor}
                className="px-4 py-2 bg-gray-200 text-gray-800 rounded-md hover:bg-gray-300"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Classification Modal */}
      {classifyingEvent && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-2xl w-full mx-4">
            <h2 className="text-xl font-semibold mb-4">Classify Event</h2>

            {/* Event Info */}
            <div className="bg-gray-50 p-4 rounded mb-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-500">
                  Chapter {classifyingEvent.chapter_number} - Event #{classifyingEvent.event_index + 1} of {classifyingEvent.total_chapter_events}
                </span>
              </div>
              <p className="font-mono text-sm mb-2">{classifyingEvent.raw_text}</p>
              {classifyingEvent.surrounding_text && (
                <details className="mt-2">
                  <summary className="text-xs text-indigo-600 cursor-pointer">Show Context</summary>
                  <p className="text-xs text-gray-600 mt-2 whitespace-pre-wrap">{classifyingEvent.surrounding_text}</p>
                </details>
              )}
            </div>

            {/* Classification Form */}
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Event Type *</label>
                <select
                  value={classificationType}
                  onChange={(e) => setClassificationType(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                >
                  <option value="">Select event type...</option>
                  <option value="class_obtained">Class Obtained</option>
                  <option value="class_evolution">Class Evolution</option>
                  <option value="class_consolidation">Class Consolidation</option>
                  <option value="class_removed">Class Removed</option>
                  <option value="level_up">Level Up</option>
                  <option value="ability_obtained">Ability Obtained (Skill/Spell/Song/Condition/etc)</option>
                  <option value="ability_removed">Ability Removed</option>
                  <option value="other">Other</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Title/Details {classificationType && '(optional)'}
                </label>
                <input
                  type="text"
                  value={classificationTitle}
                  onChange={(e) => setClassificationTitle(e.target.value)}
                  placeholder="e.g., Innkeeper, Level 20, Minotaur's Punch, etc."
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Optional: Add specific details like class name, level number, skill name, etc.
                </p>
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-3 mt-6">
              <button
                onClick={classifyEvent}
                disabled={!classificationType}
                className="flex-1 px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Save Classification
              </button>
              <button
                onClick={() => {
                  setClassifyingEvent(null);
                  setClassificationType('');
                  setClassificationTitle('');
                }}
                className="px-4 py-2 bg-gray-200 text-gray-800 rounded-md hover:bg-gray-300"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
