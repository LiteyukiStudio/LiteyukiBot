from liteyukibot import Daemon, config

if __name__ == "__main__":
    daemon = Daemon(**config.load_from_yaml("config.yaml") or {})
    daemon.run()
