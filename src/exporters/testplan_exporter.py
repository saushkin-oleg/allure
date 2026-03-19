import logging
import re
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from src.allure_api import AllureAPI
from src.pdf_generator import PDFGenerator
from src.utils import parse_steps  # ИЗМЕНЕНО: импорт из utils вместо step_parser

logger = logging.getLogger(__name__)

class TestPlanExporter:
    """Экспортер для всего тест-плана"""
    
    def __init__(self, api: AllureAPI, pdf_generator: PDFGenerator, output_dir: Path):
        """
        Инициализация экспортера
        
        Args:
            api: экземпляр AllureAPI
            pdf_generator: экземпляр PDFGenerator
            output_dir: директория для сохранения результатов
        """
        self.api = api
        self.pdf_generator = pdf_generator
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _group_by_section(self, testcases: List[Dict]) -> List[Dict]:
        """
        Группировка тест-кейсов по разделам на основе названия
        """
        sections = {}
        
        for tc in testcases:
            name = tc.get('name', '')
            
            # Пробуем извлечь раздел из названия [NTPR-XX]
            section_name = "Общее"
            match = re.match(r'\[(NTPR-\d+)\]', name)
            if match:
                section_name = match.group(1)
            else:
                # Пробуем извлечь первую часть до пробела или скобки
                match = re.match(r'^\[([^\]]+)\]', name)
                if match:
                    section_name = match.group(1)
            
            if section_name not in sections:
                sections[section_name] = {
                    'name': section_name,
                    'testCases': []
                }
            sections[section_name]['testCases'].append(tc)
        
        # Сортируем разделы
        result = list(sections.values())
        
        def section_sort_key(section):
            name = section['name']
            if name.startswith('NTPR-'):
                try:
                    num = int(name.split('-')[1])
                    return (0, num)
                except:
                    return (0, name)
            else:
                return (1, name)
        
        result.sort(key=section_sort_key)
        
        # Сортируем тест-кейсы внутри разделов
        for section in result:
            section['testCases'].sort(key=lambda x: x.get('name', ''))
        
        return result
    
    def export(self, testplan_id: int, filter_prefix: str = "NTPR",
               save_raw: bool = True, include_raw_in_pdf: bool = False) -> Optional[Path]:
        """
        Экспорт тест-плана
        
        Args:
            testplan_id: ID тест-плана
            filter_prefix: префикс для фильтрации тест-кейсов (например, "NTPR")
            save_raw: сохранять ли сырые JSON
            include_raw_in_pdf: включать ли сырые данные в PDF
            
        Returns:
            путь к созданному PDF или None при ошибке
        """
        logger.info(f"🚀 Начинаем экспорт тест-плана {testplan_id}...")
        
        # 1. Получаем информацию о тест-плане
        logger.info("📥 Получаем информацию о тест-плане...")
        testplan = self.api.get_testplan(testplan_id)
        if not testplan:
            logger.error("❌ Не удалось получить тест-план")
            return None
        
        if save_raw:
            self.api.save_json(testplan, self.output_dir / "testplan_info.json")
        
        # 2. Получаем projectId
        project_id = testplan.get('projectId')
        if not project_id:
            logger.error("❌ Не удалось определить projectId")
            return None
        
        logger.info(f"📌 Project ID: {project_id}")
        
        # 3. Получаем все тест-кейсы из тест-плана
        logger.info("📥 Получаем тест-кейсы из тест-плана...")
        all_testcases = self.api.get_testcases_from_testplan(testplan_id, project_id)
        
        if not all_testcases:
            logger.error("❌ Не удалось получить тест-кейсы")
            return None
        
        # 4. Фильтруем по префиксу
        filtered_testcases = []
        for tc in all_testcases:
            name = tc.get('name', '')
            if name and name.startswith(f'[{filter_prefix}'):
                filtered_testcases.append(tc)
        
        logger.info(f"🎯 Найдено тест-кейсов с префиксом [{filter_prefix}: {len(filtered_testcases)}")
        
        if not filtered_testcases:
            logger.error("❌ Нет тест-кейсов для экспорта")
            return None
        
        # 5. Загружаем детальную информацию для каждого
        logger.info("📥 Загружаем детальную информацию...")
        detailed_testcases = []
        
        for i, tc in enumerate(filtered_testcases, 1):
            tc_id = tc.get('id')
            if not tc_id:
                continue
            
            logger.info(f"  ⏳ [{i}/{len(filtered_testcases)}] Загружаем тест-кейс {tc_id}...")
            
            # Основная информация
            tc_detail = self.api.get_testcase(tc_id, project_id)
            if not tc_detail:
                continue
            
            # Шаги
            step_data = self.api.get_testcase_steps(tc_id, project_id)
            steps = parse_steps(step_data) if step_data else []
            
            # Дополнительные данные
            comments = self.api.get_testcase_comments(tc_id, project_id)
            audit = self.api.get_testcase_audit(tc_id, project_id)
            
            detailed_testcases.append({
                **tc_detail,
                'steps': steps,
                'comments': comments if comments else [],
                'audit': audit if audit else [],
                'generated_at': int(datetime.now().timestamp() * 1000)
            })
        
        logger.info(f"✅ Загружено деталей: {len(detailed_testcases)} из {len(filtered_testcases)}")
        
        # 6. Группируем по разделам
        logger.info("📊 Группируем по разделам...")
        sections = self._group_by_section(detailed_testcases)
        
        if save_raw:
            self.api.save_json(sections, self.output_dir / "testplan_sections.json")
        
        # 7. Генерируем PDF
        pdf_path = self.output_dir / f"testplan_{testplan_id}_full.pdf"
        self.pdf_generator.generate_testplan_pdf(
            sections, 
            testplan_id, 
            pdf_path, 
            include_raw_data=include_raw_in_pdf
        )
        
        # 8. Итоговая статистика
        total_tests = sum(len(section['testCases']) for section in sections)
        logger.info("\n" + "="*50)
        logger.info("🎉 ЭКСПОРТ ЗАВЕРШЕН УСПЕШНО")
        logger.info("="*50)
        logger.info(f"📁 Директория: {self.output_dir.absolute()}")
        logger.info(f"📊 Тест-план #{testplan_id} (projectId: {project_id})")
        logger.info(f"📋 Разделов: {len(sections)}")
        logger.info(f"📝 Всего тест-кейсов: {total_tests}")
        logger.info(f"📕 PDF файл: {pdf_path}")
        logger.info("="*50)
        
        return pdf_path