import random
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="Voltora Core Management Engine",
    version="2.0.0",
    description="Backend API powering Rider Smart Swap, VIP Subscriptions, and Guest Pay-As-You-Go."
)

# Enable CORS so local HTML files (file://) can make fetch requests without browser blocks
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 1. DATA MODELS & SCHEMAS
# ==========================================

class SmartSwapRequest(BaseModel):
    rider_id: str
    current_lat: float
    current_lng: float
    returned_pack_id: str

class SlotBookingRequest(BaseModel):
    rider_id: str
    station: str
    door_slot: str
    scheduled_time: str
    action_type: str

class PlanChangeRequest(BaseModel):
    rider_id: str
    plan_name: str
    billing_cycle: Optional[str] = "monthly"

class GuestPaySwapRequest(BaseModel):
    rider_id: str
    station: str
    payment_amount_pkr: str
    returned_pack_id: str

# ==========================================
# 2. IN-MEMORY STATE & DATABASES
# ==========================================

STATIONS_DB = {
    "Saddar Empress Hub": {
        "lat": 24.8607, "lng": 67.0211,
        "doors": {
            "Door 01": {"status": "CHARGING", "pack_id": "VOLT-0101", "soc": 45.0},
            "Door 02": {"status": "READY", "pack_id": "VOLT-0512", "soc": 98.0},
            "Door 04": {"status": "RESERVED_VIP", "pack_id": "VOLT-0842", "soc": 100.0}
        }
    },
    "Clifton Block 2 Public Hub": {
        "lat": 24.8210, "lng": 67.0315,
        "doors": {
            "Door 01": {"status": "READY", "pack_id": "VOLT-0911", "soc": 100.0},
            "Door 02": {"status": "READY", "pack_id": "VOLT-0441", "soc": 99.5},
            "Door 03": {"status": "CHARGING", "pack_id": "VOLT-0202", "soc": 15.0}
        }
    }
}

SUBSCRIBERS_DB = {
    "RDR-9021": {
        "rider_name": "Tariq Mahmood",
        "tier": "SUBSCRIBED_VIP",
        "plan": "6-Month VIP Priority",
        "plan_status": "Active",
        "next_billing": "2027-03-15",
        "primary_station": "Saddar Empress Hub",
        "dedicated_door": "Door 04",
        "swaps_used_this_month": 28,
        "assigned_batteries": [
            {
                "pack_id": "VOLT-0199",
                "location": "ON BIKE (DISCHARGING)",
                "soc": 24.0, "soh": 94.5, "temp_c": 41.2, "cycles": 312
            },
            {
                "pack_id": "VOLT-0842",
                "location": "RESERVED IN LOCKER (Door 04)",
                "soc": 100.0, "soh": 98.2, "temp_c": 28.5, "cycles": 85
            },
            {
                "pack_id": "VOLT-0311",
                "location": "CHARGING @ HOME",
                "soc": 68.5, "soh": 92.0, "temp_c": 32.0, "cycles": 420
            }
        ]
    }
}

TRANSACTIONS_LOG = []
BOOKINGS_LOG = []

# ==========================================
# 3. API ENDPOINTS
# ==========================================

@app.get("/")
def health_check():
    return {
        "service": "Voltora Core Management Engine",
        "status": "ONLINE",
        "port": 8000,
        "timestamp": datetime.now().isoformat()
    }

# --- A. Smart Dispatch Endpoint (index.html) ---
@app.post("/api/rider/smart-swap")
async def request_smart_swap(req: SmartSwapRequest):
    """Processes instant swap requests for both VIP subscribers and guest riders."""
    is_vip = req.rider_id in SUBSCRIBERS_DB and SUBSCRIBERS_DB[req.rider_id]["tier"] == "SUBSCRIBED_VIP"

    if is_vip:
        sub = SUBSCRIBERS_DB[req.rider_id]
        station_name = sub["primary_station"]
        door = sub["dedicated_door"]
        released_pack = "VOLT-0842"
        routing_type = "VIP Dedicated Reserved Locker"
    else:
        station_name = "Clifton Block 2 Public Hub"
        door = "Door 02"
        released_pack = "VOLT-0441"
        routing_type = "Public Nearest Station"

    return {
        "status": "APPROVED",
        "rider_id": req.rider_id,
        "routing_type": routing_type,
        "assigned_station": station_name,
        "locker_slot": door,
        "released_pack_id": released_pack,
        "incoming_pack_logged": req.returned_pack_id,
        "unlock_token": f"VOLT-KEY-{random.randint(1000, 9999)}"
    }

# --- B. VIP Subscriber Portal Endpoints (subscribed.html) ---
@app.get("/api/subscriber/profile/{rider_id}")
async def get_subscriber_profile(rider_id: str):
    """Returns subscriber plan details, dedicated locker info, and multi-battery telemetry."""
    if rider_id not in SUBSCRIBERS_DB:
        raise HTTPException(status_code=404, detail="Subscriber profile not found")
    return {"status": "success", "data": SUBSCRIBERS_DB[rider_id]}

@app.post("/api/subscriber/book-slot")
async def book_charging_slot(booking: SlotBookingRequest):
    """Schedules an advance locker reservation for a subscriber."""
    booking_id = f"BK-{len(BOOKINGS_LOG) + 1001}"
    unlock_code = f"#{random.randint(1000, 9999)}"

    record = {
        "booking_id": booking_id,
        "rider_id": booking.rider_id,
        "station": booking.station,
        "door_slot": booking.door_slot,
        "scheduled_time": booking.scheduled_time,
        "action_type": booking.action_type,
        "unlock_code": unlock_code,
        "status": "CONFIRMED"
    }
    BOOKINGS_LOG.append(record)

    return {
        "status": "success",
        "message": f"Slot successfully reserved at {booking.station}",
        "booking": record
    }

@app.post("/api/subscriber/change-plan")
async def change_subscription_plan(req: PlanChangeRequest):
    """Updates subscriber plan (Weekly, Monthly, 6-Month VIP)."""
    if req.rider_id in SUBSCRIBERS_DB:
        SUBSCRIBERS_DB[req.rider_id]["plan"] = req.plan_name
        return {
            "status": "success",
            "message": f"Plan updated to {req.plan_name}",
            "current_plan": req.plan_name
        }
    raise HTTPException(status_code=404, detail="Subscriber not found")

# --- C. Guest Pay-As-You-Go Endpoint (guest.html) ---
@app.post("/api/guest/pay-and-swap")
async def guest_pay_and_swap(req: GuestPaySwapRequest):
    """Processes guest pay-per-swap payment, logs transaction, and unlocks door."""
    txn_id = f"TXN-{random.randint(100000, 999999)}"
    door_assigned = "Door 02" if "Clifton" in req.station else "Door 01"
    released_pack = "VOLT-0911" if "Clifton" in req.station else "VOLT-0512"

    txn_record = {
        "transaction_id": txn_id,
        "rider_id": req.rider_id,
        "station": req.station,
        "door_slot": door_assigned,
        "returned_pack_id": req.returned_pack_id,
        "released_pack_id": released_pack,
        "amount_paid_pkr": req.payment_amount_pkr,
        "timestamp": datetime.now().isoformat()
    }
    TRANSACTIONS_LOG.append(txn_record)

    return {
        "status": "success",
        "message": "Payment verified and public locker door unlocked",
        "transaction_id": txn_id,
        "station": req.station,
        "door_slot": door_assigned,
        "released_pack_id": released_pack,
        "amount_paid": req.payment_amount_pkr,
        "door_unlock_duration_seconds": 60
    }