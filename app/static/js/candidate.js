(() => {
    'use strict';
    document.addEventListener('submit', async event => {
        const form = event.target;
        if (!form.matches('form[data-candidate-action]')) return;
        event.preventDefault();
        if (form.dataset.pending === '1' || !form.reportValidity()) return;
        if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) return;
        const message = form.querySelector('.candidate-action-message')
            || form.closest('.cv-item-card').querySelector('.candidate-action-message');
        const buttons = [...form.querySelectorAll('button[type="submit"]')];
        const body = new FormData(form);
        form.dataset.pending = '1';
        buttons.forEach(button => { button.disabled = true; });
        message.classList.remove('text-danger');
        message.textContent = 'Đang lưu…';
        try {
            const response = await fetch(form.action, {
                method: 'POST', body, credentials: 'same-origin',
                headers: {'Accept': 'application/json'}
            });
            const data = response.headers.get('Content-Type')?.includes('application/json')
                ? await response.json() : null;
            if (response.redirected || !response.ok || !data?.success) {
                throw new Error(data?.errors ? Object.values(data.errors).join(' ')
                    : 'Không thể lưu. Vui lòng tải lại trang để kiểm tra phiên đăng nhập và trạng thái mới nhất.');
            }
            // Chỉ làm mới trạng thái sau khi backend xác nhận transaction thành công.
            if (window.jobfitNotifications) {
                form.dataset.pending = '0';
                await window.jobfitNotifications.refresh();
            } else window.location.reload();
        } catch (error) {
            message.classList.add('text-danger');
            message.textContent = error.message || 'Không thể kết nối. Vui lòng thử lại.';
            buttons.forEach(button => { button.disabled = false; });
            form.dataset.pending = '0';
        }
    });
})();
