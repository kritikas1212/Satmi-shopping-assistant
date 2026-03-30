FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN addgroup --system satmi && adduser --system --ingroup satmi satmi

COPY src ./src
COPY scripts ./scripts
COPY evaluations ./evaluations
COPY monitoring ./monitoring
COPY README.md ./README.md
COPY .env.example ./.env.example

RUN chown -R satmi:satmi /app

USER satmi

ENV PYTHONPATH=/app/src
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
	CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["uvicorn", "satmi_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
