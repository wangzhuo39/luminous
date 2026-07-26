import { loadInitialViewModels } from './fixture-adapter.js';
import {
  commitConfirmedActionResult,
  getState,
  initializeState,
  setActiveSpace,
  setPresentationState,
} from './app-state.js';
import { sendChatMessage } from './adapters/api-adapter.js';
import { initConversation } from './conversation.js';
import { initCoreRuntime, resolveRuntimeMode } from './core-runtime.js';
import { initSceneParallax } from './scene-parallax.js';
import { initSceneEnvironment } from './scene-environment.js';
import { todayFixture } from './fixtures.js';
import { createFixtureLifeFlowDataSource } from './adapters/life-flow-fixture-adapter.js';
import { apiLifeFlowDataSource } from './life-flow-datasource.js';
import { initLifeFlow } from './features/life-flow/life-flow-controller.js';
import { initActionProposal } from './features/action-proposal/action-controller.js';
import { createActionView } from './features/action-proposal/action-view.js';
import { createActivityView } from './features/life-flow/activity-view.js';
import { createDiaryView } from './features/life-flow/diary-view.js';
import { createCalendarView } from './features/life-flow/calendar-view.js';
import { createReminderView } from './features/life-flow/reminder-view.js';
import { createRoutineView } from './features/life-flow/routine-view.js';
import { createTaskView } from './features/life-flow/task-view.js';
import { createTodayView } from './features/life-flow/today-view.js';
import { initOverlays } from './overlays.js';
import { initPresentation } from './presentation.js';
import { silentSpacesApi } from './services/silent-spaces-api.js';
import { initSilentSpaces } from './features/silent-spaces/silent-spaces-controller.js';
import { createSilentSpacesFixtureDataSource } from './features/silent-spaces/silent-spaces-fixture.js';
import {
  clearRecoverableDraft,
  loadRecoveredDraft,
  saveRecoverableDraft,
} from './features/productization/draft-recovery.js';
import { initPwaExperience } from './features/productization/pwa-controller.js';
import { initSpaceRouter } from './features/productization/space-router.js';

