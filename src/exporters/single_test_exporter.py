import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from src.allure_api import AllureAPI
from src.pdf_generator import PDFGenerator
from src.utils.step_parser import parse_steps

logger = logging.getLogger(__name__)

class SingleTestExporter:
    """Экспортер для одного тест-кейса (отладка)"""
    
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
    
    def export(self, testcase_id: int, project_id: int = 3, 
               save_raw: bool = True, include_raw_in_pdf: bool = True) -> Optional[Path]:
        """
        Экспорт одного тест-кейса
        
        Args:
            testcase_id: ID тест-кейса
            project_id: ID проекта
            save_raw: сохранять ли сырой JSON
            include_raw_in_pdf: включать ли сырые данные в PDF
            
        Returns:
            путь к созданному PDF или None при ошибке
        """
        logger.info(f"🚀 Начинаем отладочный экспорт тест-кейса {testcase_id}...")
        
        # 1. Получаем основную информацию
        logger.info("📥 Шаг 1/4: Загружаем основную информацию...")
        tc_detail = self.api.get_testcase(testcase_id, project_id)
        if not tc_detail:
            logger.error("❌ Не удалось получить основную информацию")
            return None
        
        # 2. Получаем шаги
        logger.info("📥 Шаг 2/4: Загружаем шаги...")
        step_data = self.api.get_testcase_steps(testcase_id, project_id)
        steps = parse_steps(step_data) if step_data else []
        logger.info(f"      Найдено корневых шагов: {len(steps)}")
        
        # 3. Получаем комментарии, аудит, вложения
        logger.info("📥 Шаг 3/4: Загружаем дополнительные данные...")
        comments = self.api.get_testcase_comments(testcase_id, project_id)
        audit = self.api.get_testcase_audit(testcase_id, project_id)
        attachments = self.api.get_testcase_attachments(testcase_id, project_id)
        
        # 4. Собираем все данные
        logger.info("📥 Шаг 4/4: Собираем данные...")
        testcase_data = {
            **tc_detail,
            'steps': steps,
            'step_data': step_data,  # сохраняем для отладки
            'comments': comments if comments else [],
            'audit': audit if audit else [],
            'attachments': attachments if attachments else [],
            'generated_at': int(datetime.now().timestamp() * 1000)
        }
        
        # Логируем статистику
        logger.info("📊 Статистика:")
        logger.info(f"   - ID: {testcase_data.get('id')}")
        logger.info(f"   - Название: {'✅' if testcase_data.get('name') else '❌'}")
        logger.info(f"   - Описание: {'✅' if testcase_data.get('description') or testcase_data.get('descriptionHtml') else '❌'}")
        logger.info(f"   - Предусловия: {'✅' if testcase_data.get('precondition') or testcase_data.get('preconditionHtml') else '❌'}")
        logger.info(f"   - Ожидаемый результат: {'✅' if testcase_data.get('expectedResult') or testcase_data.get('expectedResultHtml') else '❌'}")
        logger.info(f"   - Шаги: {len(steps)} корневых")
        logger.info(f"   - Теги: {len(testcase_data.get('tags', []))} шт.")
        logger.info(f"   - Ссылки: {len(testcase_data.get('links', []))} шт.")
        logger.info(f"   - Комментарии: {'✅' if comments else '❌'}")
        logger.info(f"   - Аудит: {'✅' if audit else '❌'}")
        logger.info(f"   - Вложения: {'✅' if attachments else '❌'}")
        
        # Сохраняем сырые данные
        if save_raw:
            json_path = self.output_dir / f"testcase_{testcase_id}_raw.json"
            self.api.save_json(testcase_data, json_path)
            logger.info(f"💾 JSON сохранён: {json_path}")
        
        # Генерируем PDF
        pdf_path = self.output_dir / f"testcase_{testcase_id}_debug.pdf"
        self.pdf_generator.generate_testcase_pdf(
            testcase_data, 
            pdf_path, 
            include_raw_data=include_raw_in_pdf
        )
        
        logger.info(f"✅ Экспорт завершён: {pdf_path}")
        return pdf_path