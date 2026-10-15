import { ArrowRight, FileText, Layers, Route, ShieldCheck, UserRound } from 'lucide-react';
import { Badge, Card } from '../components/ui';
import { percent } from '../lib/format';
import type { HealthResponse } from '../lib/types';
import styles from './About.module.css';

export function AboutPage({ health }: { health: HealthResponse | null }) {
  return <div className={styles.page}>
    <header><Badge>A transparent approach</Badge><h1>Useful assistance.<br />Visible limitations.</h1>
      <p>AI Customer Support Ticket Triage is an internship project exploring how a small machine-learning system can help a support team find a ticket's next step.</p></header>
    <div className={styles.method}>
      <Card><FileText size={20} aria-hidden="true" /><h2>Read the issue</h2><p>Simple text cleaning removes unnecessary formatting and normalizes whitespace.</p></Card>
      <ArrowRight size={18} aria-hidden="true" />
      <Card><Layers size={20} aria-hidden="true" /><h2>Predict independently</h2><p>TF-IDF features feed separate Logistic Regression models for category and urgency.</p></Card>
      <ArrowRight size={18} aria-hidden="true" />
      <Card><Route size={20} aria-hidden="true" /><h2>Suggest a handoff</h2><p>The server supplies the support queue and flags uncertainty for a person to review.</p></Card>
    </div>
    <div className={styles.notes}><Card><ShieldCheck size={22} aria-hidden="true" /><h2>Synthetic data, honest scope</h2>
      <p>The training tickets are synthetic development examples, not historical customer records. A held-out synthetic test set helps inspect behavior; it cannot establish real-world accuracy.</p>
      <p>Saved evaluation results are shown directly from the API. No dashboard statistics are invented, and the frontend does not retrain the models.</p></Card>
      <Card><UserRound size={22} aria-hidden="true" /><h2>People stay in the loop</h2>
        <p>A ticket needs review when either prediction falls below the server's threshold or no vocabulary is recognized.</p>
        {health && <p>Current review threshold: <strong className="mono">{percent(health.review_threshold)}</strong>. Set by developers; read-only here.</p>}
        <p>This application displays a routing recommendation. Flagged tickets are logged as pending for an administrator to inspect. Forwarding and approval remain manual steps outside this application.</p></Card></div>
    <Card><h2>Privacy and responsible use</h2><p>Ticket text goes to this application's API. Tickets flagged for manual review may be stored in a local server log. Submit synthetic or non-sensitive examples. Browser input and results disappear on reload; only your theme preference is stored in this browser.</p>
      <p>The Manual Review Log requires an administrator token. The token stays temporarily in React memory and is cleared when the log is locked or you leave that page. Local server logs can be lost on cloud redeployment without persistent storage.</p>
      <p>This demonstration access mechanism is not a complete production authentication system. Production use needs HTTPS, stronger authentication, rate limiting, a customer-data retention policy, and independent real-world validation.</p></Card>
    <p className={styles.source}>Method: TF-IDF + Logistic Regression · Source: models/evaluation.json · No paid AI API</p>
  </div>;
}
