import requests
import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)

class AllureAPI:
    """Класс для работы с Allure TestOps API"""
    
    def __init__(self, base_url: str, api_token: str):
        """
        Инициализация API клиента
        
        Args:
            base_url: базовый URL Allure (например, https://allure-testops.office.it-bastion.com)
            api_token: API токен для аутентификации
        """
        self.base_url = base_url.rstrip('/')
        self.headers = {
            "Authorization": f"Api-Token {api_token}",
            "Content-Type": "application/json"
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def fetch(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Any]:
        """
        GET-запрос к API Allure
        
        Args:
            endpoint: эндпоинт API (например, "testcase/4448")
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
    
    def get_testplan(self, testplan_id: int) -> Optional[Dict]:
        """Получение информации о тест-плане"""
        return self.fetch(f"testplan/{testplan_id}")
    
    def get_testcase(self, testcase_id: int, project_id: int) -> Optional[Dict]:
        """Получение основной информации о тест-кейсе"""
        return self.fetch(f"testcase/{testcase_id}", params={'projectId': project_id})
    
    def get_testcase_steps(self, testcase_id: int, project_id: int) -> Optional[Dict]:
        """Получение шагов тест-кейса через эндпоинт /step"""
        return self.fetch(f"testcase/{testcase_id}/step", params={'projectId': project_id})
    
    def get_testcase_scenario(self, testcase_id: int, project_id: int) -> Optional[Dict]:
        """Получение сценария тест-кейса (альтернативный метод)"""
        return self.fetch(f"testcase/{testcase_id}/scenario", params={'projectId': project_id})
    
    def get_testcase_comments(self, testcase_id: int, project_id: int, size: int = 50) -> Optional[Dict]:
        """Получение комментариев к тест-кейсу"""
        return self.fetch("comment", params={
            'testCaseId': testcase_id,
            'projectId': project_id,
            'size': size
        })
    
    def get_testcase_audit(self, testcase_id: int, project_id: int, size: int = 50) -> Optional[Dict]:
        """Получение аудит-лога тест-кейса"""
        return self.fetch("testcase/audit", params={
            'testCaseId': testcase_id,
            'projectId': project_id,
            'size': size
        })
    
    def get_testcase_attachments(self, testcase_id: int, project_id: int, size: int = 50) -> Optional[Dict]:
        """Получение вложений тест-кейса"""
        return self.fetch("testcase/attachment", params={
            'testCaseId': testcase_id,
            'projectId': project_id,
            'size': size
        })
    
    def get_testcases_from_testplan(self, testplan_id: int, project_id: int, 
                                     page_size: int = 100, max_pages: int = 20) -> List[Dict]:
        """
        Получение всех тест-кейсов из тест-плана с пагинацией
        
        Args:
            testplan_id: ID тест-плана
            project_id: ID проекта
            page_size: размер страницы
            max_pages: максимальное количество страниц
            
        Returns:
            список тест-кейсов
        """
        all_testcases = []
        page = 0
        
        while page < max_pages:
            logger.info(f"📥 Загружаем страницу {page + 1} тест-кейсов...")
            
            params = {
                'testPlanIds': testplan_id,
                'projectId': project_id,
                'page': page,
                'size': page_size,
                'sort': 'name,asc'
            }
            
            response = self.fetch("testcase", params=params)
            
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
            
            all_testcases.extend(testcases_page)
            
            # Проверяем, есть ли еще страницы
            if isinstance(response, dict) and response.get('last', True):
                break
            
            page += 1
        
        logger.info(f"📊 Всего получено тест-кейсов из тест-плана: {len(all_testcases)}")
        return all_testcases
    
    def save_json(self, data: Any, filepath: Path):
        """Сохранение данных в JSON файл"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        logger.debug(f"💾 Сохранено: {filepath}")