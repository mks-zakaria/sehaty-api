"""Turning one doctor's booking engine on and off from the console.

The switch thrown at the cabinet, in the fifteen minutes the pack is being sold.
"On" is the whole of what activation means there — it starts the free trial for a
doctor who has never subscribed, which is every doctor being sold their first
pack — and "off" is for the cabinet that takes walk-ins only or whose secretary
is away.

Deliberately not part of the billing router: this is not a payment, and the two
must not be confused at either end. Cancelling a subscription to remove a booking
button misstates the books; taking a payment to restore one that staff switched
off by hand changes nothing the doctor can see.

Body of each handler: parse -> ONE controller call -> return.
"""

from fastapi import APIRouter, Depends
from sehaty.core.services.entitlement import Entitlement, entitlement_for, set_booking
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.booking_admin import BookingToggleIn

router = APIRouter(prefix="/api/v1/admin/doctors", tags=["booking"])

_require_admin = require_roles(UserRole.ADMIN)


@router.get("/{doctor_id}/booking", response_model=Entitlement)
def get_booking(doctor_id: int, _admin: User = Depends(_require_admin)) -> Entitlement:
    """Whether this doctor's agenda is open, and what decides it.

    `reason` carries the cause — "no_subscription", "expired", "past_due",
    "switched_off", "cancelled", "active" — and `manually_disabled` separates the
    one case that is not about money, so the console can say "they don't want one"
    rather than putting the doctor on a collections list.
    """
    return entitlement_for(doctor_id)


@router.put("/{doctor_id}/booking", response_model=Entitlement)
def update_booking(
    doctor_id: int,
    body: BookingToggleIn,
    _admin: User = Depends(_require_admin),
) -> Entitlement:
    """Open or close the agenda.

    Returns the resulting entitlement rather than an acknowledgement, because
    switching on does not always mean booking is on: a doctor whose subscription
    expired months ago still has a closed agenda, and the operator standing in
    front of them needs to see that immediately rather than promise otherwise.
    """
    return set_booking(doctor_id, enabled=body.enabled)
