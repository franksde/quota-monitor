def test_package_imports():
    import quota_monitor
    assert quota_monitor.__version__

def test_module_runnable():
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "-m", "quota_monitor", "--help"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "quota_monitor" in result.stdout.lower()
