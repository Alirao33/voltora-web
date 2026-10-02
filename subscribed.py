from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

# --- Data Models for Subscriber Portal ---

class SlotBookingRequest(BaseModel):
    rider_id: str
    station: str
    door_slot: str
    scheduled_time: str
    action_type: str

class PlanChangeRequest(BaseModel):
    rider_id: str
    plan_name: str
    billing_cycle: str  # 'weekly', 'monthly', '6_months'

# --- Mock In-Memory Subscriber Database ---

SUBSCRIBERS_DB = {
    "RDR-9021": {
        "rider_name": "Tariq Mahmood",
        "plan": "6-Month VIP Priority",
        "plan_status": "Active",
        "next_billing": "2027-03-15",
        "primary_station": "Saddar Empress Hub",
        "dedicated_door": "Door 04",
        "swaps_used_this_month": 28,
        "swaps_limit": "Unlimited",
        "assigned_batteries": [
            {
                "pack_id": "VOLT-0199",
                "location": "ON BIKE (DISCHARGING)",
                "soc": 24.0,
                "soh": 94.5,
                "temp_c": 41.2,
                "cycles": 312,
                "max_cycles": 1500
            },
            {
                "pack_id": "VOLT-0842",
                "location": "RESERVED IN LOCKER (Door 04)",
                "soc": 100.0,
                "soh": 98.2,
                "temp_c": 28.5,
                "cycles": 85,
                "max_cycles": 1500
            },
            {
                "pack_id": "VOLT-0311",
                "location": "CHARGING @ HOME",
                "soc": 68.5,
                "soh": 92.0,
                "temp_c": 32.0,
                "cycles": 420,
                "max_cycles": 1500
            }
        ]
    }
}

BOOKINGS_DB = []

# --- Subscriber API Endpoints ---

@app.get("/api/subscriber/profile/{rider_id}")
async def get_subscriber_profile(rider_id: str):
    """Returns subscriber plan details, dedicated locker info, and multi-battery telemetry."""
    if rider_id not in SUBSCRIBERS_DB:
        raise HTTPException(status_code=404, detail="Subscriber profile not found")
    return {
        "status": "success",
        "data": SUBSCRIBERS_DB[rider_id]
    }

@app.post("/api/subscriber/book-slot")
async def book_charging_slot(booking: SlotBookingRequest):
    """Schedules an advance locker reservation for a subscriber."""
    booking_id = f"BK-{len(BOOKINGS_DB) + 1001}"
    unlock_code = f"#{hash(booking.rider_id + booking.scheduled_time) % 9000 + 1000}"
    
    record = {
        "booking_id": booking_id,
        "rider_id": booking.rider_id,
        "station": booking.station,
        "door_slot": booking.door_slot,
        "scheduled_time": booking.scheduled_time,
        "action_type": booking.action_type,
        "unlock_code": unlock_code,
        "reserved_at": datetime.now().isoformat(),
        "status": "CONFIRMED"
    }
    BOOKINGS_DB.append(record)
    
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
            "message": f"Plan updated to {req.plan_name} for rider {req.rider_id}",
            "current_plan": req.plan_name
        }
    raise HTTPException(status_code=404, detail="Rider not found")