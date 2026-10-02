import asyncio
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="Voltora IoT Telemetry Service",
    version="1.0.0",
    description="High-frequency telemetry ingestion, thermal safety monitoring, and stream broadcasting."
)

# Enable CORS for decoupled frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# In-Memory Telemetry Database
# -----------------------------------------------------------------------------
telemetry_db: Dict[str, dict] = {
    "PACK-001": {
        "pack_id": "PACK-001",
        "station_id": "STN-KHI-01",
        "soc": 92.0,
        "soh": 98.0,
        "temp_celsius": 34.2,
        "voltage": 51.2,
        "current": 2.1,
        "cycles": 140,
        "status": "NORMAL",
        "thermal_alert": False
    },
    "PACK-002": {
        "pack_id": "PACK-002",
        "station_id": "STN-KHI-01",
        "soc": 15.0,
        "soh": 91.0,
        "temp_celsius": 42.0,
        "voltage": 46.8,
        "current": 0.0,
        "cycles": 310,
        "status": "CHARGING",
        "thermal_alert": False
    },
    "PACK-003": {
        "pack_id": "PACK-003",
        "station_id": "STN-KHI-02",
        "soc": 88.0,
        "soh": 95.0,
        "temp_celsius": 58.5,
        "voltage": 50.8,
        "current": 0.0,
        "cycles": 180,
        "status": "MAINTENANCE_REQUIRED",
        "thermal_alert": True
    }
}

# Active WebSocket subscribers manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------
class TelemetryIngestPayload(BaseModel):
    pack_id: str = Field(..., example="PACK-001")
    station_id: Optional[str] = Field(None, example="STN-KHI-01")
    soc: float = Field(..., ge=0.0, le=100.0, description="State of Charge (%)")
    soh: float = Field(..., ge=0.0, le=100.0, description="State of Health (%)")
    temp_celsius: float = Field(..., description="Battery Temperature (°C)")
    voltage: float = Field(..., description="Pack Voltage (V)")
    current: float = Field(..., description="Charging/Discharging Current (A)")
    cycles: int = Field(..., ge=0, description="Lifetime charge cycles")

# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------

@app.get("/")
def health_check():
    return {
        "status": "online",
        "service": "IoT Telemetry Service",
        "port": 8001,
        "active_packs_monitored": len(telemetry_db)
    }

@app.get("/api/telemetry/live")
def get_all_telemetry():
    """Returns real-time operational metrics for all registered battery packs."""
    return {"status": "success", "count": len(telemetry_db), "data": list(telemetry_db.values())}

@app.get("/api/telemetry/{pack_id}")
def get_pack_telemetry(pack_id: str):
    """Retrieve telemetry state for a specific pack."""
    if pack_id not in telemetry_db:
        raise HTTPException(status_code=404, detail="Battery pack not found")
    return {"status": "success", "data": telemetry_db[pack_id]}

@app.post("/api/telemetry/ingest")
async def ingest_telemetry(payload: TelemetryIngestPayload):
    """
    High-frequency MQTT/HTTP ingestion endpoint.
    Automatically evaluates thermal safety (> 55°C triggers safety lock).
    """
    thermal_alert = payload.temp_celsius > 55.0
    status_flag = "MAINTENANCE_REQUIRED" if thermal_alert else "NORMAL"

    record = {
        "pack_id": payload.pack_id,
        "station_id": payload.station_id,
        "soc": payload.soc,
        "soh": payload.soh,
        "temp_celsius": payload.temp_celsius,
        "voltage": payload.voltage,
        "current": payload.current,
        "cycles": payload.cycles,
        "status": status_flag,
        "thermal_alert": thermal_alert
    }
    
    # Store state
    telemetry_db[payload.pack_id] = record

    # Broadcast updated telemetry state to connected WebSocket clients
    await manager.broadcast({
        "event": "TELEMETRY_UPDATE",
        "data": record
    })

    return {
        "status": "ingested",
        "thermal_alert": thermal_alert,
        "message": "Thermal lockout initiated!" if thermal_alert else "Telemetry updated successfully.",
        "data": record
    }

# -----------------------------------------------------------------------------
# Real-Time WebSocket Streaming Endpoint
# -----------------------------------------------------------------------------
@app.websocket("/ws/telemetry")
async def websocket_telemetry_stream(websocket: WebSocket):
    """
    WebSocket endpoint for frontends to subscribe to live battery telemetry feeds.
    """
    await manager.connect(websocket)
    try:
        # Push initial snapshot
        await websocket.send_json({
            "event": "INITIAL_SNAPSHOT",
            "data": list(telemetry_db.values())
        })
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)