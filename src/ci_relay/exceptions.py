class UnrecoverableError(ValueError):
    """Base class for all unrecoverable errors in the CI Bridge system."""

    pass


class SignatureMismatchError(UnrecoverableError):
    """Raised when a signature verification fails."""

    pass


class TeamOrgMismatchError(UnrecoverableError):
    """Raised when a team's organization doesn't match the expected organization."""

    pass


class IncompatibleJobUrlError(UnrecoverableError):
    """Raised when a job URL doesn't match the expected GitLab API URL format."""

    pass


class InvalidBuildError(UnrecoverableError):
    """Raised when an object expected to be a build is not."""

    pass


class MissingInstallationIdError(UnrecoverableError):
    """Raised when the installation_id is missing from the bridge payload."""

    pass
