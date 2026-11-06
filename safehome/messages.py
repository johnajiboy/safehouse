"""Messages to tenants.

Safety messages for emergencies use fixed, pre-approved wording and are sent at
once, because waiting for approval could put someone at risk. Every other message
is a draft that an officer must approve before it is sent.

This version records messages in the database only. Connecting a real text or
email service is left for deployment.
"""
from __future__ import annotations

from .hazards import EMERGENCY
from .models import Case

ALWAYS = "If anyone is in immediate danger, call 999."

SAFETY_TEMPLATES = {
    "Fire and explosions": (
        "We have received your report about a possible gas leak at {address}. "
        "Please call the National Gas Emergency Service on 0800 111 999 now if you have not already. "
        "If you feel unsafe, leave the property. " + ALWAYS + " An officer will contact you today."
    ),
    "Electrical hazards": (
        "We have received your report about an electrical problem at {address}. "
        "Please do not touch the socket, switch or wires. If it is safe to do so, switch off the power "
        "at the fuse box. " + ALWAYS + " An officer will contact you today."
    ),
    "Structural collapse": (
        "We have received your report about damage at {address}. "
        "Please keep everyone away from the damaged area. " + ALWAYS + " An officer will contact you today."
    ),
}
DEFAULT_SAFETY = (
    "We have received your urgent report about {address}. " + ALWAYS + " An officer will contact you today."
)


def safety_message(case: Case) -> str | None:
    if case.level != EMERGENCY:
        return None
    template = SAFETY_TEMPLATES.get(case.hazard, DEFAULT_SAFETY)
    return template.format(address=case.address)


def visit_draft(case: Case) -> str:
    return (
        f"We have arranged an inspection at {case.address} today about the {case.hazard.lower()} "
        "you reported. Please reply if this time does not suit you."
    )


def booking_draft(case: Case, repairer_name: str) -> str:
    return (
        f"{repairer_name} has been booked to deal with the {case.hazard.lower()} at {case.address}. "
        "We will confirm the time with you."
    )


def written_summary_draft(case: Case) -> str:
    return (
        f"Written summary for {case.address}\n\n"
        f"Hazard investigated: {case.hazard}.\n"
        "What we found: [officer to complete]\n"
        "Action taken to make the home safe: [officer to complete]\n"
        "Further work planned and expected timescale: [officer to complete]\n\n"
        "If you have any questions, please contact your housing officer."
    )
