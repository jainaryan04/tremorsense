// Minimal canvas charts (no dependencies, works offline).

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function setup(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return { ctx, w, h };
}

// Live trace: values in [-1, 1]-ish, marks = indices where a cue fired.
export function drawTrace(canvas, values, marks) {
  const { ctx, w, h } = setup(canvas);
  const n = values.length;
  if (!n) return;
  let m = 1e-6;
  for (const v of values) m = Math.max(m, Math.abs(v));
  ctx.strokeStyle = css("--accent");
  ctx.globalAlpha = 0.85;
  for (const i of marks) {
    const x = (i / (n - 1)) * w;
    ctx.beginPath();
    ctx.moveTo(x, 4);
    ctx.lineTo(x, h - 4);
    ctx.lineWidth = 2;
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
  ctx.strokeStyle = css("--ink");
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  values.forEach((v, i) => {
    const x = (i / (n - 1)) * w, y = h / 2 - (v / m) * (h / 2 - 6);
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.stroke();
}

// series: [{points: [[x, y]], color, dash, dots}], opts: {x0, x1, y0, y1, vlines, vlineColor, xLabel}
export function drawChart(canvas, series, opts) {
  const { ctx, w, h } = setup(canvas);
  const pad = { l: 28, r: 8, t: 8, b: 20 };
  const X = (x) => pad.l + ((x - opts.x0) / (opts.x1 - opts.x0)) * (w - pad.l - pad.r);
  const Y = (y) => h - pad.b - ((y - opts.y0) / (opts.y1 - opts.y0)) * (h - pad.t - pad.b);
  ctx.font = `11px ${css("--font")}`;
  ctx.fillStyle = css("--muted");
  ctx.strokeStyle = css("--line");
  ctx.lineWidth = 1;
  for (let g = Math.ceil(opts.y0); g <= opts.y1; g++) {
    ctx.beginPath();
    ctx.moveTo(pad.l, Y(g));
    ctx.lineTo(w - pad.r, Y(g));
    ctx.stroke();
    ctx.fillText(String(g), 8, Y(g) + 4);
  }
  if (opts.xTicks) {
    for (const [x, label] of opts.xTicks) ctx.fillText(label, X(x) - 10, h - 5);
  }
  for (const v of opts.vlines || []) {
    ctx.strokeStyle = v.color || css("--dose");
    ctx.setLineDash(v.dash || []);
    ctx.beginPath();
    ctx.moveTo(X(v.x), pad.t);
    ctx.lineTo(X(v.x), h - pad.b);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  for (const s of series) {
    ctx.strokeStyle = ctx.fillStyle = s.color;
    if (s.dots) {
      for (const [x, y] of s.points) ctx.fillRect(X(x) - 1, Y(y) - 1, 2, 2);
      continue;
    }
    ctx.lineWidth = s.width || 2;
    ctx.setLineDash(s.dash || []);
    ctx.beginPath();
    s.points.forEach(([x, y], i) => (i ? ctx.lineTo(X(x), Y(y)) : ctx.moveTo(X(x), Y(y))));
    ctx.stroke();
    ctx.setLineDash([]);
  }
}
