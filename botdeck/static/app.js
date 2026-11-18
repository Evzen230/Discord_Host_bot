const $ = (id) => document.getElementById(id);
const states = {running:'Běží',exited:'Zastaven',created:'Vytvořen',restarting:'Restartuje',paused:'Pozastaven',dead:'Chyba',not_deployed:'Nenasazen',error:'Chyba',removing:'Odstraňuje se'};
let busy = false;
let refreshing = false;
let logBot = null;
let logsLoading = false;
let noticeTimer;
const mb = (bytes) => bytes == null ? '—' : `${Math.round(bytes / 1048576)} MB`;
function uptime(start) {
  if (!start) return '—';
  const seconds = Math.max(0, (Date.now() - new Date(start).getTime()) / 1000);
  if (!Number.isFinite(seconds)) return '—';
  if (seconds >= 86400) return `${Math.floor(seconds / 86400)} d ${Math.floor(seconds % 86400 / 3600)} h`;
  if (seconds >= 3600) return `${Math.floor(seconds / 3600)} h ${Math.floor(seconds % 3600 / 60)} m`;
  return `${Math.floor(seconds / 60)} min`;
}
async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {credentials:'same-origin',cache:'no-store',...options});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Požadavek selhal.');
  return data;
}
function node(tag, className, text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text != null) item.textContent = text;
  return item;
}
function notify(message, failed = false) {
  $('notice').textContent = message;
  $('notice').classList.toggle('failure', failed);
  $('notice').hidden = false;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => {$('notice').hidden = true;}, 6000);
}
function button(label, onClick, disabled = false) {
  const item = node('button', '', label);
  item.disabled = disabled || busy;
  item.addEventListener('click', onClick);
  return item;
}
function card(bot) {
  const root = node('article','bot');
  const heading = node('div','bot-heading');
  const identity = node('div','bot-identity');
  identity.append(node('div','avatar',bot.name.slice(0,1).toUpperCase()));
  const title = node('div');
  title.append(node('h3','',bot.name), node('p','',bot.description || bot.id));
  identity.append(title);
  heading.append(identity,node('span',`badge ${bot.status}`,states[bot.status] || bot.status));
  root.append(heading);
  const stats = node('div','bot-stats');
  for (const [label,value] of [['CPU',bot.cpu_percent == null ? '—' : `${bot.cpu_percent} %`],['RAM',mb(bot.memory_bytes)],['Doba běhu',bot.status === 'running' ? uptime(bot.started_at) : '—']]) {
    const item = node('div'); item.append(node('small','',label),node('strong','',value)); stats.append(item);
  }
  root.append(stats, node('div','connection',bot.error || 'Discord připojení: neověřeno'));
  const actions = node('div','bot-actions');
  const missing = bot.status === 'not_deployed' || bot.status === 'error';
  actions.append(button('Logy',() => openLogs(bot),missing));
  actions.append(button('Spustit',() => operate(bot,'start'),!['exited','created'].includes(bot.status)));
  actions.append(button('Restart',() => operate(bot,'restart'),bot.status !== 'running'));
  actions.append(button('Zastavit',() => operate(bot,'stop'),bot.status !== 'running'));
  if (bot.dashboard_url) {
    const link = node('a','dashboard-link','Dashboard ↗');
    const url = new URL(bot.dashboard_url);
    if (['https:','http:'].includes(url.protocol)) {link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; actions.append(link);}
  }
  root.append(actions); return root;
}
async function refresh() {
  if (refreshing) return;
  refreshing = true;
  $('refresh').disabled = true;
  try {
    const data = await api('/overview');
    const running = data.bots.filter(bot => bot.status === 'running');
    $('running').textContent = running.length;
    $('total').textContent = `z ${data.bots.length} registrovaných botů`;
    const measured = running.filter(bot => bot.memory_bytes != null);
    $('bot-memory').textContent = running.length && !measured.length ? '—' : mb(measured.reduce((sum, bot) => sum + bot.memory_bytes,0));
    $('host-memory').textContent = mb(data.host?.memory_used_bytes);
    $('host-total').textContent = data.host ? `z ${mb(data.host.memory_total_bytes)} celkem` : 'Měření hostitele není dostupné';
    $('host-load').textContent = data.host?.load_1m?.toFixed(2) ?? '—';
    $('count').textContent = data.bots.length;
    $('bot-list').replaceChildren(...data.bots.map(card));
    $('empty').hidden = data.bots.length !== 0;
    $('updated').textContent = `Aktualizováno ${new Date(data.updated_at).toLocaleTimeString('cs-CZ')}`;
    $('error').hidden = true;
  } catch (error) {
    $('error').textContent = `${error.message} Zobrazené údaje mohou být zastaralé.`;
    $('error').hidden = false;
  } finally { refreshing = false; $('refresh').disabled = false; }
}
async function operate(bot, action) {
  if (busy) return;
  const labels = {start:'Spustit',stop:'Zastavit',restart:'Restartovat'};
  if (!confirm(`${labels[action]} bota „${bot.name}“?`)) return;
  busy = true;
  document.querySelectorAll('.bot-actions button').forEach(button => {button.disabled = true;});
  try {await api(`/bots/${bot.id}/${action}`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}); notify('Operace dokončena.');}
  catch (error) {notify(error.message,true);}
  finally {busy = false; await refresh();}
}
async function readLogs() {
  if (!logBot || logsLoading) return;
  logsLoading = true;
  const id = logBot.id;
  try {
    const data = await api(`/bots/${id}/logs`);
    if (logBot?.id === id) $('logs-content').textContent = data.logs || 'Zatím žádné logy.';
  } catch (error) {if (logBot?.id === id) $('logs-content').textContent = error.message;}
  finally {logsLoading = false;}
}
function openLogs(bot) {logBot = bot; $('logs-title').textContent = `Logy / ${bot.name}`; $('logs-content').textContent = 'Načítám…'; $('logs-dialog').showModal(); readLogs();}
$('close-logs').addEventListener('click',() => $('logs-dialog').close());
$('logs-dialog').addEventListener('close',() => {logBot = null;});
$('reload-logs').addEventListener('click',readLogs);
$('refresh').addEventListener('click',refresh);
setInterval(() => {if (!document.hidden && !busy) refresh();},15000);
setInterval(() => {if (!document.hidden && logBot) readLogs();},3000);
refresh();

