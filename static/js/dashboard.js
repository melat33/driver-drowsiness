/**
 * dashboard.js — Live dashboard polling and Chart.js trend chart.
 *
 * Polls /status every 1 second to update all metric displays.
 * Polls /events every 5 seconds to refresh the event log table.
 * Maintains a 60-point rolling score history for the trend chart.
 */

// ── Trend chart setup ─────────────────────────────────────────────────────────

const MAX_POINTS    = 60;
const scoreHistory  = new Array(MAX_POINTS).fill(0);
const chartLabels   = Array.from({ length: MAX_POINTS }, (_, i) => (MAX_POINTS - i) + 's');

const chartColors = scoreHistory.map(() => '#00ff88');

const trendCtx = document.getElementById('trendChart').getContext('2d');
const trendChart = new Chart(trendCtx, {
  type: 'bar',
  data: {
    labels: chartLabels,
    datasets: [{
      data: [...scoreHistory],
      backgroundColor: [...chartColors],
      borderWidth: 0,
      borderRadius: 2,
    }]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 300 },
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: ctx => 'Score: ' + ctx.parsed.y.toFixed(0),
        }
      }
    },
    scales: {
      x: {
        grid: { color: '#1e2230' },
        ticks: {
          color: '#5a6070',
          font: { size: 9, family: 'monospace' },
          maxTicksLimit: 7,
          autoSkip: true,
        }
      },
      y: {
        min: 0,
        max: 100,
        grid: { color: '#1e2230' },
        ticks: {
          color: '#5a6070',
          font: { size: 9, family: 'monospace' },
          stepSize: 25,
        }
      }
    }
  }
});


// ── Gauge helpers ─────────────────────────────────────────────────────────────

const ARC_LENGTH = 228;   // total length of the SVG arc path

function updateGauge(score) {
  const pct    = Math.min(score, 100) / 100;
  const offset = ARC_LENGTH - (pct * ARC_LENGTH);
  const angle  = -90 + (pct * 180);   // −90° = far left, +90° = far right

  document.getElementById('score-arc').style.strokeDashoffset = offset.toFixed(1);
  document.getElementById('needle').style.transform = `rotate(${angle.toFixed(1)}deg)`;
  document.getElementById('score-text').textContent = Math.round(score);
}


// ── Status pill ───────────────────────────────────────────────────────────────

function updatePill(status) {
  const pill = document.getElementById('main-pill');
  pill.textContent  = status;
  pill.className    = `status-pill ${status}`;
}


// ── Score history + chart ─────────────────────────────────────────────────────

function pushScore(score) {
  scoreHistory.shift();
  scoreHistory.push(score);

  const newColors = scoreHistory.map(v =>
    v >= 70 ? '#ff3b3b' : v >= 40 ? '#f5a623' : '#00ff88'
  );

  trendChart.data.datasets[0].data             = [...scoreHistory];
  trendChart.data.datasets[0].backgroundColor  = newColors;
  trendChart.update('none');   // skip animation for smoother live updates
}


// ── DOM update helpers ────────────────────────────────────────────────────────

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}


// ── /status polling ───────────────────────────────────────────────────────────

async function pollStatus() {
  try {
    const res  = await fetch('/status');
    if (!res.ok) return;
    const data = await res.json();

    const score  = data.fatigue_score ?? 0;
    const status = data.status ?? 'NORMAL';

    // Gauge + pill
    updateGauge(score);
    updatePill(status);

    // Live signals
    setText('v-ear',    data.ear   != null ? data.ear.toFixed(3)   : '—');
    setText('v-mar',    data.mar   != null ? data.mar.toFixed(3)   : '—');
    setText('v-yaw',    data.yaw   != null ? data.yaw.toFixed(1) + '°' : '—');
    setText('v-pitch',  data.pitch != null ? data.pitch.toFixed(1) + '°' : '—');
    setText('v-blinks', data.blinks   ?? 0);
    setText('v-yawns',  data.yawns    ?? 0);
    setText('v-drops',  data.head_drops ?? 0);
    setText('v-cf',     data.blinks   ?? 0);

    // Session totals
    setText('s-blinks', data.blinks       ?? 0);
    setText('s-yawns',  data.yawns        ?? 0);
    setText('s-alerts', data.alerts_fired ?? 0);
    setText('s-drops',  data.head_drops   ?? 0);

    // Trend chart
    pushScore(score);

  } catch (_) {
    // Network error — stay silent, try again next tick
  }
}


// ── /events polling ───────────────────────────────────────────────────────────

async function pollEvents() {
  try {
    const res    = await fetch('/events');
    if (!res.ok) return;
    const events = await res.json();

    const tbody = document.getElementById('event-tbody');
    if (!events.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty-row">No events yet</td></tr>';
      return;
    }

    tbody.innerHTML = events.map(ev => `
      <tr>
        <td>${ev.timestamp ?? '—'}</td>
        <td>${ev.event_type ?? '—'}</td>
        <td>${ev.fatigue_score != null ? ev.fatigue_score.toFixed(0) : '—'}</td>
        <td><span class="evt-badge ${ev.status ?? ''}">${ev.status ?? '—'}</span></td>
        <td>${ev.ear != null ? ev.ear.toFixed(3) : '—'}</td>
        <td>${ev.mar != null ? ev.mar.toFixed(3) : '—'}</td>
      </tr>
    `).join('');

  } catch (_) {}
}


// ── Session timer ─────────────────────────────────────────────────────────────

const sessionStart = Date.now();

function updateTimer() {
  const elapsed = Math.floor((Date.now() - sessionStart) / 1000);
  const h = String(Math.floor(elapsed / 3600)).padStart(2, '0');
  const m = String(Math.floor((elapsed % 3600) / 60)).padStart(2, '0');
  const s = String(elapsed % 60).padStart(2, '0');
  setText('session-timer', `${h}:${m}:${s}`);
}


// ── Start polling ─────────────────────────────────────────────────────────────

pollStatus();
pollEvents();
setInterval(pollStatus,  1000);
setInterval(pollEvents,  5000);
setInterval(updateTimer, 1000);