const dom = {
  body: document.body,
  scene: document.querySelector('#luminous-scene'),
  memoryCrystalField: document.querySelector('[data-hook="memory-crystal-field"]'),
  companionFigure: document.querySelector('[data-hook="companion-figure"]'),
  dialogueStream: document.querySelector('[data-hook="dialogue-stream"]'),
  inputForm: document.querySelector('[data-hook="input-form"]'),
  chatInput: document.querySelector('[data-hook="chat-input"]'),
  draftNotice: document.querySelector('[data-hook="draft-notice"]'),
  sendButton: document.querySelector('[data-hook="send-button"]'),
  statusNode: document.querySelector('[data-hook="a11y-status"]'),
  chatFeedback: document.querySelector('[data-hook="chat-feedback"]'),
  action: {
    card: document.querySelector('[data-hook="action-card"]'),
    eyebrow: document.querySelector('[data-hook="action-eyebrow"]'),
    title: document.querySelector('[data-hook="action-title"]'),
    summary: document.querySelector('[data-hook="action-summary"]'),
    status: document.querySelector('[data-hook="action-status"]'),
    actions: document.querySelector('[data-hook="action-actions"]'),
  },
  portals: {
    today: document.querySelector('#today-portal'),
    outbox: document.querySelector('#outbox-portal'),
    memory: document.querySelector('#memory-portal'),
    privacy: document.querySelector('#privacy-portal'),
  },
  dialogs: {
    today: document.querySelector('#today-overlay'),
    outbox: document.querySelector('#outbox-overlay'),
    memory: document.querySelector('#memory-overlay'),
    privacy: document.querySelector('#privacy-overlay'),
  },
  today: {
    dialog: document.querySelector('#today-overlay'),
    portal: document.querySelector('#today-portal'),
    date: document.querySelector('[data-hook="today-date"]'),
    refresh: document.querySelector('[data-hook="today-refresh"]'),
    status: document.querySelector('[data-hook="today-status"]'),
    todayPanel: document.querySelector('[data-hook="today-panel"]'),
    todayState: document.querySelector('[data-hook="today-local-state"]'),
    todayRetry: document.querySelector('[data-hook="today-retry"]'),
    clusters: document.querySelector('[data-hook="today-clusters"]'),
    timelineReveal: document.querySelector('[data-hook="timeline-reveal"]'),
    timelinePanel: document.querySelector('[data-hook="timeline-panel"]'),
    timelineBack: document.querySelector('[data-hook="timeline-back"]'),
    timelineState: document.querySelector('[data-hook="timeline-local-state"]'),
    timelineList: document.querySelector('[data-hook="timeline-list"]'),
    timelineRetry: document.querySelector('[data-hook="timeline-retry"]'),
    scrollArea: document.querySelector('.today-scroll-area'),
    tasksOpen: document.querySelector('[data-hook="tasks-open"]'),
    routinesOpen: document.querySelector('[data-hook="routines-open"]'),
    activitiesOpen: document.querySelector('[data-hook="activities-open"]'),
    diariesOpen: document.querySelector('[data-hook="diaries-open"]'),
    remindersOpen: document.querySelector('[data-hook="reminders-open"]'),
    calendarOpen: document.querySelector('[data-hook="calendar-open"]'),
    activity: {
      panel: document.querySelector('[data-hook="activity-panel"]'),
      back: document.querySelector('[data-hook="activity-back"]'),
      list: document.querySelector('[data-hook="activity-list"]'),
      listState: document.querySelector('[data-hook="activity-list-state"]'),
      create: document.querySelector('[data-hook="activity-create"]'),
      detail: document.querySelector('[data-hook="activity-detail"]'),
      crystal: document.querySelector('[data-hook="activity-crystal"]'),
      statusActions: document.querySelector('[data-hook="activity-status-actions"]'),
      form: document.querySelector('[data-hook="activity-form"]'),
      title: document.querySelector('[data-hook="activity-title"]'),
      kind: document.querySelector('[data-hook="activity-kind"]'),
      submit: document.querySelector('[data-hook="activity-submit"]'),
      cancelEdit: document.querySelector('[data-hook="activity-cancel-edit"]'),
      error: document.querySelector('[data-hook="activity-error"]'),
    },
    diary: {
      panel: document.querySelector('[data-hook="diary-panel"]'),
      back: document.querySelector('[data-hook="diary-back"]'),
      listState: document.querySelector('[data-hook="diary-list-state"]'),
      list: document.querySelector('[data-hook="diary-list"]'),
      create: document.querySelector('[data-hook="diary-create"]'),
      generate: document.querySelector('[data-hook="diary-generate"]'),
      detail: document.querySelector('[data-hook="diary-detail"]'),
      edit: document.querySelector('[data-hook="diary-edit"]'),
      remove: document.querySelector('[data-hook="diary-remove"]'),
      confirmation: document.querySelector('[data-hook="diary-confirmation"]'),
      form: document.querySelector('[data-hook="diary-form"]'),
      formHeading: document.querySelector('[data-hook="diary-form-heading"]'),
      formCaption: document.querySelector('[data-hook="diary-form-caption"]'),
      title: document.querySelector('[data-hook="diary-title"]'),
      body: document.querySelector('[data-hook="diary-body"]'),
      submit: document.querySelector('[data-hook="diary-submit"]'),
      cancelEdit: document.querySelector('[data-hook="diary-cancel-edit"]'),
      error: document.querySelector('[data-hook="diary-error"]'),
    },
    reminder: {
      panel: document.querySelector('[data-hook="reminder-panel"]'),
      back: document.querySelector('[data-hook="reminder-back"]'),
      listState: document.querySelector('[data-hook="reminder-list-state"]'),
      activeList: document.querySelector('[data-hook="reminder-active-list"]'),
      terminalRegion: document.querySelector('[data-hook="reminder-terminal-region"]'),
      terminalToggle: document.querySelector('[data-hook="reminder-terminal-toggle"]'),
      terminalList: document.querySelector('[data-hook="reminder-terminal-list"]'),
      create: document.querySelector('[data-hook="reminder-create"]'),
      detail: document.querySelector('[data-hook="reminder-detail"]'),
      detailActions: document.querySelector('[data-hook="reminder-detail-actions"]'),
      snoozeForm: document.querySelector('[data-hook="reminder-snooze-form"]'),
      snoozeAt: document.querySelector('[data-hook="reminder-snooze-at"]'),
      snoozeSubmit: document.querySelector('[data-hook="reminder-snooze-submit"]'),
      snoozeDismiss: document.querySelector('[data-hook="reminder-snooze-dismiss"]'),
      confirmation: document.querySelector('[data-hook="reminder-confirmation"]'),
      form: document.querySelector('[data-hook="reminder-form"]'),
      formHeading: document.querySelector('[data-hook="reminder-form-heading"]'),
      title: document.querySelector('[data-hook="reminder-title"]'),
      description: document.querySelector('[data-hook="reminder-description"]'),
      dueAt: document.querySelector('[data-hook="reminder-due-at"]'),
      recurrence: document.querySelector('[data-hook="reminder-recurrence"]'),
      submit: document.querySelector('[data-hook="reminder-submit"]'),
      cancelEdit: document.querySelector('[data-hook="reminder-cancel-edit"]'),
      error: document.querySelector('[data-hook="reminder-error"]'),
    },
    calendar: {
      panel: document.querySelector('[data-hook="calendar-panel"]'),
      back: document.querySelector('[data-hook="calendar-back"]'),
      listState: document.querySelector('[data-hook="calendar-list-state"]'),
      scale: document.querySelector('[data-hook="calendar-scale"]'),
      create: document.querySelector('[data-hook="calendar-create"]'),
      detail: document.querySelector('[data-hook="calendar-detail"]'),
      detailActions: document.querySelector('[data-hook="calendar-detail-actions"]'),
      confirmation: document.querySelector('[data-hook="calendar-confirmation"]'),
      form: document.querySelector('[data-hook="calendar-form"]'),
      formHeading: document.querySelector('[data-hook="calendar-form-heading"]'),
      title: document.querySelector('[data-hook="calendar-title"]'),
      allDay: document.querySelector('[data-hook="calendar-all-day"]'),
      timedFields: document.querySelector('[data-hook="calendar-timed-fields"]'),
      startsAt: document.querySelector('[data-hook="calendar-starts-at"]'),
      endsAt: document.querySelector('[data-hook="calendar-ends-at"]'),
      dateFields: document.querySelector('[data-hook="calendar-date-fields"]'),
      startDate: document.querySelector('[data-hook="calendar-start-date"]'),
      endDate: document.querySelector('[data-hook="calendar-end-date"]'),
      submit: document.querySelector('[data-hook="calendar-submit"]'),
      cancelEdit: document.querySelector('[data-hook="calendar-cancel-edit"]'),
      error: document.querySelector('[data-hook="calendar-error"]'),
    },
    task: {
      panel: document.querySelector('[data-hook="task-panel"]'),
      back: document.querySelector('[data-hook="task-back"]'),
      list: document.querySelector('[data-hook="task-list"]'),
      listState: document.querySelector('[data-hook="task-list-state"]'),
      create: document.querySelector('[data-hook="task-create"]'),
      form: document.querySelector('[data-hook="task-form"]'),
      title: document.querySelector('[data-hook="task-title"]'),
      description: document.querySelector('[data-hook="task-description"]'),
      dueAt: document.querySelector('[data-hook="task-due-at"]'),
      priority: document.querySelector('[data-hook="task-priority"]'),
      submit: document.querySelector('[data-hook="task-submit"]'),
      cancelEdit: document.querySelector('[data-hook="task-cancel-edit"]'),
      detail: document.querySelector('[data-hook="task-detail"]'),
      stepList: document.querySelector('[data-hook="task-step-list"]'),
      stepForm: document.querySelector('[data-hook="task-step-form"]'),
      stepTitle: document.querySelector('[data-hook="task-step-title"]'),
      statusActions: document.querySelector('[data-hook="task-status-actions"]'),
      archive: document.querySelector('[data-hook="task-archive"]'),
      confirmation: document.querySelector('[data-hook="task-confirmation"]'),
      error: document.querySelector('[data-hook="task-error"]'),
    },
    routine: {
      panel: document.querySelector('[data-hook="routine-panel"]'),
      back: document.querySelector('[data-hook="routine-back"]'),
      list: document.querySelector('[data-hook="routine-list"]'),
      listState: document.querySelector('[data-hook="routine-list-state"]'),
      create: document.querySelector('[data-hook="routine-create"]'),
      form: document.querySelector('[data-hook="routine-form"]'),
      title: document.querySelector('[data-hook="routine-title"]'),
      schedule: document.querySelector('[data-hook="routine-schedule"]'),
      reminderPolicy: document.querySelector('[data-hook="routine-reminder-policy"]'),
      submit: document.querySelector('[data-hook="routine-submit"]'),
      cancelEdit: document.querySelector('[data-hook="routine-cancel-edit"]'),
      detail: document.querySelector('[data-hook="routine-detail"]'),
      checkin: document.querySelector('[data-hook="routine-checkin"]'),
      deactivate: document.querySelector('[data-hook="routine-deactivate"]'),
      confirmation: document.querySelector('[data-hook="routine-confirmation"]'),
      error: document.querySelector('[data-hook="routine-error"]'),
    },
  },
  outbox: {
    portal: document.querySelector('[data-hook="outbox-portal"]'),
    unreadCount: document.querySelector('[data-hook="outbox-unread-count"]'),
    list: document.querySelector('[data-hook="outbox-arrivals"]'),
    status: document.querySelector('[data-hook="outbox-status"]'),
    retry: document.querySelector('[data-hook="outbox-retry"]'),
  },
  memory: {
    form: document.querySelector('[data-hook="memory-search-form"]'),
    input: document.querySelector('[data-hook="memory-search-input"]'),
    list: document.querySelector('[data-hook="memory-hits"]'),
    status: document.querySelector('[data-hook="memory-status"]'),
    retry: document.querySelector('[data-hook="memory-retry"]'),
  },
  privacy: {
    form: document.querySelector('[data-hook="privacy-form"]'),
    status: document.querySelector('[data-hook="privacy-status"]'),
    retry: document.querySelector('[data-hook="privacy-retry"]'),
    dnd: document.querySelector('[data-hook="privacy-dnd-status"]'),
    enabled: document.querySelector('[data-hook="privacy-enabled"]'),
    limit: document.querySelector('[data-hook="privacy-limit"]'),
    quietStart: document.querySelector('[data-hook="privacy-quiet-start"]'),
    quietEnd: document.querySelector('[data-hook="privacy-quiet-end"]'),
    save: document.querySelector('[data-hook="privacy-save"]'),
  },
  productization: {
    body: document.body,
    installSection: document.querySelector('[data-hook="install-section"]'),
    installButton: document.querySelector('[data-hook="install-button"]'),
    updateButton: document.querySelector('[data-hook="update-trigger"]'),
    updateText: document.querySelector('[data-hook="update-text"]'),
  },
};

