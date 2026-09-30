"""Import smoke test for the control skeleton package."""


def test_package_imports():
    import coldguard_control

    assert coldguard_control.__version__ == "0.1.0"
