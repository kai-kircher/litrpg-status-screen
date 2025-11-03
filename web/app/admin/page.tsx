'use client';

import { useState, useEffect } from 'react';

type RawEvent = {
  id: number;
  event_type: string;
  raw_text: string;
  parsed_data: any;
  context: string;
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
  created_at: string;
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
  const [statusFilter, setStatusFilter] = useState<'unassigned' | 'ready_to_process' | 'processed' | 'archived' | 'all'>('unassigned');
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const limit = 100;

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
      } else if (statusFilter === 'ready_to_process') {
        url += '&assigned=true&processed=false';
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

  const getEventTypeColor = (type: string) => {
    switch (type) {
      case 'class_obtained':
        return 'bg-purple-100 text-purple-800';
      case 'level_up':
        return 'bg-blue-100 text-blue-800';
      case 'skill_obtained':
        return 'bg-green-100 text-green-800';
      case 'spell_obtained':
        return 'bg-yellow-100 text-yellow-800';
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
        <h1 className="text-3xl font-bold mb-6">Event Assignment Admin</h1>

        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
            {error}
          </div>
        )}

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
              <option value="ready_to_process">Ready to Process (assigned but not processed)</option>
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
                    <span
                      className={`px-2 py-1 rounded text-xs font-medium ${getEventTypeColor(
                        event.event_type
                      )}`}
                    >
                      {event.event_type.replace('_', ' ')}
                    </span>
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
      </div>
    </div>
  );
}
