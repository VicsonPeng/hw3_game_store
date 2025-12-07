import socket
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', type=str, required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--user', type=str, required=True)
    args = parser.parse_args()

    print(f"Connecting to {args.host}:{args.port} as {args.user}...")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((args.host, args.port))
        print("Connected! Game Client Running...")
        # TODO: Implement game logic here
        while True:
            pass
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == '__main__':
    main()