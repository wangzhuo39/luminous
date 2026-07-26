import { foldTodayCategories } from './life-flow-state.js';

const CATEGORY_LABELS = Object.freeze({
  activeActivities: '正在发生',
  calendarEvents: '时间落点',
  intentions: '想照看的事',
  carriedOver: '从昨天带来',
  completedTasks: '已经收好的光影',
});

function element(tagName, options = {}) {
  const node = document.createElement(tagName);
  for (const [name, value] of Object.entries(options)) {
    if (name === 'className') node.className = value;
    else if (name === 'textContent') node.textContent = value;
    else node.setAttribute(name, value);
  }
  return node;
}

function uniqueItems(items) {
  const seen = new Set();
  return (Array.isArray(items) ? items : []).filter((item) => {
    const key = typeof item?.key === 'string' ? item.key.trim() : '';
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return typeof item.title === 'string' && item.title.length > 0;
  });
}

function categoryItems(today, name) {
  if (name === 'intentions') {
    return uniqueItems([...(today.dueTasks ?? []), ...(today.routines ?? [])]);
  }
  if (name === 'carriedOver') {
    return uniqueItems([...(today.overdueTasks ?? []), ...(today.openTasks ?? [])]);
  }
  return uniqueItems(today[name]);
}

function safeDate(value) {
  const match = typeof value === 'string'
    ? /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
    : null;
  if (!match) return null;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 12);
  return Number.isNaN(date.getTime()) ? null : date;
}

