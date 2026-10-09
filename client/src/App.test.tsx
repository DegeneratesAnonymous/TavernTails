import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import App from './App';

test('renders home quick actions', () => {
  render(<App />);
  expect(screen.getByRole('button', { name: /start new game/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /load a game/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
});

test('Steward SSO sign-in remembers who signed in so the character can be restored', async () => {
  window.history.pushState({}, '', '/?sso_token=abc')
  window.localStorage.clear()
  const fetchMock = jest.fn(async (url: string) => {
    if (String(url).includes('/player/steward-sso')) {
      return { ok: true, json: async () => ({ access_token: 'jwt', profile: { email: 'will@steward.local', username: 'will' } }) } as Response
    }
    return { ok: false, status: 404, json: async () => ({}) } as Response
  })
  const original = global.fetch
  global.fetch = fetchMock as unknown as typeof fetch
  try {
    render(<App />)
    await waitFor(() => expect(window.localStorage.getItem('access_token')).toBe('jwt'))
    expect(window.localStorage.getItem('user_email')).toBe('will@steward.local')
    expect(window.localStorage.getItem('user_username')).toBe('will')
  } finally {
    global.fetch = original
    window.history.pushState({}, '', '/')
    window.localStorage.clear()
  }
})
