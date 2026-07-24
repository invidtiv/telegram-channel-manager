import React, { useState, useEffect, useCallback } from 'react';

function MemberList({ channel, accountId, onClose }) {
  const [members, setMembers] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [fetchStatus, setFetchStatus] = useState(null);

  const loadMembers = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set('search', search);
      const response = await fetch(`/api/channels/${channel.id}/members?${params}`);
      if (response.ok) {
        const data = await response.json();
        setMembers(data);
      }
    } catch (error) {
      console.error('Error loading members:', error);
    } finally {
      setLoading(false);
    }
  }, [channel.id, search]);

  useEffect(() => {
    loadMembers();
  }, [loadMembers]);

  // Poll fetch status while fetching
  useEffect(() => {
    if (!fetching) return;
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`/api/channels/${channel.id}/members/status?account_id=${encodeURIComponent(accountId)}`);
        if (response.ok) {
          const status = await response.json();
          setFetchStatus(status);
          if (!status.running) {
            setFetching(false);
            loadMembers();
          }
        }
      } catch (error) {
        console.error('Error polling status:', error);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [fetching, channel.id, accountId, loadMembers]);

  const handleFetchMembers = async () => {
    setFetching(true);
    setFetchStatus({ running: true, message: 'Starting...', total: 0, processed: 0 });
    try {
      const response = await fetch(`/api/channels/${channel.id}/members/fetch?account_id=${encodeURIComponent(accountId)}`, {
        method: 'POST',
      });
      if (!response.ok) {
        const err = await response.json();
        setFetchStatus({ running: false, message: err.detail || 'Failed to start fetch' });
        setFetching(false);
      }
    } catch (error) {
      setFetchStatus({ running: false, message: `Error: ${error.message}` });
      setFetching(false);
    }
  };

  const handleExport = async (format) => {
    try {
      const response = await fetch(`/api/channels/${channel.id}/members/export?format=${format}`);
      if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `members_${channel.id}.${format}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }
    } catch (error) {
      console.error('Export error:', error);
    }
  };

  const progress = fetchStatus && fetchStatus.total > 0
    ? Math.round((fetchStatus.processed / fetchStatus.total) * 100)
    : 0;

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="member-modal">
        <div className="member-modal-header">
          <div className="member-modal-title">
            <h2>Members</h2>
            <span className="member-channel-name">{channel.name}</span>
            <span className="member-count-badge">{members.length} members</span>
          </div>
          <button className="modal-close-btn" onClick={onClose}>
            <svg viewBox="0 0 20 20" fill="currentColor" width="20" height="20">
              <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
          </button>
        </div>

        {/* Actions bar */}
        <div className="member-actions">
          <div className="member-search-row">
            <input
              type="text"
              className="member-search-input"
              placeholder="Search members..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <button
              className="btn btn-primary"
              onClick={handleFetchMembers}
              disabled={fetching}
            >
              {fetching ? 'Fetching...' : 'Fetch Members'}
            </button>
          </div>

          {members.length > 0 && (
            <div className="member-export-row">
              <button className="btn btn-secondary btn-sm" onClick={() => handleExport('json')}>
                Export JSON
              </button>
              <button className="btn btn-secondary btn-sm" onClick={() => handleExport('csv')}>
                Export CSV
              </button>
            </div>
          )}
        </div>

        {/* Fetch progress */}
        {fetchStatus && fetchStatus.running && (
          <div className="member-fetch-progress">
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${progress}%` }}></div>
            </div>
            <span className="progress-text">
              {fetchStatus.processed}/{fetchStatus.total} ({progress}%) - {fetchStatus.message}
            </span>
          </div>
        )}

        {/* Status message after fetch */}
        {fetchStatus && !fetchStatus.running && fetchStatus.message && (
          <div className={`member-fetch-result ${fetchStatus.message.startsWith('Error') ? 'error' : 'success'}`}>
            {fetchStatus.message}
          </div>
        )}

        {/* Members table */}
        <div className="member-table-container">
          {loading ? (
            <div className="loading-state">
              <div className="spinner-ring"></div>
              <p>Loading members...</p>
            </div>
          ) : members.length === 0 ? (
            <div className="empty-state">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" width="48" height="48">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
              </svg>
              <p>No members loaded yet.</p>
              <p className="text-muted">Click "Fetch Members" to pull members from Telegram via MTProto.</p>
            </div>
          ) : (
            <table className="member-table">
              <thead>
                <tr>
                  <th>User ID</th>
                  <th>Name</th>
                  <th>Username</th>
                  <th>Status</th>
                  <th>Type</th>
                </tr>
              </thead>
              <tbody>
                {members.map((member) => (
                  <tr key={member.id}>
                    <td className="mono">{member.user_id}</td>
                    <td>
                      {member.first_name || ''} {member.last_name || ''}
                    </td>
                    <td>
                      {member.username ? (
                        <a
                          href={`https://t.me/${member.username}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="member-username-link"
                        >
                          @{member.username}
                        </a>
                      ) : (
                        <span className="text-muted">-</span>
                      )}
                    </td>
                    <td>
                      <span className={`status-badge status-${member.status || 'unknown'}`}>
                        {member.status || 'unknown'}
                      </span>
                    </td>
                    <td>
                      {member.is_bot && <span className="type-badge bot">BOT</span>}
                      {member.is_premium && <span className="type-badge premium">PREMIUM</span>}
                      {!member.is_bot && !member.is_premium && <span className="text-muted">user</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

export default MemberList;
