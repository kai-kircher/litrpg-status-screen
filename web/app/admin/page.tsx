'use client';

import { useState, useEffect } from 'react';

type RawEvent = {
  id: number;
  event_type: string;
  raw_text: string;
  parsed_data: any;
  context: string;
  is_assigned: boolean;
  character_id: number | null;
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
  const [searchTerm, setSearchTerm] = useState('');
  const [newCharacterName, setNewCharacterName] = useState('');
  const [loading, setLoading] = useState(true);
  const [showAssigned, setShowAssigned] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const limit = 100;

  useEffect(() => {
    loadEvents();
  }, [showAssigned, offset]);

  const loadEvents = async () => {
    try {
      const response = await fetch(`/api/admin/events?assigned=${showAssigned}&limit=${limit}&offset=${offset}`);
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
      setCharacters([]);
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

  const assignEvent = async (characterId: number) => {
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

        {/* Toggle */}
        <div className="mb-6">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={showAssigned}
              onChange={(e) => {
                setShowAssigned(e.target.checked);
                setOffset(0); // Reset to first page when toggling
              }}
              className="w-4 h-4"
            />
            <span>Show assigned events</span>
          </label>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Events List */}
          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold">
                {showAssigned ? 'Assigned Events' : 'Unassigned Events'} ({total})
              </h2>
              <div className="text-sm text-gray-600">
                Showing {offset + 1}-{Math.min(offset + limit, total)} of {total}
              </div>
            </div>

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

            <div className="space-y-3 max-h-[600px] overflow-y-auto">
              {events.map((event) => (
                <div
                  key={event.id}
                  className={`border rounded-lg p-4 cursor-pointer transition ${
                    selectedEvent?.id === event.id
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                  onClick={() => setSelectedEvent(event)}
                >
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

                  {event.character_name && (
                    <div className="mt-2 flex items-center justify-between">
                      <span className="text-sm font-medium text-blue-600">
                        → {event.character_name}
                      </span>
                      <div className="flex gap-2">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            processEvent(event.id);
                          }}
                          className="text-xs px-2 py-1 bg-green-600 text-white rounded hover:bg-green-700"
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
              ))}

              {events.length === 0 && (
                <p className="text-gray-500 text-center py-8">
                  {showAssigned ? 'No assigned events' : 'No unassigned events'}
                </p>
              )}
            </div>
          </div>

          {/* Character Assignment */}
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4">Assign to Character</h2>

            {!selectedEvent ? (
              <p className="text-gray-500">Select an event from the left to assign it</p>
            ) : (
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
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
