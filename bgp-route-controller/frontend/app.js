const API_BASE = 'http://127.0.0.1:8000';

function roleHeader() {
  return { 'x-user-role': document.getElementById('active-role').value };
}

async function loadRouters() {
  const response = await fetch(`${API_BASE}/routers`);
  const routers = await response.json();
  const list = document.getElementById('router-list');
  document.getElementById('router-count').textContent = routers.length;
  list.innerHTML = routers.map((router) => `
    <article class="item">
      <strong>${router.name}</strong>
      <div>${router.host}</div>
      <div>${router.vendor} • ${router.status}</div>
      <button data-connect-router-id="${router.id}" class="mini-btn">Connect</button>
    </article>
  `).join('');
}

async function loadSessionSummary() {
  const response = await fetch(`${API_BASE}/session-summary`);
  const summary = await response.json();
  document.getElementById('session-count').textContent = summary.connected_routers.length;
  document.getElementById('session-summary').innerHTML = `
    <strong>Connected routers:</strong> ${summary.connected_routers.length}<br />
    <strong>Total routers:</strong> ${summary.router_count}<br />
    <strong>Policies:</strong> ${summary.policy_count}<br />
    <strong>Active mode:</strong> ${summary.active_mode}
  `;
}

async function loadPolicies() {
  const response = await fetch(`${API_BASE}/policies`);
  const policies = await response.json();
  const list = document.getElementById('policy-list');
  document.getElementById('policy-count').textContent = policies.length;
  list.innerHTML = policies.map((policy) => `
    <article class="item">
      <strong>${policy.prefix}</strong>
      <div>Neighbor: ${policy.neighbor}</div>
      <div>Weight: ${policy.weight} • ${policy.status}</div>
      <div class="button-row">
        <button data-policy-id="${policy.id}" class="mini-btn">Apply</button>
        <button data-delete-policy-id="${policy.id}" class="mini-btn danger-btn">Delete</button>
      </div>
    </article>
  `).join('');
}

async function loadWorkflowLog() {
  const response = await fetch(`${API_BASE}/capabilities`);
  const data = await response.json();
  const log = document.getElementById('workflow-log');
  log.innerHTML = data.history.map((entry) => {
    const durationMatch = entry.details.match(/duration_ms=(\d+)/);
    const durationText = durationMatch ? `Duration: ${durationMatch[1]} ms` : '';
    const configMatch = entry.details.match(/config:\\n([\s\S]*)$/);
    const configText = configMatch ? `<pre>${configMatch[1].trim()}</pre>` : '';
    return `
      <article class="item">
        <strong>${entry.name}</strong>
        <div>${entry.details.replace(/; config:\\n[\s\S]*$/, '')}</div>
        <div>${new Date(entry.created_at).toLocaleString()} • ${entry.actor_role} • ${entry.status}</div>
        ${durationText ? `<div>${durationText}</div>` : ''}
        ${configText}
      </article>
    `;
  }).join('');
}

async function loadCapabilities() {
  const response = await fetch(`${API_BASE}/capabilities`);
  const data = await response.json();
  document.getElementById('capability-state').innerHTML = `
    <strong>Mode:</strong> ${data.mode}<br />
    <strong>Active router:</strong> ${data.active_router_id || 'None'}<br />
    <strong>ACL ports:</strong> ${data.acl_ports.join(', ')}<br />
    <strong>Last action:</strong> ${data.last_action || 'None'}
  `;
  document.getElementById('capability-history').innerHTML = data.history.map((entry) => `
    <article class="item">
      <strong>${entry.name}</strong>
      <div>${entry.details}</div>
      <div>${entry.actor_role} • ${entry.status}</div>
    </article>
  `).join('');
}

async function loadUsers() {
  const response = await fetch(`${API_BASE}/users`);
  const users = await response.json();
  const list = document.getElementById('user-list');
  list.innerHTML = users.map((user) => `
    <article class="item">
      <strong>${user.username}</strong>
      <div>${user.role}</div>
      <button data-delete-user-id="${user.id}" class="mini-btn danger-btn">Delete</button>
    </article>
  `).join('');
}

