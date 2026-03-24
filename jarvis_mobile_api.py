import json
import os
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from tg_codex_bridge import BotConfig, TelegramBridge, normalize_whitespace, truncate_text


DEFAULT_API_HOST = os.getenv('JARVIS_MOBILE_API_HOST', '127.0.0.1').strip() or '127.0.0.1'
DEFAULT_API_PORT = int((os.getenv('JARVIS_MOBILE_API_PORT', '8787') or '8787').strip())
DEFAULT_MOBILE_CHAT_ID = int((os.getenv('JARVIS_MOBILE_DEFAULT_CHAT_ID', '910000001') or '910000001').strip())


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding='utf-8', errors='ignore').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class MobileApiService:
    def __init__(self) -> None:
        load_env_file(Path(__file__).with_name('.env'))
        self.config = BotConfig()
        self.bridge = TelegramBridge(self.config)

    def list_conversations(self, limit: int = 30) -> List[Dict[str, Any]]:
        with self.bridge.state.db_lock:
            rows = self.bridge.state.db.execute(
                """
                SELECT
                    chat_id,
                    MAX(created_at) AS updated_at,
                    COALESCE(
                        MAX(CASE WHEN role = 'user' THEN text END),
                        MAX(text),
                        ''
                    ) AS preview,
                    SUM(CASE WHEN role = 'user' THEN 1 ELSE 0 END) AS user_messages,
                    SUM(CASE WHEN role = 'assistant' THEN 1 ELSE 0 END) AS assistant_messages
                FROM chat_history
                GROUP BY chat_id
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        result: List[Dict[str, Any]] = []
        for chat_id, updated_at, preview, user_messages, assistant_messages in rows:
            title = self._build_conversation_title(int(chat_id), preview or '')
            result.append(
                {
                    'id': str(chat_id),
                    'chat_id': int(chat_id),
                    'title': title,
                    'subtitle': truncate_text(preview or 'Empty conversation', 80),
                    'updated_at': int(updated_at or 0),
                    'user_messages': int(user_messages or 0),
                    'assistant_messages': int(assistant_messages or 0),
                }
            )
        return result

    def create_conversation(self, title: str = '') -> Dict[str, Any]:
        chat_id = self._next_chat_id()
        if title:
            self.bridge.state.append_history(chat_id, 'assistant', f'Conversation created: {normalize_whitespace(title)}')
        return {
            'id': str(chat_id),
            'chat_id': chat_id,
            'title': title.strip() or f'Conversation {chat_id}',
        }

    def get_messages(self, chat_id: int, limit: int = 80) -> List[Dict[str, Any]]:
        with self.bridge.state.db_lock:
            rows = self.bridge.state.db.execute(
                """
                SELECT id, role, text, created_at
                FROM chat_history
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ).fetchall()
        messages: List[Dict[str, Any]] = []
        for row_id, role, text, created_at in reversed(rows):
            messages.append(
                {
                    'id': str(row_id),
                    'role': role,
                    'text': text,
                    'created_at': int(created_at or 0),
                }
            )
        return messages

    def send_message(self, chat_id: int, text: str, user_id: Optional[int] = None) -> Dict[str, Any]:
        cleaned = normalize_whitespace(text)
        if not cleaned:
            raise ValueError('Message text is empty')
        effective_user_id = int(user_id or 0) or None
        self.bridge.state.append_history(chat_id, 'user', cleaned)
        self.bridge.state.record_event(
            chat_id,
            effective_user_id,
            'user',
            'mobile_text',
            cleaned,
            username='mobile',
            first_name='Mobile',
            last_name='User',
            chat_type='mobile',
        )
        answer = self.bridge.ask_codex(chat_id, cleaned)
        self.bridge.state.append_history(chat_id, 'assistant', answer)
        self.bridge.state.record_event(
            chat_id,
            None,
            'assistant',
            'mobile_answer',
            answer,
            chat_type='mobile',
        )
        return {
            'conversation': {
                'id': str(chat_id),
                'chat_id': chat_id,
                'title': self._build_conversation_title(chat_id, cleaned),
            },
            'assistant_message': {
                'role': 'assistant',
                'text': answer,
            },
            'messages': self.get_messages(chat_id, limit=60),
        }

    def _next_chat_id(self) -> int:
        with self.bridge.state.db_lock:
            row = self.bridge.state.db.execute(
                'SELECT MIN(chat_id) FROM chat_history WHERE chat_id >= ?',
                (DEFAULT_MOBILE_CHAT_ID,),
            ).fetchone()
        if not row or row[0] is None:
            return DEFAULT_MOBILE_CHAT_ID
        return int(row[0]) + 1

    def _build_conversation_title(self, chat_id: int, preview: str) -> str:
        cleaned = normalize_whitespace(preview)
        if cleaned:
            return truncate_text(cleaned, 42)
        return f'Conversation {chat_id}'


