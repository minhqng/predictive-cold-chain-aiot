"""Launch the portable Leader gateway with explicit local commissioning options."""
import argparse
import os

from integration.leader_portable_stack import resolve_runtime_config, select_serial_port
from scripts.leader_serial_gateway import main as gateway_main


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator-console", action="store_true",
                        help="allow a local, single-use commissioning grant")
    args = parser.parse_args()
    config = resolve_runtime_config()
    selection = select_serial_port(config)
    if not selection.get("port"):
        parser.error("serial port unavailable or ambiguous; set COLDGUARD_SERIAL_PORT")
    argv = [
        "--serial-port", selection["port"], "--device-id", config.device_id,
        "--broker-host", os.environ.get("MQTT_HOST", config.broker_host),
        "--broker-port", os.environ.get("MQTT_PORT", str(config.broker_port)),
        "--enable-downlink", "--device-envelope",
    ]
    if args.operator_console:
        argv.append("--operator-console")
    return gateway_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
