#!/usr/bin/env python3
"""Apply an overlapping patch stack without overwriting unrelated local edits."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

checkout, patch_dir = map(Path, sys.argv[1:3])
patches = sorted(patch_dir.glob('*.patch'))
names = sorted({name for p in patches for name in
                re.findall(r'^\+\+\+ b/(.+)$', p.read_text(), re.MULTILINE)})
with tempfile.TemporaryDirectory(prefix='proton-patches-') as directory:
    temp = Path(directory)
    versions = {name: [] for name in names}
    for name in names:
        data = subprocess.check_output(['git', '-C', str(checkout), 'show', 'HEAD:' + name])
        path = temp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        versions[name].append(data)
    for patch in patches:
        subprocess.run(['git', 'apply', str(patch.resolve())], cwd=temp, check=True)
        for name in names:
            versions[name].append((temp / name).read_bytes())
    # Validate every input before changing any source file.
    for name in names:
        if (checkout / name).read_bytes() not in versions[name]:
            raise SystemExit('Local edits outside the pinned patch stack: ' + name)
    for name in names:
        path = checkout / name
        if path.read_bytes() != versions[name][-1]:
            path.write_bytes(versions[name][-1])
    print('Patch stack verified:', ', '.join(p.name for p in patches))
