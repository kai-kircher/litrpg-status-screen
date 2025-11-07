'use client';

import { useState, useEffect } from 'react';

type Character = {
  id: number;
  name: string;
};

type Chapter = {
  id: number;
  order_index: number;
  chapter_number: string;
};

type Ability = {
  name: string;
  type: string;
};

type ProgressionEvent = {
  order_index: number;
  chapter_number: string;
  classes: { name: string; level: number | null }[];
  skills: Ability[];
  spells: string[];
};

type CharacterSummary = {
  classes: { class_name: string; level: number | null; chapter_number: string }[];
  skills: Ability[];
  spells: string[];
};

export default function Home() {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedCharacter, setSelectedCharacter] = useState<number | null>(null);
  const [maxChapter, setMaxChapter] = useState<number | null>(null);
  const [progression, setProgression] = useState<ProgressionEvent[]>([]);
  const [summary, setSummary] = useState<CharacterSummary | null>(null);
  const [viewMode, setViewMode] = useState<'timeline' | 'summary'>('summary');
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(false);

  // Load characters on mount
  useEffect(() => {
    loadCharacters();
    loadChapters();
  }, []);

  // Load data when character, chapter, or view mode changes
  useEffect(() => {
    if (selectedCharacter) {
      if (viewMode === 'timeline') {
        loadProgression();
      } else {
        loadSummary();
      }
    }
  }, [selectedCharacter, maxChapter, viewMode]);

  const loadCharacters = async () => {
    try {
      const response = await fetch('/api/characters');
      const data = await response.json();
      setCharacters(data);
    } catch (err) {
      console.error('Error loading characters:', err);
    }
  };

  const loadChapters = async () => {
    try {
      const response = await fetch('/api/chapters');
      const data = await response.json();
      setChapters(data);
    } catch (err) {
      console.error('Error loading chapters:', err);
    }
  };

  const loadProgression = async () => {
    if (!selectedCharacter) return;

    setLoading(true);
    try {
      const url = maxChapter
        ? `/api/progression?characterId=${selectedCharacter}&maxOrderIndex=${maxChapter}`
        : `/api/progression?characterId=${selectedCharacter}`;

      const response = await fetch(url);
      const data = await response.json();
      setProgression(data);
    } catch (err) {
      console.error('Error loading progression:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadSummary = async () => {
    if (!selectedCharacter) return;

    setLoading(true);
    try {
      const url = maxChapter
        ? `/api/character-summary?characterId=${selectedCharacter}&maxOrderIndex=${maxChapter}`
        : `/api/character-summary?characterId=${selectedCharacter}`;

      const response = await fetch(url);
      const data = await response.json();
      setSummary(data);
    } catch (err) {
      console.error('Error loading summary:', err);
    } finally {
      setLoading(false);
    }
  };

  const filteredProgression = progression.filter((event) => {
    if (!filter) return true;
    const searchLower = filter.toLowerCase();
    return (
      event.chapter_number.toLowerCase().includes(searchLower) ||
      event.classes.some((c) => c.name.toLowerCase().includes(searchLower)) ||
      event.skills.some((s) => s.name.toLowerCase().includes(searchLower))
    );
  });

  // Helper function to get badge styling and label based on ability type
  const getAbilityBadge = (type: string) => {
    switch (type) {
      case 'spell':
      case 'spell_obtained':
        return { label: 'SPELL', bgColor: 'bg-blue-900/20', borderColor: 'border-blue-800/40', badgeColor: 'bg-blue-700' };
      case 'condition':
        return { label: 'CONDITION', bgColor: 'bg-orange-900/20', borderColor: 'border-orange-800/40', badgeColor: 'bg-orange-700' };
      case 'aspect':
        return { label: 'ASPECT', bgColor: 'bg-pink-900/20', borderColor: 'border-pink-800/40', badgeColor: 'bg-pink-700' };
      case 'title':
        return { label: 'TITLE', bgColor: 'bg-indigo-900/20', borderColor: 'border-indigo-800/40', badgeColor: 'bg-indigo-700' };
      case 'rank':
        return { label: 'RANK', bgColor: 'bg-cyan-900/20', borderColor: 'border-cyan-800/40', badgeColor: 'bg-cyan-700' };
      case 'other':
        return { label: 'OTHER', bgColor: 'bg-slate-900/20', borderColor: 'border-slate-800/40', badgeColor: 'bg-slate-700' };
      case 'skill_obtained':
      case 'skill_change':
      default:
        return { label: 'SKILL', bgColor: 'bg-green-900/20', borderColor: 'border-green-800/40', badgeColor: 'bg-green-700' };
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <div className="bg-indigo-900 py-6 shadow-lg border-b border-indigo-800">
        <div className="max-w-4xl mx-auto px-4">
          <h1 className="text-3xl font-bold text-center text-white">
            LitRPG Status Screen
          </h1>
          <p className="text-center text-indigo-200 mt-1 text-sm">
            A Chapter-by-Chapter LitRPG Character Progression Tracker
          </p>
        </div>
      </div>

      {/* Controls */}
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="bg-gray-800 rounded-lg shadow-lg border border-gray-700 p-6 space-y-4">
          {/* Series Title */}
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <label className="bg-gray-700 text-white px-4 py-2 font-medium rounded sm:min-w-[140px] text-sm">
              Series:
            </label>
            <div className="flex-1 relative">
              <select className="w-full bg-gray-900 border border-gray-600 rounded px-4 py-2 text-white appearance-none cursor-pointer hover:border-indigo-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-colors">
                <option>The Wandering Inn</option>
              </select>
              <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none">
                <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </div>
            </div>
          </div>

          {/* Character */}
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <label className="bg-gray-700 text-white px-4 py-2 font-medium rounded sm:min-w-[140px] text-sm">
              Character:
            </label>
            <div className="flex-1 relative">
              <select
                className="w-full bg-gray-900 border border-gray-600 rounded px-4 py-2 text-white appearance-none cursor-pointer hover:border-indigo-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-colors"
                value={selectedCharacter || ''}
                onChange={(e) => setSelectedCharacter(Number(e.target.value) || null)}
              >
                <option value="">Select a character...</option>
                {characters.map((char) => (
                  <option key={char.id} value={char.id}>
                    {char.name}
                  </option>
                ))}
              </select>
              <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none">
                <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </div>
            </div>
          </div>

          {/* Chapter */}
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <label className="bg-gray-700 text-white px-4 py-2 font-medium rounded sm:min-w-[140px] text-sm">
              Max Chapter:
            </label>
            <div className="flex-1 relative">
              <select
                className="w-full bg-gray-900 border border-gray-600 rounded px-4 py-2 text-white appearance-none cursor-pointer hover:border-indigo-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-colors"
                value={maxChapter || ''}
                onChange={(e) => setMaxChapter(Number(e.target.value) || null)}
              >
                <option value="">All chapters (spoilers!)</option>
                {chapters.map((ch) => (
                  <option key={ch.id} value={ch.order_index}>
                    {ch.chapter_number}
                  </option>
                ))}
              </select>
              <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none">
                <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </div>
            </div>
          </div>

          {/* View Mode Toggle */}
          {selectedCharacter && (
            <div className="flex items-center justify-center gap-2 pt-2">
              <button
                onClick={() => setViewMode('timeline')}
                className={`px-4 py-2 rounded font-medium transition-colors ${
                  viewMode === 'timeline'
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                }`}
              >
                Timeline View
              </button>
              <button
                onClick={() => setViewMode('summary')}
                className={`px-4 py-2 rounded font-medium transition-colors ${
                  viewMode === 'summary'
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                }`}
              >
                Summary View
              </button>
            </div>
          )}

          {/* Filter/Search */}
          <div className="pt-1">
            <div className="relative">
              <input
                type="text"
                placeholder="Filter by chapter, class, or skill..."
                className="w-full bg-gray-900 border border-gray-600 rounded px-4 py-2 pl-10 text-white placeholder-gray-400 hover:border-indigo-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-colors"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
              <div className="absolute left-3 top-1/2 -translate-y-1/2">
                <svg
                  className="w-4 h-4 text-gray-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                  />
                </svg>
              </div>
              {filter && (
                <button
                  onClick={() => setFilter('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Results */}
      <div className="max-w-4xl mx-auto px-4 pb-12">
        {loading && (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500 mx-auto mb-3"></div>
            <p className="text-gray-400">Loading progression...</p>
          </div>
        )}

        {!loading && !selectedCharacter && (
          <div className="bg-gray-800 rounded-lg border border-gray-700 p-8 text-center">
            <svg className="w-16 h-16 mx-auto mb-3 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
            <p className="text-gray-400">Select a character to view their progression</p>
          </div>
        )}

        {!loading && selectedCharacter && viewMode === 'timeline' && filteredProgression.length === 0 && (
          <div className="bg-gray-800 rounded-lg border border-gray-700 p-8 text-center">
            <p className="text-gray-400">No progression data found</p>
            <p className="text-gray-500 text-sm mt-1">Try selecting a different character or adjusting your filters</p>
          </div>
        )}

        {/* Timeline View */}
        {!loading && viewMode === 'timeline' && filteredProgression.length > 0 && (
          <div className="space-y-4">
            {filteredProgression.map((event, idx) => (
              <div
                key={idx}
                className="bg-gray-800 rounded-lg border border-gray-700 p-5 hover:border-gray-600 transition-colors"
              >
                <h3 className="text-xl font-bold mb-3 text-indigo-300 flex items-center gap-2">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                  </svg>
                  Chapter {event.chapter_number}
                </h3>

                <div className="space-y-2">
                  {event.classes.map((cls, clsIdx) => (
                    <div
                      key={clsIdx}
                      className="flex items-center gap-2 bg-purple-900/20 border border-purple-800/40 rounded px-3 py-2"
                    >
                      <span className="inline-flex items-center gap-1 bg-purple-700 text-white text-xs font-semibold px-2 py-0.5 rounded">
                        CLASS
                      </span>
                      <span className="text-white font-medium">{cls.name}</span>
                      {cls.level !== null && (
                        <span className="ml-auto text-purple-300 font-semibold">Level {cls.level}</span>
                      )}
                    </div>
                  ))}

                  {event.skills.map((skill, skillIdx) => {
                    const badge = getAbilityBadge(skill.type);
                    return (
                      <div
                        key={skillIdx}
                        className={`flex items-center gap-2 ${badge.bgColor} border ${badge.borderColor} rounded px-3 py-2`}
                      >
                        <span className={`inline-flex items-center gap-1 ${badge.badgeColor} text-white text-xs font-semibold px-2 py-0.5 rounded`}>
                          {badge.label}
                        </span>
                        <span className="text-white">{skill.name}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Summary View */}
        {!loading && viewMode === 'summary' && summary && (
          <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
            {/* Classes Section */}
            {summary.classes.length > 0 && (
              <div className="mb-6">
                <h3 className="text-2xl font-bold mb-4 text-indigo-300">Classes</h3>
                <div className="space-y-2">
                  {summary.classes.map((cls, idx) => (
                    <div
                      key={idx}
                      className="flex items-center gap-2 bg-purple-900/20 border border-purple-800/40 rounded px-4 py-3"
                    >
                      <span className="inline-flex items-center gap-1 bg-purple-700 text-white text-xs font-semibold px-2 py-0.5 rounded">
                        CLASS
                      </span>
                      <span className="text-white font-medium text-lg">{cls.class_name}</span>
                      {cls.level !== null && (
                        <span className="ml-auto text-purple-300 font-semibold text-lg">Level {cls.level}</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Skills Section */}
            {summary.skills.length > 0 && (
              <div className="mb-6">
                <h3 className="text-2xl font-bold mb-4 text-indigo-300">Skills</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {summary.skills.map((skill, idx) => {
                    const badge = getAbilityBadge(skill.type);
                    return (
                      <div
                        key={idx}
                        className={`flex items-center gap-2 ${badge.bgColor} border ${badge.borderColor} rounded px-3 py-2`}
                      >
                        <span className={`inline-flex items-center gap-1 ${badge.badgeColor} text-white text-xs font-semibold px-2 py-0.5 rounded`}>
                          {badge.label}
                        </span>
                        <span className="text-white">{skill.name}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Empty state */}
            {summary.classes.length === 0 && summary.skills.length === 0 && (
              <div className="text-center py-8">
                <p className="text-gray-400">No progression data found</p>
                <p className="text-gray-500 text-sm mt-1">Try selecting a different character or chapter range</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer with Buy Me a Coffee */}
      <div className="max-w-4xl mx-auto px-4 pb-8">
        <div className="text-center">
          <a href="https://www.buymeacoffee.com/kaitane" target="_blank" rel="noopener noreferrer">
            <img
              src="https://img.buymeacoffee.com/button-api/?text=Buy me a coffee&emoji=&slug=kaitane&button_colour=BD5FFF&font_colour=ffffff&font_family=Cookie&outline_colour=000000&coffee_colour=FFDD00"
              alt="Buy Me A Coffee"
              className="inline-block"
            />
          </a>
        </div>
      </div>
    </div>
  );
}
