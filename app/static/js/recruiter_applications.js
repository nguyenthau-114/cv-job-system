(() => {
    'use strict';
    document.addEventListener('submit', async event => {
        const form = event.target;
        if (!form.matches('form[data-recruiter-open], form[data-recruiter-status]')) return;
        event.preventDefault();
        const actions = form.closest('.recruiter-application-actions');
        if (actions.dataset.pending === '1') return;
        if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) return;
        const message = actions.querySelector('.recruiter-application-message');
        const body = new FormData(form);
        const buttons = [...actions.querySelectorAll('button')];
        actions.dataset.pending = '1';
        buttons.forEach(button => { button.disabled = true; });
        message.classList.remove('text-danger');
        message.textContent = 'Đang xử lý…';
        try {
            const response = await fetch(form.action, {
                method: 'POST', body, credentials: 'same-origin', headers: {'Accept': 'application/json'}
            });
            const data = response.headers.get('Content-Type')?.includes('application/json')
                ? await response.json() : null;
            if (response.redirected || !response.ok || !data?.success) {
                throw new Error(data?.errors ? Object.values(data.errors).join(' ')
                    : 'Không thể xử lý. Vui lòng tải lại trang để kiểm tra phiên đăng nhập và trạng thái mới nhất.');
            }
            if (form.dataset.recruiterOpen) {
                window.location.assign(form.dataset.recruiterOpen);
            } else if (window.jobfitNotifications) {
                actions.dataset.pending = '0';
                await window.jobfitNotifications.refresh();
            } else {
                window.location.reload();
            }
        } catch (error) {
            message.classList.add('text-danger');
            message.textContent = error.message || 'Không thể kết nối. Vui lòng thử lại.';
            actions.dataset.pending = '0';
            buttons.forEach(button => { button.disabled = false; });
        }
    });
})();
