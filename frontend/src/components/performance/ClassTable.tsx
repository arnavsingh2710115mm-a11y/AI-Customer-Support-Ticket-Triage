import { Meter } from '../ui';
import { classRows, weakestClass } from '../../lib/evaluation';
import { count, metric } from '../../lib/format';
import type { ClassifierEvaluation, ClassReport } from '../../lib/types';
import styles from './Performance.module.css';

export function ClassTable({ evaluation }: { evaluation: ClassifierEvaluation }) {
  function row(label: string, report: ClassReport) {
    return <tr key={label}><th scope="row">{label}</th>
      {(['precision', 'recall', 'f1-score'] as const).map(key => <td key={key}>
        <div className={styles.inlineScore}><Meter value={report[key]} label={label + ' ' + key} small />
          <span className="mono">{metric(report[key])}</span></div></td>)}
      <td className="mono">{count(report.support)}</td></tr>;
  }
  return <section aria-labelledby="class-table-title">
    <div className={styles.sectionHeading}><div><h2 id="class-table-title">Class-wise performance</h2><p>See the balance between precision and coverage for each class.</p></div></div>
    <div className={styles.tableScroll}><table className={styles.classTable}>
      <caption className="sr-only">Precision, recall, F1 score, and support for each class and aggregate averages</caption>
      <thead><tr><th scope="col">Class</th><th scope="col">Precision</th><th scope="col">Recall</th><th scope="col">F1-score</th><th scope="col">Support</th></tr></thead>
      <tbody>{classRows(evaluation).map(item => row(item.label, item.report))}</tbody>
      <tfoot>{row('Macro average', evaluation.class_wise_and_averages['macro avg'])}
        {row('Weighted average', evaluation.class_wise_and_averages['weighted avg'])}</tfoot>
    </table></div>
    <div className={styles.tableFoot}><span>Weakest class by F1: <strong>{weakestClass(evaluation).label}</strong></span>
      <span>Support = held-out test tickets · bars share a 0–100% scale</span></div>
  </section>;
}
