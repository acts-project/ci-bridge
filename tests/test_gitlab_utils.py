from ci_relay.gitlab.utils import should_ignore_job


def test_should_ignore_job_no_patterns():
    """Test that jobs are not ignored when no patterns are provided"""
    assert should_ignore_job("test-job", []) is False
    assert should_ignore_job("build-job", []) is False
    assert should_ignore_job("deploy-job", []) is False


def test_should_ignore_job_simple_patterns():
    """Test simple string patterns"""
    patterns = ["test-.*", ".*-debug"]

    # Should be ignored
    assert should_ignore_job("test-unit", patterns) is True
    assert should_ignore_job("test-integration", patterns) is True
    assert should_ignore_job("build-debug", patterns) is True
    assert should_ignore_job("deploy-debug", patterns) is True

    # Should not be ignored
    assert should_ignore_job("build-production", patterns) is False
    assert should_ignore_job("deploy-staging", patterns) is False
    assert should_ignore_job("lint", patterns) is False


def test_should_ignore_job_complex_patterns():
    """Test more complex regex patterns"""
    patterns = ["manual-.*", ".*-manual", "^skip-.*", ".*-skip$"]

    # Should be ignored
    assert should_ignore_job("manual-deploy", patterns) is True
    assert should_ignore_job("deploy-manual", patterns) is True
    assert should_ignore_job("skip-build", patterns) is True
    assert should_ignore_job("test-skip", patterns) is True
    assert should_ignore_job("skip-build-extra", patterns) is True
    assert should_ignore_job("extra-skip", patterns) is True

    # Should not be ignored
    assert should_ignore_job("auto-deploy", patterns) is False
    assert should_ignore_job("build-auto", patterns) is False


def test_should_ignore_job_invalid_patterns():
    """Test that invalid regex patterns are handled gracefully"""
    patterns = ["valid-pattern", "[invalid-regex", "another-valid"]

    # Should still work with valid patterns
    assert should_ignore_job("valid-pattern", patterns) is True
    assert should_ignore_job("another-valid", patterns) is True

    # Should not be ignored for non-matching patterns
    assert should_ignore_job("different-pattern", patterns) is False


def test_should_ignore_job_exact_matches():
    """Test exact string matches"""
    patterns = ["^exact-match$", "^another-exact$"]

    assert should_ignore_job("exact-match", patterns) is True
    assert should_ignore_job("another-exact", patterns) is True
    assert should_ignore_job("exact-match-extra", patterns) is False
    assert should_ignore_job("prefix-exact-match", patterns) is False
