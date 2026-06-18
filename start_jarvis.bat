@echo off
cd C:\Users\jacef\Jarvis
start "Jarvis Main" /min python main.py
start "Jarvis Memory" /min python memory_server.py
timeout /t 3
start "" "http://localhost:8080/"
