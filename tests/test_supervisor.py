"""Exercise the notebook's tool bindings and real workflows without Groq."""

import json
import unittest
from contextlib import chdir
from pathlib import Path
from tempfile import TemporaryDirectory

from llama_index.core.base.llms.types import ChatMessage, ToolCallBlock
from llama_index.core.llms.mock import MockFunctionCallingLLM

from student_supervisor import create_supervisor, run_agent


REPO = Path(__file__).resolve().parents[1]
DAY = "2026-11-24"
DATE_RANGE = {"start_date": DAY, "end_date": DAY}
SUPERVISOR = {"ask_study_planner", "ask_timetable", "ask_course_materials"}
PLANNER = {"get_deadlines", "get_free_slots", "set_study_availability", "build_study_plan"}


def call(name, **arguments):
    return ChatMessage(role="assistant", blocks=[
        ToolCallBlock(tool_call_id=name, tool_name=name, tool_kwargs=arguments),
    ])


class SupervisorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        nb = json.loads((REPO / "study_planner.ipynb").read_text(encoding="utf-8"))
        cells = {cell["id"]: "".join(cell["source"]) for cell in nb["cells"]}
        self.enterContext(chdir(self.enterContext(TemporaryDirectory())))
        self.sample_path = Path("sample_week.json")
        self.sample_path.write_text(json.dumps({
            "assignments": [{"id": "lab", "task": "Lab", "due": DAY + "T20:00", "estimated_minutes": 90}],
            "free_slots": [{"start": DAY + "T17:00", "end": DAY + "T18:00"}],
        }), encoding="utf-8")
        Path("data").mkdir()
        Path("data/timetable.json").write_text(json.dumps([
            {"day": "Tuesday", "course": "OS", "session_type": "lecture",
             "start": "17:00", "end": "17:30", "row": 7},
        ]), encoding="utf-8")
        Path("course_materials").mkdir()
        Path("course_materials/states.md").write_text("Process states include ready and running.", encoding="utf-8")
        self.namespace = {}
        for cell in ("load-data", "planner-tools", "retrieval-tools", "system-prompt"):
            exec(cells[cell], self.namespace)
        self.events = []
        self.inputs = []

    def start(self, *steps):
        # Each step is one model decision. A None reply echoes this turn's real tool outputs.
        self.steps = list(steps)

        def respond(messages, tools, **kwargs):
            exposed = {tool.metadata.name for tool in tools}
            self.inputs.append((exposed, [m.content for m in messages if m.role == "user"]))
            expected, reply = self.steps.pop(0)
            self.assertEqual(exposed, expected)
            if isinstance(reply, Exception):
                raise reply
            if reply is not None:
                return reply
            last_user = max(i for i, message in enumerate(messages) if message.role == "user")
            evidence = [m.content or "No matches" for m in messages[last_user:] if m.role == "tool"]
            return ChatMessage(role="assistant", content="\n".join(evidence))

        tool_names = PLANNER | {"search_timetable", "search_course_materials"}
        self.agent = create_supervisor(
            MockFunctionCallingLLM(response_generator=respond, is_chat_model=True),
            **{name: self.namespace[name] for name in tool_names}, trace=self.trace,
        )
        self.history = []

    def trace(self, agent_name, event):
        self.events.append((agent_name, event.tool_name, event.tool_output))

    async def ask(self, question):
        return await run_agent(self.agent, question, history=self.history, trace=self.trace)

    async def test_timetable_and_follow_up(self):
        timetable = {"search_timetable"}
        self.start(
            (SUPERVISOR, call("ask_timetable", task="Find Tuesday's OS class")),
            (timetable, call("search_timetable", day="Tuesday", course="OS")),
            (timetable, None), (SUPERVISOR, None),
            (SUPERVISOR, call("ask_timetable", task="Find Wednesday's OS class")),
            (timetable, call("search_timetable", day="Wednesday", course="OS")),
            (timetable, None), (SUPERVISOR, None),
        )
        question = "When is OS on Tuesday?"
        self.assertIn("'row': 7", await self.ask(question))
        self.assertEqual(await self.ask("And Wednesday?"), "No matches")
        self.assertEqual(self.inputs[4][1], [question, "And Wednesday?"])
        self.assertEqual(self.inputs[5][1], ["Find Wednesday's OS class"])
        self.assertFalse(self.steps)

    async def test_course_and_plan_share_one_answer(self):
        course = {"search_course_materials"}
        self.start(
            (SUPERVISOR, call("ask_course_materials", task="Explain process states")),
            (course, call("search_course_materials", query="process states")), (course, None),
            (SUPERVISOR, call("ask_study_planner", task="Plan assignments for " + DAY)),
            (PLANNER, call("build_study_plan", **DATE_RANGE)), (PLANNER, None),
            (SUPERVISOR, None),
        )
        before = self.sample_path.read_bytes()
        answer = await self.ask("Explain process states and plan my work for " + DAY)
        for evidence in ("states.md", "'section': 'text'", "ready and running", "17:30", "'remaining_minutes': 60"):
            self.assertIn(evidence, answer)
        self.assertEqual(self.sample_path.read_bytes(), before)
        self.assertEqual([(agent, tool) for agent, tool, _ in self.events], [
            ("course_materials", "search_course_materials"), ("supervisor", "ask_course_materials"),
            ("study_planner", "build_study_plan"), ("supervisor", "ask_study_planner"),
        ])
        self.assertFalse(self.steps)

    async def test_explicit_save_then_plan(self):
        task = "Replace my windows on " + DAY + " with 18:00–19:30 and plan my assignments."
        self.start(
            (SUPERVISOR, call("ask_study_planner", task=task)),
            (PLANNER, call("set_study_availability", day=DAY, windows=[{"start": "18:00", "end": "19:30"}])),
            (PLANNER, call("build_study_plan", **DATE_RANGE)), (PLANNER, None), (SUPERVISOR, None),
        )
        answer = await self.ask(task)
        self.assertIn("'minutes': 90", answer)
        self.assertIn("'unfinished': []", answer)
        self.assertEqual(json.loads(self.sample_path.read_text())["free_slots"], [
            {"start": DAY + "T18:00", "end": DAY + "T19:30"},
        ])
        self.assertFalse(self.steps)

    async def test_specialist_failure_preserves_successful_lookup(self):
        self.start(
            (SUPERVISOR, call("ask_course_materials", task="Explain process states")),
            ({"search_course_materials"}, RuntimeError("Course lookup unavailable")),
            (SUPERVISOR, call("ask_study_planner", task="Find deadlines for " + DAY)),
            (PLANNER, call("get_deadlines", **DATE_RANGE)), (PLANNER, None), (SUPERVISOR, None),
        )
        answer = await self.ask("Explain process states and list my deadlines for " + DAY)
        self.assertIn("Course lookup unavailable", answer)
        self.assertIn("'task': 'Lab'", answer)
        self.assertTrue(self.events[0][2].is_error)
        self.assertFalse(self.steps)
