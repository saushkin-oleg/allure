#!/usr/bin/env python3
"""
Allure TestOps Exporter
Главный скрипт для экспорта тест-кейсов из Allure TestOps в PDF
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Optional

from src.allure_api import AllureAPI
from src.pdf_generator import PDFGenerator
from src.exporters.single_test_exporter import SingleTestExporter
from src.exporters.testplan_exporter import TestPlanExporter

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

CONFIG_TEMPLATE = {
    "api_token": "your_api_token_here",
    "allure_url": "https://allure-testops.example.com",
    "output_dir": "./exports",
    "testplan_id": 1,
    "testcase_id": 2,
    "project_id": 3,
    "filter_prefix": "EXAMPLE"
}

def load_config(config_path: str = "config.json") -> Dict:
    """Загрузка конфигурации из JSON файла"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Проверка обязательных полей
        required_fields = ['api_token', 'allure_url']
        missing = [field for field in required_fields if field not in config]
        
        if missing:
            raise ValueError(f"В конфигурации отсутствуют поля: {', '.join(missing)}")
        
        logger.info(f"✅ Конфигурация загружена из {config_path}")
        return config
        
    except FileNotFoundError:
        logger.error(f"❌ Файл конфигурации {config_path} не найден")
        _create_config_template(config_path)
        sys.exit(1)
    except json.JSONDecodeError:
        logger.error(f"❌ Ошибка парсинга JSON в файле {config_path}")
        sys.exit(1)

def _create_config_template(config_path: str):
    """Создание шаблона файла конфигурации (внутренняя функция)"""
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(CONFIG_TEMPLATE, f, indent=4, ensure_ascii=False)
    
    logger.info(f"📝 Создан шаблон конфигурации: {config_path}")
    logger.info("✏️ Заполните его реальными данными и запустите скрипт снова")

def main():
    parser = argparse.ArgumentParser(description='Allure TestOps Exporter')
    parser.add_argument('--config', '-c', default='config.json', help='Путь к файлу конфигурации')
    parser.add_argument('--mode', '-m', choices=['testplan', 'single', 'both'], 
                       default='both', help='Режим экспорта')
    parser.add_argument('--testplan-id', type=int, help='ID тест-плана (переопределяет конфиг)')
    parser.add_argument('--testcase-id', type=int, help='ID тест-кейса (переопределяет конфиг)')
    parser.add_argument('--project-id', type=int, help='ID проекта (переопределяет конфиг)')
    parser.add_argument('--output-dir', help='Директория для сохранения (переопределяет конфиг)')
    parser.add_argument('--no-raw', action='store_true', help='Не сохранять сырые JSON')
    parser.add_argument('--include-raw-pdf', action='store_true', 
                       help='Включать сырые данные в PDF')
    
    args = parser.parse_args()
    
    # Загружаем конфигурацию
    config = load_config(args.config)
    
    # Переопределяем параметры из аргументов командной строки
    if args.testplan_id:
        config['testplan_id'] = args.testplan_id
    if args.testcase_id:
        config['testcase_id'] = args.testcase_id
    if args.project_id:
        config['project_id'] = args.project_id
    if args.output_dir:
        config['output_dir'] = args.output_dir
    
    # Создаем компоненты
    api = AllureAPI(config['allure_url'], config['api_token'])
    pdf_gen = PDFGenerator()
    output_dir = Path(config['output_dir'])
    
    # Экспортируем в зависимости от режима
    if args.mode in ('testplan', 'both'):
        exporter = TestPlanExporter(api, pdf_gen, output_dir / "testplan")
        exporter.export(
            testplan_id=config['testplan_id'],
            filter_prefix=config.get('filter_prefix', 'NTPR'),
            save_raw=not args.no_raw,
            include_raw_in_pdf=args.include_raw_pdf
        )
    
    if args.mode == 'single' or (args.mode == 'both' and args.testcase_id):
        exporter = SingleTestExporter(api, pdf_gen, output_dir / "debug")
        exporter.export(
            testcase_id=config['testcase_id'],
            project_id=config['project_id'],
            save_raw=not args.no_raw,
            include_raw_in_pdf=args.include_raw_pdf
        )

if __name__ == '__main__':
    main()