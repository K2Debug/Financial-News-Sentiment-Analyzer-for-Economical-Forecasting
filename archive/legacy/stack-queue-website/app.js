/* ── Stack Demo ── */
const stackData = [];
const stackVisual = document.getElementById('stack-visual');
const stackLog = document.getElementById('stack-log');
const stackInput = document.getElementById('stack-input');

function renderStack(container, data, mini = false) {
  container.innerHTML = '';
  if (data.length === 0) {
    container.innerHTML = '<div class="stack-empty-msg">Stack is empty</div>';
    return;
  }
  data.forEach((val, i) => {
    const el = document.createElement('div');
    el.className = 'stack-item' + (i === data.length - 1 ? ' top' : '');
    el.textContent = val;
    container.appendChild(el);
  });
}

function addLog(panel, message, type = 'action') {
  const entry = document.createElement('div');
  entry.className = `log-entry ${type}`;
  entry.textContent = message;
  panel.prepend(entry);
  while (panel.children.length > 8) panel.removeChild(panel.lastChild);
}

document.getElementById('stack-push').addEventListener('click', () => {
  const val = stackInput.value.trim();
  if (!val) { addLog(stackLog, 'Enter a value before pushing.', 'error'); return; }
  stackData.push(val);
  renderStack(stackVisual, stackData);
  addLog(stackLog, `push("${val}") — added to top`, 'success');
  stackInput.value = '';
  stackInput.focus();
});

document.getElementById('stack-pop').addEventListener('click', () => {
  if (stackData.length === 0) {
    addLog(stackLog, 'pop() — error: stack is empty', 'error');
    return;
  }
  const items = stackVisual.querySelectorAll('.stack-item');
  const top = items[items.length - 1];
  if (top) {
    top.classList.add('removing');
    setTimeout(() => {
      const val = stackData.pop();
      renderStack(stackVisual, stackData);
      addLog(stackLog, `pop() → "${val}"`, 'success');
    }, 280);
  }
});

document.getElementById('stack-peek').addEventListener('click', () => {
  if (stackData.length === 0) {
    addLog(stackLog, 'peek() — error: stack is empty', 'error');
    return;
  }
  const top = stackData[stackData.length - 1];
  const items = stackVisual.querySelectorAll('.stack-item');
  items.forEach(el => el.classList.remove('highlight'));
  if (items.length) items[items.length - 1].classList.add('highlight');
  addLog(stackLog, `peek() → "${top}" (not removed)`, 'action');
});

document.getElementById('stack-clear').addEventListener('click', () => {
  stackData.length = 0;
  renderStack(stackVisual, stackData);
  addLog(stackLog, 'Stack cleared.', 'info');
});

stackInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') document.getElementById('stack-push').click();
});

/* ── Queue Demo ── */
const queueData = [];
const queueVisual = document.getElementById('queue-visual');
const queueLog = document.getElementById('queue-log');
const queueInput = document.getElementById('queue-input');

function renderQueue(container, data) {
  container.innerHTML = '';
  if (data.length === 0) {
    container.innerHTML = '<div class="queue-empty-msg">Queue is empty</div>';
    return;
  }
  data.forEach((val, i) => {
    const el = document.createElement('div');
    let cls = 'queue-item';
    if (i === 0) cls += ' front';
    if (i === data.length - 1) cls += ' rear';
    el.className = cls;
    el.textContent = val;
    container.appendChild(el);
  });
}

document.getElementById('queue-enqueue').addEventListener('click', () => {
  const val = queueInput.value.trim();
  if (!val) { addLog(queueLog, 'Enter a value before enqueuing.', 'error'); return; }
  queueData.push(val);
  renderQueue(queueVisual, queueData);
  addLog(queueLog, `enqueue("${val}") — added to rear`, 'success');
  queueInput.value = '';
  queueInput.focus();
});

document.getElementById('queue-dequeue').addEventListener('click', () => {
  if (queueData.length === 0) {
    addLog(queueLog, 'dequeue() — error: queue is empty', 'error');
    return;
  }
  const items = queueVisual.querySelectorAll('.queue-item');
  const front = items[0];
  if (front) {
    front.classList.add('removing');
    setTimeout(() => {
      const val = queueData.shift();
      renderQueue(queueVisual, queueData);
      addLog(queueLog, `dequeue() → "${val}"`, 'success');
    }, 280);
  }
});

document.getElementById('queue-front').addEventListener('click', () => {
  if (queueData.length === 0) {
    addLog(queueLog, 'front() — error: queue is empty', 'error');
    return;
  }
  const items = queueVisual.querySelectorAll('.queue-item');
  items.forEach(el => el.classList.remove('highlight'));
  if (items.length) items[0].classList.add('highlight');
  addLog(queueLog, `front() → "${queueData[0]}" (not removed)`, 'action');
});

document.getElementById('queue-clear').addEventListener('click', () => {
  queueData.length = 0;
  renderQueue(queueVisual, queueData);
  addLog(queueLog, 'Queue cleared.', 'info');
});

queueInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') document.getElementById('queue-enqueue').click();
});

