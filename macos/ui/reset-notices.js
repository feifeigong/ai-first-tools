(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const days = byId('reset-days'), details = byId('reset-details'), recent = byId('reset-recent');
  const toggle = byId('reset-enabled'), refresh = byId('reset-refresh'), error = byId('reset-error');
  let snapshot = null, busy = false, selected = '', month = '', selectedByUser = false;
  const date = key => new Date(key + 'T00:00:00Z');
  const key = value => value.toISOString().slice(0, 10);
  const todayFallback = () => key(new Date(Date.now() + 8 * 3600000));
  const events = () => snapshot?.events || [];
  const kind = event => event?.state==='undated' ? 'upcoming' : ['completed', 'banked', 'upcoming'].includes(event?.state) ? event.state : 'history';
  const label = event => ({completed:'完成公告',banked:'重置卡',upcoming:'预告',uncertain:'待核实',undated:'预告'})[event?.state] || '历史预告';
  const dateLabel = value => {
    const day = date(value);
    return `${day.getUTCMonth()+1} 月 ${day.getUTCDate()} 日` + (value === snapshot?.today ? ' · 今天' : ` · 周${'日一二三四五六'[day.getUTCDay()]}`);
  };
  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function choose(value, focus = false, scroll = false) {
    selected = value; month = value.slice(0,7); selectedByUser = true; renderCalendar();
    if (focus) days.querySelector(`[data-date="${selected}"]`)?.focus();
    if (scroll && window.matchMedia('(max-width: 930px)').matches) details.scrollIntoView({block:'nearest',behavior:'instant'});
  }
  function renderCalendar() {
    const today = snapshot?.today || todayFallback();
    if (!selected) selected = today;
    if (!month) month = selected.slice(0,7);
    const first = date(month + '-01');
    byId('reset-month').textContent = `${first.getUTCFullYear()} 年 ${first.getUTCMonth()+1} 月`;
    first.setUTCDate(first.getUTCDate() - ((first.getUTCDay()+6)%7));
    days.replaceChildren();
    for (let index=0; index<42; index++) {
      const day = new Date(first); day.setUTCDate(day.getUTCDate()+index);
      const value = key(day), records = events().filter(item => item.date === value);
      const record = records.find(item => item.state === 'completed') || records[0];
      const button = element('button','reset-day');
      button.dataset.date=value; button.dataset.outside=String(value.slice(0,7)!==month); button.dataset.today=String(value===today);
      button.setAttribute('aria-pressed',String(value===selected)); button.tabIndex=value===selected?0:-1;
      button.setAttribute('aria-label',`${day.getUTCMonth()+1}月${day.getUTCDate()}日${record?'，'+record.badge:''}${records.length>1?'，'+records.length+'条消息':''}`);
      button.append(element('span','reset-day-number',day.getUTCDate()));
      const badge = element('span','reset-day-label',record?label(record):value===today?'今天':'');
      badge.dataset.kind=kind(record); button.append(badge);
      button.addEventListener('click',()=>choose(value,false,true));
      button.addEventListener('keydown',event=>{
        const offset={ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7}[event.key];
        if (offset !== undefined) { event.preventDefault(); const next=date(value);next.setUTCDate(next.getUTCDate()+offset);choose(key(next),true); }
        else if (event.key==='Home'||event.key==='End') { event.preventDefault(); const next=date(value);next.setUTCDate(next.getUTCDate()+(event.key==='Home'?0:6)-((next.getUTCDay()+6)%7));choose(key(next),true); }
      });
      days.append(button);
    }
    details.replaceChildren(element('h3','',dateLabel(selected)));
    const onDay = events().filter(item=>item.date===selected);
    if (!onDay.length) details.append(element('p','resume-muted',events().length?'这一天没有查到重置消息。':'还没有查到重置消息，后续更新会保留在这里。'));
    for (const item of onDay) {
      const card=element('article','reset-event'), badge=element('span','reset-badge',item.badge);
      badge.dataset.kind=kind(item);card.append(badge,element('h4','',item.heading),element('p','resume-muted',item.detail));
      if(item.timeText) card.append(element('p','reset-time',item.timeText));
      if(item.note) card.append(element('p','resume-muted reset-note',item.note));
      card.append(element('p','resume-muted reset-note',`Tibo · X · 发布于（北京）${item.publishedLabel}`));
      const open=element('button','workspace-button reset-post','查看原帖 ↗');
      open.addEventListener('click',async()=>{
        open.disabled=true;
        try { const result=await window.pywebview.api.open_reset_post(item.id);if(result.error)throw Error(result.error); }
        catch(_) { error.textContent='暂时无法打开原帖，请稍后再试。';error.hidden=false; }
        finally { open.disabled=false; }
      });
      card.append(open);details.append(card);
    }
    recent.replaceChildren();
    const seen=new Set();
    for(const item of events()) {
      if(seen.has(item.date))continue;seen.add(item.date);
      if(seen.size>4)break;
      const entry=element('button','',`${dateLabel(item.date).split(' · ')[0]} · ${item.badge}`);
      entry.addEventListener('click',()=>choose(item.date,false,true));recent.append(entry);
    }
  }
  function render() {
    if(snapshot && !selectedByUser) {
      const preferred=events().filter(item=>item.state==='upcoming').sort((a,b)=>a.date.localeCompare(b.date))[0]
        ||events().find(item=>item.state==='undated'&&item.date===snapshot.today)
        ||events().find(item=>item.state==='completed')||events()[0];
      selected=preferred?.date||snapshot.today;month=selected.slice(0,7);
    }
    toggle.setAttribute('aria-checked',String(Boolean(snapshot?.enabled)));
    const status=byId('reset-status');status.replaceChildren();
    status.hidden=Boolean(snapshot?.enabled&&snapshot.fresh&&!snapshot.partial);
    status.append(element('strong','',snapshot?.enabled===false?'重置提醒已关闭':snapshot?.statusText||'正在读取重置消息'),
      element('p','resume-muted',snapshot?.enabled===false?'历史记录会保留；重新开启后继续关注新消息。':snapshot?.detailText||'最近的预告和完成公告会显示在日历里。'));
    const stamp=snapshot?.lastCheckedLabel;
    byId('reset-updated').textContent=snapshot?.checkedText || (stamp&&stamp!=='尚未更新'?`最近尝试（北京）${stamp}`:'尚未检查');
    renderCalendar();
  }
  async function load(operation='status') {
    if(busy)return;busy=true;toggle.disabled=refresh.disabled=true;
    try {
      const result=await window.pywebview.api.reset_news_control(operation);
      if(result.error)throw Error(result.error);
      if(typeof result.enabled!=='boolean'||!Array.isArray(result.events))throw Error('format');
      snapshot=result;error.hidden=true;render();
    } catch(_) {
      error.textContent='暂时没取到最新消息，请稍后刷新；已有记录仍保留。';error.hidden=false;
      if(snapshot)snapshot={...snapshot,fresh:false,statusText:'暂时没取到最新消息，正在自动重试',detailText:'下方是上次保存的消息，发布时间已标出。'};
      render();
    } finally { busy=false;refresh.disabled=false;toggle.disabled=!snapshot; }
  }
  function moveMonth(offset) {
    const value=date(month+'-01');value.setUTCMonth(value.getUTCMonth()+offset);
    const first=key(value),record=events().find(item=>item.date.slice(0,7)===first.slice(0,7));
    choose(record?.date||first);
  }
  byId('reset-prev').addEventListener('click',()=>moveMonth(-1));
  byId('reset-next').addEventListener('click',()=>moveMonth(1));
  byId('reset-today').addEventListener('click',()=>choose(snapshot?.today||todayFallback()));
  toggle.addEventListener('click',()=>load(snapshot?.enabled?'disable':'enable'));
  refresh.addEventListener('click',()=>load('refresh'));
  byId('workspace-resume').addEventListener('click',()=>{render();load();});
  setInterval(()=>{if(!byId('auto-resume-page').hidden&&window.pywebview?.api)load();},30000);
})();
