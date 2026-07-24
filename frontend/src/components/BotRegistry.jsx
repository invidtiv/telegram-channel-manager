import React, { useState, useEffect, useRef } from 'react';

const ENVIRONMENTS = ['development', 'staging', 'production', 'testing'];
const STATUSES = ['active', 'inactive', 'revoked', 'archived'];

function BotRegistry() {
  const [bots, setBots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterEnv, setFilterEnv] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterProject, setFilterProject] = useState('');
  const [projects, setProjects] = useState([]);
  const [selectedBot, setSelectedBot] = useState(null);
  const [isEditing, setIsEditing] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [inventory, setInventory] = useState(null);
  const [assigning, setAssigning] = useState(null);
  const [assignForm, setAssignForm] = useState({ project: '', username: '', display_name: '', environment: 'development' });
  const [form, setForm] = useState({});
  const [message, setMessage] = useState('');
  const fileInputRef = useRef(null);
  const botfatherInputRef = useRef(null);

  const fetchBots = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search.trim()) params.append('search', search.trim());
      if (filterEnv) params.append('environment', filterEnv);
      if (filterStatus) params.append('status', filterStatus);
      if (filterProject) params.append('project', filterProject);
      const res = await fetch(`/api/bots?${params}`);
      if (res.ok) {
        setBots(await res.json());
      }
    } catch (e) {
      console.error('Error fetching bots:', e);
    } finally {
      setLoading(false);
    }
  };

  const fetchMetadata = async () => {
    try {
      const res = await fetch('/api/bots/projects/environments');
      if (res.ok) {
        const data = await res.json();
        setProjects(data.projects || []);
      }
    } catch (e) {
      console.error('Error fetching bot metadata:', e);
    }
  };

  const fetchInventory = async () => {
    try {
      const res = await fetch('/api/bots/inventory');
      if (res.ok) {
        setInventory(await res.json());
      }
    } catch (e) {
      console.error('Error fetching inventory:', e);
    }
  };

  useEffect(() => {
    fetchBots();
    fetchMetadata();
    fetchInventory();
  }, [search, filterEnv, filterStatus, filterProject]);

  const handleScan = async () => {
    setIsScanning(true);
    setMessage('Scanning filesystem and Docker containers...');
    try {
      const res = await fetch('/api/bots/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'full' }),
      });
      if (res.ok) {
        setInventory(await res.json());
        setMessage('Scan started. Inventory will refresh automatically.');
        // Poll for completion
        const interval = setInterval(async () => {
          const check = await fetch('/api/bots/inventory');
          if (check.ok) {
            const data = await check.json();
            setInventory(data);
            if (data.latest_run && data.latest_run.status !== 'running') {
              clearInterval(interval);
              setIsScanning(false);
              setMessage(`Scan completed: ${data.totals.found_tokens} found, ${data.totals.registered_found} registered, ${data.totals.unassigned_found} unassigned.`);
            }
          }
        }, 2000);
        setTimeout(() => {
          clearInterval(interval);
          setIsScanning(false);
        }, 60000);
      } else {
        const err = await res.json();
        setMessage(err.detail || 'Scan failed.');
        setIsScanning(false);
      }
    } catch (e) {
      setMessage('Network error during scan.');
      setIsScanning(false);
    }
    setTimeout(() => setMessage(''), 5000);
  };

  const handleAssign = async (tokenFingerprint) => {
    if (!assignForm.project.trim()) {
      setMessage('Project is required.');
      setTimeout(() => setMessage(''), 3000);
      return;
    }
    try {
      const res = await fetch('/api/bots/assign', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          token_fingerprint: tokenFingerprint,
          project: assignForm.project.trim(),
          username: assignForm.username.trim() || undefined,
          display_name: assignForm.display_name.trim() || undefined,
          environment: assignForm.environment,
        }),
      });
      if (res.ok) {
        setMessage('Token assigned to project.');
        setAssigning(null);
        setAssignForm({ project: '', username: '', display_name: '', environment: 'development' });
        await fetchBots();
        await fetchInventory();
      } else {
        const err = await res.json();
        setMessage(err.detail || 'Assignment failed.');
      }
    } catch (e) {
      setMessage('Network error during assignment.');
    }
    setTimeout(() => setMessage(''), 5000);
  };

  const resetForm = () => {
    setForm({
      token: '',
      username: '',
      display_name: '',
      description: '',
      about_text: '',
      project: '',
      environment: 'development',
      status: 'active',
      tags: '',
      notes: '',
    });
  };

  const startCreate = () => {
    resetForm();
    setSelectedBot(null);
    setIsEditing(true);
  };

  const startEdit = (bot) => {
    setForm({
      token: bot.token,
      username: bot.username,
      display_name: bot.display_name || '',
      description: bot.description || '',
      about_text: bot.about_text || '',
      project: bot.project || '',
      environment: bot.environment || 'development',
      status: bot.status || 'active',
      tags: (bot.tags || []).join(', '),
      notes: bot.notes || '',
    });
    setSelectedBot(bot);
    setIsEditing(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const payload = {
      ...form,
      tags: form.tags.split(',').map(t => t.trim()).filter(Boolean),
    };
    const url = selectedBot ? `/api/bots/${selectedBot.id}` : '/api/bots';
    const method = selectedBot ? 'PUT' : 'POST';
    try {
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        setIsEditing(false);
        fetchBots();
        setMessage(selectedBot ? 'Bot updated.' : 'Bot created.');
        setTimeout(() => setMessage(''), 3000);
      } else {
        const err = await res.json();
        setMessage(err.detail || 'Failed to save bot.');
      }
    } catch (e) {
      setMessage('Network error.');
    }
  };

  const handleDelete = async (bot) => {
    if (!confirm(`Delete bot ${bot.username}?`)) return;
    try {
      const res = await fetch(`/api/bots/${bot.id}`, { method: 'DELETE' });
      if (res.ok) {
        fetchBots();
        setMessage('Bot deleted.');
        setTimeout(() => setMessage(''), 3000);
      }
    } catch (e) {
      console.error('Error deleting bot:', e);
    }
  };

  const handleBotfatherImport = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setIsImporting(true);
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const res = await fetch('/api/bots/import-botfather', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      const result = await res.json();
      if (res.ok) {
        setMessage(`BotFather import: ${result.added} added, ${result.skipped} skipped, ${result.deleted || 0} deleted.`);
        setIsImporting(false);
        fetchBots();
        fetchProjects();
      } else {
        setMessage(result.detail || 'BotFather import failed.');
      }
    } catch (err) {
      setMessage('Invalid BotFather JSON file.');
    }
    e.target.value = '';
    setTimeout(() => setMessage(''), 5000);
  };

  const handleImport = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setIsImporting(true);
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const res = await fetch('/api/bots/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      const result = await res.json();
      if (res.ok) {
        setMessage(`Imported ${result.added} bot(s).`);
        fetchBots();
        fetchMetadata();
      } else {
        setMessage(result.detail || 'Import failed.');
      }
    } catch (e) {
      setMessage('Invalid JSON file.');
    } finally {
      setIsImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
      setTimeout(() => setMessage(''), 5000);
    }
  };

  const renderForm = () => (
    <div className="modal-overlay" onClick={() => setIsEditing(false)}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <h3>{selectedBot ? 'Edit Bot' : 'Add Bot'}</h3>
        <form onSubmit={handleSubmit} className="bot-form">
          <div className="form-grid">
            <label>
              Token
              <input type="text" value={form.token} onChange={(e) => setForm({ ...form, token: e.target.value })} required />
            </label>
            <label>
              Username
              <input type="text" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required />
            </label>
            <label>
              Display Name
              <input type="text" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
            </label>
            <label>
              Project
              <input type="text" value={form.project} onChange={(e) => setForm({ ...form, project: e.target.value })} />
            </label>
            <label>
              Environment
              <select value={form.environment} onChange={(e) => setForm({ ...form, environment: e.target.value })}>
                {ENVIRONMENTS.map(env => <option key={env} value={env}>{env}</option>)}
              </select>
            </label>
            <label>
              Status
              <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {STATUSES.map(st => <option key={st} value={st}>{st}</option>)}
              </select>
            </label>
          </div>
          <label>
            Tags (comma-separated)
            <input type="text" value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} />
          </label>
          <label>
            Description
            <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} rows={2} />
          </label>
          <label>
            Notes
            <textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} rows={3} />
          </label>
          <div className="form-actions">
            <button type="button" className="btn-secondary" onClick={() => setIsEditing(false)}>Cancel</button>
            <button type="submit" className="btn-primary">Save</button>
          </div>
        </form>
      </div>
    </div>
  );

  return (
    <div className="bot-registry-container">
      <div className="filters-card">
        <div className="filters-header">
          <h2 className="filters-title">
            Bot Registry <span className="count-badge">{bots.length}</span>
          </h2>
          <div className="bot-actions">
            <input
              type="file"
              accept=".json"
              ref={fileInputRef}
              onChange={handleImport}
              style={{ display: 'none' }}
            />
            <button className="btn-secondary" onClick={() => fileInputRef.current?.click()} disabled={isImporting}>
              {isImporting ? 'Importing...' : 'Import JSON'}
            </button>
            <input
              type="file"
              accept=".json"
              ref={botfatherInputRef}
              onChange={handleBotfatherImport}
              style={{ display: 'none' }}
            />
            <button className="btn-secondary" onClick={() => botfatherInputRef.current?.click()} disabled={isImporting}>
              Import BotFather
            </button>
            <button className="btn-secondary" onClick={handleScan} disabled={isScanning}>
              {isScanning ? 'Scanning...' : 'Scan Tokens'}
            </button>
            <button className="btn-primary" onClick={startCreate}>Add Bot</button>
          </div>
        </div>

        {message && <div className="bot-message">{message}</div>}

        <div className="filter-row">
          <div className="search-box">
            <svg className="search-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.35-4.35" />
            </svg>
            <input
              type="text"
              placeholder="Search bots..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <select value={filterProject} onChange={(e) => setFilterProject(e.target.value)} className="filter-select">
            <option value="">All projects</option>
            {projects.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
          <select value={filterEnv} onChange={(e) => setFilterEnv(e.target.value)} className="filter-select">
            <option value="">All environments</option>
            {ENVIRONMENTS.map(e => <option key={e} value={e}>{e}</option>)}
          </select>
          <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)} className="filter-select">
            <option value="">All statuses</option>
            {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>

      {loading ? (
        <div className="loading-state"><div className="spinner-ring"></div><p>Loading bots...</p></div>
      ) : bots.length === 0 ? (
        <div className="empty-state">
          <h3>No bots registered</h3>
          <p>Add a bot manually or import a TGsecrets JSON export.</p>
        </div>
      ) : (
        <div className="bots-list">
          {bots.map(bot => (
            <div key={bot.id} className="bot-card">
              <div className="bot-main">
                <div className="bot-info">
                  <div className="bot-name-row">
                    <span className={`status-pill status-${bot.status}`}>{bot.status}</span>
                    <h4 className="bot-name">{bot.display_name || bot.username}</h4>
                    <span className="bot-username">@{bot.username}</span>
                    <span className="bot-environment">{bot.environment}</span>
                  </div>
                  <div className="bot-meta">
                    <span className="meta-item">Project: <strong>{bot.project || '—'}</strong></span>
                    <span className="meta-item">Token: <code>{bot.token.slice(0, bot.token.indexOf(':') + 4)}...{bot.token.slice(-4)}</code></span>
                  </div>
                  {bot.description && <p className="bot-description">{bot.description}</p>}
                  {bot.notes && <p className="bot-notes">{bot.notes}</p>}
                  {bot.tags && bot.tags.length > 0 && (
                    <div className="bot-tags">
                      {bot.tags.map(tag => <span key={tag} className="bot-tag">{tag}</span>)}
                    </div>
                  )}
                </div>
                <div className="bot-actions">
                  <button className="btn-icon" onClick={() => startEdit(bot)} title="Edit">✎</button>
                  <button className="btn-icon btn-danger" onClick={() => handleDelete(bot)} title="Delete">×</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {inventory && inventory.latest_run && (
        <div className="filters-card">
          <div className="filters-header">
            <h2 className="filters-title">Token Inventory</h2>
            {inventory.latest_run && (
              <span className="bot-environment">
                Last scan: {inventory.latest_run.status} ({new Date(inventory.latest_run.finished_at).toLocaleString()})
              </span>
            )}
          </div>
          <div className="inventory-totals">
            <span className="inventory-total">Registered: <strong>{inventory.totals.registered_bots}</strong></span>
            <span className="inventory-total">Found: <strong>{inventory.totals.found_tokens}</strong></span>
            <span className="inventory-total">Registered found: <strong>{inventory.totals.registered_found}</strong></span>
            <span className="inventory-total">Unassigned: <strong>{inventory.totals.unassigned_found}</strong></span>
            <span className="inventory-total">Missing: <strong>{inventory.totals.registered_missing}</strong></span>
            <span className="inventory-total">Duplicates: <strong>{inventory.totals.duplicate_tokens}</strong></span>
            <span className="inventory-total">Risky: <strong>{inventory.totals.risky_tokens}</strong></span>
          </div>
          {inventory.tokens.length > 0 && (
            <div className="inventory-tokens">
              {inventory.tokens.map(token => (
                <div key={token.token_fingerprint} className={`inventory-token status-${token.status}`}>
                  <div className="token-header">
                    <span className={`status-pill status-${token.status === 'registered_found' ? 'active' : token.status === 'unassigned_found' ? 'revoked' : 'inactive'}`}>
                      {token.status}
                    </span>
                    <span className="bot-username">@{token.username || token.bot_id}</span>
                    <span className="bot-environment">{token.project || 'no project'}</span>
                    <span className="bot-environment">{token.occurrence_count} occurrence(s)</span>
                  </div>
                  {token.risks.length > 0 && (
                    <div className="token-risks">
                      {token.risks.map(risk => <span key={risk} className="risk-tag">{risk}</span>)}
                    </div>
                  )}
                  {token.status === 'unassigned_found' && (
                    <div className="token-assign">
                      {assigning === token.token_fingerprint ? (
                        <div className="assign-form">
                          <input
                            type="text"
                            placeholder="Project *"
                            value={assignForm.project}
                            onChange={(e) => setAssignForm({ ...assignForm, project: e.target.value })}
                            className="assign-input"
                          />
                          <input
                            type="text"
                            placeholder="Username (optional)"
                            value={assignForm.username}
                            onChange={(e) => setAssignForm({ ...assignForm, username: e.target.value })}
                            className="assign-input"
                          />
                          <input
                            type="text"
                            placeholder="Display name (optional)"
                            value={assignForm.display_name}
                            onChange={(e) => setAssignForm({ ...assignForm, display_name: e.target.value })}
                            className="assign-input"
                          />
                          <select
                            value={assignForm.environment}
                            onChange={(e) => setAssignForm({ ...assignForm, environment: e.target.value })}
                            className="assign-input"
                          >
                            <option value="development">Development</option>
                            <option value="staging">Staging</option>
                            <option value="production">Production</option>
                          </select>
                          <div className="assign-actions">
                            <button className="btn-primary" onClick={() => handleAssign(token.token_fingerprint)}>Assign</button>
                            <button className="btn-secondary" onClick={() => setAssigning(null)}>Cancel</button>
                          </div>
                        </div>
                      ) : (
                        <button className="btn-secondary" onClick={() => setAssigning(token.token_fingerprint)}>Assign Project</button>
                      )}
                    </div>
                  )}
                  {token.occurrences.length > 0 && (
                    <ul className="token-occurrences">
                      {token.occurrences.slice(0, 5).map((occ, idx) => (
                        <li key={idx} className="token-occurrence">
                          <code>{occ.source_label}</code>
                          {occ.risk && <span className="risk-tag">{occ.risk}</span>}
                        </li>
                      ))}
                      {token.occurrences.length > 5 && (
                        <li className="token-occurrence">...and {token.occurrences.length - 5} more</li>
                      )}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {isEditing && renderForm()}
    </div>
  );
}

export default BotRegistry;