/* ── Walkthroughs ── */
const stackSteps = [
  { data: [], desc: 'Empty stack. Nothing to remove yet.' },
  { data: ['A'], desc: 'push("A") — A is now the only item and the top.' },
  { data: ['A', 'B'], desc: 'push("B") — B sits on top of A. B will leave first.' },
  { data: ['A', 'B', 'C'], desc: 'push("C") — C is on top. Stack: bottom→A, B, C←top' },
  { data: ['A', 'B'], desc: 'pop() → "C" — C was last in, so it leaves first (LIFO).' },
  { data: ['A'], desc: 'pop() → "B" — B is removed next. Only A remains.' },
];

const queueSteps = [
  { data: [], desc: 'Empty queue. No one is waiting in line.' },
  { data: ['1'], desc: 'enqueue(1) — 1 is at both front and rear.' },
  { data: ['1', '2'], desc: 'enqueue(2) — 2 joins at the rear. Front is still 1.' },
  { data: ['1', '2', '3'], desc: 'enqueue(3) — line is [1, 2, 3]. 1 will be served first.' },
  { data: ['2', '3'], desc: 'dequeue() → 1 — 1 was first in, so it leaves first (FIFO).' },
  { data: ['3'], desc: 'dequeue() → 2 — 2 is next. Only 3 remains at the rear.' },
];

function setupWalkthrough(containerId, visualId, descId, steps, renderFn) {
  const container = document.getElementById(containerId);
  const visual = document.getElementById(visualId);
  const desc = document.getElementById(descId);

  container.querySelectorAll('.step-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const step = parseInt(btn.dataset.step, 10);
      container.querySelectorAll('.step-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderFn(visual, steps[step].data);
      desc.textContent = steps[step].desc;
    });
  });

  renderFn(visual, steps[0].data);
}

setupWalkthrough('stack-walkthrough', 'stack-wt-visual', 'stack-wt-desc', stackSteps, renderStack);
setupWalkthrough('queue-walkthrough', 'queue-wt-visual', 'queue-wt-desc', queueSteps, renderQueue);

/* ── Quiz ── */
const quizQuestions = [
  {
    q: 'You press Ctrl+Z to undo typing. Which data structure is being used?',
    options: ['Stack', 'Queue', 'Array', 'Linked List'],
    answer: 0,
    explain: 'Undo removes the most recent action first — Last In, First Out. That is a Stack.',
  },
  {
    q: 'In a print queue, documents print in the order they were sent. This is:',
    options: ['LIFO (Stack)', 'FIFO (Queue)', 'Random access', 'Sorted order'],
    answer: 1,
    explain: 'First document submitted prints first — First In, First Out. That is a Queue.',
  },
  {
    q: 'After push(A), push(B), push(C) — what does pop() return?',
    options: ['A', 'B', 'C', 'Error'],
    answer: 2,
    explain: 'C was pushed last and sits on top. pop() removes C first.',
  },
  {
    q: 'After enqueue(10), enqueue(20), enqueue(30) — what does dequeue() return?',
    options: ['10', '20', '30', 'Error'],
    answer: 0,
    explain: '10 was enqueued first and is at the front. dequeue() removes 10.',
  },
  {
    q: 'Which structure allows access at only ONE end for insert and remove?',
    options: ['Stack', 'Queue', 'Both', 'Neither'],
    answer: 0,
    explain: 'A Stack uses only the top. A Queue uses front (remove) and rear (add).',
  },
];

let quizIndex = 0;
let quizAnswered = false;

const quizQuestion = document.getElementById('quiz-question');
const quizOptions = document.getElementById('quiz-options');
const quizFeedback = document.getElementById('quiz-feedback');
const quizNext = document.getElementById('quiz-next');

function renderQuiz() {
  quizAnswered = false;
  quizFeedback.textContent = '';
  quizFeedback.className = 'quiz-feedback';
  quizNext.hidden = true;

  const q = quizQuestions[quizIndex];
  quizQuestion.textContent = `Q${quizIndex + 1}. ${q.q}`;
  quizOptions.innerHTML = '';

  q.options.forEach((opt, i) => {
    const btn = document.createElement('button');
    btn.className = 'quiz-option';
    btn.textContent = opt;
    btn.addEventListener('click', () => selectAnswer(i, btn));
    quizOptions.appendChild(btn);
  });
}

function selectAnswer(i, btn) {
  if (quizAnswered) return;
  quizAnswered = true;
  const q = quizQuestions[quizIndex];
  const buttons = quizOptions.querySelectorAll('.quiz-option');
  buttons.forEach(b => b.disabled = true);

  if (i === q.answer) {
    btn.classList.add('correct');
    quizFeedback.textContent = 'Correct! ' + q.explain;
    quizFeedback.className = 'quiz-feedback correct';
  } else {
    btn.classList.add('wrong');
    buttons[q.answer].classList.add('correct');
    quizFeedback.textContent = 'Not quite. ' + q.explain;
    quizFeedback.className = 'quiz-feedback wrong';
  }
  quizNext.hidden = false;
}

quizNext.addEventListener('click', () => {
  quizIndex = (quizIndex + 1) % quizQuestions.length;
  renderQuiz();
});

renderQuiz();

/* ── Init visuals ── */
renderStack(stackVisual, stackData);
renderQueue(queueVisual, queueData);
