/**
 * dashboard.js — Live polling, dual-ring gauge, sparkbars, FPS counter,
 * danger flash overlay, Chart.js trend with average line.
 */

// ── Constants ─────────────────────────────────────────────────────────────────

const MAX_POINTS  = 60;
const ARC_OUTER   = 240;   // outer arc (current score)
const ARC_INNER   = 196;   // inner arc (session average)

// ── State ─────────────────────────────────────────────────────────────────────

const scoreHistory = new Array(MAX_POINTS).fill(0);
const earHistory   = new Array(8).fill(0.28);   // for sparkbars
const marHistory   = new Array(8).fill(0.06);
let   scoreSum     = 0;
let   scoreCount   = 0;
let   lastFrameTs  = 0;
let   frameCount   = 0;
let   fpsValue     = 0;

// ── Chart.js ──────────────────────────────────────────────────────────────────

const trendCtx = document.getElementById('trendChart').getContext('2d');
const trendChart = new Chart(trendCtx, {
  type: 'bar',
  data: {
    labels: Array.from({ length: MAX_POINTS }, (_, i) => (MAX_POINTS - i) + 's'),
    datasets: [
      {
        label: 'Fatigue score',
        data: [...scoreHistory],
        backgroundColor: scoreHistory.map(() => '#00e676'),
        borderWidth: 0,
        borderRadius: 2,
        order: 2,
      },
      {
        label: 'Average',
        data: new Array(MAX_POINTS).fill(0),
        type: 'line',
        borderColor: 'rgba(0,212,255,0.4)',
        borderWidth: 1.5,
        borderDash: [4, 4],
        pointRadius: 0,
        fill: false,
        order: 1,
      }
    ]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 250 },
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: { label: ctx => ctx.datasetIndex === 0
          ? 'Score: ' + ctx.parsed.y.toFixed(0)
          : 'Avg: '   + ctx.parsed.y.toFixed(0)
        }
      }
    },
    scales: {
      x: {
        grid: { color: '#1a2035' },
        ticks: { color: '#4a5270', font: { size: 8, family: "'JetBrains Mono',monospace" }, maxTicksLimit: 8, autoSkip: true }
      },
      y: {
        min: 0, max: 100,
        grid: { color: '#1a2035' },
        ticks: { color: '#4a5270', font: { size: 8, family: "'JetBrains Mono',monospace" }, stepSize: 25 }
      }
    }
  }
});

// ── Gauge ─────────────────────────────────────────────────────────────────────

function updateGauge(score, avg) {
  const pct    = Math.min(score, 100) / 100;
  const avgPct = Math.min(avg, 100)   / 100;

  document.getElementById('score-arc').style.strokeDashoffset = (ARC_OUTER - pct * ARC_OUTER).toFixed(1);
  document.getElementById('avg-arc').style.strokeDashoffset   = (ARC_INNER - avgPct * ARC_INNER).toFixed(1);

  const angle = -90 + (pct * 180);
  document.getElementById('needle').style.transform = `rotate(${angle.toFixed(1)}deg)`;
  document.getElementById('score-text').textContent  = Math.round(score);
  document.getElementById('avg-label').textContent   = avg > 0 ? avg.toFixed(0) : '—';
}

// ── Status pill + danger overlay ──────────────────────────────────────────────

function updateStatus(status) {
  const pill    = document.getElementById('main-pill');
  const overlay = document.getElementById('danger-overlay');
  pill.textContent = status;
  pill.className   = `status-pill ${status}`;
  overlay.className = status === 'DANGER' ? 'active' : '';
}

// ── Sparkbars ─────────────────────────────────────────────────────────────────

function updateSpark(id, history, color) {
  const bars = document.querySelectorAll(`#${id} .spark-bar`);
  const max  = Math.max(...history, 0.001);
  bars.forEach((bar, i) => {
    const pct = Math.round((history[i] / max) * 100);
    bar.style.height     = pct + '%';
    bar.style.background = color;
    bar.style.opacity    = 0.4 + (i / bars.length) * 0.6;
  });
}

// ── Score history + chart ─────────────────────────────────────────────────────

