#!/usr/bin/env python3
"""Supervisor calls for the Home Assistant OS VM (dev/haos.sh), over the
websocket API. Needs aiohttp (it comes with Home Assistant's own packages).

    DEV_HA_URL=http://127.0.0.1:18124 DEV_HA_STATE=dev/haos python3 dev/haos_addon.py <method> <endpoint> [json]

Example: ... haos_addon.py post /store/repositories '{"repository": "https://github.com/miguelangel-nubla/hassio-repository"}'
"""
import asyncio
import json
import sys

import aiohttp

import dev


async def supervisor(method, endpoint, data=None, timeout=900):
    token = dev.access_token()
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(dev.URL.replace("http", "ws", 1) + "/api/websocket", max_msg_size=0) as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": token})
            await ws.receive_json()
            message = {"id": 1, "type": "supervisor/api", "endpoint": endpoint, "method": method, "timeout": timeout}
            if data is not None:
                message["data"] = data
            await ws.send_json(message)
            while True:
                reply = await ws.receive_json(timeout=timeout + 30)
                if reply.get("id") == 1:
                    return reply


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    payload = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
    result = asyncio.run(supervisor(sys.argv[1], sys.argv[2], payload))
    print(json.dumps(result.get("result") if result.get("success") else result, indent=1)[:6000])
