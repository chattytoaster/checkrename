import sys
import os
import ctypes
from typing import Callable, Optional
from PyQt6.QtCore import QObject
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

IPC_SERVER_NAME = "CheckRename_SingleInstance_IPC_v1"
MUTEX_NAME = "CheckRename_SingleInstance_Mutex_v1"
ERROR_ALREADY_EXISTS = 183


class SingleInstance(QObject):
    """
    Управляет гарантией единственного экземпляра приложения CheckRename.
    Предотвращает появление нескольких значков в трее и передает команды
    (например, открытие окна настроек) в уже работающий процесс.
    """

    def __init__(self, on_message_received: Optional[Callable[[str], None]] = None, parent=None):
        super().__init__(parent)
        self.on_message_received = on_message_received
        self._mutex = None
        self._server: Optional[QLocalServer] = None
        self._is_primary = False

        self._check_primary()

    def _check_primary(self):
        # 1. Проверяем именованный мьютекс Windows
        if sys.platform == "win32":
            try:
                self._mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
                last_error = ctypes.windll.kernel32.GetLastError()
                if last_error == ERROR_ALREADY_EXISTS:
                    self._is_primary = False
                    return
            except Exception:
                pass

        # 2. Проверяем возможность подключения к существующему сокету
        socket = QLocalSocket()
        socket.connectToServer(IPC_SERVER_NAME)
        if socket.waitForConnected(500):
            socket.disconnectFromServer()
            self._is_primary = False
            return

        # 3. Этот процесс является первичным экземпляром
        self._is_primary = True
        self._start_server()

    def _start_server(self):
        QLocalServer.removeServer(IPC_SERVER_NAME)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        self._server.listen(IPC_SERVER_NAME)

    def _on_new_connection(self):
        if not self._server:
            return
        client_socket = self._server.nextPendingConnection()
        if not client_socket:
            return
        client_socket.setParent(self)

        def read_data():
            try:
                data = bytes(client_socket.readAll()).decode("utf-8")
                if data and self.on_message_received:
                    self.on_message_received(data.strip())
            except Exception as e:
                print(f"Ошибка при чтении команды IPC: {e}")
            finally:
                client_socket.disconnectFromServer()

        if client_socket.bytesAvailable() > 0:
            read_data()
        else:
            client_socket.readyRead.connect(read_data)

    def close(self):
        """Освобождает сервер и системные дескрипторы."""
        if self._server:
            try:
                self._server.close()
                QLocalServer.removeServer(IPC_SERVER_NAME)
            except Exception:
                pass
            self._server = None

        if self._mutex and sys.platform == "win32":
            try:
                ctypes.windll.kernel32.CloseHandle(self._mutex)
            except Exception:
                pass
            self._mutex = None

    @property
    def is_primary(self) -> bool:
        return self._is_primary

    @classmethod
    def send_message(cls, message: str, timeout_ms: int = 1500) -> bool:
        """
        Отправляет строковое сообщение работающему первичному экземпляру.
        Возвращает True, если сообщение успешно передано.
        """
        socket = QLocalSocket()
        socket.connectToServer(IPC_SERVER_NAME)
        if not socket.waitForConnected(timeout_ms):
            return False

        socket.write(message.encode("utf-8"))
        socket.flush()
        socket.waitForBytesWritten(timeout_ms)
        import time
        time.sleep(0.1)
        socket.disconnectFromServer()
        return True
