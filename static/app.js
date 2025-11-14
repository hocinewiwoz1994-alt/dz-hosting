/* UI helpers */
const toastHost = (() => {
  const root = document.createElement('div');
  root.className = 'toast';
  document.addEventListener('DOMContentLoaded', () => document.body.appendChild(root));
  return root;
})();

function toast(msg, type='info', ms=2600){
  const el = document.createElement('div');
  el.className='item';
  el.innerHTML=msg;
  if(type==='ok') el.style.borderLeftColor='var(--success)';
  if(type==='warn') el.style.borderLeftColor='var(--warning)';
  if(type==='err') el.style.borderLeftColor='var(--danger)';
  toastHost.appendChild(el);
  setTimeout(()=>el.remove(), ms);
}

function copyText(text){
  navigator.clipboard.writeText(text).then(
    ()=> toast('Copied successfully ✅','ok'),
    ()=> toast('Copy failed ❌','err')
  );
}

(function(){
  document.addEventListener('DOMContentLoaded', ()=>{
    document.querySelectorAll('[data-copy]').forEach(el=>{
      el.classList.add('copy');
      el.addEventListener('click', ()=> copyText(el.getAttribute('data-copy')));
      el.title='Click to copy';
    });

    document.querySelectorAll('form button[name="action"][value="delete"]').forEach(btn=>{
      btn.addEventListener('click', (e)=>{
        if(!confirm('Delete this machine permanently? This action cannot be undone.')){
          e.preventDefault();
        }
      });
    });

    setTimeout(()=> document.querySelectorAll('.alert').forEach(a=> a.remove()),4000);
  });
})();

// Modal details viewer
function showDetails(name, ip, user, pass, connect, ports){
  const modal = document.getElementById('vmDetailsModal');
  const content = document.getElementById('vmDetailsContent');
  content.innerHTML = `
  🖥️ <b>Name:</b> ${name}
  🌐 <b>IP:</b> ${ip}
  👤 <b>User:</b> ${user}
  🔑 <b>Password:</b> ${pass}
  🔗 <b>Connection:</b> ${connect}
  ⚙️ <b>Ports:</b> ${ports}
  `;
  modal.classList.add('show');
}

function closeDetails(){
  document.getElementById('vmDetailsModal').classList.remove('show');
}

// Delete confirmation
document.addEventListener('DOMContentLoaded', ()=>{
  document.querySelectorAll('form button[name="action"][value="delete"]').forEach(btn=>{
    btn.addEventListener('click', (e)=>{
      if(!confirm("⚠️ Are you sure you want to delete this VM? It will be removed permanently from VirtualBox and the disk!")){
        e.preventDefault();
      }
    });
  });
});

// Status update after actions
document.addEventListener('DOMContentLoaded', () => {
  const vmStatusEl = document.querySelector('.vm-status');
  const serialEl = document.querySelector('input[name="serial"][type="hidden"]');
  const serial = serialEl ? serialEl.value : null;

  function refreshStatusOnce() {
    if (!serial || !vmStatusEl) return;
    fetch(`/api/vm_status?serial=${serial}`)
      .then(r => r.json())
      .then(data => {
        if (data.ok && data.status_text) {
          vmStatusEl.innerHTML = data.status_text.trim();
          toast(`✅ Status updated: ${data.status_text}`, 'ok');
        }
      })
      .catch(err => console.warn('status check error', err));
  }

  document.querySelectorAll('form button[name="action"]').forEach(btn => {
    btn.addEventListener('click', () => {
      setTimeout(refreshStatusOnce, 4000);
    });
  });
});

// VPS creation overlay
document.addEventListener('DOMContentLoaded', () => {
  const createForm = document.querySelector('form[action="/admin/create"]');
  if (!createForm) return;

  createForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const overlay = document.getElementById('creatingMessage');
    if (overlay) overlay.classList.add('show');

    toast('⏳ Creating virtual machine... This may take 5–20 minutes.', 'warn', 6000);

    createForm.querySelectorAll('button, select').forEach(el => el.disabled = true);

    const formData = new FormData(createForm);
    let resp;
    try {
      resp = await fetch('/admin/create', { method: 'POST', body: formData });
    } catch (err) {
      toast('❌ Failed to contact server.', 'err');
      if (overlay) overlay.classList.remove('show');
      createForm.querySelectorAll('button, select').forEach(el => el.disabled = false);
      return;
    }

    if (!resp.ok) {
      toast('⚠️ Request was not accepted (check the server).', 'err');
      if (overlay) overlay.classList.remove('show');
      createForm.querySelectorAll('button, select').forEach(el => el.disabled = false);
      return;
    }

    const data = await resp.json();
    const vmName = data.name || data.vm_name || null;
    if (!vmName) {
      toast('⚠️ VM name was not provided!', 'warn');
      if (overlay) overlay.classList.remove('show');
      createForm.querySelectorAll('button, select').forEach(el => el.disabled = false);
      return;
    }

    pollVmStatus(vmName, createForm, overlay);
  });
});

async function pollVmStatus(vmName, formEl, overlay) {
  let tries = 0;
  const maxTries = 120; // ~20 minutes
  toast(`🚧 Tracking status of ${vmName}...`, 'info', 4000);

  const timer = setInterval(async () => {
    tries++;
    try {
      const r = await fetch(`/api/vm_status?name=${encodeURIComponent(vmName)}`);
      if (!r.ok) return;

      const j = await r.json();
      const status = j.status || 'unknown';

      if (tries % 6 === 0) {
        toast(`⌛ Current status: ${status}`, 'info');
      }

      if (status === 'ready' || status === 'running') {
        clearInterval(timer);
        if (overlay) overlay.classList.remove('show');
        toast(`✅ VM ${vmName} is now ready!`, 'ok', 6000);
        setTimeout(() => window.location.reload(), 3000);

      } else if (status === 'error') {
        clearInterval(timer);
        if (overlay) overlay.classList.remove('show');
        toast(`❌ VM creation failed: ${j.note || 'Unknown error'}`, 'err', 6000);
        formEl.querySelectorAll('button, select').forEach(el => el.disabled = false);

      } else if (tries >= maxTries) {
        clearInterval(timer);
        if (overlay) overlay.classList.remove('show');
        toast('⚠️ Time limit exceeded. VM did not become ready.', 'warn', 6000);
        formEl.querySelectorAll('button, select').forEach(el => el.disabled = false);
      }

    } catch (err) {
      console.warn('poll error', err);
    }
  }, 10000);
}
function openModal(id) {
  document.getElementById(id).classList.add("show");
}

function closeModal(id) {
  document.getElementById(id).classList.remove("show");
}
const steps = [
  "Preparing environment...",
  "Allocating CPU & RAM...",
  "Creating virtual disk...",
  "Installing operating system...",
  "Configuring network...",
  "Booting virtual machine...",
  "Finalizing setup...",
  "VPS Ready ✔"
];

let i = 0;
setInterval(() => {
  const el = document.getElementById("loadingText");
  if (el) {
    el.textContent = steps[i];
    i = (i + 1) % steps.length;
  }
}, 20000);
