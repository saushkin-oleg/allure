from datetime import datetime
from typing import Optional

def format_timestamp(timestamp: Optional[int]) -> str:
    """Форматирование timestamp в дату"""
    if not timestamp:
        return "Не указано"
    try:
        return datetime.fromtimestamp(timestamp / 1000).strftime('%d.%m.%Y %H:%M:%S')
    except:
        return str(timestamp)