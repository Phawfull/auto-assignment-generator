import base64
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.request
import uuid
import zipfile

from PIL import Image

from settings import ROOT, JDBC_VERSION, JDBC_URL, check_cancel


def java_tools():
    java, javac = shutil.which("java"), shutil.which("javac")
    if java and javac:
        return java, javac
    candidates = []
    if os.environ.get("JAVA_HOME"):
        candidates.append(Path(os.environ["JAVA_HOME"]))
    for base in [Path.home() / ".jdks", Path("C:/Program Files/Java")]:
        if base.exists():
            candidates.extend(sorted(base.iterdir(), reverse=True))
    for base in candidates:
        if (base / "bin/javac.exe").exists():
            return str(base / "bin/java.exe"), str(base / "bin/javac.exe")
    raise RuntimeError("A Java JDK is needed. Install JDK 17 or newer or set JAVA_HOME.")


def child_env(extra=None):
    permitted = {"systemroot", "windir", "path", "temp", "tmp", "userprofile", "home",
                 "appdata", "localappdata", "java_home", "display", "xauthority", "lang"}
    env = {}
    for name, value in os.environ.items():
        if name.lower() in permitted:
            env[name] = value
    env.update(extra or {})
    return env


def run_process(args, folder, cancel, timeout=60, env=None):
    check_cancel(cancel)
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with subprocess.Popen(args, cwd=folder, env=env or child_env(), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, creationflags=flags) as process:
        deadline = time.monotonic() + timeout
        while True:
            try:
                output, _ = process.communicate(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                if cancel.is_set() or time.monotonic() > deadline:
                    process.kill()
                    process.communicate()
                    check_cancel(cancel)
                    raise RuntimeError(f"Program timed out after {timeout} seconds.")
        check_cancel(cancel)
    text = output.decode("utf-8", errors="replace")
    if process.returncode:
        raise RuntimeError(text[-10000:] or f"Program exited with code {process.returncode}.")
    return text


def ensure_jdbc():
    folder = ROOT / "tools"
    folder.mkdir(exist_ok=True)
    target = folder / f"mysql-connector-j-{JDBC_VERSION}.jar"
    if target.exists() and zipfile.is_zipfile(target):
        return target
    with urllib.request.urlopen(JDBC_URL, timeout=60) as response:
        data = response.read(12_000_000)
    with urllib.request.urlopen(JDBC_URL + ".sha256", timeout=30) as response:
        digest = response.read().decode().split()[0]
    if hashlib.sha256(data).hexdigest() != digest:
        raise RuntimeError("The downloaded MySQL driver failed its checksum check.")
    temporary = target.with_suffix(".download")
    temporary.write_bytes(data)
    if not zipfile.is_zipfile(temporary):
        raise RuntimeError("The MySQL driver download is not a valid JAR file.")
    temporary.replace(target)
    return target


def encode(value):
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def db_environment(settings, database=""):
    host = settings["db_host"].strip()
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host):
        raise ValueError("Use a MySQL hostname or IPv4 address without a URL.")
    port = int(settings["db_port"])
    if not 1 <= port <= 65535:
        raise ValueError("MySQL port must be from 1 to 65535.")
    suffix = "?connectTimeout=5000&socketTimeout=15000&allowPublicKeyRetrieval=true"
    base = f"jdbc:mysql://{host}:{port}/"
    return {"DB_BASE": base + suffix, "DB_URL": base + database + suffix,
            "DB_NAME": database, "DB_USER": settings["db_user"], "DB_PASSWORD": settings["db_password"]}


def prepare_database(folder, settings, java, javac, cancel, jar, database=None):
    shutil.copyfile(ROOT / "java" / "TutorialDatabase.java", folder / "TutorialDatabase.java")
    cp = os.pathsep.join([str(folder), str(jar)])
    run_process([javac, "-encoding", "UTF-8", "TutorialDatabase.java"], folder, cancel)
    env = child_env(db_environment(settings, database or ""))
    result = run_process([java, "-cp", cp, "TutorialDatabase", "setup" if database else "check"],
                         folder, cancel, env=env)
    return env, result


def compile_and_run(solution, folder, settings, cancel, log):
    java, javac = java_tools()
    folder.mkdir(parents=True, exist_ok=True)
    for file in solution["files"]:
        (folder / file["name"]).write_text(file["code"], encoding="utf-8")
    shutil.copyfile(ROOT / "java" / "TutorialRunner.java", folder / "TutorialRunner.java")
    (folder / "stdin.txt").write_text(solution["stdin"], encoding="utf-8")
    steps = []
    for step in solution["steps"]:
        fields = [step["action"], encode(step["target"]), encode(step["value"])]
        steps.append("\t".join(fields))
    (folder / "steps.tsv").write_text("\n".join(steps), encoding="utf-8")
    env = child_env()
    cp = str(folder)
    if solution["sql"]:
        log("Preparing a separate MySQL demonstration database…")
        jar = ensure_jdbc()
        database = "tutorial_" + uuid.uuid4().hex[:16]
        (folder / "setup.sql").write_text(";\n\n".join(s.rstrip("; \n") for s in solution["sql"]) + ";\n", encoding="utf-8")
        (folder / "setup.b64").write_text("\n".join(encode(s) for s in solution["sql"]), encoding="utf-8")
        (folder / "database.txt").write_text(database, encoding="utf-8")
        env, _ = prepare_database(folder, settings, java, javac, cancel, jar, database)
        cp = os.pathsep.join([str(folder), str(jar)])
    log("Compiling Java…")
    run_process([javac, "-encoding", "UTF-8", "--release", "17", "-cp", cp,
                 *[f["name"] for f in solution["files"]], "TutorialRunner.java"], folder, cancel)
    log("Running example inputs and capturing output. Keep the desktop unlocked…")
    output = run_process([java, "-Dfile.encoding=UTF-8", "-cp", cp, "TutorialRunner",
                          solution["main_class"], solution["mode"]], folder, cancel, timeout=120, env=env)
    (folder / "verification.txt").write_text(output, encoding="utf-8")
    if "RUN_OK screenshots=" not in output:
        raise RuntimeError("The runner did not confirm completion.")
    shots = []
    for line in (folder / "screenshots/captions.tsv").read_text(encoding="utf-8").splitlines():
        filename, caption = line.split("\t")
        path = folder / "screenshots" / filename
        with Image.open(path) as picture:
            picture.verify()
        shots.append((path, base64.b64decode(caption).decode("utf-8")))
    return shots
