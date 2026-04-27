import json
import sys
from datetime import datetime


# Имя файла для хранения расходов в формате JSON.
DATA_FILE = "expenses.json"
# Имя файла для хранения лимитов категорий (дефолтных и помесячных).
LIMITS_FILE = "limits.json"
# Имя файла для хранения списка категорий.
CATEGORIES_FILE = "categories.json"
# Имя файла для хранения соответствия "позиция -> категория".
ITEM_CATEGORY_FILE = "item_categories.json"

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
        print("Действия: save | edit item | edit amount | edit category | edit date | edit comment | cancel")

        action = input("Введите действие: ").strip().lower()
        if action == "save":
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

    # Считаем сумму по категориям.
    category_totals = {}
    for expense in month_expenses:
        category = expense.get("category", "Без категории")
        amount = float(expense.get("amount", 0))
        if category not in category_totals:
            category_totals[category] = 0.0
        category_totals[category] += amount

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


def print_help():
    """Печатает подсказку по запуску программы."""
    print("Доступные команды:")
    print("  python main.py add")
    print("  python main.py list")
    print("  python main.py stats")
    print("  python main.py limits set")
    print("  python main.py limits zero")
    print("  python main.py limits remove")
    print("  python main.py limits list")
    print("  python main.py categories list")
    print("  python main.py categories add")
    print("  python main.py expenses add")
    print("  python main.py expenses list")
    print("  python main.py expenses stats")
    print("  python main.py expenses limits set")
    print("  python main.py expenses limits zero")
    print("  python main.py expenses limits remove")
    print("  python main.py expenses limits list")
    print("  python main.py expenses categories list")
    print("  python main.py expenses categories add")


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
            print("Используйте: categories list или categories add")
            print_help()
            return False
        subcommand = args[1]
        if subcommand == "list":
            list_categories()
        elif subcommand == "add":
            add_category()
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
    print("Введите одну из команд: add, list, stats, limits ..., categories ...")
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
