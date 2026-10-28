(() => {
  'use strict';
  const page=document.getElementById('auto-resume-page');
  const mover=document.querySelector('.workspace-body > .app');
  const nav=document.getElementById('workspace-resume');
  const home=document.getElementById('workspace-mover');
  const running=document.getElementById('resume-running');
  const startup=document.getElementById('resume-startup');
  const credit=document.getElementById('resume-credit');
  const timer=document.getElementById('resume-timer');
  const refresh=document.getElementById('resume-refresh');
  const error=document.getElementById('resume-error');
  let busy=false, state=null;
  const setSwitch=(button,value)=>button.setAttribute('aria-checked',String(value));
  const active=result=>result.running && result.resumeEnabled!==false;
  function timerText(result) {
    if(!result.autoStartWindow)return '已关闭，不会自动发送计时请求。';
    if(!result.running)return '暂未运行，请重新开启此功能。';
    const stamp=result.nextResetAt?new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(result.nextResetAt*1000)):'';
    return ({started:`本轮计时已开始 · 下次恢复（北京）${stamp}`,
      'normal-use':`已读取当前计时 · 下次恢复（北京）${stamp}`,
      waiting:stamp?`下次恢复（北京）${stamp} · 到时自动检查，无需重复请求。`:'已开启，正在检查本轮额度。',
      activity:'正在正常工作，本轮不额外发送计时请求。',
      'quota-blocked':'正在等待额度恢复，不会为计时使用重置卡。',
      unavailable:'当前账号、模型或额度信息暂不适用，未确认计时。',
      pending:'正在确认本轮计时，请稍候。',
      unconfirmed:'本轮计时未确认，已暂停重复请求，避免多次消耗。',
      error:'计时记录暂时无法读取，已暂停请求，原记录保留。'})[result.timerStatus] || '已开启，正在检查本轮额度。';
  }
  function display(result) {
    state=result;setSwitch(running,active(result));setSwitch(startup,result.autostart);
    setSwitch(credit,!!result.autoRedeem);setSwitch(timer,!!result.autoStartWindow);
    document.getElementById('resume-title').textContent=active(result)?'已开启':'已关闭';
    document.getElementById('resume-title').dataset.state=active(result)?'on':'off';
    document.getElementById('resume-description').textContent=active(result)?'是否用卡，由下面的开关决定。':'续跑已关闭，不会继续任务或自动使用重置卡。';
    document.getElementById('timer-description').textContent=timerText(result);
  }
  async function control(operation='status') {
    if (busy) return;
    busy=true;running.disabled=credit.disabled=timer.disabled=startup.disabled=refresh.disabled=true;
    try {
      const result=await window.pywebview.api.auto_resume_control(operation);
      if(result.error) throw new Error(result.error);
      display(result);
      error.hidden=true;
    } catch(e) {
      state=null;for(const button of [running,startup,credit,timer])button.removeAttribute('aria-checked');
      document.getElementById('resume-title').textContent='状态暂时无法确认';
      document.getElementById('resume-title').dataset.state='unknown';
      document.getElementById('resume-description').textContent='请刷新确认，恢复连接后再操作。';
      document.getElementById('timer-description').textContent='状态暂时无法确认，请刷新后再试。';
      error.textContent=e.message;error.hidden=false;
      if(operation!=='status') {
        try { const actual=await window.pywebview.api.auto_resume_control('status');if(!actual.error&&actual.installed)display(actual); }
        catch(_) { /* Keep the refresh action available when status is still unknown. */ }
      }
    } finally {
      busy=false;refresh.disabled=false;running.disabled=timer.disabled=startup.disabled=!state?.installed;
      credit.disabled=!state?.installed || !active(state);
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
  running.addEventListener('click',()=>control(active(state)?'resume-off':'resume-on'));
  credit.addEventListener('click',()=>control(state?.autoRedeem?'credit-off':'credit-on'));
  timer.addEventListener('click',()=>control(state?.autoStartWindow?'timer-off':'timer-on'));
  startup.addEventListener('click',()=>control(state?.autostart?'autostart-off':'autostart-on'));
  setInterval(()=>{if(!page.hidden && window.pywebview?.api)control();},30000);
})();
