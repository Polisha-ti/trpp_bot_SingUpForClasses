FROM python:3.10-slim-buster

WORKDIR /app

# Установка зависимостей, необходимых для работы бота
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    locales && \
    rm -rf /var/lib/apt/lists/*

# Генерация и установка русской локали
RUN sed -i -e 's/# ru_RU.UTF-8 UTF-8/ru_RU.UTF-8 UTF-8/' /etc/locale.gen && \
    dpkg-reconfigure --frontend=noninteractive locales && \
    locale-gen

# Установка переменных окружения для локали
ENV LANG=ru_RU.UTF-8
ENV LANGUAGE=ru_RU:en
ENV LC_ALL=ru_RU.UTF-8

# Установка временной зоны (например, для Москвы)
ENV TZ=Europe/Moscow
RUN ln -sf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Копирование файла requirements.txt, если он есть, и установка зависимостей
# Если у вас нет requirements.txt, удалите или закомментируйте эти строки
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование всего кода приложения
COPY ./bot .

# Определение команды для запуска приложения
# Предполагается, что ваш основной исполняемый файл называется bot_2.py
CMD ["python", "bot_2.py"]