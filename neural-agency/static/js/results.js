/* NeuralAgency — Results page JS */

document.addEventListener('DOMContentLoaded', () => {
  // ─── Tab switching ───────────────────────────────────────────────────────────
  const tabs = document.querySelectorAll('.tab');
  const panels = document.querySelectorAll('.tab-panel');

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab;

      tabs.forEach(t => t.classList.remove('active'));
      panels.forEach(p => p.classList.remove('active'));

      tab.classList.add('active');
      const panel = document.getElementById(`panel-${target}`);
      if (panel) panel.classList.add('active');
    });
  });

  // ─── Copy buttons ────────────────────────────────────────────────────────────
  document.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const contentId = btn.dataset.content;
      const el = document.getElementById(`${contentId}-content`);
      if (!el) return;

      try {
        await navigator.clipboard.writeText(el.textContent);
        const orig = btn.textContent;
        btn.textContent = '✅ Copied!';
        setTimeout(() => { btn.textContent = orig; }, 2000);
      } catch {
        btn.textContent = 'Copy failed';
      }
    });
  });

  // ─── Auto-poll for in-progress jobs ─────────────────────────────────────────
  const processingBox = document.getElementById('processingBox');
  if (!processingBox) return;

  const jobId = processingBox.dataset.jobId;
  const statusEl = document.getElementById('processingStatus');

  const statusLabels = {
    pending: '⏳ Queued — waiting to start...',
    running_strategy: '🧠 Strategy Agent working...',
    running_deliverables: '✍️ Copy, Content & SEO agents working in parallel...',
    completed: '✅ Complete! Loading results...',
    failed: '❌ Failed.',
  };

  let interval = setInterval(async () => {
    try {
      const res = await fetch(`/api/job/${jobId}`);
      if (!res.ok) return;
      const data = await res.json();

      if (statusEl) {
        statusEl.textContent = statusLabels[data.status] || `Status: ${data.status}`;
      }

      if (data.status === 'completed' || data.status === 'failed') {
        clearInterval(interval);
        setTimeout(() => window.location.reload(), 1000);
      }
    } catch {
      // Silently retry
    }
  }, 3000);
});
