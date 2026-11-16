"""Let only Home Assistant's ingress reach the remote view.

As an add-on the remote view has no password of its own: Home Assistant
authenticates the person and forwards the connection from one fixed address.
Every add-on shares a network, though, so without this any other add-on
could open the logged-in browser directly.
"""
import asyncio
import sys

INGRESS_ADDRESS = "172.30.32.2"


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


async def main(listen_port: int, target_port: int, allowed: str) -> None:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")[0]
        if peer.removeprefix("::ffff:") != allowed:
            writer.close()
            return
        try:
            up_reader, up_writer = await asyncio.open_connection("127.0.0.1", target_port)
        except OSError:
            writer.close()
            return
        await asyncio.gather(pipe(reader, up_writer), pipe(up_reader, writer))

    server = await asyncio.start_server(handle, None, listen_port)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else INGRESS_ADDRESS))
