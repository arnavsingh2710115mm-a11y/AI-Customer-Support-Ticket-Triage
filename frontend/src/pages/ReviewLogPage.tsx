import { useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, ClipboardList, LockKeyhole, RefreshCw, ShieldCheck, X } from 'lucide-react';
import { Badge, Banner, Button, Card, EmptyState, Skeleton } from '../components/ui';
import type { Tone } from '../components/ui';
import { asApiError, getReviewLog, isAborted } from '../lib/api';
import type { ApiError } from '../lib/api';
import { confidence, count } from '../lib/format';
import type { ReviewLogResponse, ReviewRecord } from '../lib/types';
import styles from './ReviewLog.module.css';

const utcTime = (timestamp: string) => new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC',
}).format(new Date(timestamp));

// Credentials and customer records exist only in this page's React state.
// Leaving the route unmounts this page, aborts its requests, and releases that state.
export function ReviewLogPage() {
  const [draftToken, setDraftToken] = useState('');
  const [token, setToken] = useState('');
  const [data, setData] = useState<ReviewLogResponse | null>(null);
  const [selected, setSelected] = useState<ReviewRecord | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [attempt, setAttempt] = useState(0);
  const activeRequest = useRef<AbortController | null>(null);
  const detailHeading = useRef<HTMLHeadingElement>(null);
  const tokenInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    activeRequest.current = controller;
    setLoading(true); setError(null); setData(null); setSelected(null);
    void getReviewLog(token, page, pageSize, controller.signal).then(result => {
      if (controller.signal.aborted) return;
      if (result.total_pages > 0 && page > result.total_pages) setPage(result.total_pages);
      else setData(result);
    }).catch(cause => {
      if (controller.signal.aborted || isAborted(cause)) return;
      const failure = asApiError(cause);
      setError(failure);
      if (failure.status === 401) {
        setToken(''); setDraftToken(''); setData(null); setSelected(null);
      }
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [token, page, pageSize, attempt]);
  useEffect(() => { if (selected) detailHeading.current?.focus(); }, [selected]);

  function lock() {
    activeRequest.current?.abort();
    setToken(''); setDraftToken(''); setData(null); setSelected(null);
    setError(null); setLoading(false); setPage(1);
    requestAnimationFrame(() => tokenInput.current?.focus());
  }
  function closeDetails() {
    const id = selected?.ticket_id;
    setSelected(null);
    if (id) document.getElementById('open-review-' + id)?.focus();
  }
  return <div className={styles.page}>
    <div className={styles.pageHeader}><div><h1>Keep uncertain tickets in view.</h1>
      <p>Inspect actual tickets flagged by the models. All review records are pending.</p></div>
      {token && <Button onClick={lock}><LockKeyhole aria-hidden="true" />Lock & clear</Button>}</div>
    {error && <Banner error onRetry={token ? () => setAttempt(value => value + 1) : undefined}>
      <strong>{error.status === 401 ? 'Administrator access required' : error.code === 'REVIEW_ACCESS_DISABLED' ? 'Review access is disabled' : 'Review log unavailable'}</strong>
      <p>{error.message}</p></Banner>}
    {!token ? <Card className={styles.authCard}>
      <span className={styles.authIcon}><LockKeyhole size={24} aria-hidden="true" /></span>
      <h2>Administrator access</h2>
      <p>Review records may contain customer information. Enter the server's administrator token to unlock this page.</p>
      <form onSubmit={event => {
        event.preventDefault();
        if (!draftToken.trim()) return;
        setPage(1); setError(null); setToken(draftToken.trim()); setDraftToken('');
      }}>
        <label htmlFor="review-admin-token">Administrator token</label>
        <input id="review-admin-token" ref={tokenInput} type="password" autoComplete="off" spellCheck={false}
          autoCapitalize="none" value={draftToken} onChange={event => setDraftToken(event.target.value)}
          aria-describedby="review-token-help" required />
        <p id="review-token-help" className={styles.helper}>Used only for this session in memory. Locking or leaving this page clears access and loaded records.</p>
        <Button variant="primary" type="submit" disabled={!draftToken.trim()}><ShieldCheck aria-hidden="true" />Unlock review log</Button>
      </form>
      <p className={styles.setupNote}>Access must be enabled with ADMIN_REVIEW_TOKEN on the server. This demonstration token is not a complete production authentication system.</p>
    </Card> : <>
      <div className={styles.toolbar}>
        <span className={styles.accessNotice}><ShieldCheck size={17} aria-hidden="true" />Administrator view <span>· Newest first</span></span>
        <div className={styles.tableControls}>
          <label htmlFor="review-page-size">Rows per page</label>
          <select id="review-page-size" value={pageSize} onChange={event => { setPageSize(Number(event.target.value)); setPage(1); }}>
            {[10, 20, 50].map(size => <option key={size} value={size}>{size}</option>)}
          </select>
          <Button onClick={() => setAttempt(value => value + 1)} disabled={loading}><RefreshCw aria-hidden="true" />Refresh</Button>
        </div>
      </div>
      {loading ? <Card><Skeleton label="Loading private review records" lines={5} /></Card>
        : data && (data.items.length === 0 ? <Card><EmptyState icon={<ClipboardList size={24} />} title="No tickets waiting here">
          <p>No manual-review records have been stored. Only tickets flagged by the models appear here.</p>
        </EmptyState></Card> : <Card className={styles.recordsCard}>
          <ReviewRecords records={data.items} onOpen={setSelected} />
          <div className={styles.pagination}>
            <span>{count(data.total)} {data.total === 1 ? 'record' : 'records'} · Page {count(data.page)} of {count(data.total_pages)}</span>
            <div><Button disabled={page <= 1} onClick={() => setPage(value => value - 1)} aria-label="Previous review records page"><ChevronLeft aria-hidden="true" />Previous</Button>
              <Button disabled={page >= data.total_pages} onClick={() => setPage(value => value + 1)} aria-label="Next review records page">Next<ChevronRight aria-hidden="true" /></Button></div>
          </div>
        </Card>)}
      {selected && <section className={styles.detail} aria-labelledby="review-detail-title" onKeyDown={event => { if (event.key === 'Escape') closeDetails(); }}>
        <Card><div className={styles.detailHeader}><div><Badge tone="review">Pending review</Badge>
          <h2 id="review-detail-title" ref={detailHeading} tabIndex={-1}>Ticket details</h2></div>
          <Button variant="ghost" onClick={closeDetails} aria-label="Close ticket details"><X aria-hidden="true" /></Button></div>
          <ReviewDetails record={selected} />
        </Card>
      </section>}
      <p className={styles.privacyNote}>This page shows server-stored review records. Lock it when finished. Inspecting a record does not approve it or forward it to a support team.</p>
    </>}
  </div>;
}

export function ReviewRecords({ records, onOpen }: { records: ReviewRecord[]; onOpen: (record: ReviewRecord) => void }) {
  return <div className={styles.tableScroll} role="region" aria-label="Manual review records; scroll horizontally for all columns" tabIndex={0}>
    <table className={styles.table}><caption className="sr-only">Tickets requiring manual review, newest first. Submission times are in UTC.</caption>
      <thead><tr><th scope="col">Ticket ID</th><th scope="col">Submitted (UTC)</th><th scope="col">Category</th><th scope="col">Urgency</th><th scope="col">Suggested team</th><th scope="col">Status</th><th scope="col"><span className="sr-only">Details</span></th></tr></thead>
      <tbody>{records.map(record => <tr key={record.ticket_id}>
        <th scope="row"><span className={styles.ticketId + ' mono'}>{record.ticket_id}</span></th>
        <td><time dateTime={record.timestamp}>{utcTime(record.timestamp)}</time></td>
        <td><strong>{record.category}</strong><span className={styles.confidence + ' mono'}>{confidence(record.category_confidence)} confidence</span></td>
        <td><Badge tone={record.urgency.toLowerCase() as Tone}>{record.urgency}</Badge><span className={styles.confidence + ' mono'}>{confidence(record.urgency_confidence)} confidence</span></td>
        <td>{record.suggested_queue}</td><td><Badge tone="review">Pending</Badge></td>
        <td><Button id={'open-review-' + record.ticket_id} onClick={() => onOpen(record)} aria-label={'View ticket ' + record.ticket_id}>View</Button></td>
      </tr>)}</tbody>
    </table>
  </div>;
}

export function ReviewDetails({ record }: { record: ReviewRecord }) {
  return <>
    <dl className={styles.detailGrid}>
      <div><dt>Ticket ID</dt><dd className="mono">{record.ticket_id}</dd></div>
      <div><dt>Submitted (UTC)</dt><dd><time dateTime={record.timestamp}>{utcTime(record.timestamp)}</time></dd></div>
      <div><dt>Category prediction</dt><dd>{record.category} <span className="mono">· {confidence(record.category_confidence)}</span></dd></div>
      <div><dt>Urgency prediction</dt><dd>{record.urgency} <span className="mono">· {confidence(record.urgency_confidence)}</span></dd></div>
      <div><dt>Suggested support team</dt><dd>{record.suggested_queue}</dd></div>
      <div><dt>Review status</dt><dd>Pending</dd></div>
    </dl>
    <h3 className={styles.detailLabel}>Original ticket</h3><p className={styles.complaint}>{record.ticket_text}</p>
    <h3 className={styles.detailLabel}>Why manual review is required</h3>
    <ul className={styles.reasons}>{record.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>
  </>;
}
