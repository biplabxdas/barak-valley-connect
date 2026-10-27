const providerList = document.querySelector('#provider-list');
const filter = document.querySelector('#category-filter');
const dialog = document.querySelector('#request-dialog');
const form = document.querySelector('#request-form');
const providerDialog = document.querySelector('#provider-dialog');
const providerForm = document.querySelector('#provider-form');
const adminDialog = document.querySelector('#admin-login-dialog');
const adminForm = document.querySelector('#admin-login-form');
let providers = [];
let isAdmin = false;

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    const detail = data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg).join(', ')
      : detail;
    throw new Error(message || 'Something went wrong. Please try again.');
  }
  return data;
}

function safeText(value) {
  const span = document.createElement('span');
  span.textContent = value;
  return span.innerHTML;
}

async function loadProviders() {
  const selectedCategory = filter.value;
  const query = selectedCategory ? `?category=${encodeURIComponent(selectedCategory)}` : '';
  providers = await api(`/api/providers${query}`);
  const allProviders = selectedCategory ? await api('/api/providers') : providers;
  const categories = [...new Set(allProviders.map((provider) => provider.category))];
  const previous = filter.value;
  filter.innerHTML = '<option value="">All services</option>' + categories
    .map((category) => `<option value="${safeText(category)}">${safeText(category)}</option>`).join('');
  filter.value = previous;
  document.querySelector('#provider-count').textContent = `${providers.length} local ${providers.length === 1 ? 'pro' : 'pros'}`;
  if (providers.length === 0) {
    providerList.innerHTML = '<div class="empty-state">No providers in that category yet. Try another service.</div>';
    return;
  }
  providerList.innerHTML = providers.map((provider) => `
    <article class="provider-card">
      <div class="card-top"><div class="avatar">${safeText(provider.name.slice(0, 1).toUpperCase())}</div><span class="tag">${safeText(provider.category)}</span></div>
      <h3>${safeText(provider.name)}</h3>
      <p class="provider-meta">⌖ ${safeText(provider.area)}</p>
      <div class="card-bottom">${isAdmin ? `<span class="phone">${safeText(provider.phone)}</span><div class="card-actions"><button class="manage-button edit-provider" data-provider-id="${provider.id}">Edit</button><button class="manage-button delete-provider" data-provider-id="${provider.id}">Remove</button><button class="request-button" data-provider-id="${provider.id}">Request service →</button></div>` : `<button class="request-button" data-provider-id="${provider.id}">Request service →</button>`}</div>
    </article>`).join('');
  providerList.querySelectorAll('.request-button').forEach((button) => {
    button.addEventListener('click', () => openRequest(Number(button.dataset.providerId)));
  });
  providerList.querySelectorAll('.edit-provider').forEach((button) => {
    button.addEventListener('click', () => openProviderEditor(Number(button.dataset.providerId)));
  });
  providerList.querySelectorAll('.delete-provider').forEach((button) => {
    button.addEventListener('click', () => removeProvider(Number(button.dataset.providerId)));
  });
  if (isAdmin) await loadSummary();
}

async function loadSummary() {
  const totals = await api('/api/summary');
  document.querySelector('#request-count').textContent = `${totals.requests} total · ${totals.pending} pending · ${totals.completed} completed`;
}

function openProviderEditor(providerId = null) {
  providerForm.reset();
  document.querySelector('#provider-form-message').textContent = '';
  const provider = providers.find((item) => item.id === providerId);
  document.querySelector('#provider-form-title').textContent = provider ? 'Update provider' : 'Add a provider';
  if (provider) {
    for (const field of ['name', 'category', 'area', 'phone']) providerForm.elements[field].value = provider[field];
    providerForm.elements.provider_id.value = provider.id;
  }
  providerDialog.showModal();
}

async function removeProvider(providerId) {
  const provider = providers.find((item) => item.id === providerId);
  if (!provider || !window.confirm(`Remove ${provider.name} from the directory?`)) return;
  try {
    await api(`/api/providers/${providerId}`, { method: 'DELETE' });
    filter.value = '';
    await loadProviders();
  } catch (error) { window.alert(error.message); }
}

function openRequest(providerId) {
  const provider = providers.find((item) => item.id === providerId);
  if (!provider) return;
  document.querySelector('#service-id').value = provider.id;
  document.querySelector('#selected-provider').textContent = `${provider.name} · ${provider.category}`;
  document.querySelector('#form-message').textContent = '';
  dialog.showModal();
}

