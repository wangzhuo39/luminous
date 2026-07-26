import { AppError } from '../shared/errors.js';
import {
  adaptActivityListResponse,
  adaptActivityResponse,
  adaptDiaryEntryListResponse,
  adaptDiaryEntryResponse,
  adaptRoutineCheckinResponse,
  adaptRoutineListResponse,
  adaptRoutineResponse,
  adaptTaskListResponse,
  adaptTaskResponse,
  adaptTaskStepResponse,
  adaptTimelineResponse,
  adaptTodayResponse,
} from './life-flow-adapter.js';
import {
  adaptActionPreviewResponse,
  adaptCalendarEventListResponse,
  adaptCalendarEventResponse,
  adaptReminderListResponse,
  adaptReminderResponse,
} from './scheduling-action-adapter.js';

function copyList(value) {
  return Array.isArray(value) ? JSON.parse(JSON.stringify(value)) : [];
}

function localDate(value) {
  const pad = (number) => String(number).padStart(2, '0');
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`;
}

function boundedLimit(value, fallback = 100) {
  return Number.isInteger(value) && value > 0 ? Math.min(value, 500) : fallback;
}

function requireInput(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    throw new AppError('validation');
  }
  return input;
}

function requireTitle(input) {
  requireInput(input);
  if (typeof input.title !== 'string' || !input.title.trim()) {
    throw new AppError('validation');
  }
  return input.title;
}

export function createFixtureLifeFlowDataSource({ seed = {}, now = () => new Date() } = {}) {
  const store = {
    tasks: copyList(seed.tasks),
    routines: copyList(seed.routines),
    activities: copyList(seed.activities),
    diaryEntries: copyList(seed.diaryEntries),
    reminders: copyList(seed.reminders),
    calendarEvents: copyList(seed.calendarEvents),
    timeline: copyList(seed.timeline),
  };
  const counters = new Map();
  const nextKey = (kind) => {
    const next = (counters.get(kind) ?? 0) + 1;
    counters.set(kind, next);
    return `fixture-${kind}-${next}`;
  };
  const instant = () => {
    const value = now();
    if (!(value instanceof Date) || Number.isNaN(value.getTime())) {
      throw new AppError('validation');
    }
    return value.toISOString();
  };
  const find = (collection, keyName, key) => {
    if (typeof key !== 'string' || !key.trim()) throw new AppError('validation');
    const item = collection.find((candidate) => candidate[keyName] === key);
    if (!item) throw new AppError('not-found');
    return item;
  };

  const dataSource = {
    async loadToday({ date } = {}) {
      const day = date || localDate(now());
      const openTasks = store.tasks.filter((task) => (
        ['open', 'in_progress', 'blocked'].includes(task.status)
      ));
      return adaptTodayResponse({
        date: day,
        active_activities: store.activities.filter((activity) => activity.status === 'active'),
        calendar_events: store.calendarEvents.filter((event) => (
          event.status !== 'deleted' && String(event.starts_at ?? '').slice(0, 10) === day
        )),
        due_tasks: openTasks.filter((task) => String(task.due_at ?? '').slice(0, 10) === day),
        routines: store.routines.filter((routine) => routine.active === true),
        overdue_tasks: openTasks.filter((task) => (
          task.due_at && String(task.due_at).slice(0, 10) < day
        )),
        open_tasks: openTasks,
        completed_tasks: store.tasks.filter((task) => (
          task.status === 'completed' && String(task.completed_at ?? '').slice(0, 10) === day
        )),
      });
    },

    async loadTimeline({ from, to, kind, limit } = {}) {
      const items = store.timeline
        .filter((item) => !from || String(item.occurred_at ?? '').slice(0, 10) >= from)
        .filter((item) => !to || String(item.occurred_at ?? '').slice(0, 10) <= to)
        .filter((item) => !kind || item.kind === kind)
        .sort((left, right) => String(right.occurred_at).localeCompare(String(left.occurred_at)))
        .slice(0, boundedLimit(limit, 200));
      return adaptTimelineResponse({ items }).items;
    },

    async loadTasks({ status, limit } = {}) {
      const items = store.tasks
        .filter((task) => !status || task.status === status)
        .slice(0, boundedLimit(limit));
      return adaptTaskListResponse({ items }).items;
    },
    async createTask({ input } = {}) {
      const title = requireTitle(input);
      const task = {
        task_id: nextKey('task'),
        title,
        description: typeof input.description === 'string' ? input.description : '',
        status: 'open',
        due_at: typeof input.due_at === 'string' ? input.due_at : '',
        priority: ['low', 'normal', 'high'].includes(input.priority) ? input.priority : 'normal',
        steps: [],
      };
      store.tasks.push(task);
      return adaptTaskResponse({ task });
    },
    async updateTask({ key, changes } = {}) {
      const task = find(store.tasks, 'task_id', key);
      requireInput(changes);
      for (const field of ['title', 'description', 'due_at', 'priority']) {
        if (field in changes) task[field] = changes[field];
      }
      return adaptTaskResponse({ task });
    },
    async addTaskStep({ taskKey, input } = {}) {
      const task = find(store.tasks, 'task_id', taskKey);
      const title = requireTitle(input);
      const step = {
        step_id: nextKey('step'), title, position: task.steps.length, status: 'open',
      };
      task.steps.push(step);
      return adaptTaskStepResponse({ step });
    },
    async updateTaskStep({ taskKey, stepKey, changes } = {}) {
      const task = find(store.tasks, 'task_id', taskKey);
      const step = find(task.steps, 'step_id', stepKey);
      requireInput(changes);
      if ('title' in changes) step.title = changes.title;
      if ('status' in changes) {
        if (!['open', 'completed', 'cancelled'].includes(changes.status)) {
          throw new AppError('validation');
        }
        step.status = changes.status;
        step.completed_at = changes.status === 'completed' ? instant() : '';
      }
      return adaptTaskStepResponse({ step });
    },
    async transitionTask({ key, action } = {}) {
      const status = {
        start: 'in_progress', complete: 'completed', block: 'blocked', cancel: 'cancelled',
      }[action];
      if (!status) throw new AppError('validation');
      const task = find(store.tasks, 'task_id', key);
      task.status = status;
      if (status === 'completed') task.completed_at = instant();
      return adaptTaskResponse({ task });
    },
    async archiveTask({ key } = {}) {
      const task = find(store.tasks, 'task_id', key);
      task.status = 'archived';
      return adaptTaskResponse({ task });
    },

    async loadRoutines({ activeOnly, limit } = {}) {
      const items = store.routines
        .filter((routine) => activeOnly !== true || routine.active === true)
        .slice(0, boundedLimit(limit));
      return adaptRoutineListResponse({ items }).items;
    },
    async createRoutine({ input } = {}) {
      const title = requireTitle(input);
      const routine = {
        routine_id: nextKey('routine'),
        title,
        schedule: ['daily', 'weekly'].includes(input.schedule) ? input.schedule : 'daily',
        active: true,
        reminder_policy: ['none', 'remind'].includes(input.reminder_policy)
          ? input.reminder_policy : 'none',
      };
      store.routines.push(routine);
      return adaptRoutineResponse({ routine });
    },
    async updateRoutine({ key, changes } = {}) {
      const routine = find(store.routines, 'routine_id', key);
      requireInput(changes);
      for (const field of ['title', 'schedule', 'active', 'reminder_policy']) {
        if (field in changes) routine[field] = changes[field];
      }
      return adaptRoutineResponse({ routine });
    },
    async checkinRoutine({ key, input = {} } = {}) {
      find(store.routines, 'routine_id', key);
      const checkin = {
        checkin_id: nextKey('checkin'),
        period_key: localDate(now()),
        status: 'completed',
        note: typeof input.note === 'string' ? input.note : '',
        occurred_at: instant(),
      };
      return adaptRoutineCheckinResponse({ checkin });
    },
    async deactivateRoutine({ key } = {}) {
      const routine = find(store.routines, 'routine_id', key);
      routine.active = false;
      return adaptRoutineResponse({ routine });
    },

    async loadActivities({ status, limit } = {}) {
      const items = store.activities
        .filter((activity) => !status || activity.status === status)
        .slice(0, boundedLimit(limit));
      return adaptActivityListResponse({ items }).items;
    },
    async createActivity({ input } = {}) {
      const title = requireTitle(input);
      const allowedKinds = new Set(['focus', 'checkin', 'planning', 'reflection']);
      const kind = input.kind === undefined ? 'focus' : input.kind;
      if (!allowedKinds.has(kind)) throw new AppError('validation');
      const activity = {
        session_id: nextKey('activity'),
        title,
        kind,
        status: 'planned',
        started_at: '',
        ended_at: '',
        summary: typeof input.summary === 'string' ? input.summary : '',
      };
      store.activities.push(activity);
      return adaptActivityResponse({ activity });
    },
    async transitionActivity({ key, action } = {}) {
      const allowed = {
        planned: new Set(['start', 'cancel']),
        active: new Set(['pause', 'complete', 'cancel']),
        paused: new Set(['resume', 'complete', 'cancel']),
      };
      const status = {
        start: 'active', pause: 'paused', resume: 'active',
        complete: 'completed', cancel: 'cancelled',
      }[action];
      if (!status) throw new AppError('validation');
      const activity = find(store.activities, 'session_id', key);
      if (!allowed[activity.status]?.has(action)) throw new AppError('validation');
      activity.status = status;
      if (action === 'start' && !activity.started_at) activity.started_at = instant();
      if (action === 'complete' || action === 'cancel') activity.ended_at = instant();
      return adaptActivityResponse({ activity });
    },

    async loadDiaryEntries({ date, limit } = {}) {
      const items = store.diaryEntries
        .filter((entry) => entry.status !== 'deleted')
        .filter((entry) => !date || entry.date === date)
        .slice(0, boundedLimit(limit));
      return adaptDiaryEntryListResponse({ items }).items;
    },
    async createDiaryEntry({ input } = {}) {
      requireInput(input);
      if (typeof input.title !== 'string' || !input.title.trim()) throw new AppError('validation');
      if (typeof input.body !== 'string' || !input.body.trim()) throw new AppError('validation');
      if (typeof input.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(input.date)) {
        throw new AppError('validation');
      }
      if (input.status !== 'saved') throw new AppError('validation');
      const entry = {
        entry_id: nextKey('diary-entry'),
        title: input.title,
        body: input.body,
        date: input.date,
        status: 'saved',
        updated_at: instant(),
      };
      store.diaryEntries.push(entry);
      return adaptDiaryEntryResponse({ diary_entry: entry });
    },
    async draftDiaryEntry({ date } = {}) {
      const targetDate = date || localDate(now());
      let entry = store.diaryEntries.find((candidate) => (
        candidate.date === targetDate && candidate.status === 'draft'
      ));
      if (!entry) {
        entry = {
          entry_id: nextKey('diary-entry'),
          title: '日记草稿',
          body: '',
          date: targetDate,
          status: 'draft',
          updated_at: instant(),
        };
        store.diaryEntries.push(entry);
      }
      return adaptDiaryEntryResponse({ diary_entry: entry });
    },
    async updateDiaryEntry({ key, changes } = {}) {
      const entry = find(store.diaryEntries, 'entry_id', key);
      requireInput(changes);
      for (const field of ['date', 'title', 'body', 'status']) {
        if (field in changes) entry[field] = changes[field];
      }
      entry.updated_at = instant();
      return adaptDiaryEntryResponse({ diary_entry: entry });
    },
    async removeDiaryEntry({ key } = {}) {
      const entry = find(store.diaryEntries, 'entry_id', key);
      entry.status = 'deleted';
      entry.updated_at = instant();
      return adaptDiaryEntryResponse({ diary_entry: entry });
    },

    async loadReminders({ status, limit } = {}) {
      const items = store.reminders
        .filter((reminder) => !status || reminder.status === status)
        .slice(0, boundedLimit(limit));
      return adaptReminderListResponse({ items }).items;
    },
    async createReminder({ input } = {}) {
      const title = requireTitle(input);
      if (typeof input.due_at !== 'string' || !input.due_at.trim()) {
        throw new AppError('validation');
      }
      const reminder = {
        reminder_id: nextKey('reminder'),
        title,
        description: typeof input.description === 'string' ? input.description : '',
        due_at: input.due_at,
        timezone_name: typeof input.timezone_name === 'string' ? input.timezone_name : 'UTC',
        recurrence: typeof input.recurrence === 'string' ? input.recurrence : '',
        status: 'scheduled',
      };
      store.reminders.push(reminder);
      return adaptReminderResponse({ reminder });
    },
    async updateReminder({ key, changes } = {}) {
      const reminder = find(store.reminders, 'reminder_id', key);
      requireInput(changes);
      for (const field of [
        'title', 'description', 'due_at', 'timezone_name', 'recurrence', 'status',
      ]) {
        if (field in changes) reminder[field] = changes[field];
      }
      return adaptReminderResponse({ reminder });
    },
    async transitionReminder({ key, action, input = {} } = {}) {
      const reminder = find(store.reminders, 'reminder_id', key);
      if (action === 'snooze') {
        requireInput(input);
        if (typeof input.due_at !== 'string' || !input.due_at.trim()) {
          throw new AppError('validation');
        }
        reminder.status = 'snoozed';
        reminder.due_at = input.due_at;
      } else if (action === 'complete') {
        reminder.status = 'completed';
      } else if (action === 'cancel') {
        reminder.status = 'cancelled';
      } else {
        throw new AppError('validation');
      }
      return adaptReminderResponse({ reminder });
    },

    async loadCalendarEvents({ limit } = {}) {
      const items = store.calendarEvents
        .filter((event) => event.status !== 'deleted')
        .slice(0, boundedLimit(limit));
      return adaptCalendarEventListResponse({ items }).items;
    },
    async createCalendarEvent({ input } = {}) {
      const title = requireTitle(input);
      if (typeof input.starts_at !== 'string' || !input.starts_at.trim()) {
        throw new AppError('validation');
      }
      const calendarEvent = {
        event_id: nextKey('calendar-event'),
        title,
        starts_at: input.starts_at,
        ends_at: typeof input.ends_at === 'string' ? input.ends_at : '',
        all_day: typeof input.all_day === 'boolean' ? input.all_day : false,
        timezone_name: typeof input.timezone_name === 'string' ? input.timezone_name : 'UTC',
        status: 'active',
      };
      store.calendarEvents.push(calendarEvent);
      return adaptCalendarEventResponse({ calendar_event: calendarEvent });
    },
    async updateCalendarEvent({ key, changes } = {}) {
      const calendarEvent = find(store.calendarEvents, 'event_id', key);
      requireInput(changes);
      for (const field of [
        'title', 'starts_at', 'ends_at', 'all_day', 'timezone_name', 'status',
      ]) {
        if (field in changes) calendarEvent[field] = changes[field];
      }
      return adaptCalendarEventResponse({ calendar_event: calendarEvent });
    },
    async removeCalendarEvent({ key } = {}) {
      const calendarEvent = find(store.calendarEvents, 'event_id', key);
      calendarEvent.status = 'deleted';
      return adaptCalendarEventResponse({ calendar_event: calendarEvent });
    },

    async previewAction({ proposal, lookup = {} } = {}) {
      requireInput(proposal);
      const actions = new Set([
        'create_task', 'complete_task', 'start_focus_session',
        'checkin_routine', 'draft_diary',
      ]);
      if (!actions.has(proposal.action)) throw new AppError('validation');
      const payload = requireInput(proposal.payload);
      return adaptActionPreviewResponse({
        preview_id: nextKey('preview'),
        action: proposal.action,
        payload: JSON.parse(JSON.stringify(payload)),
        confirmation_required: true,
      }, lookup);
    },
    async confirmAction({ preview } = {}) {
      requireInput(preview);
      const snapshot = requireInput(preview.requestSnapshot);
      if (
        typeof preview.previewKey !== 'string'
        || !preview.previewKey.trim()
        || !Array.isArray(preview.summaryLines)
      ) throw new AppError('validation');
      if (preview.action === 'create_task') {
        return dataSource.createTask({ input: snapshot });
      }
      if (preview.action === 'complete_task') {
        return dataSource.transitionTask({ key: snapshot.task_id, action: 'complete' });
      }
      if (preview.action === 'start_focus_session') {
        const activity = await dataSource.createActivity({ input: snapshot });
        return dataSource.transitionActivity({ key: activity.key, action: 'start' });
      }
      if (preview.action === 'checkin_routine') {
        const { routine_id: routineKey, ...input } = snapshot;
        return dataSource.checkinRoutine({ key: routineKey, input });
      }
      if (preview.action === 'draft_diary') {
        return dataSource.draftDiaryEntry({ date: snapshot.date });
      }
      throw new AppError('validation');
    },
  };

  return Object.freeze(dataSource);
}

export const fixtureLifeFlowDataSource = createFixtureLifeFlowDataSource();
export default fixtureLifeFlowDataSource;
