import { useEffect, useRef, useState } from 'react';
import { ArrowRight, ArrowUpRight, FileText, Inbox, Send, Sparkles, X } from 'lucide-react';
import { Banner, Button, Card, Skeleton } from '../components/ui';
import { ResultPanel } from '../components/triage/ResultPanel';
import { EXAMPLE_INPUTS } from '../lib/examples';
import type { ApiError } from '../lib/api';
import type { CompletedTriage, InputRules } from '../lib/types';
import { count } from '../lib/format';
import { ticketLength } from '../lib/ticketText';
import styles from '../components/triage/Triage.module.css';

interface Props {
  text: string; onTextChange: (value: string) => void; onClassify: () => void;
  completed: CompletedTriage | null; busy: boolean; error: ApiError | null;
  rules: InputRules | null; connecting: boolean; connectionError: ApiError | null; onReconnect: () => void;
}
export function TriagePage(props: Props) {
  const { text, onTextChange, onClassify, completed, busy, error, rules, connecting, connectionError, onReconnect } = props;
  const [attempted, setAttempted] = useState(false);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const resultHeading = useRef<HTMLHeadingElement>(null);
  const length = ticketLength(text);
  const validation = rules && (length < rules.minLength
    ? 'Enter at least ' + count(rules.minLength) + ' characters to describe the issue.'
    : length > rules.maxLength ? 'Keep the ticket within ' + count(rules.maxLength) + ' characters.' : '');
  useEffect(() => {
    if (textarea.current) {
      textarea.current.style.height = 'auto';
      textarea.current.style.height = textarea.current.scrollHeight + 'px';
    }
  }, [text]);
  useEffect(() => { if (completed) resultHeading.current?.focus(); }, [completed]);
  function submit() { setAttempted(true); if (!validation && rules) onClassify(); }
  return <div className={styles.page}>
    <div className={styles.pageHeader}><div><h1>Give every ticket a clear next step.</h1>
      <p>Understand the issue. Set the priority. Find the right support team.</p></div>
      <span className={styles.localNote}><Sparkles size={15} aria-hidden="true" /> AI-assisted, human-aware</span>
    </div>
    {connectionError && <Banner error onRetry={onReconnect}><strong>Connection needs attention</strong><p>{connectionError.message}</p></Banner>}
    <div className={styles.workspace}>
      <section aria-labelledby="composer-title">
        <Card className={styles.composer}>
          <div className={styles.sectionHeader}><span className={styles.sectionIcon}><FileText size={18} aria-hidden="true" /></span>
            <div><h2 id="composer-title">New ticket</h2><p>Start with the customer's own words.</p></div></div>
          <form onSubmit={event => { event.preventDefault(); submit(); }}>
            <label htmlFor="ticket-text" className={styles.label}>Customer support ticket</label>
            <textarea id="ticket-text" ref={textarea} rows={6} value={text}
              placeholder="Describe what happened, who is affected, and any deadlines..."
              aria-invalid={Boolean(attempted && validation)} aria-describedby="ticket-help ticket-count ticket-validation ticket-privacy"
              onChange={event => { onTextChange(event.target.value); }}
              onKeyDown={event => { if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); submit(); } }} />
            <div className={styles.inputMeta}><span id="ticket-help">Ctrl/Cmd + Enter to classify</span>
              <span id="ticket-count" className="mono">{count(length)}{rules ? ' / ' + count(rules.maxLength) : ''}</span></div>
            <div id="ticket-validation" className={styles.validation} aria-live="polite">
              {attempted && validation ? <><X size={14} aria-hidden="true" />{validation}</> : null}
            </div>
            <div className={styles.composerActions}>
              <Button type="submit" variant="primary" loading={busy} disabled={!rules || connecting}>
                {!busy && <Send aria-hidden="true" />}{busy ? 'Classifying...' : 'Classify ticket'}
              </Button>
              <Button variant="ghost" type="button" onClick={() => { onTextChange(''); setAttempted(false); textarea.current?.focus(); }}>Clear</Button>
            </div>
            <p id="ticket-privacy" className={styles.privacyNotice}>Tickets flagged for manual review may be stored on this application's server. Use synthetic or non-sensitive example tickets for this demonstration.</p>
          </form>
          <div className={styles.examples}><strong>Example inputs</strong><p>Try an input. Results come from the trained models.</p>
            <div className={styles.chips}>{EXAMPLE_INPUTS.map(example => <button key={example.label} type="button"
              onClick={() => { onTextChange(example.text); setAttempted(false); textarea.current?.focus(); }}>
              {example.label}<ArrowUpRight size={13} aria-hidden="true" /></button>)}</div>
          </div>
          <div className={styles.composerFoot}><InfoDot /><span>Predictions suggest a support team. Tickets are not automatically forwarded.</span></div>
        </Card>
        <p className={styles.demoNote}>A student demonstration using synthetic training data. Review uncertain decisions before forwarding a ticket.</p>
      </section>
      <section className={styles.resultRegion} aria-labelledby="result-title" aria-busy={busy}>
        <div className={styles.resultTitle}><h2 id="result-title" ref={resultHeading} tabIndex={-1}>Triage result</h2><span>Decision workspace</span></div>
        <div className="sr-only" aria-live="polite">{completed ? completed.result.decision.needs_review ? 'Classification complete. Needs human review.' : 'Classification complete. Route to ' + completed.result.decision.assigned_queue : ''}</div>
        {error ? <Banner error onRetry={submit}><strong>{error.code === 'MODELS_MISSING' ? 'Models unavailable' : 'Unable to classify'}</strong><p>{error.message}</p></Banner>
          : busy ? <div className={styles.loading}><Card><Skeleton label="Classifying ticket" lines={3} /></Card>
            <div className={styles.predictionGrid}><Card><Skeleton lines={3} /></Card><Card><Skeleton lines={3} /></Card></div>
            <Card><Skeleton lines={2} /></Card></div>
          : completed ? <ResultPanel completed={completed} />
          : <Card className={styles.idle}>
            <div className={styles.idleSymbol}><Inbox size={28} strokeWidth={1.5} aria-hidden="true" /></div>
            <h2>A little clarity starts here.</h2><p>Submit a ticket to see its category, urgency, and recommended support queue.</p>
            <div className={styles.placeholderSlots}><div><FileText size={18} />Category</div><ArrowRight size={15} aria-hidden="true" />
              <div><Sparkles size={18} />Urgency</div><ArrowRight size={15} aria-hidden="true" /><div><Send size={18} />Route</div></div>
            <span className={styles.idleFooter}>Uncertain predictions are flagged for a person to review.</span>
          </Card>}
      </section>
    </div>
  </div>;
}
function InfoDot() { return <span className={styles.infoDot} aria-hidden="true">i</span>; }
