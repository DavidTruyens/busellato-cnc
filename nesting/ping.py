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
    try:
        socket.create_connection(('127.0.0.1', port), timeout).close()
    except OSError:
        return FREE
    try:
        url = f'http://127.0.0.1:{port}/api/ping'
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = json.loads(r.read().decode('utf-8'))
        if isinstance(body, dict) and body.get('app') == APP:
            return RUNNING
    except Exception:  # HTTP errors, resets, bad JSON, timeouts, BadStatusLine
        pass
    return OTHER


def main(argv):
    if len(argv) != 2:
        print('usage: python -m nesting.ping PORT', file=sys.stderr)
        return OTHER
    port = int(argv[1])
    code = probe(port)
    print({RUNNING: f'nesting tool runs on port {port}',
           FREE: f'port {port} is free',
           OTHER: f'port {port} is in use by another program'}[code])
    return code


if __name__ == '__main__':
    sys.exit(main(sys.argv))
