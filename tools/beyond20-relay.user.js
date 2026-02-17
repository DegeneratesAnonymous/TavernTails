// ==UserScript==
// @name         TavernTails Beyond20 Relay
// @namespace    https://taverntails.local/
// @version      0.1.0
// @description  Relays Beyond20 roll events from D&D Beyond pages into a TavernTails session chat.
// @match        https://www.dndbeyond.com/*
// @grant        none
// ==/UserScript==

(() => {
  'use strict';

  // --------- CONFIG (fill these in) ---------
  const TAVERNTAILS_BASE_URL = 'http://localhost:8000';
  const SESSION_ID = ''; // e.g. "64c3de0e" (your active TavernTails session id)
  const RELAY_TOKEN = ''; // from TavernTails: Beyond20 Relay Token

  // Optional: include a small debug banner
  const DEBUG = true;

  function log(...args) {
    if (!DEBUG) return;
    // eslint-disable-next-line no-console
    console.log('[TavernTails Relay]', ...args);
  }

  function warn(...args) {
    // eslint-disable-next-line no-console
    console.warn('[TavernTails Relay]', ...args);
  }

  function isConfigured() {
    return Boolean(TAVERNTAILS_BASE_URL && SESSION_ID && RELAY_TOKEN);
  }

  async function postRoll(beyond20Payload) {
    if (!isConfigured()) {
      warn('Not configured. Set SESSION_ID and RELAY_TOKEN.');
      return;
    }

    const url = `${TAVERNTAILS_BASE_URL.replace(/\/$/, '')}/integrations/beyond20/roll/relay`;
    const body = {
      session_id: SESSION_ID,
      beyond20: beyond20Payload,
    };

    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Relay-Token': RELAY_TOKEN,
        },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const text = await res.text();
        warn('Relay failed:', res.status, text);
        return;
      }
      log('Relayed roll ok');
    } catch (e) {
      warn('Relay error:', e);
    }
  }

  function addBanner() {
    if (!DEBUG) return;
    const el = document.createElement('div');
    el.textContent = isConfigured()
      ? 'TavernTails Relay: configured'
      : 'TavernTails Relay: NOT configured (edit SESSION_ID + RELAY_TOKEN)';
    el.style.position = 'fixed';
    el.style.bottom = '12px';
    el.style.right = '12px';
    el.style.zIndex = '999999';
    el.style.padding = '8px 10px';
    el.style.borderRadius = '8px';
    el.style.background = 'rgba(0,0,0,0.75)';
    el.style.color = '#fff';
    el.style.font = '12px/1.2 system-ui, -apple-system, Segoe UI, Roboto, sans-serif';
    el.style.border = '1px solid rgba(255,255,255,0.15)';
    document.documentElement.appendChild(el);
    setTimeout(() => el.remove(), 12000);
  }

  // Beyond20 emits DOM custom events on DDB pages:
  // - Beyond20_roll
  // - Beyond20_rendered-roll
  function onBeyond20Event(evt) {
    try {
      const detail = evt?.detail || [];
      const payload = Array.isArray(detail) ? detail[0] : detail;
      if (!payload || typeof payload !== 'object') return;
      postRoll(payload);
    } catch (e) {
      warn('Failed to handle Beyond20 event', e);
    }
  }

  document.addEventListener('Beyond20_roll', onBeyond20Event, false);
  document.addEventListener('Beyond20_rendered-roll', onBeyond20Event, false);

  addBanner();
  log('Loaded. Listening for Beyond20_roll and Beyond20_rendered-roll events.');
})();
