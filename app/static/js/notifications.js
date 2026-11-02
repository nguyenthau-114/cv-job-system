(() => {
    'use strict';
    const bell = document.querySelector('#notificationBell');
    if (!bell || window.jobfitNotifications) return;
    const csrf = document.querySelector('#notificationCsrf').value;
    const viewer = bell.dataset.viewer;
    const role = bell.dataset.role;
    const panelSelector = '.notifications-page,.candidate-dashboard,.candidate-applications,.candidate-application-detail,.recruiter-applications-page,.cv-page';
    const labels = {
        SUBMITTED: ['Đã nộp', 'text-bg-primary'], VIEWED: ['Đã xem hồ sơ', 'application-status-viewed'],
        CONSIDERING: ['Đang cân nhắc', 'text-bg-warning'], INTERVIEW: ['Đang phỏng vấn', 'text-bg-primary'],
        REJECTED: ['Đã từ chối', 'text-bg-danger'], WITHDRAWN: ['Đã rút đơn', 'text-bg-secondary']
    };
    let timer, pending = null, stopped = false, suspended = false, failures = 0, lastInbox = null, lastStates = null;
    let panelPending = false, panelRequest = null, controller = null, panelController = null, channel = null;
    const active = () => !stopped && !suspended;
    const receiveMessage = event => { if (active() && event.data === 'invalidate') wake(); };
    const closeChannel = () => {
        const previous = channel;
        channel = null;
        previous?.removeEventListener('message', receiveMessage);
        previous?.close();
    };
    const openChannel = () => {
        if (!active() || channel || typeof BroadcastChannel !== 'function') return;
        try {
            channel = new BroadcastChannel('jobfit-notifications-' + viewer);
            channel.addEventListener('message', receiveMessage);
        } catch (_) { closeChannel(); }
    };
    const invalidateOtherTabs = () => {
        if (!active()) return;
        try { channel?.postMessage('invalidate'); }
        catch (_) {
            // Kênh liên tab lỗi không làm thất bại thao tác đã lưu trên server.
            closeChannel();
            openChannel();
        }
    };
    const connection = document.querySelector('#notificationConnection');
    const formatTimes = root => root.querySelectorAll('[data-notification-time]').forEach(time => {
        time.textContent = new Date(time.dateTime).toLocaleString('vi-VN');
    });
    formatTimes(document);
    const safeURL = value => {
        const url = new URL(value, location.origin);
        if (url.origin !== location.origin) throw new Error('Đường dẫn không hợp lệ.');
        return url.href;
    };
    const postForm = (url, text) => {
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = safeURL(url);
        const token = document.createElement('input');
        token.type = 'hidden'; token.name = 'csrf_token'; token.value = csrf;
        const button = document.createElement('button');
        button.type = 'submit'; button.className = 'notification-open'; button.textContent = text;
        form.append(token, button);
        return form;
    };
    // Giữ focus theo thông báo/form, không kéo người dùng về đầu danh sách khi render lại.
    const rememberNotificationFocus = root => {
        const focused = document.activeElement;
        if (!root.contains(focused)) return () => {};
        const itemId = focused.closest('[data-notification-id]')?.dataset.notificationId;
        const id = focused.id, name = focused.name, tag = focused.tagName;
        const action = focused.form?.getAttribute('action');
        return next => {
            const scope = itemId ? [...next.querySelectorAll('[data-notification-id]')]
                .find(item => item.dataset.notificationId === itemId) : next;
            const replacement = (id && next.querySelector('#' + CSS.escape(id)))
                || (scope && [...scope.querySelectorAll('button,a,input,select')].find(element =>
                    element.tagName === tag && (!name || element.name === name)
                    && (!action || element.form?.getAttribute('action') === action)))
                || scope?.querySelector('button,a,select')
                || next.querySelector('select,button,a')
                || bell.querySelector('.notification-toggle');
            replacement?.focus({preventScroll: true});
        };
    };
    const renderInbox = data => {
        const count = document.querySelector('#notificationUnread');
        count.hidden = data.unread === 0;
        count.textContent = data.unread > 99 ? '99+' : String(data.unread);
        const summary = document.querySelector('[data-notification-unread-label]');
        if (summary) { summary.hidden = false; summary.textContent = data.unread + ' chưa đọc'; }
        document.querySelector('.notification-toggle').setAttribute('aria-label', 'Thông báo, ' + data.unread + ' chưa đọc');
        const list = document.querySelector('#notificationLatest');
        const restoreFocus = rememberNotificationFocus(list);
        const scroll = list.scrollTop;
        const fragment = document.createDocumentFragment();
        data.latest.forEach(item => {
            const article = document.createElement('article');
            article.className = 'notification-item' + (item.is_read ? '' : ' notification-unread');
            article.dataset.notificationId = item.id;
            const icon = document.createElement('span');
            icon.className = 'notification-icon'; icon.setAttribute('aria-hidden', 'true');
            const glyph = document.createElement('i'); glyph.className = 'bi bi-bell'; icon.append(glyph);
            const body = document.createElement('div'); body.className = 'notification-body';
            body.append(postForm(item.open_url, item.message));
            const meta = document.createElement('div'); meta.className = 'notification-meta';
            const time = document.createElement('time');
            time.dateTime = item.created_at + 'Z';
            time.textContent = new Date(item.created_at + 'Z').toLocaleString('vi-VN');
            const state = document.createElement('span');
            state.setAttribute('data-notification-state', '');
            state.textContent = item.is_read ? 'Đã đọc' : 'Chưa đọc';
            meta.append(time, state); body.append(meta); article.append(icon, body);
            fragment.append(article);
        });
        if (!data.latest.length) {
            const empty = document.createElement('p');
            empty.className = 'notification-empty'; empty.textContent = 'Bạn chưa có thông báo.';
            fragment.append(empty);
        }
        list.replaceChildren(fragment); restoreFocus(list); list.scrollTop = scroll;
    };
    const refreshPanel = () => {
        if (!active()) return Promise.resolve();
        panelPending = true;
        if (panelRequest || document.hidden || document.querySelector('[data-pending="1"]')) return panelRequest || Promise.resolve();
        const current = document.querySelector(panelSelector);
        if (!current) { panelPending = false; return Promise.resolve(); }
        panelPending = false;
        let selected = [...current.querySelectorAll('form[method="GET"] [name]')].map(e => [e.name, e.value]);
        const scroll = scrollY;
        const requestController = new AbortController();
        panelController = requestController;
        const timeout = setTimeout(() => requestController.abort(), 8000);
        panelRequest = fetch(location.href, {credentials: 'same-origin', cache: 'no-store', signal: requestController.signal}).then(async response => {
            if (!response.ok || response.redirected) return;
            const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
            const next = doc.querySelector(panelSelector);
            if (!next || !current.isConnected || !active() || requestController.signal.aborted) return;
            if (document.querySelector('[data-pending="1"]')) { panelPending = true; return; }
            const notificationPage = current.matches('.notifications-page');
            const restoreFocus = notificationPage ? rememberNotificationFocus(current) : () => {};
            if (notificationPage) {
                // Đọc lựa chọn mới nhất sau request, kể cả thay đổi chưa gửi trong lúc chờ.
                selected = [...current.querySelectorAll('form[method="GET"] [name]')].map(e => [e.name, e.value]);
            }
            selected.forEach(([name, value]) => {
                const input = [...next.querySelectorAll('form[method="GET"] [name]')].find(e => e.name === name);
                if (input) input.value = value;
            });
            current.replaceWith(next);
            formatTimes(next);
            restoreFocus(next);
            window.scrollTo({top: scroll, behavior: 'instant'});
        }).catch(() => { panelPending = true; }).finally(() => {
            clearTimeout(timeout); panelRequest = null; panelController = null;
        });
        return panelRequest;
    };
    const patchStates = data => {
        data.applications.forEach(item => {
            document.querySelectorAll('[data-application-id="' + item.id + '"]').forEach(root => {
                root.querySelectorAll('[data-application-status]').forEach(badge => {
                    const [label, style] = labels[item.status] || ['Chưa xác định', 'text-bg-secondary'];
                    badge.className = item.status === 'VIEWED' ? style : 'badge text-wrap ' + style;
                    badge.textContent = label;
                });
                if (role === 'CANDIDATE') {
                    root.querySelectorAll('[data-application-job]').forEach(e => { e.textContent = item.job_title; });
                    root.querySelectorAll('[data-application-company]').forEach(e => { e.textContent = item.company_name; });
                    root.querySelectorAll('[data-application-public-job]').forEach(e => {
                        e.hidden = !item.public_job_url;
                        if (item.public_job_url) e.href = safeURL(item.public_job_url); else e.removeAttribute('href');
                    });
                    for (const [action, allowed] of [['replace', item.can_replace], ['withdraw', item.can_withdraw]]) {
                        root.querySelectorAll('[data-candidate-action="' + action + '"]').forEach(form => {
                            form.hidden = !allowed;
                            form.querySelectorAll('button,select').forEach(e => { e.disabled = !allowed; });
                        });
                    }
                } else {
                    root.querySelectorAll('[data-recruiter-status]').forEach(form => {
                        const allowed = form.querySelector('[name="status"]').value === 'CONSIDERING' ? item.can_consider : item.can_reject;
                        form.hidden = !allowed; form.querySelector('button').disabled = !allowed;
                    });
                }
            });
        });
    };
    const schedule = () => {
        clearTimeout(timer);
        if (active() && !document.hidden) timer = setTimeout(sync, Math.min(60000, 5000 * 2 ** Math.min(failures, 4)));
    };
    const stop = () => {
        stopped = true; clearTimeout(timer); controller?.abort(); panelController?.abort(); closeChannel();
        document.querySelector('#notificationLatest').replaceChildren();
        document.querySelector('#notificationUnread').hidden = true;
        const summary = document.querySelector('[data-notification-unread-label]');
        if (summary) { summary.hidden = true; summary.textContent = ''; }
        document.querySelectorAll(panelSelector).forEach(panel => { panel.hidden = true; });
        connection.textContent = 'Phiên đăng nhập đã thay đổi. Vui lòng đăng nhập lại.';
    };
    function sync() {
        if (!active() || document.hidden || !navigator.onLine) { schedule(); return Promise.resolve(); }
        if (pending) return pending;
        clearTimeout(timer);
        const ids = [...new Set([...document.querySelectorAll('[data-application-id]')].map(e => e.dataset.applicationId))].slice(0, 50);
        const url = new URL(bell.dataset.syncUrl, location.origin);
        if (ids.length) url.searchParams.set('applications', ids.join(','));
        if (document.querySelector('.candidate-dashboard,.candidate-applications')) url.searchParams.set('summary', '1');
        const requestController = new AbortController();
        controller = requestController;
        let timedOut = false;
        const timeout = setTimeout(() => { timedOut = true; requestController.abort(); }, 8000);
        pending = fetch(url, {credentials: 'same-origin', cache: 'no-store', signal: requestController.signal}).then(async response => {
            if (!active() || requestController.signal.aborted) return;
            if (response.status === 401 || response.status === 403 || response.redirected) { stop(); return; }
            if (!response.ok) throw new Error('Không thể đồng bộ');
            const data = await response.json();
            if (!active() || requestController.signal.aborted) return;
            if (data.viewer !== viewer || data.role !== role) { stop(); return; }
            if (document.hidden) return;
            const inbox = JSON.stringify([data.unread, data.latest]);
            const states = JSON.stringify([data.applications, data.summary]);
            if (inbox !== lastInbox) renderInbox(data);
            patchStates(data);
            if ((lastInbox !== null && inbox !== lastInbox && document.querySelector('.notifications-page,.recruiter-applications-page'))
                || (lastStates !== null && states !== lastStates && document.querySelector('.candidate-dashboard,.candidate-applications,.candidate-application-detail,.recruiter-applications-page'))
                || panelPending) await refreshPanel();
            if (!active() || requestController.signal.aborted) return;
            lastInbox = inbox; lastStates = states; failures = 0; connection.textContent = '';
        }).catch(() => {
            if (active() && (!requestController.signal.aborted || timedOut)) { failures++; connection.textContent = 'Mất kết nối. Hệ thống sẽ tự đồng bộ lại.'; }
        }).finally(() => {
            clearTimeout(timeout); pending = null; controller = null; schedule();
        });
        return pending;
    }
    document.addEventListener('submit', async event => {
        const form = event.target;
        if (!form.matches('form[data-notification-read]')) return;
        event.preventDefault();
        if (!active() || form.dataset.pending === '1') return;
        form.dataset.pending = '1';
        const button = form.querySelector('button'); button.disabled = true;
        try {
            const response = await fetch(form.action, {method: 'POST', body: new FormData(form), credentials: 'same-origin'});
            if (!active()) return;
            if (response.status === 401 || response.status === 403 || response.redirected) { stop(); return; }
            if (!response.ok) throw new Error('Không thể đánh dấu đã đọc. Vui lòng thử lại.');
            invalidateOtherTabs();
            await wake();
            form.dataset.pending = '0';
            await refreshPanel();
        } catch (error) { if (active()) connection.textContent = error.message; }
        finally { form.dataset.pending = '0'; button.disabled = false; }
    });
    async function wake() {
        if (!active() || document.hidden) return;
        if (pending) { controller?.abort(); panelController?.abort(); await pending; }
        return sync();
    }
    document.addEventListener('visibilitychange', () => {
        clearTimeout(timer);
        if (document.hidden) { controller?.abort(); panelController?.abort(); } else wake();
    });
    window.addEventListener('online', wake);
    window.addEventListener('offline', () => {
        if (!active()) return;
        clearTimeout(timer); controller?.abort(); panelController?.abort(); connection.textContent = 'Đang ngoại tuyến.';
    });
    // pagehide có thể vào bfcache. Chỉ tạm dừng, khác với phiên bị khóa/hết hạn.
    window.addEventListener('pagehide', () => {
        suspended = true; clearTimeout(timer); controller?.abort(); panelController?.abort(); closeChannel();
    });
    window.addEventListener('pageshow', event => {
        if (!event.persisted || !suspended || stopped) return;
        suspended = false; openChannel(); wake();
    });
    window.jobfitNotifications = {sync, refresh: async () => { await refreshPanel(); await wake(); }};
    openChannel();
    sync();
})();