async function createRouter(event) {
  event.preventDefault();
  const body = {
    id: document.getElementById('router-id').value,
    name: document.getElementById('router-name').value,
    host: document.getElementById('router-host').value,
    vendor: document.getElementById('router-vendor').value || 'FRRouting',
    status: 'unknown',
  };

  await fetch(`${API_BASE}/routers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  event.target.reset();
  await loadRouters();
}

async function createPolicy(event) {
  event.preventDefault();
  const body = {
    router_id: document.getElementById('policy-router').value,
    prefix: document.getElementById('policy-prefix').value,
    neighbor: document.getElementById('policy-neighbor').value,
    weight: Number(document.getElementById('policy-weight').value),
  };

  await fetch(`${API_BASE}/policies`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  event.target.reset();
  await loadPolicies();
}

async function createUser(event) {
  event.preventDefault();
  const body = {
    id: document.getElementById('user-id').value,
    username: document.getElementById('username').value,
    role: document.getElementById('user-role').value,
    active: true,
  };

  await fetch(`${API_BASE}/users`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...roleHeader() },
    body: JSON.stringify(body),
  });

  event.target.reset();
  await loadUsers();
}

async function sendCapability(path, payload = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...roleHeader() },
    body: JSON.stringify(payload),
  });
  if (response.ok) {
    await loadCapabilities();
    await loadWorkflowLog();
  }
}

async function executeSelectedCapability(event) {
  if (event && event.type === 'keydown' && event.key !== 'Enter') return;
  if (event && event.type === 'keydown') {
    event.preventDefault();
  }
  const capability = document.getElementById('capability-select').value;
  const payload = {
    capability,
    router_id: document.getElementById('capability-router').value,
    prefix: document.getElementById('capability-prefix').value,
    circuit: document.getElementById('capability-circuit')?.value || 'GigabitEthernet0/0',
  };
  if (capability === 'acl-filters') {
    payload.ports = [53, 123, 389];
  }
  await sendCapability('/capabilities/execute', payload);
}

async function applyPolicy(event) {
  const button = event.target.closest('button[data-policy-id]');
  if (!button) return;
  const policyId = button.getAttribute('data-policy-id');
  const response = await fetch(`${API_BASE}/policies/${policyId}/apply`, { method: 'POST' });
  const result = await response.json();
  document.getElementById('command-preview').innerHTML = `
    <strong>Applied policy:</strong> ${policyId}<br />
    <strong>Commands:</strong><br />
    ${result.commands.map((command) => `• ${command}`).join('<br />')}
  `;
  await loadPolicies();
  await loadWorkflowLog();
}

async function deletePolicy(event) {
  const button = event.target.closest('button[data-delete-policy-id]');
  if (!button) return;
  const policyId = button.getAttribute('data-delete-policy-id');
  await fetch(`${API_BASE}/policies/${policyId}`, {
    method: 'DELETE',
    headers: roleHeader(),
  });
  await loadPolicies();
}

async function deleteUser(event) {
  const button = event.target.closest('button[data-delete-user-id]');
  if (!button) return;
  const userId = button.getAttribute('data-delete-user-id');
  await fetch(`${API_BASE}/users/${userId}`, {
    method: 'DELETE',
    headers: roleHeader(),
  });
  await loadUsers();
}

async function connectRouter(event) {
  const button = event.target.closest('button[data-connect-router-id]');
  if (!button) return;
  const routerId = button.getAttribute('data-connect-router-id');
  await fetch(`${API_BASE}/routers/${routerId}/connect`, { method: 'POST' });
  await loadRouters();
  await loadSessionSummary();
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('router-form').addEventListener('submit', createRouter);
  document.getElementById('policy-form').addEventListener('submit', createPolicy);
  document.getElementById('user-form').addEventListener('submit', createUser);
  document.getElementById('policy-list').addEventListener('click', (event) => {
    applyPolicy(event);
    deletePolicy(event);
  });
  document.getElementById('router-list').addEventListener('click', connectRouter);
  document.getElementById('user-list').addEventListener('click', deleteUser);
  document.getElementById('btn-execute-capability').addEventListener('click', executeSelectedCapability);
  document.getElementById('capability-prefix').addEventListener('keydown', executeSelectedCapability);
  document.getElementById('capability-select').addEventListener('keydown', executeSelectedCapability);
  loadRouters();
  loadPolicies();
  loadCapabilities();
  loadWorkflowLog();
  loadSessionSummary();
  loadUsers();
});
