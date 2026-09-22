import time
import pytest
from PyQt6.QtWidgets import QApplication
from checkrename.single_instance import SingleInstance

# Инициализация QApplication для тестов QtNetwork
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_single_instance_lifecycle(qapp):
    received = []

    def on_msg(msg: str):
        received.append(msg)

    # 1. Первый экземпляр становится первичным
    inst1 = SingleInstance(on_message_received=on_msg)
    try:
        assert inst1.is_primary is True

        # 2. Второй экземпляр видит, что он не первичный
        inst2 = SingleInstance(on_message_received=None)
        try:
            assert inst2.is_primary is False
        finally:
            inst2.close()

        # 3. Отправляем сообщение первичному экземпляру (в отдельном потоке, как второй процесс)
        import threading
        results = []
        def sender():
            res = SingleInstance.send_message("SHOW_SETTINGS")
            results.append(res)

        t = threading.Thread(target=sender)
        t.start()

        # Даем Qt циклу обработать сокет
        start = time.time()
        while not received and time.time() - start < 2.0:
            qapp.processEvents()
            time.sleep(0.05)

        t.join()
        assert results and results[0] is True
        assert "SHOW_SETTINGS" in received
    finally:
        inst1.close()
