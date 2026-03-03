import React, { useState, useEffect } from 'react';

function IngestionPanel({ onIngestionComplete }) {
  const [status, setStatus] = useState({
    running: false,
    total: 0,
    processed: 0,
    message: 'Ready to start'
  });
  const [polling, setPolling] = useState(false);

  const fetchStatus = async () => {
    try {
      const response = await fetch('/api/ingestion/status');
      if (response.ok) {
        const data = await response.json();
        setStatus(data);
        return data;
      }
    } catch (error) {
      console.error('Error fetching status:', error);
    }
    return null;
  };

  useEffect(() => {
    // Initial status fetch
    fetchStatus();
  }, []);

  useEffect(() => {
    let interval;
    if (polling) {
      interval = setInterval(async () => {
        const currentStatus = await fetchStatus();
        if (currentStatus && !currentStatus.running) {
          setPolling(false);
          onIngestionComplete();
        }
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [polling, onIngestionComplete]);

  const startIngestion = async () => {
    try {
      const response = await fetch('/api/ingestion/start', {
        method: 'POST'
      });

      if (response.ok) {
        setPolling(true);
        fetchStatus(); // Immediate update
      } else {
        const error = await response.json();
        alert(error.detail || 'Failed to start ingestion');
      }
    } catch (error) {
      console.error('Error starting ingestion:', error);
    }
  };

  const getStatusClass = () => {
    if (status.running) return 'running';
    if (status.message.includes('Completed')) return 'completed';
    if (status.message.includes('Error')) return 'error';
    return 'idle';
  };

  const getStatusIcon = () => {
    if (status.running) return <span className="spinner">⏳</span>;
    if (status.message.includes('Completed')) return '✅';
    if (status.message.includes('Error')) return '❌';
    return '⏸️';
  };

  const progressPercent = status.total > 0 
    ? Math.round((status.processed / status.total) * 100) 
    : 0;

  return (
    <div className="card">
      <h2>Channel Ingestion</h2>
      
      <div className="ingestion-status">
        <div className={`status-indicator ${getStatusClass()}`}>
          {getStatusIcon()}
          <span>{status.message}</span>
        </div>

        {status.running && status.total > 0 && (
          <div className="progress-bar">
            <div 
              className="progress-fill" 
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        )}

        {status.running && (
          <p style={{ color: '#6b7280', marginTop: '0.5rem' }}>
            Processed {status.processed} of {status.total} channels
          </p>
        )}

        {!status.running && (
          <div style={{ marginTop: '1.5rem' }}>
            <p style={{ color: '#6b7280', marginBottom: '1rem' }}>
              This will fetch all channels and groups from your Telegram account 
              and update the database.
            </p>
            <button 
              className="btn btn-primary"
              onClick={startIngestion}
              disabled={status.running}
            >
              🚀 Start Ingestion
            </button>
          </div>
        )}
      </div>

      <div style={{ marginTop: '2rem', paddingTop: '2rem', borderTop: '1px solid #e5e7eb' }}>
        <h3>About Ingestion</h3>
        <ul style={{ color: '#6b7280', lineHeight: '1.8', marginTop: '0.5rem' }}>
          <li>Fetches all channels, groups, and supergroups from your Telegram account</li>
          <li>New channels are added to the database</li>
          <li>Existing channels are updated with latest information</li>
          <li>Your tag assignments are preserved during updates</li>
          <li>Rate limiting is handled automatically</li>
        </ul>
      </div>
    </div>
  );
}

export default IngestionPanel;
