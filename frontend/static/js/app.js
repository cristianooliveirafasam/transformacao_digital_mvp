(() => {
  const body = document.body;
  const page = body.dataset.page;
  const role = body.dataset.role;
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  async function api(path, options = {}) {
    const response = await fetch(path, {
      credentials: 'same-origin',
      ...options,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(options.method && options.method !== 'GET' ? { 'X-CSRF-Token': csrf } : {}),
        ...(options.headers || {}),
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || 'Não foi possível concluir a ação.');
    return data;
  }

  function toast(message, kind = 'success') {
    const container = $('#toastContainer');
    if (!container || !window.bootstrap) {
      window.alert(message);
      return;
    }
    const item = document.createElement('div');
    item.className = `toast align-items-center text-bg-${kind} border-0`;
    item.setAttribute('role', 'status');
    item.innerHTML = '<div class="d-flex"><div class="toast-body"></div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Fechar"></button></div>';
    $('.toast-body', item).textContent = message;
    container.append(item);
    const instance = new bootstrap.Toast(item, { delay: 3600 });
    item.addEventListener('hidden.bs.toast', () => item.remove());
    instance.show();
  }

  function make(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function statusClass(status) {
    return `status-${String(status || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replaceAll(' ', '-')}`;
  }

  function formatDate(value) {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' }).format(date);
  }

  function badge(status) {
    return make('span', `status-badge ${statusClass(status)}`, status || 'Sem status');
  }

  async function loadNotifications() {
    const list = $('#notificationList');
    if (!list) return;
    try {
      const result = await api('/api/notifications');
      const count = $('#notificationCount');
      count.textContent = String(result.unread);
      count.classList.toggle('d-none', result.unread === 0);
      list.replaceChildren();
      if (!result.items.length) {
        list.append(make('div', 'notification-empty', 'Você não tem notificações.'));
        return;
      }
      result.items.forEach((notice) => {
        const link = make('a', `notification-item ${notice.read_at ? '' : 'unread'}`);
        link.href = notice.ticket_id ? `/chamados/${notice.ticket_id}` : '#';
        const title = make('strong', '', notice.title);
        const message = make('span', '', notice.message);
        const date = make('small', '', formatDate(notice.created_at));
        link.append(title, message, date);
        link.addEventListener('click', async () => {
          if (!notice.read_at) await api(`/api/notifications/${notice.id}/read`, { method: 'POST' });
        });
        list.append(link);
      });
    } catch (error) {
      list.replaceChildren(make('div', 'notification-empty', error.message));
    }
  }

  function setupNotifications() {
    $('#notificationButton')?.addEventListener('click', loadNotifications);
    $('#markNotificationsRead')?.addEventListener('click', async () => {
      try {
        const { items } = await api('/api/notifications');
        await Promise.all(items.filter((item) => !item.read_at).map((item) => api(`/api/notifications/${item.id}/read`, { method: 'POST' })));
        await loadNotifications();
        toast('Notificações marcadas como lidas.');
      } catch (error) { toast(error.message, 'danger'); }
    });
    loadNotifications();
  }

  function makeTicketRow(ticket, technician = false) {
    const row = make('tr');
    const primary = make('td');
    const anchor = make('a', '', ticket.protocol);
    anchor.href = `/chamados/${ticket.id}`;
    primary.append(anchor);
    row.append(primary);
    const remaining = technician
      ? [ticket.requester_name || '—', ticket.title]
      : [ticket.title, ticket.location];
    remaining.forEach((value) => row.append(make('td', '', value || '—')));
    const state = make('td'); state.append(badge(ticket.status)); row.append(state);
    if (technician) row.append(make('td', '', ticket.assigned_name || 'Não atribuído'));
    row.append(make('td', 'text-secondary small', formatDate(ticket.updated_at)));
    const action = make('td');
    const link = make('a', 'btn btn-light btn-sm', 'Abrir'); link.href = `/chamados/${ticket.id}`; link.setAttribute('aria-label', `Abrir chamado ${ticket.protocol}`); action.append(link); row.append(action);
    row.addEventListener('click', (event) => { if (event.target.closest('a')) return; window.location.href = `/chamados/${ticket.id}`; });
    return row;
  }

  function drawStudentTickets(tickets) {
    const bodyRows = $('#ticketRows');
    const filter = $('#ticketFilter')?.value || '';
    const visible = tickets.filter((ticket) => !filter || ticket.status === filter);
    bodyRows.replaceChildren();
    if (!visible.length) {
      const row = make('tr'); const cell = make('td', 'table-message', tickets.length ? 'Nenhum chamado com este status.' : 'Você ainda não registrou chamados.'); cell.colSpan = 6; row.append(cell); bodyRows.append(row); return;
    }
    visible.forEach((ticket) => bodyRows.append(makeTicketRow(ticket)));
  }

  async function loadStudentDashboard() {
    const rows = $('#ticketRows');
    try {
      const tickets = await api('/api/tickets');
      $('#countOpen').textContent = String(tickets.filter((x) => x.status === 'Aberto').length);
      $('#countInProgress').textContent = String(tickets.filter((x) => x.status === 'Em atendimento').length);
      $('#countWaiting').textContent = String(tickets.filter((x) => x.status === 'Aguardando informações').length);
      $('#countClosed').textContent = String(tickets.filter((x) => x.status === 'Concluído').length);
      drawStudentTickets(tickets);
      $('#ticketFilter').addEventListener('change', () => drawStudentTickets(tickets));
    } catch (error) { rows.replaceChildren(); const row = make('tr'); const cell = make('td', 'table-message', error.message); cell.colSpan = 6; row.append(cell); rows.append(row); }
  }

  function drawTechnicianTickets(tickets) {
    const rows = $('#techTicketRows');
    const filter = $('#techTicketFilter')?.value || '';
    const visible = tickets.filter((ticket) => !filter || ticket.status === filter);
    rows.replaceChildren();
    if (!visible.length) {
      const row = make('tr'); const cell = make('td', 'table-message', 'Não há chamados com este filtro.'); cell.colSpan = 7; row.append(cell); rows.append(row); return;
    }
    visible.forEach((ticket) => rows.append(makeTicketRow(ticket, true)));
  }

  async function loadTechnicianDashboard() {
    const rows = $('#techTicketRows');
    try {
      const tickets = await api('/api/tickets');
      $('#queueCount').textContent = String(tickets.length);
      $('#techCountOpen').textContent = String(tickets.filter((x) => x.status === 'Aberto').length);
      $('#techCountProgress').textContent = String(tickets.filter((x) => x.status === 'Em atendimento').length);
      $('#techCountWaiting').textContent = String(tickets.filter((x) => x.status === 'Aguardando informações').length);
      drawTechnicianTickets(tickets);
      $('#techTicketFilter').addEventListener('change', () => drawTechnicianTickets(tickets));
    } catch (error) { rows.replaceChildren(); const row = make('tr'); const cell = make('td', 'table-message', error.message); cell.colSpan = 7; row.append(cell); rows.append(row); }
  }

  function renderTimeline(events) {
    const timeline = $('#ticketTimeline');
    timeline.replaceChildren();
    if (!events.length) { timeline.append(make('p', 'text-secondary', 'Ainda não há atualizações.')); return; }
    events.forEach((event) => {
      const item = make('div', 'timeline-item');
      item.append(make('span', 'timeline-dot'));
      const author = event.author_name || 'Sistema';
      const labels = { opened: 'Chamado registrado', request_info: 'Solicitação de informações', reply: 'Resposta do aluno', close: 'Atendimento concluído', estimate: 'Previsão atualizada', status: 'Status atualizado' };
      item.append(make('div', 'timeline-title', labels[event.event_type] || 'Atualização'));
      item.append(make('div', 'timeline-meta', `${author} · ${formatDate(event.created_at)}`));
      item.append(make('div', 'timeline-message', event.message));
      timeline.append(item);
    });
  }

  async function loadTicketDetail() {
    const id = body.dataset.ticketId;
    try {
      const ticket = await api(`/api/tickets/${id}`);
      $('#ticketProtocol').textContent = ticket.protocol;
      $('#ticketTitle').textContent = ticket.title;
      $('#ticketStatusTop').textContent = ticket.status;
      $('#ticketStatusTop').className = `status-badge ${statusClass(ticket.status)}`;
      $('#ticketCategory').textContent = ticket.category;
      $('#ticketLocation').textContent = ticket.location;
      $('#ticketRequester').textContent = ticket.requester_name;
      $('#ticketAssignee').textContent = ticket.assigned_name || 'Aguardando atribuição';
      $('#ticketEstimate').textContent = ticket.estimated_at ? formatDate(ticket.estimated_at) : 'Ainda não informada';
      $('#ticketDescription').textContent = ticket.description;
      renderTimeline(ticket.events);
      if (role === 'technician') {
        $('#studentReplyCard').classList.add('d-none');
        $('#technicianTools').classList.remove('d-none');
        $('#estimatedAt').value = ticket.estimated_at ? ticket.estimated_at.slice(0, 16) : '';
        $('#closeForm button').disabled = ticket.status === 'Concluído';
        $('#requestInfoForm button').disabled = ticket.status === 'Concluído';
        $('#startForm button').disabled = ticket.status === 'Concluído' || ticket.status === 'Em atendimento';
      } else {
        const canReply = ticket.status === 'Aguardando informações';
        $('#replyMessage').disabled = !canReply;
        $('#replyButton').disabled = !canReply;
        $('#replyHelp').textContent = canReply ? 'A equipe solicitou um complemento. Envie sua resposta para retomar o atendimento.' : 'Quando houver uma solicitação de informações, responda aqui.';
      }
    } catch (error) { toast(error.message, 'danger'); }
  }

  async function setupNewTicket() {
    $('#newTicketForm')?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      if (!form.reportValidity()) return;
      const button = $('#submitTicket'); button.disabled = true; button.textContent = 'Enviando…';
      const payload = Object.fromEntries(new FormData(form));
      try {
        const result = await api('/api/tickets', { method: 'POST', body: JSON.stringify(payload) });
        window.location.href = `/chamados/${result.id}`;
      } catch (error) { toast(error.message, 'danger'); button.disabled = false; button.textContent = 'Enviar chamado'; }
    });
  }

  function setupTicketForms() {
    $('#startForm')?.addEventListener('submit', async (event) => {
      event.preventDefault();
      try { await api(`/api/tickets/${body.dataset.ticketId}/actions`, { method: 'POST', body: JSON.stringify({ action: 'start' }) }); toast('Atendimento iniciado.'); await loadTicketDetail(); }
      catch (error) { toast(error.message, 'danger'); }
    });
    $('#replyForm')?.addEventListener('submit', async (event) => {
      event.preventDefault(); const button = $('#replyButton'); button.disabled = true;
      try { await api(`/api/tickets/${body.dataset.ticketId}/reply`, { method: 'POST', body: JSON.stringify({ message: $('#replyMessage').value }) }); toast('Resposta enviada.'); await loadTicketDetail(); }
      catch (error) { toast(error.message, 'danger'); button.disabled = false; }
    });
    $('#requestInfoForm')?.addEventListener('submit', async (event) => {
      event.preventDefault(); const button = $('button[type="submit"]', event.currentTarget); button.disabled = true;
      try { await api(`/api/tickets/${body.dataset.ticketId}/request-info`, { method: 'POST', body: JSON.stringify({ message: $('#requestMessage').value }) }); toast('Solicitação enviada ao aluno.'); await loadTicketDetail(); }
      catch (error) { toast(error.message, 'danger'); button.disabled = false; }
    });
    $('#estimateForm')?.addEventListener('submit', async (event) => {
      event.preventDefault();
      try { await api(`/api/tickets/${body.dataset.ticketId}/actions`, { method: 'POST', body: JSON.stringify({ action: 'estimate', estimated_at: $('#estimatedAt').value }) }); toast('Previsão atualizada.'); await loadTicketDetail(); }
      catch (error) { toast(error.message, 'danger'); }
    });
    $('#closeForm')?.addEventListener('submit', async (event) => {
      event.preventDefault(); const button = $('button[type="submit"]', event.currentTarget); button.disabled = true;
      try { await api(`/api/tickets/${body.dataset.ticketId}/actions`, { method: 'POST', body: JSON.stringify({ action: 'close', message: $('#closureMessage').value }) }); toast('Chamado concluído.'); await loadTicketDetail(); }
      catch (error) { toast(error.message, 'danger'); button.disabled = false; }
    });
  }

  async function setupProfile() {
    const form = $('#profileForm');
    if (!form) return;
    try {
      const user = await api('/api/me');
      $('#profileEmail').value = user.email || '';
      $('#profilePhone').value = user.phone || '';
    } catch (error) { toast(error.message, 'danger'); }
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      try {
        await api('/api/profile/contact', { method: 'PUT', body: JSON.stringify({ email: $('#profileEmail').value, phone: $('#profilePhone').value }) });
        toast('Contato atualizado.');
      } catch (error) { toast(error.message, 'danger'); }
    });
  }

  setupNotifications();
  if (page === 'dashboard') loadStudentDashboard();
  if (page === 'technician') loadTechnicianDashboard();
  if (page === 'new-ticket') setupNewTicket();
  if (page === 'ticket-detail') { loadTicketDetail(); setupTicketForms(); }
  if (page === 'profile') setupProfile();
})();
