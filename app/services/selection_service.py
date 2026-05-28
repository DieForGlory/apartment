# app/services/selection_service.py

from flask import current_app, abort
from sqlalchemy.orm import joinedload

from . import currency_service
from ..core.db_utils import get_mysql_session, get_planning_session, get_default_session
import json
from datetime import date

from ..models.estate_models import EstateHouse, EstateSell
from ..models import planning_models
from ..models.exclusion_models import ExcludedSell
from ..models.planning_models import map_russian_to_mysql_key, map_mysql_key_to_russian_value

VALID_STATUSES = ["Маркетинговый резерв", "Qualified"]
DEDUCTION_AMOUNT = 3_000_000

MAX_MORTGAGE_STANDARD = 420_000_000
MIN_INITIAL_PAYMENT_PERCENT_STANDARD = 0.15


def find_apartments_by_budget(budget: float, currency: str, property_type_str: str, floor: str = None,
                              rooms: str = None, payment_method: str = None):
    mysql_session = get_mysql_session()
    planning_session = get_planning_session()
    default_session = get_default_session()

    usd_rate = currency_service.get_current_effective_rate() or 12650.0
    budget_KZT = budget * usd_rate if currency.upper() == 'USD' else budget

    active_version = planning_session.query(planning_models.DiscountVersion).filter_by(is_active=True).first()
    if not active_version:
        return {}

    property_type_enum = planning_models.PropertyType(property_type_str)
    mysql_category_key = map_russian_to_mysql_key(property_type_enum.value)

    discounts_map = {
        (d.complex_name, d.payment_method): d
        for d in planning_session.query(planning_models.Discount).filter_by(version_id=active_version.id,
                                                                            property_type=property_type_enum).all()
    }
    excluded_sell_ids = {e.sell_id for e in default_session.query(ExcludedSell).all()}

    query = mysql_session.query(EstateSell).options(
        joinedload(EstateSell.house)
    ).filter(
        EstateSell.estate_sell_category == mysql_category_key,
        EstateSell.estate_sell_status_name.in_(VALID_STATUSES),
        EstateSell.estate_price.isnot(None),
        EstateSell.estate_price > DEDUCTION_AMOUNT,
        EstateSell.id.notin_(excluded_sell_ids) if excluded_sell_ids else True
    )

    if floor and floor.isdigit():
        query = query.filter(EstateSell.estate_floor == int(floor))
    if rooms and rooms.isdigit():
        query = query.filter(EstateSell.estate_rooms == int(rooms))

    available_sells = query.all()
    results = {}
    default_discount = planning_models.Discount()

    payment_methods_to_check = list(planning_models.PaymentMethod)
    if payment_method:
        selected_pm_enum = next((pm for pm in planning_models.PaymentMethod if pm.value == payment_method), None)
        if selected_pm_enum:
            payment_methods_to_check = [selected_pm_enum]

    for sell in available_sells:
        if not sell.house: continue

        complex_name = sell.house.complex_name
        base_price = sell.estate_price

        for payment_method_enum in payment_methods_to_check:
            is_match = False
            apartment_details = {}
            price_after_deduction = base_price - DEDUCTION_AMOUNT
            discount = discounts_map.get((complex_name, payment_method_enum), default_discount)

            if payment_method_enum == planning_models.PaymentMethod.FULL_PAYMENT:
                total_discount_rate = (discount.mpp or 0) + (discount.rop or 0) + (discount.action or 0)
                final_price_KZT = price_after_deduction * (1 - total_discount_rate)
                if budget_KZT >= final_price_KZT:
                    is_match = True
                    apartment_details = {"final_price": final_price_KZT}

            elif payment_method_enum == planning_models.PaymentMethod.MORTGAGE:
                total_discount_rate = (discount.mpp or 0) + (discount.rop or 0) + (discount.action or 0)
                price_after_discounts = price_after_deduction * (1 - total_discount_rate)

                initial_payment_std = price_after_discounts - MAX_MORTGAGE_STANDARD
                min_required_std = price_after_discounts * MIN_INITIAL_PAYMENT_PERCENT_STANDARD
                if initial_payment_std >= min_required_std and budget_KZT >= initial_payment_std:
                    is_match = True
                    apartment_details = {"final_price": price_after_discounts, "initial_payment": initial_payment_std,
                                         "mortgage_type": "Стандартная"}

            if is_match:
                results.setdefault(complex_name, {"total_matches": 0, "by_payment_method": {}})
                payment_method_str = payment_method_enum.value
                results[complex_name]["by_payment_method"].setdefault(payment_method_str, {"total": 0, "by_rooms": {}})
                rooms_str = str(sell.estate_rooms) if sell.estate_rooms else "Студия"
                results[complex_name]["by_payment_method"][payment_method_str]["by_rooms"].setdefault(rooms_str, [])

                details = {"id": sell.id, "floor": sell.estate_floor, "area": sell.estate_area,
                           "base_price": base_price, **apartment_details}

                results[complex_name]["by_payment_method"][payment_method_str]["by_rooms"][rooms_str].append(details)
                results[complex_name]["by_payment_method"][payment_method_str]["total"] += 1
                results[complex_name]["total_matches"] += 1

    return results


