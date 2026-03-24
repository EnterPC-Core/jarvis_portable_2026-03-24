export function mainKeyboard() {
  return {
    inline_keyboard: [
      [
        { text: 'Помощь', callback_data: 'help' },
        { text: 'Статус', callback_data: 'status' },
      ],
      [
        { text: 'Сброс памяти', callback_data: 'reset' },
        { text: 'Стиль ответа', callback_data: 'mode' },
      ],
      [
        { text: 'Поиск: auto', callback_data: 'search:auto' },
        { text: 'Поиск: off', callback_data: 'search:off' },
      ],
      [
        { text: 'Публичный доступ: on', callback_data: 'public:on' },
        { text: 'Публичный доступ: off', callback_data: 'public:off' },
      ],
      [
        { text: 'О боте', callback_data: 'about' },
        { text: 'Админ', callback_data: 'admin' },
      ],
    ],
  };
}
