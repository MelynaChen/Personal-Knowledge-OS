'use strict';
const rawText = document.getElementById('rawText');
const previewButton = document.getElementById('previewButton');
const commitButton = document.getElementById('commitButton');
const editorMessage = document.getElementById('editorMessage');
const commitMessage = document.getElementById('commitMessage');
const previewResult = document.getElementById('previewResult');
const statusResult = document.getElementById('statusResult');
const importIdInput = document.getElementById('importId');
let previewHash = null;
let previewRawText = null;
let pollTimer = null;

function clearPreview() {
  previewHash = null;
  previewRawText = null;
  commitButton.disabled = true;
  previewResult.textContent = '内容已修改，请重新预览。';
  commitMessage.textContent = '';
}
rawText.addEventListener('input', clearPreview);

document.getElementById('sampleButton').addEventListener('click', () => {
  const now = new Date();
  const day = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  const example = {schema_version: 1, date: day, tasks: [{
    name: '网页演示：理解向量检索', category: 'AI', priority: 'Medium',
    knowledge_path: ['AI', 'RAG', '向量检索'],
    learning_goal: '理解向量检索如何找到语义相近的内容',
    action_steps: ['阅读向量检索的基本概念', '写下一个实际应用场景'],
    output_required: '一页学习笔记',
    note: {title: '向量检索学习笔记', summary: '记录向量检索的用途与基本步骤。',
      key_concepts: ['Embedding', '相似度'],
      detailed_explanation: '先把文本转换为向量，再根据相似度找出相关内容。',
      examples: ['从个人笔记中找到与问题相关的段落'], practice: ['尝试画出检索流程'],
      my_understanding: '', questions: [], common_mistakes: [], next_topics: [], resources: []},
    review: {enabled: true, difficulty: 'Medium'}
  }]};
  rawText.value = JSON.stringify(example, null, 2);
  clearPreview();
  pkosFeedback(editorMessage, '示例已载入。可以修改任务名称，再预览。');
});

function previewField(grid, label, value) {
  const term = document.createElement('dt');
  const description = document.createElement('dd');
  term.textContent = label;
  description.textContent = value;
  grid.append(term, description);
}

previewButton.addEventListener('click', async () => {
  const content = rawText.value.trim();
  clearPreview();
  if (!content) { pkosFeedback(editorMessage, '请先粘贴 JSON，或载入示例。', true); return; }
  previewButton.disabled = true;
  pkosFeedback(editorMessage, '正在预览…');
  try {
    const data = await pkosRequest('/import/preview', {method: 'POST',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify({raw_text: content})});
    previewHash = data.preview_hash;
    previewRawText = content;
    previewResult.replaceChildren();
    data.items.forEach((item, index) => {
      const task = data.payload.tasks[index];
      const article = document.createElement('article');
      article.className = 'preview-item';
      const heading = document.createElement('h3');
      heading.textContent = task.name + ' ';
      heading.append(pkosBadge(item.status.toUpperCase()));
      const grid = document.createElement('dl');
      grid.className = 'preview-grid';
      previewField(grid, 'Date', data.payload.date);
      previewField(grid, 'Category', task.category);
      previewField(grid, 'Knowledge Path', task.knowledge_path.join(' → '));
      previewField(grid, 'Priority', task.priority);
      previewField(grid, 'Learning Goal', task.learning_goal);
      previewField(grid, 'Action Steps', task.action_steps.join('\n'));
      previewField(grid, 'Note Title', task.note.title);
      previewField(grid, 'Review Difficulty', task.review.enabled ? task.review.difficulty : 'Disabled');
      article.append(heading, grid);
      previewResult.append(article);
    });
    const hasConflict = data.items.some(item => item.status === 'conflict');
    commitButton.disabled = hasConflict;
    pkosFeedback(editorMessage, hasConflict ? 'Schema Conflict：预览发现冲突，请修改 JSON 后重试。' :
      '预览成功。确认内容后可以 Commit & Sync。', hasConflict);
  } catch (error) {
    previewResult.textContent = '预览失败。';
    pkosFeedback(editorMessage, error.message, true);
  } finally { previewButton.disabled = false; }
});

commitButton.addEventListener('click', async () => {
  if (!previewHash || rawText.value.trim() !== previewRawText) { clearPreview(); return; }
  commitButton.disabled = true;
  pkosFeedback(commitMessage, '正在保存到 SQLite…');
  try {
    const data = await pkosRequest('/import/commit', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({raw_text: previewRawText, preview_hash: previewHash})});
    importIdInput.value = data.import_id;
    pkosFeedback(commitMessage, `已保存。Import ID：${data.import_id}；本地状态：${data.sync_status}。`);
    await refreshStatus();
  } catch (error) {
    pkosFeedback(commitMessage, error.message, true);
    commitButton.disabled = false;
  }
});

async function refreshStatus() {
  const id = importIdInput.value.trim();
  if (!/^\d+$/.test(id) || Number(id) < 1) {
    pkosFeedback(statusResult, '请输入有效的 Import ID。', true);
    return;
  }
  try {
    const data = await pkosRequest(`/imports/${id}`);
    statusResult.replaceChildren();
    const heading = document.createElement('p');
    const detail = document.createElement('a');
    detail.href = `/history/${id}`;
    detail.textContent = `Import #${id} 详情`;
    heading.append('Local Status：', pkosBadge(data.status), ' · ', detail);
    statusResult.append(heading);
    const allDuplicate = data.items.every(item => item.notion_sync_status === 'duplicate');
    if (data.status === 'completed') {
      const notice = document.createElement('p');
      notice.className = 'feedback success';
      notice.textContent = allDuplicate ? 'Duplicate：没有创建新的 Notion 页面。' : 'Synced to Notion';
      statusResult.append(notice);
    }
    data.items.forEach(item => {
      const block = document.createElement('div');
      block.className = 'preview-item';
      block.append(`任务 ${item.item_index + 1} · Local: ${item.local_save_status} · Sync: `,
        pkosBadge(item.notion_sync_status));
      if (item.operations.length) {
        const details = document.createElement('details');
        const summary = document.createElement('summary');
        summary.textContent = '同步步骤与错误';
        const list = document.createElement('ul');
        item.operations.forEach(op => {
          const entry = document.createElement('li');
          entry.textContent = `${op.step}: ${op.status}${op.last_error ? ' · ' + op.last_error : ''}`;
          list.append(entry);
        });
        details.append(summary, list);
        block.append(details);
      }
      statusResult.append(block);
    });
    if (data.items.some(item => item.notion_sync_status === 'failed')) {
      const retry = document.createElement('button');
      retry.type = 'button';
      retry.className = 'button secondary';
      retry.textContent = 'Retry Failed Sync';
      retry.addEventListener('click', async () => {
        retry.disabled = true;
        try {
          const result = await pkosRequest(`/imports/${id}/retry`, {method: 'POST'});
          pkosFeedback(commitMessage, result.requeued ? `已重新排队 ${result.requeued} 个可重试操作。` :
            '没有可重试操作；已完成的操作不会重建。');
          await refreshStatus();
        } catch (error) { pkosFeedback(commitMessage, `Notion Sync Failed：${error.message}`, true); }
        finally { retry.disabled = false; }
      });
      statusResult.append(retry);
    }
    clearInterval(pollTimer);
    if (data.status !== 'completed' && data.status !== 'failed') pollTimer = setInterval(refreshStatus, 5000);
  } catch (error) {
    pkosFeedback(statusResult, error.message, true);
    clearInterval(pollTimer);
  }
}
document.getElementById('statusButton').addEventListener('click', refreshStatus);
