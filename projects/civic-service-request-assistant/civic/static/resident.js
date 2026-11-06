const $ = id => document.getElementById(id);
function node(tag, text) { const n = document.createElement(tag); n.textContent = text; return n; }
function result(id, text, error = false) { const out = $(id); out.replaceChildren(node('p', text)); out.className = `result${error ? ' error' : ''}`; return out; }
async function api(path, body) {
  const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the required fields and try again.');
  return data;
}
function action(formId, output, callback) {
  $(formId).addEventListener('submit', async event => {
    event.preventDefault(); const button = event.target.querySelector('button'); button.disabled = true;
    result(output, 'Working…');
    try { await callback(); } catch (error) { result(output, error.message, true); }
    finally { button.disabled = false; }
  });
}
action('request-form', 'request-result', async () => {
  const data = await api('/api/requests', Object.fromEntries(new FormData($('request-form'))));
  const out = result('request-result', `Request received. Current status: ${data.status}. Save this private receipt to check back:`);
  const receipt = node('input', ''); receipt.value = data.receipt; receipt.readOnly = true;
  receipt.className = 'receipt'; receipt.setAttribute('aria-label', 'Your private receipt'); out.append(receipt);
  $('receipt').value = data.receipt; $('request-form').reset();
});
action('faq-form', 'faq-result', async () => {
  const data = await api('/api/faq', {question:$('question').value});
  const out = result('faq-result', data.answer);
  if (data.citation) {
    const citation = node('p', `Source: ${data.citation.title}, ${data.citation.section}. `);
    citation.className = 'citation'; const link = node('a', 'Read this passage');
    link.href = `#${data.citation.id}`; link.onclick = () => { document.querySelector('details').open = true; };
    citation.append(link); out.append(citation);
  }
});
action('track-form', 'track-result', async () => {
  const data = await api('/api/track', {receipt:$('receipt').value});
  result('track-result', `Status: ${data.status.replaceAll('_',' ')}. Last updated: ${new Date(data.updated_at).toLocaleString()}.`);
});
async function load() {
  const config = await (await fetch('/api/config')).json();
  config.services.forEach(s => { const option = node('option', s.label); option.value = s.id; $('service').append(option); });
  const guides = await (await fetch('/api/guides')).json();
  guides.forEach(p => { const section = document.createElement('section'); section.id = p.id; section.append(node('h3', `${p.title}: ${p.section}`), node('p', p.passage)); $('guides').append(section); });
}
load().catch(() => result('request-result', 'The service desk is unavailable. Reload after starting the app.', true));
