// Mirrors api/schemas.py and the actual saved evaluation.json structure.
export type Category = 'Billing' | 'Technical' | 'Account' | 'Product';
export type Urgency = 'Low' | 'Medium' | 'High';
export type SupportQueue = 'Billing Support' | 'Technical Support' | 'Account Support' | 'Product Support';
export interface Prediction<L extends string> {
  label: L;
  confidence: number;
  probabilities?: Record<L, number>;
}
export interface TriageResponse {
  category: Prediction<Category>;
  urgency: Prediction<Urgency>;
  decision: {
    needs_review: boolean;
    reasons: string[];
    assigned_queue: SupportQueue | null;
    suggested_queue: SupportQueue;
  };
  review_threshold: number;
}
export interface HealthResponse {
  status: 'ok';
  models_loaded: boolean;
  review_threshold: number;
  models: { category: boolean; urgency: boolean };
}
export interface ClassReport {
  precision: number;
  recall: number;
  'f1-score': number;
  support: number;
}
export interface ClassificationReport {
  [key: string]: ClassReport | number;
  accuracy: number;
  'macro avg': ClassReport;
  'weighted avg': ClassReport;
}
export interface ClassifierEvaluation {
  accuracy: number;
  class_wise_and_averages: ClassificationReport;
  confusion_matrix: number[][];
  label_order: string[];
}
export interface EvaluationResponse {
  data_notice?: string;
  random_seed?: number;
  training_rows?: number;
  test_rows?: number;
  category: ClassifierEvaluation;
  urgency: ClassifierEvaluation;
}
export interface InputRules { minLength: number; maxLength: number }
export interface CompletedTriage { result: TriageResponse; elapsedMs: number; text: string }
export interface ReviewRecord {
  ticket_id: string;
  timestamp: string;
  ticket_text: string;
  category: Category;
  category_confidence: number;
  urgency: Urgency;
  urgency_confidence: number;
  reasons: string[];
  suggested_queue: SupportQueue;
  status: 'pending';
}
export interface ReviewLogResponse {
  items: ReviewRecord[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}
