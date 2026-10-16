import sys
import tempfile
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_macos import prepare
from test_macos_ui import BOOT

class MacResumeUiTests(unittest.TestCase):
    def test_switches_use_bridge_restore_mover_and_recover_errors(self):
        with tempfile.TemporaryDirectory() as temporary, sync_playwright() as runtime:
            resources=prepare(Path(temporary))
            browser=runtime.chromium.launch(channel='msedge' if sys.platform=='win32' else None,headless=True)
            try:
                page=browser.new_page()
                page.add_init_script(BOOT+'''
window.resumeState={installed:true,running:false,autostart:false,watcherCount:0,error:''};
window.resumeCalls=[];window.failResume=false;
window.pywebview.api.auto_resume_control=async(op)=>{
 window.resumeCalls.push(op);if(window.failResume)return {error:'合成连接失败'};
 if(op==='start')window.resumeState.running=true;
 if(op==='stop'){window.resumeState.running=false;window.resumeState.autostart=false;}
 if(op==='autostart-on')window.resumeState.autostart=true;
 if(op==='autostart-off')window.resumeState.autostart=false;
 return {...window.resumeState};
};''')
                page.goto((resources/'ui/index.html').as_uri())
                page.locator('#workspace-resume').click()
                run=page.get_by_role('switch',name='自动续跑开关',exact=True)
                run.wait_for()
                page.wait_for_function("!document.getElementById('resume-running').disabled")
                run.click()
                page.get_by_text('自动续跑已开启',exact=True).wait_for()
                page.get_by_role('switch',name='登录后自动开启开关').click()
                page.wait_for_function("document.getElementById('resume-startup').getAttribute('aria-checked')==='true'")
                run.click()
                page.get_by_text('自动续跑已关闭',exact=True).wait_for()
                self.assertEqual(page.locator('#resume-startup').get_attribute('aria-checked'),'false')
                page.evaluate('window.failResume=true')
                page.get_by_role('button',name='刷新状态',exact=True).click()
                page.get_by_text('状态暂时无法确认',exact=True).wait_for()
                self.assertTrue(run.is_disabled())
                page.evaluate('window.failResume=false')
                page.get_by_role('button',name='刷新状态',exact=True).click()
                page.get_by_text('自动续跑已关闭',exact=True).wait_for()
                self.assertTrue(run.is_enabled())
                page.locator('#workspace-mover').click()
                self.assertTrue(page.locator('.workspace-body > .app').is_visible())
                self.assertFalse(page.locator('#auto-resume-page').is_visible())
                self.assertEqual(page.evaluate('window.resumeCalls'),['status','start','autostart-on','stop','status','status'])
            finally:browser.close()

if __name__=='__main__':unittest.main()
