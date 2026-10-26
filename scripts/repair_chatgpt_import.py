"""Plan or explicitly apply a local compatible copy of one user-named import.

Default planning reads only exact-title index metadata and first-line format
metadata. Applying requires separate authorization for that thread's content.
No authentication or model endpoint is accessed. Output omits paths and IDs.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'dialog-mover'))
from core import codex_repair, common


def resolve(title):
    root = common.codex_home()
    if root is None: raise ValueError('没有找到 ChatGPT 的本地记录。')
    root = root.absolute(); codex_repair.plain(root / 'state_5.sqlite')
    with closing(sqlite3.connect((root/'state_5.sqlite').as_uri()+'?mode=ro', uri=True, timeout=3)) as c:
        rows = c.execute('SELECT id,rollout_path,cwd,originator,source FROM threads WHERE title=? OR name=? LIMIT 2', (title,title)).fetchall()
    if len(rows) != 1: raise ValueError('这个标题没有匹配到唯一记录，未读取聊天正文。')
    identity, current, cwd, origin, source = rows[0]
    if origin != 'codex_work_desktop' or source != 'vscode': raise ValueError('目标不是已知的本机 Work 记录。')
    current = Path(current); codex_repair.plain(current)
    if not codex_repair.inside(current, root/'sessions'): raise ValueError('当前记录不在本地记录库内。')
    candidates = list((root/'sessions').glob('*/*/*/*'+identity+'.jsonl'))
    if len(candidates) > 8: raise ValueError('同编号的记录过多，未猜测选择。')
    old = []
    with closing(sqlite3.connect(':memory:')) as reader:
        for path in candidates:
            codex_repair.plain(path)
            with path.open('rb') as stream: first = stream.readline(16*1024*1024+1)
            if len(first) > 16*1024*1024: raise ValueError('记录头过大，未读取正文。')
            envelope, found_id, version = reader.execute("SELECT json_extract(?1,'$.type'),json_extract(?1,'$.payload.id'),json_extract(?1,'$.payload.dialog_mover_import_format')", (first,)).fetchone()
            if envelope == 'session_meta' and found_id == identity and version in {'paginated-import-v1','paginated-import-v2','paginated-import-v3'}:
                old.append(path)
    if len(old) != 1: raise ValueError('没有找到唯一的旧版搬入文件，未猜测修复。')
    paths = old if old[0].samefile(current) else old + [current]
    return root, identity, paths, cwd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exact-title', required=True)
    parser.add_argument('--apply-approved-compatible-copy', action='store_true')
    parser.add_argument('--open-copy', action='store_true')
    args = parser.parse_args()
    try:
        root, identity, paths, cwd = resolve(args.exact_title)
        if not args.apply_approved_compatible_copy:
            print(json.dumps({'ready': True, 'sourceFiles': len(paths), 'readsBody': False,
                              'createsNewCopy': True, 'keepsOriginal': True, 'requiresContentPermission': True}))
            return 0
        env = {'CODEX_HOME': str(root), 'APPDATA': str(common.appdata()), 'LOCALAPPDATA': str(common.localappdata())}
        result = codex_repair.create_copy(root=root, archive_root=common.localappdata()/'AI一手工具工作台/memory-preview/codex-repairs',
            source_paths=paths, old_id=identity, title=args.exact_title, directory=cwd, env=env, approved=True)
        opened = False
        if args.open_copy:
            common.open_external('codex://threads/' + result['newId']); opened = True
        result.pop('newId', None)
        print(json.dumps({**result, 'openRequested': opened, 'nativeContinuationVerified': False}))
        return 0
    except Exception as error:
        print(json.dumps({'ok': False, 'error': str(error) if type(error) is ValueError else '修复未完成，原记录已保留。'}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