let renderOverlays = () => {};
let renderLifeFlow = () => {};
let renderAction = () => {};
let renderSilentSpaces = () => {};
let renderProductization = () => {};
let silentSpacesSummary = () => ({ memoryCount: 0, outboxUnread: false, dnd: false });
let sceneEnvironment = { update() {}, destroy() {} };
let sceneParallax = { setSuspended() {}, destroy() {} };

function isResourceLifeFlowView(view) {
  return typeof view === 'string' && (
    view === 'tasks' || view.startsWith('task-')
    || view === 'routines' || view.startsWith('routine-')
    || view === 'activities' || view.startsWith('activity-')
    || view === 'diaries' || view.startsWith('diary-')
    || view === 'reminders' || view.startsWith('reminder-')
    || view === 'calendar-events' || view.startsWith('calendar-')
  );
}

function renderActivityPresence(lifeFlowState) {
  const loadedActivities = lifeFlowState.activities?.status === 'ready'
    ? lifeFlowState.activities.items
    : null;
  const hasKnownPaused = loadedActivities?.some((item) => item.status === 'paused') === true;
  const hasKnownActive = loadedActivities?.some((item) => item.status === 'active') === true;
  const hasTodayActive = lifeFlowState.today?.data?.activeActivities?.length > 0;
  dom.body.dataset.activityPresence = hasKnownPaused
    ? 'paused'
    : hasKnownActive || hasTodayActive ? 'active' : 'none';
  return dom.body.dataset.activityPresence;
}

