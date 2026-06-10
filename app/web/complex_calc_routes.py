# app/web/complex_calc_routes.py

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required
from app.services import selection_service, complex_calc_service
from app.core.decorators import permission_required
from app.core.db_utils import get_planning_session
from app.models.planning_models import PaymentTemplate
import json
from datetime import datetime
from flask import Blueprint, render_template, request, abort

complex_calc_bp = Blueprint('complex_calc', __name__, template_folder='templates')


@complex_calc_bp.route('/complex-calculations/<int:sell_id>')
@login_required
@permission_required('view_selection')
def show_page(sell_id):
    """Отображает страницу конструктора сложных расчетов."""
    card_data = selection_service.get_apartment_card_data(sell_id)
    if not card_data or not card_data.get('apartment'):
        flash("Объект не найден.", "danger")
        return redirect(url_for('main.selection'))

    planning_session = get_planning_session()
    templates = planning_session.query(PaymentTemplate).filter_by(is_active=True).all()

    return render_template(
        'calc/complex_calculations.html',
        data=card_data,
        templates=templates,
        title=f"Конструктор рассрочек: ID {sell_id}"
    )

@complex_calc_bp.route('/generate-offer', methods=['POST'])
def generate_offer():
    raw_payload = request.form.get('payload')
    if not raw_payload:
        abort(400, description="Missing payload data")

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        abort(400, description="Invalid JSON payload")

    sell_id = payload.get('sell_id')
    schedule = payload.get('schedule', [])
    discounts = payload.get('discounts', {})

    data = selection_service.get_apartment_card_data(sell_id)
    if not data or not data.get('apartment'):
        from flask import abort
        abort(404, description="Объект недвижимости не найден")

    # Расчет суммарных финансовых показателей на основе пришедшего графика
    total_nominal_price = sum(item['amount'] for item in schedule)

    # Извлечение суммы первоначального взноса (транш с индексом месяца 0)
    initial_payment_amount = 0
    for item in schedule:
        if item.get('month_index') == 0:
            initial_payment_amount = item['amount']
            break

    initial_payment_percent = 0
    if total_nominal_price > 0:
        initial_payment_percent = round((initial_payment_amount / total_nominal_price) * 100, 1)

    current_date_str = datetime.now().strftime('%d.%m.%Y')

    return render_template(
        'calc/commercial_offer_print.html',
        data=data,
        schedule=schedule,
        discounts=discounts,
        total_nominal_price=total_nominal_price,
        initial_payment_amount=initial_payment_amount,
        initial_payment_percent=initial_payment_percent,
        current_date=current_date_str
    )
@complex_calc_bp.route('/api/validate', methods=['POST'])
@login_required
@permission_required('view_selection')
def validate_schedule():
    """Обрабатывает AJAX-запрос для валидации кастомного графика платежей."""
    req_data = request.get_json()
    try:
        sell_id = req_data.get('sell_id')
        template_id = req_data.get('template_id')
        schedule = req_data.get('schedule', [])

        discounts = {
            k: float(v) for k, v in req_data.get('discounts', {}).items() if v and float(v) > 0
        }

        result = complex_calc_service.validate_constructor_schedule(
            sell_id=sell_id,
            template_id=template_id,
            provided_schedule=schedule,
            additional_discounts=discounts
        )
        return jsonify(result)
    except ValueError as e:
        # 400 - Ошибка валидации (правила NRV не пройдены)
        return jsonify({"is_valid": False, "error": str(e)}), 400
    except Exception as e:
        # 500 - Критическая ошибка кода
        current_app.logger.error(f"Critical error in schedule validation: {e}")
        return jsonify({"is_valid": False, "error": "Внутренняя ошибка сервера. Проверьте консоль Python."}), 500