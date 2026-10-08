#!/bin/sh
# Send one real message from instance B (the client) to instance A (the
# contractor): an assignment request, queued in B's outbox, sent by B's
# worker through B's outway and A's inway, stored in A's inbox.
set -eu
here="$(cd "$(dirname "$0")" && pwd)"
dc() { docker compose -p grip-local -f "$here/compose.yml" -f "$here/compose.fsc.yml" --profile two "$@"; }

id="$(python3 -c 'import uuid;print(uuid.uuid4())')"
echo "message id: $id"

dc exec -T -e MSG_ID="$id" backend-b python - <<'PY'
import asyncio, json, os, uuid
from pathlib import Path

from sqlalchemy import select

import grip.federation.contract_loader as loader
from grip.core.database import async_session
from grip.federation.models import Peer
from grip.federation.outbox import enqueue


async def main() -> None:
    example = Path(loader.__file__).parent / "contract/examples/valid/opdrachtaanvraag.zonder-context.json"
    payload = json.loads(example.read_text())
    payload["id"] = os.environ["MSG_ID"]
    payload["opdracht_uri"] = f"http://localhost:9002/id/opdracht/{uuid.uuid4()}"
    payload["opdrachtgever"]["instantie_uri"] = "http://localhost:9002"
    payload["opdrachtnemer"]["instantie_uri"] = "http://localhost:9001"
    payload["opdrachtnemer"]["naam"] = "DigiGilde voorbeeld"
    async with async_session() as db:
        peer = (await db.execute(select(Peer).where(Peer.base_uri == "http://localhost:9001"))).scalar_one()
        row = await enqueue(db, peer, "sendAssignmentRequest", payload)
        await db.commit()
        print("queued in the outbox of B:", row.operation, row.status)


asyncio.run(main())
PY

echo "waiting for the worker of B..."
for _ in 1 2 3 4 5 6 7 8 9 10; do
    status="$(dc exec -T db-b psql -U grip -At -c "select status || ' http=' || coalesce(last_status_code::text,'-') || ' attempts=' || attempts || ' ' || coalesce(left(last_error,200),'') from federation_outbox where message_id='$id'")"
    case "$status" in sent*|rejected*|dead*) break ;; esac
    sleep 3
done
echo "outbox of B: $status"
echo "inbox of A:  $(dc exec -T db-a psql -U grip -At -c "select i.operation || ' from peer ' || p.peer_id || ' (' || p.name || '), received ' || i.received_at from federation_inbox i join peer p on p.id = i.peer_id where i.message_id='$id'")"
