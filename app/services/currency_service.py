# app/services/currency_service.py

import requests
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
from app.core.extensions import db
from app.models.finance_models import CurrencySettings
from flask import current_app
from ..core.db_utils import get_default_session
from app.models.finance_models import DailyCurrencyRate

# API Национального Банка Казахстана
NBK_API_URL = "https://nationalbank.kz/rss/get_rates.cfm"


def sync_historical_rates(start_year=2020):
    """Загружает курсы валют из НБ РК начиная с указанного года по текущий день."""
    default_session = get_default_session()
    start_date = date(start_year, 1, 1)
    end_date = date.today()

    current_date = start_date
    headers = {'User-Agent': 'Mozilla/5.0'}

    while current_date <= end_date:
        if not default_session.get(DailyCurrencyRate, current_date):
            # НБ РК принимает дату в формате DD.MM.YYYY
            date_str = current_date.strftime('%d.%m.%Y')
            url = f"{NBK_API_URL}?fdate={date_str}"
            try:
                resp = requests.get(url, headers=headers, timeout=5, verify=False)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    for item in root.findall('item'):
                        if item.find('title').text == 'USD':
                            rate_float = float(item.find('description').text)
                            new_rate = DailyCurrencyRate(date=current_date, rate=rate_float)
                            default_session.add(new_rate)
                            break
                if current_date.day == 1:  # Коммит каждый месяц/неделю для надежности
                    default_session.commit()
            except Exception as e:
                print(f"Error for {date_str}: {e}")

        current_date += timedelta(days=1)

    default_session.commit()


def get_rate_for_date(target_date):
    """Возвращает курс на дату. Если настройки требуют исторический курс — берет из БД, иначе текущий эффективный."""
    settings = _get_settings()
    if not settings.use_historical_rate:
        return settings.effective_rate

    rate_record = get_default_session().get(DailyCurrencyRate, target_date)
    return rate_record.rate if rate_record else settings.effective_rate


def _get_settings():
    """Вспомогательная функция для получения единственной строки настроек."""
    default_session = get_default_session()
    settings = default_session.get(CurrencySettings, 1)
    if not settings:
        settings = CurrencySettings(id=1)
        default_session.add(settings)
        settings.manual_rate = 450.0  # Дефолтный курс для тенге (KZT)
        settings.update_effective_rate()
        default_session.commit()
    return settings


def update_cbu_rate():
    """
    Основная логика обновления курса с сайта НБ РК.
    Название функции оставлено update_cbu_rate для совместимости с планировщиком (Scheduler).
    """
    default_session = get_default_session()
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        # Получаем курс на сегодняшний день
        today_str = datetime.now().strftime("%d.%m.%Y")
        url = f"{NBK_API_URL}?fdate={today_str}"

        response = requests.get(url, headers=headers, timeout=10, verify=False)
        response.raise_for_status()

        # Парсинг XML
        root = ET.fromstring(response.content)
        rate_float = None

        for item in root.findall('item'):
            if item.find('title').text == 'USD':
                rate_float = float(item.find('description').text)
                break

        if rate_float is None:
            print("Error: NBK returned empty data for USD")
            return False

        settings = _get_settings()
        # Поля в БД называются cbu_rate, оставляем их для совместимости
        settings.cbu_rate = rate_float
        settings.cbu_last_updated = datetime.utcnow()

        # Если выбран источник банка, обновляем и эффективный курс
        if settings.rate_source == 'cbu':
            settings.update_effective_rate()

        default_session.commit()
        print(f"Successfully updated NBK rate to: {rate_float}")
        return True

    except requests.RequestException as e:
        print(f"Error fetching NBK rate: {e}")
        default_session.rollback()
        return False
    except (ValueError, ET.ParseError) as e:
        print(f"Error parsing NBK XML data: {e}")
        default_session.rollback()
        return False


def set_rate_source(source: str):
    default_session = get_default_session()
    """Устанавливает источник курса ('cbu' или 'manual')."""
    if source not in ['cbu', 'manual']:
        raise ValueError("Source must be 'cbu' or 'manual'")

    settings = _get_settings()
    settings.rate_source = source
    settings.update_effective_rate()
    default_session.commit()


def set_manual_rate(rate: float):
    default_session = get_default_session()
    """Устанавливает курс вручную."""
    if rate <= 0:
        raise ValueError("Rate must be positive")

    settings = _get_settings()
    settings.manual_rate = rate

    if settings.rate_source == 'manual':
        settings.update_effective_rate()

    default_session.commit()


def get_current_effective_rate():
    """ЕДИНАЯ функция для получения актуального курса для всех расчетов."""
    settings = _get_settings()
    return settings.effective_rate