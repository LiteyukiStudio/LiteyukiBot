import pip


def install(plugin_name) -> bool:
    try:
        pip.main(['install', plugin_name])
        return True
    except Exception as e:
        print(e)
        return False
