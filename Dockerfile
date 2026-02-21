FROM python:3.9-slim

WORKDIR /app

# Копирую requirements.txt и установлю зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирую основной файл
COPY main.py .

# Создаю директории для хранения
RUN mkdir -p storage/diagnostics

# Запускаю приложение
CMD ["python", "main.py"]
