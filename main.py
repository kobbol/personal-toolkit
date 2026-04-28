import html
import json
import math
import os
import sys
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


# Имя файла для хранения расходов в формате JSON.
DATA_FILE = "expenses.json"
# Имя файла для хранения лимитов категорий (дефолтных и помесячных).
LIMITS_FILE = "limits.json"
# Имя файла для хранения списка категорий.
CATEGORIES_FILE = "categories.json"
# Имя файла для хранения соответствия "позиция -> категория".
ITEM_CATEGORY_FILE = "item_categories.json"
# Имя HTML-файла с визуальным отчётом.
REPORT_FILE = "expense_report.html"
# Имя HTML-файла для веб-интерфейса.
WEB_UI_FILE = "web_ui.html"

# Базовые категории, которые создаются по умолчанию.
DEFAULT_CATEGORIES = [
    "Еда",
    "Транспорт",
    "Жилье",
    "Здоровье",
    "Развлечения",
    "Покупки",
    "Образование",
    "Прочее",
]


def load_expenses():
    """
    Загружает список расходов из файла.
    Если файл отсутствует или пустой, создаёт его и возвращает пустой список.
    """
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, list):
                return data
            return []
    except FileNotFoundError:
        # Если файла нет, создаём его с пустым списком расходов.
        save_expenses([])
        return []
    except json.JSONDecodeError:
        # Если JSON повреждён, безопасно начинаем с пустого списка.
        return []


def save_expenses(expenses):
    """Сохраняет список расходов в JSON-файл."""
    with open(DATA_FILE, "w", encoding="utf-8") as file:
        json.dump(expenses, file, ensure_ascii=False, indent=2)


def normalize_item_name(item_name):
    """Нормализует наименование товара/услуги для хранения и поиска."""
    return " ".join(item_name.strip().lower().split())


def load_item_categories():
    """
    Загружает словарь соответствий "позиция -> категория".
    Пример: {"такси": "Транспорт", "капучино": "Еда"}
    """
    try:
        with open(ITEM_CATEGORY_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, dict):
                return data
            return {}
    except FileNotFoundError:
        save_item_categories({})
        return {}
    except json.JSONDecodeError:
        return {}


def save_item_categories(mapping):
    """Сохраняет словарь соответствий 'позиция -> категория'."""
    with open(ITEM_CATEGORY_FILE, "w", encoding="utf-8") as file:
        json.dump(mapping, file, ensure_ascii=False, indent=2)


def normalize_category(category):
    """Нормализует название категории для исключения дублей."""
    text = category.strip()
    if not text:
        return ""
    # Делаем формат единообразным: "еДа" -> "Еда".
    return text[:1].upper() + text[1:].lower()


def get_default_limits_map():
    """Создаёт словарь дефолтных лимитов (0 означает 'лимит не задан')."""
    result = {}
    categories = load_categories()
    for category in categories:
        result[category] = 0.0
    return result


