import React, { useState } from 'react';
import { countryFlag } from './AccountBadges.jsx';

function AccountSwitcher({
  accounts,
  selectedAccountId,
  onSelect,
  onAccountCreated,
  onAccountUpdated,
}) {
  const [adding, setAdding] = useState(false);
  const [editingAccount, setEditingAccount] = useState(null);
  const [label, setLabel] = useState('');
  const [countryCode, setCountryCode] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const saveAccount = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    try {
      const response = await fetch(
        editingAccount
          ? `/api/telegram-accounts/${editingAccount.id}`
          : '/api/telegram-accounts',
        {
        method: editingAccount ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label, country_code: countryCode }),
        },
      );
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail?.message || data.detail || 'Could not create account');
      }
      setLabel('');
      setCountryCode('');
      setAdding(false);
      setEditingAccount(null);
      if (editingAccount) {
        await onAccountUpdated?.(data);
      } else {
        await onAccountCreated(data);
      }
    } catch (requestError) {
      setError(requestError.message || 'Could not create account');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="account-switcher">
      <div className="account-pills" role="group" aria-label="Telegram account">
        <button
          type="button"
          className={`account-pill ${selectedAccountId === '' ? 'active' : ''}`}
          onClick={() => onSelect('')}
        >
          🌐 All accounts
        </button>
        {accounts.map(account => (
          <button
            type="button"
            key={account.id}
            className={`account-pill ${selectedAccountId === account.id ? 'active' : ''}`}
            onClick={() => onSelect(account.id)}
            title={account.authorized ? 'Telegram connected' : 'Authorization required'}
          >
            <span aria-hidden="true">{countryFlag(account.country_code)}</span>
            <span>{account.label}</span>
            <span className={`account-auth-dot ${account.authorized ? 'connected' : ''}`} />
          </button>
        ))}
        <button type="button" className="account-add-button" onClick={() => setAdding(true)}>
          + Account
        </button>
        {selectedAccountId && (
          <button
            type="button"
            className="account-add-button"
            onClick={() => {
              const account = accounts.find(item => item.id === selectedAccountId);
              if (!account) return;
              setEditingAccount(account);
              setLabel(account.label);
              setCountryCode(account.country_code || '');
              setAdding(true);
            }}
          >
            Edit flag
          </button>
        )}
      </div>

      {adding && (
        <div
          className="modal-overlay"
          onClick={() => {
            setAdding(false);
            setEditingAccount(null);
          }}
        >
          <div className="modal-content account-modal" onClick={event => event.stopPropagation()}>
            <h3>{editingAccount ? 'Edit Telegram account' : 'Add Telegram account'}</h3>
            <p className="text-muted">
              {editingAccount
                ? 'Update the label or two-letter country flag for this account.'
                : 'This creates an isolated session. You will authorize it from the Ingestion tab.'}
            </p>
            <form className="bot-form" onSubmit={saveAccount}>
              <label>
                Account label
                <input
                  value={label}
                  onChange={event => setLabel(event.target.value)}
                  placeholder="Work, Personal, Germany…"
                  required
                  maxLength={80}
                  autoFocus
                />
              </label>
              <label>
                Flag country code
                <input
                  value={countryCode}
                  onChange={event => setCountryCode(event.target.value.toUpperCase())}
                  placeholder="DE"
                  pattern="[A-Za-z]{2}"
                  maxLength={2}
                />
              </label>
              {error && <div className="telegram-auth-error">{error}</div>}
              <div className="form-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => {
                    setAdding(false);
                    setEditingAccount(null);
                  }}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={saving}>
                  {saving ? 'Saving…' : editingAccount ? 'Save account' : 'Create account'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default AccountSwitcher;
