"""Helper for the weekly Macro Scenario Tracker update. Standard library only.

Run from the repository root with the -I flag:

  python -I tools/tracker.py validate            check index.html against the project rules
  python -I tools/tracker.py latest OUT.json      write the latest week, pretty-printed, to edit
  python -I tools/tracker.py add-week WEEK.json   append a week (or replace the week with the same date)
  python -I tools/tracker.py artifact OUT.html    write the claude.ai artifact copy (no html/head wrapper)
  python -I tools/tracker.py fred                 print the latest FRED readings used by the page
  python -I tools/tracker.py og                   re-render og.png from tools/og-card.html with Chrome

Exit code is 0 when everything passed, 1 when something failed.
"""
import csv
import io
import json
import os
import re
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.environ.get('TRACKER_INDEX') or os.path.join(ROOT, 'index.html')  # override only for testing
BLOCK_RE = re.compile(r'(<script type="application/json" id="tracker-data">)(.*?)(</script>)', re.S)

SCEN_GROUPS = {'soft': 'deal', 'crack': 'deal', 'grind': 'nodeal', 'stag': 'nodeal', 'esc': 'esc'}
LABELS = ['Now', 'Mar 27', 'Jun 27', 'Dec 27', 'Dec 28']
VARS = ['ff', 'ty', 'br', 'sp']
SIGNPOSTS = ['hormuz', 'brent', 'unemp', 'core', 'dots', 'bills', 'y30', 'hy', 'ai']
SNAP_REQUIRED = ['ff', 'effr', 'b3m', 'b6m', 'y2', 'y10', 'y30', 'mort', 'brent', 'cpi', 'core', 'unemp', 'nfp', 'spx']
SNAP_OPTIONAL = ['hy']
KINDS = {'rate', 'price', 'index', 'count', 'pp'}
WEEK_KEYS = ['date', 'label', 'short', 'updatedLabel', 'headline', 'market', 'scenarios', 'paths',
             'snapshot', 'signposts', 'changes', 'cre', 'dates', 'sources']
MAX_MOVE = 8
BAD_CHARS = {'\u2013': 'en dash', '\u2014': 'em dash'}


def read_index():
    with io.open(INDEX, encoding='utf-8', newline='') as f:
        return f.read()


