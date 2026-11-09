"""Reject private runtime artifacts and recognizable live keys in the Git index."""
import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[2]
git = ['git', '-c', 'safe.directory=' + root.as_posix(), '-C', str(root)]
files = subprocess.check_output(git + ['ls-files', '-z']).decode().split('\0')
violations = []
secret = re.compile(rb'(?:gsk_[A-Za-z0-9]{25,}|xkeysib-[A-Za-z0-9-]{40,}|xsmtpsib-[A-Za-z0-9-]{40,}|sk-proj-[A-Za-z0-9_-]{35,})')
for name in filter(None, files):
    path = Path(name)
    if any(part in ('.venv', '.venv-production', '.npm-cache', 'node_modules', 'logs', 'finance_db') for part in path.parts) or (path.name.startswith('.env') and path.name != '.env.example') or path.suffix in ('.sqlite3', '.sqlite', '.db'):
        violations.append(name + ': private runtime artifact')
    if path.suffix.lower() in ('.py', '.js', '.jsx', '.json', '.yaml', '.yml', '.md', '.txt', '.example'):
        data = subprocess.check_output(git + ['show', ':' + name])
        if secret.search(data):
            violations.append(name + ': credential pattern detected')
if violations:
    raise SystemExit('\n'.join(violations))
print(f'Publication check passed: {len(list(filter(None, files)))} files; no private runtime artifacts or matching live keys.')