class MobileApiHandler(BaseHTTPRequestHandler):
    service: MobileApiService = None  # type: ignore[assignment]

    def do_OPTIONS(self) -> None:
        self._send_json({'ok': True}, status=HTTPStatus.NO_CONTENT)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/') or '/'
        query = parse_qs(parsed.query or '')
        try:
            if path == '/health':
                self._send_json({'ok': True, 'service': 'jarvis_mobile_api'})
                return
            if path == '/v1/conversations':
                limit = self._int_query(query, 'limit', default=30, minimum=1, maximum=100)
                self._send_json({'items': self.service.list_conversations(limit=limit)})
                return
            if path.startswith('/v1/conversations/') and path.endswith('/messages'):
                chat_id = int(path.split('/')[3])
                limit = self._int_query(query, 'limit', default=80, minimum=1, maximum=200)
                self._send_json({'items': self.service.get_messages(chat_id, limit=limit)})
                return
            self._send_json({'error': 'Not found'}, status=HTTPStatus.NOT_FOUND)
        except Exception as error:
            self._handle_error(error)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/') or '/'
        try:
            payload = self._read_json()
            if path == '/v1/conversations':
                title = normalize_whitespace(str(payload.get('title') or ''))
                self._send_json(self.service.create_conversation(title=title), status=HTTPStatus.CREATED)
                return
            if path == '/v1/chat/send':
                chat_id = int(payload.get('chat_id') or DEFAULT_MOBILE_CHAT_ID)
                text = str(payload.get('text') or '')
                user_id = payload.get('user_id')
                self._send_json(self.service.send_message(chat_id, text, user_id=user_id))
                return
            self._send_json({'error': 'Not found'}, status=HTTPStatus.NOT_FOUND)
        except Exception as error:
            self._handle_error(error)

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _read_json(self) -> Dict[str, Any]:
        raw_length = self.headers.get('Content-Length') or '0'
        length = int(raw_length)
        if length <= 0:
            return {}
        data = self.rfile.read(length)
        if not data:
            return {}
        return json.loads(data.decode('utf-8'))

    def _int_query(self, query: Dict[str, List[str]], key: str, default: int, minimum: int, maximum: int) -> int:
        raw = (query.get(key) or [''])[0].strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            return default
        return max(minimum, min(value, maximum))

    def _handle_error(self, error: Exception) -> None:
        status = HTTPStatus.BAD_REQUEST if isinstance(error, ValueError) else HTTPStatus.INTERNAL_SERVER_ERROR
        payload = {
            'error': str(error),
        }
        if status == HTTPStatus.INTERNAL_SERVER_ERROR:
            payload['trace'] = traceback.format_exc(limit=4)
        self._send_json(payload, status=status)

    def _send_json(self, payload: Dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(int(status))
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.end_headers()
        if status != HTTPStatus.NO_CONTENT:
            self.wfile.write(body)


def create_server(host: str = DEFAULT_API_HOST, port: int = DEFAULT_API_PORT) -> ThreadingHTTPServer:
    MobileApiHandler.service = MobileApiService()
    return ThreadingHTTPServer((host, port), MobileApiHandler)


def main() -> None:
    server = create_server()
    print(f'Jarvis mobile API listening on http://{DEFAULT_API_HOST}:{DEFAULT_API_PORT}')
    server.serve_forever()


if __name__ == '__main__':
    main()
