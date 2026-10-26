"""Frozen import checks through the real local engine; no model requests."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from . import chatgpt, codex_history, codex_import, mover, common


def normal_import_with_saved_followups(require, compressed=False):
    from .memory_audit import isolated_connections
    with tempfile.TemporaryDirectory(prefix='ai-first-normal-import-audit-') as temporary:
        base = Path(temporary)
        home = base/'home'; roaming = home/'AppData/Roaming'; local = home/'AppData/Local'
        codex = base/'codex'; project = base/'existing-project'; scratch = base/'temp'
        cursor = home/('Library/Application Support/Cursor/User' if sys.platform == 'darwin' else 'AppData/Roaming/Cursor/User')
        for path in (home,roaming,local,codex,project,scratch,cursor): path.mkdir(parents=True,exist_ok=True)
        environment = {key:value for key,value in os.environ.items() if key.upper() in {'PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT'}}
        environment.update(HOME=str(home),USERPROFILE=str(home),APPDATA=str(roaming),LOCALAPPDATA=str(local),
            CODEX_HOME=str(codex),CURSOR_DESKTOP_USER_DIR=str(cursor),TEMP=str(scratch),TMP=str(scratch),PYTHONUTF8='1')
        with patch.dict(os.environ,environment,clear=True), patch.object(common,'_isolated_home',home), \
                patch.object(common,'_registry_env',return_value=''), patch.object(tempfile,'tempdir',str(scratch)), \
                patch.object(mover,'TEST_ENV',environment), patch.object(mover,'_history_file',return_value=base/'history.json'), \
                patch.object(mover,'log'), isolated_connections(base):
            with closing(sqlite3.connect(codex/'state_5.sqlite')) as db:
                db.executescript('''
CREATE TABLE projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,metadata TEXT NOT NULL DEFAULT '{}',position INTEGER NOT NULL,created_at_ms INTEGER NOT NULL,updated_at_ms INTEGER NOT NULL);
CREATE TABLE project_roots(project_id TEXT NOT NULL REFERENCES projects(id),position INTEGER NOT NULL,path TEXT NOT NULL,PRIMARY KEY(project_id,position));
CREATE TABLE threads(id TEXT PRIMARY KEY,rollout_path TEXT NOT NULL,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL,source TEXT NOT NULL,model_provider TEXT NOT NULL,cwd TEXT NOT NULL,title TEXT NOT NULL,sandbox_policy TEXT NOT NULL,approval_mode TEXT NOT NULL,has_user_event INTEGER DEFAULT 0,first_user_message TEXT NOT NULL DEFAULT '',preview TEXT NOT NULL DEFAULT '',created_at_ms INTEGER,updated_at_ms INTEGER,recency_at INTEGER DEFAULT 0,recency_at_ms INTEGER DEFAULT 0,thread_source TEXT,history_mode TEXT DEFAULT 'legacy',name TEXT,originator TEXT,project_id TEXT REFERENCES projects(id));
''')
            document = {'id':str(uuid.uuid4()),'cwd':str(project),'messages':[
                {'role':'user','content':'synthetic original question'},
                {'role':'assistant','content':[{'type':'thinking','text':'synthetic old thinking'},
                    {'type':'text','text':'synthetic original answer'}]}]}
            source = base/'source.json';source.write_text(json.dumps(document),encoding='utf-8')
            seeded = {}; require(mover._import_document(source,document,'cursor_desktop',seeded)[0]=='ok')
            source_database = cursor/'globalStorage/state.vscdb'
            before = hashlib.sha256(source_database.read_bytes()).hexdigest()
            details = {}; require(mover.move_one('cursor_desktop',{'id':seeded['importedId'],'title':'Synthetic audit'},
                'chatgpt_work',str(project),details)[0]=='ok')
            rollout = Path(details['location'])
            records = [json.loads(line) for line in rollout.read_text(encoding='utf-8').splitlines() if line.strip()]
            require(records[0]['payload']['dialog_mover_import_format']==codex_import.HISTORY_FORMAT)
            require(not any(r.get('type')=='response_item' and r['payload'].get('type') in codex_import.NONPORTABLE_ITEMS for r in records))
            require(any(r.get('dialog_mover_original',{}).get('reason')=='foreign_reasoning' for r in records))
            # Append synthetic, completed native-format turns. This tests saved
            # history round trips, not first/second responses from a model.
            ordinal = max(r['ordinal'] for r in records)+1
            for number in (1,2):
                stamp = (datetime.now(timezone.utc)+timedelta(seconds=number)).isoformat()
                turn = str(uuid.uuid4()); user_id = str(uuid.uuid4()); answer_id = str(uuid.uuid4())
                payloads = [
                    ('event_msg',{'type':'task_started','turn_id':turn,'model_context_window':None}),
                    ('response_item',{'type':'message','role':'user','content':[{'type':'input_text','text':f'synthetic followup {number}'}]}),
                    ('event_msg',{'type':'item_completed','thread_id':details['importedId'],'turn_id':turn,
                        'item':{'type':'UserMessage','id':user_id,'content':[{'type':'text','text':f'synthetic followup {number}','text_elements':[]}]}}),
                    ('response_item',{'type':'message','role':'assistant','content':[{'type':'output_text','text':f'synthetic saved answer {number}'}]}),
                    ('event_msg',{'type':'item_completed','thread_id':details['importedId'],'turn_id':turn,
                        'item':{'type':'AgentMessage','id':answer_id,'phase':'final_answer','content':[{'type':'Text','text':f'synthetic saved answer {number}'}]}}),
                    ('event_msg',{'type':'task_complete','turn_id':turn,'last_agent_message':None})]
                with rollout.open('a',encoding='utf-8') as stream:
                    for kind,payload in payloads:
                        stream.write(json.dumps({'timestamp':stamp,'type':kind,'ordinal':ordinal,'payload':payload})+'\n');ordinal+=1
                saved = hashlib.sha256(rollout.read_bytes()).hexdigest()
                exported = base/f'round-{number}.json'
                result = mover._run(['export',details['importedId'],'--from','codex','--out',str(exported)],environment)
                require(result.returncode==0)
                readable = exported.read_text(encoding='utf-8')
                for wanted in ('synthetic original question','synthetic original answer','synthetic old thinking',
                        f'synthetic followup {number}',f'synthetic saved answer {number}'):
                    require(wanted in readable)
                require(hashlib.sha256(rollout.read_bytes()).hexdigest()==saved)
            require(hashlib.sha256(source_database.read_bytes()).hexdigest()==before)
            if compressed:
                import zstandard
                raw = rollout.read_bytes()
                packed = Path(str(rollout) + '.zst')
                packed.write_bytes(zstandard.ZstdCompressor(write_content_size=False).compress(raw))
                rollout.unlink()  # Only this audit's synthetic history; index keeps logical path.
                if os.name == 'nt':
                    with closing(sqlite3.connect(codex/'state_5.sqlite')) as db, db:
                        db.execute('UPDATE threads SET rollout_path=? WHERE id=?',
                                   ('\\\\?\\'+str(rollout),details['importedId']))
                packed_hash = hashlib.sha256(packed.read_bytes()).hexdigest()
                (codex/'.codex-global-state.json').write_text(json.dumps({'local-projects': {
                    'synthetic': {'name': '合成项目', 'rootPaths': [str(project)]}}}), encoding='utf-8')
                entries = chatgpt.local_data(codex)['projects'][0]['sessions']
                require(len(entries)==1 and entries[0]['movable'])
                exported = mover.export_document('chatgpt_work', entries[0])
                text = json.dumps(exported)
                for wanted in ('synthetic original question','synthetic old thinking','synthetic followup 2','synthetic saved answer 2'):
                    require(wanted in text)
                require(not rollout.exists() and hashlib.sha256(packed.read_bytes()).hexdigest()==packed_hash)
                packed.write_bytes(packed.read_bytes()[:-1])
                try:
                    with codex_history.export_home(codex, details['importedId']):
                        raise AssertionError('Truncated compressed frame must be rejected')
                except ValueError:
                    pass


def run(report: Path) -> int:
    checks = {}
    def check(name, operation):
        try:
            operation()
            checks[name] = True
        except Exception:
            checks[name] = False
    def require(value):
        if not value: raise AssertionError('Synthetic compatibility check failed')
    identity = str(uuid.uuid4())
    stamp = '2026-10-23T00:00:00Z'
    def record(payload): return {'timestamp':stamp,'type':'response_item','payload':payload}
    meta = {'timestamp':stamp,'type':'session_meta','payload':{'id':identity}}
    user = record({'type':'message','role':'user','content':[{'type':'input_text','text':'synthetic question'}]})
    answer = record({'type':'message','role':'assistant','content':[{'type':'output_text','text':'synthetic answer'}]})
    reasoning = {'type':'reasoning','summary':[{'type':'summary_text','text':'合成历史思考\n' * 800}],
                 'encrypted_content':None}
    def thinking():
        source = [meta,user,record(reasoning),answer]
        before = copy.deepcopy(source)
        result = codex_import.paginated_history(source,identity)
        require(source == before)
        require(not any(entry.get('type')=='response_item' and entry['payload']['type']=='reasoning' for entry in result))
        require(not any(entry.get('payload',{}).get('item',{}).get('type')=='Reasoning' for entry in result))
        note = next(entry for entry in result if entry.get('dialog_mover_original',{}).get('reason')=='foreign_reasoning')
        require(note['dialog_mover_original']['response_item']==reasoning)
        require(reasoning['summary'][0]['text'] in note['payload']['content'][0]['text'])
    check('foreign_reasoning_is_lossless_history_not_provider_state',thinking)
    def hosted():
        originals = [{'type':'web_search_call','id':'synthetic-search','status':'completed','action':{'query':'synthetic query'}},
                     {'type':'compaction','id':'synthetic-compaction','encrypted_content':'synthetic-opaque'}]
        result = codex_import.paginated_history([meta,user,*(record(p) for p in originals),answer],identity)
        require([entry['dialog_mover_original']['response_item'] for entry in result if entry.get('dialog_mover_original')]==originals)
        require(all(entry['payload']['type']=='message' for entry in result if entry['type']=='response_item'))
    check('hosted_and_compaction_payloads_are_archived_not_replayed',hosted)
    def paired():
        result = codex_import.paginated_history([meta,user,
            record({'type':'function_call','name':'mcp__'+'x'*80,'call_id':'call_'+'y'*80,'arguments':'{"full":"synthetic"}'}),
            record({'type':'function_call_output','call_id':'call_'+'y'*80,'output':'synthetic complete result'}),answer],identity)
        calls = [entry['payload'] for entry in result if entry['type']=='response_item' and 'call_id' in entry['payload']]
        require(len(calls)==2 and calls[0]['call_id']==calls[1]['call_id'] and len(calls[0]['name'])<=64)
        require(calls[1]['output']=='synthetic complete result')
    check('complete_tool_pairs_and_identifier_protection_are_preserved',paired)
    def migration():
        with tempfile.TemporaryDirectory(prefix='ai-first-codex-format-audit-') as temporary:
            history = Path(temporary)/'history.json'
            key = mover.history_key('cursor_desktop','synthetic-history','chatgpt_work',temporary)
            history.write_text(json.dumps({key:{'time':1,'format':'paginated-import-v3'}}),encoding='utf-8')
            with patch.object(mover,'_history_file',return_value=history):
                require(not mover.already_moved('cursor_desktop','synthetic-history','chatgpt_work',temporary))
                mover._record_move('cursor_desktop','synthetic-history','chatgpt_work',temporary)
                require(mover.already_moved('cursor_desktop','synthetic-history','chatgpt_work',temporary))
        require(codex_import.HISTORY_FORMAT=='paginated-import-v4')
    check('old_import_can_be_copied_once_and_new_import_still_deduplicates',migration)
    def strict():
        for payload in ({'type':'unrecognized-fixture'}, {'type':'reasoning','summary':'malformed-fixture'}):
            try: codex_import.paginated_history([meta,user,record(payload),answer],identity)
            except ValueError: continue
            raise AssertionError('Unknown or malformed history must be rejected')
    check('unknown_or_malformed_history_is_still_rejected',strict)
    check('normal_cursor_import_and_two_saved_followups_round_trip',lambda:normal_import_with_saved_followups(require))
    check('compressed_project_history_listing_export_and_truncation_guard',lambda:normal_import_with_saved_followups(require,compressed=True))
    passed = all(checks.values())
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps({'passed':passed,'checks':checks,'syntheticOnly':True,'modelRequests':0,
        'nativeContinuationVerified':False,'savedFollowupRoundTrips':2,
        'scope':'Normal local Cursor import, two synthetic saved followup round trips and conversion/dedup protection; isolated databases only, no real chat, authentication, network or model request'},
        ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if passed else 1
