import React, { useState, useEffect } from 'react';
import MemberList from './MemberList.jsx';

function ChannelList({ tags, onTagsChange }) {
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedTags, setSelectedTags] = useState([]);
  const [memberChannel, setMemberChannel] = useState(null);

  const fetchChannels = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (selectedTags.length > 0) {
        params.append('tag_ids', selectedTags.join(','));
      }
      const trimmedSearch = search.trim();
      if (trimmedSearch) {
        params.append('search', trimmedSearch);
      }

      const response = await fetch(`/api/channels?${params}`);
      if (response.ok) {
        const data = await response.json();
        setChannels(data);
      }
    } catch (error) {
      console.error('Error fetching channels:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchChannels();
  }, [selectedTags, search]);

  const toggleTagFilter = (tagId) => {
    setSelectedTags(prev =>
      prev.includes(tagId)
        ? prev.filter(id => id !== tagId)
        : [...prev, tagId]
    );
  };

  const handleToggleTag = async (channel, tagId) => {
    const hasTag = channel.tags.some(t => t.id === tagId);
    const tag = tags.find(t => t.id === tagId);

    // Optimistically update the UI immediately
    setChannels(prevChannels =>
      prevChannels.map(ch =>
        ch.id === channel.id
          ? {
              ...ch,
              tags: hasTag
                ? ch.tags.filter(t => t.id !== tagId)
                : [...ch.tags, tag]
            }
          : ch
      )
    );

    // Then update the server in the background
    try {
      const response = await fetch(
        `/api/channels/${channel.id}/tags/${tagId}`,
        { method: hasTag ? 'DELETE' : 'POST' }
      );

      // If the server request fails, revert the optimistic update
      if (!response.ok) {
        console.error('Failed to update tag on server');
        // Revert by refetching
        fetchChannels();
      }
    } catch (error) {
      console.error('Error toggling tag:', error);
      // Revert on error by refetching
      fetchChannels();
    }
  };

  const formatNumber = (num) => {
    if (!num) return 'N/A';
    return num.toLocaleString();
  };

  return (
    <div className="channel-list-container">
      <div className="filters-card">
        <div className="filters-header">
          <h2 className="filters-title">
            Channels <span className="count-badge">{channels.length}</span>
          </h2>
          <div className="search-box">
            <svg className="search-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8"/>
              <path d="m21 21-4.35-4.35"/>
            </svg>
            <input
              type="text"
              placeholder="Search names, IDs, notes..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        <div className="filter-tags">
          <span className="filter-label">Filter:</span>
          {tags.map(tag => (
            <button
              key={tag.id}
              className={`tag-filter ${selectedTags.includes(tag.id) ? 'active' : ''}`}
              style={{
                '--tag-color': tag.color,
                backgroundColor: selectedTags.includes(tag.id) ? tag.color : 'transparent',
                color: selectedTags.includes(tag.id) ? '#ffffff' : tag.color,
                borderColor: tag.color
              }}
              onClick={() => toggleTagFilter(tag.id)}
            >
              {tag.name}
            </button>
          ))}
          {selectedTags.length > 0 && (
            <button className="clear-filters-btn" onClick={() => setSelectedTags([])}>
              Clear all
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="loading-state">
          <div className="spinner-ring"></div>
          <p>Loading channels...</p>
        </div>
      ) : channels.length === 0 ? (
        <div className="empty-state">
          <svg className="empty-icon" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
          <h3>No channels found</h3>
          <p>Try adjusting your filters or run an ingestion.</p>
        </div>
      ) : (
        <div className="channels-list">
          {channels.map(channel => (
            <div key={channel.id} className="channel-item">
              <div className="channel-main">
                <div className="channel-info">
                  <div className="channel-name-row">
                    <h3 className="channel-name">{channel.name}</h3>
                    <span className="channel-type">{channel.type}</span>
                    {channel.username && (
                      <a
                        href={`https://t.me/${channel.username}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="telegram-link-btn"
                        title="Open in Telegram"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.562 8.161c-.18 1.897-.962 6.502-1.359 8.627-.168.9-.5 1.201-.82 1.23-.697.064-1.226-.461-1.901-.903-1.056-.693-1.653-1.124-2.678-1.8-1.185-.781-.417-1.21.258-1.911.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.139-5.062 3.345-.479.329-.913.489-1.302.481-.428-.009-1.252-.242-1.865-.442-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.831-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635.099-.002.321.023.465.14.121.099.155.232.171.326.016.094.036.308.02.475z"/>
                        </svg>
                        Open
                      </a>
                    )}
                  </div>

                  <div className="channel-meta">
                    {channel.username && (
                      <a
                        href={`https://t.me/${channel.username}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="meta-item meta-link"
                        title="Open in Telegram"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
                          <circle cx="9" cy="7" r="4"/>
                          <path d="M22 21v-2a4 4 0 0 0-3-3.87"/>
                          <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                        </svg>
                        @{channel.username}
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginLeft: '2px' }}>
                          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                          <polyline points="15 3 21 3 21 9"/>
                          <line x1="10" y1="14" x2="21" y2="3"/>
                        </svg>
                      </a>
                    )}
                    <span className="meta-item">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                        <circle cx="9" cy="7" r="4"/>
                        <line x1="19" y1="8" x2="19" y2="14"/>
                        <line x1="22" y1="11" x2="16" y2="11"/>
                      </svg>
                      {formatNumber(channel.participants_count)}
                    </span>
                    {channel.is_verified && (
                      <span className="verified-badge">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                        </svg>
                        Verified
                      </span>
                    )}
                  </div>

                  <div className="channel-id-row">
                    <span className="channel-id">ID: {channel.id} • Bot: {channel.bot_chat_id}</span>
                    {(channel.type === 'group' || channel.type === 'supergroup') && (
                      <button
                        className="btn btn-members"
                        onClick={() => setMemberChannel(channel)}
                        title="View members"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                          <circle cx="9" cy="7" r="4"/>
                          <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
                          <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                        </svg>
                        Members
                      </button>
                    )}
                  </div>

                  {(channel.notes || channel.about)?.trim() && (
                    <div className="channel-notes">
                      <span className="channel-notes-label">Notes</span>
                      <p className="channel-notes-text">{(channel.notes || channel.about).trim()}</p>
                    </div>
                  )}
                </div>

                <div className="channel-tags-section">
                  <div className="tags-label">Tags:</div>
                  <div className="channel-tags-inline">
                    {tags.map(tag => {
                      const isActive = channel.tags.some(t => t.id === tag.id);
                      return (
                        <button
                          key={tag.id}
                          className={`tag-toggle ${isActive ? 'active' : ''}`}
                          style={{
                            '--tag-color': tag.color,
                            backgroundColor: isActive ? tag.color : 'transparent',
                            color: isActive ? '#ffffff' : tag.color,
                            borderColor: tag.color
                          }}
                          onClick={() => handleToggleTag(channel, tag.id)}
                          title={isActive ? `Remove ${tag.name}` : `Add ${tag.name}`}
                        >
                          {tag.name}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      {memberChannel && (
        <MemberList
          channel={memberChannel}
          onClose={() => setMemberChannel(null)}
        />
      )}
    </div>
  );
}

export default ChannelList;
