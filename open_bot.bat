@echo off
title Pulse IQ Server

cd /d C:\Users\lenno\Desktop\my-uk-eu-arb-api

echo.
echo ======================================
echo        PULSE IQ STARTING...
echo ======================================
echo.
echo Opening Pulse IQ in your browser...
echo.

start http://127.0.0.1:8000/horses

echo Starting server...
echo Leave this window open while using Pulse.
echo.

py -m uvicorn app.main:app --reload

echo.
echo Pulse stopped or crashed.
close