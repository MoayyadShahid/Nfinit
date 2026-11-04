"""Read the hand-written demo builds in ``demos/designs/*.cad``.

A design file is plain build123d code with comment markers. It describes one
demo as an ordered list of steps; every step adds code, and the code of step
N is the complete script made of steps 1 to N. So each version that the
studio shows is a real, runnable script, like a point on a CAD timeline.

    # title: 5-inch FPV drone frame
    # summary: One sentence for the demo card.
    # part: frame

    # == step
    # prompt: The request that the chat shows for this step.
    # plan: First line of the reply.
    # plan: More lines of the reply.
    # -- params
    plate_thickness = 5.0
    # -- build
        Box(10, 10, plate_thickness)
    # -- extra
    with BuildPart() as top_plate:
        ...
    # -- result
    result = Compound([frame.part, top_plate.part])

``params`` lines go at the top of the script, ``build`` lines go inside
``with BuildPart() as <part>:`` (write them indented by four spaces),
``extra`` lines go after that block, and the last ``result`` section wins.
Without one, the script ends with ``result = <part>.part``.
"""

from dataclasses import dataclass, field
from pathlib import Path

DESIGNS = Path(__file__).with_name("designs")
SECTIONS = ("params", "build", "extra", "result")


@dataclass
class Step:
    prompt: str = ""
    plan: list[str] = field(default_factory=list)
    sections: dict[str, list[str]] = field(
        default_factory=lambda: {name: [] for name in SECTIONS}
    )


@dataclass
class Design:
    slug: str
    title: str
    summary: str
    part: str
    steps: list[Step]

    def code(self, step: int) -> str:
        """The complete script of this design after ``step`` steps (1-based)."""
        if not 1 <= step <= len(self.steps):
            raise ValueError(f"{self.slug} has no step {step}.")
        chosen = self.steps[:step]

        def joined(name: str) -> list[str]:
            blocks = ["\n".join(s.sections[name]).strip("\n") for s in chosen]
            return [block for block in blocks if block.strip()]

        result = next(
            (
                "\n".join(s.sections["result"]).strip()
                for s in reversed(chosen)
                if any(line.strip() for line in s.sections["result"])
            ),
            f"result = {self.part}.part",
        )
        parts = []
        params = joined("params")
        if params:
            parts.append("\n\n".join(params))
        build = joined("build")
        if build:
            parts.append(f"with BuildPart() as {self.part}:\n" + "\n\n".join(build))
        parts.extend(joined("extra"))
        parts.append(result)
        return "\n\n".join(parts) + "\n"

    def plan(self, step: int) -> str:
        return "\n".join(self.steps[step - 1].plan).strip()


def _header(line: str, key: str) -> str | None:
    prefix = f"# {key}:"
    return line[len(prefix):].strip() if line.startswith(prefix) else None


def parse_design(path: Path) -> Design:
    meta: dict[str, str] = {}
    steps: list[Step] = []
    section: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if line == "# == step":
            steps.append(Step())
            section = None
            continue
        if not steps:
            for key in ("title", "summary", "part"):
                value = _header(line, key)
                if value is not None:
                    meta[key] = value
            continue
        step = steps[-1]
        if line.startswith("# -- "):
            name = line[5:].strip()
            if name not in SECTIONS:
                raise ValueError(f"{path.name}: unknown section '{name}'.")
            section = name
            continue
        if section is None:
            prompt = _header(line, "prompt")
            plan = _header(line, "plan")
            if prompt is not None:
                step.prompt = f"{step.prompt} {prompt}".strip()
            elif plan is not None:
                step.plan.append(plan)
            elif line.strip():
                raise ValueError(f"{path.name}: unexpected line before a section: {line}")
            continue
        step.sections[section].append(line)

    missing = [key for key in ("title", "summary", "part") if not meta.get(key)]
    if missing:
        raise ValueError(f"{path.name}: missing {', '.join(missing)}.")
    if not steps:
        raise ValueError(f"{path.name}: no steps.")
    for number, step in enumerate(steps, start=1):
        if not step.prompt or not step.plan:
            raise ValueError(f"{path.name}: step {number} needs a prompt and a plan.")
    return Design(path.name.removesuffix(".cad"), meta["title"], meta["summary"], meta["part"], steps)


def load_designs(order: list[str]) -> list[Design]:
    return [parse_design(DESIGNS / f"{slug}.cad") for slug in order]
