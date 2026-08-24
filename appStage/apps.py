from django.apps import AppConfig


class AppstageConfig(AppConfig):
    name = 'appStage'

    def ready(self):
        from . import signals  # noqa: F401
