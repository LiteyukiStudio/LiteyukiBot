ASGI_DRIVER = "~fastapi"
HTTPX_DRIVER = "~httpx"
WEBSOCKETS_DRIVER = "~websockets"


def get_driver_string(*argv):
    output_string = ""
    if ASGI_DRIVER in argv:
        output_string += ASGI_DRIVER
    for arg in argv:
        if arg != ASGI_DRIVER:
            output_string = f"{output_string}+{arg}"
    return output_string


def get_driver_full_string(*argv):
    return f"DRIVER={get_driver_string(argv)}"
