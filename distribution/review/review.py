"""Local report reader and bounded, offline Bandit review for owned Python code."""

import json
import os
import queue
import re
import stat
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent.parent
MAX_FILE = 1024 * 1024
MAX_TOTAL = 20 * MAX_FILE
MAX_FILES = 1000
EXCLUDED = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', 'vendor',
            'dist', 'build', 'runtime', 'reports', 'logs', 'data'}
RULES = {
    'B102': '动态执行代码，核对输入来源和调用必要性。',
    'B301': '不安全的反序列化，检查输入是否来自信任边界之外。',
    'B307': '动态表达式求值，考虑改用受限解析或明确分支。',
    'B501': '关闭 TLS 证书验证，配置可信证书并恢复校验。',
    'B506': 'YAML 加载方式可能不安全，检查是否可使用安全加载。',
    'B602': '子进程通过 shell 执行，优先使用参数列表和明确的可执行文件。',
    'B608': '可能拼接 SQL，检查是否使用参数化查询。',
}


def is_link(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 1024)


def read_file(path, limit):
    for part in (path, *path.parents):
        if is_link(part):
            raise ValueError('不读取符号链接、联接或重解析点。')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    with os.fdopen(os.open(str(path), flags), 'rb') as stream:
        if os.name == 'nt':
            import ctypes
            import msvcrt
            final_path = ctypes.WinDLL('kernel32').GetFinalPathNameByHandleW
            final_path.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32)
            final_path.restype = ctypes.c_uint32
            path_buffer = ctypes.create_unicode_buffer(32768)
            size = final_path(msvcrt.get_osfhandle(stream.fileno()), path_buffer, len(path_buffer), 0)
            actual = path_buffer.value
            if actual.startswith('\\\\?\\'):
                actual = actual[4:]
            if not size or size >= len(path_buffer) or os.path.normcase(actual) != os.path.normcase(str(path)):
                raise ValueError('文件打开后发现路径变化。')
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('只读取普通文件。')
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('文件大小超出本地审阅上限。')
    return raw


def snapshot(source, destination):
    for part in (source, *source.parents):
        if is_link(part):
            raise ValueError('请选择实际的本地项目目录。')
    if source == Path(source.anchor) or str(source).startswith('\\\\') or source == Path.home():
        raise ValueError('请选择具体的本地源码目录。')

    def fail_walk(error):
        raise error

    copied = skipped = total = visited = 0
    for base, folders, names in os.walk(source, followlinks=False, onerror=fail_walk):
        visited += len(folders) + len(names)
        if visited > 10000:
            raise ValueError('目录项超过 10,000 个，请缩小审阅范围。')
        parent = Path(base)
        before = len(folders)
        folders[:] = sorted(name for name in folders if not name.startswith('.')
                            and name.lower() not in EXCLUDED and not is_link(parent / name))
        skipped += before - len(folders)
        for name in sorted(names):
            path = parent / name
            relative = path.relative_to(source)
            if (path.suffix.lower() != '.py' or name.startswith('.') or is_link(path)
                    or re.search(r'(?i)secret|credential|private[_-]?key|\.env', relative.as_posix())
                    or not relative.as_posix().isprintable()):
                skipped += 1
                continue
            raw = read_file(path, MAX_FILE)
            try:
                raw.decode('utf-8-sig')
            except UnicodeError:
                skipped += 1
                continue
            total += len(raw)
            if copied >= MAX_FILES or total > MAX_TOTAL:
                raise ValueError('超过 1,000 个 Python 文件或 20 MiB，请缩小审阅范围。')
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            copied += 1
    if not copied:
        raise ValueError('所选目录没有可审阅的 UTF-8 Python 文件。')
    return copied, skipped


def format_result(document, copied, skipped):
    results = document['results']
    metrics = document['metrics']
    total = len(set(metrics) - {'_totals'})
    lines = [
        'Python 源码审阅',
        '状态：' + ('部分文件未完成分析' if document['errors'] or total != copied else '完成'),
        f'纳入 {copied} 个文件，Bandit 记录 {total} 个文件，排除 {skipped} 个文件或目录。',
        f'规则提示 {len(results)} 条，仅供代码维护者复核。',
        '',
    ]
    for row in results:
        rule = row['test_id']
        filename = row['filename'].replace('\\', '/')
        if filename.startswith('./'):
            filename = filename[2:]
        lines.append(f"{filename}:{int(row['line_number'])} [{rule}] {RULES[rule]}")
    return '\n'.join(lines) + '\n'


