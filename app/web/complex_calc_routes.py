# app/web/complex_calc_routes.py

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required
from app.services import selection_service, complex_calc_service
from app.core.decorators import permission_required
from app.core.db_utils import get_planning_session
from app.models.planning_models import PaymentTemplate

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