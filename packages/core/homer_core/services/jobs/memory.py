from homer_core.agent.intents import Forget, Remember
from homer_core.services.facts import add_fact, forget
from homer_core.services.jobs.turn import Turn


async def remember(turn: Turn, intent: Remember) -> None:
    fact = add_fact(turn.session, turn.user.id, intent.fact)
    turn.facts.append(fact.text)
    turn.note(fact_id=fact.id)
    turn.say(f"Saved to memory: {fact.text}")


async def drop(turn: Turn, intent: Forget) -> None:
    fact = forget(turn.session, turn.user, intent.about)
    if fact is None:
        turn.say("There is nothing like that in my memory.")
        return
    turn.facts[:] = [text for text in turn.facts if text != fact.text]
    turn.say(f"Forgotten: {fact.text}")
