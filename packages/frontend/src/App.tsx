import { useState, useEffect, useCallback } from 'react'
import type { Message, Media, User } from './types'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface EditableFieldProps {
  media: Media;
  fieldName: 'description' | 'transcription';
  onUpdate: (updatedMedia: Media) => void;
}
function EditableField({ media, fieldName, onUpdate }: EditableFieldProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [text, setText] = useState(media[fieldName] || "");
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const label = fieldName.charAt(0).toUpperCase() + fieldName.slice(1);
  const hasText = text !== null && text.length > 0;
  useEffect(() => {
    setText(media[fieldName] || "");
  }, [media, fieldName]);
  const handleSave = async () => {
    try {
      const response = await fetch(`${API_URL}/media/${media.id}/${fieldName}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [fieldName]: text }),
      });
      if (!response.ok) throw new Error('Failed to save');
      const updatedMedia: Media = await response.json();
      onUpdate(updatedMedia);
      setIsEditing(false);
      setError(null);
    } catch (err: any) {
      setError(err.message);
    }
  };
  const handleGenerate = async () => {
    setIsGenerating(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/media/${media.id}/generate-${fieldName}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: prompt }),
      });
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to generate');
      }
      const updatedMedia: Media = await response.json();
      onUpdate(updatedMedia);
      setPrompt("");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsGenerating(false);
    }
  };
  return (
    <div className="bg-gray-50 p-3 rounded-lg border">
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      {error && <div className="text-sm text-red-500 mb-2">Error: {error}</div>}
      {isEditing ? (
        <div className="flex flex-col gap-2">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="w-full p-2 border border-gray-300 rounded-md shadow-sm text-sm"
            rows={3}
          />
          <div className="flex gap-2">
            <button onClick={handleSave} className="px-3 py-1 bg-blue-600 text-white rounded-md text-sm hover:bg-blue-700">Save</button>
            <button onClick={() => setIsEditing(false)} className="px-3 py-1 bg-gray-300 text-gray-800 rounded-md text-sm hover:bg-gray-400">Cancel</button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <p className="text-sm text-gray-800 whitespace-pre-wrap flex-1">
            {hasText ? text : <i className="text-gray-400">No {fieldName} yet.</i>}
          </p>
          <div className="flex items-center gap-2">
            {!hasText && (
              <>
                <input
                  type="text"
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Optional: Custom prompt..."
                  className="flex-1 p-2 border border-gray-300 rounded-md shadow-sm text-sm"
                />
                <button
                  onClick={handleGenerate}
                  disabled={isGenerating}
                  className="px-3 py-2 bg-green-600 text-white rounded-md text-sm hover:bg-green-700 disabled:bg-gray-400"
                >
                  {isGenerating ? '...' : 'Generate'}
                </button>
              </>
            )}
            {hasText && (
              <button
                onClick={() => setIsEditing(true)}
                className="px-3 py-1 bg-gray-300 text-gray-800 rounded-md text-sm hover:bg-gray-400"
              >
                Edit
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function MediaItem({ media, onUpdate }: { media: Media; onUpdate: (updatedMedia: Media) => void; }) {
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const fetchMediaUrl = async () => {
      if (media.media_type === 'location') {
        setUrl(`https://maps.google.com/?q=${media.latitude},${media.longitude}`);
        setLoading(false);
        return;
      }
      if (!media.file_path) {
        setLoading(false);
        return;
      }
      try {
        const response = await fetch(`${API_URL}/media-url?key=${encodeURIComponent(media.file_path)}`);
        const data = await response.json();
        if (response.ok) setUrl(data.url);
      } catch (error) {
        console.error("Failed to fetch media URL", error);
      } finally {
        setLoading(false);
      }
    };
    fetchMediaUrl();
  }, [media.file_path, media.latitude, media.longitude, media.media_type]);
  const renderMedia = () => {
    if (loading) return <div className="text-sm text-gray-500 italic animate-pulse">Loading media...</div>;
    if (!url) return <div className="text-sm text-red-500">Could not load media.</div>;
    switch (media.media_type) {
      case 'photo':
      case 'sticker':
        return <img src={url} alt={media.file_name || 'photo'} className="max-w-full h-auto rounded-lg border border-gray-200" />;
      case 'video':
        return <video controls src={url} className="max-w-full rounded-lg border border-gray-200" />;
      case 'audio':
      case 'voice':
        return <audio controls src={url} className="w-full" />;
      case 'location':
        return <a href={url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">View Location ({media.latitude}, {media.longitude})</a>;
      default:
        return <a href={url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">Download {media.file_name || media.media_type}</a>;
    }
  }
  return (
    <div className="flex flex-col gap-2">
      {renderMedia()}
      {['photo', 'sticker'].includes(media.media_type) && (
        <EditableField media={media} fieldName="description" onUpdate={onUpdate} />
      )}
      {['audio', 'voice'].includes(media.media_type) && (
        <EditableField media={media} fieldName="transcription" onUpdate={onUpdate} />
      )}
    </div>
  )
}

// --- Main App Component ---
function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedUser, setSelectedUser] = useState<string>("")
  const [startDate, setStartDate] = useState<string>("")
  const [endDate, setEndDate] = useState<string>("")

  const fetchMessages = useCallback(async (user: string, start: string, end: string) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (user) params.append("telegram_user_id", user);
      if (start) params.append("start_date", new Date(start).toISOString());
      if (end) params.append("end_date", new Date(end).toISOString());
      
      const queryString = params.toString();
      const response = await fetch(`${API_URL}/messages?${queryString}`);
      
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || `HTTP error! status: ${response.status}`);
      }
      
      const data: Message[] = await response.json();
      setMessages(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []); 

  useEffect(() => {
    const fetchInitialData = async () => {
      try {
        const userResponse = await fetch(`${API_URL}/users`);
        if (!userResponse.ok) throw new Error('Failed to fetch users');
        const userData: User[] = await userResponse.json();
        setUsers(userData);
      } catch (e: any) {
        setError(e.message);
      }
      fetchMessages("", "", "");
    }
    fetchInitialData();
  }, [fetchMessages]); 
  
  
  const handleMediaUpdated = (updatedMedia: Media) => {
    setMessages(currentMessages => {
      return currentMessages.map(msg => {
        if (msg.id === updatedMedia.message_id) {
          return {
            ...msg,
            media: msg.media.map(m => m.id === updatedMedia.id ? updatedMedia : m)
          };
        }
        return msg;
      });
    });
  };

  const handleFilterSubmit = () => {
    fetchMessages(selectedUser, startDate, endDate);
  }

  const handleClearFilters = () => {
    setSelectedUser("");
    setStartDate("");
    setEndDate("");
    fetchMessages("", "", ""); // Fetch with cleared filters
  }

  return (
    <div className="max-w-3xl mx-auto p-5 font-sans">
      <h1 className="text-3xl font-bold text-center text-white mb-8">
        Field Notes
      </h1>
      
      {/* Filter Bar */}
      <div className="bg-gray-100 p-4 rounded-lg mb-6 shadow-sm text-black">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label htmlFor="user-filter" className="block text-sm font-medium text-gray-700">User</label>
            <select
              id="user-filter"
              value={selectedUser}
              onChange={(e) => setSelectedUser(e.target.value)}
              className="mt-1 block w-full p-2 border border-gray-300 rounded-md shadow-sm"
            >
              <option value="">All Users</option>
              {users.map((user) => (
                <option key={user.id} value={user.telegram_user_id}>
                  {user.first_name} {user.last_name || ''}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="start-date" className="block text-sm font-medium text-gray-700">Start Date</label>
            <input
              type="datetime-local"
              id="start-date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="mt-1 block w-full p-2 border border-gray-300 rounded-md shadow-sm"
            />
          </div>
          <div>
            <label htmlFor="end-date" className="block text-sm font-medium text-gray-700">End Date</label>
            <input
              type="datetime-local"
              id="end-date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="mt-1 block w-full p-2 border border-gray-300 rounded-md shadow-sm"
            />
          </div>
        </div>
        <div className="flex gap-4 mt-4">
          <button
            onClick={handleFilterSubmit}
            className="w-full bg-blue-600 text-white p-2 rounded-md hover:bg-blue-700"
          >
            Apply Filters
          </button>
          <button
            onClick={handleClearFilters}
            className="w-full bg-gray-300 text-gray-800 p-2 rounded-md hover:bg-gray-400"
          >
            Clear Filters
          </button>
        </div>
      </div>
      

      {/* Message List */}
      {loading && <h2 className="text-xl font-bold text-center animate-pulse">Loading...</h2>}
      {error && <h2 className="text-xl font-bold text-center text-red-600">Error: {error}</h2>}
      
      {!loading && !error && (
        <div className="flex flex-col gap-4">
          {messages.length === 0 && (
            <div className="text-center text-gray-500 text-lg">
              No messages found.
            </div>
          )}
          {messages.map((msg) => (
            <div key={msg.id} className="bg-white shadow-md rounded-lg p-4 border border-gray-200 text-black">
              <div className="flex justify-between items-center border-b border-gray-200 pb-2 mb-3">
                <strong className="text-lg font-semibold text-blue-600">
                  {msg.user?.first_name || 'Unknown User'}
                </strong>
                <span className="text-sm text-gray-500">
                  {new Date(msg.timestamp).toLocaleString()}
                </span>
              </div>
              {msg.text && (
                <p className="text-base text-gray-800 my-2 whitespace-pre-wrap">{msg.text}</p>
              )}
              {msg.media.length > 0 && (
                <div className="mt-3 pt-3 border-t border-gray-200 border-dashed flex flex-col gap-4">
                  {msg.media.map((item) => (
                    <MediaItem key={item.id} media={item} onUpdate={handleMediaUpdated} />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      

    </div>
  )
}

export default App