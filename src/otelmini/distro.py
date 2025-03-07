import os
import subprocess
import sys
from os.path import abspath, dirname


def auto_instrument():
    cmd = sys.argv[1:]

    filedir_path = dirname(abspath(__file__))
    auto_path = abspath(os.path.join(filedir_path, "auto"))

    # Modify PYTHONPATH to include the auto directory
    env = dict(os.environ)
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = auto_path + os.pathsep + env["PYTHONPATH"]
    else:
        env["PYTHONPATH"] = auto_path

    subprocess.run(cmd, env=env, check=False)
