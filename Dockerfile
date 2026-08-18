FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app.py .
COPY core/ core/
COPY api/ api/
COPY services/ services/
COPY schemas.py .
COPY templates/ templates/
COPY static/ static/

# Expose port
EXPOSE 5000

CMD ["python", "app.py"]
