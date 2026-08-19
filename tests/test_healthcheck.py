from healthcheck.__main__ import _systemctl_active


class Result:
    returncode = 0
    stdout = "active\n"
    stderr = ""


def test_systemctl_active(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return Result()

    monkeypatch.setattr("healthcheck.__main__.subprocess.run", run)
    assert _systemctl_active("wbozon-inventory.service") == (True, "active")
    assert calls == [["systemctl", "is-active", "wbozon-inventory.service"]]
