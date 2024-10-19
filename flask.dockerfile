# Use an official Python runtime as a parent image
FROM python:3.11-slim

#update pip
RUN python -m pip install --upgrade pip

# Set the working directory in the container
WORKDIR /app

# Copy requirements file
COPY requirements.txt requirements.txt
COPY server/gunicorn.conf gunicorn.conf

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Wll not Copy the app code, but will set volumes on docker-compose.yaml
#COPY fwww /app/fwww

# Expose the port that Gunicorn will run on
EXPOSE 8001

# Set environment variables for Flask
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Set the working directory in the container to fwww
WORKDIR /app/fwww

# Command to run the application with Gunicorn
CMD ["gunicorn", "-c", "/app/gunicorn.conf", "wsgi:app"]
