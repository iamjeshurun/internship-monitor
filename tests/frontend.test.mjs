import assert from 'node:assert/strict';
import test from 'node:test';
import {readFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import vm from 'node:vm';
import {STAGES, setDemoStatus, safeUrl, escapeHtml, currentCounts} from '../web/assets/model.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const context = {window: {}};
vm.runInNewContext(readFileSync(new URL('../web/bootstrap.js', import.meta.url), 'utf8'), context);
const snapshot = JSON.parse(JSON.stringify(context.window.TRACKER_BOOTSTRAP.snapshot));

test('every demo status change matches the real Python merger', () => {
  const python = `
import json,sys
from pathlib import Path
sys.path.insert(0,'mac')
from tracker import merge_tracker, STAGE_ORDER
f=json.loads(Path('demo/fixtures.json').read_text())
items=merge_tracker(f['queue'],f['history'],f['statuses'])
out=[]
for item in items:
 for stage in STAGE_ORDER:
  statuses={**f['statuses'],item['key']:{'status':stage}}
  changed=next(i for i in merge_tracker(f['queue'],f['history'],statuses) if i['key']==item['key'])
  out.append({'key':item['key'],'requested':stage,'status':changed['status'],'source':changed['status_source'],'events':changed.get('events',[])})
print(json.dumps(out))
`;
  const result = spawnSync(process.env.PYTHON || 'python3', ['-c', python], {cwd: root, encoding: 'utf8'});
  assert.equal(result.status, 0, result.stderr);
  const expected = JSON.parse(result.stdout);
  assert.equal(expected.length, snapshot.items.length * STAGES.length);
  for (const record of expected) {
    const result = setDemoStatus(snapshot, record.key, record.requested);
    const actual = result.items.find(item => item.key === record.key);
    assert.equal(actual.status, record.status, `${record.key} → ${record.requested}`);
    assert.equal(actual.status_source, record.source);
    assert.deepEqual(actual.events || [], record.events);
  }
});

test('demo writes do not mutate fixtures; counts follow the saved status', () => {
  const before = JSON.stringify(snapshot);
  const key = snapshot.items.find(item => item.status === 'ready').key;
  const changed = setDemoStatus(snapshot, key, 'offer');
  assert.equal(JSON.stringify(snapshot), before);
  assert.equal(currentCounts(changed.items).offer, currentCounts(snapshot.items).offer + 1);
  assert.throws(() => setDemoStatus(snapshot, key, 'screening'));
  assert.throws(() => setDemoStatus(snapshot, 'missing', 'offer'));
});

test('untrusted posting URLs and record text cannot become executable markup', () => {
  for (const url of ['javascript:alert(1)', 'data:text/html,test', '/relative', '', 'file:///tmp/a']) assert.equal(safeUrl(url), null);
  assert.equal(safeUrl('https://example.com/jobs/1'), 'https://example.com/jobs/1');
  assert.equal(escapeHtml('<img src=x onerror="bad()">'), '&lt;img src=x onerror=&quot;bad()&quot;&gt;');
});