def get_apartment_card_data(sell_id: int):
    mysql_session = get_mysql_session()
    planning_session = get_planning_session()

    sell = mysql_session.query(EstateSell).options(joinedload(EstateSell.house)).filter_by(id=sell_id).first()
    if not sell: abort(404)

    active_version = planning_session.query(planning_models.DiscountVersion).filter_by(is_active=True).first()
    if not active_version:
        return {'apartment': {}, 'pricing': [], 'all_discounts_for_property_type': []}

    russian_category_value = map_mysql_key_to_russian_value(sell.estate_sell_category)
    try:
        property_type_enum = planning_models.PropertyType(russian_category_value)
    except ValueError:
        return {'apartment': {}, 'pricing': [], 'all_discounts_for_property_type': []}

    all_discounts_for_property_type = planning_session.query(planning_models.Discount).filter_by(
        version_id=active_version.id,
        property_type=property_type_enum,
        complex_name=sell.house.complex_name
    ).all()

    serialized_discounts = [{
        'complex_name': d.complex_name, 'property_type': d.property_type.value,
        'payment_method': d.payment_method.value, 'mpp': d.mpp or 0.0, 'rop': d.rop or 0.0,
        'kd': d.kd or 0.0, 'opt': d.opt or 0.0, 'gd': d.gd or 0.0, 'holding': d.holding or 0.0,
        'shareholder': d.shareholder or 0.0, 'action': d.action or 0.0,
        'cadastre_date': d.cadastre_date.isoformat() if d.cadastre_date else None
    } for d in all_discounts_for_property_type]

    serialized_house = {
        'id': sell.house.id, 'complex_name': sell.house.complex_name, 'name': sell.house.name,
        'geo_house': sell.house.geo_house
    } if sell.house else {}

    serialized_apartment = {
        'id': sell.id, 'house_id': sell.house_id,
        'estate_sell_category': russian_category_value,
        'estate_floor': sell.estate_floor, 'estate_rooms': sell.estate_rooms, 'estate_price_m2': sell.estate_price_m2,
        'estate_sell_status_name': sell.estate_sell_status_name, 'estate_price': sell.estate_price,
        'estate_area': sell.estate_area, 'house': serialized_house
    }

    discounts_map = {
        (d['complex_name'], planning_models.PaymentMethod(d['payment_method'])): d
        for d in serialized_discounts
    }

    pricing_options = []
    base_price = serialized_apartment['estate_price']
    price_after_deduction = base_price - DEDUCTION_AMOUNT

    for payment_method_enum in planning_models.PaymentMethod:
        discount_data_for_method = discounts_map.get((serialized_house['complex_name'], payment_method_enum))
        mpp_val = discount_data_for_method.get('mpp', 0.0) if discount_data_for_method else 0.0
        rop_val = discount_data_for_method.get('rop', 0.0) if discount_data_for_method else 0.0

        if payment_method_enum == planning_models.PaymentMethod.FULL_PAYMENT:
            final_price = price_after_deduction * (1 - (mpp_val + rop_val))
            pricing_options.append({"payment_method": payment_method_enum.value, "type_key": "full_payment",
                                    "base_price": base_price, "deduction": DEDUCTION_AMOUNT,
                                    "price_after_deduction": price_after_deduction, "final_price": final_price,
                                    "initial_payment": None,
                                    "mortgage_body": None, "discounts": [{"name": "МПП", "value": mpp_val},
                                                                         {"name": "РОП", "value": rop_val}]})

        elif payment_method_enum == planning_models.PaymentMethod.MORTGAGE:
            if discount_data_for_method and (mpp_val > 0 or rop_val > 0):
                final_price_base = price_after_deduction * (1 - (mpp_val + rop_val))

                initial_payment_std = max(0, final_price_base - MAX_MORTGAGE_STANDARD)
                min_req_std = final_price_base * MIN_INITIAL_PAYMENT_PERCENT_STANDARD
                if initial_payment_std < min_req_std: initial_payment_std = min_req_std
                final_price_std = initial_payment_std + MAX_MORTGAGE_STANDARD
                pricing_options.append({"payment_method": "Ипотека (стандарт)", "type_key": "mortgage_standard",
                                        "base_price": base_price, "deduction": DEDUCTION_AMOUNT,
                                        "price_after_deduction": price_after_deduction,
                                        "final_price": final_price_std, "initial_payment": initial_payment_std,
                                        "mortgage_body": MAX_MORTGAGE_STANDARD,
                                        "discounts": [{"name": "МПП", "value": mpp_val},
                                                      {"name": "РОП", "value": rop_val}]})

    return {
        'apartment': serialized_apartment,
        'pricing': pricing_options,
        'all_discounts_for_property_type': serialized_discounts
    }