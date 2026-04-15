from django.apps import AppConfig


class ClubConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'club'
    verbose_name = 'Basketball Club'

    def ready(self):
        import club.signals  # noqa