import { useEffect, useId, useRef } from 'react';
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from 'react';
import { AlertCircle, Check, Info, LoaderCircle, X } from 'lucide-react';
import { percent } from '../../lib/format';
import styles from './Ui.module.css';

export function Button({ variant = 'secondary', loading = false, children, className = '', disabled, ...props }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost'; loading?: boolean }) {
  return <button {...props} className={[styles.button, styles[variant], className].join(' ')}
    disabled={disabled || loading} aria-busy={loading || undefined}>
    {loading && <LoaderCircle aria-hidden="true" className={styles.spinner} />}{children}
  </button>;
}
export function Card({ children, className = '', ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={styles.card + ' ' + className}>{children}</div>;
}
export type Tone = 'neutral' | 'accent' | 'review' | 'high' | 'medium' | 'low';
export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: Tone }) {
  return <span className={styles.badge + ' ' + styles[tone]}>{children}</span>;
}
export function Tooltip({ children, text }: { children: ReactNode; text: string }) {
  const id = useId();
  return <span className={styles.tooltip} aria-describedby={id}>{children}
    <span role="tooltip" id={id} className={styles.tooltipText}>{text}</span>
  </span>;
}
export function Popover({ label, children }: { label: ReactNode; children: ReactNode }) {
  return <details className={styles.popover} onKeyDown={event => {
    if (event.key === 'Escape') { event.currentTarget.open = false; event.currentTarget.querySelector('summary')?.focus(); }
  }}><summary>{label}</summary>
    <div className={styles.popoverContent}>{children}</div></details>;
}
export function Meter({ value, threshold, label, small = false }:
  { value: number; threshold?: number; label: string; small?: boolean }) {
  const below = threshold !== undefined && value < threshold;
  return <Tooltip text={threshold === undefined ? label : 'Review threshold ' + percent(threshold) + ' · Set by developers'}>
    <span className={styles.meterFocus} role="meter" tabIndex={0} aria-label={label}
      aria-valuemin={0} aria-valuemax={100} aria-valuenow={value * 100}
      aria-valuetext={(value * 100).toFixed(1) + '%' + (threshold === undefined ? '' : '; review threshold ' + (threshold * 100) + '%')}>
      <span className={styles.meter + (small ? ' ' + styles.smallMeter : '')}>
        <span className={styles.meterFill + (below ? ' ' + styles.reviewFill : '')} style={{ width: (value * 100) + '%' }} />
        {threshold !== undefined && <span className={styles.tick} style={{ left: (threshold * 100) + '%' }} />}
      </span>
    </span>
  </Tooltip>;
}
export function Tabs<T extends string>({ label, options, value, onChange }:
  { label: string; options: { value: T; label: string }[]; value: T; onChange: (value: T) => void }) {
  const controls = useRef<(HTMLButtonElement | null)[]>([]);
  return <div className={styles.tabs} role="tablist" aria-label={label}>
    {options.map((option, index) => <button key={option.value} type="button" role="tab"
      aria-selected={value === option.value} tabIndex={value === option.value ? 0 : -1}
      ref={node => { controls.current[index] = node; }}
      onClick={() => onChange(option.value)} onKeyDown={event => {
        let next: number | undefined;
        if (event.key === 'ArrowRight') next = (index + 1) % options.length;
        if (event.key === 'ArrowLeft') next = (index + options.length - 1) % options.length;
        if (event.key === 'Home') next = 0;
        if (event.key === 'End') next = options.length - 1;
        if (next !== undefined) { event.preventDefault(); onChange(options[next].value); controls.current[next]?.focus(); }
      }}>{option.label}</button>)}
  </div>;
}
export function Skeleton({ label = 'Loading', lines = 3 }: { label?: string; lines?: number }) {
  return <div role="status" aria-label={label} className={styles.skeletonGroup}>
    {Array.from({ length: lines }, (_, index) => <div key={index} className={styles.skeleton} aria-hidden="true" />)}
    <span className="sr-only">{label}</span>
  </div>;
}
export function Banner({ children, error = false, onRetry }:
  { children: ReactNode; error?: boolean; onRetry?: () => void }) {
  return <div className={styles.banner + (error ? ' ' + styles.error : '')} role={error ? 'alert' : 'note'}>
    {error ? <AlertCircle size={20} aria-hidden="true" /> : <Info size={20} aria-hidden="true" />}
    <div>{children}</div>{onRetry && <Button onClick={onRetry}>Retry</Button>}
  </div>;
}
export function EmptyState({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return <div className={styles.empty}><span className={styles.emptyIcon}>{icon}</span><h2>{title}</h2><div>{children}</div></div>;
}
export function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  useEffect(() => {
    const timeout = setTimeout(onClose, 4500);
    return () => clearTimeout(timeout);
  }, [message, onClose]);
  return <div className={styles.toast} role="status"><Check size={18} aria-hidden="true" />
    <span>{message}</span><Button variant="ghost" onClick={onClose} aria-label="Dismiss notification"><X /></Button>
  </div>;
}
