import re
from typing import Optional

def clean_html(html_content: Optional[str]) -> str:
    """Очистка HTML и преобразование в текст"""
    if not html_content:
        return ""
    # Удаляем HTML теги
    text = re.sub(r'<[^>]+>', '', html_content)
    # Заменяем HTML entities
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&#x2F;', '/')
    # Убираем множественные переносы строк
    text = re.sub(r'\n\s*\n', '\n\n', text)
    # Убираем лишние пробелы в начале и конце каждой строки
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)
    return text.strip()