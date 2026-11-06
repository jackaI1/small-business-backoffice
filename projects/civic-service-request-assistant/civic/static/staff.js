const $ = id => document.getElementById(id);
let token = '', config, selected;
const label = value => value.replaceAll('_', ' ');
function node(tag, text) { const n = document.createElement(tag); n.textContent = text; return n; }
function message(text, error = false) { $('staff-message').textContent = text; $('staff-message').className = `result${error ? ' error' : ''}`; }
async function api(path, method = 'GET', body) {
  const response = await fetch(path, {method, headers:{Authorization:`Bearer ${token}`, 'Content-Type':'application/json'}, ...(body ? {body:JSON.stringify(body)} : {})});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the required fields and try again.');
  return data;
}
async function queue() {
  const params = new URLSearchParams({status:$('status-filter').value, service:$('service-filter').value});
  const rows = await api(`/api/staff/requests?${params}`);
  $('workspace').hidden = false; $('access-form').hidden = true;
  $('queue').replaceChildren(); $('queue-count').textContent = `${rows.length} request(s) shown. Newest first, up to 200. All timestamps use your local time.`;
  rows.forEach(row => {
    const button = node('button', `${row.service}: ${row.location}`); button.className = 'queue-item';
    button.append(node('span', `${label(row.status)} • ${new Date(row.created_at).toLocaleDateString()}`));
    button.onclick = () => open(row.id).catch(e => message(e.message, true)); $('queue').append(button);
  });
  if (!rows.length) $('queue').append(node('p', 'No requests match. Send a fictional report from the resident desk or change the filters.'));
}
async function open(id) {
  selected = id;
  const row = await api(`/api/staff/requests/${id}`), detail = $('detail');
  detail.replaceChildren(node('h2', `Request ${row.id.slice(0,8)}`));
  const dl = document.createElement('dl');
  [['Status', label(row.status)], ['Service', row.service], ['Location', row.location], ['Description', row.description], ['Contact', row.contact || 'Not provided']].forEach(([key,value]) => {
    const group = document.createElement('div'); group.className = 'detail-row'; group.append(node('dt', key), node('dd', value)); dl.append(group);
  }); detail.append(dl);
  const next = config.transitions[row.status];
  if (next.length) {
    const form = document.createElement('form');
    const statusLabel = node('label', 'Next status'); statusLabel.htmlFor = 'next-status';
    const select = document.createElement('select'); select.id = 'next-status';
    next.forEach(value => { const option = node('option', label(value)); option.value = value; select.append(option); });
    const noteLabel = node('label', 'Decision or work note'); noteLabel.htmlFor = 'note';
    const note = document.createElement('textarea'); note.id = 'note'; note.required = true; note.minLength = 3; note.maxLength = 1000;
    const save = node('button', 'Save status change'); save.type = 'submit';
    form.append(statusLabel, select, noteLabel, note, save);
    form.onsubmit = async event => {
      event.preventDefault(); save.disabled = true;
      try { await api(`/api/staff/requests/${id}/status`, 'POST', {status:select.value, note:note.value, version:row.version}); await queue(); await open(id); message('Status saved.'); }
      catch (e) { message(e.message, true); } finally { save.disabled = false; }
    }; detail.append(form);
  } else detail.append(node('p', 'This request is closed.'));
  detail.append(node('h3', 'Request history')); const history = document.createElement('ol');
  row.events.forEach(event => history.append(node('li', `${label(event.status)}: ${event.note} (${new Date(event.at).toLocaleString()})`))); detail.append(history);
  const disclosure = document.createElement('details'); disclosure.append(node('summary', 'Preview safe list export'));
  disclosure.append(node('p', 'Only the fields below leave this desk. Location, description, contact and staff notes are excluded.'));
  const preview = await api(`/api/staff/requests/${id}/export`); disclosure.append(node('pre', JSON.stringify(preview, null, 2)));
  const send = node('button', 'Export to local list'); send.className = 'secondary'; send.type = 'button';
  send.onclick = async () => { send.disabled = true; try { const result = await api(`/api/staff/requests/${id}/export`, 'POST'); message(`Exported to local list item ${result.id}.`); } catch (e) { message(e.message, true); } finally { send.disabled = false; } };
  disclosure.append(send); detail.append(disclosure);
}
$('access-form').onsubmit = async event => { event.preventDefault(); token = $('token').value; $('token').value = ''; try { await queue(); message('Staff desk opened.'); } catch (e) { token = ''; message(e.message, true); } };
$('lock').onclick = () => { token = ''; selected = null; $('workspace').hidden = true; $('access-form').hidden = false; $('queue').replaceChildren(); $('detail').replaceChildren(); message('Desk locked.'); };
async function refresh() { try { await queue(); if (selected) await open(selected); } catch (e) { message(e.message, true); } }
$('refresh').onclick = refresh; $('status-filter').onchange = refresh; $('service-filter').onchange = refresh;
fetch('/api/config').then(r => r.json()).then(data => {
  config = data; Object.keys(config.transitions).forEach(s => { const option = node('option', label(s)); option.value = s; $('status-filter').append(option); });
  config.services.forEach(s => { const option = node('option', s.label); option.value = s.id; $('service-filter').append(option); });
}).catch(() => message('Unable to load desk configuration. Reload after starting the app.', true));
