import re
from dataclasses import dataclass

from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage

from homer_core.agent.toolsets import DEFAULT_TOOLSET, TOOLSETS

COMMAND = re.compile(
    r"^/(brief|inbox|digest|slot|draft|followup|remind|approve|reject)\b\s*(.*)$", re.DOTALL
)
WORD = re.compile(r"[a-z+]+")

CLASSIFY_PROMPT = (
    "You pick which tools an assistant needs for a user message. "
    f"Answer with exactly one word from this list and nothing else: {', '.join(TOOLSETS)}. "
    "mail is email only; calendar is events and free slots; mail+calendar is both or unclear; "
    "search is the web; system is the current time or a reminder."
)


@dataclass(frozen=True)
class Command:
    name: str
    arg: str


def parse_command(message: str) -> Command | None:
    match = COMMAND.match(message.strip())
    if match is None:
        return None
    return Command(match.group(1), match.group(2).strip())


def build_classifier(model: Model) -> Agent[None, str]:
    return Agent(model, output_type=str, instructions=CLASSIFY_PROMPT)


def normalise(answer: str) -> str:
    words = WORD.findall(answer.lower())
    return next((word for word in words if word in TOOLSETS), DEFAULT_TOOLSET)


async def classify(classifier: Agent[None, str], message: str) -> tuple[str, RunUsage]:
    result = await classifier.run(message)
    return normalise(result.output), result.usage
