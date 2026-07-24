document.addEventListener('DOMContentLoaded', () => {
  const elements = {
    body: document.body,
    chatInput: document.getElementById('chat-input'),
    sendButton: document.getElementById('send-button'),
    dialogueContainer: document.getElementById('dialogue-container'),
    feedbackText: document.getElementById('input-feedback'),
    companionFigure: document.getElementById('companion-figure'),
  };

  const API_BASE = ''; // Same origin
  
  // 聊天历史记录，用于发送给后端
  let chatHistory = [];
  
  // 当前正在输入中 (包括 IME)
  let isComposing = false;
  // 当前请求中
  let isRequesting = false;

  // ==== 初始化逻辑 ====
  init();

  async function init() {
    setupEventListeners();
    await fetchState();
    
    // 如果没有任何聊天，可以保持一个空态的温室
  }

  function setupEventListeners() {
    // IME 组合输入处理
    elements.chatInput.addEventListener('compositionstart', () => {
      isComposing = true;
    });
    
    elements.chatInput.addEventListener('compositionend', () => {
      isComposing = false;
      checkInput(); // 检查是否有内容可以启用发送按钮
    });

    elements.chatInput.addEventListener('input', () => {
      if (!isComposing) checkInput();
    });

    elements.chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
        e.preventDefault();
        if (!elements.sendButton.disabled) {
          sendMessage();
        }
      }
    });

    elements.sendButton.addEventListener('click', sendMessage);

    // 移动端键盘弹起处理探测 (简化版，依赖 window resize/visualViewport)
    if (window.visualViewport) {
      const initialHeight = window.visualViewport.height;
      window.visualViewport.addEventListener('resize', () => {
        if (window.visualViewport.height < initialHeight * 0.8) {
          elements.body.classList.add('keyboard-open');
        } else {
          elements.body.classList.remove('keyboard-open');
        }
      });
    }
    
    // 断网事件
    window.addEventListener('offline', () => {
      setStateClass('state-offline');
      showFeedback('温室的信号似乎被云层遮挡了，我在这里陪你等风停。');
    });
    
    window.addEventListener('online', () => {
      clearFeedback();
      fetchState();
    });
  }

  function checkInput() {
    const text = elements.chatInput.value.trim();
    elements.sendButton.disabled = text.length === 0 || isRequesting;
  }

  function setStateClass(stateName) {
    // 移除所有 state- 开头的 class
    elements.body.className = elements.body.className.replace(/\bstate-\S+/g, '');
    elements.body.classList.add(stateName);
  }

  function showFeedback(msg, isError = true) {
    elements.feedbackText.textContent = msg;
    elements.feedbackText.className = 'feedback-text show';
    if (isError) {
      elements.feedbackText.style.color = 'var(--color-error)';
    } else {
      elements.feedbackText.style.color = 'var(--text-sub)';
    }
  }

  function clearFeedback() {
    elements.feedbackText.className = 'feedback-text';
  }

  // API Calls
  async function fetchState() {
    try {
      const res = await fetch(`${API_BASE}/api/state`);
      if (res.ok) {
        const payload = await res.json();
        const state = payload.state;
        if (state) {
          applyState(state);
        }
      } else {
        throw new Error('Failed to fetch state');
      }
    } catch (e) {
      console.error(e);
    }
  }

  function applyState(state) {
    // 根据安全的状态（如情绪或风险级别）改变背景色温
    if (state.risk_level && state.risk_level !== 'low' && state.risk_level !== 'normal') {
       setStateClass('state-error');
    } else if (state.mood === 'steady' || state.mood === 'calm') {
       setStateClass('state-idle');
    } else {
       setStateClass('state-idle'); // 回退默认
    }
  }

  async function sendMessage() {
    if (isRequesting) return;
    
    const message = elements.chatInput.value.trim();
    if (!message) return;

    // UI 乐观更新
    appendMessage('user', message);
    elements.chatInput.value = '';
    checkInput();
    clearFeedback();
    
    isRequesting = true;
    elements.chatInput.disabled = true;
    setStateClass('state-thinking');

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: message,
          history: chatHistory
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`);
      }

      const data = await response.json();
      
      // 更新历史 (这里为了简单，仅推入用户刚刚的话，后端的会话可能会很长，我们也可以用返回的数据覆盖)
      chatHistory.push({ role: 'user', content: message });
      chatHistory.push({ role: 'companion', content: data.reply });
      
      // 渲染回复
      renderCompanionReply(data);
      
      // 状态恢复
      setStateClass('state-idle');

    } catch (e) {
      console.error(e);
      setStateClass('state-error');
      // 恢复输入框内容以便重试
      elements.chatInput.value = message;
      showFeedback('连结中断了，点击发送重试。');
      
      // 移除刚才乐观添加的用户消息，或者标记为发送失败
      removeLastMessage('user');
    } finally {
      isRequesting = false;
      elements.chatInput.disabled = false;
      checkInput();
      elements.chatInput.focus();
    }
  }

  // 渲染逻辑
  function appendMessage(role, text) {
    const group = document.createElement('div');
    group.className = `msg-group ${role}-msg`;
    
    const content = document.createElement('div');
    content.className = 'msg-content';
    content.textContent = text;
    group.appendChild(content);
    
    elements.dialogueContainer.appendChild(group);
    
    // 滚动到底部
    scrollToBottom();
    
    // 自动清理过老的 DOM 节点，避免无限增长
    while (elements.dialogueContainer.children.length > 20) {
      elements.dialogueContainer.removeChild(elements.dialogueContainer.firstChild);
    }
  }
  
  function removeLastMessage(role) {
    const last = elements.dialogueContainer.lastChild;
    if (last && last.classList.contains(`${role}-msg`)) {
      elements.dialogueContainer.removeChild(last);
    }
  }

  function renderCompanionReply(data) {
    // 仅渲染安全的外部 reply 字段。不要提取/传递 role_thinking 和 role_action
    appendMessage('companion', data.reply);
    
    // 如果有 presence 更新状态
    if (data.presence) {
       applyPresence(data.presence);
    }
  }

  function applyPresence(presence) {
    const halo = document.getElementById('presence-halo');
    if (!halo) return;

    // 使用安全的 presence 数据来驱动呼吸动画的节奏
    if (presence.heart_rate) {
      // 假设基础心跳 60 对应 6s 呼吸周期
      const cycle = Math.max(2, 60 / presence.heart_rate * 6);
      halo.style.animationDuration = `${cycle}s`;
    }
  }
  
  function scrollToBottom() {
    elements.dialogueContainer.scrollTop = elements.dialogueContainer.scrollHeight;
  }
});