const freeze = Object.freeze;

const ACTIONS = {
  task: {
    open: ['start', 'block', 'complete', 'cancel', 'archive'],
    in_progress: ['block', 'complete', 'cancel', 'archive'],
    blocked: ['start', 'complete', 'cancel', 'archive'],
    completed: ['archive'],
    cancelled: ['archive'],
  },
  activity: {
    planned: ['start', 'cancel'],
    active: ['pause', 'complete', 'cancel'],
    paused: ['resume', 'complete', 'cancel'],
  },
  reminder: {
    scheduled: ['complete', 'snooze', 'cancel', 'edit'],
    due: ['complete', 'snooze', 'cancel', 'edit'],
    snoozed: ['complete', 'snooze', 'cancel', 'edit'],
  },
  diary: { draft: ['edit', 'remove'], saved: ['edit', 'remove'] },
  calendar: { active: ['edit', 'remove'] },
};

/**
 * Selects the stable, bounded Today categories without mutating input VMs.
 * @param {object} todayViewModel
 */
export function foldTodayCategories(todayViewModel) {
  const viewModel = todayViewModel && typeof todayViewModel === 'object'
    ? todayViewModel
    : {};
  const list = (key) => (Array.isArray(viewModel[key]) ? viewModel[key] : []);
  const raw = {
    activeActivities: list('activeActivities'),
    calendarEvents: list('calendarEvents'),
    intentions: [...list('dueTasks'), ...list('routines')],
    carriedOver: [...list('overdueTasks'), ...list('openTasks')],
    completedTasks: list('completedTasks'),
  };
  const names = [
    'activeActivities', 'calendarEvents', 'intentions', 'carriedOver', 'completedTasks',
  ];
  const processed = {};

  for (const name of names) {
    const seen = new Set();
    const items = [];
    for (const item of raw[name]) {
      if (!item || typeof item !== 'object' || typeof item.key !== 'string') continue;
      const key = item.key.trim();
      if (!key || seen.has(key)) continue;
      seen.add(key);
      items.push(item);
    }
    processed[name] = items;
  }

  const allFiveNonEmpty = names.every((name) => processed[name].length > 0);
  const category = (name) => freeze({
    name,
    items: freeze(processed[name].slice(0, 3)),
    hiddenCount: Math.max(0, processed[name].length - 3),
  });
  const visibleCategories = names
    .filter((name) => processed[name].length > 0)
    .filter((name) => !(allFiveNonEmpty && name === 'completedTasks'))
    .map(category);
  const foldedCompleted = allFiveNonEmpty
    ? freeze({
      items: freeze([...processed.completedTasks]),
      hiddenCount: processed.completedTasks.length,
    })
    : null;

  return freeze({ visibleCategories: freeze(visibleCategories), foldedCompleted });
}

const actionsFor = (resource, status) => freeze([...(ACTIONS[resource][status] || [])]);

/** @param {string} status */
export function getTaskActions(status) { return actionsFor('task', status); }
/** @param {string} status */
export function getActivityActions(status) { return actionsFor('activity', status); }
/** @param {string} status */
export function getReminderActions(status) { return actionsFor('reminder', status); }
/** @param {boolean} active */
export function getRoutineActions(active) {
  if (active === true) return freeze(['edit', 'checkin', 'deactivate']);
  if (active === false) return freeze(['edit']);
  return freeze([]);
}
/** @param {string} status */
export function getDiaryActions(status) { return actionsFor('diary', status); }
/** @param {string} status */
export function getCalendarActions(status) { return actionsFor('calendar', status); }