async function loadRequests() {
  if (!isAdmin) return;
  const requests = await api('/api/requests');
  const list = document.querySelector('#request-list');
  if (requests.length === 0) {
    list.innerHTML = '<div class="empty-state">Your requests will appear here after you contact a local pro.</div>';
    return;
  }
  list.innerHTML = requests.map((request) => `
    <article class="request-row">
      <div><strong>${safeText(request.customer_name)}</strong><div class="request-sub">${safeText(request.customer_phone)}</div></div>
      <div><strong>${safeText(request.provider_name)}</strong><div class="request-sub">${safeText(request.category)}</div></div>
      <div><span class="status ${safeText(request.status)}">${safeText(request.status)}</span><div class="request-sub">${safeText(request.details)}</div></div>
      <select class="status-control" aria-label="Change request status" data-request-id="${request.id}">
        ${['Pending', 'Accepted', 'Completed', 'Cancelled'].map((status) => `<option ${status === request.status ? 'selected' : ''}>${status}</option>`).join('')}
      </select><button class="manage-button delete-request" data-request-id="${request.id}">Delete</button>
    </article>`).join('');
  list.querySelectorAll('.status-control').forEach((control) => {
    control.addEventListener('change', async () => {
      try {
        await api(`/api/requests/${control.dataset.requestId}/status`, {
          method: 'PATCH', body: JSON.stringify({ status: control.value }),
        });
        await loadRequests();
        await loadSummary();
      } catch (error) { window.alert(error.message); }
    });
  });
  list.querySelectorAll('.delete-request').forEach((button) => {
    button.addEventListener('click', async () => {
      if (!window.confirm('Permanently delete this service request?')) return;
      try {
        await api(`/api/requests/${button.dataset.requestId}`, { method: 'DELETE' });
        await loadRequests();
        await loadSummary();
      } catch (error) { window.alert(error.message); }
    });
  });
}

filter.addEventListener('change', loadProviders);
document.querySelector('#search-button').addEventListener('click', loadProviders);
document.querySelector('#close-dialog').addEventListener('click', () => dialog.close());
document.querySelector('#add-provider-button').addEventListener('click', () => openProviderEditor());
document.querySelector('#close-provider-dialog').addEventListener('click', () => providerDialog.close());
document.querySelector('#close-admin-dialog').addEventListener('click', () => adminDialog.close());
dialog.addEventListener('click', (event) => { if (event.target === dialog) dialog.close(); });
providerDialog.addEventListener('click', (event) => { if (event.target === providerDialog) providerDialog.close(); });
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const formData = new FormData(form);
  const payload = Object.fromEntries(formData.entries());
  payload.service_id = Number(payload.service_id);
  const message = document.querySelector('#form-message');
  try {
    await api('/api/requests', { method: 'POST', body: JSON.stringify(payload) });
    form.reset();
    document.querySelector('#success-message').textContent = 'Your request was sent. The website owner can review it in the management area.';
    document.querySelector('#success-message').hidden = false;
    window.setTimeout(() => { dialog.close(); document.querySelector('#success-message').hidden = true; }, 2200);
  } catch (error) { message.textContent = error.message; }
});

providerForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const formData = new FormData(providerForm);
  const payload = Object.fromEntries(formData.entries());
  const providerId = payload.provider_id;
  delete payload.provider_id;
  const message = document.querySelector('#provider-form-message');
  try {
    await api(providerId ? `/api/providers/${providerId}` : '/api/providers', {
      method: providerId ? 'PUT' : 'POST', body: JSON.stringify(payload),
    });
    providerDialog.close();
    filter.value = '';
    await loadProviders();
  } catch (error) { message.textContent = error.message; }
});

function updateAdminUI() {
  document.querySelectorAll('.admin-only').forEach((section) => { section.hidden = !isAdmin; });
  document.querySelector('#admin-button').textContent = isAdmin ? 'Website owner · Sign out' : 'Website owner sign in';
}

document.querySelector('#admin-button').addEventListener('click', async () => {
  if (!isAdmin) {
    document.querySelector('#admin-message').textContent = '';
    adminDialog.showModal();
    return;
  }
  try {
    await api('/api/auth/admin-logout', { method: 'POST' });
    isAdmin = false;
    updateAdminUI();
    await loadProviders();
  } catch (error) { window.alert(error.message); }
});

adminForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = document.querySelector('#admin-message');
  try {
    await api('/api/auth/admin-login', {
      method: 'POST', body: JSON.stringify({ password: new FormData(adminForm).get('password') }),
    });
    isAdmin = true;
    adminForm.reset();
    adminDialog.close();
    updateAdminUI();
    await Promise.all([loadProviders(), loadRequests()]);
  } catch (error) { message.textContent = error.message; }
});

async function loadAdminState() {
  const session = await api('/api/auth/me');
  isAdmin = session.is_admin;
  updateAdminUI();
}

loadAdminState().then(() => Promise.all([loadProviders(), isAdmin ? loadRequests() : Promise.resolve()])).catch((error) => {
  providerList.innerHTML = `<div class="empty-state">Could not connect to the app: ${safeText(error.message)}</div>`;
});

