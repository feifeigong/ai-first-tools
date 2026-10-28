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
window.resumeState={installed:true,running:false,resumeEnabled:false,autoRedeem:false,autoStartWindow:false,autostart:false,watcherCount:0,error:''};
window.resumeCalls=[];window.failResume=false;
window.pywebview.api.auto_resume_control=async(op)=>{
 window.resumeCalls.push(op);if(window.failResume)return {error:'合成连接失败'};
 if(op==='resume-on'){window.resumeState.running=true;window.resumeState.resumeEnabled=true;}
 if(op==='resume-off'){window.resumeState.running=window.resumeState.autoStartWindow;window.resumeState.resumeEnabled=false;if(!window.resumeState.running)window.resumeState.autostart=false;}
 if(op==='credit-on')window.resumeState.autoRedeem=true;
 if(op==='credit-off')window.resumeState.autoRedeem=false;
 if(op==='timer-on'){window.resumeState.autoStartWindow=true;window.resumeState.running=true;}
 if(op==='timer-off'){window.resumeState.autoStartWindow=false;window.resumeState.running=window.resumeState.resumeEnabled;}
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
                page.locator('#resume-title').filter(has_text='已开启').wait_for()
                page.get_by_role('switch',name='周额度用完时自动使用重置卡').click()
                page.wait_for_function("document.getElementById('resume-credit').getAttribute('aria-checked')==='true'")
                page.get_by_role('switch',name='周额度用完时自动使用重置卡').click()
                self.assertEqual(run.get_attribute('aria-checked'),'true')
                page.get_by_role('switch',name='登录后自动运行开关').click()
                page.wait_for_function("document.getElementById('resume-startup').getAttribute('aria-checked')==='true'")
                run.click()
                page.locator('#resume-title').filter(has_text='已关闭').wait_for()
                self.assertEqual(page.locator('#resume-startup').get_attribute('aria-checked'),'false')
                page.evaluate('window.failResume=true')
                page.get_by_role('button',name='刷新状态',exact=True).click()
                page.get_by_text('状态暂时无法确认',exact=True).wait_for()
                self.assertTrue(run.is_disabled())
                page.evaluate('window.failResume=false')
                page.get_by_role('button',name='刷新状态',exact=True).click()
                page.locator('#resume-title').filter(has_text='已关闭').wait_for()
                self.assertTrue(run.is_enabled())
                page.get_by_role('switch',name='自动开启5小时计时').click()
                page.wait_for_function("document.getElementById('resume-timer').getAttribute('aria-checked')==='true'")
                self.assertEqual(run.get_attribute('aria-checked'),'false')
                self.assertTrue(page.get_by_role('switch',name='周额度用完时自动使用重置卡').is_disabled())
                page.locator('#workspace-mover').click()
                self.assertTrue(page.locator('.workspace-body > .app').is_visible())
                self.assertFalse(page.locator('#auto-resume-page').is_visible())
                self.assertEqual(page.evaluate('window.resumeCalls'),['status','resume-on','credit-on','credit-off','autostart-on','resume-off','status','status','timer-on'])
            finally:browser.close()

if __name__=='__main__':unittest.main()
