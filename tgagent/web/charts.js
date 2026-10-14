'use strict';
/* Small dependency-free SVG charts: line (optionally area), bars (vertical / horizontal), donut, scatter.
   Colours come from the --chart-N CSS variables so both themes work. Hover shows values via <title>. */

const Charts = (() => {
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const palette = () => [1, 2, 3, 4, 5, 6].map(i => css(`--chart-${i}`));
  const esc2 = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const W = el => Math.max(260, Math.floor(el.clientWidth || el.parentElement?.clientWidth || 480));

  function niceMax(v) {
    if (v <= 0) return 1;
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
    return 10 * p;
  }
  function empty(el, text) { el.innerHTML = `<div class="chart-empty">${esc2(text)}</div>`; }

  function line(el, series, { height = 200, fmtY = v => v, fmtX = v => v, area = true, empty: emptyText = '' } = {}) {
    const pts = (series[0]?.points || []);
    if (!pts.length || series.every(s => s.points.every(p => !p.y))) return empty(el, emptyText);
    const w = W(el), h = height, l = 52, r = 10, t = 10, b = 26;
    const xs = series.flatMap(s => s.points.map(p => p.x)), ys = series.flatMap(s => s.points.map(p => p.y));
    const x0 = Math.min(...xs), x1 = Math.max(...xs) || x0 + 1, yMax = niceMax(Math.max(...ys, 0));
    const X = x => l + (x1 === x0 ? (w - l - r) / 2 : (x - x0) / (x1 - x0) * (w - l - r));
    const Y = y => t + (1 - y / yMax) * (h - t - b);
    const pal = palette();
    let svg = '';
    for (let i = 0; i <= 4; i++) {
      const v = yMax * i / 4, y = Y(v);
      svg += `<line class="grid" x1="${l}" x2="${w - r}" y1="${y}" y2="${y}"/><text x="${l - 6}" y="${y + 4}" text-anchor="end">${esc2(fmtY(v))}</text>`;
    }
    const ticks = Math.min(6, pts.length);
    for (let i = 0; i < ticks; i++) {
      const p = pts[Math.round(i * (pts.length - 1) / Math.max(1, ticks - 1))];
      svg += `<text x="${X(p.x)}" y="${h - 6}" text-anchor="middle">${esc2(fmtX(p.x))}</text>`;
    }
    series.forEach((s, si) => {
      const c = s.color || pal[si % pal.length];
      const d = s.points.map((p, i) => `${i ? 'L' : 'M'}${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join('');
      if (area && si === 0) svg += `<path d="${d}L${X(s.points.at(-1).x)},${Y(0)}L${X(s.points[0].x)},${Y(0)}Z" fill="${c}" opacity=".14"/>`;
      svg += `<path d="${d}" fill="none" stroke="${c}" stroke-width="2" stroke-linejoin="round"/>`;
      s.points.forEach(p => { svg += `<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="6" fill="transparent"><title>${esc2(fmtX(p.x))} · ${esc2(s.name || '')} ${esc2(fmtY(p.y))}</title></circle>`; });
    });
    el.innerHTML = `<svg viewBox="0 0 ${w} ${h}" height="${h}">${svg}</svg>` + legend(series.length > 1 ? series.map((s, i) => [s.name, s.color || pal[i % pal.length]]) : []);
  }

  function bars(el, items, { height = 200, fmt = v => v, horizontal = false, stacked = null, empty: emptyText = '' } = {}) {
    if (!items.length || items.every(it => !it.value)) return empty(el, emptyText);
    const pal = palette();
    const w = W(el);
    if (horizontal) {
      const rowH = 26, l = Math.min(180, w * .38), r = 64, h = items.length * rowH + 6;
      const max = niceMax(Math.max(...items.map(i => i.value)));
      let svg = '';
      items.forEach((it, i) => {
        const y = i * rowH + 4, bw = (it.value / max) * (w - l - r);
        const label = it.label.length > 24 ? it.label.slice(0, 23) + '…' : it.label;
        svg += `<text x="${l - 8}" y="${y + 15}" text-anchor="end">${esc2(label)}</text>`
          + `<rect x="${l}" y="${y + 3}" width="${Math.max(2, bw)}" height="${rowH - 10}" rx="4" fill="${it.color || pal[0]}"><title>${esc2(it.label)}: ${esc2(fmt(it.value))}</title></rect>`
          + `<text x="${l + bw + 6}" y="${y + 15}">${esc2(fmt(it.value))}</text>`;
      });
      el.innerHTML = `<svg viewBox="0 0 ${w} ${h}" height="${h}">${svg}</svg>`;
      return;
    }
    const h = height, l = 52, r = 8, t = 10, b = 26;
    const totals = items.map(it => stacked ? stacked.reduce((x, k) => x + (it[k.key] || 0), 0) : it.value);
    const max = niceMax(Math.max(...totals, 0));
    const bw = (w - l - r) / items.length;
    let svg = '';
    for (let i = 0; i <= 4; i++) {
      const v = max * i / 4, y = t + (1 - v / max) * (h - t - b);
      svg += `<line class="grid" x1="${l}" x2="${w - r}" y1="${y}" y2="${y}"/><text x="${l - 6}" y="${y + 4}" text-anchor="end">${esc2(fmt(v))}</text>`;
    }
    const every = Math.ceil(items.length / 10);
    items.forEach((it, i) => {
      const x = l + i * bw + bw * .18, wdt = bw * .64;
      let base = h - b;
      const parts = stacked ? stacked.map((k, ki) => [it[k.key] || 0, k.color || pal[ki], k.name]) : [[it.value, it.color || pal[0], '']];
      parts.forEach(([v, c, name]) => {
        const hh = v / max * (h - t - b);
        if (hh > 0) svg += `<rect x="${x}" y="${base - hh}" width="${wdt}" height="${hh}" rx="3" fill="${c}"><title>${esc2(it.label)} ${esc2(name)}: ${esc2(fmt(v))}</title></rect>`;
        base -= hh;
      });
      if (i % every === 0) svg += `<text x="${x + wdt / 2}" y="${h - 6}" text-anchor="middle">${esc2(it.short || it.label)}</text>`;
    });
    el.innerHTML = `<svg viewBox="0 0 ${w} ${h}" height="${h}">${svg}</svg>` + legend(stacked ? stacked.map((k, i) => [k.name, k.color || pal[i]]) : []);
  }

  function donut(el, items, { fmt = v => v, center = '', empty: emptyText = '' } = {}) {
    const total = items.reduce((x, i) => x + i.value, 0);
    if (!total) return empty(el, emptyText);
    const pal = palette(), s = 180, rO = 80, rI = 52, cx = s / 2, cy = s / 2;
    let a = -Math.PI / 2, svg = '';
    items.forEach((it, i) => {
      const frac = it.value / total, a2 = a + frac * Math.PI * 2, large = frac > .5 ? 1 : 0;
      const p = (r, ang) => `${(cx + r * Math.cos(ang)).toFixed(2)},${(cy + r * Math.sin(ang)).toFixed(2)}`;
      const c = it.color || pal[i % pal.length];
      if (frac >= .9999) svg += `<circle cx="${cx}" cy="${cy}" r="${(rO + rI) / 2}" fill="none" stroke="${c}" stroke-width="${rO - rI}"><title>${esc2(it.label)}</title></circle>`;
      else svg += `<path d="M${p(rO, a)}A${rO},${rO} 0 ${large} 1 ${p(rO, a2)}L${p(rI, a2)}A${rI},${rI} 0 ${large} 0 ${p(rI, a)}Z" fill="${c}"><title>${esc2(it.label)}: ${esc2(fmt(it.value))} (${(frac * 100).toFixed(1)}%)</title></path>`;
      a = a2;
    });
    svg += `<text x="${cx}" y="${cy + 5}" text-anchor="middle" style="font-size:15px;font-weight:650;fill:var(--text)">${esc2(center)}</text>`;
    el.innerHTML = `<div class="donut-wrap"><div class="chart"><svg viewBox="0 0 ${s} ${s}" height="${s}">${svg}</svg></div>`
      + `<div class="chart-legend" style="flex-direction:column;align-items:flex-start;margin:0">${items.map((it, i) =>
        `<span><i style="background:${it.color || pal[i % pal.length]}"></i>${esc2(it.label)} · ${esc2(fmt(it.value))} · ${(it.value / total * 100).toFixed(0)}%</span>`).join('')}</div></div>`;
  }

  function scatter(el, points, { height = 220, fmtX = v => v, fmtY = v => v, logY = false, groups = [], empty: emptyText = '' } = {}) {
    if (!points.length) return empty(el, emptyText);
    const w = W(el), h = height, l = 52, r = 10, t = 10, b = 26;
    const xs = points.map(p => p.x), x0 = Math.min(...xs), x1 = Math.max(...xs) || x0 + 1;
    const tr = v => logY ? Math.log10(Math.max(1, v)) : v;
    const yMaxRaw = Math.max(...points.map(p => tr(p.y)), 1), yMax = logY ? Math.ceil(yMaxRaw) : niceMax(yMaxRaw);
    const X = x => l + (x1 === x0 ? (w - l - r) / 2 : (x - x0) / (x1 - x0) * (w - l - r));
    const Y = y => t + (1 - tr(y) / yMax) * (h - t - b);
    let svg = '';
    const steps = logY ? yMax : 4;
    for (let i = 0; i <= steps; i++) {
      const v = logY ? Math.pow(10, i) : yMax * i / 4, y = t + (1 - (logY ? i : v) / yMax) * (h - t - b);
      svg += `<line class="grid" x1="${l}" x2="${w - r}" y1="${y}" y2="${y}"/><text x="${l - 6}" y="${y + 4}" text-anchor="end">${esc2(fmtY(v))}</text>`;
    }
    for (let i = 0; i < 5; i++) {
      const xv = x0 + (x1 - x0) * i / 4;
      svg += `<text x="${X(xv)}" y="${h - 6}" text-anchor="middle">${esc2(fmtX(xv))}</text>`;
    }
    points.forEach(p => { svg += `<circle cx="${X(p.x).toFixed(1)}" cy="${Y(p.y).toFixed(1)}" r="4" fill="${p.color}" opacity=".75"><title>${esc2(p.label)}</title></circle>`; });
    el.innerHTML = `<svg viewBox="0 0 ${w} ${h}" height="${h}">${svg}</svg>` + legend(groups);
  }

  function legend(items) {
    if (!items.length) return '';
    return `<div class="chart-legend">${items.map(([n, c]) => `<span><i style="background:${c}"></i>${esc2(n)}</span>`).join('')}</div>`;
  }

  return { line, bars, donut, scatter, palette };
})();
