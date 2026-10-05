"""One bounded run of another repo's program, for every check that runs one
(regen's rebuild, stores-exported's verify): its own session, so a timeout
kills the whole process tree it started, never only its first process."""
import os
import signal
import subprocess


class Timeout(Exception):
    """It did not finish in time; it and everything it started were killed."""


def bounded(argv, cwd, env, timeout):
    """(exit code, stdout, stderr). OSError when it cannot start; Timeout when
    it does not finish in `timeout` seconds."""
    p = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        raise Timeout(f"did not finish in {timeout}s")
    return p.returncode, out, err
