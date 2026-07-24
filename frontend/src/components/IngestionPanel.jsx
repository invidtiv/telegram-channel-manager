import React, { useCallback, useEffect, useState } from 'react';

const initialAuthStatus = {
  authorized: false,
  state: 'checking',
  message: 'Checking Telegram connection…',
  expires_in: null,
};

function IngestionPanel({ onIngestionComplete }) {
  const [status, setStatus] = useState({
    running: false,
    total: 0,
    processed: 0,
    message: 'Ready to start',
  });
  const [polling, setPolling] = useState(false);
  const [authStatus, setAuthStatus] = useState(initialAuthStatus);
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [authError, setAuthError] = useState('');
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');

  const fetchStatus = useCallback(async () => {
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
  }, []);

  const fetchAuthStatus = useCallback(async () => {
    try {
      const response = await fetch('/api/telegram-auth/status');
      const data = await response.json();
      if (!response.ok) {
        const detail = data.detail;
        throw new Error(
          typeof detail === 'object'
            ? detail.message
            : detail || 'Could not check Telegram authorization',
        );
      }
      setAuthStatus(data);
      setAuthError('');
      return data;
    } catch (error) {
      setAuthStatus({
        authorized: false,
        state: 'unavailable',
        message: 'Could not check Telegram connection.',
        expires_in: null,
      });
      setAuthError(error.message || 'Could not check Telegram authorization');
      return null;
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    fetchAuthStatus();
  }, [fetchAuthStatus, fetchStatus]);

  useEffect(() => {
    let interval;
    if (polling) {
      interval = setInterval(async () => {
        const currentStatus = await fetchStatus();
        if (currentStatus && !currentStatus.running) {
          setPolling(false);
          onIngestionComplete();
          if (currentStatus.message?.includes('authorized')) {
            fetchAuthStatus();
          }
        }
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [fetchAuthStatus, fetchStatus, onIngestionComplete, polling]);

  const postAuthStep = async (path, body) => {
    setAuthSubmitting(true);
    setAuthError('');
    try {
      const response = await fetch(`/api/telegram-auth/${path}`, {
        method: 'POST',
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      const data = await response.json();
      if (!response.ok) {
        const detail = data.detail;
        throw new Error(
          typeof detail === 'object'
            ? detail.message
            : detail || 'Telegram authorization failed',
        );
      }
      setAuthStatus(data);
      if (data.authorized) {
        setPhone('');
        setCode('');
        setPassword('');
      }
      return data;
    } catch (error) {
      setAuthError(error.message || 'Telegram authorization failed');
      return null;
    } finally {
      setAuthSubmitting(false);
    }
  };

  const requestCode = async (event) => {
    event.preventDefault();
    const result = await postAuthStep('request-code', { phone });
    if (result?.state === 'code_required') {
      setCode('');
    }
  };

  const submitCode = async (event) => {
    event.preventDefault();
    const result = await postAuthStep('submit-code', { code });
    setCode('');
    if (result?.state === 'password_required') {
      setPassword('');
    }
  };

  const submitPassword = async (event) => {
    event.preventDefault();
    await postAuthStep('submit-password', { password });
    setPassword('');
  };

  const cancelAuthorization = async () => {
    await postAuthStep('cancel', {});
    setCode('');
    setPassword('');
  };

  const startIngestion = async () => {
    try {
      const currentAuth = await fetchAuthStatus();
      if (!currentAuth?.authorized) {
        return;
      }

      const response = await fetch('/api/ingestion/start', {
        method: 'POST',
      });

      if (response.ok) {
        setPolling(true);
        fetchStatus();
      } else {
        const error = await response.json();
        const detail = error.detail;
        if (response.status === 401 && typeof detail === 'object') {
          setAuthStatus({
            authorized: false,
            state: detail.state || 'phone_required',
            message: detail.message || 'Telegram authorization is required.',
            expires_in: null,
          });
          return;
        }
        alert(
          (typeof detail === 'object' ? detail.message : detail)
          || 'Failed to start ingestion',
        );
      }
    } catch (error) {
      console.error('Error starting ingestion:', error);
    }
  };

  const getStatusClass = () => {
    if (status.running) return 'running';
    if (status.message?.includes('Completed')) return 'completed';
    if (status.message?.includes('Error')) return 'error';
    return 'idle';
  };

  const getStatusIcon = () => {
    if (status.running) return <span className="spinner">⏳</span>;
    if (status.message?.includes('Completed')) return '✅';
    if (status.message?.includes('Error')) return '❌';
    return '⏸️';
  };

  const progressPercent = status.total > 0
    ? Math.round((status.processed / status.total) * 100)
    : 0;

  const renderAuthorization = () => {
    if (authStatus.state === 'checking') {
      return <p className="telegram-auth-help">Checking the persisted Telegram session…</p>;
    }

    if (authStatus.authorized) {
      return (
        <div className="telegram-auth-connected" role="status">
          <span aria-hidden="true">✓</span>
          <div>
            <strong>Telegram connected</strong>
            <p>The saved session is authorized and ready for ingestion.</p>
          </div>
        </div>
      );
    }

    return (
      <>
        <div className="telegram-auth-warning" role="status">
          <span aria-hidden="true">!</span>
          <div>
            <strong>Telegram authorization required</strong>
            <p>{authStatus.message}</p>
          </div>
        </div>

        {authError && (
          <div className="telegram-auth-error" role="alert">
            {authError}
          </div>
        )}

        {(authStatus.state === 'phone_required' || authStatus.state === 'unavailable') && (
          <form className="telegram-auth-form" onSubmit={requestCode}>
            <div className="form-group">
              <label htmlFor="telegram-phone">Telegram phone number</label>
              <input
                id="telegram-phone"
                type="tel"
                autoComplete="tel"
                inputMode="tel"
                placeholder="+491234567890"
                value={phone}
                onChange={(event) => setPhone(event.target.value)}
                required
                maxLength={24}
                disabled={authSubmitting}
              />
              <span className="telegram-auth-help">
                Include the country code. The number is sent directly to Telegram and is not saved by this app.
              </span>
            </div>
            <button className="btn btn-primary" type="submit" disabled={authSubmitting}>
              {authSubmitting ? 'Sending…' : 'Send verification code'}
            </button>
          </form>
        )}

        {authStatus.state === 'code_required' && (
          <form className="telegram-auth-form" onSubmit={submitCode}>
            <div className="form-group">
              <label htmlFor="telegram-code">Verification code</label>
              <input
                id="telegram-code"
                type="text"
                autoComplete="one-time-code"
                inputMode="numeric"
                pattern="[0-9 ]+"
                placeholder="12345"
                value={code}
                onChange={(event) => setCode(event.target.value)}
                required
                maxLength={12}
                autoFocus
                disabled={authSubmitting}
              />
              <span className="telegram-auth-help">
                Enter the code from Telegram within {Math.max(1, Math.ceil((authStatus.expires_in || 600) / 60))} minutes.
              </span>
            </div>
            <div className="telegram-auth-actions">
              <button className="btn btn-primary" type="submit" disabled={authSubmitting}>
                {authSubmitting ? 'Verifying…' : 'Verify code'}
              </button>
              <button className="btn btn-secondary" type="button" onClick={cancelAuthorization} disabled={authSubmitting}>
                Start over
              </button>
            </div>
          </form>
        )}

        {authStatus.state === 'password_required' && (
          <form className="telegram-auth-form" onSubmit={submitPassword}>
            <div className="form-group">
              <label htmlFor="telegram-password">Two-step verification password</label>
              <input
                id="telegram-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                maxLength={256}
                autoFocus
                disabled={authSubmitting}
              />
              <span className="telegram-auth-help">
                This is only submitted to Telegram and is never stored by this app.
              </span>
            </div>
            <div className="telegram-auth-actions">
              <button className="btn btn-primary" type="submit" disabled={authSubmitting}>
                {authSubmitting ? 'Connecting…' : 'Complete authorization'}
              </button>
              <button className="btn btn-secondary" type="button" onClick={cancelAuthorization} disabled={authSubmitting}>
                Start over
              </button>
            </div>
          </form>
        )}
      </>
    );
  };

  return (
    <div className="card">
      <h2>Channel Ingestion</h2>

      <section className="telegram-auth-card" aria-labelledby="telegram-auth-heading">
        <div className="telegram-auth-heading">
          <div>
            <span className="telegram-auth-eyebrow">Account connection</span>
            <h3 id="telegram-auth-heading">Telegram session</h3>
          </div>
          {!authStatus.authorized && authStatus.state !== 'checking' && (
            <button
              type="button"
              className="telegram-auth-refresh"
              onClick={fetchAuthStatus}
              disabled={authSubmitting}
            >
              Check again
            </button>
          )}
        </div>
        {renderAuthorization()}
      </section>

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

        {!status.running && authStatus.authorized && (
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
