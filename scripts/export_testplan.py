#!/usr/bin/env python3
"""
Скрипт для экспорта всего тест-плана
"""

import sys
from pathlib import Path

# Добавляем родительскую директорию в путь для импорта
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import load_config
from src.allure_api import AllureAPI
from src.pdf_generator import PDFGenerator
from src.exporters.testplan_exporter import TestPlanExporter

def main():
    config = load_config()
    
    api = AllureAPI(config['allure_url'], config['api_token'])
    pdf_gen = PDFGenerator()
    output_dir = Path(config['output_dir']) / "testplan"
    
    exporter = TestPlanExporter(api, pdf_gen, output_dir)
    exporter.export(
        testplan_id=config['testplan_id'],
        filter_prefix=config.get('filter_prefix', 'NTPR'),
        save_raw=True,
        include_raw_in_pdf=False
    )

if __name__ == '__main__':
    main()