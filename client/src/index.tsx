import React from 'react';
import ReactDOM from 'react-dom/client';
import './theme.css';
import './ui.css';
import './index.css';
import App from './App';
import reportWebVitals from './reportWebVitals';
import AppErrorBoundary from './components/ui/AppErrorBoundary'

// Surface otherwise-silent crashes that can appear as a white screen after refresh.
if (typeof window !== 'undefined') {
  window.addEventListener('error', (event) => {
    // eslint-disable-next-line no-console
    console.error('Global window error', event.error || event.message)
  })
  window.addEventListener('unhandledrejection', (event) => {
    // eslint-disable-next-line no-console
    console.error('Unhandled promise rejection', (event as PromiseRejectionEvent).reason)
  })
}

const root = ReactDOM.createRoot(
  document.getElementById('root') as HTMLElement
);
root.render(
  <React.StrictMode>
    <AppErrorBoundary>
      <App />
    </AppErrorBoundary>
  </React.StrictMode>
);

// If you want to start measuring performance in your app, pass a function
// to log results (for example: reportWebVitals(console.log))
// or send to an analytics endpoint. Learn more: https://bit.ly/CRA-vitals
reportWebVitals();
