/**
 * Visual PRD annotation runtime.
 * Inject this file into the prototype document, then call AnnotationRuntime.init().
 */
(function installAnnotationRuntime(global) {
  "use strict";

  const VERSION = "1.1.1";
  const HOST_ID = "visual-prd-annotation-runtime";
  const VALID_SCOPES = new Set(["page", "tab", "drawer", "modal"]);
  const LAYER_RANK = { page: 0, tab: 0, drawer: 1, modal: 2 };
  const SCOPE_LABEL = { page: "页面", tab: "Tab", drawer: "抽屉", modal: "弹窗" };
  const DEFAULT_OPTIONS = {
    pageId: "",
    dotOffsetX: 6,
    dotOffsetY: 6,
    zIndex: 2147483000,
    loopNavigation: true
  };

  const state = {
    definitions: new Map(),
    ids: [],
    options: { ...DEFAULT_OPTIONS },
    currentPageId: "",
    activeRecords: [],
    activeId: "",
    host: null,
    shadow: null,
    dotsRoot: null,
    panel: null,
    scanTimer: 0,
    anchorSignature: "",
    resizeObserver: null,
    abortController: null,
    refreshFrame: 0,
    positionFrame: 0,
    missingIds: new Set()
  };

  function normalizeText(value) {
    return value == null ? "" : String(value);
  }

  function normalizeRules(value) {
    if (Array.isArray(value)) return value.map(normalizeText).filter(Boolean);
    if (value == null || value === "") return [];
    return [normalizeText(value)];
  }

  function normalizeDefinition(input) {
    if (!input || typeof input !== "object") {
      throw new TypeError("Annotation definition must be an object.");
    }
    const id = normalizeText(input.id).trim();
    if (!id) throw new TypeError("Annotation definition requires a non-empty id.");
    const order = Number(input.order);
    if (!Number.isInteger(order) || order < 1) {
      throw new TypeError(`Annotation "${id}" requires a positive integer order.`);
    }

    const rawScope = typeof input.scope === "string"
      ? { type: input.scope }
      : (input.scope || {});
    const scopeType = normalizeText(rawScope.type || "page").toLowerCase();
    if (!VALID_SCOPES.has(scopeType)) {
      throw new TypeError(`Unsupported annotation scope: ${scopeType}`);
    }

    return {
      id,
      order,
      pageId: normalizeText(input.pageId || "*").trim() || "*",
      title: normalizeText(input.title || "未命名标注"),
      body: normalizeText(input.body),
      businessRules: normalizeRules(input.businessRules),
      scope: {
        type: scopeType,
        id: normalizeText(rawScope.id).trim()
      }
    };
  }

  function definitionGroupKey(definition) {
    const pageGroup = definition.pageId === "*" ? "cross-page" : `page:${definition.pageId}`;
    return `${pageGroup}|${definition.scope.type}:${definition.scope.id}`;
  }

  function validateDefinitionOrders(definitions) {
    const groups = new Map();
    definitions.forEach(definition => {
      const key = definitionGroupKey(definition);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(definition);
    });

    groups.forEach((members, key) => {
      const seen = new Set();
      members.forEach(definition => {
        if (seen.has(definition.order)) {
          throw new TypeError(`Duplicate annotation order ${definition.order} in scope group "${key}".`);
        }
        seen.add(definition.order);
      });
    });
  }

  function validateVisibleOrders(records) {
    const orders = records.map(record => record.definition.order).sort((left, right) => left - right);
    const expected = Array.from({ length: records.length }, (_, index) => index + 1);
    if (orders.length !== expected.length || orders.some((order, index) => order !== expected[index])) {
      const detail = records.map(record => `${record.id}:${record.definition.order}`).join(", ");
      throw new TypeError(
        `Visible annotation orders for page "${state.currentPageId}" must be continuous from 1 without duplicates; got ${detail}.`
      );
    }
  }

  function isVisible(element) {
    if (!(element instanceof Element)) return false;
    if (element.closest("[hidden], [aria-hidden='true']")) return false;
    const style = getComputedStyle(element);
    if (style.display === "none" || style.visibility === "hidden") return false;
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function resolvePageId() {
    if (typeof state.options.pageId === "function") {
      const supplied = normalizeText(state.options.pageId()).trim();
      if (supplied) return supplied;
    } else if (normalizeText(state.options.pageId).trim()) {
      return normalizeText(state.options.pageId).trim();
    }

    const bodyPage = document.body?.dataset.annoPage;
    if (bodyPage) return bodyPage;

    const visiblePage = [...document.querySelectorAll("[data-anno-page]")]
      .filter(element => !element.hasAttribute("data-anno") && isVisible(element))
      .at(-1);
    if (visiblePage?.dataset.annoPage) return visiblePage.dataset.annoPage;

    return `${location.pathname}${location.hash}` || "page";
  }

  function resolveAnchorPage(anchor, definition) {
    return definition.pageId === "*"
      ? (anchor.closest("[data-anno-page]")?.dataset.annoPage || state.currentPageId)
      : definition.pageId;
  }

  function inferScope(anchor, definition, pageId) {
    const explicitContainer = anchor.closest("[data-anno-scope]");
    const dialog = anchor.closest("dialog, [role='dialog'][aria-modal='true']");
    let type = explicitContainer?.dataset.annoScope || definition.scope.type;
    let container = explicitContainer;

    if (!explicitContainer && dialog) {
      type = "modal";
      container = dialog;
    }
    type = VALID_SCOPES.has(type) ? type : "page";

    const scopeId = normalizeText(
      explicitContainer?.dataset.annoScopeId
      || explicitContainer?.id
      || dialog?.dataset.annoScopeId
      || dialog?.id
      || definition.scope.id
      || (type === "page" ? pageId : type)
    ).trim();

    return {
      type,
      id: scopeId,
      key: `${type}:${scopeId}`,
      container: container || anchor,
      rank: LAYER_RANK[type]
    };
  }

  function elementStackScore(element, domIndex) {
    const parsed = Number.parseInt(getComputedStyle(element).zIndex, 10);
    const zIndex = Number.isFinite(parsed) ? parsed : 0;
    return zIndex * 100000 + domIndex;
  }

  function sortByDefinitionOrder(records) {
    return records.sort((left, right) => (
      left.definition.order - right.definition.order
      || left.scope.key.localeCompare(right.scope.key)
      || left.id.localeCompare(right.id)
    ));
  }

  function topOverlayContext() {
    const candidates = [
      ...document.querySelectorAll(
        "[data-anno-scope='drawer'], [data-anno-scope='modal'], dialog[open], [role='dialog'][aria-modal='true']"
      )
    ];
    const seen = new Set();
    const contexts = [];

    candidates.forEach((container, domIndex) => {
      if (seen.has(container) || !isVisible(container)) return;
      seen.add(container);
      const declaredType = container.dataset.annoScope;
      const type = declaredType === "drawer" ? "drawer" : "modal";
      contexts.push({
        container,
        type,
        rank: LAYER_RANK[type],
        stackScore: elementStackScore(container, domIndex)
      });
    });

    return contexts.reduce((top, context) => {
      if (!top || context.rank > top.rank) return context;
      if (context.rank === top.rank && context.stackScore >= top.stackScore) return context;
      return top;
    }, null);
  }

  function collectRecords() {
    state.currentPageId = resolvePageId();
    const records = [];
    const anchors = [...document.querySelectorAll("[data-anno]")];

    anchors.forEach((anchor, domIndex) => {
      if (!isVisible(anchor)) return;
      const id = normalizeText(anchor.dataset.anno).trim();
      const definition = state.definitions.get(id);
      if (!definition) {
        if (id && !state.missingIds.has(id)) {
          state.missingIds.add(id);
          console.warn(`[AnnotationRuntime] Missing annotation data for data-anno="${id}".`);
        }
        return;
      }

      const pageId = resolveAnchorPage(anchor, definition);
      if (pageId !== state.currentPageId) return;
      const scope = inferScope(anchor, definition, pageId);
      records.push({
        id,
        anchor,
        definition,
        pageId,
        scope,
        domIndex,
        stackScore: elementStackScore(scope.container, domIndex)
      });
    });

    const overlay = topOverlayContext();
    if (!overlay) {
      // Page and Tab annotations share the business-page layer and can coexist.
      return sortByDefinitionOrder(records.filter(record => record.scope.rank === 0));
    }

    // An open top-layer overlay suppresses all lower layers, even if it has no annotations.
    return sortByDefinitionOrder(records.filter(record => (
      record.scope.rank === overlay.rank
      && (record.scope.container === overlay.container || overlay.container.contains(record.anchor))
    )));
  }

  function createElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text != null) element.textContent = text;
    return element;
  }

  function mount() {
    document.getElementById(HOST_ID)?.remove();
    const host = document.createElement("div");
    host.id = HOST_ID;
    host.style.cssText = `position:fixed;inset:0;z-index:${state.options.zIndex};pointer-events:none;`;
    host.innerHTML = `
      <style>
        #${HOST_ID}, #${HOST_ID} *, #${HOST_ID} *::before, #${HOST_ID} *::after { box-sizing: border-box; }
        #${HOST_ID} .anno-dots { position: fixed; inset: 0; pointer-events: none; }
        #${HOST_ID} .anno-dot {
          position: fixed; display: grid; place-items: center; width: 26px; height: 26px;
          padding: 0; border: 2px solid #fff; border-radius: 50%; color: #fff;
          background: #5b5bd6; box-shadow: 0 4px 14px rgba(42, 38, 133, .38);
          font: 800 11px/1 system-ui, sans-serif; cursor: pointer; pointer-events: auto;
          transform: translate(-50%, -50%); transition: transform 120ms ease, background 120ms ease;
        }
        #${HOST_ID} .anno-dot:hover, #${HOST_ID} .anno-dot:focus-visible, #${HOST_ID} .anno-dot[aria-expanded="true"] {
          background: #302b8d; outline: none; transform: translate(-50%, -50%) scale(1.1);
        }
        #${HOST_ID} .anno-panel {
          position: fixed; width: min(360px, calc(100vw - 24px)); max-height: min(520px, calc(100vh - 24px));
          overflow: auto; border: 1px solid rgba(91, 91, 214, .28); border-radius: 14px;
          color: #172033; background: rgba(255, 255, 255, .98);
          box-shadow: 0 20px 60px rgba(23, 32, 51, .22); pointer-events: auto;
          font: 13px/1.55 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }
        #${HOST_ID} .anno-panel[hidden] { display: none; }
        #${HOST_ID} .head { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; padding: 16px 17px 11px; }
        #${HOST_ID} .meta { margin-bottom: 4px; color: #696f82; font-size: 10px; font-weight: 750; letter-spacing: .06em; text-transform: uppercase; }
        #${HOST_ID} h2 { margin: 0; font-size: 16px; line-height: 1.35; }
        #${HOST_ID} .close { width: 28px; height: 28px; border: 0; border-radius: 8px; color: #667085; background: #f0f2f5; cursor: pointer; }
        #${HOST_ID} .content { padding: 0 17px 15px; }
        #${HOST_ID} .body { margin: 0; color: #4f586b; white-space: pre-wrap; }
        #${HOST_ID} .rules { margin-top: 14px; padding: 12px 13px; border-radius: 10px; background: #f6f6ff; }
        #${HOST_ID} .rules-title { margin: 0 0 7px; color: #4742a7; font-size: 11px; font-weight: 800; }
        #${HOST_ID} .rules ul { margin: 0; padding-left: 18px; }
        #${HOST_ID} .rules li + li { margin-top: 5px; }
        #${HOST_ID} .empty-rules { margin: 0; color: #8a6b21; }
        #${HOST_ID} .footer { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 8px; padding: 11px 13px; border-top: 1px solid #e5e8ee; }
        #${HOST_ID} .nav { min-height: 32px; padding: 0 10px; border: 1px solid #d9dce5; border-radius: 8px; color: #3f4658; background: #fff; cursor: pointer; }
        #${HOST_ID} .nav:last-child { justify-self: end; }
        #${HOST_ID} .nav:disabled { opacity: .42; cursor: default; }
        #${HOST_ID} .counter { color: #7b8191; font-size: 11px; }
      </style>
      <div class="anno-dots"></div>
      <aside class="anno-panel" role="dialog" aria-label="标注详情" hidden></aside>
    `;
    (document.body || document.documentElement).appendChild(host);
    state.host = host;
    state.shadow = host;
    state.dotsRoot = host.querySelector(".anno-dots");
    state.panel = host.querySelector(".anno-panel");
  }

  function renderDots() {
    state.dotsRoot.replaceChildren();

    state.activeRecords.forEach(record => {
      const dot = createElement("button", "anno-dot", record.definition.order);
      dot.type = "button";
      dot.dataset.annotationId = record.id;
      dot.setAttribute("aria-label", `标注 ${record.definition.order}：${record.definition.title}`);
      dot.setAttribute("aria-expanded", String(record.id === state.activeId));
      state.dotsRoot.appendChild(dot);
    });
  }

  function getRenderedNumber(id) {
    const dot = [...(state.dotsRoot?.querySelectorAll(".anno-dot") || [])]
      .find(item => item.dataset.annotationId === normalizeText(id));
    if (!dot) return null;
    const number = Number(dot.textContent);
    return Number.isInteger(number) ? number : null;
  }

  function positionDot(dot, record) {
    if (!isVisible(record.anchor)) {
      dot.hidden = true;
      return;
    }
    dot.hidden = false;
    const rect = record.anchor.getBoundingClientRect();
    const x = Math.max(13, Math.min(innerWidth - 13, rect.right + state.options.dotOffsetX));
    const y = Math.max(13, Math.min(innerHeight - 13, rect.top + state.options.dotOffsetY));
    dot.style.left = `${x}px`;
    dot.style.top = `${y}px`;
  }

  function positionPanel(record) {
    if (!record || state.panel.hidden) return;
    const dot = [...state.dotsRoot.querySelectorAll(".anno-dot")]
      .find(item => item.dataset.annotationId === record.id);
    const anchorRect = dot?.getBoundingClientRect() || record.anchor.getBoundingClientRect();
    const panelRect = state.panel.getBoundingClientRect();
    const gap = 10;
    let left = anchorRect.right + gap;
    if (left + panelRect.width > innerWidth - 12) left = anchorRect.left - panelRect.width - gap;
    left = Math.max(12, Math.min(innerWidth - panelRect.width - 12, left));
    const top = Math.max(12, Math.min(innerHeight - panelRect.height - 12, anchorRect.top - 8));
    state.panel.style.left = `${left}px`;
    state.panel.style.top = `${top}px`;
  }

  function positionAll() {
    state.positionFrame = 0;
    const byId = new Map(state.activeRecords.map(record => [record.id, record]));
    state.dotsRoot?.querySelectorAll(".anno-dot").forEach(dot => {
      const record = byId.get(dot.dataset.annotationId);
      if (record) positionDot(dot, record);
    });
    positionPanel(byId.get(state.activeId));
  }

  function schedulePosition() {
    if (!state.positionFrame) state.positionFrame = requestAnimationFrame(positionAll);
  }

  function sameScopeRecords(record) {
    return state.activeRecords.filter(candidate => candidate.scope.key === record.scope.key);
  }

  function renderPanel(record) {
    if (!record) return closePanel();
    const definition = record.definition;
    const siblings = sameScopeRecords(record);
    const siblingIndex = siblings.findIndex(item => item.id === record.id);
    const canNavigate = siblings.length > 1;

    const head = createElement("div", "head");
    const heading = createElement("div");
    heading.appendChild(createElement(
      "div",
      "meta",
      `标注 ${definition.order} · ${SCOPE_LABEL[record.scope.type]}`
    ));
    heading.appendChild(createElement("h2", "", definition.title));
    const close = createElement("button", "close", "×");
    close.type = "button";
    close.dataset.annoAction = "close";
    close.setAttribute("aria-label", "关闭标注");
    head.append(heading, close);

    const content = createElement("div", "content");
    const body = createElement("div", "body");
    const imagePattern = /!\[([^\]]*)]\((data:image\/(?:png|jpeg|gif|webp|svg\+xml)(?:;base64)?,[^\s)]+)\)/g;
    let cursor = 0;
    for (const match of definition.body.matchAll(imagePattern)) {
      body.appendChild(document.createTextNode(definition.body.slice(cursor, match.index)));
      const image = document.createElement("img");
      image.src = match[2]; image.alt = match[1]; image.style.maxWidth = "100%";
      body.appendChild(image); cursor = match.index + match[0].length;
    }
    body.appendChild(document.createTextNode(definition.body.slice(cursor)));
    content.appendChild(body);
    const rules = createElement("section", "rules");
    rules.appendChild(createElement("h3", "rules-title", "业务规则"));
    if (definition.businessRules.length) {
      const list = createElement("ul");
      definition.businessRules.forEach(rule => list.appendChild(createElement("li", "", rule)));
      rules.appendChild(list);
    } else {
      rules.appendChild(createElement("p", "empty-rules", "待确认：暂无明确业务规则"));
    }
    content.appendChild(rules);

    const footer = createElement("footer", "footer");
    const previous = createElement("button", "nav", "← 上一条");
    previous.type = "button";
    previous.dataset.annoAction = "previous";
    previous.disabled = !canNavigate;
    const counter = createElement("span", "counter", `${definition.order} / ${siblings.length}`);
    const next = createElement("button", "nav", "下一条 →");
    next.type = "button";
    next.dataset.annoAction = "next";
    next.disabled = !canNavigate;
    footer.append(previous, counter, next);

    state.panel.replaceChildren(head, content, footer);
    state.panel.hidden = false;
    state.dotsRoot.querySelectorAll(".anno-dot").forEach(dot => {
      dot.setAttribute("aria-expanded", String(dot.dataset.annotationId === record.id));
    });
    requestAnimationFrame(() => positionPanel(record));
  }

  function openPanel(id) {
    const record = state.activeRecords.find(item => item.id === id);
    if (!record) return false;
    state.activeId = id;
    renderPanel(record);
    return true;
  }

  function closePanel() {
    state.activeId = "";
    if (state.panel) state.panel.hidden = true;
    state.dotsRoot?.querySelectorAll(".anno-dot").forEach(dot => dot.setAttribute("aria-expanded", "false"));
  }

  function navigatePanel(direction) {
    const record = state.activeRecords.find(item => item.id === state.activeId);
    if (!record) return;
    const siblings = sameScopeRecords(record);
    if (siblings.length < 2) return;
    const current = siblings.findIndex(item => item.id === record.id);
    let next = current + direction;
    if (state.options.loopNavigation) next = (next + siblings.length) % siblings.length;
    else next = Math.max(0, Math.min(siblings.length - 1, next));
    openPanel(siblings[next].id);
  }

  function refreshNow() {
    state.refreshFrame = 0;
    const previousScope = state.activeRecords.find(item => item.id === state.activeId)?.scope.key;
    state.activeRecords = collectRecords();
    validateVisibleOrders(state.activeRecords);
    renderDots();
    observeTargets();

    const activeRecord = state.activeRecords.find(item => item.id === state.activeId);
    if (!activeRecord || (previousScope && activeRecord.scope.key !== previousScope)) closePanel();
    else renderPanel(activeRecord);
    schedulePosition();
    document.dispatchEvent(new CustomEvent("annotation-runtime:updated", {
      detail: {
        pageId: state.currentPageId,
        activeId: state.activeId,
        visibleIds: state.activeRecords.map(record => record.id)
      }
    }));
  }

  function refresh() {
    if (!state.refreshFrame) state.refreshFrame = requestAnimationFrame(refreshNow);
    return api;
  }

  function observeTargets() {
    if (!state.resizeObserver) return;
    state.resizeObserver.disconnect();
    state.activeRecords.forEach(record => state.resizeObserver.observe(record.anchor));
  }

  function refreshAfterExternalMotion(event) {
    if (state.host?.contains(event.target)) return;
    refresh();
  }

  function currentAnchorSignature() {
    return [...document.querySelectorAll("[data-anno]")].map(anchor => [
      anchor.dataset.anno || "",
      anchor.closest("[data-page]")?.dataset.page || "",
      anchor.closest("[data-anno-scope]")?.dataset.annoScope || "",
      anchor.closest("[data-anno-scope-id]")?.dataset.annoScopeId || "",
      anchor.hidden ? "hidden" : "visible"
    ].join(":" )).join("|");
  }

  function scanAnchorChanges() {
    const signature = currentAnchorSignature();
    if (signature === state.anchorSignature) return;
    state.anchorSignature = signature;
    refresh();
  }

  function bindEvents() {
    state.abortController = new AbortController();
    const signal = state.abortController.signal;

    document.addEventListener("click", event => {
      if (!(event.target instanceof Element)) return;
      const dot = event.target.closest(".anno-dot");
      if (dot) {
        openPanel(dot.dataset.annotationId);
        setTimeout(refresh, 0);
        return;
      }

      const panel = event.target.closest(".anno-panel");
      if (panel) {
        const action = event.target.closest("[data-anno-action]")?.dataset.annoAction;
        if (action === "close") closePanel();
        if (action === "previous") navigatePanel(-1);
        if (action === "next") navigatePanel(1);
        setTimeout(refresh, 0);
        return;
      }

      if (state.activeId) closePanel();
      setTimeout(refresh, 0);
    }, { capture: true, signal });

    document.addEventListener("scroll", schedulePosition, { capture: true, passive: true, signal });
    document.addEventListener("transitionend", refreshAfterExternalMotion, { capture: true, signal });
    document.addEventListener("animationend", refreshAfterExternalMotion, { capture: true, signal });
    document.addEventListener("proto:render", refresh, { signal });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape") closePanel();
      if (!state.activeId) return;
      if (event.key === "ArrowLeft") navigatePanel(-1);
      if (event.key === "ArrowRight") navigatePanel(1);
    }, { signal });
    global.addEventListener("resize", schedulePosition, { passive: true, signal });
    global.addEventListener("hashchange", refresh, { signal });
    global.addEventListener("popstate", refresh, { signal });

    state.resizeObserver = "ResizeObserver" in global
      ? new global.ResizeObserver(schedulePosition)
      : null;

    state.anchorSignature = currentAnchorSignature();
    state.scanTimer = global.setInterval(scanAnchorChanges, 750);
  }

  function applyDefinitionChanges(upserts, removes = []) {
    const staged = new Map(state.definitions);
    const stagedIds = state.ids.filter(id => !removes.includes(id));
    removes.forEach(id => staged.delete(id));
    upserts.map(normalizeDefinition).forEach(definition => {
      if (!staged.has(definition.id)) stagedIds.push(definition.id);
      staged.set(definition.id, definition);
    });
    validateDefinitionOrders([...staged.values()]);
    state.definitions.clear();
    staged.forEach((definition, id) => state.definitions.set(id, definition));
    state.ids = stagedIds;
    upserts.forEach(rawDefinition => state.missingIds.delete(normalizeText(rawDefinition.id)));
  }

  function init(config = {}) {
    destroy();
    state.options = { ...DEFAULT_OPTIONS, ...(config.options || {}) };
    if (config.pageId != null) state.options.pageId = config.pageId;
    const definitions = config.annotations || [];
    if (!Array.isArray(definitions)) throw new TypeError("init.annotations must be an array.");
    applyDefinitionChanges(definitions);
    mount();
    bindEvents();
    refresh();
    return api;
  }

  function update(change = {}) {
    const upsert = change.upsert || change.annotations || [];
    const remove = change.remove || [];
    if (!Array.isArray(upsert) || !Array.isArray(remove)) {
      throw new TypeError("update.upsert and update.remove must be arrays.");
    }
    const removeIds = remove.map(rawId => normalizeText(rawId));
    applyDefinitionChanges(upsert, removeIds);
    if (removeIds.includes(state.activeId)) closePanel();
    refresh();
    return api;
  }

  function setPage(pageId) {
    state.options.pageId = normalizeText(pageId).trim();
    refresh();
    return api;
  }

  function getState() {
    return {
      version: VERSION,
      pageId: state.currentPageId,
      activeId: state.activeId,
      visibleIds: state.activeRecords.map(record => record.id),
      annotations: state.ids.map(id => state.definitions.get(id)).filter(Boolean)
    };
  }

  function destroy() {
    if (state.refreshFrame) cancelAnimationFrame(state.refreshFrame);
    if (state.positionFrame) cancelAnimationFrame(state.positionFrame);
    state.abortController?.abort();
    global.clearInterval(state.scanTimer);
    state.resizeObserver?.disconnect();
    state.host?.remove();
    state.definitions.clear();
    state.ids = [];
    state.currentPageId = "";
    state.activeRecords = [];
    state.activeId = "";
    state.host = null;
    state.shadow = null;
    state.dotsRoot = null;
    state.panel = null;
    state.abortController = null;
    state.scanTimer = 0;
    state.anchorSignature = "";
    state.resizeObserver = null;
    state.refreshFrame = 0;
    state.positionFrame = 0;
    state.missingIds.clear();
  }

  const api = {
    __isVisualPrdRuntime: true,
    version: VERSION,
    init,
    update,
    refresh,
    setPage,
    open: openPanel,
    close: closePanel,
    getRenderedNumber,
    getState,
    destroy
  };

  if (global.AnnotationRuntime?.__isVisualPrdRuntime) {
    global.AnnotationRuntime.destroy();
  }
  global.AnnotationRuntime = api;
})(window);
