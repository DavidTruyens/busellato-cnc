"""Identity probe: is the nesting tool running on this port?

    python -m nesting.ping PORT

Exit code 0: the nesting tool answers; 1: nothing listens; 2: something
else listens.  Used by the launchers.  Stdlib only and light: it does not
import the server.
"""
import json
import socket
import sys
import urllib.request

APP = 'nesting'  # must match nesting.server.APP

RUNNING = 0
FREE = 1
OTHER = 2


def probe(port, timeout=3.0):
    if not isinstance(port, int) or not 0 < port < 65536:
        return OTHER
    try:
        socket.create_connection(('127.0.0.1', port), timeout).close()
    except (OverflowError, ValueError):  # not a usable port number
        return OTHER
    except OSError:
        return FREE
    try:
        url = f'http://127.0.0.1:{port}/api/ping'
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=timeout) as r:
            body = json.loads(r.read(65536).decode('utf-8'))
        if isinstance(body, dict) and body.get('app') == APP:
            return RUNNING
    except Exception:  # HTTP errors, resets, bad JSON, timeouts, BadStatusLine
        pass
    return OTHER


def main(argv):
    # Exit code 1 must only ever mean "free": anything odd returns OTHER.
    try:
        if len(argv) != 2:
            raise ValueError('wrong argument count')
        port = int(argv[1])
        if not 0 < port < 65536:
            raise ValueError('port out of range')
    except ValueError:
        print('usage: python -m nesting.ping PORT', file=sys.stderr)
        return OTHER
    try:
        code = probe(port)
        print({RUNNING: f'nesting tool runs on port {port}',
               FREE: f'port {port} is free',
               OTHER: f'port {port} is in use by another program'}[code])
        return code
    except Exception as e:
        print(f'ping failed: {e}', file=sys.stderr)
        return OTHER


if __name__ == '__main__':
    sys.exit(main(sys.argv))
