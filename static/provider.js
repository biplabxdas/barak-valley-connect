const profile = document.querySelector('#profile-content');
const providerId = Number(window.location.pathname.split('/').pop());

function safeText(value) {
  const span = document.createElement('span');
  span.textContent = value || '';
  return span.innerHTML;
}

async function loadProfile() {
  try {
    const response = await fetch(`/api/providers/${providerId}`);
    const provider = await response.json();
    if (!response.ok) throw new Error(provider.detail || 'Provider could not be found.');
    document.title = `${provider.name} — Barak Valley Connect`;
    const skills = (provider.skills || '').split(',').map((skill) => skill.trim()).filter(Boolean);
    profile.innerHTML = `
      <div class="profile-top"><span class="avatar">${safeText(provider.name.slice(0, 1).toUpperCase())}</span><span class="tag">${safeText(provider.category)}</span></div>
      <p class="eyebrow">LOCAL SERVICE PROVIDER</p>
      <h1>${safeText(provider.name)}</h1>
      <p class="profile-area">⌖ Serving ${safeText(provider.area)}</p>
      ${provider.is_sample ? '<p class="sample-label">Sample listing · local demo data</p>' : ''}
      <p class="profile-description">${safeText(provider.description || 'This provider has not added a description yet.')}</p>
      ${skills.length ? `<h2>Services and skills</h2><ul class="skill-list">${skills.map((skill) => `<li>${safeText(skill)}</li>`).join('')}</ul>` : ''}
      <a class="button button-dark profile-cta" href="/?request=${provider.id}">Request this service →</a>
      <p class="match-note">Contact details are shared through the service request process.</p>`;
  } catch (error) {
    profile.innerHTML = `<div class="empty-state">${safeText(error.message)}</div>`;
  }
}

loadProfile();
