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
let currentAccount = null;
let accountRegisterMode = false;

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  let data = null;
  if (response.status !== 204) {
    const contentType = response.headers.get('content-type') || '';
    data = contentType.includes('application/json') ? await response.json() : null;
  }
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

function safeAttribute(value) {
  return safeText(value).replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

function availabilityClass(status = 'Not specified') {
  return status.toLowerCase().replaceAll(' ', '-');
}

function availabilityLabel(status = 'Not specified') {
  return status === 'Not specified' ? 'Availability not stated' : `Listed ${status.toLowerCase()}`;
}

async function loadProviders() {
  const selectedCategory = filter.value;
  const params = new URLSearchParams();
  if (selectedCategory) params.set('category', selectedCategory);
  const searchText = document.querySelector('#provider-search').value.trim();
  if (searchText) params.set('q', searchText);
  const query = params.size ? `?${params.toString()}` : '';
  providers = await api(`/api/providers${query}`);
  const categories = await api('/api/categories');
  const previous = filter.value;
  filter.innerHTML = '<option value="">All services</option>' + categories
    .map((category) => `<option value="${safeAttribute(category.name)}">${safeText(category.name)}</option>`).join('');
  filter.value = previous;
  document.querySelector('#provider-count').textContent = `${providers.length} local ${providers.length === 1 ? 'pro' : 'pros'}`;
  if (providers.length === 0) {
    providerList.innerHTML = '<div class="empty-state">No providers in that category yet. Try another service.</div>';
    return;
  }
  providerList.innerHTML = providers.map((provider) => `
    <article class="provider-card">
      <div class="card-top"><div class="avatar">${safeText(provider.name.slice(0, 1).toUpperCase())}</div><span class="tag">${safeText(provider.category)}</span></div>
      <h3><a class="provider-link" href="/providers/${provider.id}">${safeText(provider.name)}</a></h3>
      ${provider.is_sample ? '<span class="sample-label">Synthetic demo provider · not a real business</span>' : ''}
      <p class="provider-meta">⌖ ${safeText(provider.area)}</p>
      <p class="provider-description">${safeText(provider.description || '')}</p>
      <div class="provider-card-status"><span class="availability ${safeAttribute(availabilityClass(provider.availability))}">${safeText(availabilityLabel(provider.availability))}</span></div>
      <div class="card-bottom">${isAdmin ? `<span class="phone">${safeText(provider.phone)}</span><div class="card-actions"><button class="manage-button edit-provider" data-provider-id="${provider.id}">Edit</button><button class="manage-button delete-provider" data-provider-id="${provider.id}">Remove</button>${provider.is_sample ? '<button class="request-button" disabled title="Synthetic demo profiles do not accept requests">Demo only</button>' : `<button class="request-button" data-provider-id="${provider.id}">Request service →</button>`}</div>` : provider.is_sample ? '<button class="request-button" disabled title="Synthetic demo profiles do not accept requests">Demo profile · requests disabled</button>' : `<button class="request-button" data-provider-id="${provider.id}">Request service →</button>`}</div>
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

function showProviderLoadError(error) {
  providerList.innerHTML = `<div class="empty-state" role="status">Could not load providers: ${safeText(error.message)}</div>`;
  document.querySelector('#provider-count').textContent = '';
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
    for (const field of ['name', 'category', 'area', 'phone', 'description', 'skills', 'availability']) providerForm.elements[field].value = provider[field] || (field === 'availability' ? 'Not specified' : '');
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
  if (currentAccount?.role === 'customer') {
    form.elements.customer_name.value = currentAccount.display_name;
    form.elements.customer_phone.value = currentAccount.phone;
  }
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

document.querySelector('#match-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = document.querySelector('#match-button');
  const results = document.querySelector('#match-results');
  const understanding = document.querySelector('#match-understanding');
  const description = document.querySelector('#match-description').value.trim();
  button.disabled = true;
  results.innerHTML = '<p class="match-message">Looking through the current listings…</p>';
  understanding.hidden = true;
  try {
    const result = await api('/api/recommendations', {
      method: 'POST', body: JSON.stringify({ description }),
    });
    const analysis = result.analysis || {};
    const details = [];
    if (analysis.category) details.push(`<span class="insight-chip">Service: ${safeText(analysis.category)}</span>`);
    if (analysis.required_skills?.length) details.push(`<span class="insight-chip">Skills: ${safeText(analysis.required_skills.slice(0, 4).join(', '))}${analysis.required_skills.length > 4 ? '…' : ''}</span>`);
    if (analysis.location) details.push(`<span class="insight-chip">Area: ${safeText(analysis.location)}${analysis.location_matched ? '' : ' · no exact area listing'}</span>`);
    if (analysis.urgency === 'urgent') details.push('<span class="insight-chip urgency-chip">Time-sensitive request</span>');
    understanding.innerHTML = details.length ? `<strong>We picked up</strong>${details.join('')}` : '';
    understanding.hidden = details.length === 0;
    results.innerHTML = `<p class="match-message">${safeText(result.message)}</p>` + result.matches.map((provider) => `
      <article class="match-card">
        <div class="match-card-top"><span class="tag">${safeText(provider.category)}</span><span class="availability ${safeAttribute(availabilityClass(provider.availability))}">${safeText(availabilityLabel(provider.availability))}</span></div>
        <h3><a class="provider-link" href="/providers/${provider.id}">${safeText(provider.name)}</a></h3>
        <p>Serving ${safeText(provider.area)}</p>
        ${provider.is_sample ? '<span class="sample-label">Synthetic demo provider · not a real business</span>' : ''}
        <div class="match-score">Listing fit: ${Math.round(provider.score * 100)}% <span>(not a probability or provider rating)</span></div>
        <ul class="match-reasons">${provider.reasons.map((reason) => `<li>${safeText(reason)}</li>`).join('')}</ul>
        <details class="match-breakdown"><summary>See match factors</summary><div>${Object.entries(provider.feature_scores || {}).filter(([, score]) => score !== null).map(([name, score]) => `<span>${safeText(name)} <strong>${Math.round(score * 100)}%</strong></span>`).join('')}</div><p>These are component signals combined into a listing-fit score. Availability is profile-stated.</p></details>
        ${provider.is_sample ? '<button class="request-button" disabled title="Synthetic demo profiles do not accept requests">Demo profile · requests disabled</button>' : `<button class="request-button" data-provider-id="${provider.id}">Request service →</button>`}
      </article>`).join('');
    results.querySelectorAll('.request-button').forEach((matchButton) => {
      matchButton.addEventListener('click', async () => {
        filter.value = '';
        await loadProviders();
        openRequest(Number(matchButton.dataset.providerId));
      });
    });
  } catch (error) {
    results.innerHTML = `<p class="match-message">${safeText(error.message)}</p>`;
  } finally { button.disabled = false; }
});

filter.addEventListener('change', () => loadProviders().catch(showProviderLoadError));
document.querySelector('#search-button').addEventListener('click', () => loadProviders().catch(showProviderLoadError));
document.querySelector('#provider-search').addEventListener('input', () => {
  window.clearTimeout(window.providerSearchTimer);
  window.providerSearchTimer = window.setTimeout(() => loadProviders().catch(showProviderLoadError), 220);
});
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

function setAccountMode(register) {
  accountRegisterMode = register;
  document.querySelector('#account-title').textContent = register ? 'Create an account' : 'Sign in';
  document.querySelector('#account-submit').textContent = register ? 'Create account' : 'Sign in';
  document.querySelector('#account-register-fields').hidden = !register;
  document.querySelector('#account-form').elements.password.autocomplete = register ? 'new-password' : 'current-password';
  for (const name of ['display_name', 'phone']) document.querySelector('#account-form').elements[name].required = register;
  updateProviderRegistrationFields();
}

function updateProviderRegistrationFields() {
  const form = document.querySelector('#account-form');
  const providerFields = document.querySelector('#provider-register-fields');
  const isProviderRegistration = accountRegisterMode && form.elements.role.value === 'provider';
  providerFields.hidden = !isProviderRegistration;
  form.elements.category.required = isProviderRegistration;
  form.elements.area.required = isProviderRegistration;
}

function showAccountDashboard() {
  document.querySelector('#account-title').textContent = currentAccount
    ? 'Your account' : accountRegisterMode ? 'Create an account' : 'Sign in';
  document.querySelector('#account-form').hidden = Boolean(currentAccount);
  document.querySelector('#account-dashboard').hidden = !currentAccount;
  document.querySelector('#account-welcome').textContent = currentAccount
    ? `Signed in as ${currentAccount.display_name} · ${currentAccount.role}` : '';
  document.querySelector('#account-button').textContent = currentAccount
    ? `${currentAccount.display_name} · Account` : 'Sign in / Create account';
  const actions = document.querySelector('#account-actions');
  const details = document.querySelector('#account-details');
  if (!currentAccount) {
    actions.innerHTML = '';
    details.innerHTML = '';
    return;
  }
  const primaryAction = currentAccount.role === 'customer'
    ? '<button type="button" class="manage-button" id="my-requests-button">My requests</button>'
    : '<button type="button" class="manage-button" id="provider-profile-button">Edit my listing</button><button type="button" class="manage-button" id="provider-requests-button">Requests for my services</button>';
  actions.innerHTML = primaryAction;
  details.innerHTML = '';
  const requestsButton = document.querySelector('#my-requests-button') || document.querySelector('#provider-requests-button');
  requestsButton?.addEventListener('click', loadAccountRequests);
  document.querySelector('#provider-profile-button')?.addEventListener('click', editProviderProfile);
}

async function loadAccountRequests() {
  const details = document.querySelector('#account-details');
  details.textContent = 'Loading requests…';
  try {
    const path = currentAccount.role === 'customer' ? '/api/my/requests' : '/api/provider/requests';
    const requests = await api(path);
    if (!requests.length) { details.innerHTML = '<p class="manage-note">No requests to show yet.</p>'; return; }
    details.innerHTML = requests.map((request) => `
      <article class="account-request"><strong>${safeText(currentAccount.role === 'customer' ? request.provider_name : request.customer_name)}</strong>
        <span class="status ${safeText(request.status)}">${safeText(request.status)}</span>
        ${currentAccount.role === 'provider' ? `<p>Customer contact: ${safeText(request.customer_phone)}</p>` : ''}
        <p>${safeText(request.details)}</p></article>`).join('');
  } catch (error) { details.textContent = error.message; }
}

async function editProviderProfile() {
  const details = document.querySelector('#account-details');
  details.textContent = 'Loading your listing…';
  try {
    const provider = await api('/api/provider/profile');
    details.innerHTML = `<form id="provider-profile-form" class="profile-edit-form">
      <label>Business name<input name="name" required minlength="2" maxlength="80" value="${safeAttribute(provider.name)}"></label>
      <label>Category<input name="category" required minlength="2" maxlength="50" value="${safeAttribute(provider.category)}"></label>
      <label>Area served<input name="area" required minlength="2" maxlength="80" value="${safeAttribute(provider.area)}"></label>
      <label>Business phone<input name="phone" required minlength="7" maxlength="20" value="${safeAttribute(provider.phone)}"></label>
      <label>Description<textarea name="description" maxlength="1000" rows="3">${safeText(provider.description)}</textarea></label>
      <label>Skills<input name="skills" maxlength="500" value="${safeAttribute(provider.skills)}"></label>
      <label>Current availability<select name="availability">${['Not specified', 'Available', 'Busy', 'Unavailable'].map((status) => `<option ${status === (provider.availability || 'Not specified') ? 'selected' : ''}>${status}</option>`).join('')}</select></label>
      <p class="form-message" role="status"></p><button class="button button-dark" type="submit">Save listing</button></form>`;
    details.querySelector('form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const message = form.querySelector('.form-message');
      const payload = Object.fromEntries(new FormData(form).entries());
      try {
        await api('/api/provider/profile', { method: 'PUT', body: JSON.stringify(payload) });
        message.textContent = 'Your listing has been updated.';
        await loadProviders();
      } catch (error) { message.textContent = error.message; }
    });
  } catch (error) { details.textContent = error.message; }
}

document.querySelector('#account-button').addEventListener('click', () => {
  document.querySelector('#account-message').textContent = '';
  if (!currentAccount) setAccountMode(false);
  showAccountDashboard();
  document.querySelector('#account-dialog').showModal();
});
document.querySelector('#close-account-dialog').addEventListener('click', () => document.querySelector('#account-dialog').close());
document.querySelector('#account-login-mode').addEventListener('click', () => setAccountMode(false));
document.querySelector('#account-register-mode').addEventListener('click', () => setAccountMode(true));
document.querySelector('#account-form').elements.role.addEventListener('change', updateProviderRegistrationFields);
document.querySelector('#account-dialog').addEventListener('click', (event) => {
  if (event.target === event.currentTarget) event.currentTarget.close();
});
document.querySelector('#account-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const message = document.querySelector('#account-message');
  const payload = Object.fromEntries(new FormData(form).entries());
  if (accountRegisterMode) {
    if (payload.role === 'customer') {
      delete payload.category;
      delete payload.area;
      delete payload.description;
      delete payload.skills;
    }
    try {
      const result = await api('/api/auth/register', { method: 'POST', body: JSON.stringify(payload) });
      currentAccount = result.account;
    } catch (error) { message.textContent = error.message; return; }
  } else {
    try {
      const result = await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ email: payload.email, password: payload.password }) });
      currentAccount = result.account;
    } catch (error) { message.textContent = error.message; return; }
  }
  form.reset();
  showAccountDashboard();
  if (currentAccount.role === 'customer') {
    document.querySelector('#request-form').elements.customer_name.value = currentAccount.display_name;
    document.querySelector('#request-form').elements.customer_phone.value = currentAccount.phone;
  }
  await loadProviders();
});
document.querySelector('#account-logout').addEventListener('click', async () => {
  try {
    await api('/api/auth/logout', { method: 'POST' });
    currentAccount = null;
    form.reset();
    showAccountDashboard();
    document.querySelector('#account-dialog').close();
    await loadProviders();
  } catch (error) { document.querySelector('#account-message').textContent = error.message; }
});

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
  currentAccount = session.account;
  updateAdminUI();
  showAccountDashboard();
}

loadAdminState().then(async () => {
  await Promise.all([loadProviders(), isAdmin ? loadRequests() : Promise.resolve()]);
  const requestedProvider = Number(new URLSearchParams(window.location.search).get('request'));
  if (requestedProvider) openRequest(requestedProvider);
}).catch((error) => {
  providerList.innerHTML = `<div class="empty-state">Could not connect to the app: ${safeText(error.message)}</div>`;
});

