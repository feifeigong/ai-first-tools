(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);

  const LOGOS = {
    cursor_desktop: "cursor", cursor_cli: "cursor", workbuddy: "workbuddy", workbuddy_ai: "workbuddy-ai",
    qwen_work: "qwen", doubao_work: "doubao", antigravity: "antigravity", antigravity_cli: "antigravity",
    codex: "chatgpt", chatgpt: "chatgpt", chatgpt_work: "chatgpt", claude_code: "claude", claude: "claude",
    claude_desktop: "claude", cowork: "claude", grok: "grok", grokbot: "grok-bot", hermes: "hermes", opencode: "opencode",
    codebuddy: "codebuddy", kimi: "kimi", deepseek: "deepseek", perplexity: "perplexity",
  };
  const SOFTWARE_ICON = '<svg viewBox="0 0 24 24" width="21" height="21" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="15" rx="3"/><path d="M3 9h18M7 6.5h.01M10 6.5h.01"/></svg>';

  function agentLogo(id, name) {
    const asset = LOGOS[id];
    return `<span class="agent-logo ${asset === "chatgpt" ? "agent-logo-chatgpt" : ""}" data-agent-logo="${esc(id)}" title="${esc(name)}">${asset ? `<img src="assets/agents/${asset}.png" alt="${esc(name)} 图标" draggable="false">` : SOFTWARE_ICON}</span>`;
  }

  document.addEventListener("error", (event) => {
    const image = event.target;
    if (!(image instanceof HTMLImageElement) || !image.parentElement?.matches(".agent-logo")) return;
    const container = image.parentElement;
    container.classList.remove("agent-logo-chatgpt");
    container.classList.add("agent-logo-missing");
    container.innerHTML = SOFTWARE_ICON;
    container.title += "：暂未找到原版图标";
  }, true);
  const KIND = { task: "任务", space: "空间", project: "项目", recent: "最近", folder: "文件夹", none: "没有目录" };
  const ICON = {
    folder: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/></svg>',
    task: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/></svg>',
    recent: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    chevron: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>',
    foldIn: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 4l5 5 5-5"/><path d="M7 20l5-5 5 5"/></svg>',
    foldOut: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 9l5-5 5 5"/><path d="M7 15l5 5 5-5"/></svg>',
    tick: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    dash: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round"><path d="M6 12h12"/></svg>',
  };
  const GROUP_ICON = { task: ICON.task, recent: ICON.recent };

  const state = {
    unsupported: [],
    agents: [],
    targets: [],
    current: null,
    cache: {},
    selected: new Set(),
    query: "",
    kind: "all",
    sheet: null,
    folded: {},
    searchFolded: new Set(),
  };

  /* ------------------------------------------------------------ api */
  const real = () => window.pywebview && window.pywebview.api;
  const preview = new URL(window.location.href).searchParams.get("demo") === "1";
  const mock = {
    async agents() {
      return {
        ready: true,
        agents: [
          { id: "cursor_desktop", name: "Cursor", sub: "代码编辑器里的对话", color: "#1f2933", canTarget: true },
          { id: "workbuddy", name: "WorkBuddy", sub: "国内版", color: "#e8590c", canTarget: true },
          { id: "workbuddy_ai", name: "WorkBuddy AI", sub: "海外版", color: "#0c8599", canTarget: true },
          { id: "qwen_work", name: "千问办公", sub: "通义千问", color: "#6741d9", canTarget: true },
          { id: "doubao_work", name: "豆包工作", sub: "字节跳动", color: "#1971c2", canTarget: false },
          { id: "antigravity", name: "Antigravity", sub: "Google", color: "#2f9e44", canTarget: true },
          { id: "chatgpt", name: "ChatGPT", sub: "聊天、工作、Codex", color: "#0b8f6f", canTarget: false },
        ],
      };
    },
    async sessions(id) {
      const s = (n, t, w, f, m = true, note = "") => ({ id: `${id}-${n}`, title: t, when: w, ts: n, folder: f, movable: m, note, kind: id === "chatgpt" ? (n % 2 ? "chat" : "work") : "" });
      const groups = [
        { title: "AI-First-Hand", kind: "folder", path: "C:\\Users\\me\\Documents\\cowork\\AI-First-Hand", sessions: [
          s(9, "Wechat styled HTML file", "23 小时前", "x"), s(8, "同步 GitHub 写作工作流", "20 天前", "x"),
          s(7, "WeChat article covers", "26 天前", "x"), s(6, "Codex multi-agent research report", "2026-09-08", "x"),
          s(20, "Article title and cover design", "27 天前", "x"), s(21, "Model identification inquiry", "28 天前", "x"),
          s(22, "DeepSeek Harness tutorial", "30 天前", "x"), s(23, "Codex context tutorial", "31 天前", "x"), s(24, "Opus writing with AI", "33 天前", "x") ] },
        { title: "vibcoding", kind: "folder", path: "D:\\vibcoding", sessions: [
          s(5, "ChatGPT conversation extraction", "10 分钟前", "y"), s(4, "Agent对话共享工具", "6 天前", "y") ] },
        { title: "没有目录", kind: "none", path: "", sessions: [
          s(3, "Codex WeChat article search", "28 天前", "", true), s(2, "云端对话示例", "30 天前", "", false, "这条对话只保存在云端，不能搬运") ] },
      ];
      return { groups, total: 8, movable: 7 };
    },
    async folders() {
      return [
        { path: "C:\\Users\\me\\Documents\\cowork\\AI-First-Hand", name: "AI-First-Hand" },
        { path: "D:\\vibcoding", name: "vibcoding" },
        { path: "D:\\javaProject\\zkkx-cloud", name: "zkkx-cloud" },
      ];
    },
    async pick_folder() { return "D:\\新建的文件夹"; },
    async open_import_folder() { return { error: "这是界面预览，没有实际导入文件。" }; },
    async open_in_app() { return { error: "这是界面预览，没有实际导入文件。" }; },
    _n: 0,
    async start_move(source, ids) { mock._n = 0; mock._total = ids.length; mock._ids = ids; return { ok: true, total: ids.length }; },
    async move_status() {
      mock._n = Math.min(mock._total, mock._n + 1);
      const items = mock._ids.map((id, i) => ({ id, title: "示例对话 " + (i + 1), state: i < mock._n ? "ok" : "running", message: "已搬好" }));
      return { finished: mock._n >= mock._total, total: mock._total, done: mock._n, ok: mock._n, skipped: 0, failed: 0, items };
    },
  };
  const call = async (name, ...args) => {
    const api = real();
    if (api && api[name]) return api[name](...args);
    return mock[name](...args);
  };

  /* ---------------------------------------------------------- toast */
  function toast(text) {
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = text;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 2600);
  }

  /* ----------------------------------------------------------- rail */
  const label = (agent) => {
    const twins = state.agents.filter((item) => item.name === agent.name).length > 1;
    return twins ? `${agent.name} ${agent.sub}` : agent.name;
  };

  function renderRail() {
    const main = state.agents
      .map((agent) => {
        const data = state.cache[agent.id];
        const count = data && !data.error ? data.total : "";
        return `<button class="agent ${state.current === agent.id ? "active" : ""}" data-agent="${agent.id}">
          ${agentLogo(agent.id, agent.name)}
          <span class="agent-text"><div class="agent-name">${esc(agent.name)}</div><div class="agent-sub">${esc(agent.sub) || "&nbsp;"}</div></span>
          <span class="agent-count">${count}</span>
        </button>`;
      })
      .join("");
    const extra = state.unsupported.length
      ? `<div class="rail-label rail-label-2">还发现这些</div>` +
        state.unsupported
          .map(
            (item) => `<button class="agent dim ${state.current === "x:" + item.id ? "active" : ""}" data-extra="${esc(item.id)}">
              ${agentLogo(item.id, item.name)}
              <span class="agent-text"><div class="agent-name">${esc(item.name)}</div><div class="agent-sub">${esc(item.reason === "empty" ? "暂无对话" : "暂时读不了")}</div></span>
            </button>`
          )
          .join("")
      : "";
    $("#agents").innerHTML = main + extra;
  }

  function showExtra(id) {
    const item = state.unsupported.find((entry) => entry.id === id);
    if (!item) return;
    state.current = "x:" + id;
    state.selected = new Set();
    updateBar();
    renderRail();
    $("#title").textContent = item.name;
    $("#subtitle").textContent = "";
    $("#fold-all").hidden = true;
    $("#list").innerHTML = item.reason === "empty"
      ? `<div class="empty"><b>${esc(item.name)} 已安装，但里面还没有对话</b>有了对话之后再来看看。</div>`
      : `<div class="empty"><b>已经发现 ${esc(item.name)}</b>它的对话保存格式还没有公开，目前读不了，所以先不能搬。<br>已经安装、但这里不能搬的软件会一直列在左边，不会被漏掉。</div>`;
  }

  /* ----------------------------------------------------------- list */
  async function open(agentId, refresh = false) {
    state.current = agentId;
    state.selected = new Set();
    state.query = "";
    state.kind = "all";
    $("#search").value = "";
    updateBar();
    renderRail();
    const agent = state.agents.find((item) => item.id === agentId);
    $("#title").textContent = label(agent);
    $("#subtitle").textContent = agentId === "chatgpt" ? "正在从网页版读取，需要联网，可能要半分钟…" : "正在读取…";
    $("#fold-all").hidden = true;
    $("#list").innerHTML = '<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>';
    if (refresh || !state.cache[agentId] || agentId === "chatgpt") state.cache[agentId] = await call("sessions", agentId, refresh);
    if (state.current !== agentId) return;
    renderRail();
    renderList();
    watchWeb(agentId, 0);
  }

  // ChatGPT shows its last saved cloud list at once and updates it in the background;
  // swap in the fresh list as soon as it is ready.
  async function watchWeb(agentId, tries) {
    const data = state.cache[agentId];
    if (!data || data.error || !data.web || !data.web.refreshing || tries >= 60) return;
    await new Promise((resolve) => setTimeout(resolve, 3000));
    if (state.current !== agentId) return;
    const next = await call("sessions", agentId, false);
    if (state.current !== agentId || !next || next.error) return;
    state.cache[agentId] = next;
    renderRail();
    renderList();
    watchWeb(agentId, tries + 1);
  }

  function visibleGroups() {
    const data = state.cache[state.current];
    if (!data || data.error) return [];
    const query = state.query.trim().toLowerCase();
    return data.groups
      .map((group) => ({
        ...group,
        sessions: group.sessions.filter(
          (item) =>
            (state.kind === "all" || !item.kind || item.kind === state.kind) &&
            (!query || item.title.toLowerCase().includes(query) || (group.title + group.path).toLowerCase().includes(query))
        ),
      }))
      .filter((group) => group.sessions.length || (group.keepEmpty && state.kind === "all" && (!query || (group.title + group.path).toLowerCase().includes(query))));
  }

  const groupKey = (group) => group.key || `${group.kind}|${group.path || group.title}`;

  // While searching every match is shown; folding then only lasts for that search.
  function foldSet() {
    if (state.query.trim()) return state.searchFolded;
    if (!state.folded[state.current]) {
      // a first look: folders holding many conversations start folded
      const data = state.cache[state.current];
      const initial = new Set();
      if (data && !data.error && data.groups.length > 1) {
        data.groups.forEach((group) => { if (group.sessions.length > 8) initial.add(groupKey(group)); });
      }
      state.folded[state.current] = initial;
    }
    return state.folded[state.current];
  }

  function renderFoldAll(groups) {
    const button = $("#fold-all");
    button.hidden = groups.length < 2;
    if (button.hidden) return;
    const fold = foldSet();
    const allFolded = groups.every((group) => fold.has(groupKey(group)));
    button.innerHTML = allFolded ? `${ICON.foldOut}<span>全部展开</span>` : `${ICON.foldIn}<span>全部收起</span>`;
  }

  function renderChips() {
    const data = state.cache[state.current];
    const box = $("#chips");
    const mixed = data && !data.error && data.groups.some((g) => g.sessions.some((s) => s.kind));
    box.hidden = !mixed;
    if (!mixed) return;
    const all = data.groups.flatMap((g) => g.sessions);
    const count = (k) => all.filter((s) => k === "all" || s.kind === k).length;
    box.innerHTML = [["all", "全部"], ["chat", "聊天"], ["work", "工作"], ["codex", "Codex"]]
      .map(([k, name]) => `<button class="chip ${state.kind === k ? "on" : ""}" data-kind="${k}">${name}<i>${count(k)}</i></button>`)
      .join("");
  }

  function renderList() {
    renderChips();
    const data = state.cache[state.current];
    const agent = state.agents.find((item) => item.id === state.current);
    if (!data) return;
    if (data.error) {
      $("#subtitle").textContent = "";
      $("#fold-all").hidden = true;
      $("#list").innerHTML = `<div class="empty"><b>读取没有成功</b>${esc(data.error)}</div>`;
      return;
    }
    const web = data.web;
    const webNote = web && web.refreshing ? "　云端聊天正在更新…"
      : web && web.age > 600 ? `　云端聊天是 ${Math.round(web.age / 60)} 分钟前的，点右上角刷新获取最新` : "";
    $("#subtitle").textContent = `${data.total} 条对话，其中 ${data.movable} 条可以搬运。归档和删除过的不显示。${webNote}`;
    const groups = visibleGroups();
    renderFoldAll(groups);
    if (!groups.length) {
      $("#list").innerHTML = `<div class="empty"><b>${state.query ? "没有找到匹配的对话" : "这里还没有对话"}</b>${state.query ? "换个关键词试试。" : agent.full + " 里没有可以显示的对话。"}</div>`;
      return;
    }
    const fold = foldSet();
    const sectionLabel = { pinned: "置顶", threads: "项目", projects: "项目" };
    let lastSection = "";
    $("#list").innerHTML = groups
      .map((group, gi) => {
        const movable = group.sessions.filter((item) => item.movable);
        const picked = movable.filter((item) => state.selected.has(item.id)).length;
        const mark = picked === 0 ? "" : picked === movable.length ? ICON.tick : ICON.dash;
        const klass = picked === 0 ? "" : picked === movable.length ? "on" : "part";
        const kind = group.kind === "none" ? (group.title === KIND.none ? "" : KIND.none) : KIND[group.kind] || "";
        const key = groupKey(group);
        const expanded = !fold.has(key);
        const sectionTitle = sectionLabel[group.section] || (group.section !== "chats" ? group.sectionTitle : "");
        const banner = group.section && group.section !== lastSection && sectionTitle
          ? `<div class="section-label">${esc(sectionTitle)}</div>` : "";
        if (group.section) lastSection = group.section;
        if (group.headless) {
          return `${banner}<div class="card">${group.sessions.map((item) => `<div class="row ${item.movable ? "" : "disabled"} ${state.selected.has(item.id) ? "selected" : ""}" data-id="${esc(item.id)}">
                  <span class="check">${ICON.tick}</span>
                  ${item.kind ? `<span class="kind ${item.kind}">${{chat: "聊天", work: "工作", codex: "Codex"}[item.kind] || ""}</span>` : ""}
                  <div class="row-main"><div class="row-title" title="${esc(item.title)}">${esc(item.title)}</div>${item.note ? `<div class="row-note">${esc(item.note)}</div>` : (item.folder ? `<div class="row-note">${esc(item.folder)}</div>` : "")}</div>
                  <span class="row-when">${esc(item.when)}</span>
                </div>`).join("")}</div>`;
        }
        return `${banner}<div class="group ${group.kind === "none" ? "group-none" : ""} ${expanded ? "" : "folded"}">
          <div class="group-head">
            ${movable.length ? `<button class="group-check" data-group="${gi}" aria-label="选择这一组"><span class="check ${klass}">${mark}</span></button>` : '<span class="group-check-gap"></span>'}
            <button class="group-fold" data-fold="${esc(key)}" aria-expanded="${expanded}" title="${expanded ? "收起" : "展开"}">
              <span class="chevron">${ICON.chevron}</span>
              <span class="group-icon">${GROUP_ICON[group.kind] || ICON.folder}</span>
              <span class="group-title" title="${esc(group.title)}">${esc(group.title)}</span>
              <span class="group-path" title="${esc(group.path || kind)}">${esc(group.path || kind)}</span>
              <span class="group-count">${group.sessions.length}</span>
            </button>
          </div>
          ${expanded ? `<div class="card">
            ${group.sessions
              .map(
                (item) => `<div class="row ${item.movable ? "" : "disabled"} ${state.selected.has(item.id) ? "selected" : ""}" data-id="${esc(item.id)}">
                  <span class="check">${ICON.tick}</span>
                  ${item.kind ? `<span class="kind ${item.kind}">${{chat: "聊天", work: "工作", codex: "Codex"}[item.kind] || ""}</span>` : ""}
                  <div class="row-main"><div class="row-title" title="${esc(item.title)}">${esc(item.title)}</div>${item.note ? `<div class="row-note">${esc(item.note)}</div>` : (item.folder && (group.kind === "recent" || group.kind === "task") ? `<div class="row-note">${esc(item.folder)}</div>` : "")}</div>
                  <span class="row-when">${esc(item.when)}</span>
                </div>`
              )
              .join("")}
          </div>` : ""}
        </div>`;
      })
      .join("");
  }

  function toggle(id) {
    if (state.selected.has(id)) state.selected.delete(id);
    else state.selected.add(id);
  }

  function updateBar() {
    const count = state.selected.size;
    $("#bar").hidden = count === 0;
    $("#bar-count").textContent = count;
    const agent = state.agents.find((item) => item.id === state.current);
    $("#bar-text").textContent = `条已选${agent ? "，来自 " + agent.full : ""}`;
  }

  /* ---------------------------------------------------------- sheet */
  const STEP_NAMES = ["软件", "文件夹", "确认"];

  function openSheet() {
    state.sheet = { step: 0, product: null, target: null, directory: "", folders: null, folderQuery: "", job: null, busy: false };
    $("#sheet").hidden = false;
    renderSheet();
  }

  function closeSheet() {
    if (state.sheet && state.sheet.busy) return;
    $("#sheet").hidden = true;
    state.sheet = null;
  }

  function selectedSessions() {
    const data = state.cache[state.current];
    const map = new Map();
    data.groups.forEach((group) => group.sessions.forEach((item) => map.set(item.id, item)));
    return [...state.selected].map((id) => map.get(id)).filter(Boolean);
  }

  function sharedFolder() {
    const folders = new Set(selectedSessions().map((item) => item.folder).filter(Boolean));
    const empty = selectedSessions().some((item) => !item.folder);
    return folders.size === 1 && !empty ? [...folders][0] : "";
  }

  function stepsHtml(step) {
    return STEP_NAMES.map((name, i) => `<li class="${i === step ? "on" : i < step ? "done" : ""}"><i>${i + 1}</i>${name}</li>`).join("");
  }

  function renderSheet() {
    const sheet = state.sheet;
    if (!sheet) return;
    const finished = sheet.step >= 3;
    $("#steps").innerHTML = finished ? "" : stepsHtml(sheet.step);
    $("#sheet-back").disabled = (sheet.step === 0 && !sheet.product) || finished || sheet.busy;
    const body = $("#sheet-body");
    if (sheet.step === 0) renderTargets(body);
    else if (sheet.step === 1) renderFolders(body);
    else if (sheet.step === 2) renderConfirm(body);
    else renderRun(body);
  }

  function renderTargets(body) {
    const product = state.sheet.product;
    if (product) {
      const name = product === "chatgpt" ? "ChatGPT" : "Claude";
      const options = state.targets.filter((agent) => agent.product === product).sort((left, right) => Number(right.canTarget) - Number(left.canTarget));
      body.innerHTML = `<h2>搬进 ${name} 的哪里？</h2><p class="lead">本机任务可以搬入，普通云端聊天只支持搬出。请选择具体模式。</p>
        <div class="choices choices-modes">${options.map(targetHtml).join("")}</div>`;
      bindTargets(body);
      return;
    }
    const shown = new Set();
    const cards = state.targets.map((agent) => {
      if (!agent.product) return targetHtml(agent);
      if (shown.has(agent.product)) return "";
      shown.add(agent.product);
      const options = state.targets.filter((item) => item.product === agent.product);
      const enabled = options.some((item) => item.canTarget);
      const name = agent.product === "chatgpt" ? "ChatGPT" : "Claude";
      const description = agent.product === "chatgpt" ? "选择本机 Work 或 Codex" : "选择本机 Cowork 或 Claude Code";
      return `<button class="choice product-choice" data-product="${agent.product}">
        ${agentLogo(agent.product, name)}
        <span class="choice-copy"><b>${name}</b><small>${enabled ? description : "查看可用模式与限制"}</small></span>${ICON.chevron}
      </button>`;
    }).join("");
    body.innerHTML = `<h2>搬到哪个软件？</h2><p class="lead">已选 ${state.selected.size} 条对话。点一下目的地。</p>
      <div class="choices">${cards}</div>`;
    body.querySelectorAll("[data-product]").forEach((button) => {
      button.onclick = () => { state.sheet.product = button.dataset.product; renderSheet(); };
    });
    bindTargets(body);
  }

  function targetHtml(agent) {
    const ok = agent.canTarget;
    return `<button class="choice ${state.sheet.target === agent.id ? "on" : ""}" data-target="${agent.id}" ${ok ? "" : "disabled"}>
      ${agentLogo(agent.id, agent.name)}
      <span class="choice-copy"><b>${esc(agent.name)}</b><small>${esc(ok ? agent.targetSub || agent.sub : agent.readOnlyReason || "当前版本没有写入实现")}</small></span>
    </button>`;
  }

  function bindTargets(body) {
    body.querySelectorAll("[data-target]").forEach((button) => {
      button.onclick = () => {
        state.sheet.target = button.dataset.target;
        state.sheet.step = 1;
        loadFolders();
        renderSheet();
      };
    });
  }

  function backSheet() {
    const sheet = state.sheet;
    if (!sheet || sheet.busy || sheet.step >= 3) return;
    if (sheet.step > 0) sheet.step -= 1;
    else if (sheet.product) sheet.product = null;
    else { closeSheet(); return; }
    renderSheet();
  }

  async function loadFolders() {
    const sheet = state.sheet;
    if (sheet.folders) return;
    sheet.folders = [];
    sheet.loadingFolders = true;
    const list = await call("folders");
    if (state.sheet !== sheet) return;
    sheet.folders = list;
    sheet.loadingFolders = false;
    if (sheet.step === 1) renderSheet();
  }

  function renderFolders(body) {
    const sheet = state.sheet;
    const target = state.targets.find((item) => item.id === sheet.target);
    const same = sharedFolder();
    const query = sheet.folderQuery.trim().toLowerCase();
    const items = (sheet.folders || []).filter((item) => !query || (item.name + item.path).toLowerCase().includes(query));
    const entry = (path, name, tag) => `<button class="folder ${sheet.directory === path ? "on" : ""}" data-path="${esc(path)}">
        ${ICON.folder}<span style="min-width:0;flex:1"><div class="folder-name">${esc(name)}${tag ? ` <small style="color:var(--accent);font-weight:600">${tag}</small>` : ""}</div><div class="folder-path">${esc(path)}</div></span></button>`;
    const chosenExtra = sheet.directory && !(sheet.folders || []).some((item) => item.path === sheet.directory) && sheet.directory !== same
      ? entry(sheet.directory, sheet.directory.split(/[\\/]/).filter(Boolean).pop() || sheet.directory, "新选的") : "";
    body.innerHTML = `<h2>放进哪个文件夹？</h2><p class="lead">${esc(target.folderHint || "选择导入记录使用的工作目录，不会复制项目文件。")}</p>
      ${target.notice ? `<div class="import-notice">${esc(target.notice)}</div>` : ""}
      <div class="folder-search">
        <label class="search">${'<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>'}<input id="folder-q" type="search" placeholder="搜索文件夹" value="${esc(sheet.folderQuery)}" /></label>
        <button id="pick" class="btn plain">选择或新建…</button>
      </div>
      <div class="folder-list">
        ${same ? entry(same, same.split(/[\\/]/).filter(Boolean).pop() || same, "和原来一样") : ""}
        ${chosenExtra}
        ${sheet.loadingFolders ? '<div class="loading"><div class="spinner"></div>正在整理文件夹…</div>' : items.filter((item) => item.path !== same).map((item) => entry(item.path, item.name, "")).join("")}
        ${!sheet.loadingFolders && !items.length && !same && !chosenExtra ? '<div class="empty" style="padding:30px 0">没有找到，点右上「选择或新建…」。</div>' : ""}
      </div>
      <div class="foot"><span class="hint">${sheet.directory ? esc(sheet.directory) : "还没有选文件夹"}</span><button id="next" class="btn primary" ${sheet.directory ? "" : "disabled"}>下一步</button></div>`;
    body.querySelectorAll("[data-path]").forEach((button) => {
      button.onclick = () => { sheet.directory = button.dataset.path; renderSheet(); };
    });
    const input = body.querySelector("#folder-q");
    input.oninput = () => {
      sheet.folderQuery = input.value;
      const pos = input.selectionStart;
      renderSheet();
      const again = $("#folder-q");
      again.focus();
      again.setSelectionRange(pos, pos);
    };
    body.querySelector("#pick").onclick = async () => {
      const chosen = await call("pick_folder");
      if (chosen) { sheet.directory = chosen; renderSheet(); }
    };
    const next = body.querySelector("#next");
    if (next) next.onclick = () => { sheet.step = 2; renderSheet(); };
  }

  function renderConfirm(body) {
    const sheet = state.sheet;
    const source = state.agents.find((item) => item.id === state.current);
    const target = state.targets.find((item) => item.id === sheet.target);
    body.innerHTML = `<h2>确认一下</h2><p class="lead">原来的记录会原样保留，这里只是复制一份过去。</p>
      <div class="summary"><dl>
        <div class="line"><dt>从</dt><dd>${esc(source.full)}</dd></div>
        <div class="line"><dt>对话</dt><dd>${state.selected.size} 条</dd></div>
        <div class="line"><dt>搬到</dt><dd>${esc(target.full)}</dd></div>
        <div class="line"><dt>文件夹</dt><dd>${esc(sheet.directory)}</dd></div>
      </dl></div>
      ${target.notice ? `<div class="import-notice">${esc(target.notice)}</div>` : ""}
      <div class="foot"><span class="hint">搬运过程中请不要关闭本软件</span><button id="go" class="btn primary">开始搬运</button></div>`;
    body.querySelector("#go").onclick = startMove;
  }

  async function startMove() {
    const sheet = state.sheet;
    const result = await call("start_move", state.current, [...state.selected], sheet.target, sheet.directory);
    if (result.error) { toast(result.error); return; }
    sheet.step = 3;
    sheet.busy = true;
    sheet.status = { total: result.total, done: 0, items: [] };
    renderSheet();
    poll();
  }

  async function poll() {
    const sheet = state.sheet;
    if (!sheet) return;
    const status = await call("move_status");
    sheet.status = status;
    if (status.finished) sheet.busy = false;
    if (state.sheet === sheet) renderSheet();
    if (!status.finished) setTimeout(poll, 450);
    else if (!sheet.autoOpened) {
      sheet.autoOpened = true;
      let last = -1;
      status.items.forEach((item, index) => { if (item.state === "ok" && item.openUrl) last = index; });
      if (last >= 0) {
        const result = await call("open_in_app", last);
        sheet.openRequest = { index: last, error: result && result.error };
        if (state.sheet === sheet) renderSheet();
        if (result && result.error) toast(result.error);
      }
    }
  }

  function renderRun(body) {
    const sheet = state.sheet;
    const status = sheet.status;
    const target = state.targets.find((item) => item.id === sheet.target);
    if (!status.finished) {
      const percent = status.total ? Math.round((status.done / status.total) * 100) : 0;
      body.innerHTML = `<h2>正在搬运…</h2><p class="lead">请稍等，不要关闭软件。</p>
        <div class="progress-bar"><i style="width:${percent}%"></i></div>
        <div class="progress-text">${status.done} / ${status.total}</div>`;
      return;
    }
    const bad = status.failed > 0;
    const hint = target.resultHint || "已写入目标软件的本机记录。";
    body.innerHTML = `<div class="done-mark ${bad ? "warn" : ""}">${bad ? ICON.dash.replace(/13/g, "26") : ICON.tick.replace(/13/g, "26")}</div>
      <h2>${bad ? "复制完成，有几条没成功" : "记录已复制"}</h2>
      <p class="lead">成功 ${status.ok} 条${status.skipped ? `，已搬过 ${status.skipped} 条` : ""}${bad ? `，没成功 ${status.failed} 条` : ""}。${status.ok ? hint : ""}</p>
      ${status.ok ? '<p class="hint" data-verification-scope>已确认记录写入后能够重新读取；目标软件是否显示、能否继续对话，仍需在对应软件确认。项目文件、附件和运行环境不会一起复制。</p>' : ""}
      ${status.items.length ? `<div class="results">${status.items.map((item, index) => `<div class="result ${item.state}"><div class="result-heading"><span class="t">${esc(item.title)}</span><span class="m">${esc(item.message)}</span></div>
        ${item.resumeCommand ? `<label class="resume-label">打开记录命令（在所选文件夹执行）<input readonly value="${esc(item.resumeCommand)}" aria-label="续聊命令" /></label>` : ""}
        ${item.openUrl && item.state === "ok" ? `<div class="result-location"><span>${sheet.openRequest?.index === index ? (sheet.openRequest.error ? "记录已复制，打开软件失败；可以重试" : "已请求打开这条记录；请在 ChatGPT 中确认") : "可请求 ChatGPT 打开这条本机记录"}</span><button class="btn plain small" data-open-app="${index}">在 ChatGPT 中打开</button></div>` : ""}
        ${item.location && item.state === "ok" ? `<div class="result-location"><span>${esc(item.location)}</span><button class="btn plain small" data-import-folder="${index}">查看位置</button></div>` : ""}</div>`).join("")}</div>` : ""}
      <div class="foot"><span class="hint">${esc(sheet.directory)}</span><button id="finish" class="btn primary">完成</button></div>`;
    body.querySelector("#finish").onclick = () => {
      closeSheet();
      state.selected = new Set();
      updateBar();
      renderList();
    };
    body.querySelectorAll("[data-open-app]").forEach((button) => {
      button.onclick = async () => {
        const result = await call("open_in_app", Number(button.dataset.openApp));
        sheet.openRequest = { index: Number(button.dataset.openApp), error: result && result.error };
        if (state.sheet === sheet) renderSheet();
        if (result.error) toast(result.error);
      };
    });
    body.querySelectorAll("[data-import-folder]").forEach((button) => {
      button.onclick = async () => {
        const result = await call("open_import_folder", Number(button.dataset.importFolder));
        if (result.error) toast(result.error);
      };
    });
  }

  /* ----------------------------------------------------------- wiring */
  function wire() {
    $("#agents").addEventListener("click", (event) => {
      const extra = event.target.closest("[data-extra]");
      if (extra) { showExtra(extra.dataset.extra); return; }
      const button = event.target.closest("[data-agent]");
      if (button) open(button.dataset.agent);
    });
    $("#list").addEventListener("click", (event) => {
      const groupButton = event.target.closest("[data-group]");
      if (groupButton) {
        const group = visibleGroups()[Number(groupButton.dataset.group)];
        const movable = group.sessions.filter((item) => item.movable);
        const all = movable.every((item) => state.selected.has(item.id));
        movable.forEach((item) => (all ? state.selected.delete(item.id) : state.selected.add(item.id)));
        updateBar();
        renderList();
        return;
      }
      const foldButton = event.target.closest("[data-fold]");
      if (foldButton) {
        const fold = foldSet();
        const key = foldButton.dataset.fold;
        if (fold.has(key)) fold.delete(key);
        else fold.add(key);
        const keep = $("#list").scrollTop;
        renderList();
        $("#list").scrollTop = keep;
        return;
      }
      const row = event.target.closest(".row");
      if (!row || row.classList.contains("disabled")) return;
      toggle(row.dataset.id);
      row.classList.toggle("selected", state.selected.has(row.dataset.id));
      updateBar();
      const keep = $("#list").scrollTop;
      renderList();
      $("#list").scrollTop = keep;
    });
    $("#chips").addEventListener("click", (event) => {
      const chip = event.target.closest("[data-kind]");
      if (!chip) return;
      state.kind = chip.dataset.kind;
      renderList();
    });
    $("#search").addEventListener("input", (event) => {
      state.query = event.target.value;
      state.searchFolded = new Set();
      renderList();
    });
    $("#fold-all").addEventListener("click", () => {
      const groups = visibleGroups();
      const fold = foldSet();
      const allFolded = groups.every((group) => fold.has(groupKey(group)));
      groups.forEach((group) => (allFolded ? fold.delete(groupKey(group)) : fold.add(groupKey(group))));
      renderList();
    });
    $("#reload").addEventListener("click", refresh);
    $("#bar-clear").addEventListener("click", () => { state.selected = new Set(); updateBar(); renderList(); });
    $("#bar-go").addEventListener("click", openSheet);
    $("#sheet").addEventListener("click", (event) => { if (event.target.closest("[data-close]")) closeSheet(); });
    $("#sheet-back").addEventListener("click", () => {
      backSheet();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || !state.sheet) return;
      if (state.sheet.step >= 3) closeSheet();
      else backSheet();
    });
  }

  async function discoverAgents() {
    const info = await call("agents");
    state.agents = info.agents;
    state.agents.forEach((agent) => { agent.full = state.agents.filter((item) => item.name === agent.name).length > 1 ? `${agent.name} ${agent.sub}` : agent.name; });
    state.targets = info.targets || info.agents;
    state.targets.forEach((agent) => { agent.full = state.targets.filter((item) => item.name === agent.name).length > 1 ? `${agent.name} ${agent.sub}` : agent.name; });
    state.unsupported = info.unsupported || [];
    renderRail();
    return info;
  }

  async function refresh() {
    const button = $("#reload");
    if (button.disabled) return;
    button.disabled = true;
    try {
      const info = await discoverAgents();
      if (!info.ready) {
        $("#list").innerHTML = '<div class="empty"><b>缺少搬运组件</b>请重新安装本软件。</div>';
        return;
      }
      const current = state.agents.find((agent) => agent.id === state.current) || state.agents[0];
      if (current) await open(current.id, true);
      else {
        state.current = null;
        state.selected = new Set();
        updateBar();
        $("#list").innerHTML = '<div class="empty"><b>还没发现支持的本机记录</b>在来源软件中产生记录后，点右上角刷新再试。</div>';
      }
    } catch {
      $("#list").innerHTML = '<div class="empty"><b>刷新没有成功</b>请稍后再试，不会使用演示数据替代您的记录。</div>';
    } finally { button.disabled = false; }
  }

  async function boot() {
    wire();
    const info = await discoverAgents();
    if (!info.ready) {
      $("#list").innerHTML = '<div class="empty"><b>缺少搬运组件</b>请重新安装本软件。</div>';
      return;
    }
    if (!state.agents.length) {
      $("#list").innerHTML = '<div class="empty"><b>还没发现支持的本机记录</b>在来源软件中产生记录后，点右上角刷新再试。</div>';
      return;
    }
    await open(state.agents[0].id);
    for (const agent of state.agents.slice(1)) {
      if (!state.cache[agent.id]) {
        state.cache[agent.id] = await call("sessions", agent.id, false);
        renderRail();
      }
    }
  }

  let started = false;
  const start = () => {
    if (window.pywebview?.platform === "cocoa" && !window.__AI_FIRST_BRIDGE_READY__) return;
    if (!started && (real() || preview)) {
      started = true;
      boot().catch(() => { $("#list").innerHTML = '<div class="empty"><b>连接本机搬运组件失败</b>请重新打开软件，不会使用演示记录代替您的数据。</div>'; });
    }
  };
  window.addEventListener("pywebviewready", start);
  window.addEventListener("ai-first-ready", start);
  setTimeout(() => {
    if (!started && !real() && !preview) $("#list").innerHTML = '<div class="loading"><div class="spinner"></div>正在连接本机搬运组件…</div>';
    start();
  }, 500);
})();
