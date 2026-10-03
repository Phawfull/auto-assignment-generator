from pathlib import Path


ROOT = Path(__file__).resolve().parent


MODEL = "gpt-4.1"


SUBJECT = "APP — Advanced Programming Practice"


JDBC_VERSION = "9.4.0"


JDBC_URL = (
    "https://repo.maven.apache.org/maven2/com/mysql/mysql-connector-j/"
    f"{JDBC_VERSION}/mysql-connector-j-{JDBC_VERSION}.jar"
)


class Cancelled(Exception):
    pass


def check_cancel(event):
    if event.is_set():
        raise Cancelled("Stopped. Completed work is saved in the output folder.")
