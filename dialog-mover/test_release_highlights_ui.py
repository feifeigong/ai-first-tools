from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright
from test_macos_ui import BOOT

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from prepare_macos import prepare

def bootstrap():
    data=json.loads((ROOT/'workspace/assets/whats-new.json').read_text(encoding='utf-8'))
    data={'release':data['versions']['macos'],'title':data['title'],'description':data['description'],'items':data['items']}
    return BOOT+'''\nwindow.newsReads=0;window.acknowledged=0;window.fullNotesOpened=0;
    window.__notes=PAYLOAD;
    window.pywebview.api.release_notes=async()=>{window.newsReads++;return {...window.__notes,automatic:localStorage.getItem('synthetic-notes-seen')!==window.__notes.release};};
    window.pywebview.api.acknowledge_release_notes=async release=>{window.acknowledged++;localStorage.setItem('synthetic-notes-seen',release);return {ok:true};};
    window.pywebview.api.open_release_notes=async()=>{window.fullNotesOpened++;return {ok:true};};
    '''.replace('PAYLOAD',json.dumps(data))

class HighlightsUiTests(unittest.TestCase):
    def test_automatic_once_manual_reopen_all_close_methods_and_keyboard_focus(self):
        with tempfile.TemporaryDirectory() as temporary,sync_playwright() as runtime:
            resources=prepare(Path(temporary));browser=runtime.chromium.launch(channel='msedge' if sys.platform=='win32' else None,headless=True)
            try:
                page=browser.new_page(viewport={'width':1200,'height':820});page.add_init_script(bootstrap())
                page.goto((resources/'ui/index.html').as_uri());dialog=page.locator('#release-highlights')
                dialog.wait_for(state='visible');self.assertEqual(page.evaluate('document.activeElement.id'),'release-done')
                page.keyboard.press('Tab');self.assertEqual(page.evaluate('document.activeElement.id'),'release-close')
                page.keyboard.press('Escape');page.wait_for_function('window.acknowledged===1')
                self.assertEqual(page.evaluate('document.activeElement.id'),'workspace-version')
                page.reload();page.wait_for_function('window.newsReads>0');page.wait_for_timeout(900);self.assertFalse(dialog.is_visible())
                page.get_by_role('button',name='查看本次更新').click();dialog.wait_for(state='visible')
                page.get_by_role('button',name='完整更新说明 ↗').click();self.assertEqual(page.evaluate('window.fullNotesOpened'),1)
                page.get_by_role('button',name='关闭更新说明').click();page.wait_for_function('window.acknowledged===1')
                page.get_by_role('button',name='查看本次更新').click();page.get_by_role('button',name='知道了',exact=True).click()
                page.wait_for_function('window.acknowledged===2');self.assertFalse(dialog.is_visible())
            finally:browser.close()

    def test_user_activity_or_an_open_migration_sheet_prevents_a_delayed_popup(self):
        with tempfile.TemporaryDirectory() as temporary,sync_playwright() as runtime:
            resources=prepare(Path(temporary));browser=runtime.chromium.launch(channel='msedge' if sys.platform=='win32' else None,headless=True)
            try:
                for action in ("document.dispatchEvent(new Event('pointerdown'))","document.getElementById('sheet').hidden=false"):
                    page=browser.new_page();page.clock.install();page.add_init_script(bootstrap());page.goto((resources/'ui/index.html').as_uri())
                    page.wait_for_function('window.newsReads>0');page.evaluate(action);page.clock.fast_forward(1500)
                    self.assertFalse(page.locator('#release-highlights').is_visible());self.assertEqual(page.evaluate('window.acknowledged'),0);page.close()
            finally:browser.close()

    def test_small_layout_keeps_actions_visible_and_renders_strings_without_html(self):
        with tempfile.TemporaryDirectory() as temporary,sync_playwright() as runtime:
            resources=prepare(Path(temporary));browser=runtime.chromium.launch(channel='msedge' if sys.platform=='win32' else None,headless=True)
            try:
                for width,height in ((1200,820),(375,640)):
                    page=browser.new_page(viewport={'width':width,'height':height},reduced_motion='reduce');page.add_init_script(bootstrap())
                    page.goto((resources/'ui/index.html').as_uri());page.locator('#release-highlights').wait_for(state='visible')
                    page.evaluate("window.__notes.items=[{label:'修复',title:'较长内容也能完整阅读',text:'<script>window.danger=true</script> '+ '合成说明'.repeat(24)},...window.__notes.items]")
                    page.get_by_role('button',name='知道了',exact=True).click();page.get_by_role('button',name='查看本次更新').click()
                    box=page.locator('#release-highlights').bounding_box();button=page.locator('#release-done').bounding_box()
                    self.assertGreaterEqual(box['x'],0);self.assertLessEqual(box['x']+box['width'],width+1);self.assertLessEqual(box['height'],height-38)
                    self.assertLessEqual(button['y']+button['height'],height);self.assertEqual(page.locator('#release-items script').count(),0)
                    self.assertIsNone(page.evaluate('window.danger'))
                    output=ROOT/'artifacts/whats-new-2026-10-28';output.mkdir(parents=True,exist_ok=True)
                    page.screenshot(path=str(output/f'web-{width}.png'));page.close()
            finally:browser.close()

if __name__=='__main__':unittest.main()
