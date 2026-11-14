from typing import Any

from fastapi import APIRouter

from homer_sim.deps import Authed, Sim
from homer_sim.errors import COLD_CACHE, ApiError

router = APIRouter(prefix="/v1", dependencies=[Authed])


@router.get("/people:searchContacts")
def search_contacts(sim: Sim, query: str, readMask: str = "", pageSize: int = 10) -> dict[str, Any]:
    sim.people_queries.append(query)
    if not query:
        return {}
    if sim.people_cold:
        sim.people_cold -= 1
        raise ApiError(400, COLD_CACHE, "FAILED_PRECONDITION")
    results = [
        {
            "person": {
                "resourceName": f"people/{contact['id']}",
                "names": [
                    {
                        "displayName": f"{contact['given']} {contact['family']}",
                        "givenName": contact["given"],
                        "familyName": contact["family"],
                    }
                ],
                "emailAddresses": [{"value": contact["email"]}],
            }
        }
        for contact in sim.search_contacts(query)[:pageSize]
    ]
    return {"results": results} if results else {}
