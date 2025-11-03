FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY backend /app
ENV HOST=0.0.0.0 PORT=5000 FLASK_DEBUG=true
EXPOSE 5000
CMD ["python", "app.py"]
