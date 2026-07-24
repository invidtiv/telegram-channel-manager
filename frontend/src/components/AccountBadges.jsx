import React from 'react';

export function countryFlag(countryCode) {
  const code = (countryCode || '').trim().toUpperCase();
  if (!/^[A-Z]{2}$/.test(code)) return '🌐';
  return String.fromCodePoint(...[...code].map(letter => 127397 + letter.charCodeAt(0)));
}

export function AccountBadges({ accounts = [] }) {
  if (!accounts.length) return null;
  return (
    <span className="account-badges" aria-label="Telegram accounts">
      {accounts.map(account => (
        <span
          key={account.id}
          className="account-badge"
          title={account.label}
        >
          <span aria-hidden="true">{countryFlag(account.country_code)}</span>
          <span>{account.label}</span>
        </span>
      ))}
    </span>
  );
}
