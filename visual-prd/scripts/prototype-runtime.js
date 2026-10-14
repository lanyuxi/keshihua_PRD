/**
 * Visual PRD prototype runtime.
 *
 * Declarative conventions:
 * - Pages:        data-page="detail"
 * - Actions:      data-action="navigate:detail"
 * - State input:  data-model="draft.title"
 * - State output: data-bind="draft.title"
 * - Visibility:   data-show="draft.ready" / data-hide="draft.ready"
 * - Modals:       data-modal="editor" data-modal-type="drawer|dialog|popover"
 * - Modal values: data-modal-bind="title"
 * - Forms:        data-form="goal" and data-validate="required|min:3"
 * - Lists:        data-list="goals", direct children use data-list-item
 * - Controls:     data-filter="status", data-search="goals", data-sort="title"
 *
 * The only public global is window.__proto.
 */
(function installPrototypeRuntime(global) {
  "use strict";

  const VERSION = "1.0.0";
  const STYLE_ID = "visual-prd-prototype-runtime-style";
  const DEFAULT_CONFIG = {
    initialState: {},
    persist: true,
    persistKey: `visual-prd:prototype:${location.pathname || "default"}`,
    pageTransition: "fade",
    render: null,
    renderers: {},
    listRenderers: {},
    validators: {},
    submitHandlers: {},
    modalRenderers: {}
  };

  const state = {
    route: { pageId: "", params: {} },
    lists: {}
  };

  let config = { ...DEFAULT_CONFIG };
  let initialized = false;
  let hydrated = false;
  let abortController = null;
  let persistTimer = 0;
  let lastRenderedPage = "";
  let modalSequence = 0;
  const modalStack = [];
  const subscribers = new Set();

  function isPlainObject(value) {
    return Boolean(value) && Object.prototype.toString.call(value) === "[object Object]";
  }

  function cloneValue(value) {
    if (Array.isArray(value)) return value.map(cloneValue);
    if (isPlainObject(value)) {
      return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, cloneValue(item)]));
    }
    return value;
  }

  function readPath(source, path, fallback) {
    if (!path) return source;
    const value = String(path).split(".").reduce((current, key) => (
      current == null ? undefined : current[key]
    ), source);
    return value === undefined ? fallback : value;
  }

  function patchForPath(path, value) {
    const keys = String(path).split(".").filter(Boolean);
    if (!keys.length) return {};
    const patch = {};
    let cursor = patch;
    keys.forEach((key, index) => {
      if (index === keys.length - 1) cursor[key] = value;
      else cursor = cursor[key] = {};
    });
    return patch;
  }

  function mergeState(target, patch, prefix, changedPaths) {
    Object.entries(patch).forEach(([key, nextValue]) => {
      const path = prefix ? `${prefix}.${key}` : key;
      const previousValue = target[key];
      // A route is an atomic browser-history snapshot. Deep-merging it would
      // keep query parameters from the page we just left (for example a
      // detail taskId leaking back into the list page after browser Back).
      if (path === "route" && isPlainObject(nextValue)) {
        const normalizedRoute = {
          pageId: String(nextValue.pageId || ""),
          params: isPlainObject(nextValue.params) ? cloneValue(nextValue.params) : {}
        };
        if (JSON.stringify(previousValue) !== JSON.stringify(normalizedRoute)) {
          target[key] = normalizedRoute;
          changedPaths.add(path);
        }
        return;
      }
      if (isPlainObject(nextValue) && isPlainObject(previousValue)) {
        mergeState(previousValue, nextValue, path, changedPaths);
        return;
      }
      if (!Object.is(previousValue, nextValue)) {
        target[key] = cloneValue(nextValue);
        changedPaths.add(path);
      }
    });
  }

  function pathsIntersect(left, right) {
    return left === right || left.startsWith(`${right}.`) || right.startsWith(`${left}.`);
  }

  function isAffected(path, changedPaths) {
    if (!changedPaths?.size) return true;
    return [...changedPaths].some(changed => pathsIntersect(path, changed));
  }

  function parseLiteral(rawValue) {
    const value = String(rawValue).trim();
    if (value === "true") return true;
    if (value === "false") return false;
    if (value === "null") return null;
    if (value === "undefined") return undefined;
    if (value !== "" && Number.isFinite(Number(value))) return Number(value);
    if ((value.startsWith("{") && value.endsWith("}")) || (value.startsWith("[") && value.endsWith("]"))) {
      try { return JSON.parse(value); } catch (_) { /* use the original string */ }
    }
    return value;
  }

  function cssEscape(value) {
    if (global.CSS?.escape) return global.CSS.escape(String(value));
    return String(value).replace(/[^a-zA-Z0-9_-]/g, character => `\\${character}`);
  }

  function safeStorageGet(key) {
    if (!config.persist) return null;
    try { return localStorage.getItem(key); } catch (_) { return null; }
  }

  function persistState() {
    if (!config.persist) return;
    clearTimeout(persistTimer);
    persistTimer = setTimeout(() => {
      try {
        localStorage.setItem(config.persistKey, JSON.stringify(state));
      } catch (error) {
        console.warn("[PrototypeRuntime] State persistence failed.", error);
      }
    }, 60);
  }

  function hydrateState() {
    if (hydrated) return;
    hydrated = true;
    mergeState(state, config.initialState || {}, "", new Set());
    const saved = safeStorageGet(config.persistKey);
    if (!saved) return;
    try {
      const parsed = JSON.parse(saved);
      if (isPlainObject(parsed)) mergeState(state, parsed, "", new Set());
    } catch (error) {
      console.warn("[PrototypeRuntime] Persisted state is invalid and was ignored.", error);
    }
  }

  function setState(patchOrUpdater) {
    const patch = typeof patchOrUpdater === "function"
      ? patchOrUpdater(state)
      : patchOrUpdater;
    if (!isPlainObject(patch)) throw new TypeError("setState(patch) requires an object or updater function.");

    const changedPaths = new Set();
    mergeState(state, patch, "", changedPaths);
    if (!changedPaths.size) return state;

    render(changedPaths);
    persistState();
    subscribers.forEach(listener => listener(state, [...changedPaths]));
    document.dispatchEvent(new CustomEvent("proto:statechange", {
      detail: { state, changedPaths: [...changedPaths] }
    }));
    return state;
  }

  function setElementValue(element, value) {
    if (element.matches("input[type='checkbox']")) {
      element.checked = Boolean(value);
    } else if (element.matches("input[type='radio']")) {
      element.checked = String(element.value) === String(value);
    } else if (element.matches("input, textarea, select")) {
      const normalized = value == null ? "" : value;
      if (element.multiple && Array.isArray(normalized)) {
        [...element.options].forEach(option => { option.selected = normalized.includes(option.value); });
      } else if (element.value !== String(normalized)) {
        element.value = String(normalized);
      }
    } else {
      element.textContent = value == null ? "" : String(value);
    }
  }

  function renderBindings(changedPaths) {
    document.querySelectorAll("[data-bind]").forEach(element => {
      const path = element.dataset.bind;
      if (isAffected(path, changedPaths)) setElementValue(element, readPath(state, path, ""));
    });

    document.querySelectorAll("[data-model]").forEach(element => {
      const path = element.dataset.model;
      if (isAffected(path, changedPaths)) setElementValue(element, readPath(state, path, ""));
    });

    document.querySelectorAll("[data-show]").forEach(element => {
      const path = element.dataset.show;
      if (isAffected(path, changedPaths)) element.hidden = !Boolean(readPath(state, path));
    });

    document.querySelectorAll("[data-hide]").forEach(element => {
      const path = element.dataset.hide;
      if (isAffected(path, changedPaths)) element.hidden = Boolean(readPath(state, path));
    });
  }

  function animatePage(page) {
    page.classList.remove("proto-page-enter-fade", "proto-page-enter-slide");
    void page.offsetWidth;
    const className = config.pageTransition === "slide"
      ? "proto-page-enter-slide"
      : "proto-page-enter-fade";
    page.classList.add(className);
    page.addEventListener("animationend", () => page.classList.remove(className), { once: true });
  }

  function renderPages(changedPaths) {
    if (!isAffected("route", changedPaths)) return;
    const pageId = state.route?.pageId || "";
    document.querySelectorAll("[data-page]").forEach(page => {
      const active = page.dataset.page === pageId;
      page.hidden = !active;
      page.setAttribute("aria-hidden", String(!active));
      page.classList.toggle("proto-page-active", active);
      if (active && pageId !== lastRenderedPage) animatePage(page);
    });
    document.querySelectorAll("[data-route-active]").forEach(element => {
      const active = element.dataset.routeActive === pageId;
      element.classList.toggle("active", active);
      element.setAttribute("aria-current", active ? "page" : "false");
    });
    lastRenderedPage = pageId;
  }

  function listControlTarget(control) {
    return control.dataset.listTarget
      || control.closest("[data-list-controls]")?.dataset.listControls
      || control.dataset.search
      || document.querySelector("[data-list]")?.dataset.list
      || "default";
  }

  function itemField(item, key) {
    const attributeKey = String(key).replace(/[A-Z]/g, letter => `-${letter.toLowerCase()}`);
    return item.getAttribute(`data-${attributeKey}`)
      ?? item.getAttribute(`data-field-${attributeKey}`)
      ?? "";
  }

  function renderLists(changedPaths) {
    if (changedPaths?.size && ![...changedPaths].some(path => pathsIntersect(path, "lists"))) return;

    document.querySelectorAll("[data-list]").forEach(list => {
      const listId = list.dataset.list;
      const listState = readPath(state, `lists.${listId}`, {});
      const listRenderer = config.listRenderers?.[listId];
      if (typeof listRenderer === "function") {
        listRenderer(list, Array.isArray(listState.items) ? listState.items : [], state);
      }
      const filters = listState.filters || {};
      const search = String(listState.search || "").trim().toLocaleLowerCase();
      const sort = listState.sort || {};
      const items = [...list.children].filter(child => child.hasAttribute("data-list-item"));

      items.forEach(item => {
        const matchesFilters = Object.entries(filters).every(([key, value]) => {
          if (value == null || value === "" || value === "all") return true;
          const itemValue = itemField(item, key);
          return Array.isArray(value) ? value.includes(itemValue) : itemValue === String(value);
        });
        const searchText = (item.dataset.searchText || item.textContent || "").toLocaleLowerCase();
        item.hidden = !(matchesFilters && (!search || searchText.includes(search)));
      });

      document.querySelectorAll(`[data-empty-for="${cssEscape(listId)}"]`).forEach(empty => {
        empty.hidden = items.some(item => !item.hidden);
      });

      if (sort.key) {
        const direction = sort.direction === "desc" ? -1 : 1;
        items.sort((left, right) => {
          const leftValue = itemField(left, sort.key);
          const rightValue = itemField(right, sort.key);
          const leftNumber = Number(leftValue);
          const rightNumber = Number(rightValue);
          if (leftValue !== "" && rightValue !== "" && Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) {
            return (leftNumber - rightNumber) * direction;
          }
          return leftValue.localeCompare(rightValue, "zh-CN", { numeric: true }) * direction;
        });
        items.forEach(item => list.appendChild(item));
      }

      document.querySelectorAll(`[data-list-target="${cssEscape(listId)}"][data-filter]`).forEach(control => {
        if (!control.matches("button, [role='button']")) return;
        const [key, value = control.value] = control.dataset.filter.split("=");
        const active = String(filters[key] ?? "all") === String(value ?? "");
        control.classList.toggle("active", active);
        control.setAttribute("aria-pressed", String(active));
      });
    });
  }

  function renderCustomRegions(changedPaths) {
    document.querySelectorAll("[data-render]").forEach(region => {
      const renderer = config.renderers?.[region.dataset.render];
      if (typeof renderer !== "function") return;
      const dependencies = (region.dataset.renderDeps || "")
        .split(",")
        .map(value => value.trim())
        .filter(Boolean);
      if (dependencies.length && changedPaths?.size && !dependencies.some(path => isAffected(path, changedPaths))) return;
      renderer(region, state, { changedPaths: [...(changedPaths || [])] });
    });
  }

  function render(changedPaths) {
    const normalized = changedPaths instanceof Set
      ? changedPaths
      : new Set(Array.isArray(changedPaths) ? changedPaths : []);
    renderBindings(normalized);
    renderPages(normalized);
    renderLists(normalized);
    renderCustomRegions(normalized);
    if (typeof config.render === "function") {
      config.render(state, { changedPaths: [...normalized] });
    }
    document.dispatchEvent(new CustomEvent("proto:render", {
      detail: { state, changedPaths: [...normalized] }
    }));
    return state;
  }

  function encodeRoute(pageId, params) {
    const query = new URLSearchParams();
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value == null) return;
      if (Array.isArray(value)) value.forEach(item => query.append(key, item));
      else query.set(key, value);
    });
    const suffix = query.toString();
    return `#/page/${encodeURIComponent(pageId)}${suffix ? `?${suffix}` : ""}`;
  }

  function decodeRoute(hash) {
    const match = String(hash || "").match(/^#\/page\/([^?]+)(?:\?(.*))?$/);
    if (!match) return null;
    const params = {};
    new URLSearchParams(match[2] || "").forEach((value, key) => {
      if (Object.prototype.hasOwnProperty.call(params, key)) {
        params[key] = Array.isArray(params[key]) ? [...params[key], value] : [params[key], value];
      } else params[key] = value;
    });
    return { pageId: decodeURIComponent(match[1]), params };
  }

  function firstPageId() {
    return document.querySelector("[data-page]")?.dataset.page || "home";
  }

  function pageExists(pageId) {
    return Boolean(document.querySelector(`[data-page="${cssEscape(pageId)}"]`));
  }

  function isEmbeddedDocument() {
    return location.protocol === "about:" && global.parent && global.parent !== global;
  }

  function notifyParentRoute(route, replace = false) {
    if (!isEmbeddedDocument()) return false;
    try {
      global.parent.postMessage({ type: "visual-prd:prototype-route", route, replace }, "*");
      return true;
    } catch (_) {
      return false;
    }
  }

  function navigate(pageId, params = {}) {
    const normalizedPageId = String(pageId || "").trim();
    if (!normalizedPageId) throw new TypeError("navigate(pageId) requires a page ID.");
    if (!pageExists(normalizedPageId)) {
      console.warn(`[PrototypeRuntime] Page not found: ${normalizedPageId}`);
      return null;
    }
    const route = { pageId: normalizedPageId, params: cloneValue(params || {}) };
    setState({ route });
    const nextHash = encodeRoute(route.pageId, route.params);
    if (!notifyParentRoute(route) && location.hash !== nextHash) {
      try { location.hash = nextHash; }
      catch (_) { /* about:srcdoc and sandboxed frames cannot update History */ }
    }
    return route;
  }

  function syncRouteFromHash() {
    const route = decodeRoute(location.hash);
    if (route && pageExists(route.pageId)) {
      setState({ route });
      return;
    }
    const fallback = { pageId: firstPageId(), params: {} };
    setState({ route: fallback });
    try { history.replaceState(null, "", encodeRoute(fallback.pageId, fallback.params)); }
    catch (_) { /* keep in-memory routing when History is unavailable */ }
  }

  function modalElement(modalId) {
    return document.querySelector(`[data-modal="${cssEscape(modalId)}"]`);
  }

  function resolveModalType(element, data) {
    const type = data?.type || element.dataset.modalType || "dialog";
    return ["drawer", "dialog", "popover"].includes(type) ? type : "dialog";
  }

  function bindModalData(element, data) {
    element.querySelectorAll("[data-modal-bind]").forEach(target => {
      const value = readPath(data, target.dataset.modalBind, "");
      setElementValue(target, value);
    });
  }

  function positionPopover(layer) {
    if (layer.type !== "popover") return;
    const anchor = layer.anchor;
    if (!(anchor instanceof Element) || !anchor.isConnected) return;
    const anchorRect = anchor.getBoundingClientRect();
    const modalRect = layer.element.getBoundingClientRect();
    let left = anchorRect.left;
    let top = anchorRect.bottom + 8;
    if (left + modalRect.width > innerWidth - 10) left = innerWidth - modalRect.width - 10;
    if (top + modalRect.height > innerHeight - 10) top = anchorRect.top - modalRect.height - 8;
    layer.element.style.left = `${Math.max(10, left)}px`;
    layer.element.style.top = `${Math.max(10, top)}px`;
  }

  function openModal(modalId, data = {}) {
    const normalizedId = String(modalId || "").trim();
    const element = modalElement(normalizedId);
    if (!element) {
      console.warn(`[PrototypeRuntime] Modal not found: ${normalizedId}`);
      return null;
    }

    const existingIndex = modalStack.findIndex(layer => layer.id === normalizedId);
    if (existingIndex >= 0) {
      const [existing] = modalStack.splice(existingIndex, 1);
      modalStack.push(existing);
      existing.data = data;
      bindModalData(existing.element, data);
      return existing;
    }

    const type = resolveModalType(element, data);
    const trigger = data.trigger instanceof Element ? data.trigger : document.activeElement;
    const anchor = data.anchor instanceof Element
      ? data.anchor
      : (typeof data.anchor === "string" ? document.querySelector(data.anchor) : trigger);
    const layer = {
      id: normalizedId,
      type,
      element,
      data,
      trigger,
      anchor,
      originalParent: element.parentNode,
      originalNextSibling: element.nextSibling,
      backdrop: null,
      sequence: ++modalSequence
    };

    if (type !== "popover") {
      const backdrop = document.createElement("div");
      backdrop.className = "proto-modal-backdrop";
      backdrop.dataset.modalBackdrop = normalizedId;
      backdrop.style.zIndex = String(10000 + layer.sequence * 2);
      document.body.appendChild(backdrop);
      layer.backdrop = backdrop;
      requestAnimationFrame(() => backdrop.classList.add("open"));
    }

    document.body.appendChild(element);
    element.hidden = false;
    element.dataset.modalType = type;
    element.classList.add("proto-modal-layer");
    element.style.zIndex = String(10001 + layer.sequence * 2);
    element.setAttribute("aria-hidden", "false");
    if (type !== "popover") {
      element.setAttribute("role", "dialog");
      element.setAttribute("aria-modal", "true");
    }
    bindModalData(element, data);
    modalStack.push(layer);

    const renderer = config.modalRenderers?.[normalizedId];
    if (typeof renderer === "function") renderer(element, data, state);
    requestAnimationFrame(() => {
      element.classList.add("open");
      positionPopover(layer);
      element.querySelector("[autofocus], input, select, textarea, button")?.focus();
    });
    document.dispatchEvent(new CustomEvent("proto:modalopen", { detail: { modalId: normalizedId, type, data } }));
    return layer;
  }

  function closeModal() {
    const layer = modalStack.pop();
    if (!layer) return null;
    layer.element.classList.remove("open");
    layer.backdrop?.classList.remove("open");

    const finish = () => {
      layer.element.hidden = true;
      layer.element.classList.remove("proto-modal-layer");
      layer.element.removeAttribute("style");
      layer.element.setAttribute("aria-hidden", "true");
      layer.backdrop?.remove();
      if (layer.originalParent) {
        layer.originalParent.insertBefore(layer.element, layer.originalNextSibling);
      }
      if (layer.trigger instanceof HTMLElement && layer.trigger.isConnected) layer.trigger.focus();
    };
    setTimeout(finish, 190);
    document.dispatchEvent(new CustomEvent("proto:modalclose", {
      detail: { modalId: layer.id, type: layer.type }
    }));
    return layer;
  }

  function closeAllModals() {
    while (modalStack.length) closeModal();
  }

  function inputValue(element) {
    if (element.matches("input[type='checkbox']")) return element.checked;
    if (element.matches("input[type='radio']")) return element.checked ? element.value : undefined;
    if (element.matches("select[multiple]")) return [...element.selectedOptions].map(option => option.value);
    if (element.dataset.valueType === "number") return element.value === "" ? null : Number(element.value);
    return element.value;
  }

  function errorKey(field) {
    return field.dataset.model || field.name || field.id || "field";
  }

  function showFieldError(field, message) {
    const key = errorKey(field);
    let error = field.parentElement?.querySelector(`[data-error-for="${cssEscape(key)}"]`);
    if (!error) {
      error = document.createElement("div");
      error.className = "proto-field-error";
      error.dataset.errorFor = key;
      error.id = `proto-error-${Math.random().toString(36).slice(2)}`;
      field.insertAdjacentElement("afterend", error);
    }
    error.textContent = message || "";
    error.hidden = !message;
    field.setAttribute("aria-invalid", String(Boolean(message)));
    if (message) field.setAttribute("aria-describedby", error.id);
    else field.removeAttribute("aria-describedby");
  }

  function validateField(field) {
    const value = inputValue(field);
    const text = Array.isArray(value) ? value.join("") : String(value ?? "");
    const rules = (field.dataset.validate || "").split("|").filter(Boolean);
    if (field.required && !rules.includes("required")) rules.unshift("required");

    for (const ruleText of rules) {
      const [rule, argument = ""] = ruleText.split(":");
      if (rule === "required" && (!text.trim() || (field.type === "checkbox" && !field.checked))) return "此字段为必填项";
      if (rule === "email" && text && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text)) return "请输入有效的邮箱地址";
      if (rule === "number" && text && !Number.isFinite(Number(text))) return "请输入有效数字";
      if (rule === "min" && text.length < Number(argument)) return `至少输入 ${argument} 个字符`;
      if (rule === "max" && text.length > Number(argument)) return `最多输入 ${argument} 个字符`;
      if (rule === "min-value" && text && Number(text) < Number(argument)) return `数值不能小于 ${argument}`;
      if (rule === "max-value" && text && Number(text) > Number(argument)) return `数值不能大于 ${argument}`;
      const custom = config.validators?.[rule];
      if (typeof custom === "function") {
        const result = custom(value, field, state, argument);
        if (result !== true && result) return String(result);
      }
    }
    return "";
  }

  function validateForm(form) {
    let firstInvalid = null;
    form.querySelectorAll("input, select, textarea, [data-model]").forEach(field => {
      if (field.disabled) return;
      const message = validateField(field);
      showFieldError(field, message);
      if (message && !firstInvalid) firstInvalid = field;
    });
    firstInvalid?.focus();
    return !firstInvalid;
  }

  function formValues(form) {
    const result = Object.fromEntries(new FormData(form).entries());
    form.querySelectorAll("[data-model]").forEach(field => {
      const value = inputValue(field);
      const key = field.name || field.dataset.model;
      if (value !== undefined && key) result[key] = value;
    });
    return result;
  }

  async function submitForm(form, formId, event) {
    if (!form || !validateForm(form)) return false;
    const values = formValues(form);
    const handler = config.submitHandlers?.[formId];
    try {
      const result = typeof handler === "function"
        ? await handler({ values, state, form, event, setState })
        : null;
      if (isPlainObject(result)) setState(result);
      document.dispatchEvent(new CustomEvent("proto:submit", {
        detail: { formId, values, handled: typeof handler === "function" }
      }));
      return true;
    } catch (error) {
      console.error(`[PrototypeRuntime] Submit handler failed: ${formId}`, error);
      document.dispatchEvent(new CustomEvent("proto:submiterror", { detail: { formId, error } }));
      return false;
    }
  }

  function parseDataObject(rawValue) {
    if (!rawValue) return {};
    try { return JSON.parse(rawValue); }
    catch (_) { console.warn("[PrototypeRuntime] Invalid JSON data was ignored:", rawValue); return {}; }
  }

  function applyAction(element, action, event) {
    const separator = action.indexOf(":");
    const type = separator < 0 ? action : action.slice(0, separator);
    const payload = separator < 0 ? "" : action.slice(separator + 1);

    if (type === "navigate") {
      navigate(payload, parseDataObject(element.dataset.params));
      return;
    }
    if (type === "open-modal") {
      openModal(payload, { ...parseDataObject(element.dataset.modalData), trigger: element });
      return;
    }
    if (type === "close-modal") {
      closeModal();
      return;
    }
    if (type === "set-state") {
      const equals = payload.indexOf("=");
      if (equals < 1) throw new Error(`Invalid set-state action: ${action}`);
      setState(patchForPath(payload.slice(0, equals), parseLiteral(payload.slice(equals + 1))));
      return;
    }
    if (type === "toggle") {
      setState(patchForPath(payload, !Boolean(readPath(state, payload))));
      return;
    }
    if (type === "submit") {
      const form = document.getElementById(payload) || document.querySelector(`[data-form="${cssEscape(payload)}"]`);
      if (form?.requestSubmit) form.requestSubmit();
      else submitForm(form, payload, event);
    }
  }

  function updateFilter(control) {
    const listId = listControlTarget(control);
    const [key, declaredValue] = control.dataset.filter.split("=");
    let value = declaredValue;
    if (value === undefined) value = inputValue(control);
    setState(patchForPath(`lists.${listId}.filters.${key}`, value));
  }

  function updateSearch(control) {
    const listId = listControlTarget(control);
    setState(patchForPath(`lists.${listId}.search`, control.value));
  }

  function updateSort(control) {
    const listId = listControlTarget(control);
    const key = control.dataset.sort;
    const current = readPath(state, `lists.${listId}.sort`, {});
    const direction = current.key === key && current.direction === "asc" ? "desc" : "asc";
    setState(patchForPath(`lists.${listId}.sort`, { key, direction }));
    control.dataset.sortDirection = direction;
  }

  function bindEvents() {
    abortController = new AbortController();
    const signal = abortController.signal;

    document.addEventListener("click", event => {
      const actionElement = event.target.closest("[data-action]");
      if (actionElement && !actionElement.matches(":disabled, [aria-disabled='true']")) {
        event.preventDefault();
        applyAction(actionElement, actionElement.dataset.action, event);
        return;
      }
      const filter = event.target.closest("button[data-filter], [role='button'][data-filter]");
      if (filter) {
        event.preventDefault();
        updateFilter(filter);
        return;
      }
      const sort = event.target.closest("[data-sort]");
      if (sort) {
        event.preventDefault();
        updateSort(sort);
        return;
      }
      const backdrop = event.target.closest("[data-modal-backdrop]");
      if (backdrop && modalStack.at(-1)?.backdrop === backdrop) closeModal();
    }, { signal });

    document.addEventListener("input", event => {
      const field = event.target.closest("[data-model]");
      if (field) {
        const value = inputValue(field);
        if (value !== undefined) setState(patchForPath(field.dataset.model, value));
        showFieldError(field, "");
      }
      const search = event.target.closest("[data-search]");
      if (search) updateSearch(search);
    }, { signal });

    document.addEventListener("change", event => {
      const filter = event.target.closest("input[data-filter], select[data-filter]");
      if (filter) updateFilter(filter);
      const field = event.target.closest("select[data-model], input[type='checkbox'][data-model], input[type='radio'][data-model]");
      if (field) {
        const value = inputValue(field);
        if (value !== undefined) setState(patchForPath(field.dataset.model, value));
      }
    }, { signal });

    document.addEventListener("submit", event => {
      const form = event.target.closest("form");
      if (!form) return;
      event.preventDefault();
      submitForm(form, form.dataset.form || form.id || "default", event);
    }, { signal });

    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && modalStack.length) {
        event.preventDefault();
        closeModal();
        return;
      }
      if (!["Enter", " "].includes(event.key) || !(event.target instanceof Element)) return;
      const filter = event.target.closest("[role='button'][data-filter]");
      const sort = event.target.closest("[role='button'][data-sort]");
      if (filter || sort) {
        event.preventDefault();
        if (filter) updateFilter(filter);
        else updateSort(sort);
      }
    }, { signal });

    global.addEventListener("hashchange", syncRouteFromHash, { signal });
    global.addEventListener("popstate", syncRouteFromHash, { signal });
    global.addEventListener("message", event => {
      if (event.source !== global.parent || event.data?.type !== "visual-prd:prototype-navigate") return;
      const route = event.data.route;
      if (route?.pageId) setState({ route: { pageId: String(route.pageId), params: cloneValue(route.params || {}) } });
    }, { signal });
    global.addEventListener("resize", () => modalStack.forEach(positionPopover), { passive: true, signal });
    document.addEventListener("scroll", () => modalStack.forEach(positionPopover), { capture: true, passive: true, signal });
  }

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      @keyframes proto-page-fade { from { opacity: 0; } to { opacity: 1; } }
      @keyframes proto-page-slide { from { opacity: 0; transform: translateX(14px); } to { opacity: 1; transform: translateX(0); } }
      .proto-page-enter-fade { animation: proto-page-fade 180ms ease both; }
      .proto-page-enter-slide { animation: proto-page-slide 220ms ease both; }
      .proto-modal-backdrop { position: fixed; inset: 0; opacity: 0; background: var(--backdrop, rgba(15, 23, 42, .46)); transition: opacity 180ms ease; }
      .proto-modal-backdrop.open { opacity: 1; }
      .proto-modal-layer { position: fixed; opacity: 0; pointer-events: none; transition: opacity 180ms ease, transform 180ms ease; }
      .proto-modal-layer.open { opacity: 1; pointer-events: auto; }
      .proto-modal-layer[data-modal-type="dialog"] { left: 50%; top: 50%; max-width: calc(100vw - 24px); max-height: calc(100vh - 24px); transform: translate(-50%, -48%) scale(.98); }
      .proto-modal-layer[data-modal-type="dialog"].open { transform: translate(-50%, -50%) scale(1); }
      .proto-modal-layer[data-modal-type="drawer"] { top: 0; right: 0; height: 100vh; max-width: calc(100vw - 24px); transform: translateX(100%); }
      .proto-modal-layer[data-modal-type="drawer"].open { transform: translateX(0); }
      .proto-modal-layer[data-modal-type="popover"] { transform: translateY(5px); }
      .proto-modal-layer[data-modal-type="popover"].open { transform: translateY(0); }
      .proto-field-error { margin-top: 5px; color: var(--danger, #c03245); font: 12px/1.4 var(--font-family, system-ui, sans-serif); }
    `;
    (document.head || document.documentElement).appendChild(style);
  }

  function init(options = {}) {
    config = {
      ...config,
      ...options,
      renderers: { ...config.renderers, ...(options.renderers || {}) },
      listRenderers: { ...config.listRenderers, ...(options.listRenderers || {}) },
      validators: { ...config.validators, ...(options.validators || {}) },
      submitHandlers: { ...config.submitHandlers, ...(options.submitHandlers || {}) },
      modalRenderers: { ...config.modalRenderers, ...(options.modalRenderers || {}) }
    };

    if (!initialized) {
      initialized = true;
      injectStyles();
      hydrateState();
      bindEvents();
      const route = decodeRoute(location.hash);
      if (route && pageExists(route.pageId)) mergeState(state, { route }, "", new Set());
      else {
        const configuredRoute = config.initialState?.route;
        const pageId = pageExists(configuredRoute?.pageId) ? configuredRoute.pageId : firstPageId();
        state.route = {
          pageId,
          params: isPlainObject(configuredRoute?.params) ? cloneValue(configuredRoute.params) : {}
        };
        // Inside the review container the parent URL is authoritative. Do not
        // overwrite it with a persisted iframe route during startup; the
        // parent will immediately send its current hash route after load.
        if (!isEmbeddedDocument()) {
          try { history.replaceState(null, "", encodeRoute(pageId, state.route.params)); }
          catch (_) { /* keep in-memory routing when History is unavailable */ }
        }
      }
      render();
    } else if (options.initialState) {
      setState(options.initialState);
    } else {
      render();
    }
    return api;
  }

  function subscribe(listener) {
    if (typeof listener !== "function") throw new TypeError("subscribe(listener) requires a function.");
    subscribers.add(listener);
    return () => subscribers.delete(listener);
  }

  function destroy() {
    abortController?.abort();
    abortController = null;
    clearTimeout(persistTimer);
    closeAllModals();
    document.getElementById(STYLE_ID)?.remove();
    subscribers.clear();
    initialized = false;
  }

  const api = {
    version: VERSION,
    state,
    init,
    setState,
    render,
    navigate,
    openModal,
    closeModal,
    subscribe,
    destroy
  };

  if (global.__proto?.destroy && global.__proto?.version) global.__proto.destroy();
  global.__proto = api;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => { if (!initialized) init(); }, { once: true });
  } else {
    init();
  }
})(window);
