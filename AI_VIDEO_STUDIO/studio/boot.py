"""Stdlib-only bootstrap: re-exec a script under the studio venv and expose STUDIO_HOME."""
import os
import sys

STUDIO_HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV = os.environ.get("STUDIO_VENV", "/opt/ai_video_studio/venv")


def ensure_venv(script=None):
    py = os.path.join(VENV, "bin", "python")
    if os.path.realpath(sys.prefix) == os.path.realpath(VENV) or os.environ.get("STUDIO_NO_REEXEC"):
        return
    if not os.path.exists(py):
        sys.stderr.write(
            f"[studio] venv not found at {VENV}. Run AI_VIDEO_STUDIO/install.sh first "
            "(or set STUDIO_VENV).\n")
        sys.exit(3)
    env = dict(os.environ)
    env["PYTHONPATH"] = STUDIO_HOME + os.pathsep + env.get("PYTHONPATH", "")
    env["STUDIO_NO_REEXEC"] = "1"
    os.execve(py, [py] + ([script] if script else []) + sys.argv[1:], env)
