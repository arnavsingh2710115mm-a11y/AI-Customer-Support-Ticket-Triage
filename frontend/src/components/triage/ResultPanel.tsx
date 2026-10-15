import { useState } from 'react';
import { ArrowRight, Check, ChevronDown, Copy, FileText, Info, Route, ShieldCheck, UserRound } from 'lucide-react';
import { Badge, Button, Card, Meter, Toast } from '../ui';
import type { Tone } from '../ui';
import { CategoryIcon } from './CategoryIcon';
import type { CompletedTriage, Prediction } from '../../lib/types';
import { confidence, percent } from '../../lib/format';
import styles from './Triage.module.css';

export function ResultPanel({ completed }: { completed: CompletedTriage }) {
  const { result, elapsedMs } = completed;
  const { decision, review_threshold: threshold } = result;
  const [toast, setToast] = useState('');
  const [manualCopy, setManualCopy] = useState(false);
  const summary = [
    'Ticket triage result', 'Category: ' + result.category.label + ' (' + confidence(result.category.confidence) + ')',
    'Urgency: ' + result.urgency.label + ' (' + confidence(result.urgency.confidence) + ')',
    'Manual review: ' + (decision.needs_review ? 'Required' : 'Not required'),
    'Assigned queue: ' + (decision.assigned_queue ?? 'None — manual review'),
    'Suggested queue: ' + decision.suggested_queue,
    ...decision.reasons, 'Review threshold: ' + percent(threshold),
    'Model trained on synthetic data; real-world accuracy is not established.',
  ].join('\n');
  async function copySummary() {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(summary);
      setToast('Summary copied');
    } catch {
      const fallback = document.createElement('textarea');
      fallback.value = summary;
      document.body.appendChild(fallback);
      fallback.select();
      let copied = false;
      try { copied = document.execCommand('copy'); } catch { /* Show a manual selection instead. */ }
      fallback.remove();
      if (copied) setToast('Summary copied'); else setManualCopy(true);
    }
  }
  return <div className={styles.results}>
    <Card className={styles.decision + ' ' + (decision.needs_review ? styles.reviewDecision : styles.autoDecision)}>
      <span className={styles.decisionIcon}>{decision.needs_review ? <UserRound size={22} /> : <Route size={22} />}</span>
      <div><Badge tone={decision.needs_review ? 'review' : 'accent'}>{decision.needs_review ? 'Human in the loop' : 'Ready to route'}</Badge>
        <h2>{decision.needs_review ? 'Needs human review' : 'Route to ' + decision.assigned_queue}</h2>
        <p>{decision.needs_review ? decision.reasons.map(reason => reason.replace(/\.$/, '')).join('; ') + '.'
          : 'Both predictions meet the review threshold. The suggested team can take it from here.'}</p>
        <span className={styles.elapsed}>Classified in <span className="mono">{elapsedMs}</span> ms</span></div>
    </Card>
    <div className={styles.predictionGrid}>
      <PredictionCard title="Category" prediction={result.category} threshold={threshold}
        badge={<Badge><CategoryIcon category={result.category.label} />{result.category.label}</Badge>} />
      <PredictionCard title="Urgency" prediction={result.urgency} threshold={threshold}
        badge={<Badge tone={result.urgency.label.toLowerCase() as Tone}><span className={styles.dot} />{result.urgency.label}</Badge>} />
    </div>
    <Card className={styles.handoff}>
      <h3>Support team handoff</h3>
      <div className={styles.path}>
        <div className={styles.pathNode}><FileText size={18} aria-hidden="true" /><span><small>Input</small>Ticket</span></div>
        <ArrowRight className={styles.pathArrow} size={16} aria-hidden="true" />
        <div className={styles.pathNode}><CategoryIcon category={result.category.label} size={18} /><span><small>Category</small>{result.category.label}</span></div>
        <ArrowRight className={styles.pathArrow} size={16} aria-hidden="true" />
        <div className={styles.pathNode + ' ' + (decision.needs_review ? styles.reviewNode : styles.queueNode)}>
          {decision.needs_review ? <UserRound size={18} /> : <ShieldCheck size={18} />}
          <span><small>{decision.needs_review ? 'Human checkpoint' : 'Destination'}</small>
            {decision.needs_review ? 'Manual review' : decision.assigned_queue}</span></div>
      </div>
      {decision.needs_review && <p className={styles.suggested}>Suggested after review: <strong>{decision.suggested_queue}</strong></p>}
    </Card>
    {decision.needs_review && <Card className={styles.reviewDetails}>
      <h3>Why this was flagged</h3>
      {([['Category', result.category], ['Urgency', result.urgency]] as const).map(([title, prediction]) => {
        const below = prediction.confidence < threshold;
        return <div className={styles.reviewRow} key={title}>{below ? <Info size={17} aria-hidden="true" /> : <Check size={17} aria-hidden="true" />}
          <div><p>{title + ' confidence ' + confidence(prediction.confidence) + (below ? ' is below the ' : ' meets the ') + percent(threshold) + ' threshold.'}</p>
            {below && <Meter value={prediction.confidence} threshold={threshold} label={title + ' confidence review check'} small />}</div></div>;
      })}
      {decision.reasons.some(reason => reason.includes('vocabulary')) && <p className={styles.vocabulary}>The model did not recognize vocabulary in this ticket. A person should interpret the issue.</p>}
      <div className={styles.guidance}><strong>Reviewer guidance</strong><p>Verify the category, verify the urgency, then forward the ticket to the suggested team.</p></div>
    </Card>}
    <details className={styles.explanation}>
      <summary>How this was decided <ChevronDown size={16} aria-hidden="true" /></summary>
      <div><p>A ticket goes to manual review when either prediction's confidence is below {percent(threshold)}. Text with no recognized vocabulary is also reviewed.</p>
        <dl><div><dt>Category model</dt><dd>Logistic Regression · TF-IDF</dd></div><div><dt>Urgency model</dt><dd>Logistic Regression · TF-IDF</dd></div>
          <div><dt>Review threshold</dt><dd className="mono">{percent(threshold)} <span className="muted">· Set by developers</span></dd></div></dl>
        <p>Confidence scores are model probabilities, not guarantees of correctness.</p></div>
    </details>
    <div className={styles.resultActions}><Button onClick={() => void copySummary()}><Copy aria-hidden="true" />Copy summary</Button>
      <span>Keep the decision in context.</span></div>
    {manualCopy && <div className={styles.manualCopy}><label htmlFor="manual-summary">Clipboard unavailable. Select and copy this summary:</label>
      <textarea id="manual-summary" readOnly value={summary} rows={10} onFocus={event => event.currentTarget.select()} /></div>}
    {toast && <Toast message={toast} onClose={() => setToast('')} />}
  </div>;
}
function PredictionCard({ title, prediction, threshold, badge }: {
  title: string; prediction: Prediction<string>; threshold: number; badge: React.ReactNode;
}) {
  const below = prediction.confidence < threshold;
  const other = prediction.probabilities ? Object.entries(prediction.probabilities)
    .filter(([label]) => label !== prediction.label).sort((a, b) => b[1] - a[1]).slice(0, 3) : [];
  return <Card className={styles.prediction}>
    <div className={styles.predictionHeading}><h3>{title}</h3>{badge}</div>
    <div className={styles.bigConfidence}>{confidence(prediction.confidence)}</div>
    <Meter value={prediction.confidence} threshold={threshold} label={title + ' prediction confidence'} />
    <p className={below ? styles.below : styles.above}>{below ? 'Below review threshold' : 'Meets review threshold'}</p>
    {other.length > 0 && <div className={styles.candidates}><span>Other candidates</span>{other.map(([label, value]) =>
      <div key={label}><span>{label}</span><span className="mono">{confidence(value)}</span></div>)}</div>}
  </Card>;
}
