/* NeuralAgency — Main App JS */

document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('briefForm');
  const submitBtn = document.getElementById('submitBtn');
  const statusBox = document.getElementById('statusBox');
  const statusText = document.getElementById('statusText');

  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const data = new FormData(form);
    const deliverables = [...form.querySelectorAll('input[name="deliverables"]:checked')]
      .map(el => el.value);

    if (deliverables.length === 0) {
      alert('Please select at least one deliverable.');
      return;
    }

    const brief = {
      business_name: data.get('business_name'),
      product_description: data.get('product_description'),
      target_audience: data.get('target_audience'),
      campaign_goal: data.get('campaign_goal'),
      brand_voice: data.get('brand_voice') || 'Professional but approachable',
      budget_range: data.get('budget_range') || 'Not specified',
      timeline: data.get('timeline') || '30 days',
      differentiators: data.get('differentiators') || 'Not specified',
      deliverables,
    };

    submitBtn.disabled = true;
    submitBtn.textContent = 'Launching agents...';
    statusBox.classList.remove('hidden');
    statusText.textContent = 'Submitting your brief...';

    try {
      const res = await fetch('/api/brief', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(brief),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Submission failed');
      }

      const { job_id } = await res.json();
      statusText.textContent = 'Brief received. Redirecting to results...';

      setTimeout(() => {
        window.location.href = `/results/${job_id}`;
      }, 1200);

    } catch (err) {
      statusBox.classList.add('hidden');
      submitBtn.disabled = false;
      submitBtn.textContent = '🚀 Launch AI Campaign Generation';
      alert(`Error: ${err.message}`);
    }
  });
});
