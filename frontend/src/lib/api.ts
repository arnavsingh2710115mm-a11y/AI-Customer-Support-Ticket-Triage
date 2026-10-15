import type {
  ClassifierEvaluation, ClassReport, EvaluationResponse, HealthResponse, InputRules, TriageResponse,
} from './types';

export class ApiError extends Error {
  constructor(public code: string, message: string, public status = 0) { super(message); }
}
export const asApiError = (error: unknown) => error instanceof ApiError ? error
  : new ApiError('UNEXPECTED_ERROR', 'Something went wrong. Please try again.');
export const isAborted = (error: unknown) => error instanceof DOMException && error.name === 'AbortError';
const object = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
const number = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
const probability = (value: unknown): value is number => number(value) && value >= 0 && value <= 1;
const integer = (value: unknown): value is number => number(value) && value >= 0 && Number.isInteger(value);
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(v => typeof v === 'string');
function unexpected(): never {
  throw new ApiError('INVALID_RESPONSE', 'The API returned an unexpected response. Check that the frontend and API versions match.');
}
async function request(path: string, signal: AbortSignal, init?: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(path, { ...init, signal, headers: { 'Content-Type': 'application/json' } });
  } catch (error) {
    if (isAborted(error)) throw error;
    throw new ApiError('API_UNREACHABLE', 'Cannot reach the local API. Start it from the project folder: python -m uvicorn api.main:app --port 8000');
  }
  if (!response.ok) {
    let body: unknown;
    try { body = await response.json(); } catch { /* A stopped Vite proxy may return plain text. */ }
    if (object(body) && object(body.error) && typeof body.error.code === 'string' && typeof body.error.message === 'string') {
      throw new ApiError(body.error.code, body.error.message, response.status);
    }
    if (response.status === 502 || response.status === 504 || response.status === 500) {
      throw new ApiError('API_UNREACHABLE', 'The local API is unavailable. Start it from the project folder: python -m uvicorn api.main:app --port 8000', response.status);
    }
    throw new ApiError('HTTP_ERROR', 'The request could not be completed. Please retry.', response.status);
  }
  return response;
}
async function json(path: string, signal: AbortSignal, init?: RequestInit): Promise<unknown> {
  const response = await request(path, signal, init);
  try { return await response.json(); } catch { return unexpected(); }
}
export function parseHealth(data: unknown): HealthResponse {
  if (!object(data) || data.status !== 'ok' || typeof data.models_loaded !== 'boolean'
    || !probability(data.review_threshold) || !object(data.models)
    || typeof data.models.category !== 'boolean' || typeof data.models.urgency !== 'boolean') unexpected();
  return data as unknown as HealthResponse;
}
export function parseTriage(data: unknown): TriageResponse {
  if (!object(data) || !object(data.category) || !object(data.urgency) || !object(data.decision)) unexpected();
  const categories = ['Billing', 'Technical', 'Account', 'Product'];
  const urgencies = ['Low', 'Medium', 'High'];
  const queues = ['Billing Support', 'Technical Support', 'Account Support', 'Product Support'];
  for (const [prediction, labels] of [[data.category, categories], [data.urgency, urgencies]] as const) {
    if (!labels.includes(String(prediction.label)) || !probability(prediction.confidence)) unexpected();
    if (prediction.probabilities !== undefined) {
      const values = prediction.probabilities;
      if (!object(values) || Object.keys(values).length !== labels.length
        || !labels.every(label => probability(values[label]))) unexpected();
    }
  }
  const decision = data.decision;
  if (typeof decision.needs_review !== 'boolean' || !strings(decision.reasons)
    || !queues.includes(String(decision.suggested_queue)) || !probability(data.review_threshold)
    || (decision.needs_review ? decision.assigned_queue !== null : !queues.includes(String(decision.assigned_queue)))) unexpected();
  return data as unknown as TriageResponse;
}
function validReport(value: unknown): value is ClassReport {
  return object(value) && probability(value.precision) && probability(value.recall)
    && probability(value['f1-score']) && integer(value.support);
}
function validClassifier(value: unknown): value is ClassifierEvaluation {
  if (!object(value) || !probability(value.accuracy) || !strings(value.label_order) || !value.label_order.length
    || !object(value.class_wise_and_averages) || !Array.isArray(value.confusion_matrix)) return false;
  const labels = value.label_order;
  const report = value.class_wise_and_averages;
  return probability(report.accuracy) && [...labels, 'macro avg', 'weighted avg'].every(label => validReport(report[label]))
    && value.confusion_matrix.length === labels.length
    && value.confusion_matrix.every(row => Array.isArray(row) && row.length === labels.length && row.every(integer));
}
export function parseEvaluation(data: unknown): EvaluationResponse {
  if (!object(data) || !validClassifier(data.category) || !validClassifier(data.urgency)) unexpected();
  for (const key of ['training_rows', 'test_rows', 'random_seed']) {
    if (data[key] !== undefined && !integer(data[key])) unexpected();
  }
  if (data.data_notice !== undefined && typeof data.data_notice !== 'string') unexpected();
  return data as unknown as EvaluationResponse;
}
export async function getHealth(signal: AbortSignal) { return parseHealth(await json('/api/health', signal)); }
export async function getEvaluation(signal: AbortSignal) { return parseEvaluation(await json('/api/evaluation', signal)); }
export async function triage(text: string, signal: AbortSignal) {
  return parseTriage(await json('/api/triage', signal, { method: 'POST', body: JSON.stringify({ text }) }));
}
export async function getInputRules(signal: AbortSignal): Promise<InputRules> {
  const data = await json('/api/openapi.json', signal);
  if (!object(data) || !object(data.components) || !object(data.components.schemas)) unexpected();
  const schema = data.components.schemas.TriageRequest;
  if (!object(schema) || !object(schema.properties) || !object(schema.properties.text)) unexpected();
  const text = schema.properties.text;
  if (!integer(text.minLength) || !integer(text.maxLength) || text.minLength > text.maxLength) unexpected();
  return { minLength: text.minLength, maxLength: text.maxLength };
}
export async function downloadEvaluation(signal: AbortSignal) {
  const response = await request('/api/evaluation/download', signal);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = 'evaluation.json';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
