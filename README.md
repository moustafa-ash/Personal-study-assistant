# Personal AI Assistant for Students

## Use Case

Ask about your university timetable, find information in your course notes, and plan study time around classes and assignment deadlines. For example, ask “When is my Machine Learning lecture?” or “Explain process states using my OS lectures.”

## LLM and Provider

The assistant uses `openai/gpt-oss-20b` through Groq's free API with LlamaIndex. It uses `SimpleKeywordTableIndex` to index course documents locally. Conversation messages, tool results, and retrieved excerpts can be sent to Groq when answering a request. The agent has a 180-second workflow timeout.

## Tools for the Agent

| Tool | Inputs | Output |
| --- | --- | --- |
| `get_deadlines` | Start and end dates | Assignments due in that range and their estimated minutes. |
| `get_free_slots` | Start and end dates | Merged availability windows. |
| `set_study_availability` | Date and list of start and end times | Saves a complete replacement for that date's windows. An empty list clears them. |
| `build_study_plan` | Start and end dates, optional daily limit | Study blocks that avoid classes and minutes that remain unscheduled. |
| `search_timetable` | Optional day, course, and session type | Matching weekly classes and timetable row references. |
| `search_course_materials` | Question | Up to four keyword-matched excerpts with source references. |

Dates use `YYYY-MM-DD`. Availability uses same-day `HH:MM` start and end times in Africa/Cairo time. Study planning uses a 120-minute daily limit unless another limit is requested. It schedules assignments whose deadlines fall within the requested date range, earliest deadline first.

## Supervisor and specialists

The notebook sends each message to a LlamaIndex supervisor. It keeps the conversation history, gives each specialist a self-contained task, and combines their results into one reply. The prompts and agent definitions live in [student_supervisor.py](student_supervisor.py).

| Specialist | Tools | Result returned to the supervisor |
| --- | --- | --- |
| Study planner | `get_deadlines`, `get_free_slots`, `set_study_availability`, `build_study_plan` | Deadlines, saved windows, confirmed updates, or class-aware study blocks and unfinished minutes. |
| Timetable | `search_timetable` | Weekly class details with timetable row references. |
| Course materials | `search_course_materials` | An answer grounded in lecture excerpts with filenames and page or section references. |

For example, “Explain process states using my OS lectures, then plan my assignment work for 2026-11-24 using my saved availability” calls the course materials and study planning specialists. Only an explicit request to replace or clear availability changes the saved windows. The notebook trace labels each tool result with the agent that called it.

## Implemented Features

- Weekly timetable lookup and study planning that removes class hours from available windows.
- Study availability entered through chat and saved in [sample_week.json](sample_week.json).
- Course Q&A grounded in selectable-text PDFs, Markdown, and text files, with filename and page or section references.
- Conversation context and tool-call output in the notebook.

The `course_materials/` folder contains Operating Systems lecture PDFs. Store your private weekly schedule in `data/timetable.json`, using [timetable.example.json](data/timetable.example.json) as a starting point. The file is ignored by Git. When it is absent, the assistant starts with an empty timetable. `sample_week.json` contains example assignments and windows that you can edit for your own dates.

### Run Locally

1. Open PowerShell in the project folder and install the dependencies. Skip the first command if `.venv` already exists.

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirement.txt
   ```

2. If `.env` is missing, copy `.env.example` to `.env`. Add your Groq key as `GROQ_API_KEY=your_key`.
3. Start the notebook and run its cells in order.

   ```powershell
   .\.venv\Scripts\python.exe -m jupyterlab study_planner.ipynb
   ```

4. Add supported files to `course_materials/` and rerun the **Timetable and course materials** cell to rebuild the index. Edit `sample_week.json` for assignment deadlines, or tell the assistant your availability. When changing a date's availability, provide every window you want to keep for that date.

The **Check the example** cell verifies the supplied sample data. Skip it if you have changed the sample windows. PDFs need selectable text. Keyword retrieval can miss relevant passages when a question uses different wording, so check the cited sources.

Run the offline orchestration tests from the project directory with `.\.venv\Scripts\python.exe -m unittest discover -s tests`. The tests use a scripted model and temporary study data.

## Future Work

- OCR for scanned course notes.
- Semantic retrieval for questions that use different wording from the notes.
- One-off timetable changes such as class cancellations.
