// The version badge is independent of the analysis and demo workflows.
(async () => {
  const badge = document.getElementById('runtime-version');
  if (!badge) return;
  try {
    const response = await fetch('/api/health');
    if (!response.ok) return;
    const health = await response.json();
    if (typeof health.version === 'string' && health.version.trim()) {
      badge.textContent = `v${health.version}`;
    }
  } catch (_) {
    // Keep the unavailable label when health cannot be read.
  }
})();
