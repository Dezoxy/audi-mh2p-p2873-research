#!/usr/bin/env python3
"""Assemble an SD card layout from the pinned third-party submodules.

Copies a base loader and selected mods into a new directory, checks that each
submodule is at the revision recorded in this repository, refuses conflicting
selections, and writes CARD-MANIFEST.json with hashes. It never writes to a
head unit. See third_party/CATALOG.md.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
THIRD = ROOT / 'third_party'
BASES = {'modkit': 'MH2p_SD_ModKit', 'q3team': 'Q3Team-MH2p-GEM'}
MODS = {  # name -> (submodule, folder name on the card)
    'carplay-fullscreen': ('MH2p_CarPlay_FullScreen', 'CarPlayFullScreen'),
    'carplay-windowed': ('MH2p_CarPlay_WindowedFullScreen', 'CarPlayWindowedFullScreen'),
    'navcompass': ('MH2p_NavCompassIgnore', 'NavCompassIgnore'),
    'gem': ('MH2p_GreenEngineeringMenu', 'GreenEngineeringMenu'),
    'ssh-access': ('mh2p-ssh-access', 'mh2p-ssh-access'),
}
EXCLUSIVE = [('carplay-fullscreen', 'carplay-windowed')]
STAGES = ['Update', 'Post', 'Persist']
PREFLIGHT_ZIP = ROOT / 'dist/Audi-P2873-preflight-addon.zip'


def pinned_revision(name):
    """Gitlink recorded in the index (staged or committed): '160000 <sha> 0 <path>'."""
    out = subprocess.run(['git', 'ls-files', '--stage', f'third_party/{name}'], cwd=ROOT, capture_output=True, text=True)
    parts = out.stdout.split()
    return parts[1] if len(parts) >= 4 and parts[0] == '160000' else None


def checked_out_revision(name):
    out = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=THIRD / name, capture_output=True, text=True)
    return out.stdout.strip() or None


def require_pinned(name, allow_unpinned):
    if not (THIRD / name).is_dir() or not any((THIRD / name).iterdir()):
        sys.exit(f'submodule not checked out: third_party/{name} (run: git submodule update --init)')
    pinned, actual = pinned_revision(name), checked_out_revision(name)
    if pinned != actual and not allow_unpinned:
        sys.exit(f'third_party/{name} is at {actual}, repository pins {pinned}; refusing (use --allow-unpinned to override)')
    return actual


def copy_tree(src, dst, skip=('.git', '.gitignore', '.DS_Store')):
    for item in src.iterdir():
        if item.name in skip:
            continue
        target = dst / item.name
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            copy_tree(item, target, skip)
        else:
            shutil.copy2(item, target)


def assemble(output, base, mods, ssh_pubkey, preflight, allow_unpinned):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        sys.exit(f'output directory is not empty: {output}')
    for a, b in EXCLUSIVE:
        if a in mods and b in mods:
            sys.exit(f'{a} and {b} install the same file; choose one')
    if base == 'q3team' and mods:
        sys.exit('the q3team base uses the ModKit v1 layout; ModKit v2 mods cannot be added to it')
    if 'ssh-access' in mods and not ssh_pubkey:
        sys.exit('ssh-access needs --ssh-pubkey FILE (your OpenSSH public key)')
    revisions = {}
    output.mkdir(parents=True, exist_ok=True)
    base_sub = BASES[base]
    revisions[base_sub] = require_pinned(base_sub, allow_unpinned)
    copy_tree(THIRD / base_sub, output)
    for name in mods:
        sub, folder = MODS[name]
        revisions[sub] = require_pinned(sub, allow_unpinned)
        dst = output / 'Mods' / folder
        dst.mkdir(parents=True)
        for stage in STAGES:
            if (THIRD / sub / stage).is_dir():
                (dst / stage).mkdir()
                copy_tree(THIRD / sub / stage, dst / stage)
        for doc in ['LICENSE.md', 'README.md']:
            if (THIRD / sub / doc).is_file():
                shutil.copy2(THIRD / sub / doc, dst / doc)
        if name == 'ssh-access':
            key = Path(ssh_pubkey).read_text().strip()
            if not key.startswith(('ssh-rsa ', 'ssh-ed25519 ', 'ecdsa-')):
                sys.exit('--ssh-pubkey does not look like an OpenSSH public key')
            (dst / 'Update/authorized_keys').write_text(key + '\n')
    if preflight:
        if not PREFLIGHT_ZIP.is_file():
            sys.exit(f'preflight addon not built: {PREFLIGHT_ZIP} (run tools/build_sd_preflight.py)')
        with zipfile.ZipFile(PREFLIGHT_ZIP) as z:
            for info in z.infolist():
                target = output / info.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(info))
                if info.filename.endswith('.sh'):
                    target.chmod(0o755)
    files = {}
    for p in sorted(output.rglob('*')):
        if p.is_file() and p.name != 'CARD-MANIFEST.json':
            files[str(p.relative_to(output))] = hashlib.sha256(p.read_bytes()).hexdigest()
    manifest = {'base': base, 'mods': mods, 'preflight': preflight, 'submodule_revisions': revisions,
                'file_count': len(files), 'files': files, 'vehicle_tested': False}
    (output / 'CARD-MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (output / 'CARD-README.txt').write_text(
        'Copy everything in this directory to the root of a FAT32 SD card.\n'
        'macOS adds hidden ._ and .DS_Store files; remove them before ejecting (dot_clean -m /Volumes/CARD),\n'
        'otherwise the unit reports more than one manifest file.\n'
        'To uninstall a mod later, put an empty uninstall.txt in its Mods/<name>/ folder and run the update again.\n'
        'Running the base loader modifies the unit (servicemgrmibhigh wrapper). See third_party/CATALOG.md.\n')
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--output', required=True, help='new or empty directory to assemble the card layout in')
    ap.add_argument('--base', choices=sorted(BASES), default='modkit')
    ap.add_argument('--mod', action='append', default=[], choices=sorted(MODS), help='repeatable')
    ap.add_argument('--ssh-pubkey', help='OpenSSH public key file for ssh-access')
    ap.add_argument('--preflight', action='store_true', help='include this project\'s diagnostic addon')
    ap.add_argument('--allow-unpinned', action='store_true')
    a = ap.parse_args()
    m = assemble(a.output, a.base, a.mod, a.ssh_pubkey, a.preflight, a.allow_unpinned)
    print(json.dumps({k: v for k, v in m.items() if k != 'files'}, indent=2))


if __name__ == '__main__':
    main()
