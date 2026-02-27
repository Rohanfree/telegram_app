# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies for tgcrypto and other packages
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Create the downloads directory
RUN mkdir -p downloads

# Set environment variables
ENV HOST=0.0.0.0
ENV PORT=8000
ENV RELOAD=false

# Expose the port the app runs on
EXPOSE 8000

# Run main.py when the container launches
CMD ["python", "main.py"]
