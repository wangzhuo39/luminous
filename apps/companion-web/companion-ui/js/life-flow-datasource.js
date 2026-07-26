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

export function createApiLifeFlowDataSource({ api = lifeFlowApi } = {}) {
  const one = (method, adapter) => (params) => api[method](params).then(adapter);
  const list = (method, adapter) => (params) => api[method](params)
    .then((raw) => adapter(raw).items);

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

    loadReminders: list('loadReminders', adaptReminderListResponse),
    createReminder: one('createReminder', adaptReminderResponse),
    updateReminder: one('updateReminder', adaptReminderResponse),
    transitionReminder: one('transitionReminder', adaptReminderResponse),

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
