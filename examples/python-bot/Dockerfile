FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir 'discord.py>=2.5,<3'
COPY bot.py .
USER 10001:10001
CMD ["python", "bot.py"]

