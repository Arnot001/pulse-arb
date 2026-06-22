@echo off
cd /d C:\Users\lenno\Desktop\my-uk-eu-arb-api

py -m uvicorn app.main:app --reload

pause