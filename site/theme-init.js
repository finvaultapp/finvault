// Runs before first paint so a saved light/dark choice never flashes.
try { const t = localStorage.getItem('fv.site.theme'); if (t) document.documentElement.dataset.theme = t } catch (e) {}
