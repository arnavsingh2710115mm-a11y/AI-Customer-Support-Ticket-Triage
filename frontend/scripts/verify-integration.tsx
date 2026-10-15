import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  ApiError, getEvaluation, getHealth, getInputRules, getReviewLog, isAborted, parseEvaluation, parseHealth, parseReviewLog, parseTriage, triage,
} from '../src/lib/api';
import { confidence, count, metric } from '../src/lib/format';
import { EXAMPLE_INPUTS } from '../src/lib/examples';
import { EvaluationMetrics } from '../src/components/performance/EvaluationMetrics';
import { ClassTable } from '../src/components/performance/ClassTable';
import { ConfusionMatrix } from '../src/components/performance/ConfusionMatrix';
import { ResultPanel } from '../src/components/triage/ResultPanel';
import { ReviewDetails, ReviewLogPage, ReviewRecords } from '../src/pages/ReviewLogPage';
import { TriagePage } from '../src/pages/TriagePage';
import { ticketLength } from '../src/lib/ticketText';
import type { ClassReport } from '../src/lib/types';

const base = process.env.VERIFY_API_URL ?? 'http://127.0.0.1:8000';
const originalFetch = globalThis.fetch;
globalThis.fetch = (input, init) => originalFetch(new URL(String(input), base), init);
const signal = () => new AbortController().signal;
const mode = process.env.VERIFY_MODE ?? 'normal';
const decode = (text: string) => text.replace(/<span[^>]*role="tooltip"[^>]*>.*?<\/span>/g, '')
  .replace(/<[^>]*>/g, '').replace(/&amp;/g, '&').replace(/&#x27;/g, "'");

if (mode === 'unreachable') {
  test('Stopped API produces actionable unreachable error without losing client data', async () => {
    await assert.rejects(getHealth(signal()), error => error instanceof ApiError && error.code === 'API_UNREACHABLE'
      && error.message.includes('python -m uvicorn'));
  });
} else if (mode === 'missing-evaluation') {
  test('Missing evaluation is surfaced with the actual API fix instruction', async () => {
    await assert.rejects(getEvaluation(signal()), error => error instanceof ApiError
      && error.code === 'EVALUATION_MISSING' && error.status === 404 && error.message.includes('EVALUATION_PATH'));
    assert.equal((await getHealth(signal())).models_loaded, true);
  });
} else {
  const health = await getHealth(signal());
  const evaluation = await getEvaluation(signal());
  const saved = JSON.parse(await readFile('../models/evaluation.json', 'utf8'));

  test('Typed client reads actual health and input limits', async () => {
    assert.equal(health.models_loaded, true);
    const rules = await getInputRules(signal());
    const schema = await (await originalFetch(base + '/api/openapi.json')).json();
    assert.equal(rules.minLength, schema.components.schemas.TriageRequest.properties.text.minLength);
    assert.equal(rules.maxLength, schema.components.schemas.TriageRequest.properties.text.maxLength);
  });
  test('Unexpected response shapes fail clearly', () => {
    for (const parse of [parseHealth, parseTriage, parseEvaluation, parseReviewLog]) {
      assert.throws(() => parse({}), error => error instanceof ApiError && error.code === 'INVALID_RESPONSE');
    }
  });
  test('Abort signals are honored', async () => {
    const controller = new AbortController(); controller.abort();
    await assert.rejects(getHealth(controller.signal), isAborted);
  });
  test('Evaluation values and original download bytes match protected source', async () => {
    assert.deepEqual(evaluation, saved);
    const download = await originalFetch(base + '/api/evaluation/download');
    assert.equal(download.status, 200);
    assert.deepEqual(Buffer.from(await download.arrayBuffer()), await readFile('../models/evaluation.json'));
  });
  for (const classifier of ['category', 'urgency'] as const) {
    const current = evaluation[classifier];
    const original = saved[classifier];
    test(classifier + ': all rendered KPI values match saved evaluation', () => {
      const html = renderToStaticMarkup(<EvaluationMetrics evaluation={current} testSize={evaluation.test_rows} />);
      const rendered = [...html.matchAll(/<strong[^>]*>(.*?)<\/strong>/g)].map(match => decode(match[1]));
      const report = original.class_wise_and_averages['macro avg'];
      assert.deepEqual(rendered, [original.accuracy, report.precision, report.recall, report['f1-score']].map(metric));
    });
    test(classifier + ': every class and aggregate table cell matches saved evaluation', () => {
      const html = renderToStaticMarkup(<ClassTable evaluation={current} />);
      const rows = [...html.matchAll(/<tr[^>]*>(.*?)<\/tr>/g)].slice(1).map(match =>
        [...match[1].matchAll(/<(?:td|th)[^>]*>(.*?)<\/(?:td|th)>/g)].map(cell => decode(cell[1])));
      const labels = [...current.label_order, 'macro avg', 'weighted avg'];
      assert.deepEqual(rows, labels.map((label, index) => {
        const report = original.class_wise_and_averages[label] as ClassReport;
        return [
          index < current.label_order.length ? label : label === 'macro avg' ? 'Macro average' : 'Weighted average',
          metric(report.precision), metric(report.recall), metric(report['f1-score']), count(report.support),
        ];
      }));
    });
    test(classifier + ': every confusion matrix cell has the correct count and accessible detail', () => {
      const html = renderToStaticMarkup(<ConfusionMatrix evaluation={current} />);
      const actualCells = [...html.matchAll(/<td[^>]*aria-label="([^"]+)"[^>]*>(.*?)<\/td>/g)];
      assert.equal(actualCells.length, current.label_order.length ** 2);
      current.confusion_matrix.forEach((row, i) => row.forEach((value, j) => {
        const total = row.reduce((sum, item) => sum + item, 0);
        const cell = actualCells[i * row.length + j];
        assert.equal(cell[1], 'Actual ' + current.label_order[i] + ' → predicted ' + current.label_order[j]
          + ': ' + value + ' of ' + total + ' (' + confidence(total ? value / total : 0) + ')');
        assert.match(cell[2], new RegExp('>' + value + '</span>'));
      }));
    });
  }
  test('Three real client predictions and rendered results match direct ML and legacy Streamlit', async () => {
    const tickets = [EXAMPLE_INPUTS[0].text, EXAMPLE_INPUTS[1].text, EXAMPLE_INPUTS[4].text];
    const script = [
      'import json, sys',
      'from pathlib import Path',
      'sys.path.insert(0, str(Path.cwd().parent))',
      'from predict_ticket import load_ticket_models, predict_ticket',
      'from api.config import REVIEW_THRESHOLD',
      'from streamlit.testing.v1 import AppTest',
      'models = load_ticket_models()',
      'dashboard = AppTest.from_file(str(Path.cwd().parent / "app.py")).run(timeout=30)',
      'assert not dashboard.exception',
      'results = []',
      'for text in json.load(sys.stdin):',
      '    expected = predict_ticket(text, REVIEW_THRESHOLD, loaded_models=models)',
      '    dashboard.text_area[0].input(text)',
      '    dashboard.button[0].click().run(timeout=30)',
      '    assert not dashboard.exception',
      '    assert dashboard.session_state["prediction_result"] == expected',
      '    results.append(expected)',
      'print(json.dumps(results))',
    ].join('\n');
    const python = process.env.TICKET_PYTHON ?? process.env.USERPROFILE + '/anaconda3/envs/ticket_ai/python.exe';
    const direct = spawnSync(python, ['-B', '-c', script], {
      input: JSON.stringify(tickets), encoding: 'utf8',
      env: { ...process.env, STREAMLIT_BROWSER_GATHER_USAGE_STATS: 'false' },
    });
    assert.equal(direct.status, 0, direct.stderr);
    const expected = JSON.parse(direct.stdout);
    for (const [index, text] of tickets.entries()) {
      const started = performance.now();
      const actual = await triage(text, signal());
      const html = renderToStaticMarkup(<ResultPanel completed={{ result: actual, text, elapsedMs: Math.round(performance.now() - started) }} />);
      assert.equal(actual.category.label, expected[index].category);
      assert.equal(actual.urgency.label, expected[index].urgency);
      assert.equal(actual.category.confidence, expected[index].category_confidence);
      assert.equal(actual.urgency.confidence, expected[index].urgency_confidence);
      assert.equal(actual.decision.needs_review, expected[index].needs_manual_review);
      assert.equal(actual.decision.suggested_queue, expected[index].suggested_queue);
      assert.equal(actual.decision.assigned_queue, expected[index].needs_manual_review ? null : expected[index].queue);
      assert.ok(html.includes(confidence(actual.category.confidence)));
      assert.ok(html.includes(confidence(actual.urgency.confidence)));
      assert.ok(html.includes(actual.decision.suggested_queue));
    }
  });
  test('Composer counts Unicode code points and displays the actual API input limit', async () => {
    const rules = await getInputRules(signal());
    assert.equal(ticketLength('  😀 café\n'), 6);
    assert.equal(ticketLength('😀'.repeat(rules.maxLength)), rules.maxLength);
    assert.equal(ticketLength('😀'.repeat(rules.maxLength + 1)), rules.maxLength + 1);
    const bomInput = '\uFEFF' + 'a'.repeat(rules.minLength - 1);
    const controlInput = '\u0085\u001C' + 'a'.repeat(rules.minLength - 1);
    assert.equal(ticketLength(bomInput), rules.minLength);
    assert.equal(ticketLength(controlInput), rules.minLength - 1);
    assert.equal((await originalFetch(base + '/api/triage', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: bomInput }),
    })).status, 200);
    assert.equal((await originalFetch(base + '/api/triage', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: controlInput }),
    })).status, 422);
    const html = renderToStaticMarkup(<TriagePage text={'😀'.repeat(rules.minLength)} onTextChange={() => {}}
      onClassify={() => {}} completed={null} busy={false} error={null} rules={rules} connecting={false}
      connectionError={null} onReconnect={() => {}} />);
    assert.ok(html.includes(count(rules.minLength) + ' / ' + count(rules.maxLength)));
    assert.ok(html.includes('Tickets flagged for manual review may be stored'));
    assert.ok(html.includes('synthetic or non-sensitive'));
  });
  test('Review page starts locked without rendering customer records', () => {
    const html = renderToStaticMarkup(<ReviewLogPage />);
    assert.ok(html.includes('Administrator access'));
    assert.ok(html.includes('type="password"'));
    assert.ok(html.includes('Unlock review log'));
    assert.ok(!html.includes('<table'));
  });
  test('Review client rejects unauthenticated access with the actual authorization error', async () => {
    await assert.rejects(getReviewLog('', 1, 20, signal()), error => error instanceof ApiError
      && error.status === 401 && error.code === 'UNAUTHORIZED');
  });
  test('Review client sends the ephemeral token only in a header, disables caching, and renders actual records', async () => {
    const token = process.env.VERIFY_REVIEW_TOKEN;
    assert.ok(token, 'Validation requires an ephemeral server token in VERIFY_REVIEW_TOKEN');
    const previousFetch = globalThis.fetch;
    let checkedHeader = false;
    globalThis.fetch = (input, init) => {
      const url = new URL(String(input), base);
      assert.equal(url.pathname, '/api/review-log');
      assert.equal(url.search, '?page=1&page_size=20');
      assert.ok(!url.href.includes(token), 'Credential must never appear in a URL');
      assert.ok(new Headers(init?.headers).get('Authorization') === 'Bearer ' + token, 'Authorization must use the Bearer header');
      assert.equal(init?.cache, 'no-store');
      checkedHeader = true;
      return previousFetch(input, init);
    };
    let records;
    try { records = await getReviewLog(token, 1, 20, signal()); }
    finally { globalThis.fetch = previousFetch; }
    assert.ok(checkedHeader);
    const response = await originalFetch(base + '/api/review-log?page=1&page_size=20', {
      headers: { Authorization: 'Bearer ' + token }, cache: 'no-store',
    });
    assert.equal(response.status, 200);
    assert.deepEqual(records, await response.json());
    assert.ok(records.items.length > 0, 'Earlier genuine ML predictions should create review records');
    const table = renderToStaticMarkup(<ReviewRecords records={records.items} onOpen={() => {}} />);
    assert.equal([...table.matchAll(/<tr>/g)].length, records.items.length + 1);
    for (const record of records.items) {
      assert.ok(table.includes(record.ticket_id));
      assert.ok(table.includes(record.category));
      assert.ok(table.includes(confidence(record.category_confidence)));
      assert.ok(table.includes(confidence(record.urgency_confidence)));
      assert.ok(table.includes(record.suggested_queue));
      assert.ok(table.includes('dateTime="' + record.timestamp + '"'));
      const detail = renderToStaticMarkup(<ReviewDetails record={record} />);
      assert.ok(detail.includes(record.ticket_id));
      assert.ok(detail.includes('Original ticket'));
      assert.ok(detail.includes('Pending'));
    }
  });
  test('Light and dark semantic text pairs meet WCAG AA, including matrix backgrounds', async () => {
    const css = await readFile('src/styles/tokens.css', 'utf8');
    const sections = css.split("[data-theme='dark']");
    function tokens(section: string) {
      return Object.fromEntries([...section.matchAll(/--([\w-]+):\s*(#[0-9A-Fa-f]{6})/g)].map(match => [match[1], match[2]]));
    }
    function rgb(color: string) { return [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16)); }
    function luminance(color: number[]) {
      const values = color.map(v => v / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
      return values[0] * .2126 + values[1] * .7152 + values[2] * .0722;
    }
    function contrast(a: number[], b: number[]) {
      const values = [luminance(a), luminance(b)].sort((x, y) => y - x);
      return (values[0] + .05) / (values[1] + .05);
    }
    const light = tokens(sections[0]);
    for (const [name, theme] of [['light', light], ['dark', { ...light, ...tokens(sections[1]) }]] as const) {
      const pairs = [
        ...['ink', 'ink-2', 'ink-3'].flatMap(fg => ['bg', 'surface', 'surface-2', 'accent-soft', 'review-soft'].map(bg => [fg, bg])),
        ...['accent', 'review', 'high', 'medium', 'low', 'error'].map(color => [color, color + '-soft']),
        ['white', 'accent'], ['bg', 'ink'], ['disabled', 'surface-2'],
      ];
      for (const [fg, bg] of pairs) {
        assert.ok(contrast(rgb(theme[fg]), rgb(theme[bg])) >= 4.5, name + ': ' + fg + ' on ' + bg + ' fails AA');
      }
      for (const color of ['accent', 'rust']) {
        const surface = rgb(theme.surface);
        const mixed = rgb(theme[color]).map((v, i) => v * .25 + surface[i] * .75);
        assert.ok(contrast(rgb(theme.ink), mixed) >= 4.5, name + ': matrix text fails AA');
      }
    }
  });
}