function safeInstant(value) {
  if (typeof value !== 'string' || !/(?:Z|[+-]\d{2}:\d{2})$/.test(value)) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function createTodayView(dom, { onResourceSelect = () => {} } = {}) {
  const expanded = new Set();
  let resourcesExpanded = false;
  let resourceEntries = [];
  let returnTarget = null;
  const dateFormatter = new Intl.DateTimeFormat('zh-CN', {
    month: 'long', day: 'numeric', weekday: 'long',
  });
  const timeFormatter = new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit', minute: '2-digit', hour12: false,
  });

  function announce(message) {
    if (dom.status && dom.status.textContent !== message) dom.status.textContent = message;
  }

  function setLocalState(node, message, retryButton, canRetry) {
    if (!node) return;
    node.hidden = !message;
    const messageNode = node.querySelector('[data-hook$="state-message"]');
    if (messageNode) messageNode.textContent = message;
    if (retryButton) retryButton.hidden = !canRetry;
  }

  function renderItem(item, className) {
    const listItem = element('li', { className });
    const isResource = item.kind === 'task'
      || item.kind === 'routine'
      || item.kind === 'activity'
      || item.kind === 'reminder'
      || item.kind === 'calendar';
    const content = isResource
      ? element('button', { type: 'button', className: 'today-resource-entry' })
      : listItem;
    if (isResource) {
      const index = resourceEntries.length;
      content.dataset.resourceIndex = String(index);
      resourceEntries.push({
        resource: item.kind === 'task' ? 'tasks'
          : item.kind === 'routine' ? 'routines'
            : item.kind === 'activity' ? 'activities'
              : item.kind === 'reminder' ? 'reminders' : 'calendarEvents',
        key: item.key,
        node: content,
      });
    }
    const occurredAt = safeInstant(item.occurredAt);
    if (occurredAt) {
      content.append(element('time', {
        className: 'today-item-time',
        datetime: item.occurredAt,
        textContent: timeFormatter.format(occurredAt),
      }));
    }
    content.append(element('span', {
      className: 'today-item-title', textContent: item.title,
    }));
    if (isResource) listItem.append(content);
    return listItem;
  }

  function renderCategory(today, category, foldedCompleted = false) {
    const name = foldedCompleted ? 'completedTasks' : category.name;
    const items = categoryItems(today, name);
    const isExpanded = expanded.has(name);
    const section = element('section', { className: 'today-cluster' });
    section.dataset.category = name;
    section.classList.toggle('is-expanded', isExpanded);
    const heading = element('h3', {
      className: 'today-cluster-title', textContent: CATEGORY_LABELS[name],
    });
    const list = element('ul', { className: 'today-item-list' });
    items.forEach((item, index) => {
      const listItem = renderItem(item, 'today-item');
      listItem.hidden = foldedCompleted ? !isExpanded : index >= 3 && !isExpanded;
      if (foldedCompleted || index >= 3) listItem.dataset.disclosureItem = name;
      list.append(listItem);
    });

    if (foldedCompleted) {
      heading.hidden = !isExpanded;
      list.hidden = !isExpanded;
    }
    section.append(heading, list);

    const hiddenCount = foldedCompleted ? items.length : Math.max(0, items.length - 3);
    if (hiddenCount > 0) {
      const button = element('button', {
        type: 'button',
        className: 'today-disclosure-button',
        'aria-expanded': String(isExpanded),
      });
      button.dataset.category = name;
      button.dataset.hiddenCount = String(hiddenCount);
      button.dataset.folded = String(foldedCompleted);
      button.textContent = foldedCompleted && !isExpanded
        ? `+${hiddenCount} 已收集光影`
        : isExpanded ? '收起' : `+${hiddenCount} 展开`;
      foldedCompleted ? section.prepend(button) : section.append(button);
    }
    return section;
  }

  function renderClusters(today) {
    resourceEntries = [];
    const folded = foldTodayCategories(today);
    dom.clusters.replaceChildren();
    folded.visibleCategories.forEach((category) => {
      dom.clusters.append(renderCategory(today, category));
    });
    if (folded.foldedCompleted) {
      dom.clusters.append(renderCategory(today, folded.foldedCompleted, true));
    }
    return folded.visibleCategories.length > 0 || folded.foldedCompleted !== null;
  }

  function renderResourceNav(showToday) {
    const shouldShow = showToday && resourcesExpanded;
    if (dom.resourceNav) dom.resourceNav.hidden = !shouldShow;
    if (dom.resourceNavToggle) {
      dom.resourceNavToggle.setAttribute('aria-expanded', String(shouldShow));
      dom.resourceNavToggle.textContent = shouldShow ? '收起' : '展开';
    }
  }

  function renderToday(today) {
    const hasData = today.data && typeof today.data === 'object';
    const pending = today.status === 'loading' || today.status === 'refreshing';
    dom.refresh.disabled = pending;
    dom.refresh.setAttribute('aria-busy', String(pending));
    setLocalState(dom.todayState, '', dom.todayRetry, false);

    if (!hasData && (today.status === 'unloaded' || today.status === 'loading')) {
      dom.clusters.replaceChildren(...Array.from({ length: 3 }, () => (
        element('div', { className: 'today-skeleton', 'aria-hidden': 'true' })
      )));
      announce('正在让今天的光线落定');
      return;
    }
    if (!hasData && today.status === 'error') {
      dom.clusters.replaceChildren();
      setLocalState(dom.todayState, today.error?.message || '今日暂时没有展开。', dom.todayRetry, true);
      announce('今日暂时没有展开');
      renderResourceNav(true);
      return;
    }

    const hasContent = renderClusters(today.data);
    if (!hasContent) {
      setLocalState(dom.todayState, '晨光静静落着，今天还没有需要展开的事。', dom.todayRetry, false);
    } else if (today.status === 'error') {
      setLocalState(dom.todayState, today.error?.message || '刷新暂时没有完成。', dom.todayRetry, true);
    }
    renderResourceNav(true);
    announce(today.status === 'refreshing' ? '正在让光线重新落定' : '今日光影已经展开');
  }

  function renderTimeline(timeline) {
    dom.timelineList.replaceChildren();
    setLocalState(dom.timelineState, '', dom.timelineRetry, false);
    if (timeline.status === 'unloaded' || timeline.status === 'loading') {
      setLocalState(dom.timelineState, '正在沿着光影往回看。', dom.timelineRetry, false);
      announce('正在展开时间线');
      return;
    }
    if (timeline.status === 'error') {
      setLocalState(dom.timelineState, timeline.error?.message || '时间线暂时没有展开。', dom.timelineRetry, true);
      announce('时间线暂时没有展开');
      return;
    }
    if (!Array.isArray(timeline.items) || timeline.items.length === 0) {
      setLocalState(dom.timelineState, '这里还没有留下可回看的光影。', dom.timelineRetry, false);
      announce('时间线为空');
      return;
    }
    timeline.items.forEach((item) => {
      dom.timelineList.append(renderItem(item, 'today-timeline-item'));
    });
    announce('时间线已经展开');
  }

  function handleDisclosure(event) {
    const resourceButton = event.target.closest('button[data-resource-index]');
    if (resourceButton && dom.clusters.contains(resourceButton)) {
      const rawIndex = resourceButton.dataset.resourceIndex;
      const index = /^\d+$/.test(rawIndex || '') ? Number(rawIndex) : -1;
      const entry = resourceEntries[index];
      if (entry) {
        returnTarget = { resource: entry.resource, key: entry.key };
        onResourceSelect(entry.resource, entry.key);
      }
      return;
    }
    const button = event.target.closest('button[data-category]');
    if (!button || !dom.clusters.contains(button)) return;
    const name = button.dataset.category;
    expanded.has(name) ? expanded.delete(name) : expanded.add(name);
    const open = expanded.has(name);
    const section = button.closest('.today-cluster');
    const folded = button.dataset.folded === 'true';
    section?.querySelectorAll(`[data-disclosure-item="${name}"]`)
      .forEach((node) => { node.hidden = !open; });
    if (folded) {
      const heading = section?.querySelector('.today-cluster-title');
      const list = section?.querySelector('.today-item-list');
      if (heading) heading.hidden = !open;
      if (list) list.hidden = !open;
    }
    section?.classList.toggle('is-expanded', open);
    button.setAttribute('aria-expanded', String(open));
    button.textContent = open
      ? '收起'
      : folded ? `+${button.dataset.hiddenCount} 已收集光影`
        : `+${button.dataset.hiddenCount} 展开`;
  }

  dom.clusters.addEventListener('click', handleDisclosure);
  dom.resourceNavToggle?.addEventListener('click', () => {
    resourcesExpanded = !resourcesExpanded;
    renderResourceNav(true);
  });

  function render(lifeFlow) {
    const showToday = lifeFlow?.view === 'today';
    const showTimeline = lifeFlow?.view === 'timeline';
    if (dom.dialog) {
      const resource = lifeFlow?.view?.startsWith('task')
        ? lifeFlow.tasks
        : lifeFlow?.view?.startsWith('routine') ? lifeFlow.routines
          : lifeFlow?.view?.startsWith('activity') ? lifeFlow.activities
            : lifeFlow?.view?.startsWith('diary') ? lifeFlow.diaries
              : lifeFlow?.view?.startsWith('reminder') ? lifeFlow.reminders
                : lifeFlow?.view?.startsWith('calendar') ? lifeFlow.calendarEvents : null;
      dom.dialog.dataset.todayStatus = showTimeline
        ? lifeFlow.timeline.status
        : resource?.status || lifeFlow.today.status;
    }
    dom.todayPanel.hidden = !showToday;
    dom.todayPanel.setAttribute('aria-hidden', String(!showToday));
    dom.timelinePanel.hidden = !showTimeline;
    dom.timelinePanel.setAttribute('aria-hidden', String(!showTimeline));
    renderResourceNav(showToday);
    const date = safeDate(lifeFlow?.today?.data?.date);
    if (date) {
      dom.date.dateTime = lifeFlow.today.data.date;
      dom.date.textContent = dateFormatter.format(date);
    }
    if (showTimeline) renderTimeline(lifeFlow.timeline);
    else if (showToday) renderToday(lifeFlow.today);
  }

  return Object.freeze({
    render,
    focusReturn() {
      const match = returnTarget
        ? resourceEntries.find((entry) => (
          entry.resource === returnTarget.resource && entry.key === returnTarget.key
        ))
        : null;
      const fallback = returnTarget?.resource === 'routines' ? dom.routinesOpen
        : returnTarget?.resource === 'activities' ? dom.activitiesOpen
          : returnTarget?.resource === 'diaries' ? dom.diariesOpen
            : returnTarget?.resource === 'reminders' ? dom.remindersOpen
              : returnTarget?.resource === 'calendarEvents' ? dom.calendarOpen : dom.tasksOpen;
      requestAnimationFrame(() => (match?.node || fallback)?.focus({ preventScroll: true }));
      returnTarget = null;
    },
    destroy() {
      dom.clusters.removeEventListener('click', handleDisclosure);
      expanded.clear();
    },
  });
}
