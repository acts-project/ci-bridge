import nox

nox.options.default_venv_backend = "uv"


@nox.session
def pre_commit(session: nox.Session):
    """Run pre-commit hooks."""
    session.run("uv", "run", "--frozen", "pre-commit", "run", "--all-files")


@nox.session
@nox.parametrize("python", ["3.11", "3.12", "3.13"])
def tests(session: nox.Session):
    session.run(
        "uv",
        "run",
        "--frozen",
        "--python",
        session.bin + "/python",
        "--active",
        "pytest",
    )
