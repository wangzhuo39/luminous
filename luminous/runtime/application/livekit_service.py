from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import timedelta
from secrets import token_urlsafe
from typing import Any

from luminous.runtime.config import BackendConfig
from luminous.runtime.infrastructure.runtime_store import CompanionRuntimeStore


@dataclass(frozen=True)
class LiveKitConnection:
    session_id: str
    server_url: str
    participant_token: str
    room_name: str
    participant_identity: str

    def to_dict(self) -> dict[str, str]:
        return {
            "callSessionId": self.session_id,
            "serverUrl": self.server_url,
            "participantToken": self.participant_token,
            "roomName": self.room_name,
            "participantIdentity": self.participant_identity,
        }


class LiveKitService:
    def __init__(self, config: BackendConfig, store: CompanionRuntimeStore) -> None:
        self.config = config
        self.store = store

    def create_connection(self, *, session_digest: str, client: str = "android") -> LiveKitConnection:
        from livekit import api

        if not self.config.livekit_configured:
            raise ValueError("LiveKit is not configured")
        identity_suffix = (session_digest or token_urlsafe(18))[:24]
        participant_identity = f"user-{identity_suffix}"
        room_name = f"luminous-{token_urlsafe(18)}"
        session_id = f"voice_{token_urlsafe(18)}"
        metadata = json.dumps(
            {
                "voice_session_id": session_id,
                "client": client[:32],
            },
            ensure_ascii=True,
            separators=(",", ":"),
        )
        token = (
            api.AccessToken(self.config.livekit_api_key, self.config.livekit_api_secret)
            .with_identity(participant_identity)
            .with_name("Luminous companion user")
            .with_ttl(timedelta(minutes=10))
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                    can_publish_sources=["microphone"],
                )
            )
            .with_room_config(
                api.RoomConfiguration(
                    agents=[
                        api.RoomAgentDispatch(
                            agent_name=self.config.livekit_agent_name,
                            metadata=metadata,
                        )
                    ]
                )
            )
            .to_jwt()
        )
        self.store.create_voice_session(
            session_id=session_id,
            session_digest=session_digest,
            room_name=room_name,
            participant_identity=participant_identity,
            client=client[:32],
        )
        return LiveKitConnection(
            session_id=session_id,
            server_url=self.config.livekit_public_url or self.config.livekit_url,
            participant_token=token,
            room_name=room_name,
            participant_identity=participant_identity,
        )

    def read_session(self, session_id: str, *, session_digest: str = "") -> dict[str, Any] | None:
        session = self.store.read_voice_session(session_id, session_digest=session_digest)
        return self._public_session(session) if session else None

    def update_session(
        self,
        session_id: str,
        *,
        session_digest: str = "",
        status: str | None = None,
        metrics: dict[str, Any] | None = None,
        last_error: str | None = None,
    ) -> dict[str, Any] | None:
        session = self.store.update_voice_session(
            session_id,
            session_digest=session_digest,
            status=status,
            metrics=metrics,
            last_error=last_error,
        )
        return self._public_session(session) if session else None

    def end_session(self, session_id: str, *, session_digest: str = "") -> dict[str, Any] | None:
        session = self.store.read_voice_session(session_id, session_digest=session_digest)
        if session is None:
            return None
        room_deleted = bool(dict(session.get("metrics", {})).get("room_deleted", False))
        error = ""

        if self.config.livekit_configured and not room_deleted:
            try:
                asyncio.run(self._delete_room(str(session["room_name"])))
                room_deleted = True
            except Exception as exc:  # LiveKit may already have removed an empty room.
                error = str(exc)[:1000]
        updated = self.store.update_voice_session(
            session_id,
            session_digest=session_digest,
            status="ended",
            metrics={"room_deleted": room_deleted},
            last_error=error,
        )
        return self._public_session(updated) if updated else None

    async def _delete_room(self, room_name: str) -> None:
        from livekit import api

        async with api.LiveKitAPI(
            url=self.config.livekit_url,
            api_key=self.config.livekit_api_key,
            api_secret=self.config.livekit_api_secret,
        ) as client:
            await client.room.delete_room(api.DeleteRoomRequest(room=room_name))

    @staticmethod
    def _public_session(session: dict[str, Any]) -> dict[str, Any]:
        return {
            "callSessionId": str(session.get("session_id", "")),
            "roomName": str(session.get("room_name", "")),
            "participantIdentity": str(session.get("participant_identity", "")),
            "client": str(session.get("client", "")),
            "status": str(session.get("status", "")),
            "createdAt": str(session.get("created_at", "")),
            "updatedAt": str(session.get("updated_at", "")),
            "connectedAt": str(session.get("connected_at", "")),
            "endedAt": str(session.get("ended_at", "")),
            "lastError": str(session.get("last_error", "")),
            "metrics": dict(session.get("metrics", {})),
        }
