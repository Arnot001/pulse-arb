#!/bin/bash

cd ~/Documents/pulse-arb || exit

echo "Starting Pulse Horses..."
echo "Open: http://127.0.0.1:8000/horses"

./.venv/Scripts/python.exe -m uvicorn app.main:app --reload