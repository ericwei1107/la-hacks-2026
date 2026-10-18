import logging
import time
import threading
from analytics.observability import traced

from analytics.metrics import trend_values
from analytics.repository import FileRepository
from analytics.tigerdata.database import Database, connection
from analytics.tigerdata.trends import assemble, signature

logger = logging.getLogger('analytics.tigerdata')
RETRY_SECONDS = 30


class TigerRepository(FileRepository):
    def __init__(self, data_dir, url):
        super().__init__(data_dir)
        self.url = url
        self.retry_at = 0
        self.database_lock = threading.Lock()

    @traced('tigerdata.trends')
    def trends(self, player, character, stat=None):
        with self.lock:
            sessions = [entry for entry in self._sessions().values() if entry[2]['player'] == player and entry[2]['human_character'] == character]
        if not sessions:
            return assemble(player, character, [])
        stored = {}
        acquired = self.database_lock.acquire(blocking=False)
        try:
            if acquired and time.monotonic() >= self.retry_at:
                try:
                    with connection(self.url, api=True) as conn:
                        stored = Database(conn).trends([entry[2]['session_id'] for entry in sessions])
                    self.retry_at = 0
                except Exception:
                    self.retry_at = time.monotonic() + RETRY_SECONDS
                    logger.warning('Tiger Data trends unavailable; serving files; retrying after thirty seconds')
        finally:
            if acquired:
                self.database_lock.release()
        with self.lock:
            sessions = [entry for entry in self._sessions().values() if entry[2]['player'] == player and entry[2]['human_character'] == character]
            points = []
            for _, _, meta, recording in sessions:
                sid = meta['session_id']
                candidate = stored.get(sid)
                if candidate and candidate[0] == signature(self, meta, recording):
                    values = candidate[1]
                else:
                    _, records = self._records(recording, sid)
                    _, metrics = self._metrics(sid)
                    values = trend_values(meta, records, metrics)
                points.append((meta, values))
            return assemble(player, character, points, stat)
