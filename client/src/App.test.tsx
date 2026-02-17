import React from 'react';
import { render, screen } from '@testing-library/react';
import App from './App';

test('renders home hero with Get Started button', () => {
  render(<App />);
  const btn = screen.getByRole('button', { name: /get started/i });
  expect(btn).toBeInTheDocument();
});
