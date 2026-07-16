import asyncio, os, sys
from livekit import api as L
def tr():
    v=os.getenv("VOBIZ_SIP_TRANSPORT","udp").lower()
    return {"auto":L.SIPTransport.SIP_TRANSPORT_AUTO,"udp":L.SIPTransport.SIP_TRANSPORT_UDP,
            "tcp":L.SIPTransport.SIP_TRANSPORT_TCP,"tls":L.SIPTransport.SIP_TRANSPORT_TLS}[v]
async def main():
    lk=L.LiveKitAPI(url=os.environ["LIVEKIT_URL"],api_key=os.environ["LIVEKIT_API_KEY"],api_secret=os.environ["LIVEKIT_API_SECRET"])
    try:
        # reuse existing Vobiz trunk if already created, else make one
        existing=await lk.sip.list_sip_outbound_trunk(L.ListSIPOutboundTrunkRequest())
        for t in existing.items:
            if t.name=="Vobiz Trunk":
                print("TRUNK_ID="+t.sip_trunk_id+" (existing)"); return
        t=await lk.sip.create_outbound_trunk(L.CreateSIPOutboundTrunkRequest(trunk=L.SIPOutboundTrunkInfo(
            name="Vobiz Trunk", address=os.environ["VOBIZ_SIP_DOMAIN"], transport=tr(),
            auth_username=os.environ.get("VOBIZ_USERNAME") or os.environ.get("VOBIZ_AUTH_ID"),
            auth_password=os.environ.get("VOBIZ_PASSWORD") or os.environ.get("VOBIZ_AUTH_TOKEN"),
            numbers=[os.environ["VOBIZ_PHONE_NUMBER"]])))
        print("TRUNK_ID="+t.sip_trunk_id+" (created)")
    finally:
        await lk.aclose()
asyncio.run(main())
