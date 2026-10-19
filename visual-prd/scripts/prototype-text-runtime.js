(function installPrototypeText(global) {
  "use strict";
  const excluded = 'script,style,noscript,[data-vprd-text-editor],#visual-prd-annotation-runtime';
  const textNodes = element => [...element.childNodes].filter(node => node.nodeType === 3);

  function installGuard(win) {
    if (win.__visualPrdCopyGuard) return win.__visualPrdCopyGuard;
    const guard = {enabled: false};
    for (const type of ['click', 'pointerdown', 'pointerup', 'mousedown', 'mouseup', 'dblclick', 'keydown', 'keypress', 'keyup', 'submit']) {
      const handler = type === 'click' ? 'click' : type.startsWith('key') ? 'keydown' : 'pointerdown';
      win.addEventListener(type, event => {if (guard.enabled) guard[handler]?.(event);}, true);
    }
    win.__visualPrdCopyGuard = guard;
    return guard;
  }

  function apply(doc, edits) {
    function resolve(edit) {
      let element;
      try {element = doc.querySelector(edit.selector);} catch (_) {return null;}
      if (!element) return null;
      if (edit.attribute) return ['placeholder', 'value'].includes(edit.attribute) ? element : null;
      return [...element.childNodes].filter(node => node.nodeType === 3)[edit.textIndex];
    }
    const refresh = () => {
      for (const edit of edits) {
        const node = resolve(edit);
        if (!node) continue;
        const value = edit.attribute ? node.getAttribute(edit.attribute) : node.nodeValue;
        // Never overwrite unrelated business data after a rerender or row reorder.
        if (value !== edit.original || value === edit.value) continue;
        if (edit.attribute) node.setAttribute(edit.attribute, edit.value);
        else node.nodeValue = edit.value;
      }
    };
    const observer = new doc.defaultView.MutationObserver(refresh);
    observer.observe(doc.documentElement, {subtree: true, childList: true, characterData: true,
      attributes: true, attributeFilter: ['placeholder', 'value']});
    refresh();
    return {refresh, resolve, disconnect: () => observer.disconnect()};
  }

  function selectorFor(doc, element) {
    const parts = [];
    for (let node = element; node && node !== doc.body; node = node.parentElement) {
      for (const attribute of ['id', 'data-id', 'data-page', 'data-modal']) {
        const value = node.getAttribute(attribute);
        if (!value) continue;
        const selector = `[${attribute}="${doc.defaultView.CSS.escape(value)}"]`;
        if (doc.querySelectorAll(selector).length === 1) return [selector, ...parts].join(' > ');
      }
      parts.unshift(`:nth-child(${[...node.parentElement.children].indexOf(node) + 1})`);
    }
    return ['body', ...parts].join(' > ');
  }

  function create({document: doc, edits, onChange}) {
    const win = doc.defaultView;
    const guard = installGuard(win);
    const saved = edits.map(edit => ({...edit}));
    const applied = apply(doc, saved);
    let enabled = false, active = null, popup = null, outline = null;
    function close() {
      popup?.remove(); popup = null;
      if (active) {
        if (outline) active.element.style.setProperty('outline', outline.value, outline.priority);
        else active.element.style.removeProperty('outline');
      }
      active = null;
    }
    function choose(event) {
      let target = event.target;
      if (!(target instanceof win.Element) || target.closest(excluded)) return null;
      if (target.closest('svg')) target = target.closest('button,a,label') || target;
      if (target.matches('input,textarea')) {
        const attribute = target.matches('input[type=button],input[type=submit],input[type=reset]') ? 'value' : 'placeholder';
        return {element: target, attribute, original: target.getAttribute(attribute)};
      }
      if (target.matches('select')) target = target.options[target.selectedIndex] || target;
      const range = doc.caretRangeFromPoint?.(event.clientX, event.clientY);
      let node = range?.startContainer;
      if (!node || node.nodeType !== 3 || !target.contains(node) || !node.nodeValue.trim()) {
        const walker = doc.createTreeWalker(target, win.NodeFilter.SHOW_TEXT);
        node = walker.nextNode();
        while (node && ((!node.nodeValue.trim() && !saved.some(edit => !edit.attribute && applied.resolve(edit) === node)) || node.parentElement.closest(excluded))) node = walker.nextNode();
      }
      if (!node) {
        const previous = saved.find(edit => edit.selector === selectorFor(doc, target) && !edit.attribute);
        node = previous && applied.resolve(previous);
      }
      if (!node || node.parentElement.closest(excluded)) return null;
      return {element: node.parentElement, node, textIndex: textNodes(node.parentElement).indexOf(node), original: node.nodeValue};
    }
    function click(event) {
      if (!enabled) return;
      event.stopImmediatePropagation();
      if (event.target.closest?.('[data-vprd-text-editor]')) {
        if (event.target.closest('button')) close();
        return;
      }
      event.preventDefault();
      close();
      const target = choose(event);
      if (!target) return;
      const selector = selectorFor(doc, target.element);
      const existing = saved.find(edit => edit.selector === selector && edit.attribute === target.attribute && edit.textIndex === target.textIndex);
      const edit = existing || {selector, ...(target.attribute ? {attribute: target.attribute} : {textIndex: target.textIndex}), original: target.original, value: target.original};
      active = target;
      const old = target.element.style.getPropertyValue('outline');
      outline = old ? {value: old, priority: target.element.style.getPropertyPriority('outline')} : null;
      target.element.style.setProperty('outline', '2px solid #2563eb', 'important');
      popup = doc.createElement('div'); popup.dataset.vprdTextEditor = '';
      popup.setAttribute('role', 'dialog'); popup.setAttribute('aria-label', '编辑原型文案');
      popup.style.cssText = 'position:fixed;z-index:2147483647;width:min(320px,calc(100vw - 24px));padding:12px;background:#fff;border:1px solid #cdd8ee;border-radius:9px;box-shadow:0 8px 30px #17203333;color:#172033;font:13px/1.5 sans-serif;box-sizing:border-box';
      const label = doc.createElement('div'); label.textContent = '编辑原型文案 · 修改自动保存';
      const input = doc.createElement('textarea'); input.setAttribute('aria-label', '修改原型文案'); input.value = edit.value ?? ''; input.rows = 3;
      input.style.cssText = 'display:block;width:100%;box-sizing:border-box;margin:8px 0;padding:8px;border:1px solid #cdd8ee;border-radius:5px;font:inherit;color:#172033;background:#fff';
      const done = doc.createElement('button'); done.type = 'button'; done.textContent = '确定';
      done.style.cssText = 'display:block;margin-left:auto;padding:5px 14px;border:0;border-radius:5px;color:white;background:#2563eb;cursor:pointer;font:inherit';
      input.addEventListener('input', event => {
        event.stopPropagation(); edit.value = input.value;
        if (target.attribute) target.element.setAttribute(target.attribute, edit.value);
        else target.node.nodeValue = edit.value;
        if (!saved.includes(edit)) saved.push(edit);
        onChange(saved.map(item => ({...item})));
      });
      popup.append(label, input, done);
      popup.style.margin = '0'; popup.style.inset = 'auto';
      popup.setAttribute('popover', 'manual');
      (target.element.closest('dialog[open]') || doc.body).append(popup);
      popup.showPopover?.();
      const rect = target.element.getBoundingClientRect();
      popup.style.left = Math.max(12, Math.min(win.innerWidth - popup.offsetWidth - 12, rect.left)) + 'px';
      popup.style.top = Math.max(12, Math.min(win.innerHeight - popup.offsetHeight - 12, rect.bottom + 8)) + 'px';
      input.focus(); input.select();
    }
    function pointer(event) {
      if (!enabled) return;
      event.stopImmediatePropagation();
      if (!event.target.closest?.('[data-vprd-text-editor]')) {
        if (event.type === 'pointerdown' && event.target.closest?.(':disabled')) click(event);
        else event.preventDefault();
      }
    }
    function key(event) {
      if (!enabled) return;
      event.stopImmediatePropagation();
      if (!event.target.closest?.('[data-vprd-text-editor]') && !event.ctrlKey && !event.metaKey && !event.altKey) event.preventDefault();
      if (event.key === 'Escape') {event.preventDefault(); close();}
    }
    guard.click = click; guard.pointerdown = pointer; guard.keydown = key;
    return {
      setEnabled(value) {enabled = value; guard.enabled = value; if (!enabled) close();},
      destroy() {close(); applied.disconnect(); guard.enabled = false; guard.click = guard.pointerdown = guard.keydown = null;}
    };
  }
  global.VisualPRDPrototypeText = {apply, create, installGuard};
})(window);
