from typing import Any

from fastapi import APIRouter

from achilles_sim.deps import Authed, Sim

router = APIRouter(prefix="/v1", dependencies=[Authed])


@router.get("/people:searchContacts")
def search_contacts(sim: Sim, query: str, readMask: str = "", pageSize: int = 10) -> dict[str, Any]:
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
