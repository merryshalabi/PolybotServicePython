FROM python:3.10-slim

# Create working directory
WORKDIR /app

# Copy only requirements first for caching benefits
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the full project
COPY . .

# Expose the port your Flask app runs on (optional but helpful)
EXPOSE 8000

# Run the Polybot Flask app
CMD ["python3", "polybot/app.py"]
