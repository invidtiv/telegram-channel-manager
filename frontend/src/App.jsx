import React, { useState, useEffect } from 'react';
import './App.css';
import ChannelList from './components/ChannelList.jsx';
import TagManager from './components/TagManager.jsx';
import IngestionPanel from './components/IngestionPanel.jsx';
import BotRegistry from './components/BotRegistry.jsx';

function App() {
  const [activeTab, setActiveTab] = useState('channels');
  const [tags, setTags] = useState([]);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const fetchTags = async () => {
    try {
      const response = await fetch('/api/tags');
      if (response.ok) {
        const data = await response.json();
        setTags(data);
      }
    } catch (error) {
      console.error('Error fetching tags:', error);
    }
  };

  useEffect(() => {
    fetchTags();
  }, [refreshTrigger]);

  const handleRefresh = () => {
    setRefreshTrigger(prev => prev + 1);
  };

  return (
    <div className="app dark-mode">
      <header className="app-header">
        <div className="header-content">
          <div className="header-title">
            <svg className="header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            <div>
              <h1>Telegram Channel Manager</h1>
              <p className="header-subtitle">Organize and tag your channels</p>
            </div>
          </div>

          <nav className="nav-tabs">
            <button
              className={`nav-tab ${activeTab === 'channels' ? 'active' : ''}`}
              onClick={() => setActiveTab('channels')}
            >
              <svg viewBox="0 0 20 20" fill="currentColor">
                <path d="M2 5a2 2 0 012-2h7a2 2 0 012 2v4a2 2 0 01-2 2H9l-3 3v-3H4a2 2 0 01-2-2V5z" />
                <path d="M15 7v2a4 4 0 01-4 4H9.828l-1.766 1.767c.28.149.599.233.938.233h2l3 3v-3h2a2 2 0 002-2V9a2 2 0 00-2-2h-1z" />
              </svg>
              Channels
            </button>
            <button
              className={`nav-tab ${activeTab === 'bots' ? 'active' : ''}`}
              onClick={() => setActiveTab('bots')}
            >
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.38-1 1.72v1.78h3c.55 0 1 .45 1 1v7c0 .55-.45 1-1 1H7c-.55 0-1-.45-1-1V8.5c0-.55.45-1 1-1h3V5.72c-.6-.34-1-.98-1-1.72a2 2 0 0 1 2-2h1zm-1 12h2v2h-2v-2zm-4 0h2v2H7v-2zm8 0h2v2h-2v-2z" />
              </svg>
              Bots
            </button>
            <button
              className={`nav-tab ${activeTab === 'tags' ? 'active' : ''}`}
              onClick={() => setActiveTab('tags')}
            >
              <svg viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M17.707 9.293a1 1 0 010 1.414l-7 7a1 1 0 01-1.414 0l-7-7A.997.997 0 012 10V5a3 3 0 013-3h5c.256 0 .512.098.707.293l7 7zM5 6a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
              </svg>
              Tags
            </button>
            <button
              className={`nav-tab ${activeTab === 'ingest' ? 'active' : ''}`}
              onClick={() => setActiveTab('ingest')}
            >
              <svg viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
              Ingestion
            </button>
          </nav>
        </div>
      </header>

      <main className="app-main">
        {activeTab === 'channels' && (
          <ChannelList
            tags={tags}
            onTagsChange={handleRefresh}
          />
        )}
        {activeTab === 'bots' && (
          <BotRegistry />
        )}
        {activeTab === 'tags' && (
          <TagManager
            tags={tags}
            onTagsChange={handleRefresh}
          />
        )}
        {activeTab === 'ingest' && (
          <IngestionPanel onIngestionComplete={handleRefresh} />
        )}
      </main>
    </div>
  );
}

export default App;