def load_limits():
    """
    Загружает структуру лимитов из файла.
    Формат:
    {
      "default": {"Еда": 15000, "Транспорт": 5000},
      "monthly": {"2026-04": {"Еда": 14000, "Транспорт": 4500}}
    }
    """
    try:
        with open(LIMITS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            if not isinstance(data, dict):
                data = {}

            if "default" not in data or not isinstance(data["default"], dict):
                data["default"] = get_default_limits_map()
            if "monthly" not in data or not isinstance(data["monthly"], dict):
                data["monthly"] = {}

            return data
    except FileNotFoundError:
        limits_data = {"default": get_default_limits_map(), "monthly": {}}
        save_limits(limits_data)
        return limits_data
    except json.JSONDecodeError:
        limits_data = {"default": get_default_limits_map(), "monthly": {}}
        return limits_data


def save_limits(limits):
    """Сохраняет лимиты категорий в JSON-файл."""
    with open(LIMITS_FILE, "w", encoding="utf-8") as file:
        json.dump(limits, file, ensure_ascii=False, indent=2)


def load_categories():
    """
    Загружает список категорий.
    Если файла нет, создаёт его с базовыми категориями.
    """
    try:
        with open(CATEGORIES_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            if not isinstance(data, list):
                data = []
    except FileNotFoundError:
        data = DEFAULT_CATEGORIES[:]
        save_categories(data)
        return data
    except json.JSONDecodeError:
        data = DEFAULT_CATEGORIES[:]
        save_categories(data)
        return data

    cleaned = []
    for item in data:
        if isinstance(item, str):
            normalized = normalize_category(item)
            if normalized and normalized not in cleaned:
                cleaned.append(normalized)

    if not cleaned:
        cleaned = DEFAULT_CATEGORIES[:]

    save_categories(cleaned)
    return cleaned


def save_categories(categories):
    """Сохраняет категории в JSON-файл."""
    with open(CATEGORIES_FILE, "w", encoding="utf-8") as file:
        json.dump(categories, file, ensure_ascii=False, indent=2)


def add_category_to_system(category):
    """Добавляет новую категорию в общий список и лимиты (если её там не было)."""
    normalized = normalize_category(category)
    if not normalized:
        return False

    categories = load_categories()
    if normalized not in categories:
        categories.append(normalized)
        save_categories(categories)

    limits_data = load_limits()
    if normalized not in limits_data["default"]:
        limits_data["default"][normalized] = 0.0
        save_limits(limits_data)

    return True


def build_state_payload():
    """Собирает состояние приложения для веб-интерфейса."""
    expenses = load_expenses()
    categories = load_categories()
    item_categories = load_item_categories()
    limits_data = load_limits()
    month_key = get_current_month_key()
    month_limits = get_month_limits(month_key)
    month_expenses = []
    for index, expense in enumerate(expenses):
        date_text = expense.get("date", "")
        parsed = parse_date(date_text)
        if parsed is None:
            continue
        if parsed.year == int(month_key[:4]) and parsed.month == int(month_key[5:7]):
            month_expenses.append((index, expense))
    month_expenses = sorted(month_expenses, key=lambda item: item[1].get("date", ""), reverse=True)
    month_expense_values = [expense for _, expense in month_expenses]
    category_totals = calculate_category_totals(month_expense_values)
    daily_totals = calculate_daily_totals(month_expense_values)

    month_total = 0.0
    for amount in category_totals.values():
        month_total += amount

    month_expenses_payload = []
    for index, expense in month_expenses:
        month_expenses_payload.append(
            {
                "id": index,
                "item": expense.get("item", "Без названия"),
                "amount": float(expense.get("amount", 0)),
                "category": expense.get("category", "Без категории"),
                "date": expense.get("date", ""),
                "comment": expense.get("comment", ""),
            }
        )

    known_items_map = {}
    for expense in expenses:
        item_name = str(expense.get("item", "")).strip()
        if not item_name:
            continue
        normalized_item = normalize_item_name(item_name)
        if normalized_item not in known_items_map:
            known_items_map[normalized_item] = {
                "item": item_name,
                "category": expense.get("category", "Без категории"),
                "lastAmount": float(expense.get("amount", 0)),
            }

    for normalized_item, category in item_categories.items():
        if normalized_item not in known_items_map:
            known_items_map[normalized_item] = {
                "item": normalized_item,
                "category": category,
                "lastAmount": 0.0,
            }

    known_items = sorted(
        known_items_map.values(),
        key=lambda item: item["item"].lower(),
    )

    sorted_categories = sorted(category_totals.items(), key=lambda item: item[1], reverse=True)
    category_rows = []
    for category, amount in sorted_categories:
        percent = (amount / month_total) * 100 if month_total else 0
        category_rows.append(
            {
                "category": category,
                "amount": amount,
                "percent": round(percent, 1),
                "limit": float(month_limits.get(category, 0)),
            }
        )

    return {
        "currentMonth": month_key,
        "summary": {
            "monthTotal": month_total,
            "entriesCount": len(month_expense_values),
            "categoriesCount": len(category_totals),
        },
        "categories": categories,
        "knownItems": known_items,
        "limits": {
            "default": limits_data["default"],
            "monthly": month_limits,
        },
        "monthExpenses": month_expenses_payload,
        "categoryRows": category_rows,
        "charts": {
            "pieSvg": build_pie_chart_svg(category_totals),
            "lineSvg": build_line_chart_svg(daily_totals),
        },
    }


def add_expense_record(item_name, amount, category, date_value, comment=""):
    """Добавляет расход без интерактивного ввода."""
    item_name = item_name.strip()
    if not item_name:
        raise ValueError("Наименование не может быть пустым.")

    try:
        amount_value = float(str(amount).replace(",", "."))
    except ValueError as error:
        raise ValueError("Сумма должна быть числом.") from error

    if amount_value <= 0:
        raise ValueError("Сумма должна быть больше нуля.")

    normalized_category = normalize_category(category)
    if not normalized_category:
        raise ValueError("Категория не может быть пустой.")

    parsed_date = parse_date(date_value)
    if parsed_date is None:
        raise ValueError("Дата должна быть в формате YYYY-MM-DD.")

    add_category_to_system(normalized_category)

    expenses = load_expenses()
    item_categories = load_item_categories()
    normalized_item = normalize_item_name(item_name)
    item_categories[normalized_item] = normalized_category
    save_item_categories(item_categories)

    expense = {
        "item": item_name,
        "amount": amount_value,
        "category": normalized_category,
        "date": parsed_date.strftime("%Y-%m-%d"),
        "comment": comment.strip(),
    }
    expenses.append(expense)
    save_expenses(expenses)
    return expense


def update_expense_record(expense_id, item_name, amount, category, date_value, comment=""):
    """Обновляет существующий расход по индексу в файле."""
    expenses = load_expenses()
    try:
        expense_index = int(expense_id)
    except (TypeError, ValueError) as error:
        raise ValueError("Некорректный идентификатор расхода.") from error

    if expense_index < 0 or expense_index >= len(expenses):
        raise ValueError("Расход для редактирования не найден.")

    item_name = item_name.strip()
    if not item_name:
        raise ValueError("Наименование не может быть пустым.")

    try:
        amount_value = float(str(amount).replace(",", "."))
    except ValueError as error:
        raise ValueError("Сумма должна быть числом.") from error

    if amount_value <= 0:
        raise ValueError("Сумма должна быть больше нуля.")

    normalized_category = normalize_category(category)
    if not normalized_category:
        raise ValueError("Категория не может быть пустой.")

    parsed_date = parse_date(date_value)
    if parsed_date is None:
        raise ValueError("Дата должна быть в формате YYYY-MM-DD.")

    add_category_to_system(normalized_category)

    expenses[expense_index] = {
        "item": item_name,
        "amount": amount_value,
        "category": normalized_category,
        "date": parsed_date.strftime("%Y-%m-%d"),
        "comment": comment.strip(),
    }
    save_expenses(expenses)

    item_categories = load_item_categories()
    item_categories[normalize_item_name(item_name)] = normalized_category
    save_item_categories(item_categories)

    return expenses[expense_index]


def delete_expense_record(expense_id):
    """Удаляет расход по индексу в файле."""
    expenses = load_expenses()
    try:
        expense_index = int(expense_id)
    except (TypeError, ValueError) as error:
        raise ValueError("Некорректный идентификатор расхода.") from error

    if expense_index < 0 or expense_index >= len(expenses):
        raise ValueError("Расход для удаления не найден.")

    removed_expense = expenses.pop(expense_index)
    save_expenses(expenses)
    return removed_expense


def rename_category_in_system(old_category, new_category):
    """Переименовывает категорию и обновляет связанные данные."""
    old_category = normalize_category(old_category)
    new_category = normalize_category(new_category)

    if not old_category or not new_category:
        raise ValueError("Названия категорий не должны быть пустыми.")
    if old_category == new_category:
        raise ValueError("Новое название совпадает с текущим.")

    categories = load_categories()
    if old_category not in categories:
        raise ValueError("Категория для переименования не найдена.")
    if new_category in categories:
        raise ValueError("Такая категория уже существует.")

    updated_categories = []
    for category in categories:
        if category == old_category:
            updated_categories.append(new_category)
        else:
            updated_categories.append(category)
    save_categories(updated_categories)

    expenses = load_expenses()
    changed_expenses = 0
    for expense in expenses:
        if expense.get("category", "") == old_category:
            expense["category"] = new_category
            changed_expenses += 1
    save_expenses(expenses)

    item_categories = load_item_categories()
    changed_items = 0
    for item_name, category in list(item_categories.items()):
        if category == old_category:
            item_categories[item_name] = new_category
            changed_items += 1
    save_item_categories(item_categories)

    limits_data = load_limits()
    if old_category in limits_data["default"]:
        limits_data["default"][new_category] = limits_data["default"].pop(old_category)
    else:
        limits_data["default"][new_category] = 0.0

    for month_limits in limits_data["monthly"].values():
        if old_category in month_limits:
            month_limits[new_category] = month_limits.pop(old_category)
        elif new_category not in month_limits:
            month_limits[new_category] = 0.0
    save_limits(limits_data)

    return {
        "changed_expenses": changed_expenses,
        "changed_items": changed_items,
    }


def remove_category_from_system(category_to_remove, replacement_category):
    """Удаляет категорию и переносит связанные данные в другую категорию."""
    category_to_remove = normalize_category(category_to_remove)
    replacement_category = normalize_category(replacement_category)

    if not category_to_remove or not replacement_category:
        raise ValueError("Категории не должны быть пустыми.")
    if category_to_remove == replacement_category:
        raise ValueError("Нельзя переносить категорию саму в себя.")

    categories = load_categories()
    if category_to_remove not in categories:
        raise ValueError("Категория для удаления не найдена.")
    if replacement_category not in categories:
        raise ValueError("Категория для переноса не найдена.")
    if len(categories) < 2:
        raise ValueError("Нельзя удалить последнюю категорию.")

    updated_categories = []
    for category in categories:
        if category != category_to_remove:
            updated_categories.append(category)
    save_categories(updated_categories)

    expenses = load_expenses()
    changed_expenses = 0
    for expense in expenses:
        if expense.get("category", "") == category_to_remove:
            expense["category"] = replacement_category
            changed_expenses += 1
    save_expenses(expenses)

    item_categories = load_item_categories()
    changed_items = 0
    for item_name, category in list(item_categories.items()):
        if category == category_to_remove:
            item_categories[item_name] = replacement_category
            changed_items += 1
    save_item_categories(item_categories)

    limits_data = load_limits()
    if category_to_remove in limits_data["default"]:
        del limits_data["default"][category_to_remove]
    if replacement_category not in limits_data["default"]:
        limits_data["default"][replacement_category] = 0.0

    for month_limits in limits_data["monthly"].values():
        if category_to_remove in month_limits:
            del month_limits[category_to_remove]
        if replacement_category not in month_limits:
            month_limits[replacement_category] = 0.0
    save_limits(limits_data)

    return {
        "changed_expenses": changed_expenses,
        "changed_items": changed_items,
    }


def set_limit_value(scope, category, limit_amount):
    """Устанавливает лимит категории без интерактивного ввода."""
    if scope not in ("default", "month"):
        raise ValueError("scope должен быть 'default' или 'month'.")

    category = normalize_category(category)
    if not category:
        raise ValueError("Категория не может быть пустой.")

    categories = load_categories()
    if category not in categories:
        raise ValueError("Такой категории нет. Сначала добавьте её в список.")

    try:
        amount_value = float(str(limit_amount).replace(",", "."))
    except ValueError as error:
        raise ValueError("Лимит должен быть числом.") from error

    if amount_value < 0:
        raise ValueError("Лимит не может быть отрицательным.")

    limits_data = load_limits()
    if scope == "default":
        limits_data["default"][category] = amount_value
    else:
        month_key = get_current_month_key()
        month_limits = get_month_limits(month_key)
        month_limits[category] = amount_value
        limits_data = load_limits()
        limits_data["monthly"][month_key] = month_limits
    save_limits(limits_data)


def zero_limit_value(scope, category):
    """Обнуляет лимит категории без интерактивного ввода."""
    set_limit_value(scope, category, 0)


def remove_limit_value(scope, category):
    """Удаляет лимит категории без интерактивного ввода."""
    if scope not in ("default", "month"):
        raise ValueError("scope должен быть 'default' или 'month'.")

    category = normalize_category(category)
    if not category:
        raise ValueError("Категория не может быть пустой.")

    limits_data = load_limits()
    if scope == "default":
        if category in limits_data["default"]:
            del limits_data["default"][category]
            save_limits(limits_data)
        else:
            raise ValueError("Для этой категории нет дефолтного лимита.")
    else:
        month_key = get_current_month_key()
        month_limits = get_month_limits(month_key)
        if category in month_limits:
            del month_limits[category]
            limits_data = load_limits()
            limits_data["monthly"][month_key] = month_limits
            save_limits(limits_data)
        else:
            raise ValueError("Для этой категории нет месячного лимита.")


def run_web_interface(host="127.0.0.1", port=8000):
    """Запускает локальный веб-интерфейс приложения."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    web_ui_path = os.path.join(base_dir, WEB_UI_FILE)

    if not os.path.exists(web_ui_path):
        print(f"Файл веб-интерфейса не найден: {web_ui_path}")
        return

    class ExpenseWebHandler(BaseHTTPRequestHandler):
        def _send_json(self, payload, status=200):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html_file(self, file_path):
            with open(file_path, "rb") as file:
                body = file.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self):
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0:
                return {}
            raw_body = self.rfile.read(content_length).decode("utf-8")
            if not raw_body.strip():
                return {}
            return json.loads(raw_body)

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path in ("/", "/index.html"):
                self._send_html_file(web_ui_path)
                return
            if parsed.path == "/api/state":
                self._send_json({"ok": True, "data": build_state_payload()})
                return
            self._send_json({"ok": False, "error": "Маршрут не найден."}, status=404)

        def do_POST(self):
            parsed = urlparse(self.path)
            try:
                payload = self._read_json_body()
                if parsed.path == "/api/expenses":
                    expense = add_expense_record(
                        payload.get("item", ""),
                        payload.get("amount", 0),
                        payload.get("category", ""),
                        payload.get("date", ""),
                        payload.get("comment", ""),
                    )
                    self._send_json({"ok": True, "expense": expense, "data": build_state_payload()})
                    return
                if parsed.path == "/api/expenses/update":
                    expense = update_expense_record(
                        payload.get("id"),
                        payload.get("item", ""),
                        payload.get("amount", 0),
                        payload.get("category", ""),
                        payload.get("date", ""),
                        payload.get("comment", ""),
                    )
                    self._send_json({"ok": True, "expense": expense, "data": build_state_payload()})
                    return
                if parsed.path == "/api/expenses/delete":
                    removed_expense = delete_expense_record(payload.get("id"))
                    self._send_json({"ok": True, "expense": removed_expense, "data": build_state_payload()})
                    return
                if parsed.path == "/api/categories/add":
                    category = normalize_category(payload.get("name", ""))
                    if not category:
                        raise ValueError("Категория не может быть пустой.")
                    categories = load_categories()
                    if category in categories:
                        raise ValueError("Такая категория уже существует.")
                    add_category_to_system(category)
                    self._send_json({"ok": True, "data": build_state_payload()})
                    return
                if parsed.path == "/api/categories/rename":
                    result = rename_category_in_system(
                        payload.get("oldCategory", ""),
                        payload.get("newCategory", ""),
                    )
                    self._send_json({"ok": True, "result": result, "data": build_state_payload()})
                    return
                if parsed.path == "/api/categories/remove":
                    result = remove_category_from_system(
                        payload.get("category", ""),
                        payload.get("replacementCategory", ""),
                    )
                    self._send_json({"ok": True, "result": result, "data": build_state_payload()})
                    return
                if parsed.path == "/api/limits/set":
                    set_limit_value(
                        payload.get("scope", ""),
                        payload.get("category", ""),
                        payload.get("amount", 0),
                    )
                    self._send_json({"ok": True, "data": build_state_payload()})
                    return
                if parsed.path == "/api/limits/zero":
                    zero_limit_value(payload.get("scope", ""), payload.get("category", ""))
                    self._send_json({"ok": True, "data": build_state_payload()})
                    return
                if parsed.path == "/api/limits/remove":
                    remove_limit_value(payload.get("scope", ""), payload.get("category", ""))
                    self._send_json({"ok": True, "data": build_state_payload()})
                    return
                self._send_json({"ok": False, "error": "Маршрут не найден."}, status=404)
            except ValueError as error:
                self._send_json({"ok": False, "error": str(error)}, status=400)
            except json.JSONDecodeError:
                self._send_json({"ok": False, "error": "Некорректный JSON в запросе."}, status=400)
            except Exception as error:
                self._send_json({"ok": False, "error": f"Внутренняя ошибка: {error}"}, status=500)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer((host, port), ExpenseWebHandler)
    url = f"http://{host}:{port}"
    print(f"Веб-интерфейс запущен: {url}")
    print("Для остановки нажмите Ctrl+C.")

    try:
        webbrowser.open(url)
    except Exception:
        print("Не удалось автоматически открыть браузер.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nВеб-интерфейс остановлен.")
    finally:
        server.server_close()


def get_current_year_month():
    """Возвращает текущий год и месяц как кортеж (год, месяц)."""
    now = datetime.now()
    return now.year, now.month


def get_current_month_key():
    """Возвращает текущий месяц в формате YYYY-MM."""
    now = datetime.now()
    return f"{now.year:04d}-{now.month:02d}"


def parse_date(date_text):
    """
    Преобразует строку даты формата YYYY-MM-DD в объект datetime.
    Возвращает None, если формат неверный.
    """
    try:
        return datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        return None


def get_month_limits(month_key):
    """
    Возвращает лимиты конкретного месяца.
    Если лимиты на месяц ещё не были заданы, копирует дефолтные.
    """
    limits_data = load_limits()

    if month_key not in limits_data["monthly"] or not isinstance(limits_data["monthly"][month_key], dict):
        limits_data["monthly"][month_key] = dict(limits_data["default"])
        save_limits(limits_data)

    return limits_data["monthly"][month_key]


def get_month_limits_for_current():
    """Удобный метод для получения лимитов текущего месяца."""
    return get_month_limits(get_current_month_key())


def pick_category_interactive():
    """
    Даёт выбрать категорию из фиксированного списка.
    Разрешает добавить новую категорию при необходимости.
    """
    categories = load_categories()

    while True:
        print("Доступные категории:")
        for index, category in enumerate(categories, start=1):
            print(f"  {index}. {category}")
        print("  0. Добавить новую категорию")

        choice = input("Выберите номер категории: ").strip()
        if not choice:
            print("Введите номер из списка.")
            continue

        try:
            number = int(choice)
        except ValueError:
            print("Нужно ввести целое число.")
            continue

        if number == 0:
            new_name = input("Введите название новой категории: ").strip()
            normalized = normalize_category(new_name)
            if not normalized:
                print("Категория не может быть пустой.")
                continue
            if normalized in categories:
                print("Такая категория уже существует.")
                continue

            add_category_to_system(normalized)
            print(f"Категория '{normalized}' добавлена.")
            categories = load_categories()
            continue

        if 1 <= number <= len(categories):
            return categories[number - 1]

        print("Номер вне диапазона. Повторите ввод.")


def input_amount():
    """Запрашивает сумму и возвращает корректное число."""
    while True:
        amount_input = input("Введите сумму: ").strip().replace(",", ".")
        try:
            amount = float(amount_input)
            if amount <= 0:
                print("Сумма должна быть больше нуля.")
                continue
            return amount
        except ValueError:
            print("Некорректная сумма. Введите число, например 250 или 99.50.")


def input_date():
    """Запрашивает дату или ставит сегодняшнюю, если ввод пустой."""
    while True:
        date_input = input("Введите дату (YYYY-MM-DD) или Enter для сегодняшней: ").strip()
        if not date_input:
            return datetime.now().strftime("%Y-%m-%d")
        parsed = parse_date(date_input)
        if parsed is None:
            print("Некорректный формат даты. Используйте YYYY-MM-DD.")
            continue
        return parsed.strftime("%Y-%m-%d")


def resolve_category_for_item(item_name, item_categories):
    """
    Возвращает категорию для позиции.
    Если позиция известна, берёт сохранённую категорию, иначе предлагает выбор.
    """
    normalized_item = normalize_item_name(item_name)
    if normalized_item in item_categories:
        category = item_categories[normalized_item]
        print(f"Для позиции '{item_name}' использована сохранённая категория: {category}")
        return category

    print("Для этой позиции категория ещё не задана.")
    category = pick_category_interactive()
    return category


def add_expense():
    """Интерактивно добавляет один расход в файл."""
    expenses = load_expenses()
    item_categories = load_item_categories()

    # Сначала запрашиваем наименование товара/услуги.
    while True:
        item_name = input("Введите товар/услугу: ").strip()
        if item_name:
            break
        print("Наименование не может быть пустым.")

    amount = input_amount()
    category = resolve_category_for_item(item_name, item_categories)
    date_value = input_date()
    comment = input("Комментарий (необязательно): ").strip()

    # Перед сохранением даём возможность исправить ключевые поля.
    while True:
        print("\nПроверьте запись перед сохранением:")
        print(f"  Товар/услуга: {item_name}")
        print(f"  Сумма: {amount:.2f}")
        print(f"  Категория: {category}")
        print(f"  Дата: {date_value}")
        print(f"  Комментарий: {comment if comment else '(пусто)'}")
        print(
            "Действия: Enter/save | edit item | edit amount | edit category | "
            "edit date | edit comment | cancel"
        )

        action = input("Введите действие: ").strip().lower()
        if action in ("", "save"):
            break
        if action == "cancel":
            print("Добавление записи отменено.")
            return
        if action == "edit item":
            while True:
                new_item = input("Введите товар/услугу: ").strip()
                if new_item:
                    item_name = new_item
                    break
                print("Наименование не может быть пустым.")
            # При смене товара пытаемся автоматически подобрать категорию заново.
            category = resolve_category_for_item(item_name, item_categories)
            continue
        if action == "edit amount":
            amount = input_amount()
            continue
        if action == "edit category":
            category = pick_category_interactive()
            continue
        if action == "edit date":
            date_value = input_date()
            continue
        if action == "edit comment":
            comment = input("Комментарий (необязательно): ").strip()
            continue

        print("Неизвестное действие. Введите одно из предложенных значений.")

    # Сохраняем/обновляем связь 'позиция -> категория' после подтверждения записи.
    normalized_item = normalize_item_name(item_name)
    item_categories[normalized_item] = category
    save_item_categories(item_categories)
    print(f"Связка сохранена: '{item_name}' -> '{category}'")

    expense = {
        "item": item_name,
        "amount": amount,
        "category": category,
        "date": date_value,
        "comment": comment,
    }
    expenses.append(expense)
    save_expenses(expenses)
    print("Расход успешно добавлен.")

    # Сразу подсказываем статус лимита текущего месяца для выбранной категории.
    month_expenses = get_current_month_expenses(expenses)
    category_total = 0.0
    for item in month_expenses:
        if item.get("category", "") == category:
            category_total += float(item.get("amount", 0))

    current_limits = get_month_limits_for_current()
    limit_amount = float(current_limits.get(category, 0))
    if limit_amount > 0:
        if category_total > limit_amount:
            print(
                f"Внимание: лимит категории '{category}' превышен на "
                f"{category_total - limit_amount:.2f}"
            )
        else:
            print(
                f"Лимит категории '{category}': {category_total:.2f} из {limit_amount:.2f} "
                f"({(category_total / limit_amount) * 100:.1f}%)"
            )


def get_current_month_expenses(expenses):
    """Возвращает только расходы за текущий месяц."""
    year, month = get_current_year_month()
    result = []
    for expense in expenses:
        date_text = expense.get("date", "")
        parsed = parse_date(date_text)
        if parsed is None:
            continue
        if parsed.year == year and parsed.month == month:
            result.append(expense)
    return result


def calculate_category_totals(expenses):
    """Считает сумму расходов по категориям."""
    category_totals = {}
    for expense in expenses:
        category = expense.get("category", "Без категории")
        amount = float(expense.get("amount", 0))
        if category not in category_totals:
            category_totals[category] = 0.0
        category_totals[category] += amount
    return category_totals


def calculate_daily_totals(expenses):
    """Считает сумму расходов по дням."""
    daily_totals = {}
    for expense in expenses:
        date_text = expense.get("date", "")
        amount = float(expense.get("amount", 0))
        if date_text not in daily_totals:
            daily_totals[date_text] = 0.0
        daily_totals[date_text] += amount
    return dict(sorted(daily_totals.items()))


def get_chart_palette():
    """Возвращает палитру цветов для диаграмм."""
    return [
        "#4F46E5",
        "#0EA5E9",
        "#10B981",
        "#F59E0B",
        "#EF4444",
        "#8B5CF6",
        "#EC4899",
        "#14B8A6",
        "#F97316",
        "#84CC16",
    ]


def build_pie_chart_svg(category_totals):
    """Строит SVG круговой диаграммы по категориям."""
    width = 860
    height = 360
    center_x = 180
    center_y = 180
    radius = 110
    palette = get_chart_palette()
    total = sum(category_totals.values())

    svg_parts = [
        f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" '
        'aria-label="Круговая диаграмма расходов по категориям">'
    ]

    if total <= 0:
        svg_parts.append(
            '<text x="50%" y="50%" text-anchor="middle" dominant-baseline="middle" '
            'class="empty-label">Нет данных для диаграммы</text>'
        )
        svg_parts.append("</svg>")
        return "".join(svg_parts)

    sorted_categories = sorted(category_totals.items(), key=lambda item: item[1], reverse=True)
    start_angle = -math.pi / 2

    for index, (category, amount) in enumerate(sorted_categories):
        fraction = amount / total
        sweep_angle = fraction * math.pi * 2
        end_angle = start_angle + sweep_angle
        large_arc_flag = 1 if sweep_angle > math.pi else 0

        start_x = center_x + radius * math.cos(start_angle)
        start_y = center_y + radius * math.sin(start_angle)
        end_x = center_x + radius * math.cos(end_angle)
        end_y = center_y + radius * math.sin(end_angle)
        color = palette[index % len(palette)]

        if len(sorted_categories) == 1:
            svg_parts.append(
                f'<circle cx="{center_x}" cy="{center_y}" r="{radius}" fill="{color}"></circle>'
            )
        else:
            path = (
                f"M {center_x} {center_y} "
                f"L {start_x:.2f} {start_y:.2f} "
                f"A {radius} {radius} 0 {large_arc_flag} 1 {end_x:.2f} {end_y:.2f} Z"
            )
            svg_parts.append(f'<path d="{path}" fill="{color}"></path>')

        legend_y = 45 + (index * 28)
        percent = fraction * 100
        safe_category = html.escape(category)
        svg_parts.append(
            f'<rect x="390" y="{legend_y - 12}" width="14" height="14" rx="3" fill="{color}"></rect>'
        )
        svg_parts.append(
            f'<text x="414" y="{legend_y}" class="legend-label">'
            f"{safe_category}: {amount:.2f} ({percent:.1f}%)</text>"
        )
        start_angle = end_angle

    svg_parts.append("</svg>")
    return "".join(svg_parts)


def build_line_chart_svg(daily_totals):
    """Строит SVG линейного графика расходов по дням."""
    width = 860
    height = 360
    left = 70
    right = width - 30
    top = 30
    bottom = height - 55
    plot_width = right - left
    plot_height = bottom - top
    items = list(daily_totals.items())

    svg_parts = [
        f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" '
        'aria-label="Линейный график расходов по дням">'
    ]

    if not items:
        svg_parts.append(
            '<text x="50%" y="50%" text-anchor="middle" dominant-baseline="middle" '
            'class="empty-label">Нет данных для графика</text>'
        )
        svg_parts.append("</svg>")
        return "".join(svg_parts)

    max_value = max(amount for _, amount in items)
    if max_value <= 0:
        max_value = 1.0

    for step in range(6):
        value = max_value * (5 - step) / 5
        y = top + (plot_height * step / 5)
        svg_parts.append(
            f'<line x1="{left}" y1="{y:.2f}" x2="{right}" y2="{y:.2f}" class="grid-line"></line>'
        )
        svg_parts.append(
            f'<text x="{left - 12}" y="{y + 4:.2f}" text-anchor="end" class="axis-label">{value:.0f}</text>'
        )

    svg_parts.append(f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" class="axis-line"></line>')
    svg_parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" class="axis-line"></line>')

    points = []
    for index, (date_text, amount) in enumerate(items):
        x = left if len(items) == 1 else left + (plot_width * index / (len(items) - 1))
        y = bottom - ((amount / max_value) * plot_height)
        points.append((x, y, date_text, amount))

    polyline_points = " ".join(f"{x:.2f},{y:.2f}" for x, y, _, _ in points)
    svg_parts.append(f'<polyline points="{polyline_points}" class="line-path"></polyline>')

    for x, y, date_text, amount in points:
        day_label = html.escape(date_text[8:10] if len(date_text) >= 10 else date_text)
        full_date = html.escape(date_text)
        svg_parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4.5" class="line-point"></circle>')
        svg_parts.append(
            f'<text x="{x:.2f}" y="{bottom + 22}" text-anchor="middle" class="axis-label">{day_label}</text>'
        )
        svg_parts.append(
            f'<text x="{x:.2f}" y="{y - 12:.2f}" text-anchor="middle" class="point-label">'
            f"{amount:.0f}</text>"
        )
        svg_parts.append(
            f'<title>{full_date}: {amount:.2f}</title>'
        )

    svg_parts.append("</svg>")
    return "".join(svg_parts)


def generate_visual_report():
    """Создаёт HTML-отчёт с диаграммой и графиком по расходам текущего месяца."""
    expenses = load_expenses()
    month_expenses = get_current_month_expenses(expenses)

    if not month_expenses:
        print("За текущий месяц расходов не найдено.")
        return

    category_totals = calculate_category_totals(month_expenses)
    daily_totals = calculate_daily_totals(month_expenses)
    month_total = sum(category_totals.values())
    month_key = get_current_month_key()

    sorted_categories = sorted(category_totals.items(), key=lambda item: item[1], reverse=True)
    rows_html = []
    for category, amount in sorted_categories:
        percent = (amount / month_total) * 100 if month_total else 0
        rows_html.append(
            "<tr>"
            f"<td>{html.escape(category)}</td>"
            f"<td>{amount:.2f}</td>"
            f"<td>{percent:.1f}%</td>"
            "</tr>"
        )

    report_html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <title>Отчёт по расходам за {month_key}</title>
  <style>
    body {{
      font-family: Arial, sans-serif;
      margin: 0;
      padding: 24px;
      background: #f5f7fb;
      color: #1f2937;
    }}
    .container {{
      max-width: 1100px;
      margin: 0 auto;
    }}
    .card {{
      background: #ffffff;
      border-radius: 16px;
      padding: 20px 24px;
      margin-bottom: 20px;
      box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
    }}
    h1, h2 {{
      margin-top: 0;
    }}
    .summary {{
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
    }}
    .summary-item {{
      background: #eef2ff;
      border-radius: 12px;
      padding: 14px 16px;
      min-width: 180px;
    }}
    .summary-label {{
      display: block;
      font-size: 14px;
      color: #4b5563;
      margin-bottom: 6px;
    }}
    .summary-value {{
      font-size: 28px;
      font-weight: bold;
      color: #111827;
    }}
    .chart {{
      width: 100%;
      height: auto;
      overflow: visible;
    }}
    .legend-label, .axis-label, .point-label, .empty-label {{
      fill: #374151;
      font-size: 13px;
    }}
    .grid-line {{
      stroke: #d1d5db;
      stroke-width: 1;
    }}
    .axis-line {{
      stroke: #6b7280;
      stroke-width: 1.5;
    }}
    .line-path {{
      fill: none;
      stroke: #4f46e5;
      stroke-width: 3;
      stroke-linecap: round;
      stroke-linejoin: round;
    }}
    .line-point {{
      fill: #4f46e5;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid #e5e7eb;
      text-align: left;
    }}
    th {{
      background: #f9fafb;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="card">
      <h1>Отчёт по расходам за {month_key}</h1>
      <div class="summary">
        <div class="summary-item">
          <span class="summary-label">Общая сумма</span>
          <span class="summary-value">{month_total:.2f}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">Количество записей</span>
          <span class="summary-value">{len(month_expenses)}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">Категорий с расходами</span>
          <span class="summary-value">{len(category_totals)}</span>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>Диаграмма по категориям</h2>
      {build_pie_chart_svg(category_totals)}
    </div>

    <div class="card">
      <h2>График расходов по дням</h2>
      {build_line_chart_svg(daily_totals)}
    </div>

    <div class="card">
      <h2>Таблица по категориям</h2>
      <table>
        <thead>
          <tr>
            <th>Категория</th>
            <th>Сумма</th>
            <th>Доля</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows_html)}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""

    with open(REPORT_FILE, "w", encoding="utf-8") as file:
        file.write(report_html)

    report_path = os.path.abspath(REPORT_FILE)
    print(f"Визуальный отчёт сформирован: {report_path}")

    try:
        webbrowser.open(f"file://{report_path}")
        print("Отчёт открыт в браузере.")
    except Exception:
        print("Не удалось автоматически открыть отчёт в браузере.")


def list_expenses():
    """Показывает расходы за текущий месяц, сгруппированные по датам."""
    expenses = load_expenses()
    month_expenses = get_current_month_expenses(expenses)

    if not month_expenses:
        print("За текущий месяц расходов не найдено.")
        return

    # Группируем расходы по дате в словарь: дата -> список расходов.
    grouped = {}
    for expense in month_expenses:
        date_key = expense.get("date", "")
        if date_key not in grouped:
            grouped[date_key] = []
        grouped[date_key].append(expense)

    # Сортируем даты по возрастанию.
    sorted_dates = sorted(grouped.keys())
    for date_key in sorted_dates:
        print(f"\nДата: {date_key}")
        day_total = 0.0
        for item in grouped[date_key]:
            item_name = item.get("item", "Без названия")
            amount = float(item.get("amount", 0))
            category = item.get("category", "Без категории")
            comment = item.get("comment", "")
            day_total += amount
            if comment:
                print(f"  - {item_name} | {amount:.2f} | {category} | {comment}")
            else:
                print(f"  - {item_name} | {amount:.2f} | {category}")
        print(f"  Итого за день: {day_total:.2f}")


def show_stats():
    """Показывает итоговую сумму по каждой категории за текущий месяц."""
    expenses = load_expenses()
    month_expenses = get_current_month_expenses(expenses)

    if not month_expenses:
        print("За текущий месяц расходов не найдено.")
        return

    category_totals = calculate_category_totals(month_expenses)

    # Считаем общую сумму за месяц, чтобы показывать долю каждой категории.
    month_total = 0.0
    for amount in category_totals.values():
        month_total += amount

    print("Статистика по категориям за текущий месяц:")
    print(f"Общий итог за месяц: {month_total:.2f}\n")

    # Выводим категории в порядке убывания суммы для более наглядного отчёта.
    sorted_categories = sorted(category_totals.items(), key=lambda item: item[1], reverse=True)
    month_limits = get_month_limits_for_current()
    for category, amount in sorted_categories:
        percent = (amount / month_total) * 100
        line = f"- {category}: {amount:.2f} ({percent:.1f}%)"

        # Если для категории задан лимит, показываем прогресс/превышение.
        limit_amount = float(month_limits.get(category, 0))
        if limit_amount > 0:
            used_percent = (amount / limit_amount) * 100
            if amount > limit_amount:
                line += f" | Лимит {limit_amount:.2f} (ПРЕВЫШЕН на {amount - limit_amount:.2f})"
            else:
                line += f" | Лимит {limit_amount:.2f} (использовано {used_percent:.1f}%)"

        print(line)


def ask_limit_scope():
    """Спрашивает, где менять лимит: в дефолтных или в текущем месяце."""
    while True:
        scope = input("Где менять лимит? (default/month): ").strip().lower()
        if scope in ("default", "month"):
            return scope
        print("Введите 'default' или 'month'.")


def ask_limit_category():
    """Спрашивает категорию для операций с лимитом."""
    categories = load_categories()
    print("Категории:")
    for category in categories:
        print(f"- {category}")
    while True:
        category = normalize_category(input("Введите категорию: ").strip())
        if not category:
            print("Категория не может быть пустой.")
            continue
        if category not in categories:
            print("Такой категории нет. Сначала добавьте её через 'categories add'.")
            continue
        return category


def set_limit():
    """Задаёт или изменяет лимит категории."""
    scope = ask_limit_scope()
    category = ask_limit_category()

    while True:
        limit_input = input("Введите лимит (число >= 0): ").strip().replace(",", ".")
        try:
            limit_amount = float(limit_input)
            if limit_amount < 0:
                print("Лимит не может быть отрицательным.")
                continue
            break
        except ValueError:
            print("Некорректный лимит. Введите число, например 15000 или 7500.50.")

    limits_data = load_limits()
    if scope == "default":
        limits_data["default"][category] = limit_amount
        save_limits(limits_data)
        print(f"Дефолтный лимит для '{category}' установлен: {limit_amount:.2f}")
    else:
        month_key = get_current_month_key()
        month_limits = get_month_limits(month_key)
        month_limits[category] = limit_amount
        limits_data = load_limits()
        limits_data["monthly"][month_key] = month_limits
        save_limits(limits_data)
        print(f"Лимит текущего месяца для '{category}' установлен: {limit_amount:.2f}")


def zero_limit():
    """Обнуляет лимит категории (ставит 0)."""
    scope = ask_limit_scope()
    category = ask_limit_category()

    limits_data = load_limits()
    if scope == "default":
        limits_data["default"][category] = 0.0
        save_limits(limits_data)
        print(f"Дефолтный лимит категории '{category}' обнулён.")
    else:
        month_key = get_current_month_key()
        month_limits = get_month_limits(month_key)
        month_limits[category] = 0.0
        limits_data = load_limits()
        limits_data["monthly"][month_key] = month_limits
        save_limits(limits_data)
        print(f"Лимит текущего месяца категории '{category}' обнулён.")


def remove_limit():
    """
    Удаляет лимит категории:
    - для default: удаляет ключ (при следующем обновлении может появиться как 0)
    - для month: удаляет месячное переопределение
    """
    scope = ask_limit_scope()
    category = ask_limit_category()
    limits_data = load_limits()

    if scope == "default":
        if category in limits_data["default"]:
            del limits_data["default"][category]
            save_limits(limits_data)
            print(f"Дефолтный лимит категории '{category}' удалён.")
        else:
            print("Для этой категории нет дефолтного лимита.")
    else:
        month_key = get_current_month_key()
        month_limits = get_month_limits(month_key)
        if category in month_limits:
            del month_limits[category]
            limits_data = load_limits()
            limits_data["monthly"][month_key] = month_limits
            save_limits(limits_data)
            print(f"Месячный лимит категории '{category}' удалён.")
        else:
            print("Для этой категории нет месячного лимита.")


def list_limits():
    """Показывает дефолтные и текущие месячные лимиты."""
    limits_data = load_limits()
    month_key = get_current_month_key()
    month_limits = get_month_limits(month_key)

    print("Дефолтные лимиты:")
    for category in sorted(load_categories()):
        print(f"- {category}: {float(limits_data['default'].get(category, 0)):.2f}")

    print(f"\nЛимиты текущего месяца ({month_key}):")
    for category in sorted(load_categories()):
        print(f"- {category}: {float(month_limits.get(category, 0)):.2f}")


def list_categories():
    """Показывает список доступных категорий."""
    categories = load_categories()
    print("Категории:")
    for category in categories:
        print(f"- {category}")


def add_category():
    """Добавляет новую категорию в систему."""
    new_name = input("Введите новую категорию: ").strip()
    normalized = normalize_category(new_name)
    if not normalized:
        print("Категория не может быть пустой.")
        return

    categories = load_categories()
    if normalized in categories:
        print("Такая категория уже существует.")
        return

    add_category_to_system(normalized)
    print(f"Категория '{normalized}' успешно добавлена.")


def choose_existing_category(prompt_text, exclude_category=None):
    """Просит ввести существующую категорию, при необходимости исключая одну из них."""
    categories = load_categories()
    available_categories = []
    for category in categories:
        if category != exclude_category:
            available_categories.append(category)

    if not available_categories:
        print("Нет доступных категорий для выбора.")
        return None

    print("Категории:")
    for category in available_categories:
        print(f"- {category}")

    while True:
        category = normalize_category(input(prompt_text).strip())
        if not category:
            print("Категория не может быть пустой.")
            continue
        if category not in available_categories:
            print("Такой категории нет в списке.")
            continue
        return category


def rename_category():
    """Переименовывает категорию и обновляет связанные данные."""
    old_category = choose_existing_category("Введите категорию для переименования: ")
    if not old_category:
        return

    new_name = input("Введите новое название категории: ").strip()
    new_category = normalize_category(new_name)
    if not new_category:
        print("Новое название категории не может быть пустым.")
        return

    try:
        result = rename_category_in_system(old_category, new_category)
    except ValueError as error:
        print(error)
        return

    print(
        f"Категория '{old_category}' переименована в '{new_category}'. "
        f"Обновлено записей расходов: {result['changed_expenses']}, "
        f"автокатегорий: {result['changed_items']}."
    )


def remove_category():
    """Удаляет категорию с переносом связанных записей в другую категорию."""
    categories = load_categories()
    if len(categories) < 2:
        print("Нельзя удалить последнюю категорию в списке.")
        return

    category_to_remove = choose_existing_category("Введите категорию для удаления: ")
    if not category_to_remove:
        return

    replacement_category = choose_existing_category(
        f"Введите категорию для переноса данных вместо '{category_to_remove}': ",
        exclude_category=category_to_remove,
    )
    if not replacement_category:
        return

    confirm = input(
        f"Подтвердите удаление категории '{category_to_remove}' "
        f"с переносом в '{replacement_category}' (yes/no): "
    ).strip().lower()
    if confirm not in ("yes", "y", "да"):
        print("Удаление категории отменено.")
        return

    try:
        result = remove_category_from_system(category_to_remove, replacement_category)
    except ValueError as error:
        print(error)
        return

    print(
        f"Категория '{category_to_remove}' удалена. "
        f"Перенесено записей расходов: {result['changed_expenses']}, "
        f"автокатегорий: {result['changed_items']}."
    )


def print_help():
    """Печатает подсказку по запуску программы."""
    print("Доступные команды:")
    print("  python main.py add")
    print("  python main.py list")
    print("  python main.py stats")
    print("  python main.py charts")
    print("  python main.py web")
    print("  python main.py limits set")
    print("  python main.py limits zero")
    print("  python main.py limits remove")
    print("  python main.py limits list")
    print("  python main.py categories list")
    print("  python main.py categories add")
    print("  python main.py categories rename")
    print("  python main.py categories remove")
    print("  python main.py expenses add")
    print("  python main.py expenses list")
    print("  python main.py expenses stats")
    print("  python main.py expenses charts")
    print("  python main.py expenses web")
    print("  python main.py expenses limits set")
    print("  python main.py expenses limits zero")
    print("  python main.py expenses limits remove")
    print("  python main.py expenses limits list")
    print("  python main.py expenses categories list")
    print("  python main.py expenses categories add")
    print("  python main.py expenses categories rename")
    print("  python main.py expenses categories remove")


def get_args_from_argv(argv):
    """
    Возвращает пользовательские аргументы запуска.
    Поддерживаются два формата:
    1) python main.py <args...>
    2) python main.py expenses <args...>
    """
    args = argv[1:]

    if not args:
        return []

    if args[0] == "expenses":
        return args[1:]
    return args


def run_command(args):
    """Выполняет одну команду приложения и возвращает True/False (успех/ошибка)."""
    if not args:
        print_help()
        return False

    command = args[0]
    if command == "add":
        if len(args) != 1:
            print("Команда 'add' не принимает дополнительных аргументов.")
            print_help()
            return False
        add_expense()
        return True
    elif command == "list":
        if len(args) != 1:
            print("Команда 'list' не принимает дополнительных аргументов.")
            print_help()
            return False
        list_expenses()
        return True
    elif command == "stats":
        if len(args) != 1:
            print("Команда 'stats' не принимает дополнительных аргументов.")
            print_help()
            return False
        show_stats()
        return True
    elif command == "charts":
        if len(args) != 1:
            print("Команда 'charts' не принимает дополнительных аргументов.")
            print_help()
            return False
        generate_visual_report()
        return True
    elif command == "web":
        if len(args) != 1:
            print("Команда 'web' не принимает дополнительных аргументов.")
            print_help()
            return False
        run_web_interface()
        return True
    elif command == "limits":
        if len(args) != 2:
            print("Используйте: limits set | limits zero | limits remove | limits list")
            print_help()
            return False
        subcommand = args[1]
        if subcommand == "set":
            set_limit()
        elif subcommand == "zero":
            zero_limit()
        elif subcommand == "remove":
            remove_limit()
        elif subcommand == "list":
            list_limits()
        else:
            print(f"Неизвестная подкоманда limits: {subcommand}")
            print_help()
            return False
        return True
    elif command == "categories":
        if len(args) != 2:
            print("Используйте: categories list | categories add | categories rename | categories remove")
            print_help()
            return False
        subcommand = args[1]
        if subcommand == "list":
            list_categories()
        elif subcommand == "add":
            add_category()
        elif subcommand == "rename":
            rename_category()
        elif subcommand == "remove":
            remove_category()
        else:
            print(f"Неизвестная подкоманда categories: {subcommand}")
            print_help()
            return False
        return True
    else:
        print(f"Неизвестная команда: {command}")
        print_help()
        return False


def run_interactive_mode():
    """
    Запускает интерактивный режим:
    - показывает подсказки при старте
    - принимает команды до выхода
    """
    print("Личный учёт расходов — интерактивный режим")
    print("Введите одну из команд: add, list, stats, charts, web, limits ..., categories ...")
    print("Дополнительно: help — показать подсказки, exit — выйти\n")
    print_help()
    print("")

    while True:
        raw = input("expenses> ").strip()
        if not raw:
            print("Введите команду или 'help'.")
            continue

        if raw.lower() in ("exit", "quit", "q"):
            print("Выход из приложения.")
            break

        if raw.lower() in ("help", "h", "?"):
            print_help()
            print("")
            continue

        command_args = raw.split()
        run_command(command_args)
        print("")


def main():
    """
    Точка входа.
    Поддерживает:
    - запуск с аргументами (python main.py <command>)
    - интерактивный режим (python main.py)
    """
    args = get_args_from_argv(sys.argv)
    if not args:
        run_interactive_mode()
        return

    run_command(args)


if __name__ == "__main__":
    main()
