"""Explicitly authorized, read-only metadata projection for one workbench import.

No conversation text, identifiers, paths, credentials or opaque state values are
returned. SQLite JSON projection selects metadata without materializing message
content as Python objects. This is diagnostic code, never a migration test.
"""
from __future__ import annotations
import argparse
import collections
import json
import os
import re
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ENVELOPES={'session_meta','response_item','event_msg','turn_context','compacted'}
KINDS={'message','reasoning','function_call','function_call_output','custom_tool_call','custom_tool_call_output',
       'web_search_call','computer_call','code_interpreter_call','compaction','mcp_call','mcp_list_tools',
       'task_started','task_complete','item_started','item_completed','user_message','agent_message',
       'agent_reasoning','token_count','error','turn_aborted'}
ITEMS={'UserMessage','AgentMessage','Reasoning','DynamicToolCall','WebSearch','ContextCompaction',
       'userMessage','agentMessage','reasoning','dynamicToolCall','webSearch','contextCompaction'}
MARKERS={'response_id','previous_response_id','last_response_id','state_id','encrypted_content',
         'reasoning_state','serialized_response','provider_response_id'}

def type_label(value):
    # Enum identifiers only: no free text, record IDs, paths or opaque values.
    return value if isinstance(value,str) and re.fullmatch(r'[A-Za-z][A-Za-z_]{0,63}',value) else 'other'


def plain(path):
    if not path.is_absolute() or any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (path,*path.parents)):
        raise ValueError('unverified_location')


def projection(path,expected_id,*,exact_title_match=False):
    plain(path)
    before=path.stat()
    if before.st_size>100*1024*1024: raise ValueError('oversized_record')
    counts=collections.Counter(); later=collections.Counter(); markers=collections.Counter(); formats=set()
    import_at=None; lines=0
    with closing(sqlite3.connect(':memory:')) as json_reader, path.open('rb') as stream:
        for raw in stream:
            if len(raw)>16*1024*1024 or lines>=100000: raise ValueError('oversized_record')
            if not raw.strip(): continue
            envelope,kind,item,role,timestamp,identity,version,encrypted,summary_count=json_reader.execute('''
                SELECT json_extract(?1,'$.type'),json_extract(?1,'$.payload.type'),
                       json_extract(?1,'$.payload.item.type'),json_extract(?1,'$.payload.role'),
                       json_extract(?1,'$.timestamp'),
                       CASE WHEN json_extract(?1,'$.type')='session_meta' THEN json_extract(?1,'$.payload.id') END,
                       json_extract(?1,'$.payload.dialog_mover_import_format'),
                       CASE WHEN json_extract(?1,'$.payload.encrypted_content') IS NOT NULL
                              AND json_extract(?1,'$.payload.encrypted_content')!='' THEN 1 ELSE 0 END,
                       CASE WHEN json_type(?1,'$.payload.summary')='array' THEN json_array_length(?1,'$.payload.summary') ELSE 0 END
                ''',(raw,)).fetchone()
            if lines==0:
                if envelope!='session_meta' or identity!=expected_id: raise ValueError('record_identity_mismatch')
                if not exact_title_match and version not in {'paginated-import-v1','paginated-import-v2','paginated-import-v3','paginated-import-v4'}:
                    raise ValueError('record_is_not_a_workbench_import')
                if version is None: formats.add('absent')
                import_at=datetime.fromisoformat(timestamp.replace('Z','+00:00'))
            lines+=1
            tags=['envelope:'+ type_label(envelope)]
            if kind is not None: tags.append('payload:'+ type_label(kind))
            if item is not None: tags.append('display:'+ type_label(item))
            if kind=='message': tags.append('role:'+ (role if role in {'user','assistant','system','developer'} else 'other'))
            if kind=='reasoning': tags.append('reasoning:opaque-present' if encrypted else 'reasoning:opaque-absent')
            if kind=='reasoning' and summary_count: tags.append('reasoning:visible-summary-present')
            counts.update(tags)
            try:
                if lines>1 and datetime.fromisoformat(timestamp.replace('Z','+00:00'))>import_at: later.update(tags)
            except (TypeError,ValueError): pass
            if version is not None: formats.add(version if version in {'paginated-import-v1','paginated-import-v2','paginated-import-v3','paginated-import-v4'} else 'unrecognized')
            for key,count in json_reader.execute("SELECT key,COUNT(*) FROM json_tree(?) WHERE key IN ("+','.join('?' for _ in MARKERS)+") AND atom IS NOT NULL GROUP BY key",(raw,*sorted(MARKERS))):
                markers[key]+=count
    after=path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns): raise ValueError('record_changed_during_inspection')
    return {'formatVersions':sorted(formats),'recordCount':lines,'types':dict(counts),
            'typesWithTimestampAfterRegistration':dict(later),'continuationMarkerCounts':dict(markers)}