function renderScene(viewModel) {
  if (dom.companionFigure) {
    dom.companionFigure.setAttribute('aria-label', viewModel.caption);
  }
  dom.body.dataset.tone = viewModel.tone;
}

function renderConversation(viewModel, draft) {
  if (dom.dialogueStream) {
    const fragment = document.createDocumentFragment();
    viewModel.messages.forEach((message) => {
      const messageElement = document.createElement('div');
      messageElement.className = `message ${message.role}-message`;
      const paragraph = document.createElement('p');
      paragraph.textContent = message.text;
      messageElement.appendChild(paragraph);
      fragment.appendChild(messageElement);
    });
    dom.dialogueStream.replaceChildren(fragment);
  }
  if (dom.chatInput && dom.chatInput.value !== draft) {
    dom.chatInput.value = draft;
  }
}

function renderOutbox(viewModel) {
  if (dom.outbox.unreadCount) {
    dom.outbox.unreadCount.textContent = viewModel.unreadCount > 0 ? String(viewModel.unreadCount) : '';
  }
  if (dom.outbox.portal) {
    dom.outbox.portal.classList.toggle('has-unread', viewModel.unreadCount > 0);
  }
  if (dom.outbox.arrivals) {
    const fragment = document.createDocumentFragment();
    viewModel.arrivals.forEach((item) => {
      const listItem = document.createElement('li');
      const heading = document.createElement('h3');
      heading.textContent = item.title;
      const paragraph = document.createElement('p');
      paragraph.textContent = item.snippet;
      listItem.append(heading, paragraph);
      fragment.appendChild(listItem);
    });
    dom.outbox.arrivals.replaceChildren(fragment);
  }
}

