#!/bin/bash
# Entrypoint script to set up cookies from environment variable

# If YT_DLP_COOKIES env var is set, write it to a file
if [ -n "$YT_DLP_COOKIES" ]; then
    echo "Setting up YouTube cookies..."
    echo "$YT_DLP_COOKIES" > /app/cookies.txt
    chmod 600 /app/cookies.txt
fi

# Start the application
exec uvicorn main:app --host 0.0.0.0 --port 8080
