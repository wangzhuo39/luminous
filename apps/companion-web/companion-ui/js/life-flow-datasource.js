import { lifeFlowApi } from './services/life-flow-api.js';
import {
  adaptTodayResponse,
  adaptTimelineResponse,
  adaptTaskResponse,
  adaptTaskListResponse,
  adaptTaskStepResponse,
  adaptRoutineResponse,
  adaptRoutineListResponse,
  adaptRoutineCheckinResponse,
  adaptActivityResponse,
  adaptActivityListResponse,
  adaptDiaryEntryResponse,
  adaptDiaryEntryListResponse,
} from './adapters/life-flow-adapter.js';
import {
  adaptReminderResponse,
  adaptReminderListResponse,
  adaptCalendarEventResponse,
  adaptCalendarEventListResponse,
  adaptActionPreviewResponse,
  adaptConfirmedActionResponse,
} from './adapters/scheduling-action-adapter.js';

export function createApiLifeFlowDataSource({
  api = lifeFlowApi,
  nativeBridge = null,
} = {}) {
  const one = (method, adapter) => (params) => api[method](params).then(adapter);
  const list = (method, adapter) => (params) => api[method](params)
    .then((raw) => adapter(raw).items);
  const syncReminder = async (reminder) => {
    const bridge = nativeBridge || (typeof window === 'undefined' ? null : window.LuminousNative);
    try { await bridge?.syncReminder?.(reminder); } catch { /* Server state remains authoritative. */ }
    return reminder;
  };
  const reminderOne = (method) => (params) => api[method](params)
    .then(adaptReminderResponse)
    .then(syncReminder);
  const reminderList = (params) => api.loadReminders(params)
    .then((raw) => adaptReminderListResponse(raw).items)
    .then(async (items) => {
      await Promise.all(items.map(syncReminder));
      return items;
    });

  return Object.freeze({
    loadToday: one('loadToday', adaptTodayResponse),
    loadTimeline: list('loadTimeline', adaptTimelineResponse),

    loadTasks: list('loadTasks', adaptTaskListResponse),
    createTask: one('createTask', adaptTaskResponse),
    updateTask: one('updateTask', adaptTaskResponse),
    addTaskStep: one('addTaskStep', adaptTaskStepResponse),
    updateTaskStep: one('updateTaskStep', adaptTaskStepResponse),
    transitionTask: one('transitionTask', adaptTaskResponse),
    archiveTask: one('archiveTask', adaptTaskResponse),

    loadRoutines: list('loadRoutines', adaptRoutineListResponse),
    createRoutine: one('createRoutine', adaptRoutineResponse),
    updateRoutine: one('updateRoutine', adaptRoutineResponse),
    checkinRoutine: one('checkinRoutine', adaptRoutineCheckinResponse),
    deactivateRoutine: one('deactivateRoutine', adaptRoutineResponse),

    loadActivities: list('loadActivities', adaptActivityListResponse),
    createActivity: one('createActivity', adaptActivityResponse),
    transitionActivity: one('transitionActivity', adaptActivityResponse),

    loadDiaryEntries: list('loadDiaryEntries', adaptDiaryEntryListResponse),
    createDiaryEntry: one('createDiaryEntry', adaptDiaryEntryResponse),
    draftDiaryEntry: one('draftDiaryEntry', adaptDiaryEntryResponse),
    updateDiaryEntry: one('updateDiaryEntry', adaptDiaryEntryResponse),
    removeDiaryEntry: one('removeDiaryEntry', adaptDiaryEntryResponse),

    loadReminders: reminderList,
    createReminder: reminderOne('createReminder'),
    updateReminder: reminderOne('updateReminder'),
    transitionReminder: reminderOne('transitionReminder'),

    loadCalendarEvents: list('loadCalendarEvents', adaptCalendarEventListResponse),
    createCalendarEvent: one('createCalendarEvent', adaptCalendarEventResponse),
    updateCalendarEvent: one('updateCalendarEvent', adaptCalendarEventResponse),
    removeCalendarEvent: one('removeCalendarEvent', adaptCalendarEventResponse),

    previewAction: ({ proposal, lookup, signal }) => api
      .previewAction({ proposal, signal })
      .then((raw) => adaptActionPreviewResponse(raw, lookup)),
    confirmAction: ({ preview, signal }) => api
      .confirmAction({ preview, signal })
      .then((raw) => adaptConfirmedActionResponse(raw, preview.action)),
  });
}

export const apiLifeFlowDataSource = createApiLifeFlowDataSource();
export default apiLifeFlowDataSource;
