"""Bundled, text-only release highlights and an independent acknowledgement ledger."""
from __future__ import annotations
import json
import os
import re
import uuid
import unicodedata
from pathlib import Path

def version_valid(value):
    return isinstance(value,str) and len(value)<=48 and re.fullmatch(r'\d+\.\d+\.\d+(?:-macos-preview\.\d+)?',value) is not None

def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError('Duplicate field')
        result[key]=value
    return result

def fields(value,names):
    if not isinstance(value,dict) or set(value)!=set(names): raise ValueError('Unknown format')

def text(value,key,limit):
    item=value.get(key)
    if not isinstance(item,str) or not item.strip() or len(item)>limit or any(unicodedata.category(c) in {'Cc','Cs'} for c in item): raise ValueError('Invalid text')
    return item

def parse(raw,version):
    if len(raw.encode('utf-8'))>32768 or not version_valid(version): raise ValueError('Invalid release')
    value=json.loads(raw,object_pairs_hook=unique)
    fields(value,('schema','versions','title','description','items'))
    if type(value['schema']) is not int or value['schema']!=1: raise ValueError('Unknown format')
    versions=value['versions'];fields(versions,('windows','macos'))
    if not version_valid(versions['windows']) or '-' in versions['windows'] or not version_valid(versions['macos']) or '-macos-preview.' not in versions['macos'] or versions['macos']!=version: raise ValueError('Release mismatch')
    items=value['items']
    if not isinstance(items,list) or not 1<=len(items)<=3: raise ValueError('Invalid highlights')
    result=[]
    for row in items:
        fields(row,('label','title','text'));label=text(row,'label',4)
        if label not in {'新增','改进','修复','完善'}: raise ValueError('Unknown label')
        result.append({'label':label,'title':text(row,'title',32),'text':text(row,'text',140)})
    return {'release':version,'title':text(value,'title',32),'description':text(value,'description',80),'items':result}

class Highlights:
    def __init__(self,manifest:Path,directory:Path,version:str):
        self.path=directory/'whats-new.json';self.version=version;self.acknowledged=False
        try:
            if manifest.stat().st_size>32768: raise ValueError('Too large')
            self.content=parse(manifest.read_text(encoding='utf-8'),version)
        except (OSError,ValueError,TypeError,RecursionError): self.content=None

    def _read(self):
        if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (self.path,*self.path.parents)): raise ValueError('Linked settings')
        if not self.path.exists(): return []
        if self.path.stat().st_size>16384: raise ValueError('Too large')
        data=json.loads(self.path.read_text(encoding='utf-8'),object_pairs_hook=unique);fields(data,('schema','seen'))
        seen=data['seen']
        if type(data['schema']) is not int or data['schema']!=1 or not isinstance(seen,list) or len(seen)>64 or any(not version_valid(x) for x in seen) or len(set(seen))!=len(seen): raise ValueError('Unknown settings')
        return seen

    def info(self):
        if self.content is None:return {}
        try: automatic=not self.acknowledged and self.version not in self._read()
        except (OSError,ValueError,TypeError,RecursionError): automatic=False
        return {**self.content,'automatic':automatic}

    def has_seen(self):
        try:return self.content is not None and self.version in self._read()
        except (OSError,ValueError,TypeError,RecursionError):return False

    def acknowledge(self,version):
        if self.content is None or version!=self.version:return False
        self.acknowledged=True;temporary=None
        try:
            seen=self._read()
            if version in seen:return True
            self.path.parent.mkdir(parents=True,exist_ok=True)
            self._read()
            temporary=self.path.with_name(self.path.name+'.'+uuid.uuid4().hex+'.tmp')
            temporary.write_text(json.dumps({'schema':1,'seen':[*seen[-63:],version]}),encoding='utf-8')
            os.replace(temporary,self.path);return True
        except (OSError,ValueError,TypeError,RecursionError):return False
        finally:
            if temporary is not None:
                try:temporary.unlink(missing_ok=True)
                except OSError:pass