function renderMemoryPrivacy(viewModel) {
  if (dom.memory.prompt) {
    dom.memory.prompt.textContent = viewModel.memoryPrompt;
  }
  if (dom.privacy.caption) {
    dom.privacy.caption.textContent = viewModel.privacyCaption;
  }
  if (dom.privacy.status) {
    dom.privacy.status.textContent = viewModel.boundaryStatus;
  }
}

function renderPresentation(presentation) {
  dom.body.dataset.reducedMotion = String(presentation.isReducedMotion);
  dom.body.dataset.keyboardVisible = String(presentation.isKeyboardVisible);
}

function renderRuntime(current) {
  const { appStatus, appError, conversation, runtimeMode } = current;
  dom.body.dataset.appStatus = appStatus;
  dom.inputForm.dataset.chatStatus = conversation.chatStatus;
  if (conversation.chatError?.kind) {
    dom.inputForm.dataset.errorKind = conversation.chatError.kind;
  } else {
    delete dom.inputForm.dataset.errorKind;
  }

  if (dom.chatFeedback) {
    dom.chatFeedback.textContent = conversation.chatError?.message ?? '';
  }
  const networkOffline = appStatus === 'offline'
    || dom.body.dataset.network === 'offline'
    || navigator.onLine === false;
  const readyToSend = (runtimeMode === 'fixture' || appStatus === 'ready') && !networkOffline;
  const isSubmitting = conversation.chatStatus === 'submitting';
  const hasDraft = conversation.draft.trim().length > 0;
  dom.chatInput.readOnly = isSubmitting;
  dom.chatInput.placeholder = appStatus === 'offline' || networkOffline
    ? '当前没有风，信笺暂时无法寄出...'
    : '触碰水面...';
  if (dom.dialogueStream) {
    dom.dialogueStream.hidden = networkOffline;
    dom.dialogueStream.setAttribute('aria-hidden', String(networkOffline));
  }
  dom.sendButton.disabled = !readyToSend || isSubmitting || !hasDraft;
  dom.sendButton.setAttribute(
    'aria-label',
    conversation.chatStatus === 'error' && conversation.chatError?.retryable ? '重试发送' : '发送',
  );
}

function render() {
  const current = getState();
  if (!current.viewModels) {
    return;
  }
  renderScene(current.viewModels.scene);
  renderConversation(current.viewModels.conversation, current.conversation.draft);
  renderLifeFlow(current.lifeFlow);
  renderAction();
  renderSilentSpaces();
  renderProductization(current);
  renderOverlays(current.activeSpace);
  const quietSummary = silentSpacesSummary();
  sceneEnvironment.update({
    tone: current.viewModels.scene.tone,
    activityPresence: dom.body.dataset.activityPresence,
    memoryCount: quietSummary.memoryCount,
    outboxUnread: quietSummary.outboxUnread || current.viewModels.outbox.unreadCount > 0,
    dnd: quietSummary.dnd,
    activeSpace: current.activeSpace,
  });
  sceneParallax.setSuspended(current.activeSpace !== null);
  renderPresentation(current.presentation);
  renderRuntime(current);
}

