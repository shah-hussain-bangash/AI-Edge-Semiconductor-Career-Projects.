"""Start only the loopback portal; optionally observe one explicit USB port."""
import argparse
import getpass
import os


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial-port", default="", help="e.g. /dev/cu.usbserial-0001")
    parser.add_argument("--bootstrap", action="store_true", help="Prompt for first local admin only")
    args = parser.parse_args()
    from usb_heartbeat import valid_port
    if args.serial_port and not valid_port(args.serial_port):
        parser.error("Expected a local USB serial port")
    os.environ["EDGEOPS_SERIAL_PORT"] = args.serial_port
    if args.bootstrap:
        os.environ["EDGEOPS_ADMIN_EMAIL"] = input("Local admin email: ").strip()
        os.environ["EDGEOPS_ADMIN_PASSWORD"] = getpass.getpass("New password (14+ characters): ")
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8765, workers=1)


if __name__ == "__main__":
    main()
