import { useEffect, useRef, useState } from 'react';
import { NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { ArrowUpRight, BarChart3, Check, Circle, ClipboardList, Info, Inbox, Moon, Sun } from 'lucide-react';
import { Badge, Button, Popover, Tooltip } from '../components/ui';
import { asApiError, getHealth, getInputRules, isAborted, triage } from '../lib/api';
import type { ApiError } from '../lib/api';
import type { CompletedTriage, HealthResponse, InputRules } from '../lib/types';
import { TriagePage } from '../pages/TriagePage';
import { PerformancePage } from '../pages/PerformancePage';
import { AboutPage } from '../pages/AboutPage';
import { ReviewLogPage } from '../pages/ReviewLogPage';
import { ticketLength, trimTicketText } from '../lib/ticketText';
import styles from './App.module.css';

const pages = [
  { to: '/', label: 'Triage', mobileLabel: 'Triage', icon: Inbox, description: 'Classify, prioritize, and find the right team.' },
  { to: '/performance', label: 'Model performance', mobileLabel: 'Performance', icon: BarChart3, description: 'Understand the models behind each decision.' },
  { to: '/review-log', label: 'Manual Review Log', mobileLabel: 'Review log', icon: ClipboardList, description: 'Administrator access to tickets awaiting review.' },
  { to: '/about', label: 'About & method', mobileLabel: 'About', icon: Info, description: 'A transparent look at the approach and its limits.' },
];
function firstTheme() {
  try {
    const saved = localStorage.getItem('triage-theme');
    if (saved === 'light' || saved === 'dark') return saved;
  } catch { /* Storage may be disabled. */ }
  return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
export function App() {
  const location = useLocation();
  const page = pages.find(item => item.to === location.pathname) ?? pages[0];
  const [theme, setTheme] = useState(firstTheme);
  const [text, setText] = useState('');
  const [completed, setCompleted] = useState<CompletedTriage | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [rules, setRules] = useState<InputRules | null>(null);
  const [connectionError, setConnectionError] = useState<ApiError | null>(null);
  const [connecting, setConnecting] = useState(true);
  const [connectionAttempt, setConnectionAttempt] = useState(0);
  const activeRequest = useRef<AbortController | null>(null);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('triage-theme', theme); } catch { /* In-memory theme still works. */ }
  }, [theme]);
  useEffect(() => { document.title = page.label + ' · Ticket triage'; }, [page.label]);
  useEffect(() => {
    const controller = new AbortController();
    setConnecting(true);
    setConnectionError(null);
    void Promise.allSettled([getHealth(controller.signal), getInputRules(controller.signal)]).then(results => {
      if (controller.signal.aborted) return;
      const [healthResult, rulesResult] = results;
      if (healthResult.status === 'fulfilled') setHealth(healthResult.value);
      else { setHealth(null); setConnectionError(asApiError(healthResult.reason)); }
      if (rulesResult.status === 'fulfilled') setRules(rulesResult.value);
      else { setRules(null); setConnectionError(asApiError(rulesResult.reason)); }
      setConnecting(false);
    });
    return () => controller.abort();
  }, [connectionAttempt]);
  useEffect(() => () => activeRequest.current?.abort(), []);

  function updateText(next: string) {
    activeRequest.current?.abort();
    setBusy(false); setText(next); setError(null); setCompleted(null);
  }
  async function classify() {
    if (busy || !rules) return;
    const trimmed = trimTicketText(text);
    const length = ticketLength(text);
    if (length < rules.minLength || length > rules.maxLength) return;
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setBusy(true); setError(null); setCompleted(null);
    const started = performance.now();
    try {
      const result = await triage(text, controller.signal);
      const elapsedMs = Math.round(performance.now() - started);
      await new Promise(resolve => setTimeout(resolve, Math.max(0, 250 - elapsedMs)));
      if (!controller.signal.aborted) {
        setCompleted({ result, elapsedMs, text: trimmed });
        setHealth(previous => previous ? { ...previous, review_threshold: result.review_threshold } : previous);
        if (!health?.models_loaded) setConnectionAttempt(value => value + 1);
      }
    } catch (cause) {
      if (!isAborted(cause) && !controller.signal.aborted) {
        setError(asApiError(cause));
        if (asApiError(cause).code === 'MODELS_MISSING' || asApiError(cause).code === 'API_UNREACHABLE') setHealth(null);
      }
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  return <div className={styles.app}>
    <a className="skip" href="#main-content">Skip to content</a>
    <aside className={styles.sidebar} aria-label="Product navigation">
      <NavLink to="/" className={styles.brand} aria-label="Ticket triage home">
        <svg viewBox="0 0 32 32" width="32" height="32" aria-hidden="true"><rect x="1" y="1" width="30" height="30" rx="8" fill="currentColor" /><path d="M9 10h14M16 10v13M10 16h6" fill="none" stroke="var(--white)" strokeWidth="2" strokeLinecap="round" /></svg>
        <span>Ticket triage<small>Support operations</small></span>
      </NavLink>
      <nav className={styles.navigation}>{pages.map(item => <NavLink key={item.to} to={item.to} end={item.to === '/'}
        className={({ isActive }) => isActive ? styles.navItem + ' ' + styles.active : styles.navItem}>
        <item.icon size={18} aria-hidden="true" /><span className={styles.fullLabel}>{item.label}</span><span className={styles.mobileLabel}>{item.mobileLabel}</span>
      </NavLink>)}</nav>
      <div className={styles.sidebarFooter}><span className={styles.footerMark}><Circle size={12} /> Local model inference</span>
        <p>Student demonstration<br />Synthetic data</p><ArrowUpRight size={16} aria-hidden="true" /></div>
    </aside>
    <div className={styles.workspace}>
      <header className={styles.topbar}>
        <div className={styles.pageIdentity}><strong>{page.label}</strong><span>{page.description}</span></div>
        <div className={styles.topActions}>
          <Popover label={<Badge>Synthetic data <Info size={13} aria-hidden="true" /></Badge>}>
            <strong>A demonstration, with limits</strong><p>These models were trained and evaluated on synthetic tickets. Their results do not establish real-world accuracy.</p>
          </Popover>
          <span className={styles.status} role="status">
            {health?.models_loaded ? <Check size={14} aria-hidden="true" /> : <Circle size={10} aria-hidden="true" />}
            {connecting ? 'Checking models' : health?.models_loaded ? 'Models loaded' : 'Unavailable'}
          </span>
          <Tooltip text={'Switch to ' + (theme === 'light' ? 'dark' : 'light') + ' theme'}>
            <Button variant="ghost" aria-label={'Switch to ' + (theme === 'light' ? 'dark' : 'light') + ' theme'}
              onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}>
              {theme === 'light' ? <Moon /> : <Sun />}
            </Button>
          </Tooltip>
        </div>
      </header>
      <main id="main-content" className={styles.content} tabIndex={-1}>
        <Routes>
          <Route path="/" element={<TriagePage text={text} onTextChange={updateText} onClassify={() => void classify()}
            completed={completed} busy={busy} error={error} rules={rules} connecting={connecting}
            connectionError={connectionError} onReconnect={() => setConnectionAttempt(value => value + 1)} />} />
          <Route path="/performance" element={<PerformancePage />} />
          <Route path="/review-log" element={<ReviewLogPage />} />
          <Route path="/about" element={<AboutPage health={health} />} />
          <Route path="*" element={<div className={styles.notFound}><h1>Page not found</h1><p>Return to the ticket workspace to continue.</p><NavLink to="/">Go to triage</NavLink></div>} />
        </Routes>
      </main>
    </div>
  </div>;
}
