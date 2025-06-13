# Use official Python 3.12 slim image
FROM python:3.12-slim

# Set working directory inside the container
WORKDIR /app

# Copy dependency files first for better Docker layer caching
COPY pyproject.toml ./

# Install dependencies
RUN pip install --no-cache-dir .

# Copy the application code
COPY app/ ./app/

# Expose the port the application will run on
EXPOSE 8000

# Command to run the application using uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]