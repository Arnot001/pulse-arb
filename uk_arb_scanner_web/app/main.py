from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from app.core.scanner import run_scan


app = FastAPI()