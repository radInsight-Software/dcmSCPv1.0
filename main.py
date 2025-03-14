from fastapi import FastAPI, HTTPException,Response,Request 
from pydantic import BaseModel
import asyncio
import sys
from pathlib import Path
import io
from pydicom import dcmread
import os
import csv
import datetime
from fastapi.responses import FileResponse
from collections import deque
from dicomweb_client.api import DICOMwebClient

from pynetdicom import (
    AE, evt,
    StoragePresentationContexts,
    PYNETDICOM_IMPLEMENTATION_UID,
    PYNETDICOM_IMPLEMENTATION_VERSION
)


from pydicom.dataset import Dataset
from pydicom.uid import ImplicitVRLittleEndian
from pynetdicom.sop_class import (
    CTImageStorage,
    MRImageStorage,
    PositronEmissionTomographyImageStorage,
    RTStructureSetStorage,
    RTDoseStorage,
    XRayAngiographicImageStorage,
    UltrasoundImageStorage,
    NuclearMedicineImageStorage,
    Verification,
    RTPlanStorage,
    RTImageStorage
)
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# File to store configuration
CONFIG_FILE = "config.csv"


LOG_FILE_PATH = "templates/dicom_scp.log"  # Consider making this configurable

# FastAPI app
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace "*" with specific domains for better security
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# Global variables for the DICOM SCP server
ae = None
ae_task = None
ae_running = False
dicom_folder_path_global = ""
received_patients_global = ""
dicom_web_server_url_global = ""
storage_type = "fileSaving"

import datetime

def log_custom_event(message: str, log_file: str =LOG_FILE_PATH, level: str = "INFO"):
    """Logs a custom message to a specified log file with a timestamp in 'dd-MMM-yyyy h:mmAM/PM' format.

    Args:
        message (str): The message to log.
        log_file (str): The name of the log file. Default is 'dicom_scp.log'.
        level (str): The log level (e.g., INFO, WARNING, ERROR). Default is 'INFO'.
    """
    try:
        # Format timestamp as 'dd-MMM-yyyy h:mmAM/PM'
        timestamp = datetime.datetime.now().strftime("%d-%b-%Y %I:%M%p")
        log_entry = f"{timestamp} [{level}] {message}"
        with open(log_file, "a") as file:
            file.write(log_entry + "\n")
    except Exception as e:
        print(f"Failed to log message: {e}")


class ServerConfig(BaseModel):
    aeTitle: str
    port: int
    ipAddress: str
    dicomFolderPath: str
    dicomWebServer: str = ""
    fileSaving: bool

# Event handler for C-STORE
def handle_store(event):
    """Handle incoming C-STORE requests to save DICOM files."""
    global ae, ae_task, ae_running, storage_type, dicom_folder_path_global, dicom_web_server_url_global, received_patients_global

    try:
        # Get the dataset from the event
        dataset: Dataset = event.dataset
        context = event.context

        # Add the DICOM File Meta Information
        meta = Dataset()
        meta.MediaStorageSOPClassUID = dataset.SOPClassUID
        meta.MediaStorageSOPInstanceUID = dataset.SOPInstanceUID
        meta.ImplementationClassUID = PYNETDICOM_IMPLEMENTATION_UID
        meta.ImplementationVersionName = PYNETDICOM_IMPLEMENTATION_VERSION
        meta.TransferSyntaxUID = context.transfer_syntax

        # Ensure meta information is included when saving
        dataset.file_meta = meta

        # Set the transfer syntax attributes of the dataset
        dataset.is_little_endian = context.transfer_syntax.is_little_endian
        dataset.is_implicit_VR = context.transfer_syntax.is_implicit_VR

        # Extract PatientID
        patient_id = dataset.get("PatientID", "Unknown")

        # Log unique patient by ID only
        if patient_id != received_patients_global:
            log_custom_event(f"Receiving PatientID {patient_id}")
            received_patients_global = patient_id

        # Generate a filename based on SOPInstanceUID
        sop_instance_uid = dataset.SOPInstanceUID
        file_path = os.path.join(dicom_folder_path_global, f"{patient_id}", f"{sop_instance_uid}.dcm")         
        if storage_type == "fileSaving":
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            # Save the dataset locally
            dataset.save_as(file_path, write_like_original=False)
            #log_custom_event(f"Saved DICOM file for PatientID {patient_id}: {file_path}")

                   
            # Store in DICOMweb server if enabled
        if storage_type == "dicomWebServer":
            if not dicom_web_server_url_global:
                log_custom_event("DICOMweb server URL is not configured.")
                return 0xC000  # Processing Failure
            
            try:
                client = DICOMwebClient(url=dicom_web_server_url_global)

                # ✅ Convert dataset to byte stream
                dicom_bytes_io = io.BytesIO()
                dataset.save_as(dicom_bytes_io, write_like_original=False)
                dicom_bytes = dicom_bytes_io.getvalue()

                # Upload to DICOMweb
                client.store_instances([dicom_bytes])
                
                log_custom_event(f"Uploaded DICOM file for PatientID {patient_id} to DICOMweb Server")
            except Exception as e:
                log_custom_event(f"Error uploading file to DICOMweb Server for PatientID {patient_id}: {e}")
                return 0xC000  # Processing Failure

        # Return a success status
        return 0x0000  # Success Status Code

    except Exception as e:
        log_custom_event(f"Error processing C-STORE request for PatientID {patient_id}: {e}")
        return 0xC000  # Processing Failure Status Code

