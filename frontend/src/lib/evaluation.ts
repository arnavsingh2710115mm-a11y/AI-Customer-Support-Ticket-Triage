import type { ClassifierEvaluation, ClassReport } from './types';

export function classRows(evaluation: ClassifierEvaluation) {
  return evaluation.label_order.map(label => ({
    label,
    report: evaluation.class_wise_and_averages[label] as ClassReport,
  }));
}
export function weakestClass(evaluation: ClassifierEvaluation) {
  return classRows(evaluation).reduce((lowest, current) =>
    current.report['f1-score'] < lowest.report['f1-score'] ? current : lowest);
}
export function largestConfusion(evaluation: ClassifierEvaluation) {
  let largest: { actual: string; predicted: string; count: number; total: number } | null = null;
  evaluation.confusion_matrix.forEach((row, rowIndex) => {
    row.forEach((value, columnIndex) => {
      if (rowIndex !== columnIndex && value > 0 && (!largest || value > largest.count)) {
        largest = {
          actual: evaluation.label_order[rowIndex], predicted: evaluation.label_order[columnIndex],
          count: value, total: row.reduce((sum, cell) => sum + cell, 0),
        };
      }
    });
  });
  return largest as { actual: string; predicted: string; count: number; total: number } | null;
}
