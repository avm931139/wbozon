import threading
import sys


class ThreadSafeProgressBar:
    """
    Класс для отображения прогресс-бара в консоли с поддержкой многопоточности.

    Подходит для отображения текущего хода выполнения задач, которые обрабатываются параллельно в нескольких потоках.
    Использует блокировку (threading.Lock) для безопасного обновления состояния из разных потоков.

    Атрибуты:
        total (int): Общее количество шагов (элементов), которое требуется обработать.
        prefix (str): Текст, отображаемый перед прогресс-баром (по умолчанию 'Загрузка').
        suffix (str): Текст, отображаемый после прогресс-бара (по умолчанию 'Готово').
        length (int): Длина визуальной полоски прогресса (по умолчанию 50 символов).
        fill (str): Символ, которым заполняется прогресс-бар (по умолчанию '█').

    Методы:
        update(step=1):
            Увеличивает текущий прогресс на указанное количество шагов (по умолчанию 1).
            Перерисовывает прогресс-бар в консоли.
            При достижении total автоматически переходит на новую строку.
    """

    def __init__(self, total, prefix='Загрузка', suffix='Готово', length=50, fill='█'):
        self.total = total
        self.prefix = prefix
        self.suffix = suffix
        self.length = length
        self.fill = fill
        self.current = 0
        self.lock = threading.Lock()

    def update(self, step=1):
        with self.lock:
            self.current += step
            percent = f"{100 * (self.current / float(self.total)):.1f}"
            filled_length = int(self.length * self.current // self.total)
            bar = self.fill * filled_length + '-' * (self.length - filled_length)
            sys.stdout.write(f'\r{self.prefix} |{bar}| {percent}% {self.suffix}')
            sys.stdout.flush()
            if self.current == self.total:
                print()