# Start the server
async def start_dicom_server(config: ServerConfig):
    global ae, ae_task, ae_running, storage_type, dicom_folder_path_global, dicom_web_server_url_global
    if ae_running:
        raise HTTPException(status_code=400, detail="DICOM server is already running.")

    dicom_folder_path_global = config.dicomFolderPath
    
    
    try:
         
        ae = AE(ae_title=config.aeTitle)
        ae.supported_contexts = StoragePresentationContexts
         
        ae.add_supported_context(Verification)
        # Add requested presentation contexts for all SOP classes
        ae.add_requested_context(PositronEmissionTomographyImageStorage)
        ae.add_requested_context(RTStructureSetStorage)
        ae.add_requested_context(RTDoseStorage)
        ae.add_requested_context(XRayAngiographicImageStorage)
        ae.add_requested_context(UltrasoundImageStorage)
        ae.add_requested_context(NuclearMedicineImageStorage)
        ae.add_requested_context(CTImageStorage)
        ae.add_requested_context(MRImageStorage)
        ae.add_requested_context(Verification)  # For testing connectivity
        
        # Set up base directory for received DICOM files
        if config.dicomFolderPath :
            os.makedirs(config.dicomFolderPath, exist_ok=True)
        

        

        ae_task = asyncio.create_task(
            asyncio.to_thread(ae.start_server, (config.ipAddress, config.port), evt_handlers=[(evt.EVT_C_STORE, handle_store)])            
        )    
            
        storage_type = "fileSaving" if config.fileSaving else "dicomWebServer"
        dicom_folder_path_global = config.dicomFolderPath if config.fileSaving else ""
        dicom_web_server_url_global = config.dicomWebServer if not config.fileSaving else ""
        ae_running = True          
        log_custom_event(f"DICOM SCP server started..")
    except Exception as e:
        log_custom_event(f"Failed to start DICOM SCP server: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start DICOM SCP server: {e}")

# Stop the server
async def stop_dicom_server():
    global ae, ae_task, ae_running
    if not ae_running:
        raise HTTPException(status_code=400, detail="DICOM server is not running.")

    try:
        ae.shutdown()
        if ae_task:
            await ae_task
        ae = None
        ae_task = None
        ae_running = False
        log_custom_event("DICOM SCP server stopped successfully.")
    except Exception as e:
        log_custom_event(f"Failed to stop DICOM SCP server: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop DICOM SCP server: {e}")

# API Endpoints
@app.post("/start")
async def start_server(config: ServerConfig):
    """Start the DICOM SCP server."""
    await start_dicom_server(config)
    return {"message": f"DICOM SCP server started with AE Title '{config.aeTitle}' on port {config.port}, IP Address '{config.ipAddress}', and DICOM Folder Path '{config.dicomFolderPath}'."}

@app.post("/stop")
async def stop_server():
    """Stop the DICOM SCP server."""
    await stop_dicom_server()
    return {"message": "DICOM SCP server stopped successfully."}

@app.get("/status")
async def server_status():
    """Get the status of the DICOM SCP server."""
    return {"running": ae_running}

 
