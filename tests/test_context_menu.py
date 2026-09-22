import pytest
from docrename.context_menu import (
    register_context_menu,
    unregister_context_menu,
    is_context_menu_registered
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
