"""文件持久化存储 - JSON 格式存储 Session 数据"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .session import Session


class SessionStorage:
    """Session 文件持久化存储"""

    def __init__(self, storage_dir: str = "dm_agent/data/sessions"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_file(self, session_id: str) -> Path:
        return self.storage_dir / f"{session_id}.json"

    def save_session(self, session: "Session") -> bool:
        try:
            file_path = self._get_session_file(session.session_id)
            data = session.to_dict()
            
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            print(f"保存 session 失败: {e}")
            return False
    
    def load_session(self, session_id: str) -> Optional["Session"]:
        try:
            file_path = self._get_session_file(session_id)
            
            if not file_path.exists():
                return None
            
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            from .session import Session
            return Session.from_dict(data)
        except Exception as e:
            print(f"加载 session 失败: {e}")
            return None

    def delete_session(self, session_id: str) -> bool:
        try:
            file_path = self._get_session_file(session_id)
            
            if file_path.exists():
                file_path.unlink()
            
            return True
        except Exception as e:
            print(f"删除 session 失败: {e}")
            return False

    def list_sessions(self) -> List[str]:
        try:
            session_files = list(self.storage_dir.glob("*.json"))
            return [f.stem for f in session_files]
        except Exception as e:
            print(f"列出 sessions 失败: {e}")
            return []

    def session_exists(self, session_id: str) -> bool:
        return self._get_session_file(session_id).exists()

    def get_all_sessions(self) -> List["Session"]:
        from .session import Session
        sessions: List[Session] = []
        for session_id in self.list_sessions():
            session = self.load_session(session_id)
            if session:
                sessions.append(session)
        return sessions

    def clear_all(self) -> bool:
        try:
            for session_file in self.storage_dir.glob("*.json"):
                session_file.unlink()
            return True
        except Exception as e:
            print(f"清空所有 sessions 失败: {e}")
            return False

    def get_storage_stats(self) -> Dict[str, Any]:
        sessions = self.list_sessions()
        total_size = 0
        
        for session_id in sessions:
            file_path = self._get_session_file(session_id)
            if file_path.exists():
                total_size += file_path.stat().st_size
        
        return {
            "storage_dir": str(self.storage_dir),
            "session_count": len(sessions),
            "total_size_bytes": total_size,
            "total_size_kb": round(total_size / 1024, 2),
        }