@app.post("/save-config")
async def save_config(config: ServerConfig):
    """
    Save the server configuration to a CSV file.
    Validates fields based on the selected storage type (File Saving or DICOM Web Server).
    """
     
    try:
        # Validation based on selected storage type
        if config.fileSaving:
            if not config.dicomFolderPath:
                raise HTTPException(status_code=400, detail="DICOM Folder Path is required for File Saving mode.")
        else:
            if not config.dicomWebServer:
                raise HTTPException(status_code=400, detail="DICOM Web Server URL is required for DICOM Web Server mode.")

        # Save configuration to CSV file
        with open(CONFIG_FILE, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["AE Title", "Port", "IP Address", "File Saving", "DICOM Folder Path", "DICOM Web Server"])
            writer.writerow([
                config.aeTitle,
                config.port,
                config.ipAddress,
                config.fileSaving,
                config.dicomFolderPath or "",
                config.dicomWebServer or ""
            ])
       # log_event("Configuration saved successfully.")
        return {"message": "Configuration saved successfully."}

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        #log_event(f"Failed to save configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save configuration: {e}")


 
@app.get("/load-config")
async def load_config():
    try:
        with open(CONFIG_FILE, "r") as file:
            reader = csv.DictReader(file)
            data = next(reader, {})            
            return {
                "aeTitle": data.get("AE Title", ""),
                "port": int(data.get("Port", 0)),
                "ipAddress": data.get("IP Address", ""),
                "fileSaving": data.get("File Saving", "True") == "True",
                "dicomFolderPath": data.get("DICOM Folder Path", ""),
                "dicomWebServer": data.get("DICOM Web Server", "")
            }
    except FileNotFoundError:
        return {"message": "Configuration file not found."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load configuration: {e}")

@app.get("/logs")
async def get_logs():
    """Fetch the last 100 lines from the server logs. Create the file if it doesn't exist."""
    try:
        # Ensure the directory exists before creating the file
        os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)

        # Create the log file if it doesn't exist
        if not os.path.exists(LOG_FILE_PATH):
            with open(LOG_FILE_PATH, "w") as file:
                file.write("")  # Create an empty file
            return {"logs": ["No logs available. File created."]}

        # Read last 100 lines efficiently
        logs = deque(maxlen=100)
        with open(LOG_FILE_PATH, "r") as file:
            for line in file:
                logs.append(line.strip())  # Remove newlines for cleaner output
        
        return {"logs": list(logs)}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading logs: {str(e)}")
    
# Mount the static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

# Route specifically for serving favicon (PNG)
@app.get("/favicon.png", include_in_schema=False)
async def favicon():
    return FileResponse("static/logo.png")

#------------------------Add Export Files
class DICOMRequest(BaseModel):
    dicom_data: bytes
    dicom_server_ip: str
    dicom_server_port: int
    dicom_server_ae_title: str

@app.post("/upload")
async def upload_dicom(request: Request):
    # Parse the JSON payload
    body = await request.json()
    dicom_data = body["dicom_data"]
    dicom_server_ip = body["dicom_server_ip"]
    dicom_server_port = int(body["dicom_server_port"])
    dicom_server_ae_title = body["dicom_server_ae_title"]

   # print(dicom_server_ip, dicom_server_ae_title, dicom_server_port)
    # Load the DICOM data
    dicom_file_like = io.BytesIO(bytes(dicom_data))
    dataset = dcmread(dicom_file_like)

    # Create an Application Entity (AE) for communication
    ae = AE()

    # Add requested presentation contexts
    ae.add_requested_context(CTImageStorage, transfer_syntax=ImplicitVRLittleEndian)
    ae.add_requested_context(MRImageStorage, transfer_syntax=ImplicitVRLittleEndian)
    ae.add_requested_context(RTStructureSetStorage, transfer_syntax=ImplicitVRLittleEndian)
    ae.add_requested_context(RTPlanStorage, transfer_syntax=ImplicitVRLittleEndian)
    ae.add_requested_context(RTImageStorage, transfer_syntax=ImplicitVRLittleEndian)

    # Associate with the DICOM server
    assoc = ae.associate(dicom_server_ip, dicom_server_port, ae_title=dicom_server_ae_title)

    if assoc.is_established:
        status = assoc.send_c_store(dataset)
        if status.Status == 0x0000:
            assoc.release()
            log_custom_event(f"DICOM file successfully sent to the DICOM server")
            return Response(content="DICOM file successfully sent to the DICOM server", status_code=200)
        else:
            assoc.release()
            log_custom_event(f"Failed to send DICOM file. Status: {status.Status}")
            return Response(content=f"Failed to send DICOM file. Status: {status.Status}", status_code=500)
          
        
    else:
        log_custom_event(f"Failed to establish association with the DICOM server")
        return Response(content="Failed to establish association with the DICOM server", status_code=500)
         

app.mount("/static", StaticFiles(directory="."), name="static")
# Determine the root directory of the application
if getattr(sys, 'frozen', False):  # If the app is frozen with PyInstaller
    ROOT_DIR = Path(sys.executable).parent
else:  # When running as a script
    ROOT_DIR = Path(__file__).parent

# Mount the templates directory to serve HTML files directly
app.mount("/templates", StaticFiles(directory=ROOT_DIR / "templates"), name="templates")
   
@app.get("/", response_class=HTMLResponse)
async def home():
   try:
        #print(ROOT_DIR / "templates" / "index.html")
        with open(ROOT_DIR / "templates" / "index.html", "r", encoding="utf-8") as f:
            content = f.read()
            #print(content)  # DEBUG: Print HTML content
            return HTMLResponse(content=content)
   except FileNotFoundError:
        return HTMLResponse(content="<h1>Index file not found!</h1>", status_code=404)
   except Exception as e:
        return HTMLResponse(content=f"<h1>Error loading the page: {e}</h1>", status_code=500)


#uvicorn main:app --host 192.168.184.205 --port 4000 --reload