def latest_import(title=None):
    sys.path.insert(0,str(ROOT/'dialog-mover'))
    from core import common
    from core.chatgpt import _norm
    histories=[common.localappdata()/'AI一手工具工作台/memory-preview/mover/history.json',common.appdata()/'对话搬家/history.json']
    entries=[]
    for path in histories:
        plain(path)
        if not path.is_file(): continue
        if path.stat().st_size>4*1024*1024: raise ValueError('oversized_workbench_metadata')
        for key,value in json.loads(path.read_text(encoding='utf-8')).items():
            if not (key.startswith('cursor_desktop:') and isinstance(value,dict) and type(value.get('time')) is int): continue
            for target in ('chatgpt_work','codex'):
                separator='->'+target+':'
                if separator in key: entries.append((value['time'],key.split(separator,1)[1],target))
    if not entries: raise ValueError('no_matching_workbench_import')
    stamp,directory,target=max(entries,key=lambda row:row[0])
    root=common.codex_home()
    if root is None: raise ValueError('destination_not_found')
    root=root.resolve(); database=root/'state_5.sqlite';plain(database)
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=3)) as connection:
        if title is not None:
            # The exact title is supplied by the user. No title or content is
            # selected or emitted, and no fuzzy search or unrelated scan occurs.
            rows=connection.execute('''SELECT id,rollout_path,history_mode FROM threads
                WHERE title=? OR name=?
                ORDER BY created_at DESC LIMIT 2''',(title,title)).fetchall()
        else:
            rows=connection.execute('''SELECT id,rollout_path,history_mode FROM threads
                WHERE created_at BETWEEN ? AND ? AND cwd=? COLLATE NOCASE
                ORDER BY created_at DESC LIMIT 4''',(stamp-30,stamp+1,directory)).fetchall()
    if len(rows)!=1: raise ValueError('matching_import_is_ambiguous' if rows else 'matching_import_not_found')
    identity,location,mode=rows[0]
    path=Path(location);plain(path)
    resolved=path.resolve(); boundary=(root/'sessions').resolve()
    inside=_norm(str(resolved)).startswith(_norm(str(boundary))+'\\') if sys.platform=='win32' else resolved.is_relative_to(boundary)
    if not inside: raise ValueError('destination_record_outside_store')
    result=projection(path,identity,exact_title_match=title is not None)
    result['historyMode']=mode if mode in {'paginated','legacy'} else 'other'
    result['destinationMode']=target
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--approved-latest-cursor-import-metadata',action='store_true',required=True)
    parser.add_argument('--exact-title')
    args=parser.parse_args()
    try: print(json.dumps({'readOnly':True,'bodyExposed':False,'authenticationAccessed':False,**latest_import(args.exact_title)},ensure_ascii=False))
    except Exception as error:
        # Fixed codes only: never include paths, SQL values or source payloads.
        code=str(error) if type(error) is ValueError and str(error) in {
            'unverified_location','oversized_record','record_identity_mismatch','record_is_not_a_workbench_import','record_changed_during_inspection',
            'oversized_workbench_metadata','no_matching_workbench_import','destination_not_found',
            'matching_import_is_ambiguous','matching_import_not_found','destination_record_outside_store'} else type(error).__name__
        print(json.dumps({'readOnly':True,'completed':False,'errorCode':code}))
