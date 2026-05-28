# app/web/settings_routes.py

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from app.core.decorators import permission_required
from app.core.db_utils import get_planning_session, get_mysql_session, get_default_session
from app.models.planning_models import PaymentTemplate
from app.services import settings_service
from app.models.estate_models import EstateHouse
from app.models import auth_models

settings_bp = Blueprint('settings', __name__, template_folder='templates')

# --- МАРШРУТЫ ДЛЯ КОНСТРУКТОРА КАЛЬКУЛЯТОРОВ ---

@settings_bp.route('/settings/calculator', methods=['GET', 'POST'])
@login_required
@permission_required('manage_settings')
def calculator_settings():
    planning_session = get_planning_session()
    if request.method == 'POST':
        name = request.form.get('name')
        max_term = request.form.get('max_term_months')
        min_dp = request.form.get('min_initial_payment_percent')
        min_nrv = request.form.get('min_nrv_percent')
        rate = request.form.get('discount_rate_annual')
        require_nrv = request.form.get('require_nrv_validation') == 'on'

        try:
            template = PaymentTemplate(
                name=name,
                max_term_months=int(max_term),
                min_initial_payment_percent=float(min_dp),
                min_nrv_percent=float(min_nrv) if require_nrv else 0.0,
                discount_rate_annual=float(rate) if require_nrv else 0.0,
                require_nrv_validation=require_nrv,
                is_active=True
            )
            planning_session.add(template)
            planning_session.commit()
            flash("Шаблон успешно создан", "success")
        except Exception as e:
            planning_session.rollback()
            flash(f"Ошибка при создании шаблона: {str(e)}", "danger")
        return redirect(url_for('settings.calculator_settings'))

    templates = planning_session.query(PaymentTemplate).all()
    return render_template('settings/calculator_settings.html', templates=templates, title="Настройки калькулятора")

@settings_bp.route('/settings/calculator/toggle/<int:template_id>', methods=['POST'])
@login_required
@permission_required('manage_settings')
def toggle_template(template_id):
    planning_session = get_planning_session()
    template = planning_session.query(PaymentTemplate).get(template_id)
    if template:
        template.is_active = not template.is_active
        planning_session.commit()
        return jsonify({"success": True, "is_active": template.is_active})
    return jsonify({"success": False, "error": "Шаблон не найден"}), 404

@settings_bp.route('/settings/calculator/delete/<int:template_id>', methods=['POST'])
@login_required
@permission_required('manage_settings')
def delete_template(template_id):
    planning_session = get_planning_session()
    template = planning_session.query(PaymentTemplate).get(template_id)
    if template:
        planning_session.delete(template)
        planning_session.commit()
        flash("Шаблон удален", "success")
    return redirect(url_for('settings.calculator_settings'))


# --- ВОССТАНОВЛЕННЫЕ МАРШРУТЫ ИЗ СТАРОГО ФАЙЛА ---

@settings_bp.route('/manage-inventory-exclusions', methods=['GET', 'POST'])
@login_required
@permission_required('manage_settings')
def manage_inventory_exclusions():
    """Страница для управления исключенными ЖК из сводки по остаткам."""
    if request.method == 'POST':
        complex_name = request.form.get('complex_name')
        if complex_name:
            message, category = settings_service.toggle_complex_exclusion(complex_name)
            flash(message, category)
        return redirect(url_for('settings.manage_inventory_exclusions'))

    mysql_session = get_mysql_session()
    all_complexes = mysql_session.query(EstateHouse.complex_name).distinct().order_by(
        EstateHouse.complex_name).all()
    excluded_complexes = settings_service.get_all_excluded_complexes()
    excluded_names = {c.complex_name for c in excluded_complexes}

    return render_template(
        'settings/manage_exclusions.html',
        title="Исключения в сводке по остаткам",
        all_complexes=[c[0] for c in all_complexes],
        excluded_names=excluded_names
    )

@settings_bp.route('/email-recipients', methods=['GET', 'POST'])
@login_required
@permission_required('manage_settings')
def manage_email_recipients():
    """Страница для управления получателями email-уведомлений."""
    default_session = get_default_session()

    if request.method == 'POST':
        selected_user_ids = request.form.getlist('recipient_ids', type=int)

        default_session.query(auth_models.EmailRecipient).delete()

        for user_id in selected_user_ids:
            recipient = auth_models.EmailRecipient(user_id=user_id)
            default_session.add(recipient)

        default_session.commit()
        flash('Список получателей уведомлений успешно обновлен.', 'success')
        return redirect(url_for('settings.manage_email_recipients'))

    all_users = default_session.query(auth_models.User).order_by(auth_models.User.full_name).all()
    subscribed_user_ids = {r.user_id for r in default_session.query(auth_models.EmailRecipient).all()}

    return render_template(
        'settings/manage_recipients.html',
        title="Получатели уведомлений",
        all_users=all_users,
        subscribed_user_ids=subscribed_user_ids
    )