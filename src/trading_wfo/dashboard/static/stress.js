/* Uses textContent via the dashboard's addCell helpers, never result HTML. */
function renderStress(win) {
  const result = win?.robustness_result;
  const summary = state.data.robustness_summary;
  document.querySelector('#stress-note').textContent = !result
    ? 'Configure robustness=RobustnessConfig(...) in WalkForwardRunner to run frozen OOS stress tests.'
    : (summary?.warning || 'Diagnostics only; no reoptimization. Window sums are not a compounded portfolio. Spread stress can change the trade sample.');
  document.querySelector('#stress-rows').replaceChildren(...(result?.scenarios || []).map(s => {
    const row = el('tr'), m = s.metrics || {};
    addCell(row, s.name); addCell(row, money(m.net_profit), cls(m.net_profit));
    addCell(row, money(s.delta_net_profit), cls(s.delta_net_profit));
    addCell(row, number(m.profit_factor)); addCell(row, percent(m.max_drawdown_pct));
    addCell(row, number(m.total_trades, 0)); addCell(row, s.status);
    return row;
  }));
  document.querySelector('#stress-summary-rows').replaceChildren(...(summary?.scenarios || []).map(s => {
    const row = el('tr'); addCell(row, s.name);
    addCell(row, money(s.net_profit), cls(s.net_profit)); addCell(row, number(s.profit_factor));
    addCell(row, `${s.negative_windows} / ${s.evaluated_windows} (${s.skipped_windows} skipped)`);
    addCell(row, percent(s.worst_window_dd_pct));
    addCell(row, money(s.without_best_year_profit), cls(s.without_best_year_profit));
    return row;
  }));
  const periodRows = (items, key) => items.flatMap(s => (s[key] || []).map(p => {
    const row = el('tr'); addCell(row, s.name); addCell(row, p.period);
    addCell(row, money(p.net_profit), cls(p.net_profit)); addCell(row, number(p.total_trades, 0));
    return row;
  }));
  document.querySelector('#stress-year-rows').replaceChildren(...periodRows(summary?.scenarios || [], 'yearly'));
  document.querySelector('#stress-month-rows').replaceChildren(...periodRows(result?.scenarios || [], 'monthly'));
  const mc = result?.monte_carlo, boot = mc?.iid_bootstrap;
  document.querySelector('#stress-monte-carlo').textContent = !boot
    ? 'Monte Carlo is optional (monte_carlo_samples).'
    : `Baseline trade bootstrap: ${mc.samples} samples; negative PnL ${percent(boot.negative_profit_fraction * 100)}; 95th percentile realized DD ${money(boot.max_drawdown_p50_p95_p99[1])}. Account currency; not future-loss probability or intratrade risk.`;
}
