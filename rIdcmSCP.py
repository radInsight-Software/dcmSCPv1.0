import os
import sys
import uvicorn
import fastapi  # Ensures FastAPI is bundled
import importlib
import fastapi.staticfiles  # Ensures static files are bundled
import fastapi.middleware  # Ensures middleware is bundled
import fastapi.templating  # Ensures templates are bundled
import fastapi.responses  # Ensures response handling is included
import logging
from logging.config import dictConfig
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware  # Ensure middleware is included
from license_validator import LicenseValidator




app = FastAPI()
# Middleware Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import ctypes

def protect_memory():
    try:
        ctypes.windll.kernel32.SetProcessDEPPolicy(1)  # Enable DEP (Data Execution Prevention)
        ctypes.windll.ntdll.NtSetInformationProcess(
            ctypes.windll.kernel32.GetCurrentProcess(), 29, ctypes.byref(ctypes.c_int(1)), 4
        )
    except Exception:
        pass

protect_memory()

def is_debugger_attached():
    try:
        return ctypes.windll.kernel32.IsDebuggerPresent()
    except Exception:
        return False

if is_debugger_attached():
    print("Debugger detected! Exiting...")
    sys.exit(1)

# Ensure 'static/' and 'templates/' exist
if not os.path.exists("static"):
    os.makedirs("static")
if not os.path.exists("templates"):
    os.makedirs("templates")

# Mount Static Files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Logging Configuration
log_file = "app.log"
if not os.path.exists(log_file):
    open(log_file, 'w').close()

custom_log_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(levelname)s - %(message)s",
        },
    },
    "handlers": {
        "file": {
            "class": "logging.FileHandler",
            "formatter": "default",
            "filename": log_file,
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["file"],
    },
    "loggers": {
        "uvicorn": {
            "level": "INFO",
            "handlers": ["file"],
            "propagate": False,
        },
        "uvicorn.error": {
            "level": "ERROR",
            "handlers": ["file"],
            "propagate": False,
        },
        "uvicorn.access": {
            "level": "INFO",
            "handlers": ["file"],
            "propagate": False,
        },
    },
}

dictConfig(custom_log_config)

# Ensure Python loads the compiled module
sys.path.append(".")

main_encrypted = importlib.import_module("main_protected")  # Import compiled module

app = main_encrypted.app  # Use the FastAPI app from the compiled module

if __name__ == "__main__":

    logging.info("Starting FastAPI app...")
    software_name = "ProductA"  # Change as needed
    validator = LicenseValidator(software_name)
    is_valid = validator.validate_license()

    if is_valid:
        print("🎉 Software is licensed and valid!")
        logging.info("Software is licensed and valid!")

    else:
        print("🚨 Software license is invalid or expired!")
        logging.info("Software license is invalid or expired!")
        sys.exit(1)

    if getattr(sys, 'frozen', False):  # PyInstaller bundle detection
        BASE_DIR = sys._MEIPASS
        sys.path.insert(0, BASE_DIR)
        app_module = "main_protected"
    else:
        BASE_DIR = os.path.abspath(".")
        app_module = "main_protected"

    logging.info(f"Using ASGI app module: {app_module}")

    uvicorn.run(
        f"{app_module}:app",
        host="0.0.0.0",
        port=4000,
        log_level="info",
        log_config=custom_log_config,
    )



#taskkill /f /im dcmscp.exe
##pyinstaller --onefile  --noconsole --add-data=templates:templates --hidden-import=main --hidden-import=uvicorn --hidden-import=fastapi run_app.py

# .\myenv\Scripts\Activate 
#pyinstaller --onefile --noconsole  --icon=logo.ico --add-data "main_encrypted.pyd;." --add-data "templates/*;templates" --add-data "static/*;static" --add-data "dist/protected_main/pyarmor_runtime_000000;pyarmor_runtime_000000" --hidden-import=pyarmor_runtime  --hidden-import=fastapi.middleware --hidden-import=fastapi.templating --hidden-import=uvicorn --hidden-import=pydicom --hidden-import=pynetdicom --hidden-import=fastapi.staticfiles --hidden-import=fastapi --hidden-import=starlette ridcmscp.py

##without pymour
#pyinstaller --onefile --noconsole  --icon=logo.ico --add-data "main_protected.pyd;." --add-data "templates/*;templates" --add-data "static/*;static" --hidden-import=fastapi.middleware --hidden-import=fastapi.templating --hidden-import=uvicorn --hidden-import=pydicom --hidden-import=pynetdicom --hidden-import=dicomweb_client --hidden-import=fastapi.staticfiles --hidden-import=fastapi --hidden-import=starlette ridcmscp.py