"""Build the separate, Windows x64 local review release from explicit inputs."""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
OUTPUT = PROJECT / 'artifacts' / 'review-dist'


def build(version, python, wheels):
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('expected a three-part release version')
    if os.name != 'nt' or sys.version_info[:2] != (3, 12) or sys.maxsize <= 2**32:
        raise RuntimeError('use Windows x64 Python 3.12 to build the review edition')
    for name in ('python.exe', 'pythonw.exe', 'python312.dll', 'DLLs/_tkinter.pyd', 'tcl', 'Lib/tkinter', 'LICENSE.txt'):
        if not (python / name).exists():
            raise ValueError('missing runtime component: ' + name)
    identity = subprocess.check_output(
        [str(python / 'python.exe'), '-I', '-c',
         'import struct, sys; print(sys.version_info[:2], struct.calcsize("P"))'],
        text=True,
    ).strip()
    if identity != '(3, 12) 8':
        raise ValueError('portable runtime must be Windows x64 Python 3.12')

    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=OUTPUT, prefix='build-') as folder:
        work = Path(folder)
        app = work / 'app'
        app.mkdir()
        bundled = app / 'python'
        bundled.mkdir()
        for path in python.iterdir():
            if path.is_file() and path.suffix.lower() in {'.exe', '.dll', '.txt'} and path.name != 'python3.exe':
                shutil.copy2(path, bundled)
        for name in ('DLLs', 'Lib', 'tcl'):
            shutil.copytree(
                python / name, bundled / name,
                ignore=shutil.ignore_patterns('__pycache__', 'site-packages', 'test', 'tests',
                                              'ensurepip', 'idlelib', 'turtledemo', 'Tools'),
            )
        env = dict(os.environ, TEMP=str(work), TMP=str(work))
        command = [sys.executable, '-I', '-m', 'pip', '--isolated', '--disable-pip-version-check',
                   '--no-cache-dir', 'install', '--require-hashes', '--only-binary=:all:',
                   '--no-compile', '--target', str(bundled / 'Lib' / 'site-packages'),
                   '-r', str(HERE / 'bandit-windows-x64.lock')]
        if wheels:
            command.extend(['--no-index', '--find-links', str(wheels)])
        subprocess.run(command, check=True, env=env)
        shutil.copy2(HERE / 'review.py', app)
        (app / 'VERSION').write_text(version + '\n', encoding='ascii')
        subprocess.run([str(bundled / 'python.exe'), '-I', '-B', str(app / 'review.py'), '--self-check'],
                       check=True, timeout=105, env=env)

        csc = Path(os.environ['SystemRoot']) / 'Microsoft.NET' / 'Framework64' / 'v4.0.30319' / 'csc.exe'
        setup = work / 'SRC-Auto-Review-Setup.exe'
        subprocess.run([str(csc), '/nologo', '/target:winexe', '/platform:x64', '/optimize+',
                        '/r:System.Windows.Forms.dll', '/r:System.Drawing.dll', '/r:System.Web.Extensions.dll',
                        '/r:System.IO.Compression.dll', '/out:' + str(setup), str(HERE / 'ReviewSetup.cs')],
                       check=True)
        archive = work / ('SRC-Auto-Review-v' + version + '-win-x64.zip')
        with ZipFile(archive, 'w', ZIP_DEFLATED, compresslevel=6) as z:
            for path in sorted(app.rglob('*')):
                if path.is_file():
                    z.write(path, path.relative_to(app).as_posix())
        checksums = work / 'REVIEW-SHA256SUMS.txt'
        with checksums.open('w', encoding='ascii') as output:
            for path in (setup, archive):
                output.write(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name + '\n')
        for path in (setup, archive, checksums):
            os.replace(path, OUTPUT / path.name)
            print(OUTPUT / path.name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--runtime', type=Path, default=PROJECT / 'runtime' / 'python')
    parser.add_argument('--wheels', type=Path)
    args = parser.parse_args()
    build(args.version, args.runtime.resolve(), args.wheels.resolve() if args.wheels else None)
