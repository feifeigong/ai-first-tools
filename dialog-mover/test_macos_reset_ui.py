from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_macos import prepare
from test_macos_ui import BOOT


def news():
    return {'enabled':True,'fresh':True,'partial':False,'today':'2026-10-23','lastCheckedLabel':'10-23 09:05',
        'checkedText':'消息更新于（北京）10-23 08:00',
        'statusText':'最近的重置消息','detailText':'', 'events':[
            {'id':'2113162413008884099','date':'2026-10-23','state':'past-preview','badge':'预计已生效','heading':'已到原定重置时间',
             'detail':'仅按原预告时间推算；程序还未取得对应的确认帖，实际额度以 Codex 显示为准。','timeText':'原计划 · 10 月 23 日 02:00 前',
             'note':'按原帖 PST 换算；若泛指当地美西时间，则为 01:00 前。','publishedLabel':'10-22 14:55'},
            {'id':'2112432076767289678','date':'2026-10-20','state':'completed','badge':'重置确认','heading':'Tibo 已确认重置完成',
             'detail':'按 Tibo 的确认帖记录。这是发帖时间，具体到账以你的 Codex 用量为准。','timeText':'确认帖发布于 10-20 14:33','note':'','publishedLabel':'10-20 14:33'},
            {'id':'2107913674593644711','date':'2026-10-08','state':'banked','badge':'发放重置卡','heading':'Tibo 发布了重置卡消息',
             'detail':'发放可以留着以后使用的重置卡。','timeText':'公告发布于 10-08 03:19','note':'','publishedLabel':'10-08 03:19'}]}


class MacResetUiTests(unittest.TestCase):
    def test_calendar_chinese_states_switches_selection_keyboard_and_narrow_layout(self):
        with tempfile.TemporaryDirectory() as temporary, sync_playwright() as runtime:
            resources=prepare(Path(temporary))
            browser=runtime.chromium.launch(channel='msedge' if sys.platform=='win32' else None,headless=True)
            try:
                page=browser.new_page(viewport={'width':1440,'height':1000},timezone_id='America/Los_Angeles')
                errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.add_init_script(BOOT+f'window.resetFixture={json.dumps(news())};'+'''
window.resumeCalls=[];window.resetCalls=[];window.failReset=false;
window.resumeState={installed:true,running:false,autostart:false};
window.pywebview.api.auto_resume_control=async(op)=>{
 resumeCalls.push(op);if(op==='resume-on')resumeState.running=true;
 if(op==='resume-off'){resumeState.running=false;resumeState.autostart=false;}
 if(op==='autostart-on')resumeState.autostart=true;
 return {...resumeState};
};
window.pywebview.api.reset_news_control=async(op)=>{
 resetCalls.push(op);if(failReset)return {error:'合成断网'};
 if(op==='enable')resetFixture.enabled=true;if(op==='disable')resetFixture.enabled=false;
 return JSON.parse(JSON.stringify(resetFixture));
};
window.pywebview.api.open_reset_post=async(id)=>{window.lastPost=id;return {ok:true};};
''')
                page.goto((resources/'ui/index.html').as_uri())
                page.locator('#workspace-resume').click()
                page.wait_for_function("!document.getElementById('reset-enabled').disabled")
                self.assertEqual(page.locator('.reset-day').count(),42)
                self.assertEqual(page.locator('#reset-updated').inner_text(),'消息更新于（北京）10-23 08:00')
                self.assertEqual(page.locator('#reset-month').inner_text(),'2026 年 10 月')
                self.assertEqual(page.locator('.reset-day[aria-pressed=true]').get_attribute('data-date'),'2026-10-20')
                page.locator('[data-date="2026-10-23"]').click()
                self.assertIn('已到原定重置时间',page.locator('#reset-details').inner_text())
                self.assertNotIn('尚未确认完成',page.locator('#reset-details').inner_text())
                self.assertIn('02:00',page.locator('#reset-details').inner_text())
                page.get_by_role('button',name='查看原帖 ↗',exact=True).click()
                self.assertEqual(page.evaluate('window.lastPost'),'2113162413008884099')
                page.locator('#reset-refresh').click()
                page.wait_for_function("window.resetCalls.includes('refresh')")
                self.assertEqual(page.locator('.reset-day[aria-pressed=true]').get_attribute('data-date'),'2026-10-23')
                page.locator('[data-date="2026-10-23"]').focus()
                page.keyboard.press('ArrowLeft')
                self.assertEqual(page.locator('.reset-day[aria-pressed=true]').get_attribute('data-date'),'2026-10-22')
                page.locator('#reset-today').click()
                self.assertEqual(page.locator('.reset-day[aria-pressed=true]').get_attribute('data-date'),'2026-10-23')
                page.locator('#reset-prev').click()
                self.assertEqual(page.locator('#reset-month').inner_text(),'2026 年 9 月')
                page.locator('#reset-next').click()
                self.assertEqual(page.locator('.reset-day[aria-pressed=true]').get_attribute('data-date'),'2026-10-23')
                page.locator('#resume-running').click()
                page.wait_for_function("document.getElementById('resume-running').getAttribute('aria-checked')==='true'")
                page.locator('#resume-running').click()
                page.wait_for_function("document.getElementById('resume-running').getAttribute('aria-checked')==='false'")
                self.assertEqual(page.locator('#reset-enabled').get_attribute('aria-checked'),'true')
                before=page.evaluate('window.resumeCalls.slice()')
                page.locator('#reset-enabled').click()
                page.get_by_text('重置提醒已关闭',exact=True).wait_for()
                self.assertEqual(page.evaluate('window.resumeCalls'),before)
                page.locator('#reset-enabled').click()
                page.wait_for_function("document.getElementById('reset-enabled').getAttribute('aria-checked')==='true'")
                output=Path(__file__).resolve().parents[1]/'artifacts/development/macos-parity-ui'
                output.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(output/'calendar-wide.png'))
                page.set_viewport_size({'width':900,'height':760})
                page.locator('[data-date="2026-10-08"]').click()
                self.assertIn('发放重置卡',page.locator('#reset-details').inner_text())
                self.assertFalse(page.locator('#auto-resume-page').evaluate('el=>el.scrollWidth>el.clientWidth+1'))
                page.screenshot(path=str(output/'calendar-narrow.png'))
                page.evaluate('window.failReset=true')
                page.locator('#reset-refresh').click()
                page.get_by_text('暂时没取到最新消息，请稍后刷新；已有记录仍保留。',exact=True).wait_for()
                self.assertIn('发放重置卡',page.locator('#reset-details').inner_text())
                page.evaluate('window.failReset=false')
                self.assertEqual(page.locator('#reset-updated').inner_text(),'消息更新于（北京）10-23 08:00')
                page.locator('#reset-refresh').click()
                page.wait_for_function("document.getElementById('reset-error').hidden")
                self.assertEqual(errors,[])
            finally:browser.close()


if __name__=='__main__':unittest.main()
