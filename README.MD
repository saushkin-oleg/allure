# Allure TestOps Exporter

Утилита для экспорта тест-планов и тест-кейсов из **Allure TestOps** в формат PDF.  
Поддерживает кириллицу, корректно отображает иерархию шагов, предусловия, теги, вложения и метаданные — ровно так, как они выглядят на странице тест-кейса в веб-интерфейсе Allure TestOps.

---

## Возможности

- 📋 Экспорт полного тест-плана в один PDF — с группировкой кейсов по разделам
- 🔍 Экспорт отдельного тест-кейса в PDF (режим отладки)
- 📊 Полные данные каждого кейса: название, статус, тип, теги, пользовательские поля, параметры, ссылки, описание, предусловия, шаги с ожидаемыми результатами, вложения
- 🔗 Ссылка на страницу кейса в Allure TestOps прямо в PDF
- 🌐 Поддержка кириллицы (Arial на Windows, DejaVu на Linux)
- 🔧 Сохранение промежуточных JSON-данных для диагностики

---

## Структура проекта

```
allure/
├── main.py                  # Точка входа, CLI-интерфейс
├── config_example.json      # Пример конфигурации (скопируйте в config.json)
├── requirements.txt         # Зависимости Python
├── src/
│   ├── allure_api.py        # Работа с Allure TestOps REST API
│   ├── pdf_generator.py     # Генерация PDF (стили, шрифты, рендер)
│   ├── utils.py             # Вспомогательные функции (очистка HTML/Markdown,
│   │                        # парсинг шагов, форматирование дат)
│   └── exporters/
│       ├── testplan_exporter.py      # Экспорт тест-плана
│       └── single_test_exporter.py  # Экспорт одного тест-кейса
```

---

## Установка

**1. Клонируйте репозиторий:**

```bash
git clone https://github.com/saushkin-oleg/allure.git
cd allure
```

**2. Установите зависимости:**

```bash
pip install -r requirements.txt
```

**3. Создайте файл конфигурации:**

Скопируйте пример и заполните своими данными:

```bash
cp config_example.json config.json
```

Содержимое `config.json`:

```json
{
    "api_token": "ваш-api-токен",
    "allure_url": "https://allure-testops.example.com",
    "output_dir": "./exports",
    "testplan_id": 1,
    "testcase_id": 2,
    "project_id": 3,
    "filter_prefix": "EXAMPLE"
}
```

### Описание полей конфигурации

| Поле | Обязательное | Описание |
|---|---|---|
| `api_token` | ✅ | API-токен Allure TestOps (`Profile → API tokens`) |
| `allure_url` | ✅ | Базовый URL вашего Allure TestOps (без слеша в конце) |
| `output_dir` | — | Директория для сохранения PDF (по умолчанию `./exports`) |
| `testplan_id` | — | ID тест-плана для экспорта |
| `testcase_id` | — | ID тест-кейса для отладочного экспорта |
| `project_id` | — | ID проекта в Allure TestOps |
| `filter_prefix` | — | Префикс для группировки кейсов по разделам |

---

## Использование

### Основной скрипт (`main.py`)

```bash
# Экспорт тест-плана
python main.py --mode testplan

# Экспорт одного тест-кейса
python main.py --mode single

# Оба режима одновременно (по умолчанию)
python main.py --mode both

# Указать другой конфиг
python main.py --config my_config.json

# Переопределить ID из командной строки
python main.py --mode testplan --testplan-id 42
python main.py --mode single --testcase-id 123 --project-id 5

# Указать директорию вывода
python main.py --output-dir ./my_exports

# Не сохранять промежуточные JSON
python main.py --no-raw
```

### Параметры командной строки

| Параметр | Короткий | По умолчанию | Описание |
|---|---|---|---|
| `--config` | `-c` | `config.json` | Путь к файлу конфигурации |
| `--mode` | `-m` | `both` | Режим: `testplan`, `single`, `both` |
| `--testplan-id` | — | из конфига | ID тест-плана |
| `--testcase-id` | — | из конфига | ID тест-кейса |
| `--project-id` | — | из конфига | ID проекта |
| `--output-dir` | — | из конфига | Директория для сохранения PDF |
| `--no-raw` | — | `false` | Не сохранять промежуточные JSON-файлы |

---

## Результаты

После успешного запуска в `output_dir` появятся:

```
exports/
├── testplan/
│   ├── testplan_39_full.pdf     # Итоговый PDF тест-плана
│   └── testplan_tree.json       # Промежуточные данные (если не --no-raw)
└── debug/
    ├── testcase_4448_debug.pdf  # PDF одного тест-кейса
    └── testcase_4448_raw.json   # Сырые данные из API
```

### Что содержит PDF тест-плана

- Заголовок, номер тест-плана, дата генерации, общее число кейсов
- Кейсы, сгруппированные по разделам (по первому тегу или `[префиксу]` в названии)
- Для каждого кейса:
  - Название, ID, ссылка на страницу в Allure TestOps
  - Статус, тип (ручной/автоматизированный), автор, даты создания и изменения
  - Теги, пользовательские поля, параметры
  - Внешние ссылки
  - Описание и предусловия
  - Шаги с ожидаемыми результатами (поддержка вложенных шагов)
  - Список вложений со ссылками на скачивание

---

## Поддержка кириллицы

Скрипт автоматически подбирает шрифт в следующем порядке:

1. **Arial** — `C:\Windows\Fonts\arial.ttf` (Windows)
2. **DejaVu Sans** — `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf` (Linux)
3. **Helvetica** — встроенный в ReportLab (без кириллицы, fallback)

Для корректного отображения кириллицы на Linux установите DejaVu:

```bash
# Ubuntu/Debian
sudo apt-get install fonts-dejavu

# Или поместите файлы шрифта в папку fonts/ рядом со скриптом:
mkdir fonts
cp /path/to/DejaVuSans.ttf fonts/
cp /path/to/DejaVuSans-Bold.ttf fonts/
```

---

## Устранение неполадок

**Кейсов меньше, чем ожидается**  
Убедитесь, что `testplan_id` в конфиге соответствует нужному плану. Скрипт читает `treeSelection` плана (группы и отдельные листовые кейсы) и учитывает исключения.

**Ошибка авторизации (HTTP 401/403)**  
Проверьте значение `api_token` в `config.json`. Токен создаётся в Allure TestOps: `Profile → API tokens → Generate`.

**Недоступен Allure TestOps (connection error)**  
Убедитесь, что `allure_url` доступен из вашей сети и не содержит лишнего слеша в конце.

**Квадратики вместо кириллицы в PDF**  
Установите шрифт DejaVu (Linux) или убедитесь, что Arial доступен (Windows). См. раздел «Поддержка кириллицы».

---

## Зависимости

```
requests
reportlab
```

Устанавливаются командой:

```bash
pip install -r requirements.txt
```

---

## Лицензия

MIT
