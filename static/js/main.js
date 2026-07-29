document.addEventListener('DOMContentLoaded', () => {
    const bookingForm = document.getElementById('bookingForm');
    const serviceSelect = document.getElementById('serviceSelect');
    const dateInput = document.getElementById('dateInput');
    const timeSelect = document.getElementById('timeSelect');
    const phoneInput = document.getElementById('phoneInput');
    const emailInput = document.getElementById('emailInput');
    const phoneError = document.getElementById('phoneError');
    const emailError = document.getElementById('emailError');
    const consentPolicy = document.getElementById('consentPolicy');
    const submitBtn = document.getElementById('bookSubmitBtn');
    const formMessage = document.getElementById('formMessage');
    const servicesList = document.getElementById('servicesList');
    const navToggle = document.getElementById('navToggle');
    const nav = document.querySelector('.nav');
    const navClose = document.getElementById('navClose');

    if (navToggle && nav) {
        navToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            nav.classList.toggle('nav-open');
        });

        if (navClose) {
            navClose.addEventListener('click', () => {
                nav.classList.remove('nav-open');
            });
        }

        nav.querySelectorAll('a').forEach(link => {
            link.addEventListener('click', () => {
                nav.classList.remove('nav-open');
            });
        });

        document.addEventListener('click', (e) => {
            if (nav.classList.contains('nav-open') && !nav.contains(e.target) && !navToggle.contains(e.target)) {
                nav.classList.remove('nav-open');
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && nav.classList.contains('nav-open')) {
                nav.classList.remove('nav-open');
            }
        });
    }

    fetch('/api/services')
        .then(r => r.json())
        .then(services => {
            const mainServices = services.filter(s => s.category === 'main');
            const extraServices = services.filter(s => s.category === 'extra');

            services.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s.id;
                opt.textContent = `${s.name} — ${s.price}₽`;
                serviceSelect.appendChild(opt);
            });

            if (servicesList) {
                let html = '';
                if (mainServices.length) {
                    html += '<div class="service-group"><h3 class="service-group-title">Основные услуги</h3>';
                    mainServices.forEach(s => {
                        html += renderServiceItem(s);
                    });
                    html += '</div>';
                }
                if (extraServices.length) {
                    html += '<div class="service-group"><h3 class="service-group-title">Дополнительные услуги</h3>';
                    extraServices.forEach(s => {
                        html += renderServiceItem(s);
                    });
                    html += '</div>';
                }
                servicesList.innerHTML = html;
            }
        });

    function renderServiceItem(s) {
        const inc = s.description ? s.description.split(',').map(i => i.trim()) : [];
        return `
            <div class="service-item">
                <div class="service-item-header">
                    <span class="service-item-name">${s.name}</span>
                    <span class="service-item-price">${s.price}₽</span>
                </div>
                ${inc.length ? '<ul class="service-item-includes">' + inc.map(i => `<li>${i}</li>`).join('') + '</ul>' : ''}
            </div>
        `;
    }

    const today = new Date().toISOString().split('T')[0];
    if (dateInput) dateInput.setAttribute('min', today);

    function loadSlots() {
        const serviceId = serviceSelect.value;
        const date = dateInput.value;
        if (!serviceId || !date) {
            timeSelect.innerHTML = '<option value="">— Сначала выберите услугу и дату —</option>';
            return;
        }
        timeSelect.innerHTML = '<option value="">Загрузка...</option>';
        fetch(`/api/slots?service_id=${serviceId}&date=${date}`)
            .then(r => r.json())
            .then(slots => {
                if (slots.error) {
                    timeSelect.innerHTML = `<option value="">${slots.error}</option>`;
                    return;
                }
                if (slots.length === 0) {
                    timeSelect.innerHTML = '<option value="">Нет свободных слотов</option>';
                    return;
                }
                timeSelect.innerHTML = slots.map(s =>
                    `<option value="${s.start}">${s.start} — ${s.end}</option>`
                ).join('');
            })
            .catch(() => {
                timeSelect.innerHTML = '<option value="">Ошибка загрузки</option>';
            });
    }

    if (serviceSelect) serviceSelect.addEventListener('change', loadSlots);
    if (dateInput) dateInput.addEventListener('change', loadSlots);

    document.querySelectorAll('.address-option').forEach(el => {
        el.addEventListener('click', () => {
            document.querySelectorAll('.address-option').forEach(o => o.classList.remove('active'));
            el.classList.add('active');
            el.querySelector('input[type="radio"]').checked = true;
        });
    });

    function updateSubmitState() {
        if (submitBtn) {
            submitBtn.disabled = !consentPolicy.checked;
        }
    }
    if (consentPolicy) {
        consentPolicy.addEventListener('change', updateSubmitState);
    }

    const phoneMask = (val) => {
        let digits = val.replace(/\D/g, '');
        if (digits.startsWith('7')) digits = digits.slice(1);
        if (digits.startsWith('8')) digits = digits.slice(1);
        digits = digits.slice(0, 10);
        if (!digits) return '+7 ';
        let result = '+7 ';
        if (digits.length > 0) result += '(' + digits.slice(0, 3);
        if (digits.length > 3) result += ') ' + digits.slice(3, 6);
        if (digits.length > 6) result += '-' + digits.slice(6, 8);
        if (digits.length > 8) result += '-' + digits.slice(8, 10);
        return result;
    };

    if (phoneInput) {
        phoneInput.addEventListener('input', () => {
            const cursor = phoneInput.selectionStart;
            const prevLen = phoneInput.value.length;
            phoneInput.value = phoneMask(phoneInput.value);
            const valid = phoneInput.value.replace(/\D/g, '').length >= 11;
            phoneError.textContent = valid ? '' : 'Некорректный номер телефона';
        });
    }

    if (emailInput) {
        emailInput.addEventListener('input', () => {
            const valid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailInput.value);
            emailError.textContent = valid ? '' : 'Некорректный email';
        });
    }

    if (bookingForm) {
        bookingForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const phoneValid = phoneInput.value.replace(/\D/g, '').length >= 11;
            const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailInput.value);

            if (!phoneValid || !emailValid) {
                formMessage.textContent = 'Проверьте правильность заполнения полей';
                formMessage.className = 'form-message error';
                return;
            }
            if (!consentPolicy.checked) {
                formMessage.textContent = 'Необходимо согласие с политикой конфиденциальности';
                formMessage.className = 'form-message error';
                return;
            }

            submitBtn.disabled = true;
            submitBtn.textContent = 'Отправка...';

            const selectedAddress = document.querySelector('.address-option.active');
            const address = selectedAddress ? selectedAddress.dataset.value : 'amg';

            const data = {
                name: bookingForm.querySelector('[name="name"]').value,
                phone: phoneInput.value,
                email: emailInput.value,
                service_id: parseInt(serviceSelect.value),
                date: dateInput.value,
                time: timeSelect.value,
                address: address,
                consent_policy: consentPolicy.checked ? 1 : 0,
                consent_mailing: bookingForm.querySelector('[name="consent_mailing"]').checked ? 1 : 0,
            };

            try {
                const res = await fetch('/api/book', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data),
                });
                const result = await res.json();
                if (result.success) {
                    formMessage.textContent = result.message;
                    formMessage.className = 'form-message success';
                    bookingForm.reset();
                    timeSelect.innerHTML = '<option value="">— Сначала выберите услугу и дату —</option>';
                    document.querySelectorAll('.address-option').forEach((o, i) => {
                        o.classList.toggle('active', i === 0);
                        o.querySelector('input[type="radio"]').checked = i === 0;
                    });
                    updateSubmitState();
                } else {
                    formMessage.textContent = result.error || 'Ошибка при записи';
                    formMessage.className = 'form-message error';
                }
            } catch (err) {
                formMessage.textContent = 'Ошибка сервера. Попробуйте позже.';
                formMessage.className = 'form-message error';
            }

            submitBtn.disabled = false;
            submitBtn.textContent = 'Записаться';
        });
    }
});

function openModal(id) {
    document.getElementById(id).classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeModal(id) {
    document.getElementById(id).classList.remove('active');
    document.body.style.overflow = '';
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal.active').forEach(m => m.classList.remove('active'));
        document.body.style.overflow = '';
    }
});

function rateBooking(bookingId, rating) {
    fetch('/api/rate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ booking_id: bookingId, rating: rating }),
    })
    .then(r => r.json())
    .then(result => {
        if (result.success) {
            const card = document.querySelector(`.booking-card[data-id="${bookingId}"] .stars`);
            if (card) {
                card.innerHTML = Array.from({length: 5}, (_, i) =>
                    `<span class="star active">${i < rating ? '★' : '☆'}</span>`
                ).join('');
            }
        }
        alert(result.message || result.error);
    });
}
