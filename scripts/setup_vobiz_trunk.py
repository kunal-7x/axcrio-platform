import asyncio
import os

from dotenv import load_dotenv
from livekit import api as livekit_api


load_dotenv(".env.local", override=True)
load_dotenv()


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def require_first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    raise RuntimeError(f"Missing required environment variable: {' or '.join(names)}")


def sip_transport() -> livekit_api.SIPTransport.ValueType:
    value = os.getenv("VOBIZ_SIP_TRANSPORT", "udp").lower()
    transports = {
        "auto": livekit_api.SIPTransport.SIP_TRANSPORT_AUTO,
        "udp": livekit_api.SIPTransport.SIP_TRANSPORT_UDP,
        "tcp": livekit_api.SIPTransport.SIP_TRANSPORT_TCP,
        "tls": livekit_api.SIPTransport.SIP_TRANSPORT_TLS,
    }
    if value not in transports:
        raise RuntimeError("VOBIZ_SIP_TRANSPORT must be one of: auto, udp, tcp, tls")
    return transports[value]


async def main() -> None:
    lk = livekit_api.LiveKitAPI(
        url=require_env("LIVEKIT_URL"),
        api_key=require_env("LIVEKIT_API_KEY"),
        api_secret=require_env("LIVEKIT_API_SECRET"),
    )

    try:
        trunk = await lk.sip.create_outbound_trunk(
            livekit_api.CreateSIPOutboundTrunkRequest(
                trunk=livekit_api.SIPOutboundTrunkInfo(
                    name="Vobiz Trunk",
                    address=require_env("VOBIZ_SIP_DOMAIN"),
                    transport=sip_transport(),
                    auth_username=require_first_env("VOBIZ_USERNAME", "VOBIZ_AUTH_ID"),
                    auth_password=require_first_env("VOBIZ_PASSWORD", "VOBIZ_AUTH_TOKEN"),
                    numbers=[require_env("VOBIZ_PHONE_NUMBER")],
                )
            )
        )
        print(f"LIVEKIT_SIP_TRUNK_ID={trunk.sip_trunk_id}")
    finally:
        await lk.aclose()


if __name__ == "__main__":
    asyncio.run(main())
