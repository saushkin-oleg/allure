import requests
import json
import sys
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import html
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging
import time

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

class AllureExporter:
    """Класс для экспорта тест-кейсов из Allure TestOps"""
    
    def __init__(self, config_path: str = "config.json"):
        """
        Инициализация экспортера
        
        Args:
            config_path: путь к файлу конфигурации
        """
        self.config = self._load_config(config_path)
        self.headers = {
            "Authorization": f"Api-Token {self.config['api_token']}",
            "Content-Type": "application/json"
        }
        self.base_url = self.config['allure_url'].rstrip('/')
        self.output_dir = Path(self.config['output_dir'])
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """
        Загрузка конфигурации из JSON файла
        
        Args:
            config_path: путь к файлу конфигурации
            
        Returns:
            словарь с конфигурацией
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Проверка обязательных полей
            required_fields = ['api_token', 'allure_url', 'test_plan_id']
            missing = [field for field in required_fields if field not in config]
            
            if missing:
                raise ValueError(f"В конфигурации отсутствуют поля: {', '.join(missing)}")
            
            logger.info(f"✅ Конфигурация загружена из {config_path}")
            return config
            
        except FileNotFoundError:
            logger.error(f"❌ Файл конфигурации {config_path} не найден")
            self._create_config_template(config_path)
            sys.exit(1)
        except json.JSONDecodeError:
            logger.error(f"❌ Ошибка парсинга JSON в файле {config_path}")
            sys.exit(1)
    
    def _create_config_template(self, config_path: str):
        """Создание шаблона файла конфигурации"""
        template = {
            "api_token": "your_api_token_here",
            "allure_url": "https://allure-testops.office.it-bastion.com",
            "test_plan_id": "39",
            "output_dir": "./allure_export",
            "pdf_name": "testplan_39_full.pdf",
            "tree_id": 6  # Добавляем tree_id из URL
        }
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(template, f, indent=4, ensure_ascii=False)
        
        logger.info(f"📝 Создан шаблон конфигурации: {config_path}")
        logger.info("✏️ Заполните его реальными данными и запустите скрипт снова")
    
    def _fetch_data(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        GET-запрос к API Allure
        
        Args:
            endpoint: эндпоинт API
            params: параметры запроса
            
        Returns:
            данные ответа или None при ошибке
        """
        url = f"{self.base_url}/api/rs/{endpoint.lstrip('/')}"
        
        try:
            logger.debug(f"📡 Запрос: {url}")
            if params:
                logger.debug(f"📌 Параметры: {params}")
            
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.debug(f"❌ Ошибка {response.status_code}: {endpoint}")
                logger.debug(f"📄 Ответ: {response.text[:200]}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.debug(f"❌ Ошибка сети: {e}")
            return None
    
    def _save_json(self, data: Any, filepath: Path):
        """Сохранение данных в JSON файл"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        logger.debug(f"💾 Сохранено: {filepath}")
    
    def _clean_html(self, html_content: Optional[str]) -> str:
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
        return text.strip()
    
    def _format_datetime(self, timestamp: Optional[int]) -> str:
        """Форматирование timestamp в дату"""
        if not timestamp:
            return "Не указано"
        try:
            return datetime.fromtimestamp(timestamp / 1000).strftime('%d.%m.%Y %H:%M:%S')
        except:
            return str(timestamp)
    
    def _get_testcase_full_details(self, testcase_id: int, project_id: int) -> Optional[Dict]:
        """
        Получение полной информации о тест-кейсе
        """
        logger.info(f"    Загружаем тест-кейс {testcase_id}...")
        
        # Основная информация
        tc_detail = self._fetch_data(f"testcase/{testcase_id}", params={'projectId': project_id})
        if not tc_detail:
            return None
        
        # Получаем сценарий (шаги)
        steps = tc_detail.get('steps', [])
        scenario = None
        
        # Если шагов нет в основном ответе, пробуем получить через /scenario
        if not steps:
            scenario = self._fetch_data(f"testcase/{testcase_id}/scenario", params={'projectId': project_id})
            if scenario and isinstance(scenario, dict) and 'steps' in scenario:
                steps = scenario.get('steps', [])
        
        return {
            'id': tc_detail.get('id'),
            'name': tc_detail.get('name'),
            'description': tc_detail.get('description'),
            'descriptionHtml': tc_detail.get('descriptionHtml'),
            'precondition': tc_detail.get('precondition'),
            'preconditionHtml': tc_detail.get('preconditionHtml'),
            'expectedResult': tc_detail.get('expectedResult'),
            'expectedResultHtml': tc_detail.get('expectedResultHtml'),
            'steps': steps,
            'scenario': scenario,
            'tags': tc_detail.get('tags', []),
            'links': tc_detail.get('links', []),
            'createdDate': tc_detail.get('createdDate'),
            'lastModifiedDate': tc_detail.get('lastModifiedDate'),
            'createdBy': tc_detail.get('createdBy'),
            'lastModifiedBy': tc_detail.get('lastModifiedBy'),
            'status': tc_detail.get('status'),
            'workflow': tc_detail.get('workflow'),
            'automated': tc_detail.get('automated')
        }
    
    def _get_testcases_from_testplan_filtered(self, project_id: int, test_plan_id: int, tag_filter: str = "NTPR") -> List[Dict]:
        """
        Получение тест-кейсов из тест-плана с фильтрацией по тегу или префиксу названия
        """
        all_testcases = []
        page = 0
        page_size = 100
        
        while True:
            logger.info(f"📥 Загружаем страницу {page + 1} тест-кейсов...")
            
            params = {
                'testPlanIds': test_plan_id,
                'projectId': project_id,
                'page': page,
                'size': page_size,
                'sort': 'name,asc'
            }
            
            response = self._fetch_data("testcase", params=params)
            
            if not response:
                break
            
            if isinstance(response, dict) and 'content' in response:
                testcases_page = response.get('content', [])
                total_elements = response.get('totalElements', 0)
                logger.info(f"   Страница {page + 1}: {len(testcases_page)} тестов (всего в плане: {total_elements})")
            elif isinstance(response, list):
                testcases_page = response
                logger.info(f"   Страница {page + 1}: {len(testcases_page)} тестов")
            else:
                break
            
            if not testcases_page:
                break
            
            # Фильтруем по префиксу [NTPR в названии
            filtered_page = []
            for tc in testcases_page:
                name = tc.get('name', '')
                if name and name.startswith(f'[{tag_filter}'):
                    filtered_page.append(tc)
            
            all_testcases.extend(filtered_page)
            
            # Проверяем, есть ли еще страницы
            if isinstance(response, dict) and response.get('last', True):
                break
            
            page += 1
            # Безопасность: не больше 20 страниц
            if page > 20:
                break
        
        logger.info(f"📊 Всего получено тест-кейсов с префиксом [{tag_filter}: {len(all_testcases)}")
        return all_testcases
    
    def _get_testcases_by_aql(self, project_id: int, aql: str) -> List[Dict]:
        """
        Получение тест-кейсов через AQL запрос
        """
        logger.info(f"📥 Выполняем AQL запрос: {aql}")
        
        params = {
            'projectId': project_id,
            'rql': aql,
            'page': 0,
            'size': 1000
        }
        
        response = self._fetch_data("testcase/_search", params=params)
        
        if not response:
            return []
        
        if isinstance(response, dict) and 'content' in response:
            testcases = response.get('content', [])
        elif isinstance(response, list):
            testcases = response
        else:
            return []
        
        logger.info(f"📊 Получено тест-кейсов по AQL: {len(testcases)}")
        return testcases
    
    def _get_testcases_by_tag(self, project_id: int, tag_name: str) -> List[Dict]:
        """
        Получение тест-кейсов по тегу
        """
        logger.info(f"📥 Получаем тест-кейсы с тегом: {tag_name}")
        
        # Используем AQL для поиска по тегу
        aql = f'tag = "{tag_name}"'
        return self._get_testcases_by_aql(project_id, aql)
    
    def _get_testcases_from_tree(self, project_id: int, tree_id: int) -> List[Dict]:
        """
        Получение тест-кейсов из указанного дерева
        """
        logger.info(f"📥 Получаем тест-кейсы из дерева {tree_id}...")
        
        # Получаем структуру дерева
        tree_params = {
            'projectId': project_id,
            'treeId': tree_id,
            'size': 1000
        }
        
        response = self._fetch_data("testcasetree/entity", params=tree_params)
        
        if not response or 'content' not in response:
            return []
        
        # Рекурсивно собираем все тест-кейсы
        testcases = []
        for item in response.get('content', []):
            if item.get('type') == 'LEAF':
                testcases.append({'id': item.get('testCaseId')})
        
        logger.info(f"📊 Получено тест-кейсов из дерева: {len(testcases)}")
        return testcases
    
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
    
    def _generate_pdf_reportlab(self, sections: List[Dict], output_path: Path):
        """Генерация PDF с использованием ReportLab"""
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        import html
        
        # Регистрируем шрифт с поддержкой кириллицы
        try:
            pdfmetrics.registerFont(TTFont('Arial', 'C:\\Windows\\Fonts\\arial.ttf'))
            pdfmetrics.registerFont(TTFont('Arial-Bold', 'C:\\Windows\\Fonts\\arialbd.ttf'))
            font_name = 'Arial'
            font_bold = 'Arial-Bold'
            logger.info("✅ Загружен шрифт Arial")
        except:
            font_name = 'Helvetica'
            font_bold = 'Helvetica-Bold'
            logger.warning("⚠️ Используется Helvetica (без поддержки кириллицы)")
        
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=20*mm,
            leftMargin=20*mm,
            topMargin=20*mm,
            bottomMargin=20*mm
        )
        
        styles = getSampleStyleSheet()
        story = []
        
        # Создаем стили
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontName=font_bold,
            fontSize=18,
            spaceAfter=10,
            alignment=1
        )
        
        section_style = ParagraphStyle(
            'SectionStyle',
            parent=styles['Heading2'],
            fontName=font_bold,
            fontSize=14,
            spaceBefore=15,
            spaceAfter=10,
            textColor='#2c3e50'
        )
        
        testcase_style = ParagraphStyle(
            'TestCaseStyle',
            parent=styles['Heading3'],
            fontName=font_bold,
            fontSize=12,
            spaceBefore=10,
            spaceAfter=5,
            leftIndent=5*mm
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontName=font_name,
            fontSize=10,
            spaceAfter=3,
            leftIndent=10*mm
        )
        
        bold_style = ParagraphStyle(
            'CustomBold',
            parent=styles['Normal'],
            fontName=font_bold,
            fontSize=10,
            spaceAfter=3,
            leftIndent=10*mm
        )
        
        meta_style = ParagraphStyle(
            'MetaStyle',
            parent=styles['Normal'],
            fontName=font_name,
            fontSize=8,
            textColor='gray',
            leftIndent=10*mm,
            spaceAfter=1
        )
        
        date_style = ParagraphStyle(
            'DateStyle',
            parent=styles['Normal'],
            fontName=font_name,
            fontSize=10,
            textColor='gray',
            spaceAfter=20,
            alignment=1
        )
        
        # Заголовок
        story.append(Paragraph("Тест-план NT-PROXY", title_style))
        story.append(Paragraph(f"#{self.config['test_plan_id']}", title_style))
        story.append(Paragraph(f"Сгенерировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}", date_style))
        story.append(Spacer(1, 10*mm))
        
        # Статистика
        total_tests = sum(len(section['testCases']) for section in sections)
        story.append(Paragraph(f"📊 Всего тест-кейсов: {total_tests}", normal_style))
        story.append(Paragraph(f"📁 Разделов: {len(sections)}", normal_style))
        story.append(Spacer(1, 5*mm))
        
        # Генерация разделов
        test_counter = 1
        for section_idx, section in enumerate(sections, 1):
            story.append(Paragraph(f"{section_idx}. {section['name']}", section_style))
            
            for tc in section['testCases']:
                tc_id = tc.get('id', '')
                tc_name = tc.get('name', 'Без имени')
                
                # Заголовок тест-кейса
                story.append(Paragraph(
                    f"{test_counter}. {html.escape(tc_name)} [ID: {tc_id}]",
                    testcase_style
                ))
                
                # Мета-информация
                created = self._format_datetime(tc.get('createdDate'))
                modified = self._format_datetime(tc.get('lastModifiedDate'))
                created_by = tc.get('createdBy', 'Неизвестно')
                
                story.append(Paragraph(f"Создан: {created} ({created_by})", meta_style))
                story.append(Paragraph(f"Изменён: {modified}", meta_style))
                
                # Теги
                tags = tc.get('tags', [])
                if tags:
                    tag_names = [t.get('name', '') for t in tags if t.get('name')]
                    if tag_names:
                        story.append(Paragraph(f"Теги: {', '.join(tag_names)}", meta_style))
                
                story.append(Spacer(1, 2*mm))
                
                # Описание
                desc = tc.get('description', '')
                if desc:
                    desc = self._clean_html(desc)
                    if desc:
                        story.append(Paragraph("<b>Описание:</b>", bold_style))
                        story.append(Paragraph(html.escape(desc), normal_style))
                        story.append(Spacer(1, 2*mm))
                
                # Предусловия
                precondition = tc.get('precondition', '')
                if precondition:
                    precondition = self._clean_html(precondition)
                    if precondition:
                        story.append(Paragraph("<b>Предусловия:</b>", bold_style))
                        for line in precondition.split('\n'):
                            line = line.strip()
                            if line:
                                if line.startswith('*') or line.startswith('-') or line.startswith('•'):
                                    story.append(Paragraph(f"• {html.escape(line[1:].strip())}", normal_style))
                                else:
                                    story.append(Paragraph(html.escape(line), normal_style))
                        story.append(Spacer(1, 2*mm))
                
                # Сценарий (шаги)
                steps = tc.get('steps', [])
                if steps:
                    story.append(Paragraph("<b>Сценарий:</b>", bold_style))
                    for step_num, step in enumerate(steps, 1):
                        step_name = step.get('name', '')
                        if step_name:
                            step_name = self._clean_html(step_name)
                            story.append(Paragraph(f"{step_num}. {html.escape(step_name)}", normal_style))
                    story.append(Spacer(1, 2*mm))
                
                # Ожидаемый результат
                expected = tc.get('expectedResult', '')
                if expected:
                    expected = self._clean_html(expected)
                    if expected:
                        story.append(Paragraph("<b>Ожидаемый результат:</b>", bold_style))
                        story.append(Paragraph(html.escape(expected), normal_style))
                        story.append(Spacer(1, 2*mm))
                
                story.append(Spacer(1, 5*mm))
                test_counter += 1
            
            if section_idx < len(sections):
                story.append(PageBreak())
        
        doc.build(story)
        logger.info(f"✅ PDF создан: {output_path}")
    
    def run(self):
        """Основной метод экспорта"""
        test_plan_id = self.config['test_plan_id']
        logger.info(f"🚀 Начинаем выгрузку тест-плана {test_plan_id}...")
        
        # 1. Получение информации о тест-плане
        logger.info("📥 Получаем информацию о тест-плане...")
        testplan = self._fetch_data(f"testplan/{test_plan_id}")
        
        if not testplan:
            logger.error("❌ Не удалось получить тест-план")
            return
        
        self._save_json(testplan, self.output_dir / "testplan_info.json")
        
        # 2. Получение projectId
        project_id = testplan.get('projectId')
        if not project_id:
            logger.error("❌ Не удалось определить projectId")
            return
        
        logger.info(f"📌 Project ID: {project_id}")
        
        # 3. Получаем тест-кейсы разными способами и выбираем лучший результат
        testcases = []
        
        # Способ 1: Фильтрация по префиксу [NTPR
        logger.info("📥 Способ 1: Фильтрация по префиксу [NTPR...")
        testcases = self._get_testcases_from_testplan_filtered(project_id, int(test_plan_id), "NTPR")
        
        # Способ 2: Если мало, пробуем по тегу nt-proxy
        if len(testcases) < 50:
            logger.info("📥 Способ 2: Поиск по тегу nt-proxy...")
            tag_testcases = self._get_testcases_by_tag(project_id, "nt-proxy")
            if tag_testcases:
                # Пересекаем с тест-планом
                testplan_ids = set()
                for tc in testcases:
                    testplan_ids.add(tc.get('id'))
                
                for tc in tag_testcases:
                    if tc.get('id') not in testplan_ids:
                        testcases.append(tc)
        
        # Способ 3: Если всё ещё мало, используем treeId из конфига
        if len(testcases) < 50 and 'tree_id' in self.config:
            logger.info(f"📥 Способ 3: Получение из дерева {self.config['tree_id']}...")
            tree_testcases = self._get_testcases_from_tree(project_id, self.config['tree_id'])
            if tree_testcases:
                testcases = tree_testcases
        
        if not testcases:
            logger.error("❌ Не удалось получить тест-кейсы")
            return
        
        logger.info(f"✅ Найдено тест-кейсов: {len(testcases)}")
        
        # 4. Загружаем детальную информацию для каждого тест-кейса
        logger.info("📥 Загружаем детальную информацию...")
        detailed_testcases = []
        for i, tc in enumerate(testcases, 1):
            tc_id = tc.get('id')
            if not tc_id:
                continue
            
            logger.info(f"  ⏳ [{i}/{len(testcases)}] Загружаем тест-кейс {tc_id}...")
            tc_detail = self._get_testcase_full_details(tc_id, project_id)
            if tc_detail:
                detailed_testcases.append(tc_detail)
            
            # Небольшая задержка, чтобы не нагружать API
            time.sleep(0.1)
        
        logger.info(f"✅ Загружено деталей: {len(detailed_testcases)} из {len(testcases)}")
        
        # 5. Группируем по разделам
        logger.info("📊 Группируем по разделам...")
        sections = self._group_by_section(detailed_testcases)
        
        # 6. Сохраняем структуру
        self._save_json(sections, self.output_dir / "testplan_tree.json")
        
        # 7. Генерация PDF
        pdf_name = self.config.get('pdf_name', f"testplan_{test_plan_id}_full.pdf")
        pdf_path = self.output_dir / pdf_name
        self._generate_pdf_reportlab(sections, pdf_path)
        
        # 8. Итоговая статистика
        total_tests = sum(len(section['testCases']) for section in sections)
        logger.info("\n" + "="*50)
        logger.info("🎉 ЭКСПОРТ ЗАВЕРШЕН УСПЕШНО")
        logger.info("="*50)
        logger.info(f"📁 Директория: {self.output_dir.absolute()}")
        logger.info(f"📊 Тест-план #{test_plan_id} (projectId: {project_id})")
        logger.info(f"📋 Разделов: {len(sections)}")
        logger.info(f"📝 Всего тест-кейсов: {total_tests}")
        logger.info(f"📕 PDF файл: {pdf_path}")
        logger.info("="*50)

def main():
    """Точка входа"""
    exporter = AllureExporter("config.json")
    exporter.run()

if __name__ == "__main__":
    main()