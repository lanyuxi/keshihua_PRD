(function (global) {
  "use strict";

  const clone = value => JSON.parse(JSON.stringify(value));
  const ENUMS = {
    "components.filter.variant": ["select", "segmented", "chips"],
    "components.list.variant": ["table", "cards"],
    "components.list.density": ["comfortable", "compact"],
    "components.tabs.variant": ["underline", "pills", "segmented"],
    "components.button.size": ["small", "medium", "large"],
    "components.modal.dialog_size": ["small", "medium", "large"]
  };
  const INTEGER_RANGES = {
    "tokens.typography.base_size": [10, 24],
    "tokens.radii.control": [0, 96],
    "tokens.radii.panel": [0, 96],
    "tokens.radii.overlay": [0, 96],
    "tokens.spacing.page": [0, 96],
    "tokens.spacing.panel": [0, 96],
    "tokens.spacing.control_x": [0, 96],
    "tokens.spacing.control_y": [0, 96],
    "tokens.spacing.gap": [0, 96],
    "components.modal.drawer_width": [280, 960]
  };

  function readPath(root, path) {
    return String(path).split(".").reduce((value, key) => value == null ? undefined : value[key], root);
  }

  function setPath(root, path, value) {
    const keys = String(path).split(".");
    let cursor = root;
    keys.forEach((key, index) => {
      if (index === keys.length - 1) cursor[key] = value;
      else {
        if (!cursor[key] || typeof cursor[key] !== "object") cursor[key] = {};
        cursor = cursor[key];
      }
    });
  }

  function merge(base, patch) {
    const result = clone(base || {});
    Object.entries(patch || {}).forEach(([key, value]) => {
      result[key] = value && typeof value === "object" && !Array.isArray(value) && result[key] && typeof result[key] === "object"
        ? merge(result[key], value)
        : clone(value);
    });
    return result;
  }

  function normalizeListSettings(root) {
    const list = root?.components?.list;
    if (list?.variant === "compact") {
      list.variant = "table";
      list.density = "compact";
    }
  }

  function normalizeProfile(value) {
    if (!value || typeof value !== "object") return value;
    const normalized = clone(value);
    normalizeListSettings(normalized);
    Object.values(normalized.page_overrides || {}).forEach(normalizeListSettings);
    return normalized;
  }

  function rgb(value) {
    const text = String(value || "").trim();
    const hex = text.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
    if (hex) {
      const digits = hex[1].length === 3 ? [...hex[1]].map(char => char + char).join("") : hex[1];
      return [0, 2, 4].map(index => parseInt(digits.slice(index, index + 2), 16));
    }
    const match = text.match(/^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})/i);
    return match ? match.slice(1, 4).map(Number) : null;
  }

  function contrastRatio(foreground, background) {
    const luminance = color => {
      const channels = rgb(color);
      if (!channels || channels.some(value => value > 255)) return null;
      const linear = channels.map(value => {
        const channel = value / 255;
        return channel <= 0.03928 ? channel / 12.92 : Math.pow((channel + 0.055) / 1.055, 2.4);
      });
      return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
    };
    const a = luminance(foreground);
    const b = luminance(background);
    if (a == null || b == null) return 0;
    return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  }

  function validateProfile(profile) {
    const errors = [];
    if (!profile || typeof profile !== "object") return { valid: false, errors: ["界面规范必须是对象"] };
    if (profile.schema_version !== "1.0") errors.push("schema_version 必须为 1.0");
    if (!/^[A-Za-z][A-Za-z0-9_-]*$/.test(profile.id || "")) errors.push("id 无效");
    Object.entries(ENUMS).forEach(([path, choices]) => {
      const value = readPath(profile, path);
      if (value !== undefined && !choices.includes(value)) errors.push(`${path} 无效`);
    });
    Object.entries(INTEGER_RANGES).forEach(([path, range]) => {
      const value = readPath(profile, path);
      if (value !== undefined && (!Number.isInteger(value) || value < range[0] || value > range[1])) {
        errors.push(`${path} 必须为 ${range[0]}–${range[1]} 的整数`);
      }
    });
    const lineHeight = readPath(profile, "tokens.typography.line_height");
    if (lineHeight !== undefined && (typeof lineHeight !== "number" || lineHeight < 1.2 || lineHeight > 2.2)) {
      errors.push("tokens.typography.line_height 必须为 1.2–2.2");
    }
    Object.entries(profile.page_overrides || {}).forEach(([page, patch]) => {
      Object.entries(ENUMS).forEach(([path, choices]) => {
        const value = readPath(patch, path);
        if (value !== undefined && !choices.includes(value)) errors.push(`page_overrides.${page}.${path} 无效`);
      });
      Object.entries(INTEGER_RANGES).forEach(([path, range]) => {
        const value = readPath(patch, path);
        if (value !== undefined && (!Number.isInteger(value) || value < range[0] || value > range[1])) {
          errors.push(`page_overrides.${page}.${path} 必须为 ${range[0]}–${range[1]} 的整数`);
        }
      });
    });
    const checkContrast = (colors, prefix = "") => {
      ["brand", "brand_contrast", "ink", "surface", "canvas"].forEach(key => {
        if (!rgb(colors[key])) errors.push(`${prefix}tokens.colors.${key} 不是有效颜色`);
      });
      if (contrastRatio(colors.brand, colors.brand_contrast) < 4.5) errors.push(`${prefix}品牌色与品牌文字对比度低于 4.5:1`);
      if (contrastRatio(colors.ink, colors.surface) < 4.5) errors.push(`${prefix}主文字与面板背景对比度低于 4.5:1`);
      if (contrastRatio(colors.ink, colors.canvas) < 4.5) errors.push(`${prefix}主文字与页面背景对比度低于 4.5:1`);
    };
    checkContrast(profile.tokens?.colors || {});
    Object.entries(profile.page_overrides || {}).forEach(([page, patch]) => {
      checkContrast(merge(profile, patch).tokens?.colors || {}, `page_overrides.${page}：`);
    });
    return { valid: errors.length === 0, errors };
  }

  function create(options) {
    const frame = options.frame;
    const original = normalizeProfile(options.initialProfile);
    const storageKey = `${options.storageKey}:ui-profile:${original.id}`;
    let profile = clone(original);
    let scope = "global";
    let pageId = options.getPageId() || "page";
    let lastFocused = null;
    let applyFrame = 0;
    let persistTimer = 0;
    const root = document.querySelector("#ui-configurator");
    const drawer = document.querySelector("#ui-config-drawer");
    const openButton = document.querySelector("#ui-config-open");
    const pageLabel = document.querySelector("#ui-config-page");
    const status = document.querySelector("#ui-config-status");
    const app = document.querySelector("#app");
    const fields = [...document.querySelectorAll("[data-ui-path]")];

    function pagePatch(createIfMissing = false) {
      if (!profile.page_overrides) profile.page_overrides = {};
      if (createIfMissing && !profile.page_overrides[pageId]) profile.page_overrides[pageId] = {};
      return profile.page_overrides[pageId];
    }

    function fieldValue(path) {
      if (scope === "page") {
        const local = readPath(pagePatch(false), path);
        if (local !== undefined) return { value: local, inherited: false };
      }
      return { value: readPath(profile, path), inherited: scope === "page" };
    }

    function setFieldError(field, message = "") {
      const label = field.closest("label");
      let error = label?.querySelector(".ui-config-error");
      if (message && label && !error) {
        error = document.createElement("small");
        error.className = "ui-config-error";
        label.appendChild(error);
      }
      if (error) error.textContent = message;
      label?.classList.toggle("is-invalid", Boolean(message));
      field.setAttribute("aria-invalid", String(Boolean(message)));
    }

    function currentCapabilities() {
      return frame.contentWindow?.__vprdUiProfile?.describe?.(pageId) || {};
    }

    function render() {
      pageId = options.getPageId() || pageId;
      pageLabel.textContent = pageId;
      root.dataset.scope = scope;
      document.querySelectorAll("[data-ui-scope]").forEach(button => {
        button.setAttribute("aria-pressed", String(button.dataset.uiScope === scope));
      });
      const capabilities = currentCapabilities();
      let shadowed = 0;
      fields.forEach(field => {
        const path = field.dataset.uiPath;
        const current = fieldValue(path);
        const label = field.closest("label");
        const capability = capabilities[path];
        const isShadowed = scope === "global" && readPath(pagePatch(false), path) !== undefined;
        const currentLocked = capability?.total > 0 && capability.lockedCount === capability.total;
        const currentUnavailable = capability?.total === 0;
        const isLocked = scope === "page" && currentLocked;
        const isUnavailable = scope === "page" && currentUnavailable;
        const isPartial = Boolean(capability?.partial);
        shadowed += Number(isShadowed);
        field.value = current.value ?? "";
        field.disabled = isLocked || isUnavailable;
        setFieldError(field);
        label?.classList.toggle("is-inherited", current.inherited);
        label?.classList.toggle("is-shadowed", isShadowed);
        label?.classList.toggle("is-locked", isLocked);
        label?.classList.toggle("is-unavailable", isUnavailable);
        label?.classList.toggle("is-current-locked", scope === "global" && currentLocked);
        label?.classList.toggle("is-current-unavailable", scope === "global" && currentUnavailable);
        label?.classList.toggle("is-partial", isPartial);
        field.title = isLocked ? "该页面组件已在产品模型中固定，不能由规范覆盖"
          : isUnavailable ? "当前页面没有这类组件"
          : scope === "global" && currentLocked ? "当前页面组件已由产品模型固定；全局修改只影响其他未固定页面"
          : scope === "global" && currentUnavailable ? "当前页面没有这类组件；全局修改仍会影响其他页面"
          : isShadowed ? "当前页面已有覆盖；修改全局默认不会改变当前预览"
          : current.inherited ? "当前沿用全局值，修改后会创建页面覆盖"
          : isPartial ? "仅影响未在产品模型中固定的组件"
          : "";
      });
      status.classList.remove("is-error");
      status.textContent = scope === "global"
        ? `正在编辑全局默认${shadowed ? `；当前页面有 ${shadowed} 项覆盖` : ""}`
        : `正在编辑页面 ${pageId} 的覆盖`;
    }

    function persistSoon(immediate = false) {
      clearTimeout(persistTimer);
      const write = () => {
        try { localStorage.setItem(storageKey, JSON.stringify(profile)); } catch (_) { /* Offline preview can continue without persistence. */ }
      };
      if (immediate) write();
      else persistTimer = setTimeout(write, 160);
    }

    function apply(announce = false, immediatePersist = false) {
      const validation = validateProfile(profile);
      if (!validation.valid) {
        status.textContent = validation.errors[0];
        status.classList.add("is-error");
        return false;
      }
      const runtime = frame.contentWindow?.__vprdUiProfile;
      if (!runtime?.apply) {
        status.textContent = "当前原型不支持实时界面规范";
        status.classList.add("is-error");
        return false;
      }
      runtime.apply(profile, pageId);
      persistSoon(immediatePersist);
      options.onApply?.(clone(profile));
      if (announce) options.showToast?.("界面规范已应用");
      return true;
    }

    function scheduleApply() {
      if (applyFrame) cancelAnimationFrame(applyFrame);
      applyFrame = requestAnimationFrame(() => { applyFrame = 0; apply(); });
    }

    function updateField(field) {
      const path = field.dataset.uiPath;
      let value = field.value;
      if (field.dataset.uiType === "number") {
        if (value.trim() === "") {
          setFieldError(field, "该数值不能为空");
          return;
        }
        value = Number(value);
        const min = Number(field.min);
        const max = Number(field.max);
        if (!Number.isInteger(value) || value < min || value > max) {
          setFieldError(field, `请输入 ${min}–${max} 的整数`);
          return;
        }
      }
      const candidate = clone(profile);
      setPath(scope === "global" ? candidate : (candidate.page_overrides[pageId] ||= {}), path, value);
      const validation = validateProfile(candidate);
      if (!validation.valid) {
        setFieldError(field, validation.errors[0]);
        status.textContent = validation.errors[0];
        status.classList.add("is-error");
        return;
      }
      setFieldError(field);
      profile = candidate;
      render();
      scheduleApply();
    }

    function focusable() {
      return [...drawer.querySelectorAll("button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex='-1'])")]
        .filter(element => !element.hidden && element.offsetParent !== null);
    }

    function open() {
      pageId = options.getPageId() || pageId;
      lastFocused = document.activeElement;
      root.hidden = false;
      if (app) app.inert = true;
      openButton.setAttribute("aria-expanded", "true");
      render();
      focusable()[0]?.focus();
    }

    function close() {
      root.hidden = true;
      if (app) app.inert = false;
      openButton.setAttribute("aria-expanded", "false");
      (lastFocused && document.contains(lastFocused) ? lastFocused : openButton).focus();
    }

    function reset() {
      if (scope === "global") {
        const overrides = clone(profile.page_overrides || {});
        profile = clone(original);
        profile.page_overrides = overrides;
      } else if (profile.page_overrides) {
        delete profile.page_overrides[pageId];
      }
      apply(true, true);
      render();
    }

    function exportProfile() {
      const validation = validateProfile(profile);
      if (!validation.valid) {
        status.textContent = `无法导出：${validation.errors[0]}`;
        status.classList.add("is-error");
        options.showToast?.("界面规范存在错误，暂不能导出");
        return;
      }
      const blob = new Blob([`${JSON.stringify(profile, null, 2)}\n`], { type: "application/json;charset=utf-8" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "ui-profile.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(link.href), 0);
      options.showToast?.("已导出 ui-profile.json");
    }

    openButton.hidden = false;
    openButton.addEventListener("click", open);
    root.addEventListener("click", event => {
      if (event.target === root || event.target.closest("[data-ui-close]")) close();
      const scopeButton = event.target.closest("[data-ui-scope]");
      if (scopeButton) { scope = scopeButton.dataset.uiScope; render(); }
      if (event.target.closest("[data-ui-reset]")) reset();
      if (event.target.closest("[data-ui-export]")) exportProfile();
    });
    root.addEventListener("input", event => {
      const field = event.target.closest("input[data-ui-path]");
      if (field) updateField(field);
    });
    root.addEventListener("change", event => {
      const field = event.target.closest("select[data-ui-path]");
      if (field) updateField(field);
    });
    document.addEventListener("keydown", event => {
      if (root.hidden) return;
      if (event.key === "Escape") { close(); return; }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (!items.length) { event.preventDefault(); drawer.focus(); return; }
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });

    try {
      const saved = normalizeProfile(JSON.parse(localStorage.getItem(storageKey) || "null"));
      const validation = saved && typeof saved === "object" ? validateProfile(saved) : { valid: false };
      if (validation.valid && saved.schema_version === original.schema_version && saved.id === original.id) profile = merge(original, saved);
      else if (saved) console.warn("已忽略不兼容或无效的界面规范草稿", validation.errors || []);
    } catch (_) { /* Ignore malformed local drafts. */ }

    return {
      apply: () => apply(),
      setPage(nextPageId) {
        if (!nextPageId || nextPageId === pageId) return;
        pageId = nextPageId;
        apply();
        if (!root.hidden) render();
      },
      getProfile: () => clone(profile),
      open,
      close
    };
  }

  global.VisualPRDUIConfigurator = { create, validateProfile, normalizeProfile, contrastRatio };
})(window);
