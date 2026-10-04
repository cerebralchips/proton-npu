#!/usr/bin/env python3
"""Fast source-package checks. This does not run or certify RTL simulation."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import ast
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
names = subprocess.check_output(
    ['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT
).decode().split('\0')
FILES = {ROOT / name for name in names if name and (ROOT / name).is_file()}
errors = []


def require(ok, message):
    if not ok:
        errors.append(message)


def link(source, url):
    parsed = urlsplit(url)
    prefix = 'https://github.com/cerebralchips/proton-npu/'
    if url.startswith(prefix + 'blob/hardware/') or url.startswith(prefix + 'tree/hardware/'):
        target = ROOT / unquote(parsed.path.split('/hardware/', 1)[1])
    elif parsed.scheme or parsed.netloc or not parsed.path:
        return
    else:
        target = (source.parent / unquote(parsed.path)).resolve()
    present = target in FILES or any(target in p.parents for p in FILES)
    require(present, f'{source.relative_to(ROOT)}: missing packaged link {url}')


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.tags = set()
        self.ids = set()
        self.anchors = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.add(tag)
        if 'id' in a:
            require(a['id'] not in self.ids, f'{self.path.name}: duplicate id {a["id"]}')
            self.ids.add(a['id'])
        if tag == 'html':
            require(a.get('lang'), f'{self.path.name}: missing language')
        if tag == 'img':
            require(a.get('alt'), f'{self.path.name}: missing image description')
        for name in ['src', 'href']:
            if a.get(name):
                link(self.path, a[name])
                if a[name].startswith('#') and len(a[name]) > 1:
                    self.anchors.append(a[name][1:])


private_path = re.compile(r'[/](?:Users|home)[/][A-Za-z0-9_.-]+[/]')
secret = re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)')
for path in sorted(FILES):
    rel = path.relative_to(ROOT)
    require(path.stat().st_size < 1_000_000, f'{rel}: oversized source-package file')
    try:
        text = path.read_text()
    except UnicodeDecodeError:
        errors.append(f'{rel}: unexpected binary in source package')
        continue
    require(not private_path.search(text), f'{rel}: personal absolute path')
    require(not secret.search(text), f'{rel}: possible credential')
    if path.suffix == '.py':
        ast.parse(text, filename=str(rel))
    elif path.suffix == '.sh' or rel == Path('scripts/ara'):
        subprocess.run(['bash', '-n', str(path)], check=True)
    elif path.suffix == '.json':
        json.loads(text)
    elif path.suffix == '.svg':
        ET.fromstring(text)
    elif path.suffix == '.html':
        page = Page(path)
        page.feed(text)
        require({'html', 'title', 'body'} <= page.tags, f'{rel}: incomplete HTML')
        for anchor in page.anchors:
            require(anchor in page.ids, f'{rel}: missing anchor #{anchor}')
    elif path.suffix == '.md':
        for url in re.findall(r'\[[^\]]*\]\(([^\s)]+)(?:\s+[^)]*)?\)', text):
            link(path, url)

vendor = ROOT / 'hardware/matrix/vendor/quadrilatero'
provenance = json.loads((vendor / 'provenance.json').read_text())
for name, expected in provenance['files'].items():
    require(hashlib.sha256((vendor / name).read_bytes()).hexdigest() == expected,
            f'vendored file differs from provenance: {name}')
lock = json.loads((ROOT / 'sources.lock.json').read_text())
require(lock['matrix']['quadrilatero']['commit'] == provenance['commit'], 'matrix pin differs from provenance')

with tempfile.TemporaryDirectory() as directory:
    generated = Path(directory) / 'workload.h'
    subprocess.run([sys.executable, str(ROOT / 'tests/matrix/workload.py'), str(generated)], check=True)
    require(generated.read_bytes() == (ROOT / 'examples/scalar_vector_matrix/workload.h').read_bytes(),
            'generated application expectations are stale')

if errors:
    print('\n'.join(errors), file=sys.stderr)
    raise SystemExit(1)
print(f'PASS: {len(FILES)} source files; syntax, packaged links, provenance and workload data checked.')
print('Full RTL verification is separate: ./scripts/ara matrix')
