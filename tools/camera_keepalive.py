#!/usr/bin/env python3
"""Keep a Rover camera session open. Uses the existing camera SDK environment."""
import argparse
import signal
import threading


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", default="192.168.1.6:50051")
    args = parser.parse_args()
    from dobot_quad import CameraId, RobotClient
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    robot = None
    opened = False
    camera = CameraId.FRONT_RGB
    try:
        robot = RobotClient(args.address)
        uri = robot.video.open(camera)
        opened = True
        print("RTSP:", uri, flush=True)
        print("Keep this process running. Ctrl+C closes the session.", flush=True)
        stop.wait()
    finally:
        if robot is not None:
            try:
                if opened:
                    robot.video.close(camera)
            finally:
                robot.close()


if __name__ == "__main__":
    main()