def run_bandit(source, self_check=False):
    installed = ROOT.parent.name == 'versions' and (BASE / '.src-auto-review').is_file()
    work = ROOT if self_check else (BASE if installed else ROOT) / 'workspace'
    if not self_check:
        work.mkdir(exist_ok=True)
        if is_link(work):
            raise ValueError('审阅工作区必须是实际目录。')
    with tempfile.TemporaryDirectory(dir=str(work), prefix='review-') as temp:
        clean = Path(temp) / 'source'
        clean.mkdir()
        copied, skipped = snapshot(source, clean)
        # Keep plugin/cache writes inside the temporary directory.
        env = os.environ.copy()
        for key in ('TEMP', 'TMP', 'XDG_CACHE_HOME'):
            env[key] = temp
        result = subprocess.run(
            [sys.executable, '-I', '-B', '-X', 'utf8', '-m', 'bandit', '-r', '.', '-q',
             '-f', 'json', '-t', ','.join(RULES), '--ignore-nosec'],
            cwd=clean, env=env, capture_output=True, timeout=90,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if result.returncode not in (0, 1) or not result.stdout:
            raise ValueError('Bandit 未生成有效结果。')
        return format_result(json.loads(result.stdout), copied, skipped)


def main(self_check=False):
    root = tk.Tk()
    if self_check:
        root.withdraw()
    root.title('SRC-Auto 本地审阅版')
    root.geometry('890x620')
    root.minsize(570, 380)
    page = ttk.Frame(root, padding=20)
    page.pack(fill='both', expand=True)
    ttk.Label(page, text='SRC-Auto 本地审阅版', font=('Microsoft YaHei UI', 19, 'bold')).pack(anchor='w')
    ttk.Label(page, text='打开本机报告，或对有权读取的 Python 源码进行离线静态检查。').pack(anchor='w', pady=(4, 12))
    bar = ttk.Frame(page)
    bar.pack(fill='x', pady=(0, 8))
    status = tk.StringVar(value='请选择报告文件或源码目录。')
    box = scrolledtext.ScrolledText(page, wrap='word', font=('Microsoft YaHei UI', 11), state='disabled')
    box.pack(fill='both', expand=True)
    ttk.Label(page, textvariable=status, wraplength=500).pack(anchor='w', pady=(8, 0))
    pending = queue.Queue()
    reviewing = False

    def show(value, label):
        box.configure(state='normal')
        box.delete('1.0', 'end')
        box.insert('1.0', value)
        box.configure(state='disabled')
        status.set(label)

    def open_report():
        file = filedialog.askopenfilename(filetypes=[('本地文本报告', '*.md *.txt *.json')])
        if not file:
            return
        try:
            path = Path(os.path.abspath(file))
            if path.suffix.lower() not in {'.md', '.txt', '.json'}:
                raise ValueError('请选择 Markdown、TXT 或 JSON 文件。')
            show(read_file(path, 2 * MAX_FILE).decode('utf-8-sig'), '已打开 ' + path.name)
        except (OSError, UnicodeError, ValueError):
            messagebox.showerror('报告无法读取', '请确认文件为 UTF-8 文本、最多 2 MiB，且路径中没有链接。')

    def review_folder():
        nonlocal reviewing
        folder = filedialog.askdirectory(mustexist=True)
        if not folder or not messagebox.askyesno(
            '确认读取权限', '我有权读取此目录，并同意创建审阅期间使用的临时副本。是否开始？'
        ):
            return
        reviewing = True
        for button in buttons:
            button.configure(state='disabled')
        status.set('正在执行 Python 静态检查…')

        def worker():
            try:
                pending.put((True, run_bandit(Path(os.path.abspath(folder)))))
            except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                pending.put((False, '审阅未完成。请检查目录权限、文件数量与大小，并确认安装完整。'))

        def poll():
            nonlocal reviewing
            try:
                ok, value = pending.get_nowait()
            except queue.Empty:
                root.after(150, poll)
                return
            reviewing = False
            for button in buttons:
                button.configure(state='normal')
            show(value, '已生成本地审阅结果。' if ok else '本次审阅已停止。')

        threading.Thread(target=worker).start()
        root.after(150, poll)

    def save():
        if not box.get('1.0', 'end-1c'):
            return
        path = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('文本报告', '*.txt')])
        if path:
            try:
                Path(path).write_text(box.get('1.0', 'end-1c'), encoding='utf-8')
                status.set('已保存 ' + Path(path).name)
            except OSError:
                messagebox.showerror('保存失败', '请选择有写入权限的文件。')

    def close():
        if reviewing:
            messagebox.showinfo('审阅进行中', '请等当前静态检查结束后再关闭窗口。')
        else:
            root.destroy()

    buttons = [ttk.Button(bar, text=label, command=action)
               for label, action in [('打开报告', open_report), ('审阅 Python 目录', review_folder),
                                     ('另存当前文本', save)]]
    for button in buttons:
        button.pack(side='left', padx=(0, 8))
    root.protocol('WM_DELETE_WINDOW', close)
    if self_check:
        root.after_idle(root.destroy)
    root.mainloop()


if __name__ == '__main__':
    if sys.argv[1:] == ['--self-check']:
        main(self_check=True)
        with tempfile.TemporaryDirectory(dir=str(ROOT), prefix='smoke-') as folder:
            (Path(folder) / 'sample.py').write_text(
                'import requests\nrequests.get("https://example.invalid", verify=False)\n',
                encoding='utf-8',
            )
            report = run_bandit(Path(folder), self_check=True)
            if '状态：完成' not in report or 'sample.py:2 [B501]' not in report:
                sys.exit(1)
    else:
        main()
