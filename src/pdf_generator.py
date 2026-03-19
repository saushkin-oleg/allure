from pathlib import Path
from typing import List, Dict
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import html
import logging
import json
import datetime

from src.utils import clean_html, format_timestamp, remove_bold_markers  # Добавляем импорт

logger = logging.getLogger(__name__)

class PDFGenerator:
    """Класс для генерации PDF отчетов"""
    
    def __init__(self, font_path: str = None):
        """
        Инициализация генератора PDF
        
        Args:
            font_path: путь к шрифту с поддержкой кириллицы (опционально)
        """
        self.font_name = 'Helvetica'
        self.font_bold = 'Helvetica-Bold'
        self._init_fonts(font_path)
        self._init_styles()
    
    def _init_fonts(self, font_path: str = None):
        """Инициализация шрифтов"""
        try:
            # Пробуем Arial (Windows)
            pdfmetrics.registerFont(TTFont('Arial', 'C:\\Windows\\Fonts\\arial.ttf'))
            pdfmetrics.registerFont(TTFont('Arial-Bold', 'C:\\Windows\\Fonts\\arialbd.ttf'))
            self.font_name = 'Arial'
            self.font_bold = 'Arial-Bold'
            logger.info("✅ Загружен шрифт Arial")
        except:
            if font_path:
                try:
                    pdfmetrics.registerFont(TTFont('Custom', font_path))
                    self.font_name = 'Custom'
                    self.font_bold = 'Custom'
                    logger.info(f"✅ Загружен шрифт из {font_path}")
                except:
                    logger.warning("⚠️ Используется Helvetica (без поддержки кириллицы)")
            else:
                logger.warning("⚠️ Используется Helvetica (без поддержки кириллицы)")
    
    def _init_styles(self):
        """Инициализация стилей для PDF"""
        self.styles = getSampleStyleSheet()
        
        self.title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Heading1'],
            fontName=self.font_bold,
            fontSize=18,
            spaceAfter=10,
            alignment=1
        )
        
        self.heading_style = ParagraphStyle(
            'HeadingStyle',
            parent=self.styles['Heading2'],
            fontName=self.font_bold,
            fontSize=14,
            spaceBefore=15,
            spaceAfter=5,
            textColor='#2c3e50'
        )
        
        self.subheading_style = ParagraphStyle(
            'SubheadingStyle',
            parent=self.styles['Heading3'],
            fontName=self.font_bold,
            fontSize=12,
            spaceBefore=10,
            spaceAfter=3,
            textColor='#34495e'
        )
        
        self.normal_style = ParagraphStyle(
            'CustomNormal',
            parent=self.styles['Normal'],
            fontName=self.font_name,
            fontSize=10,
            spaceAfter=3,
            leftIndent=5*mm
        )
        
        self.bold_style = ParagraphStyle(
            'CustomBold',
            parent=self.styles['Normal'],
            fontName=self.font_bold,
            fontSize=10,
            spaceAfter=3,
            leftIndent=5*mm
        )
        
        self.meta_style = ParagraphStyle(
            'MetaStyle',
            parent=self.styles['Normal'],
            fontName=self.font_name,
            fontSize=8,
            textColor='gray',
            leftIndent=5*mm,
            spaceAfter=1
        )
        
        self.date_style = ParagraphStyle(
            'DateStyle',
            parent=self.styles['Normal'],
            fontName=self.font_name,
            fontSize=10,
            textColor='gray',
            spaceAfter=20,
            alignment=1
        )

    def _format_step(self, step: Dict, level: int = 0, show_expected_header: bool = True) -> List[Paragraph]:
        """
        Форматирование шага с учетом вложенности и ожидаемых результатов
        
        Args:
            step: данные шага
            level: уровень вложенности (для отступов)
            show_expected_header: показывать ли заголовок "Ожидаемый результат"
        """
        result = []
        indent = "   " * level
        
        # Основной текст шага - очищаем от ** и HTML
        step_body = step.get('body', '')
        if step_body:
            step_body = clean_html(step_body)
            step_body = remove_bold_markers(step_body)  # Убираем **
            result.append(Paragraph(f"{indent}• {html.escape(step_body)}", self.normal_style))
        
        # Отображаем ожидаемые результаты
        expected_results = step.get('expected_results', [])
        if expected_results and show_expected_header:
            # Добавляем заголовок "Ожидаемый результат" с отступом
            result.append(Paragraph(f"{indent}   Ожидаемый результат:", self.bold_style))
        
        for expected in expected_results:
            expected_body = expected.get('body', '')
            if expected_body:
                expected_body = clean_html(expected_body)
                expected_body = remove_bold_markers(expected_body)  # Убираем **
                result.append(Paragraph(f"{indent}      - {html.escape(expected_body)}", self.normal_style))
                
                # Если у ожидаемого результата есть дочерние шаги
                for child in expected.get('children', []):
                    # Рекурсивно обрабатываем дочерние шаги с увеличенным отступом,
                    # но без повторного заголовка
                    for p in self._format_step(child, level + 3, False):
                        result.append(p)
        
        # Рекурсивно обрабатываем остальные дочерние шаги
        for child in step.get('children', []):
            result.extend(self._format_step(child, level + 1))
        
        return result

    def _prepare_text(self, text: str) -> str:
        """
        Подготовка текста для отображения в PDF:
        - очистка HTML
        - удаление маркдаун-разметки **
        - экранирование специальных символов
        
        Args:
            text: исходный текст
            
        Returns:
            подготовленный текст
        """
        if not text:
            return ""
        text = clean_html(text)
        text = remove_bold_markers(text)
        return html.escape(text)

    def generate_testcase_pdf(self, testcase_data: Dict, output_path: Path, 
                              include_raw_data: bool = False):
        """
        Генерация PDF для одного тест-кейса
        
        Args:
            testcase_data: данные тест-кейса
            output_path: путь для сохранения PDF
            include_raw_data: включать ли сырые данные в конце
        """
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=20*mm,
            leftMargin=20*mm,
            topMargin=20*mm,
            bottomMargin=20*mm
        )
        
        story = []
        
        # Заголовок
        story.append(Paragraph("Тест-кейс", self.title_style))
        story.append(Paragraph(f"ID: {testcase_data.get('id', 'Неизвестно')}", self.title_style))
        
        generated_at = testcase_data.get('generated_at')
        if generated_at:
            story.append(Paragraph(f"Сгенерировано: {format_timestamp(generated_at)}", self.date_style))
        else:
            story.append(Paragraph(f"Сгенерировано: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}", self.date_style))
        story.append(Spacer(1, 10*mm))
        
        # Название
        story.append(Paragraph("📌 Название", self.heading_style))
        story.append(Paragraph(self._prepare_text(testcase_data.get('name', 'Без имени')), self.normal_style))
        story.append(Spacer(1, 5*mm))
        
        # Мета-информация
        story.append(Paragraph("📊 Мета-информация", self.heading_style))
        
        created = format_timestamp(testcase_data.get('createdDate'))
        modified = format_timestamp(testcase_data.get('lastModifiedDate'))
        created_by = testcase_data.get('createdBy', 'Неизвестно')
        
        story.append(Paragraph(f"Создан: {created} ({created_by})", self.meta_style))
        story.append(Paragraph(f"Изменён: {modified}", self.meta_style))
        
        if testcase_data.get('automated') is not None:
            story.append(Paragraph(f"Автоматизирован: {'Да' if testcase_data['automated'] else 'Нет'}", self.meta_style))
        
        # Теги
        tags = testcase_data.get('tags', [])
        if tags:
            tag_names = [t.get('name', '') for t in tags if t.get('name')]
            if tag_names:
                story.append(Paragraph(f"Теги: {', '.join(tag_names)}", self.meta_style))
        
        # Ссылки
        links = testcase_data.get('links', [])
        if links:
            story.append(Paragraph("Ссылки:", self.meta_style))
            for link in links:
                url = link.get('url', '')
                if url:
                    story.append(Paragraph(f"  • {url}", self.meta_style))
        
        story.append(Spacer(1, 5*mm))
        
        # Описание
        desc = testcase_data.get('description', '') or testcase_data.get('descriptionHtml', '')
        if desc:
            story.append(Paragraph("📝 Описание", self.heading_style))
            prepared_desc = self._prepare_text(desc)
            if prepared_desc:
                story.append(Paragraph(prepared_desc, self.normal_style))
            else:
                story.append(Paragraph("<i>(описание пустое после очистки)</i>", self.meta_style))
        else:
            story.append(Paragraph("📝 Описание", self.heading_style))
            story.append(Paragraph("<i>(отсутствует)</i>", self.meta_style))
        story.append(Spacer(1, 5*mm))
        
        # Предусловия
        precondition = testcase_data.get('precondition', '') or testcase_data.get('preconditionHtml', '')
        if precondition:
            story.append(Paragraph("🔧 Предусловия", self.heading_style))
            prepared_precondition = self._prepare_text(precondition)
            if prepared_precondition:
                for line in prepared_precondition.split('\n'):
                    line = line.strip()
                    if line:
                        if line.startswith('*') or line.startswith('-') or line.startswith('•'):
                            story.append(Paragraph(f"• {line[1:].strip()}", self.normal_style))
                        else:
                            story.append(Paragraph(line, self.normal_style))
            else:
                story.append(Paragraph("<i>(предусловия пустые после очистки)</i>", self.meta_style))
        else:
            story.append(Paragraph("🔧 Предусловия", self.heading_style))
            story.append(Paragraph("<i>(отсутствуют)</i>", self.meta_style))
        story.append(Spacer(1, 5*mm))
        
        # Сценарий (шаги)
        steps = testcase_data.get('steps', [])
        if steps:
            story.append(Paragraph("📋 Сценарий", self.heading_style))
            
            # Используем метод _format_step для форматирования шагов
            for step in steps:
                story.extend(self._format_step(step))
        else:
            story.append(Paragraph("📋 Сценарий", self.heading_style))
            story.append(Paragraph("<i>(отсутствует)</i>", self.meta_style))
        story.append(Spacer(1, 5*mm))

        # Ожидаемый результат (общий) - если есть отдельное поле
        expected = testcase_data.get('expectedResult', '') or testcase_data.get('expectedResultHtml', '')
        if expected:
            story.append(Paragraph("✅ Ожидаемый результат (общий)", self.heading_style))
            prepared_expected = self._prepare_text(expected)
            if prepared_expected:
                story.append(Paragraph(prepared_expected, self.normal_style))
            else:
                story.append(Paragraph("<i>(ожидаемый результат пустой после очистки)</i>", self.meta_style))
        story.append(Spacer(1, 5*mm))
        
        # Комментарии
        comments = testcase_data.get('comments', {})
        if comments and isinstance(comments, dict) and 'content' in comments:
            comment_list = comments.get('content', [])
            if comment_list:
                story.append(Paragraph("💬 Комментарии", self.heading_style))
                for comment in comment_list[:10]:  # Показываем последние 10
                    text = comment.get('body', '')
                    author = comment.get('createdBy', 'Неизвестно')
                    date = format_timestamp(comment.get('createdDate'))
                    if text:
                        story.append(Paragraph(f"• {author} ({date}):", self.meta_style))
                        story.append(Paragraph(f"  {self._prepare_text(text)}", self.normal_style))
        
        # История изменений
        audit = testcase_data.get('audit', {})
        if audit and isinstance(audit, dict) and 'content' in audit:
            audit_list = audit.get('content', [])
            if audit_list:
                story.append(Paragraph("📜 История изменений", self.heading_style))
                for entry in audit_list[:10]:  # Показываем последние 10
                    user = entry.get('username', 'Система')
                    action = entry.get('actionType', '')
                    date = format_timestamp(entry.get('timestamp'))
                    if action:
                        story.append(Paragraph(f"• {date} - {user}: {action}", self.meta_style))
        
        # Вложения
        attachments = testcase_data.get('attachments', {})
        if attachments and isinstance(attachments, dict) and 'content' in attachments:
            attachment_list = attachments.get('content', [])
            if attachment_list:
                story.append(Paragraph("📎 Вложения", self.heading_style))
                for att in attachment_list[:10]:
                    name = att.get('name', '')
                    size = att.get('size', 0)
                    if name:
                        story.append(Paragraph(f"• {name} ({size} bytes)", self.meta_style))
        
        # Сырые данные (для отладки)
        if include_raw_data:
            story.append(PageBreak())
            story.append(Paragraph("🔧 Отладочная информация", self.heading_style))
            story.append(Paragraph("Сырые данные (сокращено):", self.meta_style))
            
            # Создаем копию без больших полей для читаемости
            debug_data = testcase_data.copy()
            if 'scenarioSteps' in debug_data:
                debug_data['scenarioSteps'] = f"<{len(debug_data['scenarioSteps']) if debug_data['scenarioSteps'] else 0} шагов>"
            if 'steps' in debug_data and len(debug_data['steps']) > 0:
                debug_data['steps'] = f"<{len(debug_data['steps'])} корневых шагов>"
            
            raw_data_str = json.dumps(debug_data, ensure_ascii=False, indent=2)[:5000]
            story.append(Paragraph(html.escape(raw_data_str), self.meta_style))
        
        doc.build(story)
        logger.info(f"✅ PDF создан: {output_path}")
    
    def generate_testplan_pdf(self, sections: List[Dict], testplan_id: int, 
                              output_path: Path, include_raw_data: bool = False):
        """
        Генерация PDF для всего тест-плана с группировкой по разделам
        
        Args:
            sections: список разделов с тест-кейсами
            testplan_id: ID тест-плана
            output_path: путь для сохранения PDF
            include_raw_data: включать ли сырые данные
        """
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=20*mm,
            leftMargin=20*mm,
            topMargin=20*mm,
            bottomMargin=20*mm
        )
        
        story = []
        
        # Заголовок
        story.append(Paragraph("Тест-план NT-PROXY", self.title_style))
        story.append(Paragraph(f"#{testplan_id}", self.title_style))
        story.append(Paragraph(f"Сгенерировано: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}", self.date_style))
        story.append(Spacer(1, 10*mm))
        
        # Статистика
        total_tests = sum(len(section['testCases']) for section in sections)
        story.append(Paragraph(f"📊 Всего тест-кейсов: {total_tests}", self.normal_style))
        story.append(Paragraph(f"📁 Разделов: {len(sections)}", self.normal_style))
        story.append(Spacer(1, 5*mm))
        
        # Генерация разделов
        test_counter = 1
        for section_idx, section in enumerate(sections, 1):
            story.append(Paragraph(f"{section_idx}. {section['name']}", self.heading_style))
            
            for tc in section['testCases']:
                tc_id = tc.get('id', '')
                tc_name = tc.get('name', 'Без имени')
                
                # Заголовок тест-кейса
                story.append(Paragraph(
                    f"{test_counter}. {self._prepare_text(tc_name)} [ID: {tc_id}]",
                    self.subheading_style
                ))
                
                # Мета-информация
                created = format_timestamp(tc.get('createdDate'))
                modified = format_timestamp(tc.get('lastModifiedDate'))
                created_by = tc.get('createdBy', 'Неизвестно')
                
                story.append(Paragraph(f"Создан: {created} ({created_by})", self.meta_style))
                story.append(Paragraph(f"Изменён: {modified}", self.meta_style))
                
                # Теги
                tags = tc.get('tags', [])
                if tags:
                    tag_names = [t.get('name', '') for t in tags if t.get('name')]
                    if tag_names:
                        story.append(Paragraph(f"Теги: {', '.join(tag_names)}", self.meta_style))
                
                story.append(Spacer(1, 2*mm))
                
                # Описание
                desc = tc.get('description', '') or tc.get('descriptionHtml', '')
                if desc:
                    prepared_desc = self._prepare_text(desc)
                    if prepared_desc:
                        story.append(Paragraph("<b>Описание:</b>", self.bold_style))
                        story.append(Paragraph(prepared_desc, self.normal_style))
                        story.append(Spacer(1, 2*mm))
                
                # Предусловия
                precondition = tc.get('precondition', '') or tc.get('preconditionHtml', '')
                if precondition:
                    prepared_precondition = self._prepare_text(precondition)
                    if prepared_precondition:
                        story.append(Paragraph("<b>Предусловия:</b>", self.bold_style))
                        for line in prepared_precondition.split('\n'):
                            line = line.strip()
                            if line:
                                if line.startswith('*') or line.startswith('-') or line.startswith('•'):
                                    story.append(Paragraph(f"• {line[1:].strip()}", self.normal_style))
                                else:
                                    story.append(Paragraph(line, self.normal_style))
                        story.append(Spacer(1, 2*mm))
                
                # Шаги
                steps = tc.get('steps', [])
                if steps:
                    story.append(Paragraph("<b>Сценарий:</b>", self.bold_style))
                    for step in steps:
                        story.extend(self._format_step(step))
                    story.append(Spacer(1, 2*mm))
                
                # Ожидаемый результат (общий)
                expected = tc.get('expectedResult', '') or tc.get('expectedResultHtml', '')
                if expected:
                    prepared_expected = self._prepare_text(expected)
                    if prepared_expected:
                        story.append(Paragraph("<b>Ожидаемый результат (общий):</b>", self.bold_style))
                        story.append(Paragraph(prepared_expected, self.normal_style))
                        story.append(Spacer(1, 2*mm))
                
                # Разделитель между тест-кейсами
                story.append(Spacer(1, 3*mm))
                story.append(Paragraph("-" * 80, self.meta_style))
                story.append(Spacer(1, 3*mm))
                
                test_counter += 1
            
            # Между разделами добавляем разрыв страницы
            if section_idx < len(sections):
                story.append(PageBreak())
        
        doc.build(story)
        logger.info(f"✅ PDF создан: {output_path}")