function main() {
  const initialViewModels = loadInitialViewModels();
  const runtimeMode = resolveRuntimeMode(window.location);
  let draftStorage = null;
  try { draftStorage = window.sessionStorage; } catch { /* Privacy mode can deny storage. */ }
  const recoveredDraft = loadRecoveredDraft(draftStorage);
  initializeState(initialViewModels, { runtimeMode, initialDraft: recoveredDraft?.text ?? '' });
  if (dom.draftNotice) dom.draftNotice.hidden = !recoveredDraft;
  const spaceRouter = initSpaceRouter(window, { setSpace: setActiveSpace, onStateChange: render });
  spaceRouter.applyInitial();
  renderOverlays = initOverlays(dom, render, { onSpaceChange: (space) => spaceRouter.navigate(space) });
  sceneParallax = initSceneParallax(dom.scene, dom.body);
  sceneEnvironment = initSceneEnvironment({
    scene: dom.scene,
    crystalField: dom.memoryCrystalField,
    now: runtimeMode === 'fixture'
      ? () => new Date(`${todayFixture.date_iso}T07:20:00+08:00`)
      : () => new Date(),
  });
  let lifeFlowController = null;
  let actionController = null;
  let previousLifeFlowView = null;
  let previousTaskActionStatus = 'idle';
  let previousRoutineActionStatus = 'idle';
  let previousActivityActionStatus = 'idle';
  let previousDiaryActionStatus = 'idle';
  let previousReminderActionStatus = 'idle';
  let previousCalendarActionStatus = 'idle';
  const lifeFlowScroll = new Map();
  const announce = (message) => {
    if (dom.statusNode) dom.statusNode.textContent = message;
  };
  const silentSpacesController = initSilentSpaces(dom, {
    dataSource: runtimeMode === 'fixture'
      ? createSilentSpacesFixtureDataSource({ date: todayFixture.date_iso })
      : silentSpacesApi,
    announce,
    onStateChange: render,
  });
  renderSilentSpaces = () => silentSpacesController.render();
  silentSpacesSummary = () => silentSpacesController.summary();
  const actionView = createActionView(dom.action, {
    dispatch: (event) => {
      if (event.type === 'CONFIRM') return actionController?.confirm();
      if (event.type === 'CANCEL') return actionController?.cancel();
      if (event.type === 'RETRY_PREVIEW') return actionController?.retryPreview();
      if (event.type === 'RETRY_CONFIRM') return actionController?.retryConfirm();
      return false;
    },
    announce,
  });
  const todayView = createTodayView(dom.today, {
    onResourceSelect: (resource, key) => lifeFlowController?.openResourceItem(resource, key),
  });
  const taskView = createTaskView(dom.today.task, {
    dispatch: (event) => lifeFlowController?.handleTaskEvent(event),
    announce,
  });
  const routineView = createRoutineView(dom.today.routine, {
    dispatch: (event) => lifeFlowController?.handleRoutineEvent(event),
    announce,
  });
  const activityView = createActivityView(dom.today.activity, {
    dispatch: (event) => lifeFlowController?.handleActivityEvent(event),
    announce,
  });
  const diaryView = createDiaryView(dom.today.diary, {
    dispatch: (event) => lifeFlowController?.handleDiaryEvent(event),
    announce,
  });
  const reminderView = createReminderView(dom.today.reminder, {
    dispatch: (event) => lifeFlowController?.handleReminderEvent(event),
    announce,
  });
  const calendarView = createCalendarView(dom.today.calendar, {
    dispatch: (event) => lifeFlowController?.handleCalendarEvent(event),
    announce,
  });
  renderLifeFlow = (lifeFlowState) => {
    const viewChanged = lifeFlowState.view !== previousLifeFlowView;
    if (viewChanged && previousLifeFlowView && dom.today.scrollArea) {
      lifeFlowScroll.set(previousLifeFlowView, dom.today.scrollArea.scrollTop);
    }
    todayView.render(lifeFlowState);
    taskView.render(lifeFlowState.tasks, lifeFlowState.view);
    routineView.render(lifeFlowState.routines, lifeFlowState.view);
    activityView.render(lifeFlowState.activities, lifeFlowState.view);
    diaryView.render(lifeFlowState.diaries, lifeFlowState.view);
    reminderView.render(lifeFlowState.reminders, lifeFlowState.view);
    calendarView.render(lifeFlowState.calendarEvents, lifeFlowState.view);
    renderActivityPresence(lifeFlowState);
    const completedResourceAction = (
      previousTaskActionStatus === 'pending' && lifeFlowState.tasks.action.status === 'idle'
    ) || (
      previousRoutineActionStatus === 'pending' && lifeFlowState.routines.action.status === 'idle'
    ) || (
      previousActivityActionStatus === 'pending'
      && lifeFlowState.activities.action.status === 'idle'
    ) || (
      previousDiaryActionStatus === 'pending'
      && lifeFlowState.diaries.action.status === 'idle'
    ) || (
      previousReminderActionStatus === 'pending'
      && lifeFlowState.reminders.action.status === 'idle'
    ) || (
      previousCalendarActionStatus === 'pending'
      && lifeFlowState.calendarEvents.action.status === 'idle'
    );
    if (viewChanged && dom.today.scrollArea) {
      dom.today.scrollArea.scrollTop = lifeFlowScroll.get(lifeFlowState.view) || 0;
    } else if (completedResourceAction && dom.today.scrollArea) {
      const activeView = lifeFlowState.view;
      requestAnimationFrame(() => {
        dom.today.scrollArea.scrollTop = 0;
        const target = activeView === 'task-detail'
          ? dom.today.task.back
          : activeView === 'routine-detail' ? dom.today.routine.back
            : activeView === 'activity-detail' ? dom.today.activity.back : null;
        const focusTarget = activeView === 'diary-detail' ? dom.today.diary.back
          : activeView === 'reminder-detail' ? dom.today.reminder.back
            : activeView === 'calendar-detail' ? dom.today.calendar.back : target;
        focusTarget?.focus({ preventScroll: true });
      });
    }
    if (viewChanged) {
      taskView.focusEntry(lifeFlowState.view);
      routineView.focusEntry(lifeFlowState.view);
      activityView.focusEntry(lifeFlowState.view);
      diaryView.focusEntry(lifeFlowState.view);
      reminderView.focusEntry(lifeFlowState.view);
      calendarView.focusEntry(lifeFlowState.view);
      if (lifeFlowState.view === 'today' && isResourceLifeFlowView(previousLifeFlowView)) {
        todayView.focusReturn();
      }
      previousLifeFlowView = lifeFlowState.view;
    }
    previousTaskActionStatus = lifeFlowState.tasks.action.status;
    previousRoutineActionStatus = lifeFlowState.routines.action.status;
    previousActivityActionStatus = lifeFlowState.activities.action.status;
    previousDiaryActionStatus = lifeFlowState.diaries.action.status;
    previousReminderActionStatus = lifeFlowState.reminders.action.status;
    previousCalendarActionStatus = lifeFlowState.calendarEvents.action.status;
  };
  const fixtureDate = todayFixture.date_iso;
  const fixtureLifeFlowDataSource = createFixtureLifeFlowDataSource({
    now: () => new Date(`${fixtureDate}T16:00:00+08:00`),
    seed: {
      activities: [{
        session_id: 'fixture-activity-rest',
        title: todayFixture.summary_items[1]?.text ?? '给自己留一点时间休息。',
        kind: 'reflection',
        status: 'active',
        started_at: `${fixtureDate}T15:00:00+08:00`,
      }],
      diaryEntries: [{
        entry_id: 'fixture-diary-today',
        date: fixtureDate,
        title: '今天的一束光',
        body: '下午的光线很安静。\n我给自己留了一点停下来的时间。',
        status: 'saved',
        updated_at: `${fixtureDate}T15:30:00+08:00`,
      }],
      calendarEvents: [{
        event_id: 'fixture-calendar-meeting',
        title: todayFixture.summary_items[0]?.text ?? '上午有一次重要的会议提醒。',
        starts_at: `${fixtureDate}T10:00:00+08:00`,
        ends_at: `${fixtureDate}T11:00:00+08:00`,
        all_day: false,
        timezone_name: 'Asia/Shanghai',
        status: 'active',
      }],
      reminders: [
        {
          reminder_id: 'fixture-reminder-break',
          title: '给自己留一点时间休息',
          description: '离开屏幕，看看窗外的光。',
          due_at: `${fixtureDate}T15:00:00+08:00`,
          timezone_name: 'Asia/Shanghai',
          recurrence: null,
          status: 'due',
        },
        {
          reminder_id: 'fixture-reminder-water',
          title: '慢慢喝一杯水',
          description: '',
          due_at: `${fixtureDate}T17:30:00+08:00`,
          timezone_name: 'Asia/Shanghai',
          recurrence: 'daily',
          status: 'scheduled',
        },
      ],
      timeline: [
        {
          item_id: 'fixture-timeline-rest',
          title: todayFixture.summary_items[1]?.text ?? '给自己留一点时间休息。',
          kind: 'activity',
          occurred_at: `${fixtureDate}T15:00:00+08:00`,
        },
        {
          item_id: 'fixture-timeline-meeting',
          title: todayFixture.summary_items[0]?.text ?? '上午有一次重要的会议提醒。',
          kind: 'calendar',
          occurred_at: `${fixtureDate}T10:00:00+08:00`,
        },
      ],
    },
  });
  const lifeFlowDataSource = runtimeMode === 'fixture'
    ? fixtureLifeFlowDataSource
    : apiLifeFlowDataSource;
  lifeFlowController = initLifeFlow(dom.today, {
    dataSource: lifeFlowDataSource,
    announce,
    onStateChange: render,
    localDate: runtimeMode === 'fixture' ? () => fixtureDate : undefined,
  });
  let previousActionProposalStatus = 'idle';
  actionController = initActionProposal({
    dataSource: lifeFlowDataSource,
    getLookup: () => ({
      tasks: getState().lifeFlow.tasks.items,
      routines: getState().lifeFlow.routines.items,
    }),
    commitResult: commitConfirmedActionResult,
    announce,
    onStateChange: render,
  });
  renderAction = () => {
    const actionState = actionController.getState();
    actionView.render(actionState);
    dom.body.dataset.actionProposal = actionState.status;
    if (actionState.status === 'preview_ready' && previousActionProposalStatus !== 'preview_ready') {
      actionView.focus();
    }
    previousActionProposalStatus = actionState.status;
  };
  if (runtimeMode === 'fixture') {
    window.__luminousActionFixture = Object.freeze({
      propose: (proposal) => actionController.injectProposal(proposal),
      state: () => actionController.getState().status,
    });
  }
  initPresentation((key, value) => {
    const currentValue = getState().presentation[key];
    if (currentValue !== value) {
      setPresentationState(key, value);
      render();
    }
  });
  const pwaExperience = initPwaExperience(dom.productization, {
    onStateChange: render,
    isBusy: () => {
      const current = getState();
      const resourceBusy = Object.values(current.lifeFlow ?? {}).some((value) => (
        value?.editor?.status === 'pending' || value?.action?.status === 'pending'
      ));
      const activelyWriting = document.activeElement === dom.chatInput
        && current.conversation.draft.trim().length > 0;
      return current.conversation.chatStatus === 'submitting' || resourceBusy || activelyWriting;
    },
  });
  renderProductization = () => pwaExperience.render();
  render();
  const conversation = initConversation(dom, {
    mode: runtimeMode,
    sendChat: sendChatMessage,
    announce(message) {
      if (dom.statusNode) dom.statusNode.textContent = message;
    },
    onStateChange: render,
    onDraftInput(value) {
      saveRecoverableDraft(draftStorage, value);
      if (dom.draftNotice) dom.draftNotice.hidden = true;
    },
    onDraftSent() {
      clearRecoverableDraft(draftStorage);
      if (dom.draftNotice) dom.draftNotice.hidden = true;
    },
  });
  const runtime = initCoreRuntime({
    mode: runtimeMode,
    announce(message) {
      if (dom.statusNode) dom.statusNode.textContent = message;
    },
    onStateChange: render,
  });
  dom.body.removeAttribute('data-js-loading');

  window.addEventListener('pagehide', () => {
    conversation.destroy();
    lifeFlowController.destroy();
    taskView.destroy();
    routineView.destroy();
    activityView.destroy();
    diaryView.destroy();
    reminderView.destroy();
    calendarView.destroy();
    actionController.destroy();
    actionView.destroy();
    silentSpacesController.destroy();
    pwaExperience.destroy();
    spaceRouter.destroy();
    delete window.__luminousActionFixture;
    todayView.destroy();
    runtime.destroy();
    sceneEnvironment.destroy();
    sceneParallax.destroy();
  }, { once: true });
}

main();
