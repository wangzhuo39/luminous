/**
 * @typedef {'calm' | 'warm' | 'quiet' | 'concerned' | 'unknown'} VisualTone
 */

/**
 * @typedef {object} SceneViewModel
 * @property {string} caption
 * @property {VisualTone} tone
 */

/**
 * @typedef {object} MessageViewModel
 * @property {string} id
 * @property {'user' | 'assistant'} role
 * @property {string} text
 */

/**
 * @typedef {object} ConversationViewModel
 * @property {MessageViewModel[]} messages
 * @property {{idPrefix: string, text: string}} localReply
 * @property {{caption: string, tone: VisualTone}} sceneAfterLocalSend
 */

/**
 * @typedef {object} TodaySummaryItem
 * @property {string} id
 * @property {string} text
 */

/**
 * @typedef {object} TodayViewModel
 * @property {string} date
 * @property {TodaySummaryItem[]} summaryItems
 */

/**
 * @typedef {object} OutboxArrival
 * @property {string} id
 * @property {string} title
 * @property {string} snippet
 */

/**
 * @typedef {object} OutboxViewModel
 * @property {OutboxArrival[]} arrivals
 * @property {number} unreadCount
 */

/**
 * @typedef {object} MemoryPrivacyViewModel
 * @property {string} memoryPrompt
 * @property {string} privacyCaption
 * @property {string} boundaryStatus
 */

/**
 * @typedef {object} AllViewModels
 * @property {SceneViewModel} scene
 * @property {ConversationViewModel} conversation
 * @property {TodayViewModel} today
 * @property {OutboxViewModel} outbox
 * @property {MemoryPrivacyViewModel} memoryPrivacy
 */

/**
 * @typedef {'offline'|'timeout'|'validation'|'not-found'|'model-unavailable'|'server'|'cancelled'|'unknown'} AppErrorKind
 */

/**
 * @typedef {object} SafeErrorDescriptor
 * @property {AppErrorKind} kind
 * @property {number|null} status
 * @property {string} message
 * @property {boolean} retryable
 */

/**
 * @typedef {object} ChatResultViewModel
 * @property {MessageViewModel} assistantMessage
 * @property {SceneViewModel} scene
 */

export {};
