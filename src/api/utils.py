import os
import yaml
from nonebot import logger


def load_config() -> dict[str, any]:
    """
    Load config from config.yml
    :return:
    """
    config = {
            'host': '0.0.0.0',
            'port': 20216,
            'nickname': ['Liteyuki'],
            'command_start': [''],
    }

    if not os.path.exists('config.yml'):
        logger.warning('warn.config_file_not_found')
        with open('config.yml', 'w', encoding='utf-8') as f:
            f.write(yaml.dump(config, indent=4))
    else:
        try:
            with open('config.yml', 'r', encoding='utf-8') as f:
                config.update(yaml.load(f, Loader=yaml.FullLoader))
                logger.success('success.config_loaded')
            # 格式化后写入
            with open('config.yml', 'w', encoding='utf-8') as f:
                f.write(yaml.dump(config, indent=4))
        except Exception as e:
            logger.error(f'error.load_config: {e}')

    return config
