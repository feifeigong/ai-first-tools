from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'macos'))
from release_highlights import Highlights,parse

class ReleaseHighlightsTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.manifest=ROOT/'workspace/assets/whats-new.json'
        self.version=json.loads((ROOT/'macos/version.json').read_text(encoding='utf-8'))['release']

    def test_bundled_highlights_match_both_platform_versions(self):
        data=json.loads(self.manifest.read_text(encoding='utf-8'))
        self.assertEqual(data['versions']['macos'],self.version)
        import xml.etree.ElementTree as ET
        self.assertEqual(data['versions']['windows'],ET.parse(ROOT/'workspace/AIFirst.Workspace.csproj').findtext('.//Version'))
        self.assertTrue(parse(self.manifest.read_text(encoding='utf-8'),self.version)['items'])

    def test_once_per_acknowledged_release_survives_restart_and_keeps_old_versions(self):
        first=Highlights(self.manifest,self.root,self.version)
        self.assertTrue(first.info()['automatic']);self.assertTrue(first.acknowledge(self.version))
        reopened=Highlights(self.manifest,self.root,self.version)
        self.assertFalse(reopened.info()['automatic']);self.assertTrue(reopened.has_seen())
        new_version='0.4.0-macos-preview.999'
        changed=json.loads(self.manifest.read_text(encoding='utf-8'));changed['versions']['macos']=new_version
        other=self.root/'next.json';other.write_text(json.dumps(changed),encoding='utf-8')
        next_release=Highlights(other,self.root,new_version)
        self.assertTrue(next_release.info()['automatic']);self.assertTrue(next_release.acknowledge(new_version))
        self.assertFalse(Highlights(self.manifest,self.root,self.version).info()['automatic'])

    def test_foreign_or_unknown_state_is_never_overwritten_and_does_not_interrupt(self):
        for data in ('broken',json.dumps({'schema':2,'seen':[]}),json.dumps({'schema':1,'seen':['../other']}),json.dumps({'schema':1,'seen':[],'other':True}),'x'*17000):
            file=self.root/'whats-new.json';file.write_text(data,encoding='utf-8')
            state=Highlights(self.manifest,self.root,self.version)
            self.assertFalse(state.info()['automatic']);self.assertFalse(state.acknowledge(self.version))
            self.assertFalse(state.has_seen())
            self.assertEqual(file.read_text(encoding='utf-8'),data)

    def test_malformed_mismatched_and_duplicate_content_is_not_displayed(self):
        raw=self.manifest.read_text(encoding='utf-8')
        for data in ('broken',raw.replace(self.version,'0.4.0-macos-preview.999'),raw.replace('"schema": 1','"schema": true'),raw.replace('"items": [','"items": null,"items": [')):
            file=self.root/'notes.json';file.write_text(data,encoding='utf-8')
            self.assertEqual(Highlights(file,self.root,self.version).info(),{})

    def test_wrong_acknowledgement_cannot_write_a_file_or_consume_current_notes(self):
        state=Highlights(self.manifest,self.root,self.version)
        self.assertFalse(state.acknowledge('../other'));self.assertTrue(state.info()['automatic'])
        self.assertFalse((self.root/'whats-new.json').exists())

    def test_bridge_uses_only_bundled_release_and_fixed_public_download_domain(self):
        from entry import MacApi
        api=MacApi(True);api._release_highlights=Highlights(self.manifest,self.root,self.version)
        with patch('entry.open_external') as opened:
            self.assertTrue(api.release_notes()['automatic'])
            self.assertTrue(api.open_release_notes()['ok'])
            opened.assert_called_once_with('https://github.com/feifeigong/ai-first-tools/releases/tag/v'+self.version)
        self.assertTrue(api.acknowledge_release_notes(self.version)['ok'])
        self.assertFalse(api.release_notes()['automatic'])

if __name__=='__main__':unittest.main()
