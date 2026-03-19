"""
Утилиты для проекта Allure TestOps Exporter
"""

import re
from datetime import datetime
from typing import Dict, List, Optional


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


def remove_bold_markers(text: str) -> str:
    """
    Удаляет маркдаун-разметку **жирный текст** из строки
    
    Args:
        text: исходный текст с маркдаун-разметкой
        
    Returns:
        текст без маркдаун-разметки
    """
    if not text:
        return ""
    # Удаляем ** с обоих сторон
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    return text


def format_timestamp(timestamp: Optional[int]) -> str:
    """Форматирование timestamp в дату"""
    if not timestamp:
        return "Не указано"
    try:
        return datetime.fromtimestamp(timestamp / 1000).strftime('%d.%m.%Y %H:%M:%S')
    except:
        return str(timestamp)


def parse_steps(step_data: Optional[Dict]) -> List[Dict]:
    """
    Парсинг шагов из ответа эндпоинта /step
    
    Args:
        step_data: данные из /testcase/{id}/step
        
    Returns:
        список корневых шагов с полной структурой
    """
    steps = []
    
    if not step_data or not isinstance(step_data, dict):
        return steps
    
    scenario_steps = step_data.get('scenarioSteps', {})
    root_children = step_data.get('root', {}).get('children', [])
    
    # Сначала создадим словарь всех шагов для быстрого доступа
    steps_dict = {}
    for step_id, step in scenario_steps.items():
        steps_dict[int(step_id)] = step
    
    def build_step_tree(step_id, visited=None):
        if visited is None:
            visited = set()
        
        # Защита от циклов
        if step_id in visited:
            return None
        visited.add(step_id)
        
        if step_id not in steps_dict:
            return None
        
        step = steps_dict[step_id]
        
        # Проверяем, является ли шаг контейнером для ожидаемых результатов
        is_expected_container = step.get('body') == "Expected Result"
        
        step_info = {
            'id': step.get('id'),
            'body': step.get('body'),
            'bodyJson': step.get('bodyJson'),
            'is_expected_container': is_expected_container,
            'expected_results': [],  # Сюда будут собраны ожидаемые результаты
            'children': []
        }
        
        # Если у шага есть expectedResultId, это ссылка на ожидаемый результат
        if 'expectedResultId' in step and not is_expected_container:
            expected_id = step['expectedResultId']
            if expected_id in steps_dict:
                expected_container = steps_dict[expected_id]
                # Собираем все дочерние шаги expected_container как ожидаемые результаты
                for child_id in expected_container.get('children', []):
                    if child_id in steps_dict:
                        child_step = steps_dict[child_id]
                        # Рекурсивно строим дерево для ожидаемого результата
                        expected_step_info = {
                            'id': child_step.get('id'),
                            'body': child_step.get('body'),
                            'bodyJson': child_step.get('bodyJson'),
                            'is_expected': True,
                            'children': []
                        }
                        # Добавляем дочерние шаги ожидаемого результата
                        for grandchild_id in child_step.get('children', []):
                            if grandchild_id in steps_dict:
                                grandchild = build_step_tree(grandchild_id, visited.copy())
                                if grandchild:
                                    expected_step_info['children'].append(grandchild)
                        
                        step_info['expected_results'].append(expected_step_info)
        
        # Обрабатываем дочерние шаги
        for child_id in step.get('children', []):
            # Пропускаем, если это контейнер ожидаемых результатов (они уже обработаны)
            if child_id in steps_dict and steps_dict[child_id].get('body') == "Expected Result":
                continue
            
            child_step = build_step_tree(child_id, visited.copy())
            if child_step:
                step_info['children'].append(child_step)
        
        return step_info
    
    # Строим дерево для каждого корневого шага
    for root_id in root_children:
        root_step = build_step_tree(root_id)
        if root_step:
            steps.append(root_step)
    
    return steps