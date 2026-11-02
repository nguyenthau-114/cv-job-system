(() => {
    'use strict';
    const ui = document.getElementById('jobUI');
    if (!ui || typeof bootstrap === 'undefined') return;
    const quick = document.getElementById('jobQuickModal');
    const apply = document.getElementById('jobApplyModal');
    let activeModal = null;
    let requestedModal = null;
    let quickSequence = 0;
    let optionsSequence = 0;
    let submitting = false;
    let applicationJobId = null;
    let applicationDetailURL = '';
    let applicationOptionsURL = '';
    const saving = new Set();
    const node = id => document.getElementById(id);
    const text = (id, value) => { node(id).textContent = value || ''; };

    // Chờ hidden.bs.modal trước khi mở modal kế tiếp, kể cả đang chạy fade.
    function displayModal(element) {
        requestedModal = element;
        if (activeModal === element) return;
        if (activeModal) {
            bootstrap.Modal.getOrCreateInstance(activeModal).hide();
        } else {
            activeModal = element;
            bootstrap.Modal.getOrCreateInstance(element).show();
        }
    }
    [quick, apply].forEach(element => {
        // Ghi nhận yêu cầu đóng cả khi Bootstrap còn đang chạy hiệu ứng mở.
        element.addEventListener('click', event => {
            if (event.target === element || event.target.closest('[data-bs-dismiss="modal"]')) {
                requestedModal = null;
                bootstrap.Modal.getOrCreateInstance(element).hide();
            }
        });
        element.addEventListener('keydown', event => {
            if (event.key === 'Escape') {
                requestedModal = null;
                bootstrap.Modal.getOrCreateInstance(element).hide();
            }
        });
        element.addEventListener('shown.bs.modal', () => {
            if (requestedModal !== element) bootstrap.Modal.getOrCreateInstance(element).hide();
        });
        element.addEventListener('hidden.bs.modal', () => {
            activeModal = null;
            if (requestedModal === element) requestedModal = null;
            if (element === quick) quickSequence += 1;
            if (element === apply) optionsSequence += 1;
            if (requestedModal) displayModal(requestedModal);
        });
    });

    function internalURL(value) {
        const url = new URL(value, window.location.origin);
        if (url.origin !== window.location.origin) throw new Error('Đường dẫn không hợp lệ.');
        return url;
    }
    function loginURL(detail, intent) {
        const next = internalURL(detail);
        if (intent === 'apply') next.searchParams.set('apply', '1');
        const login = internalURL(ui.dataset.loginUrl);
        login.searchParams.set('next', next.pathname + next.search);
        return login.href;
    }
    async function requestJSON(url, options = {}) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 20000);
        let response;
        try {
            response = await fetch(internalURL(url), {
                credentials: 'same-origin', ...options, signal: controller.signal,
                headers: {Accept: 'application/json', ...(options.headers || {})},
            });
        } catch (error) {
            throw new Error(error.name === 'AbortError' ? 'Yêu cầu mất quá nhiều thời gian. Vui lòng thử lại.' : 'Không thể kết nối. Vui lòng thử lại.');
        } finally {
            clearTimeout(timer);
        }
        if (response.redirected) {
            const error = new Error('Phiên đăng nhập đã thay đổi. Vui lòng đăng nhập lại.');
            error.login = true;
            throw error;
        }
        if (!(response.headers.get('Content-Type') || '').includes('application/json')) {
            throw new Error(response.status === 400 ? 'Phiên biểu mẫu đã hết hạn. Vui lòng tải lại trang.' : 'Không thể xử lý yêu cầu lúc này.');
        }
        const data = await response.json();
        if (!response.ok || !data.success) {
            const error = new Error(Object.values(data.errors || {}).join(' ') || 'Không thể xử lý yêu cầu.');
            error.errors = data.errors || {};
            throw error;
        }
        return data;
    }
    function announce(message, failure = false) {
        text('jobActionMessage', message);
        node('jobActionMessage').classList.toggle('text-danger', failure);
        window.showJobfitToast(node('jobActionMessage'), failure ? 'danger' : 'success');
    }
    function setSaved(id, state) {
        document.querySelectorAll('[data-job-action="save"]').forEach(button => {
            if (button.dataset.jobId !== String(id)) return;
            button.dataset.isSaved = state ? '1' : '0';
            button.classList.toggle('is-saved', state);
            button.setAttribute('aria-pressed', String(state));
            const label = state ? 'Bỏ lưu tin tuyển dụng' : 'Lưu tin tuyển dụng';
            button.setAttribute('aria-label', label);
            button.title = label;
            const icon = button.querySelector('i');
            if (icon) icon.className = state ? 'bi bi-heart-fill' : 'bi bi-heart';
        });
    }
    function setApplied(id, status) {
        document.querySelectorAll('[data-job-action="apply"]').forEach(button => {
            if (button.dataset.jobId !== String(id)) return;
            button.disabled = true;
            button.textContent = status === 'WITHDRAWN' ? 'Đã ứng tuyển (đã rút)' : 'Đã ứng tuyển';
            button.dataset.applied = '1';
        });
    }

    async function openQuick(button) {
        const sequence = ++quickSequence;
        text('jobQuickTitle', 'Xem nhanh công việc');
        text('jobQuickMessage', 'Đang tải thông tin công việc...');
        node('jobQuickContent').hidden = true;
        node('jobQuickDetail').hidden = true;
        node('jobQuickApply').hidden = true;
        displayModal(quick);
        try {
            const data = await requestJSON(button.dataset.quickUrl);
            if (sequence !== quickSequence) return;
            const job = data.job;
            text('jobQuickTitle', job.title);
            text('jobQuickCompany', job.company);
            for (const [field, value] of Object.entries({Salary: job.salary, Location: job.location,
                Experience: job.experience, Deadline: job.deadline, Description: job.description, Requirement: job.requirement})) {
                text('jobQuick' + field, value);
            }
            node('jobQuickDescriptionSection').hidden = !job.description;
            node('jobQuickRequirementSection').hidden = !job.requirement;
            for (const [kind, suffix] of [['REQUIRED', 'Required'], ['PREFERRED', 'Preferred']]) {
                const container = node('jobQuick' + suffix);
                container.replaceChildren();
                const skills = job.skills.filter(skill => skill.type === kind);
                node('jobQuick' + suffix + 'Section').hidden = !skills.length;
                skills.forEach(skill => {
                    const tag = document.createElement('span');
                    tag.className = 'jobs-skill-tag';
                    tag.textContent = skill.name;
                    container.appendChild(tag);
                });
            }
            text('jobQuickMessage', '');
            node('jobQuickContent').hidden = false;
            node('jobQuickDetail').href = internalURL(job.detail_url).href;
            node('jobQuickDetail').hidden = false;
            const action = node('jobQuickApply');
            action.dataset.jobId = String(job.id);
            action.dataset.optionsUrl = job.options_url;
            action.dataset.detailUrl = job.detail_url;
            action.hidden = false;
            action.disabled = Boolean(job.application_status) || Boolean(ui.dataset.role && ui.dataset.role !== 'CANDIDATE');
            action.textContent = job.application_status ? 'Đã ứng tuyển' : 'Ứng tuyển ngay';
            setSaved(job.id, job.is_saved);
            if (job.application_status) setApplied(job.id, job.application_status);
        } catch (error) {
            if (sequence === quickSequence) text('jobQuickMessage', error.message);
        }
    }

    async function openApply(button) {
        if (submitting) {
            announce('Đơn ứng tuyển đang được gửi. Vui lòng chờ phản hồi.');
            displayModal(apply);
            return;
        }
        const sequence = ++optionsSequence;
        const form = node('jobApplyForm');
        const confirm = node('jobApplyConfirm');
        applicationJobId = button.dataset.jobId;
        applicationDetailURL = button.dataset.detailUrl;
        applicationOptionsURL = button.dataset.optionsUrl;
        form.hidden = true;
        confirm.hidden = true;
        confirm.disabled = true;
        text('jobApplyMessage', 'Đang chuẩn bị biểu mẫu...');
        node('jobApplyMessage').classList.remove('text-danger');
        node('jobApplyLogin').href = loginURL(applicationDetailURL, 'apply');
        node('jobApplyLogin').hidden = true;
        displayModal(apply);
        if (!ui.dataset.role) {
            text('jobApplyMessage', 'Vui lòng đăng nhập bằng tài khoản Candidate để ứng tuyển.');
            node('jobApplyLogin').hidden = false;
            return;
        }
        if (ui.dataset.role !== 'CANDIDATE') {
            text('jobApplyMessage', 'Chỉ tài khoản Candidate đang hoạt động được ứng tuyển.');
            return;
        }
        try {
            const data = await requestJSON(button.dataset.optionsUrl);
            if (sequence !== optionsSequence) return;
            text('jobApplyTitle', 'Ứng tuyển công việc');
            text('jobApplyJobName', data.job.title);
            text('jobApplyCompany', data.job.company);
            if (data.application_status) {
                text('jobApplyMessage', 'Bạn đã từng ứng tuyển công việc này. Đơn đã rút vẫn được tính là đã ứng tuyển.');
                setApplied(data.job.id, data.application_status);
                return;
            }
            form.reset();
            clearFieldErrors();
            form.action = internalURL(data.submit_url).href;
            for (const [name, value] of Object.entries(data.contact)) form.elements[name].value = value;
            const select = node('jobApplicationCV');
            select.replaceChildren();
            const placeholder = new Option('Chọn CV đã lưu', '');
            select.appendChild(placeholder);
            data.cvs.forEach(cv => select.appendChild(new Option(cv.name, String(cv.id))));
            node('jobApplyCVGuide').hidden = data.cvs.length > 0;
            text('jobApplyMessage', '');
            form.hidden = false;
            confirm.hidden = false;
            confirm.disabled = data.cvs.length === 0;
        } catch (error) {
            if (sequence !== optionsSequence) return;
            text('jobApplyMessage', error.message);
            node('jobApplyMessage').classList.add('text-danger');
            node('jobApplyLogin').hidden = !error.login;
        }
    }

    function clearFieldErrors() {
        node('jobApplyForm').querySelectorAll('.is-invalid').forEach(field => field.classList.remove('is-invalid'));
        node('jobApplyForm').querySelectorAll('[data-field-error]').forEach(field => { field.textContent = ''; });
    }
    node('jobApplyForm').addEventListener('submit', async event => {
        event.preventDefault();
        const form = event.currentTarget;
        if (submitting || form.hidden || !form.reportValidity()) return;
        const id = applicationJobId;
        const confirm = node('jobApplyConfirm');
        const payload = new FormData(form);
        submitting = true;
        confirm.disabled = true;
        clearFieldErrors();
        try {
            const result = await requestJSON(form.action, {method: 'POST', body: payload,
                headers: {'X-CSRFToken': node('jobCsrfToken').value}});
            setApplied(id, 'SUBMITTED');
            form.hidden = true;
            confirm.hidden = true;
            text('jobApplyMessage', result.message);
            announce(result.message);
        } catch (error) {
            text('jobApplyMessage', error.message);
            node('jobApplyMessage').classList.add('text-danger');
            for (const [name, message] of Object.entries(error.errors || {})) {
                const field = form.elements.namedItem(name);
                if (field) field.classList.add('is-invalid');
                const feedback = form.querySelector('[data-field-error="' + name + '"]');
                if (feedback) feedback.textContent = message;
            }
            if (error.errors && error.errors.application) {
                // Backend dùng cùng trường lỗi cho đơn trùng và lỗi lưu. Chỉ khóa khi có đơn thật.
                try {
                    const state = await requestJSON(applicationOptionsURL);
                    if (state.application_status) {
                        setApplied(id, state.application_status);
                        confirm.hidden = true;
                    }
                } catch (verificationError) {
                    // Giữ dữ liệu form để thử lại khi chưa xác minh được trạng thái.
                }
            }
            if (error.login) {
                node('jobApplyLogin').href = loginURL(applicationDetailURL, 'apply');
                node('jobApplyLogin').hidden = false;
            }
        } finally {
            submitting = false;
            confirm.disabled = false;
        }
    });

    async function saveJob(button) {
        if (!ui.dataset.role) {
            window.location.assign(loginURL(button.dataset.detailUrl, 'save'));
            return;
        }
        if (ui.dataset.role !== 'CANDIDATE' || saving.has(button.dataset.jobId)) return;
        const id = button.dataset.jobId;
        saving.add(id);
        const buttons = [...document.querySelectorAll('[data-job-action="save"]')].filter(item => item.dataset.jobId === id);
        buttons.forEach(item => { item.disabled = true; });
        try {
            const data = await requestJSON(button.dataset.saveUrl, {
                method: 'POST', headers: {'X-CSRFToken': node('jobCsrfToken').value},
                body: new URLSearchParams({is_saved: button.dataset.isSaved === '1' ? '0' : '1'}),
            });
            setSaved(id, data.is_saved);
            announce(data.message);
            if (ui.dataset.savedPage === '1' && !data.is_saved) window.location.reload();
        } catch (error) {
            announce(error.message, true);
            if (error.login) {
                const link = document.createElement('a');
                link.href = loginURL(button.dataset.detailUrl, 'save');
                link.textContent = ' Đăng nhập lại';
                node('jobActionMessage').appendChild(link);
            }
        } finally {
            saving.delete(id);
            buttons.forEach(item => { item.disabled = false; });
        }
    }
    document.addEventListener('click', event => {
        const button = event.target.closest('[data-job-action]');
        if (!button || button.disabled) return;
        event.preventDefault();
        if (button.dataset.jobAction === 'quick') openQuick(button);
        if (button.dataset.jobAction === 'apply') openApply(button);
        if (button.dataset.jobAction === 'save') saveJob(button);
    });
    if (new URLSearchParams(window.location.search).get('apply') === '1') {
        const button = document.querySelector('[data-job-action="apply"][data-job-id]');
        if (button && !button.disabled) openApply(button);
    }
})();
