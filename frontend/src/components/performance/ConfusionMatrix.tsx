import { useRef, useState } from 'react';
import { Tabs } from '../ui';
import { confidence, count } from '../../lib/format';
import { largestConfusion } from '../../lib/evaluation';
import type { ClassifierEvaluation } from '../../lib/types';
import styles from './Performance.module.css';

export function ConfusionMatrix({ evaluation }: { evaluation: ClassifierEvaluation }) {
  const [mode, setMode] = useState<'counts' | 'rate'>('counts');
  const [active, setActive] = useState<[number, number] | null>(null);
  const cells = useRef<(HTMLTableCellElement | null)[][]>([]);
  const labels = evaluation.label_order;
  const largest = largestConfusion(evaluation);
  function description(row: number, column: number) {
    const values = evaluation.confusion_matrix[row];
    const total = values.reduce((sum, value) => sum + value, 0);
    const value = values[column];
    return 'Actual ' + labels[row] + ' → predicted ' + labels[column] + ': ' + value + ' of ' + total
      + ' (' + confidence(total ? value / total : 0) + ')';
  }
  return <section aria-labelledby="confusion-title" className={styles.matrixSection}>
    <div className={styles.sectionHeading}><div><h2 id="confusion-title">Where predictions land</h2><p>Confusion matrix · rows are actual, columns are predicted.</p></div>
      <Tabs label="Confusion matrix display" value={mode} onChange={setMode}
        options={[{ value: 'counts', label: 'Counts' }, { value: 'rate', label: '% of actual class' }]} />
    </div>
    <div className={styles.tableScroll} role="region" aria-label="Confusion matrix; scroll horizontally for all columns" tabIndex={0}>
      <table className={styles.matrix} aria-label="Confusion matrix: actual rows and predicted columns">
        <caption>Predicted class →</caption>
        <thead><tr><th scope="col">Actual class ↓</th>{labels.map((label, column) =>
          <th scope="col" key={label} className={active?.[1] === column ? styles.highlightHeader : ''}>{label}</th>)}<th scope="col">Total</th></tr></thead>
        <tbody>{evaluation.confusion_matrix.map((row, rowIndex) => {
          const total = row.reduce((sum, value) => sum + value, 0);
          return <tr key={labels[rowIndex]}>
            <th scope="row" className={active?.[0] === rowIndex ? styles.highlightHeader : ''}>{labels[rowIndex]}</th>
            {row.map((value, columnIndex) => {
              const rate = total ? value / total : 0;
              const highlighted = active?.[0] === rowIndex || active?.[1] === columnIndex;
              const text = description(rowIndex, columnIndex);
              return <td key={columnIndex} tabIndex={0} aria-label={text}
                className={styles.matrixCell + (highlighted ? ' ' + styles.highlightCell : '')}
                style={{ background: 'color-mix(in srgb, var(' + (rowIndex === columnIndex ? '--accent' : '--rust')
                  + ') ' + (rate * 25) + '%, var(--surface))' }}
                ref={node => { if (!cells.current[rowIndex]) cells.current[rowIndex] = []; cells.current[rowIndex][columnIndex] = node; }}
                onMouseEnter={() => setActive([rowIndex, columnIndex])} onMouseLeave={event => {
                  if (document.activeElement !== event.currentTarget) setActive(null);
                }}
                onFocus={() => setActive([rowIndex, columnIndex])} onBlur={() => setActive(null)}
                onKeyDown={event => {
                  let rowTarget = rowIndex; let columnTarget = columnIndex;
                  if (event.key === 'ArrowRight') columnTarget = (columnIndex + 1) % labels.length;
                  else if (event.key === 'ArrowLeft') columnTarget = (columnIndex + labels.length - 1) % labels.length;
                  else if (event.key === 'ArrowDown') rowTarget = (rowIndex + 1) % labels.length;
                  else if (event.key === 'ArrowUp') rowTarget = (rowIndex + labels.length - 1) % labels.length;
                  else return;
                  event.preventDefault(); cells.current[rowTarget][columnTarget]?.focus();
                }}>
                <span className="mono">{mode === 'counts' ? count(value) : confidence(rate)}</span>
                <span className={styles.cellTooltip} role="tooltip">{text}</span>
              </td>;
            })}
            <td className={styles.total + ' mono'}>{count(total)}</td>
          </tr>;
        })}</tbody>
      </table>
    </div>
    <div className={styles.matrixLegend}><span><i className={styles.correctSwatch} />Correct predictions</span>
      <span><i className={styles.errorSwatch} />Misclassifications</span><span>Darker = higher share of the actual class</span></div>
    <p className={styles.matrixDescription} aria-live="polite">{active ? description(active[0], active[1]) : 'Hover or focus a cell for detail. Use arrow keys to move between cells.'}</p>
    <div className={styles.takeaway}>{largest
      ? 'Largest confusion: ' + largest.actual + ' tickets predicted as ' + largest.predicted + ' (' + largest.count + ' of ' + largest.total + ').'
      : 'There are no off-diagonal errors in this saved confusion matrix.'}</div>
  </section>;
}
