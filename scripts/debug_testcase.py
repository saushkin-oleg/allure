#!/usr/bin/env python3
"""
Скрипт для отладки одного тест-кейса
"""

import sys
from pathlib import Path

# Добавляем родительскую директорию в путь для импорта
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import load_config
from src.allure_api import AllureAPI
from src.pdf_generator import PDFGenerator
from src.exporters.single_test_exporter import SingleTestExporter

def main():
    config = load_config()
    
    api = AllureAPI(config['allure_url'], config['api_token'])
    pdf_gen = PDFGenerator()
    output_dir = Path(config['output_dir']) / "debug"
    
    exporter = SingleTestExporter(api, pdf_gen, output_dir)
    exporter.export(
        testcase_id=config['testcase_id'],
        project_id=config['project_id'],
        save_raw=True,
        include_raw_in_pdf=True
    )

if __name__ == '__main__':
    main()