def write_index(text):
    with io.open(INDEX, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


def load_data(text):
    m = BLOCK_RE.search(text)
    if not m:
        raise SystemExit('tracker-data block not found in index.html')
    return m, json.loads(m.group(2))


def dump_data(data):
    raw = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    return raw.replace('</', '<\\/')


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check_week(w, errs, tag):
    for k in WEEK_KEYS:
        if k not in w:
            errs.append('%s: missing key %s' % (tag, k))
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', str(w.get('date', ''))):
        errs.append('%s: date must be YYYY-MM-DD' % tag)

    scen = w.get('scenarios') or []
    ids = [s.get('id') for s in scen]
    if sorted(ids) != sorted(SCEN_GROUPS):
        errs.append('%s: scenario ids must be exactly %s, got %s' % (tag, list(SCEN_GROUPS), ids))
    total = 0
    for s in scen:
        sid = s.get('id')
        if SCEN_GROUPS.get(sid) and s.get('group') != SCEN_GROUPS[sid]:
            errs.append('%s: scenario %s must be in group %s' % (tag, sid, SCEN_GROUPS[sid]))
        p = s.get('prob')
        if not isinstance(p, int) or isinstance(p, bool) or p < 0:
            errs.append('%s: scenario %s prob must be a non-negative integer' % (tag, sid))
        else:
            total += p
        for k in ('name', 'story'):
            if not s.get(k):
                errs.append('%s: scenario %s missing %s' % (tag, sid, k))
        e = s.get('end27') or {}
        for v in VARS:
            if not is_num(e.get(v)):
                errs.append('%s: scenario %s end27.%s must be a number' % (tag, sid, v))
    if total != 100:
        errs.append('%s: odds sum to %s, not 100' % (tag, total))

    paths = w.get('paths') or {}
    if paths.get('labels') != LABELS:
        errs.append('%s: paths.labels must be %s' % (tag, LABELS))
    for v in VARS:
        pv = paths.get(v) or {}
        for sid in SCEN_GROUPS:
            arr = pv.get(sid)
            if not isinstance(arr, list) or len(arr) != 5 or not all(is_num(x) for x in arr):
                errs.append('%s: paths.%s.%s must be 5 numbers' % (tag, v, sid))
                continue
            s = next((x for x in scen if x.get('id') == sid), None)
            if s and is_num((s.get('end27') or {}).get(v)) and abs(arr[3] - s['end27'][v]) > 1e-9:
                errs.append('%s: paths.%s.%s Dec 27 point %s does not equal end27 %s' % (tag, v, sid, arr[3], s['end27'][v]))

    sp = w.get('signposts') or []
    sp_ids = [x.get('id') for x in sp]
    if sp_ids != SIGNPOSTS:
        errs.append('%s: signpost ids must be %s in order, got %s' % (tag, SIGNPOSTS, sp_ids))
    for x in sp:
        if x.get('status') not in ('deal', 'none', 'stress'):
            errs.append('%s: signpost %s status must be deal, none or stress' % (tag, x.get('id')))
        for k in ('name', 'now', 'good', 'bad'):
            if not x.get(k):
                errs.append('%s: signpost %s missing %s' % (tag, x.get('id'), k))

    snap = w.get('snapshot') or []
    snap_ids = [r.get('id') for r in snap]
    for rid in SNAP_REQUIRED:
        if rid not in snap_ids:
            errs.append('%s: snapshot row %s missing' % (tag, rid))
    for r in snap:
        rid = r.get('id')
        if rid not in SNAP_REQUIRED + SNAP_OPTIONAL:
            errs.append('%s: unknown snapshot row %s' % (tag, rid))
        if not is_num(r.get('value')):
            errs.append('%s: snapshot %s value must be a number' % (tag, rid))
        if r.get('kind') not in KINDS:
            errs.append('%s: snapshot %s kind must be one of %s' % (tag, rid, sorted(KINDS)))
        for k in ('label', 'fmt', 'asof'):
            if not r.get(k):
                errs.append('%s: snapshot %s missing %s' % (tag, rid, k))

    for k in ('changes', 'cre'):
        if not isinstance(w.get(k), list) or not all(isinstance(x, str) and x for x in w.get(k) or []):
            errs.append('%s: %s must be a list of strings' % (tag, k))
    for d in w.get('dates') or []:
        if not d.get('d') or not d.get('e'):
            errs.append('%s: every date needs d and e' % tag)
    for s in w.get('sources') or []:
        if not s.get('title') or not str(s.get('url', '')).startswith('https://'):
            errs.append('%s: every source needs a title and an https url' % tag)


def cmd_validate(_args):
    text = read_index()
    errs, warns = [], []
    for ch, name in BAD_CHARS.items():
        n = text.count(ch)
        if n:
            errs.append('index.html contains %d %s character(s)' % (n, name))
    try:
        m, data = load_data(text)
    except ValueError as e:
        print('FAIL: JSON does not parse: %s' % e)
        return 1
    raw = m.group(2)
    if '</script' in raw.lower():
        errs.append('JSON contains </script')
    if '<!--' in raw:
        errs.append('JSON contains <!--')
    if 'chart.js/4.4.1/' not in text.lower():
        errs.append('Chart.js 4.4.1 from cdnjs not found')
    if 'investment advice' not in text:
        errs.append('footer line about investment advice is missing')

    weeks = data.get('weeks') or []
    if not weeks:
        errs.append('no weeks in data')
    dates = [w.get('date') for w in weeks]
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        errs.append('weeks must be in date order with unique dates: %s' % dates)
    for w in weeks:
        check_week(w, errs, w.get('date', '?'))

    if len(weeks) >= 2:
        cur, prev = weeks[-1], weeks[-2]
        pp = {s.get('id'): s.get('prob') for s in prev.get('scenarios') or []}
        for s in cur.get('scenarios') or []:
            old = pp.get(s.get('id'))
            if is_num(old) and is_num(s.get('prob')) and abs(s['prob'] - old) > MAX_MOVE:
                warns.append('%s moved %+d points (rule: at most %d unless something decisive happened; say what in "changes")'
                             % (s.get('id'), s['prob'] - old, MAX_MOVE))

    for x in warns:
        print('WARN: ' + x)
    for x in errs:
        print('FAIL: ' + x)
    if errs:
        return 1
    latest = weeks[-1]
    print('OK: %d week(s), latest %s, odds %s' % (len(weeks), latest.get('date'),
          ', '.join('%s %d' % (s['id'], s['prob']) for s in latest['scenarios'])))
    return 0


def cmd_latest(args):
    if not args:
        raise SystemExit('usage: latest OUT.json')
    _, data = load_data(read_index())
    with io.open(args[0], 'w', encoding='utf-8') as f:
        json.dump(data['weeks'][-1], f, ensure_ascii=False, indent=1)
        f.write('\n')
    print('wrote latest week (%s) to %s' % (data['weeks'][-1]['date'], args[0]))
    return 0


def cmd_add_week(args):
    if not args:
        raise SystemExit('usage: add-week WEEK.json')
    with io.open(args[0], encoding='utf-8') as f:
        week = json.load(f)
    errs = []
    check_week(week, errs, week.get('date', '?'))
    if errs:
        for x in errs:
            print('FAIL: ' + x)
        return 1
    text = read_index()
    m, data = load_data(text)
    weeks = [w for w in data['weeks'] if w.get('date') != week['date']]
    replaced = len(weeks) != len(data['weeks'])
    weeks.append(week)
    weeks.sort(key=lambda w: w['date'])
    data['weeks'] = weeks
    new_text = text[:m.start(2)] + '\n' + dump_data(data) + '\n' + text[m.end(2):]
    write_index(new_text)
    print('%s week %s; %d week(s) in data. Now run: validate' % ('replaced' if replaced else 'added', week['date'], len(weeks)))
    return 0


def artifact_fragment(text):
    head = text.split('<head>', 1)[1].split('</head>', 1)[0]
    head = head[head.index('<title>'):]
    body = text.split('<body>', 1)[1].rsplit('</body>', 1)[0]
    return head.strip() + '\n\n' + body.strip() + '\n'


def cmd_artifact(args):
    if not args:
        raise SystemExit('usage: artifact OUT.html')
    frag = artifact_fragment(read_index())
    with io.open(args[0], 'w', encoding='utf-8', newline='\n') as f:
        f.write(frag)
    print('wrote artifact copy to %s (%d bytes)' % (args[0], len(frag.encode('utf-8'))))
    return 0


def fetch_text(url):
    # FRED stalls some non-curl clients, so prefer the system curl and fall back to urllib.
    try:
        r = subprocess.run(['curl', '-s', '-f', '-m', '30', url], capture_output=True, timeout=40)
        if r.returncode == 0 and r.stdout:
            return r.stdout.decode('utf-8')
    except (OSError, subprocess.SubprocessError):
        pass
    req = urllib.request.Request(url, headers={'User-Agent': 'curl/8.4.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8')


def fred_series(sid):
    url = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=' + sid
    rows = list(csv.reader(io.StringIO(fetch_text(url))))
    out = []
    for row in rows[1:]:
        if len(row) == 2 and row[1] not in ('', '.'):
            out.append((row[0], float(row[1])))
    return out


def cmd_fred(_args):
    daily = [
        ('EFFR', 'effr', 'Effective fed funds, %'),
        ('DGS3MO', 'b3m', '3M Treasury (constant maturity), %'),
        ('DGS6MO', 'b6m', '6M Treasury (constant maturity), %'),
        ('DGS2', 'y2', '2Y Treasury, %'),
        ('DGS10', 'y10', '10Y Treasury, %'),
        ('DGS30', 'y30', '30Y Treasury, %'),
        ('BAMLH0A0HYM2', 'hy', 'ICE BofA US high-yield OAS, % (x100 for bps)'),
        ('SP500', 'spx', 'S&P 500 close'),
        ('DCOILBRENTEU', '-', 'Dated Brent SPOT. Not the front-month futures price the page uses. Context only.'),
    ]
    status = 0
    print('FRED latest readings (date, value). Weekly change uses the last value 5+ sessions earlier.')
    for sid, row, label in daily:
        try:
            obs = fred_series(sid)
            d, v = obs[-1]
            prior = obs[-6] if len(obs) >= 6 else None
            extra = ' | 5 sessions earlier %s %.3f' % prior if prior else ''
            print('  %-13s row=%-5s %s  %.3f  %s%s' % (sid, row, d, v, label, extra))
        except Exception as e:
            status = 1
            print('  %-13s FAILED: %s' % (sid, e))
    # Monthly series: match prior periods by date, because FRED has gaps (October 2025 was never collected).
    def shift(d, months):
        y, m = int(d[:4]), int(d[5:7]) - 1 + months
        return '%04d-%02d-01' % (y + m // 12, m % 12 + 1)

    def pct(obs, months):
        by = dict(obs)
        d, v = obs[-1]
        old = by.get(shift(d, -months))
        return None if old is None else (v / old - 1) * 100

    def fmt(x, spec):
        return 'n/a (prior month missing on FRED)' if x is None else spec % x

    try:
        u = fred_series('UNRATE')
        print('  %-13s row=unemp %s  %.1f  Unemployment rate, %%' % ('UNRATE', u[-1][0], u[-1][1]))
        p = fred_series('PAYEMS')
        pp = dict(p).get(shift(p[-1][0], -1))
        print('  %-13s row=nfp   %s  %s  Payrolls change, thousands (first print, revised later)'
              % ('PAYEMS', p[-1][0], fmt(None if pp is None else p[-1][1] - pp, '%+.0f')))
        c = fred_series('CPIAUCSL')
        print('  %-13s row=cpi   %s  %s  CPI y/y, %% (SA index; BLS headline y/y uses NSA and can differ by 0.1)'
              % ('CPIAUCSL', c[-1][0], fmt(pct(c, 12), '%.1f')))
        k = fred_series('CPILFESL')
        print('  %-13s row=core  %s  %s  Core CPI y/y, %% | m/m %s'
              % ('CPILFESL', k[-1][0], fmt(pct(k, 12), '%.1f'), fmt(pct(k, 1), '%.2f%%')))
    except Exception as e:
        status = 1
        print('  monthly series FAILED: %s' % e)
    print('Not from FRED: fed funds target (FOMC), 30Y mortgage (Mortgage News Daily daily index), Brent (ICE front-month futures).')
    return status


def find_chrome():
    for p in [r'C:\Program Files\Google\Chrome\Application\chrome.exe',
              r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
              r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
              r'C:\Program Files\Microsoft\Edge\Application\msedge.exe']:
        if os.path.exists(p):
            return p
    raise SystemExit('Chrome or Edge not found')


def cmd_og(_args):
    src = os.path.join(ROOT, 'tools', 'og-card.html')
    out = os.path.join(ROOT, 'og.png')
    url = 'file:///' + src.replace('\\', '/')
    subprocess.run([find_chrome(), '--headless=new', '--disable-gpu', '--hide-scrollbars',
                    '--force-device-scale-factor=1', '--window-size=1200,630', '--virtual-time-budget=8000',
                    '--screenshot=' + out, url], check=True, capture_output=True)
    print('wrote %s' % out)
    return 0


COMMANDS = {'validate': cmd_validate, 'latest': cmd_latest, 'add-week': cmd_add_week,
            'artifact': cmd_artifact, 'fred': cmd_fred, 'og': cmd_og}

if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    sys.exit(COMMANDS[sys.argv[1]](sys.argv[2:]))
