(() => {
  'use strict';
  const page=document.getElementById('auto-resume-page');
  const mover=document.querySelector('.workspace-body > .app');
  const nav=document.getElementById('workspace-resume');
  const home=document.getElementById('workspace-mover');
  const running=document.getElementById('resume-running');
  const startup=document.getElementById('resume-startup');
  const refresh=document.getElementById('resume-refresh');
  const error=document.getElementById('resume-error');
  let busy=false, state=null;
  const setSwitch=(button,value)=>button.setAttribute('aria-checked',String(value));
  function display(result) {
    state=result;setSwitch(running,result.running);setSwitch(startup,result.autostart);
    document.getElementById('resume-title').textContent=result.running?'自动续跑已开启':'自动续跑已关闭';
    document.getElementById('resume-title').dataset.state=result.running?'on':'off';
    document.getElementById('resume-description').textContent=result.running?'额度恢复后，会接着原来的对话继续。':result.autostart?'当前已关闭；下次登录电脑会自动开启。':'已关闭，不会自动续跑或使用重置卡。';
  }
  async function control(operation='status') {
    if (busy) return;
    busy=true;running.disabled=startup.disabled=refresh.disabled=true;
    try {
      const result=await window.pywebview.api.auto_resume_control(operation);
      if(result.error) throw new Error(result.error);
      display(result);
      error.hidden=true;
    } catch(e) {
      state=null;setSwitch(running,false);setSwitch(startup,false);
      document.getElementById('resume-title').textContent='状态暂时无法确认';
      document.getElementById('resume-title').dataset.state='unknown';
      document.getElementById('resume-description').textContent='请刷新确认，恢复连接后再操作。';
      error.textContent=e.message;error.hidden=false;
      if(operation!=='status') {
        try { const actual=await window.pywebview.api.auto_resume_control('status');if(!actual.error&&actual.installed)display(actual); }
        catch(_) { /* Keep the refresh action available when status is still unknown. */ }
      }
    } finally {
      busy=false;refresh.disabled=false;running.disabled=startup.disabled=!state?.installed;
    }
  }
  nav.addEventListener('click',()=>{
    mover.hidden=true;page.hidden=false;document.body.classList.add('show-resume');
    home.removeAttribute('aria-current');nav.setAttribute('aria-current','page');control();
  });
  home.addEventListener('click',()=>{
    page.hidden=true;mover.hidden=false;document.body.classList.remove('show-resume');
    nav.removeAttribute('aria-current');home.setAttribute('aria-current','page');
  });
  refresh.addEventListener('click',()=>control());
  running.addEventListener('click',()=>control(state?.running?'stop':'start'));
  startup.addEventListener('click',()=>control(state?.autostart?'autostart-off':'autostart-on'));
  setInterval(()=>{if(!page.hidden && window.pywebview?.api)control();},30000);
})();
