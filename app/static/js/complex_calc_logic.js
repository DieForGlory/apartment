document.addEventListener('DOMContentLoaded', () => {
    const templateSelect = document.getElementById('templateSelect');
    const scheduleConstructor = document.getElementById('scheduleConstructor');
    const scheduleBody = document.getElementById('scheduleBody');
    const btnAddPayment = document.getElementById('btnAddPayment');
    const btnAutoDistribute = document.getElementById('btnAutoDistribute');
    const btnValidateSchedule = document.getElementById('btnValidateSchedule');

    const targetAmountDisplay = document.getElementById('targetAmountDisplay');
    const distributedAmountDisplay = document.getElementById('distributedAmountDisplay');
    const remainingAmountDisplay = document.getElementById('remainingAmountDisplay');
    const validationResultBox = document.getElementById('validationResultBox');

    // Значение должно подтягиваться из расчета цены со скидками
    let currentTargetPrice = parseFloat(document.getElementById('basePriceRaw').value) || 0;
    let maxTermMonths = 0;

    function init() {
        bindEvents();
    }

    function bindEvents() {
        templateSelect.addEventListener('change', (e) => {
            const selectedOption = e.target.options[e.target.selectedIndex];
            if (e.target.value) {
                maxTermMonths = parseInt(selectedOption.dataset.maxTerm, 10);
                scheduleConstructor.style.display = 'block';
                resetSchedule();
            } else {
                scheduleConstructor.style.display = 'none';
            }
        });

        btnAddPayment.addEventListener('click', () => addScheduleRow());

        btnAutoDistribute.addEventListener('click', autoDistributeRemainder);

        scheduleBody.addEventListener('input', (e) => {
            if (e.target.classList.contains('amount-input') || e.target.classList.contains('month-input')) {
                recalculateBalance();
            }
        });

        scheduleBody.addEventListener('click', (e) => {
            if (e.target.classList.contains('btn-remove-row')) {
                e.target.closest('tr').remove();
                recalculateBalance();
            }
        });

        btnValidateSchedule.addEventListener('click', executeValidation);
    }

    function resetSchedule() {
        scheduleBody.innerHTML = '';
        addScheduleRow(0); // Обязательный ПВ
        recalculateBalance();
    }

    function addScheduleRow(monthIndex = null, amount = '') {
        const nextMonth = monthIndex !== null ? monthIndex : getNextAvailableMonth();
        const tr = document.createElement('tr');

        const isInitial = nextMonth === 0;

        tr.innerHTML = `
            <td>
                <input type="number" class="form-control form-control-sm bg-dark text-white border-secondary rounded-0 month-input"
                       min="0" max="${maxTermMonths}" step="1" value="${nextMonth}" ${isInitial ? 'readonly' : ''}>
            </td>
            <td>
                <input type="number" class="form-control form-control-sm bg-dark text-white border-secondary rounded-0 amount-input"
                       min="0" step="1" value="${amount}" placeholder="Сумма транша">
            </td>
            <td class="text-end">
                ${!isInitial ? `<button class="btn btn-sm btn-outline-danger rounded-0 btn-remove-row">✖</button>` : ''}
            </td>
        `;
        scheduleBody.appendChild(tr);
    }

    function getNextAvailableMonth() {
        const inputs = Array.from(scheduleBody.querySelectorAll('.month-input'));
        if (inputs.length === 0) return 0;
        const maxCurrent = Math.max(...inputs.map(i => parseInt(i.value || 0, 10)));
        return Math.min(maxCurrent + 1, maxTermMonths);
    }

    function recalculateBalance() {
        const amounts = Array.from(scheduleBody.querySelectorAll('.amount-input'));
        const distributed = amounts.reduce((sum, input) => sum + (parseFloat(input.value) || 0), 0);
        const remaining = currentTargetPrice - distributed;

        targetAmountDisplay.textContent = formatCurrency(currentTargetPrice);
        distributedAmountDisplay.textContent = formatCurrency(distributed);
        remainingAmountDisplay.textContent = formatCurrency(remaining);

        if (Math.abs(remaining) < 1) {
            remainingAmountDisplay.className = 'fw-bold text-success';
            btnValidateSchedule.disabled = false;
        } else {
            remainingAmountDisplay.className = 'fw-bold text-danger';
            btnValidateSchedule.disabled = true;
        }
    }

    function autoDistributeRemainder() {
        const amounts = Array.from(scheduleBody.querySelectorAll('.amount-input'));
        const distributed = amounts.reduce((sum, input) => sum + (parseFloat(input.value) || 0), 0);
        let remaining = currentTargetPrice - distributed;

        if (remaining <= 0) return;

        const emptyInputs = amounts.filter(input => !input.value || parseFloat(input.value) === 0);

        if (emptyInputs.length > 0) {
            const splitAmount = Math.floor(remaining / emptyInputs.length);
            let remainderObj = remaining - (splitAmount * emptyInputs.length);

            emptyInputs.forEach((input, index) => {
                input.value = splitAmount + (index === emptyInputs.length - 1 ? remainderObj : 0);
            });
        } else {
            addScheduleRow(getNextAvailableMonth(), remaining);
        }
        recalculateBalance();
    }

    function formatCurrency(val) {
        return new Intl.NumberFormat('ru-RU').format(val);
    }

    async function executeValidation() {
        const templateId = templateSelect.value;
        const schedule = Array.from(scheduleBody.querySelectorAll('tr')).map(tr => ({
            month_index: parseInt(tr.querySelector('.month-input').value, 10),
            amount: parseFloat(tr.querySelector('.amount-input').value)
        }));

        btnValidateSchedule.disabled = true;
        btnValidateSchedule.textContent = 'ОБРАБОТКА МАТРИЦЫ...';

        try {
            const payload = {
                sell_id: SELL_ID,
                template_id: parseInt(templateId, 10),
                schedule: schedule,
                discounts: getActiveDiscounts() // Функция из старого скрипта для сбора %
            };

            const response = await fetch('/api/validate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await response.json();
            renderValidationState(data, response.ok);
        } catch (err) {
            renderValidationState({ error: "Ошибка соединения с сервером" }, false);
        } finally {
            btnValidateSchedule.disabled = false;
            btnValidateSchedule.textContent = 'ПРОВЕРИТЬ И ЗАФИКСИРОВАТЬ ГРАФИК';
        }
    }

    function renderValidationState(data, isOk) {
        validationResultBox.classList.remove('d-none');
        const statusText = document.getElementById('validationStatusText');

        if (isOk && data.is_valid) {
            validationResultBox.className = 'mt-4 p-3 border border-success bg-success bg-opacity-10';
            statusText.className = 'fw-bold mb-3 text-success';
            statusText.textContent = 'График успешно верифицирован';

            document.getElementById('valTerm').textContent = `${data.term_months} мес.`;
            document.getElementById('valDp').textContent = formatCurrency(data.initial_payment);
            document.getElementById('valNrv').textContent = `${data.nrv_percent}%`;
            document.getElementById('valNrv').className = 'fs-4 fw-bold text-success';
        } else {
            validationResultBox.className = 'mt-4 p-3 border border-danger bg-danger bg-opacity-10';
            statusText.className = 'fw-bold mb-3 text-danger';
            statusText.textContent = `Отказ валидации: ${data.error}`;

            document.getElementById('valTerm').textContent = '—';
            document.getElementById('valDp').textContent = '—';
            document.getElementById('valNrv').textContent = '—';
            document.getElementById('valNrv').className = 'fs-4 fw-bold text-danger';
        }
    }

    init();
});