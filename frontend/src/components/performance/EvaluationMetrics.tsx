import { Info } from 'lucide-react';
import { Card } from '../ui';
import { count, metric } from '../../lib/format';
import type { ClassifierEvaluation } from '../../lib/types';
import styles from './Performance.module.css';

export function EvaluationMetrics({ evaluation, testSize }: { evaluation: ClassifierEvaluation; testSize?: number }) {
  const average = evaluation.class_wise_and_averages['macro avg'];
  return <>
    <div className={styles.kpiGrid}>{[
      { label: 'Accuracy', value: evaluation.accuracy, explanation: 'Correct predictions across all test tickets' },
      { label: 'Precision (macro)', value: average.precision, explanation: 'How often predicted classes were correct' },
      { label: 'Recall (macro)', value: average.recall, explanation: 'How much of each actual class was found' },
      { label: 'F1 (macro)', value: average['f1-score'], explanation: 'Balance of precision and recall' },
    ].map(item => <Card key={item.label} className={styles.kpi}><h2>{item.label}</h2>
      <strong className="mono">{metric(item.value)}</strong><p>{item.explanation}</p>
      {testSize !== undefined && <small className="mono">n = {count(testSize)}</small>}</Card>)}</div>
    <p className={styles.sampleNote}><Info size={15} aria-hidden="true" />
      {testSize !== undefined && testSize > 0 ? 'Each test ticket is about ' + (100 / testSize).toFixed(1) + '% of the accuracy score. ' : ''}
      Macro averages give each class equal weight.</p>
  </>;
}
