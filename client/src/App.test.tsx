import React from 'react';
import { render, screen } from '@testing-library/react';
import App from './App';

test('renders home quick actions', () => {
  render(<App />);
  expect(screen.getByRole('button', { name: /start new game/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /load a game/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
});
