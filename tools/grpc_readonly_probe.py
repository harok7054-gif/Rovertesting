#!/usr/bin/env python3
"""Query status and available motions without constructing RobotClient."""
import argparse
import json
import math


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", default="192.168.1.6:50051")
    parser.add_argument("--timeout", type=float, default=5)
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("timeout must be finite and positive")
    import grpc
    from dobot_quad.proto import grpc_service_pb2 as pb
    from dobot_quad.proto import grpc_service_pb2_grpc as pb_grpc
    with grpc.insecure_channel(args.address) as channel:
        stub = pb_grpc.gRPCServiceStub(channel)
        state = stub.GetRobotState(pb.GetRobotStateRequest(), timeout=args.timeout)
        motions = stub.GetAvailableMotions(pb.GetMotionsRequest(), timeout=args.timeout)
        result = {
            "address": args.address,
            "state_success": bool(state.success),
            "current_state": state.current_state,
            "current_speed_ratio": state.current_speed_ratio,
            "motions_success": bool(motions.success),
            "motions": [m.motion_id for m in motions.motions],
        }
        for name in ("robot_type", "obstacle_avoidance_enabled"):
            if hasattr(state, name):
                result[name] = getattr(state, name)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not state.success or not motions.success:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
