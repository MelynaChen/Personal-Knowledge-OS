'use strict';
(async () => {
  const connected = document.getElementById('notionConnected');
  const initialized = document.getElementById('notionInitialized');
  const schema = document.getElementById('notionSchema');
  const message = document.getElementById('notionHealthMessage');
  try {
    const data = await pkosRequest('/notion/health');
    connected.textContent = data.connected ? 'Yes' : 'No';
    initialized.textContent = data.initialized ? 'Yes' : 'No';
    schema.textContent = data.schema_valid ? 'Yes' : 'No';
    if (data.error) pkosFeedback(message, `连接检查：${data.error}`, true);
  } catch (error) {
    connected.textContent = initialized.textContent = schema.textContent = 'Unknown';
    pkosFeedback(message, `Network Error：${error.message}`, true);
  }
})();