function pushScore(score) {
  scoreHistory.shift();
  scoreHistory.push(score);

  scoreSum   += score;
  scoreCount += 1;
  const avg   = scoreCount > 0 ? scoreSum / scoreCount : 0;

  trendChart.data.datasets[0].data            = [...scoreHistory];
  trendChart.data.datasets[0].backgroundColor = scoreHistory.map(v =>
    v >= 70 ? '#ff3d3d' : v >= 40 ? '#ffab40' : '#00e676'
  );
  trendChart.data.datasets[1].data = new Array(MAX_POINTS).fill(parseFloat(avg.toFixed(1)));
  trendChart.update('none');

  return avg;
}

// ── FPS counter (measures image reload rate as proxy for stream fps) ──────────

const feedImg = document.getElementById('video-feed');
feedImg.addEventListener('load', () => {
  frameCount++;
  const now = performance.now();
  if (now - lastFrameTs >= 1000) {
    fpsValue   = frameCount;
    frameCount = 0;
    lastFrameTs = now;
    const label = fpsValue + ' fps';
    document.getElementById('fps-badge').textContent = label;
    document.getElementById('fps-info').textContent  = label;
  }
});

// ── DOM helpers ───────────────────────────────────────────────────────────────

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

// ── /status polling ───────────────────────────────────────────────────────────

async function pollStatus() {
  try {
    const res  = await fetch('/status');
    if (!res.ok) return;
    const d    = await res.json();

    const score  = d.fatigue_score ?? 0;
    const status = d.status ?? 'NORMAL';

    const avg = pushScore(score);
    updateGauge(score, avg);
    updateStatus(status);

    // EAR sparkbar
    if (d.ear != null) {
      earHistory.shift(); earHistory.push(d.ear);
      updateSpark('spark-ear', earHistory, '#00d4ff');
    }

    // MAR sparkbar
    if (d.mar != null) {
      marHistory.shift(); marHistory.push(d.mar);
      updateSpark('spark-mar', marHistory, '#ffab40');
    }

    // Live signals
    setText('v-ear',    d.ear   != null ? d.ear.toFixed(3)   : '—');
    setText('v-mar',    d.mar   != null ? d.mar.toFixed(3)   : '—');
    setText('v-yaw',    d.yaw   != null ? d.yaw.toFixed(1) + '°' : '—');
    setText('v-pitch',  d.pitch != null ? d.pitch.toFixed(1) + '°' : '—');
    setText('v-blinks', d.blinks      ?? 0);
    setText('v-yawns',  d.yawns       ?? 0);
    setText('v-yawns-recent', d.yawns_recent ?? 0);
    setText('v-drops',  d.head_drops  ?? 0);
    setText('v-cf',     d.blinks      ?? 0);

    // Session totals
    setText('s-blinks', d.blinks       ?? 0);
    setText('s-yawns',  d.yawns        ?? 0);
    setText('s-alerts', d.alerts_fired ?? 0);
    setText('s-drops',  d.head_drops   ?? 0);

  } catch (_) {}
}

// ── /events polling ───────────────────────────────────────────────────────────

async function pollEvents() {
  try {
    const res    = await fetch('/events');
    if (!res.ok) return;
    const events = await res.json();
    const tbody  = document.getElementById('event-tbody');

    if (!events.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty-row">Monitoring — no events yet</td></tr>';
      return;
    }

    tbody.innerHTML = events.map(ev => `
      <tr>
        <td>${ev.timestamp ?? '—'}</td>
        <td>${ev.event_type ?? '—'}</td>
        <td>${ev.fatigue_score != null ? parseFloat(ev.fatigue_score).toFixed(0) : '—'}</td>
        <td><span class="evt-badge ${ev.status ?? ''}">${ev.status ?? '—'}</span></td>
        <td>${ev.ear != null ? parseFloat(ev.ear).toFixed(3) : '—'}</td>
        <td>${ev.mar != null ? parseFloat(ev.mar).toFixed(3) : '—'}</td>
      </tr>`).join('');
  } catch (_) {}
}

// ── Session timer ─────────────────────────────────────────────────────────────

const sessionStart = Date.now();
function updateTimer() {
  const t = Math.floor((Date.now() - sessionStart) / 1000);
  const h = String(Math.floor(t / 3600)).padStart(2, '0');
  const m = String(Math.floor((t % 3600) / 60)).padStart(2, '0');
  const s = String(t % 60).padStart(2, '0');
  setText('session-timer', `${h}:${m}:${s}`);
}

// ── Boot ──────────────────────────────────────────────────────────────────────

lastFrameTs = performance.now();
pollStatus();
pollEvents();
setInterval(pollStatus,  1000);
setInterval(pollEvents,  5000);
setInterval(updateTimer, 1000);
