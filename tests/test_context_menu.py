import pytest
from checkrename.context_menu import (
    register_context_menu,
    unregister_context_menu,
    is_context_menu_registered,
    is_win11_classic_menu_enabled,
    set_win11_classic_menu
)

def test_context_menu_lifecycle():
    # Проверяем регистрацию в HKCU
    initial_status = is_context_menu_registered()
    try:
        # Регистрируем
        res_reg = register_context_menu("Тест: Найти номер счета")
        assert res_reg is True
        assert is_context_menu_registered() is True

        # Удаляем
        res_unreg = unregister_context_menu()
        assert res_unreg is True
        assert is_context_menu_registered() is False
    finally:
        # Возвращаем исходное состояние
        if initial_status:
            register_context_menu()
        else:
            unregister_context_menu()


def test_win11_classic_menu_toggle():
    initial = is_win11_classic_menu_enabled()
    try:
        set_win11_classic_menu(True)
        assert is_win11_classic_menu_enabled() is True

        set_win11_classic_menu(False)
        assert is_win11_classic_menu_enabled() is False
    finally:
        set_win11_classic_menu(initial)


def test_autostart_lifecycle():
    from checkrename.context_menu import is_autostart_registered, set_autostart, get_launch_command
    initial = is_autostart_registered()
    try:
        assert set_autostart(True) is True
        assert is_autostart_registered() is True

        cmd = get_launch_command(file_arg_placeholder=False)
        assert "CheckRename" in cmd or "python" in cmd

        assert set_autostart(False) is True
        assert is_autostart_registered() is False
    finally:
        if initial:
            set_autostart(True)

