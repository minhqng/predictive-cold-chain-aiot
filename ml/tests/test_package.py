"""Import smoke test for the ML skeleton package."""


def test_package_imports():
    import coldguard_ml

    assert coldguard_ml.__version__ == "0.1.0"
