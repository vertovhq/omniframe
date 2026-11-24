# User scripts

Put a Python script in this folder, or in the folder set by `OMNIFRAME_SCRIPTS_DIR`
(default `~/.omniframe/scripts`), and the model can run it with the `run_script` tool.
No change to the OmniFrame server is needed.

`frame_stats.py` in this folder is an example.

## Ask the model to list or run them

- `run_script()` lists every script: its name, a one-line summary and an example of its arguments.
- `run_script(name="frame_stats", args={"project": "my-video", "images": ["renders/still.jpg"]})` runs one.

## Write a script

A script must follow this contract:

1. Name: `.py` file, name made of lowercase letters, digits and `_`, at most 40 characters.
   Anything else is ignored by the listing and refused when run.
2. Module docstring: the first line is a one-line summary. A line starting with `Args:`
   gives an example of the arguments as JSON.
3. It reads one argument: `sys.argv[1]`, the path of a JSON file holding the arguments.
4. It prints its result as one JSON object on the last line of stdout. Put any other output
   on stderr or earlier lines.
5. Optional: a result key `images` with a list of image paths. OmniFrame returns those images to
   the model as pictures, after the JSON.

```python
"""Count the frames in a folder.

Args: {"project": "my-video", "folder": "renders"}
"""

import json
import sys
from pathlib import Path

args = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
folder = Path(args["folder"])
count = len(list(folder.glob("*.jpg")))
print(json.dumps({"folder": str(folder), "jpg_count": count}))
```

## How a run works

- The script runs with the Python that runs OmniFrame, so `numpy` and `Pillow` are available.
  Other packages must be installed into that environment.
- The script runs with `python -P`. Python does not put the script's folder on the import
  path, so a script named `json.py` cannot shadow the standard library. Two scripts cannot
  import each other by plain name.
- `args.project` sets the working folder to that project's folder. Relative paths in the
  arguments and in `images` are resolved there. Without `project`, the folder is the output
  folder (`OMNIFRAME_OUTPUT_DIR`).
- Default timeout: 120 seconds. Set `timeout_s` from 1 to 3600. A script that runs longer is
  stopped, and the result has `timed_out: true`.
- A run longer than about 20 seconds returns a `job_id`. Poll it with `job_status`.
- A script that exits with an error, or prints no JSON, returns `ok: false` with the end
  of its stdout and stderr.
- If a name exists in both `scripts/` and `OMNIFRAME_SCRIPTS_DIR`, the one in `scripts/` runs and the other is ignored.
- Scripts run with your user rights and can read and write any file you can. Put only
  scripts you wrote, or have read, into these folders.
