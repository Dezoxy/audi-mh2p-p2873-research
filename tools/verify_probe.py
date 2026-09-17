#!/usr/bin/env python3
"""Judge the on-unit tool probe: does each installer assumption hold on this unit?"""
import json
from pathlib import Path
import re
import sys

HEX2 = re.compile(r'^[0-9a-fA-F]{2}$')
REQUIRED_TOOLS = ['gzip', 'dd', 'hd', 'wc', 'cp', 'mv', 'rm', 'mkdir', 'chmod', 'ls', 'df', 'sync', 'awk', 'sed',
                  'date', 'cat', 'head', 'tail', 'dirname', 'basename', 'slay', 'mount', 'ksh']
CRC_CHECKS = ['crc-selftest', 'crc-img_ver', 'crc-altered-rejected']


def hd_bytes(text):
    """Apply the same rule as common.sh: skip the offset token, take 2-hex-digit tokens until a non-hex token."""
    first = text.strip().splitlines()[0] if text.strip() else ''
    out = []
    for tok in first.split()[1:]:
        if HEX2.match(tok):
            out.append(tok.lower())
        else:
            break
    return out


def selftest_edges():
    body = bytes(range(256)) * 16
    body = body[:-1] + b'\x00'
    return [f'{b:02x}' for b in body[:8]], [f'{b:02x}' for b in body[-8:]]


def read(probe, name):
    p = probe / name
    return p.read_text() if p.exists() else ''


def df_rows_ok(text):
    rows = [l for l in text.splitlines() if l.strip()]
    return len(rows) == 2 and len(rows[1].split()) >= 4 and rows[1].split()[3].isdigit()


def verify(probe):
    probe = Path(probe)
    checks = {}
    for line in read(probe, 'result.txt').splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == 'check':
            checks[parts[1]] = {'status': parts[2], 'detail': ' '.join(parts[3:])}
    first, last = selftest_edges()
    tools = dict(l.partition(' ')[::2] for l in read(probe, 'tools.txt').splitlines() if ' ' in l)
    free_lines = [l for l in read(probe, 'result.txt').splitlines() if l.startswith('check free-kb ')]
    v = {
        'complete': (probe / 'COMPLETE').exists(),
        'hd_format_ok': hd_bytes(read(probe, 'hd-first8.txt'))[:8] == first and hd_bytes(read(probe, 'hd-last8.txt'))[:8] == last,
        'df_format_ok': df_rows_ok(read(probe, 'df-app.txt')) and df_rows_ok(read(probe, 'df-media.txt')),
        'crc_pipeline_ok': all(checks.get(k, {}).get('status') == 'PASS' for k in CRC_CHECKS),
        'free_space_ok': bool(free_lines) and all(' PASS ' in l for l in free_lines),
        'dir_is_empty_ok': checks.get('dir-is-empty', {}).get('status') == 'PASS',
        'tools_missing': [t for t in REQUIRED_TOOLS if tools.get(t, 'MISSING') == 'MISSING'],
        'hash_tools_present': [t for t in ['cksum', 'md5sum', 'sum', 'cmp', 'od'] if tools.get(t, 'MISSING') != 'MISSING'],
        'modkit_chain': checks.get('modkit-chain', {}).get('detail', 'unknown'),
        'environment': read(probe, 'env.txt').strip().splitlines()[:3],
        'network': {
            'interfaces_with_inet': [l.strip() for l in read(probe, 'net-ifconfig.txt').splitlines() if 'inet ' in l],
            'listening': [l.strip() for l in read(probe, 'net-sockstat.txt').splitlines()[1:] if l.strip()][:20],
            'daemons': [l.strip() for l in read(probe, 'net-processes.txt').splitlines() if l.strip()][:20],
            'ssh_key_dir_present': '.ssh' in read(probe, 'net-ssh-files.txt') and 'No such file' not in read(probe, 'net-ssh-files.txt').split('.ssh')[0][-80:],
        },
        'failsafe_heartbeats': [l for l in read(probe.parent, 'AudiP2873-failsafe-heartbeat.txt').splitlines() if l.strip()],
        'checks': checks,
        'installation_approved': False,
    }
    v['assumptions_hold'] = all([v['complete'], v['hd_format_ok'], v['df_format_ok'], v['crc_pipeline_ok'],
                                 v['free_space_ok'], v['dir_is_empty_ok'], not v['tools_missing']])
    return v


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('usage: verify_probe.py /Volumes/CARD/AudiP2873-probe')
    verdict = verify(sys.argv[1])
    print(json.dumps(verdict, indent=2))
    sys.exit(0 if verdict['assumptions_hold'] else 1)
