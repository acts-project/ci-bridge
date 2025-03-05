import nox

nox.options.default_venv_backend = "uv"


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
