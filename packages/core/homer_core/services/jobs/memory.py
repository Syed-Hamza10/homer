from homer_core.agent.intents import Forget, Recall, Remember
from homer_core.services.facts import add_fact, forget, keywords, matching
from homer_core.services.jobs.turn import Turn


async def remember(turn: Turn, intent: Remember) -> None:
    fact = add_fact(turn.session, turn.user.id, intent.fact)
    turn.facts.append(fact.text)
    turn.note(fact_id=fact.id)
    turn.say(f"Saved to memory: {fact.text}")


async def drop(turn: Turn, intent: Forget) -> None:
    about = intent.about if keywords(intent.about) else turn.message
    fact = forget(turn.session, turn.user, about)
    if fact is None:
        turn.say("I have nothing saved like that, so there is nothing to forget.")
        return
    turn.facts[:] = [text for text in turn.facts if text != fact.text]
    turn.say(f"Forgot: {fact.text}")


async def recall(turn: Turn, intent: Recall) -> None:
    facts = matching(turn.session, turn.user, intent.about)
    who = f" about {intent.about}" if keywords(intent.about) else ""
    if not facts:
        turn.say(f"I have nothing saved{who}.")
        return
    listed = "\n".join(f"- {fact.text}" for fact in facts)
    turn.say(f"Here is what I have saved{who}:\n{listed}")
