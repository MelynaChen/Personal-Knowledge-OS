'use strict';

async function pkosRequest(path, options = {}) {
  let response;
  try { response = await fetch(path, options); }
  catch { throw new Error('Network Error：无法连接本地 FastAPI 服务。'); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail ?? data.error ?? '';
    const summary = Array.isArray(detail) ? detail.map(item => item.msg || String(item)).join('；') : String(detail);
    const title = response.status === 422 ? 'Import Validation Failed' :
      response.status === 409 ? 'Schema Conflict' : response.status >= 500 ? 'Server Error' : 'Request Failed';
    throw new Error(`${title}：${summary || `HTTP ${response.status}`}`.slice(0, 400));
  }
  return data;
}

function pkosFeedback(element, text, error = false) {
  if (!element) return;
  element.textContent = text;
  element.classList.toggle('error', error);
  element.classList.toggle('success', !error);
}

function pkosBadge(value) {
  const span = document.createElement('span');
  span.className = `badge status-${String(value).toLowerCase().replaceAll(' ', '-')}`;
  span.textContent = value;
  return span;
}

document.addEventListener('click', async event => {
  const scoreButton = event.target.closest('.score-button');
  if (scoreButton) {
    const card = scoreButton.closest('.review-card');
    const actions = card.querySelector('.review-actions');
    const feedback = card.querySelector('.review-result');
    const buttons = Array.from(actions.querySelectorAll('button'));
    buttons.forEach(button => { button.disabled = true; });
    const previousLevel = Number(card.dataset.level);
    try {
      const data = await pkosRequest(`/reviews/${card.dataset.reviewId}/complete`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({memory_score: Number(scoreButton.dataset.score),
          request_key: crypto.randomUUID(), expected_version: Number(card.dataset.version)})
      });
      actions.remove();
      pkosFeedback(feedback, `已完成：Level ${previousLevel} → ${data.new_level}；下次复习 ${data.next_review_date}。`);
    } catch (error) {
      buttons.forEach(button => { button.disabled = false; });
      pkosFeedback(feedback, `Review Failed：${error.message}`, true);
    }
    return;
  }

  const retryButton = event.target.closest('.retry-button');
  if (retryButton) {
    retryButton.disabled = true;
    const feedback = document.getElementById('retryMessage');
    try {
      const data = await pkosRequest(`/imports/${retryButton.dataset.importId}/retry`, {method: 'POST'});
      pkosFeedback(feedback, data.requeued ? `已重新排队 ${data.requeued} 个可重试操作。刷新页面可查看状态。` : '没有可重试的失败操作；已完成的操作不会重新创建。');
    } catch (error) { pkosFeedback(feedback, `Notion Sync Failed：${error.message}`, true); }
    finally { retryButton.disabled = false; }
    return;
  }

  const copyButton = event.target.closest('.copy-button');
  if (copyButton) {
    const target = document.getElementById(copyButton.dataset.copyTarget);
    const feedback = document.getElementById('copyMessage');
    try {
      await navigator.clipboard.writeText(target.textContent.trim());
      pkosFeedback(feedback, '已复制到剪贴板。');
    } catch {
      pkosFeedback(feedback, '复制失败；请选中上方文本手动复制。', true);
    }
  }
});

const taskStatus = document.getElementById('taskStatus');
if (taskStatus) {
  let savedStatus = taskStatus.value;
  taskStatus.addEventListener('change', async () => {
    const feedback = document.getElementById('taskStatusMessage');
    taskStatus.disabled = true;
    try {
      const data = await pkosRequest(`/tasks/${taskStatus.dataset.taskId}/status`, {
        method: 'PATCH', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({status: taskStatus.value})
      });
      savedStatus = data.status;
      pkosFeedback(feedback, `本地状态已更新为 ${savedStatus}。`);
    } catch (error) {
      taskStatus.value = savedStatus;
      pkosFeedback(feedback, error.message, true);
    } finally { taskStatus.disabled = false; }
  });
}
