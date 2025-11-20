from core.config.components import ComponentsConfig
from core.config.envs.development import DevelopmentConfig
from core.config.envs.production import ProductionConfig


class ProductionSettings(ProductionConfig, ComponentsConfig):
    ...


class DevelopmentSettings(DevelopmentConfig, ComponentsConfig):
    ...


def get_settings() -> ProductionSettings | DevelopmentSettings:
    if ComponentsConfig().DEBUG:
        return DevelopmentSettings()
    return ProductionSettings()


settings = get_settings()
